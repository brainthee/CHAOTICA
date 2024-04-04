from django.http.response import HttpResponseRedirect
from functools import wraps


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
