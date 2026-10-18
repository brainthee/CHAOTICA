from django.http import (
    HttpResponseForbidden,
    HttpResponse,
    HttpResponseRedirect,
    JsonResponse,
)
from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone as dj_timezone
from django.shortcuts import reverse, redirect, resolve_url
from urllib.parse import urlparse
from django.contrib.auth.models import AnonymousUser
from ..models import User
from django.urls import reverse
from django.conf import settings
from django.core.cache import cache
from constance import config
from django.contrib import messages
from django.contrib.messages import get_messages
import zoneinfo
from contextvars import ContextVar

# The request being served, and an optional explicit user override (tests,
# consumers, management commands). ContextVars rather than thread-locals so the
# value follows the request across asgiref's sync/async hops and never leaks
# between concurrent requests sharing a thread.
API_V1_PREFIX = "/api/v1/"

_current_request = ContextVar("chaotica_current_request", default=None)
_UNSET = object()
_current_user_override = ContextVar("chaotica_current_user", default=_UNSET)


def get_current_request():
    return _current_request.get()


def get_current_user():
    """The user acting in this context, or None (anonymous, cron, Celery, shell).

    Read lazily from the request so users authenticated later than middleware
    (DRF token/OAuth2 users — DRF writes ``request.user`` through to the
    underlying HttpRequest) and impersonated users are both seen.
    """
    override = _current_user_override.get()
    if override is not _UNSET:
        return override
    request = _current_request.get()
    user = getattr(request, "user", None) if request is not None else None
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return user


def get_current_impersonator():
    """The real user behind an impersonation session, else None."""
    request = _current_request.get()
    return getattr(request, "impersonator", None) if request is not None else None


def set_current_user(user):
    """Explicitly set the acting user; ``None`` clears the override."""
    _current_user_override.set(_UNSET if user is None else user)


class EnsureUserMiddleware:
    """Guarantees ``request.user`` exists.

    Requests that fail before AuthenticationMiddleware runs (e.g. a malformed
    Host header rejected by Django's CommonMiddleware) still trigger error-page
    rendering. Our base template runs ``{% generate_menu %}`` whose checks
    dereference ``request.user``, so without a user attribute the error page
    raises a secondary AttributeError (turning a benign 400 into noisy 500s —
    the bulk of which come from vulnerability scanners sending junk hosts).

    Seed an AnonymousUser early so error pages render cleanly. For normal
    requests AuthenticationMiddleware overwrites this with the real lazy user.
    Must be ordered before SecurityMiddleware/CommonMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not hasattr(request, "user"):
            request.user = AnonymousUser()
        return self.get_response(request)


class HealthCheckMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.META["PATH_INFO"] == "/ping":
            return HttpResponse("pong!")


class NewInstallMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Check if setup is needed - check for all essential components.
        # Cache the result so we don't run 5 COUNT queries on every request.
        setup_needed = cache.get("chaotica_setup_needed")
        if setup_needed is None:
            # Setup is "needed" only on a genuinely fresh install (no users).
            # Empty clients/services/skills is a legitimate operating state and
            # must NOT force the whole app into the wizard (which previously
            # caused an app-wide lockout and an unauthenticated login bypass).
            setup_needed = User.objects.count() == 0
            if not setup_needed:
                # Setup complete — cache indefinitely (cleared on server restart)
                cache.set("chaotica_setup_needed", False, None)
            else:
                # Re-check on next request (don't cache True for long)
                cache.set("chaotica_setup_needed", True, 5)

        excluded_paths = ["/media", "/static", "/admin", "/setup"]
        for path in excluded_paths:
            if request.path.startswith(path):
                return

        # Check if local login is disabled
        if not config.LOCAL_LOGIN_ENABLED:
            if request.method == "POST" and request.path == "/auth/login/":
                # Nuh huh!
                return HttpResponseForbidden()

        # Check if setup wizard is needed
        if setup_needed and not config.MAINTENANCE_MODE:
            if request.path.startswith(API_V1_PREFIX):
                return JsonResponse(
                    {
                        "error": {
                            "code": "setup_required",
                            "message": "This instance has not been set up yet.",
                        }
                    },
                    status=503,
                )
            # Redirect to setup wizard...
            return HttpResponseRedirect(reverse("setup_wizard"))

        # Lets not force a profile update
        # # Check if we should force a profile complete (aka first login)
        # excluded_profile_urls = [
        #     "/profile/",
        #     "/profile/update",
        #     "/profile/update/skills",
        #     "/oauth2/logout",
        #     "/auth/logout/",
        #     "/impersonate/stop/",  # Allow us to stop impersonating even if profile needs updating
        #     "/setup",  # Also exclude setup wizard from profile update requirement
        #     "/notifications/api",
        # ]
        # if request.user.is_authenticated and not request.user.profile_last_updated:
        #     msg = "You must first update your profile!"
        #     if msg not in [m.message for m in get_messages(request)]:
        #         messages.warning(request=request, message=msg)

        #     for path in excluded_profile_urls:
        #         if request.path.startswith(path):
        #             return

        #     return HttpResponseRedirect(reverse("update_own_profile"))


class CurrentUserMiddleware:
    """Exposes the current request to models (see :func:`get_current_user`)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _current_request.set(request)
        try:
            return self.get_response(request)
        finally:
            _current_request.reset(token)


class AjaxLoginRedirect401Middleware:
    """Turn the ``login_required`` login redirect into a 401 for AJAX requests.

    When a session expires, ``@login_required`` views answer with a 302 to the
    login page. A browser follows that redirect transparently for an XHR/fetch,
    so front-end code (e.g. the scheduler double-click modal loader) receives the
    login *page* HTML with a 200 status and — expecting JSON — fails with an
    opaque parse error instead of telling the user their session lapsed.

    For requests flagged ``X-Requested-With: XMLHttpRequest`` we intercept the
    redirect-to-login *before* the browser follows it and return a small 401 JSON
    body. The client already renders 401 as "your session has expired — please
    sign in again", so this fixes every AJAX endpoint uniformly.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Path of LOGIN_URL, resolved once (LOGIN_URL may be a name or a path).
        self._login_path = urlparse(resolve_url(settings.LOGIN_URL)).path

    def __call__(self, request):
        response = self.get_response(request)

        is_ajax = request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest"
        if (
            is_ajax
            and response.status_code == 302
            and urlparse(response.get("Location", "")).path == self._login_path
        ):
            return JsonResponse(
                {"error": "Your session has expired — please sign in again."},
                status=401,
            )
        return response


class MaintenanceModeMiddleware(MiddlewareMixin):
    def process_request(self, request):
        path = request.META.get("PATH_INFO", "")

        # Allow access to admin login and authentication pages during maintenance
        admin_allowed_paths = [
            "/admin/",
            "/admin/login/",
            "/admin/logout/",
            "/oauth2/",  # For ADFS authentication
        ]

        is_admin_path_allowed = any(
            path.startswith(allowed_path) for allowed_path in admin_allowed_paths
        )

        # /api/v1/ authenticates in the view (token/OAuth2), so the user isn't
        # known yet; MaintenanceModePermission answers 503 there instead.
        if path.startswith(API_V1_PREFIX):
            return

        if (
            config.MAINTENANCE_MODE
            and not request.user.is_superuser
            and path != reverse("maintenance")
            and not is_admin_path_allowed
        ):
            response = redirect(reverse("maintenance"))
            return response


class TimezoneMiddleware:
    """Activates the authenticated user's preferred timezone for each request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, "user") and request.user.is_authenticated:
            tz_name = getattr(request.user, "pref_timezone", None) or "UTC"
            dj_timezone.activate(zoneinfo.ZoneInfo(tz_name))
        else:
            dj_timezone.deactivate()
        return self.get_response(request)


OAUTH_PREFIX = "/o/"
OAUTH_TOKEN_PATHS = ("/o/token/", "/o/revoke_token/")


class OAuthGateMiddleware:
    """Guards the OAuth2 provider endpoints (``/o/``).

    - off unless ``API_OAUTH2_ENABLED`` (404);
    - no granting apps access while impersonating someone (403) — the token
      would act as them long after the impersonation ends;
    - the token endpoints answer maintenance mode with JSON, not a redirect
      a client can't follow.

    Must come after ImpersonateMiddleware and before MaintenanceModeMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith(OAUTH_PREFIX):
            if not config.API_OAUTH2_ENABLED:
                return JsonResponse(
                    {"error": "not_found", "error_description": "OAuth2 is disabled."},
                    status=404,
                )
            if getattr(request, "impersonator", None) is not None:
                return HttpResponseForbidden(
                    "Apps can't be connected while impersonating someone."
                )
            if config.MAINTENANCE_MODE and path in OAUTH_TOKEN_PATHS:
                return JsonResponse(
                    {
                        "error": "temporarily_unavailable",
                        "error_description": "CHAOTICA is in maintenance mode.",
                    },
                    status=503,
                )
        return self.get_response(request)
