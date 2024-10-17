from django.http import (
    HttpResponseForbidden,
    HttpResponse,
    HttpResponseRedirect,
)
from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import reverse, redirect
from .models import User
from django.urls import reverse
from django.conf import settings
from constance import config
from django.contrib import messages
from django.contrib.messages import get_messages


class HealthCheckMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.META["PATH_INFO"] == "/ping":
            return HttpResponse("pong!")


class NewInstallMiddleware(MiddlewareMixin):
    def process_request(self, request):
        new_install = User.objects.all().count() <= 1
        excluded_paths = ["/media", "/static", "/admin"]
        new_install_excluded_urls = [
            "/signup/",
            "/quote",
        ]
        for path in excluded_paths:
            if request.path.startswith(path):
                return

        # Check if local login is disabled
        if not config.LOCAL_LOGIN_ENABLED:
            if request.method == "POST" and request.path == "/auth/login/":
                # Nuh huh!
                return HttpResponseForbidden()

        # Check if it's a new install and we should force signup
        if new_install and not request.user.is_authenticated:
            if request.path not in new_install_excluded_urls:
                # Redirect to signup page...
                return HttpResponseRedirect(reverse("signup"))

        # Check if we should force a profile complete (aka first login)
        excluded_profile_urls = [
            "/profile/",
            "/profile/update",
            "/profile/update/skills",
            "/oauth2/logout",
            "/auth/logout/",
            "/impersonate/stop/",  # Allow us to stop impersonating even if profile needs updating
        ]
        if request.user.is_authenticated and not request.user.profile_last_updated:
            msg = "You must first update your profile!"
            if msg not in [m.message for m in get_messages(request)]:
                messages.warning(request=request, message=msg)
            if request.path not in excluded_profile_urls:
                return HttpResponseRedirect(reverse("view_own_profile"))


class MaintenanceModeMiddleware(MiddlewareMixin):
    def process_request(self, request):
        path = request.META.get("PATH_INFO", "")
        if (
            settings.MAINTENANCE_MODE
            and not request.user.is_superuser
            and path != reverse("maintenance")
        ):
            response = redirect(reverse("maintenance"))
            return response
