import ipaddress
import re
from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware as DjSessionMiddleware
from django.core.exceptions import DisallowedHost
from django.http import HttpResponseBadRequest


class SessionMiddleware(DjSessionMiddleware):
    def __init__(self, get_response):
        super().__init__(get_response)
        # Define trusted proxy networks
        self.trusted_proxies = getattr(settings, 'TRUSTED_PROXIES', [])
        self.compiled_trusted_proxies = []
        
        # Compile trusted proxy networks for efficient checking
        for proxy in self.trusted_proxies:
            try:
                self.compiled_trusted_proxies.append(ipaddress.ip_network(proxy, strict=False))
            except ValueError:
                # Log warning about invalid proxy configuration
                pass
        
        # Get allowed hosts from settings
        self.allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
        
        # Compile regex patterns for wildcard domains
        self.allowed_host_patterns = []
        for host in self.allowed_hosts:
            if host == '*':
                # Allow all hosts (not recommended for production)
                self.allowed_host_patterns.append(re.compile(r'.*'))
            elif host.startswith('.'):
                # Wildcard subdomain (e.g., '.example.com')
                pattern = re.escape(host).replace(r'\.', r'\.?')
                self.allowed_host_patterns.append(re.compile(f'^(.+{pattern}|{pattern[2:]})$', re.IGNORECASE))
            elif '*' in host:
                # Handle other wildcard patterns
                pattern = re.escape(host).replace(r'\*', r'[^.]*')
                self.allowed_host_patterns.append(re.compile(f'^{pattern}$', re.IGNORECASE))
            else:
                # Exact match
                self.allowed_host_patterns.append(re.compile(f'^{re.escape(host)}$', re.IGNORECASE))

    def validate_host(self, request):
        """
        Validate the HTTP_HOST header against ALLOWED_HOSTS.
        Returns True if valid, False otherwise.
        """
        host = request.META.get('HTTP_HOST')
        
        # If no HOST header, check if we should allow it
        if not host:
            # You can decide whether to allow requests without HOST header
            # For HTTP/1.0 compatibility, you might want to allow it
            return getattr(settings, 'ALLOW_EMPTY_HOST', False)
        
        # Remove port if present
        if ':' in host:
            host_parts = host.rsplit(':', 1)
            host = host_parts[0]
            # Validate port number if present
            try:
                port = int(host_parts[1])
                if not (1 <= port <= 65535):
                    return False
            except (ValueError, IndexError):
                return False
        
        # Remove brackets from IPv6 addresses
        if host.startswith('[') and host.endswith(']'):
            host = host[1:-1]
            # Validate IPv6 address
            try:
                ipaddress.IPv6Address(host)
            except ValueError:
                return False
        
        # Check for null bytes or other invalid characters
        if '\x00' in host or '\n' in host or '\r' in host:
            return False
        
        # Validate against allowed hosts
        if not self.allowed_hosts:
            # If ALLOWED_HOSTS is empty and DEBUG is False, reject
            if not settings.DEBUG:
                return False
            # In DEBUG mode with empty ALLOWED_HOSTS, allow localhost variants
            return host in ['localhost', '127.0.0.1', '[::1]']
        
        # Check against allowed host patterns
        for pattern in self.allowed_host_patterns:
            if pattern.match(host):
                return True
        
        # Also check raw IP addresses if they're in ALLOWED_HOSTS
        try:
            ip = ipaddress.ip_address(host)
            return str(ip) in self.allowed_hosts
        except ValueError:
            # Not an IP address, that's fine
            pass
        
        return False

    def get_client_ip(self, request):
        """
        Securely extract the real client IP address from request headers.
        Only trusts proxy headers when the request comes from a trusted proxy.
        """
        # Get the immediate client IP (could be proxy or real client)
        remote_addr = request.META.get('REMOTE_ADDR')
        if not remote_addr:
            return None
            
        try:
            remote_ip = ipaddress.ip_address(remote_addr)
        except ValueError:
            return None
        
        # If no trusted proxies configured, return the direct connection IP
        if not self.compiled_trusted_proxies:
            return str(remote_ip)
        
        # Check if the request is coming from a trusted proxy
        is_trusted_proxy = any(
            remote_ip in trusted_network 
            for trusted_network in self.compiled_trusted_proxies
        )
        
        if not is_trusted_proxy:
            # Request is not from a trusted proxy, return the direct IP
            return str(remote_ip)
        
        # Request is from trusted proxy, check forwarded headers in order of preference
        forwarded_headers = [
            'HTTP_X_FORWARDED_FOR',      # Most common
            'HTTP_X_REAL_IP',            # Nginx
            'HTTP_CF_CONNECTING_IP',     # Cloudflare
            'HTTP_X_CLIENT_IP',          # Some proxies
            'HTTP_FORWARDED',            # RFC 7239 standard
        ]
        
        for header in forwarded_headers:
            header_value = request.META.get(header)
            if header_value:
                # Handle comma-separated IPs (X-Forwarded-For can contain multiple IPs)
                if header == 'HTTP_X_FORWARDED_FOR':
                    # Take the first IP (leftmost = original client)
                    ip_list = [ip.strip() for ip in header_value.split(',')]
                    client_ip = self._validate_ip(ip_list[0])
                elif header == 'HTTP_FORWARDED':
                    # RFC 7239 format: for=192.168.1.1;proto=https
                    client_ip = self._parse_forwarded_header(header_value)
                else:
                    client_ip = self._validate_ip(header_value.strip())
                
                if client_ip:
                    return client_ip
        
        # Fallback to direct connection IP if no valid forwarded IP found
        return str(remote_ip)
    
    def _validate_ip(self, ip_string):
        """Validate and return IP address string, or None if invalid."""
        try:
            ip = ipaddress.ip_address(ip_string)
            # Reject private/local IPs when they come from headers
            # (these could be spoofed internal addresses)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return None
            return str(ip)
        except ValueError:
            return None
    
    def _parse_forwarded_header(self, forwarded_value):
        """Parse RFC 7239 Forwarded header to extract client IP."""
        # Simple parser for "for=" parameter
        for part in forwarded_value.split(';'):
            part = part.strip()
            if part.startswith('for='):
                ip_part = part[4:].strip('"')
                # Handle IPv6 brackets
                if ip_part.startswith('[') and ip_part.endswith(']'):
                    ip_part = ip_part[1:-1]
                return self._validate_ip(ip_part)
        return None

    def process_request(self, request):
        # Validate HTTP_HOST header first
        if not self.validate_host(request):
            # Log the invalid host attempt if you have logging configured
            # logger.warning(f"Invalid HTTP_HOST header: {request.META.get('HTTP_HOST')}")
            
            # Return a 400 Bad Request for invalid host headers
            return HttpResponseBadRequest(
                "Invalid HTTP_HOST header",
                content_type="text/plain"
            )
        
        # Get the real client IP using secure method
        client_ip = self.get_client_ip(request)
        
        session_key = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
        request.session = self.SessionStore(
            ip=client_ip,
            user_agent=request.headers.get("User-Agent", ""),
            session_key=session_key,
        )