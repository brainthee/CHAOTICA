from django.apps import apps
from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.db.models import Model
from django.db.models.base import ModelBase
from django.db.models.query import QuerySet
from django.shortcuts import get_object_or_404
from .utils import get_unit_40x_or_None
from .enums import JobGuestPermissions
from django.utils.functional import wraps
from guardian.exceptions import GuardianError


# Using the Guardian "permission_required" decorator here


def unit_permission_required(perm, lookup_variables=None, **kwargs):
    login_url = kwargs.pop("login_url", settings.LOGIN_URL)
    redirect_field_name = kwargs.pop("redirect_field_name", REDIRECT_FIELD_NAME)
    return_403 = kwargs.pop("return_403", False)
    return_404 = kwargs.pop("return_404", False)
    accept_global_perms = kwargs.pop("accept_global_perms", False)

    # Check if perm is given as string in order not to decorate
    # view function itself which makes debugging harder
    if not isinstance(perm, str):
        raise GuardianError(
            "First argument must be in format: "
            "'app_label.codename or a callable which return similar string'"
        )

    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            # if more than one parameter is passed to the decorator we try to
            # fetch object for which check would be made
            obj = None
            if lookup_variables:
                model, lookups = lookup_variables[0], lookup_variables[1:]
                # Parse model
                if isinstance(model, str):
                    splitted = model.split(".")
                    if len(splitted) != 2:
                        raise GuardianError(
                            "If model should be looked up from "
                            "string it needs format: 'app_label.ModelClass'"
                        )
                    model = apps.get_model(*splitted)
                elif issubclass(model.__class__, (Model, ModelBase, QuerySet)):
                    pass
                else:
                    raise GuardianError(
                        "First lookup argument must always be "
                        "a model, string pointing at app/model or queryset. "
                        "Given: %s (type: %s)" % (model, type(model))
                    )
                # Parse lookups
                if len(lookups) % 2 != 0:
                    raise GuardianError(
                        "Lookup variables must be provided "
                        "as pairs of lookup_string and view_arg"
                    )
                lookup_dict = {}
                for lookup, view_arg in zip(lookups[::2], lookups[1::2]):
                    if view_arg not in kwargs:
                        raise GuardianError(
                            "Argument %s was not passed "
                            "into view function" % view_arg
                        )
                    lookup_dict[lookup] = kwargs[view_arg]
                obj = get_object_or_404(model, **lookup_dict)

            # This is the bit that's changed...
            response = get_unit_40x_or_None(
                request,
                perms=[perm],
                obj=obj,
                login_url=login_url,
                redirect_field_name=redirect_field_name,
                return_403=return_403,
                return_404=return_404,
                accept_global_perms=accept_global_perms,
            )
            if response:
                return response
            return view_func(request, *args, **kwargs)

        return wraps(view_func)(_wrapped_view)

    return decorator


def unit_permission_required_or_403(perm, *args, **kwargs):
    """
    Simple wrapper for permission_required decorator.

    Standard Django's permission_required decorator redirects user to login page
    in case permission check failed. This decorator may be used to return
    HttpResponseForbidden (status 403) instead of redirection.

    The only difference between ``permission_required`` decorator is that this
    one always set ``return_403`` parameter to ``True``.
    """
    kwargs["return_403"] = True
    return unit_permission_required(perm, *args, **kwargs)


def job_permission_required_or_403(perm, *args, **kwargs):
    login_url = kwargs.pop("login_url", settings.LOGIN_URL)
    redirect_field_name = kwargs.pop("redirect_field_name", REDIRECT_FIELD_NAME)
    return_403 = kwargs.pop("return_403", False)
    return_404 = kwargs.pop("return_404", False)
    accept_global_perms = kwargs.pop("accept_global_perms", False)

    # Check if perm is given as string in order not to decorate
    # view function itself which makes debugging harder
    if not isinstance(perm, str):
        raise GuardianError(
            "First argument must be in format: "
            "'app_label.codename or a callable which return similar string'"
        )

    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            # if more than one parameter is passed to the decorator we try to
            # fetch object for which check would be made
            obj = None
            if args:
                model, lookups = args[0], args[1:]
                # Parse model
                if isinstance(model, str):
                    splitted = model.split(".")
                    if len(splitted) != 2:
                        raise GuardianError(
                            "If model should be looked up from "
                            "string it needs format: 'app_label.ModelClass'"
                        )
                    model = apps.get_model(*splitted)
                elif issubclass(model.__class__, (Model, ModelBase, QuerySet)):
                    pass
                else:
                    raise GuardianError(
                        "First lookup argument must always be "
                        "a model, string pointing at app/model or queryset. "
                        "Given: %s (type: %s)" % (model, type(model))
                    )
                # Parse lookups
                if len(lookups) % 2 != 0:
                    raise GuardianError(
                        "Lookup variables must be provided "
                        "as pairs of lookup_string and view_arg"
                    )
                lookup_dict = {}
                for lookup, view_arg in zip(lookups[::2], lookups[1::2]):
                    if view_arg not in kwargs:
                        raise GuardianError(
                            "Argument %s was not passed "
                            "into view function" % view_arg
                        )
                    lookup_dict[lookup] = kwargs[view_arg]
                obj = get_object_or_404(model, **lookup_dict)

            # This is the bit that's changed...
            response = get_unit_40x_or_None(
                request,
                perms=[perm],
                obj=obj,
                login_url=login_url,
                redirect_field_name=redirect_field_name,
                return_403=return_403,
                return_404=return_404,
                accept_global_perms=accept_global_perms,
            )

            team = None
            from .models import Job, Phase
            if isinstance(obj, Job):
                team = obj.team()
            elif isinstance(obj, Phase):
                team = obj.job.team()
            
            if not team:
                response = False

            if response:
                # It's forbidden - lets check if we have specific job permissions...
                if request.user in team:
                    should_permit = True # We're in the team - permit for now!
                    # We're in the team but check if we're doing a permission we'll permit for the moment?
                    if perm not in JobGuestPermissions.ALLOWED:
                        should_permit = False # Ok, asking for a denied perm. 
                            
                    if should_permit:
                        response = False
                    
            if response:
                return response
            return view_func(request, *args, **kwargs)

        return wraps(view_func)(_wrapped_view)

    return decorator