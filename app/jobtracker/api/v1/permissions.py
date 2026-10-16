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
