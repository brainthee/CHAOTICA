"""
ASGI config for chaotica project.

It exposes the ASGI callable as a module-level variable named ``application``.

HTTP is served by Django as usual; WebSocket connections are routed through
Channels to the scheduler consumers (live schedule delta updates).

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "chaotica.settings")

# Initialise Django (populate apps) before importing anything that touches models.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.auth import AuthMiddlewareStack  # noqa: E402

from chaotica_utils.ws_auth import WsAuthMiddleware  # noqa: E402
from jobtracker.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # Origin is checked against this site, not ALLOWED_HOSTS (which is a
        # wildcard in most deployments) — see chaotica_utils/ws_auth.py.
        "websocket": AuthMiddlewareStack(
            WsAuthMiddleware(URLRouter(websocket_urlpatterns))
        ),
    }
)
