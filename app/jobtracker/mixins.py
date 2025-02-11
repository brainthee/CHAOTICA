from guardian.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from .utils import get_unit_40x_or_None
from .enums import JobGuestPermissions
from django.contrib.auth.decorators import login_required, REDIRECT_FIELD_NAME
from django.conf import settings


class UnitPermissionRequiredMixin(PermissionRequiredMixin):
    # We also want to check we're logged in first!

    redirect_field_name = REDIRECT_FIELD_NAME
    login_url = settings.LOGIN_URL

    def dispatch(self, request, *args, **kwargs):
        return login_required(
            redirect_field_name=self.redirect_field_name, login_url=self.login_url
        )(super().dispatch)(request, *args, **kwargs)

    def check_permissions(self, request):
        """
        Checks if *request.user* has all permissions returned by
        *get_required_permissions* method.

        :param request: Original request.
        """
        obj = self.get_permission_object()

        forbidden = get_unit_40x_or_None(
            request,
            perms=self.get_required_permissions(request),
            obj=obj,
            login_url=self.login_url,
            redirect_field_name=self.redirect_field_name,
            return_403=self.return_403,
            return_404=self.return_404,
            accept_global_perms=self.accept_global_perms,
            any_perm=self.any_perm,
        )
        if forbidden:
            self.on_permission_check_fail(request, forbidden, obj=obj)
        if forbidden and self.raise_exception:
            raise PermissionDenied()
        return forbidden


class JobPermissionRequiredMixin(PermissionRequiredMixin):
    # We also want to check we're logged in first!

    redirect_field_name = REDIRECT_FIELD_NAME
    login_url = settings.LOGIN_URL

    def dispatch(self, request, *args, **kwargs):
        return login_required(
            redirect_field_name=self.redirect_field_name, login_url=self.login_url
        )(super().dispatch)(request, *args, **kwargs)

    def check_permissions(self, request):
        """
        Checks if *request.user* has all permissions returned by
        *get_required_permissions* method.

        :param request: Original request.
        """
        obj = self.get_permission_object()
        perms = self.get_required_permissions(request)

        forbidden = get_unit_40x_or_None(
            request,
            perms=perms,
            obj=obj,
            login_url=self.login_url,
            redirect_field_name=self.redirect_field_name,
            return_403=True,
            return_404=self.return_404,
            accept_global_perms=self.accept_global_perms,
            any_perm=self.any_perm,
        )

        team = None
        from .models import Job, Phase

        if isinstance(obj, Job):
            team = obj.team()
        elif isinstance(obj, Phase):
            team = obj.job.team()

        if forbidden:
            # It's forbidden - lets check if we have specific job permissions...
            if request.user in team:
                should_permit = True  # We're in the team - permit for now!
                # We're in the team but check if we're doing a permission we'll permit for the moment?
                for perm in perms:
                    if perm not in JobGuestPermissions.ALLOWED:
                        should_permit = False  # Ok, asking for a denied perm.

                if should_permit:
                    forbidden = False

        if forbidden:
            self.on_permission_check_fail(request, forbidden, obj=obj)
        if forbidden and self.raise_exception:
            raise PermissionDenied()
        return forbidden


class PrefetchRelatedMixin(object):
    prefetch_related = None

    def get_queryset(self):
        if self.prefetch_related is None:
            raise ImproperlyConfigured(
                "%(cls)s is missing the prefetch_related"
                "property. This must be a tuple or list."
                % {"cls": self.__class__.__name__}
            )

        if not isinstance(self.prefetch_related, (tuple, list)):
            raise ImproperlyConfigured(
                "%(cls)s's select_related property "
                "must be a tuple or list." % {"cls": self.__class__.__name__}
            )

        queryset = super(PrefetchRelatedMixin, self).get_queryset()
        return queryset.prefetch_related(*self.prefetch_related)
