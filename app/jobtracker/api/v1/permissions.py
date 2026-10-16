from constance import config
from rest_framework import permissions, status
from rest_framework.exceptions import APIException


class ServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "CHAOTICA is in maintenance mode. Please try again later."
    default_code = "maintenance"


class MaintenanceModePermission(permissions.BasePermission):
    """503 for everyone but superusers while ``MAINTENANCE_MODE`` is on.

    Runs as a permission (after DRF authentication) because the site
    middleware can't see token / bearer users; the middleware skips
    ``/api/v1/`` and defers to this.
    """

    def has_permission(self, request, view):
        if not config.MAINTENANCE_MODE:
            return True
        if getattr(request.user, "is_superuser", False):
            return True
        raise ServiceUnavailable()


class OAuth2ScopeIfBearer(permissions.BasePermission):
    """OAuth2 bearer tokens need ``read`` (safe methods) or ``write``.

    Only applies to django-oauth-toolkit access tokens: session and DRF-token
    callers are unaffected (stock ``TokenHasScope`` would 403 the former and
    error on the latter).
    """

    def has_permission(self, request, view):
        try:
            from oauth2_provider.models import AbstractAccessToken
        except ImportError:  # OAuth2 not installed
            return True
        token = request.auth
        if not isinstance(token, AbstractAccessToken):
            return True
        scope = "read" if request.method in permissions.SAFE_METHODS else "write"
        return token.is_valid([scope])
