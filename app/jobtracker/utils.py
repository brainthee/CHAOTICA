import logging
import os
from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.http import HttpResponseForbidden, HttpResponseNotFound
from django.shortcuts import render
from guardian.conf import settings as guardian_settings
from .models import Job, Phase, OrganisationalUnit
from chaotica_utils.enums import UnitRoles

logger = logging.getLogger(__name__)
abspath = lambda *p: os.path.abspath(os.path.join(*p))


def get_unit_40x_or_None(request, perms, obj=None, login_url=None,
                    redirect_field_name=None, return_403=False,
                    return_404=False, accept_global_perms=False,
                    any_perm=False):
    login_url = login_url or settings.LOGIN_URL
    redirect_field_name = redirect_field_name or REDIRECT_FIELD_NAME

    # Handles both original and with object provided permission check
    # as ``obj`` defaults to None

    has_permissions = False
    # global perms check first (if accept_global_perms)
    if accept_global_perms:
        has_permissions = all(request.user.has_perm(perm) for perm in perms)
    # if still no permission granted, try obj perms
    if not has_permissions:
        if any_perm:
            has_permissions = any(request.user.has_perm(perm, obj)
                                  for perm in perms)
        else:
            has_permissions = all(request.user.has_perm(perm, obj)
                                  for perm in perms)
    
    # Ok, now lets check unit permissions...
    if not has_permissions:
        unit = None
        if isinstance(obj, Job):
            unit = obj.unit
        if isinstance(obj, Phase):
            unit = obj.job.unit
        if isinstance(obj, OrganisationalUnit):
            unit = obj
        if unit:
            if any_perm:
                has_permissions = any(request.user.has_perm(perm, unit)
                                    for perm in perms)
            else:
                has_permissions = all(request.user.has_perm(perm, unit)
                                    for perm in perms)

    if not has_permissions:
        if return_403:
            if guardian_settings.RENDER_403:
                response = render(request, guardian_settings.TEMPLATE_403)
                response.status_code = 403
                return response
            elif guardian_settings.RAISE_403:
                raise PermissionDenied
            return HttpResponseForbidden()
        if return_404:
            if guardian_settings.RENDER_404:
                response = render(request, guardian_settings.TEMPLATE_404)
                response.status_code = 404
                return response
            elif guardian_settings.RAISE_404:
                raise ObjectDoesNotExist
            return HttpResponseNotFound()
        else:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path(),
                                     login_url,
                                     redirect_field_name)