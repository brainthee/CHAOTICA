from guardian.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from .utils import get_unit_40x_or_None

from django.contrib.auth.decorators import login_required, REDIRECT_FIELD_NAME
from django.conf import settings


class UnitPermissionRequiredMixin(PermissionRequiredMixin):
    # We also want to check we're logged in first!

    redirect_field_name = REDIRECT_FIELD_NAME
    login_url = settings.LOGIN_URL

    def dispatch(self, request, *args, **kwargs):
        return login_required(redirect_field_name=self.redirect_field_name,
                              login_url=self.login_url)(
            super().dispatch
        )(request, *args, **kwargs)

    def check_permissions(self, request):
        """
        Checks if *request.user* has all permissions returned by
        *get_required_permissions* method.

        :param request: Original request.
        """
        obj = self.get_permission_object()

        forbidden = get_unit_40x_or_None(request,
                                    perms=self.get_required_permissions(
                                        request),
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