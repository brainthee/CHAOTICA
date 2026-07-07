from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ImproperlyConfigured
from guardian.mixins import PermissionRequiredMixin


class SecurePermissionRequiredMixin(PermissionRequiredMixin):
    """Guardian's ``PermissionRequiredMixin`` with a consistent auth story.

    Guardian checks permissions before Django's ``LoginRequiredMixin`` gets a
    turn, so with ``return_403 = True`` an *anonymous* visitor receives a bare
    403 instead of a login prompt. This mixin redirects unauthenticated users to
    the login page first, then defers to guardian for authenticated users (who
    still get a 403 when they lack the object/global permission).
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            login_url = getattr(self, "login_url", None) or settings.LOGIN_URL
            redirect_field_name = (
                getattr(self, "redirect_field_name", None) or REDIRECT_FIELD_NAME
            )
            return redirect_to_login(
                request.get_full_path(), login_url, redirect_field_name
            )
        return super().dispatch(request, *args, **kwargs)


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
