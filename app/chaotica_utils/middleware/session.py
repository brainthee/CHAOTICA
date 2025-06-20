import ipaddress
from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware as DjSessionMiddleware


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
        # Get the real client IP using secure method
        client_ip = self.get_client_ip(request)
        
        session_key = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
        request.session = self.SessionStore(
            ip=client_ip,
            user_agent=request.headers.get("User-Agent", ""),
            session_key=session_key,
        )