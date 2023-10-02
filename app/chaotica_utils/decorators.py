from django.http.response import HttpResponseRedirect, HttpResponse, HttpResponseForbidden
from functools import wraps
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth import REDIRECT_FIELD_NAME


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


# def manager_required(function):
#   @wraps(function)
#   def wrap(request, *args, **kwargs):
#         if request.user.is_manager or request.user.is_superuser:
#              return function(request, *args, **kwargs)
#         else:
#             return HttpResponseForbidden()

#   return wrap