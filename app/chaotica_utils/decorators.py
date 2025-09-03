from django.http.response import HttpResponseRedirect
from django.http import HttpResponseForbidden
from functools import wraps


def superuser_required(view_func):
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            return HttpResponseForbidden()
        return view_func(request, *args, **kwargs)
    return wrapped_view


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
