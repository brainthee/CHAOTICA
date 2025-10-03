from django.http import (
    HttpResponseForbidden,
    HttpResponse,
    HttpResponseRedirect,
)
from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import reverse, redirect
from ..models import User
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
        # Check if setup is needed - check for all essential components
        from jobtracker.models import OrganisationalUnit, Service, SkillCategory, Client

        # Setup is complete only when we have ALL of these:
        # 1. At least one user
        # 2. At least one org unit
        # 3. At least one service
        # 4. At least one skill category
        # 5. At least one client
        setup_needed = (
            User.objects.all().count() == 0 or
            OrganisationalUnit.objects.all().count() == 0 or
            Service.objects.all().count() == 0 or
            SkillCategory.objects.all().count() == 0 or
            Client.objects.all().count() == 0
        )

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
        
        is_admin_path_allowed = any(path.startswith(allowed_path) for allowed_path in admin_allowed_paths)
        
        if (
            config.MAINTENANCE_MODE
            and not request.user.is_superuser
            and path != reverse("maintenance")
            and not is_admin_path_allowed
        ):
            response = redirect(reverse("maintenance"))
            return response
