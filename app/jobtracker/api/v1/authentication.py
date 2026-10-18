"""Authentication for /api/v1/: OAuth2 bearer, DRF token, session — in that
order, so a bearer token always wins over an ambient session cookie."""

from constance import config
from oauth2_provider.contrib.rest_framework import OAuth2Authentication
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class ActiveUserOAuth2Authentication(OAuth2Authentication):
    """django-oauth-toolkit bearer tokens, only while ``API_OAUTH2_ENABLED``,
    and never for deactivated accounts (DOT doesn't check ``is_active``)."""

    def authenticate(self, request):
        if not config.API_OAUTH2_ENABLED:
            return None
        result = super().authenticate(request)
        if result is not None and not result[0].is_active:
            raise AuthenticationFailed("User inactive or deleted.")
        return result


API_V1_AUTHENTICATION = [
    ActiveUserOAuth2Authentication,
    TokenAuthentication,
    SessionAuthentication,
]


try:  # document the bearer scheme in the OpenAPI schema
    from drf_spectacular.contrib.django_oauth_toolkit import DjangoOAuthToolkitScheme

    class ActiveUserOAuth2Scheme(DjangoOAuthToolkitScheme):
        target_class = "jobtracker.api.v1.authentication.ActiveUserOAuth2Authentication"

except ImportError:  # pragma: no cover
    pass
