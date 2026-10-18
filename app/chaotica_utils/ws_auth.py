"""WebSocket handshake guard.

Session cookies are ``SameSite=None`` in production, so a browser on any site
will attach them to a WebSocket it opens to us. Unlike HTTP there is no CORS or
CSRF on a WebSocket handshake — only the ``Origin`` header tells us who opened
it. A cookie-authenticated connection is therefore accepted only when its
Origin is this site (same host as the request, or listed in
``CSRF_TRUSTED_ORIGINS``).

Clients that can't send the cookie (OAuth2 apps) connect with a single-use
``?ticket=`` instead (``chaotica_utils.realtime``). A ticket is the
credential, so it needs no Origin check — and replaces the cookie user.

Sits inside ``AuthMiddlewareStack`` in ``chaotica/asgi.py``.
"""

from urllib.parse import parse_qs, urlsplit

from channels.db import database_sync_to_async

from channels.security.websocket import WebsocketDenier
from django.conf import settings


def _header(scope, name):
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin1")
    return None


def _hostname(value):
    if not value:
        return None
    # Host headers have no scheme; give urlsplit one so it parses the netloc.
    if "//" not in value:
        value = "//" + value
    try:
        return (urlsplit(value).hostname or "").lower() or None
    except ValueError:
        return None


def origin_allowed(scope):
    origin = _header(scope, b"origin")
    if origin is None:
        # Browsers always send Origin on a WebSocket handshake; a client that
        # doesn't isn't a browser being driven by another site.
        return True
    origin = origin.strip()
    trusted = {
        o.rstrip("/").lower() for o in getattr(settings, "CSRF_TRUSTED_ORIGINS", [])
    }
    if origin.rstrip("/").lower() in trusted:
        return True
    origin_host = _hostname(origin)
    if not origin_host:
        return False
    # Compare hostnames only: nginx forwards ``$host``, which drops the port.
    request_hosts = {
        _hostname(_header(scope, b"host")),
        _hostname(_header(scope, b"x-forwarded-host")),
    } - {None}
    return origin_host in request_hosts


@database_sync_to_async
def _ticket_user(raw):
    from .models import User
    from .realtime import redeem_ticket

    user_id = redeem_ticket(raw)
    if user_id is None:
        return None
    return User.objects.filter(pk=user_id, is_active=True).first()


def _ticket(scope):
    query = parse_qs(scope.get("query_string", b"").decode("latin1"))
    values = query.get("ticket")
    return values[0] if values else None


class WsAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            ticket = _ticket(scope)
            if ticket is not None:
                user = await _ticket_user(ticket)
                if user is None:
                    return await WebsocketDenier()(scope, receive, send)
                scope = {**scope, "user": user, "ws_ticket": True}
            elif not origin_allowed(scope):
                # Reject the handshake (HTTP 403) before any consumer runs.
                return await WebsocketDenier()(scope, receive, send)
        return await self.inner(scope, receive, send)
