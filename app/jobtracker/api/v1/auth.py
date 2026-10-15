from constance import config
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.exceptions import PermissionDenied
from rest_framework.throttling import ScopedRateThrottle

from .base import ApiV1Mixin
from .permissions import MaintenanceModePermission


class ThrottledObtainAuthToken(ApiV1Mixin, ObtainAuthToken):
    """POST username/password -> DRF token.

    It is a password login, so it obeys the same switch as the login page
    (``LOCAL_LOGIN_ENABLED``) and is rate limited per client IP.
    """

    permission_classes = [MaintenanceModePermission]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_token"

    def post(self, request, *args, **kwargs):
        if not config.LOCAL_LOGIN_ENABLED:
            raise PermissionDenied("Local (password) login is disabled.")
        return super().post(request, *args, **kwargs)
