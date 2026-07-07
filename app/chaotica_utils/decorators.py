from django.http.response import HttpResponseRedirect
from django.http import HttpResponseForbidden
from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.views import redirect_to_login
from functools import wraps

from guardian.decorators import (
    permission_required_or_403 as _guardian_permission_required_or_403,
)


def superuser_required(view_func):
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        # Anonymous users get a login prompt; authenticated non-superusers get 403.
        if not request.user.is_authenticated:
            return redirect_to_login(
                request.get_full_path(), settings.LOGIN_URL, REDIRECT_FIELD_NAME
            )
        if not request.user.is_superuser:
            return HttpResponseForbidden()
        return view_func(request, *args, **kwargs)
    return wrapped_view


def permission_required_or_403(perm, *args, **kwargs):
    """Drop-in replacement for guardian's ``permission_required_or_403``.

    Guardian's decorator returns a bare 403 for *any* failure, including
    anonymous users. This variant first redirects unauthenticated users to the
    login page (so they get a login prompt), then defers to guardian for
    authenticated users — who still get a 403 when they lack the permission. The
    signature is identical to guardian's, so it's a straight import swap.
    """
    guardian_decorator = _guardian_permission_required_or_403(perm, *args, **kwargs)

    def decorator(view_func):
        guarded = guardian_decorator(view_func)

        @wraps(view_func)
        def wrapped_view(request, *view_args, **view_kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(
                    request.get_full_path(), settings.LOGIN_URL, REDIRECT_FIELD_NAME
                )
            return guarded(request, *view_args, **view_kwargs)

        return wrapped_view

    return decorator


def redirect_if_authenticated(redirect_to):
    def inner_function(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            request = args[0]
            if request.user.is_authenticated:
                return HttpResponseRedirect(redirect_to)
            return function(*args, **kwargs)

        return wrapper

    return inner_function
