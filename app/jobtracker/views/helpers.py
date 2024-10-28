from django.http import JsonResponse
from django.template import loader
from ..models import Contact, Phase
from ..enums import PhaseStatuses
from ..forms import (
    AssignMultipleUser,
    AssignUser,
    AssignMultipleContacts,
    AssignContact,
)
from chaotica_utils.views import log_system_activity
from chaotica_utils.models import User
import logging


logger = logging.getLogger(__name__)


def _process_assign_user(request, obj, prop, multiple=False, users=None):
    data = dict()
    if users is None:
        users = User.objects.filter(is_active=True)
    if request.method == "POST":
        if multiple:
            form = AssignMultipleUser(request.POST, users=users)
        else:
            form = AssignUser(request.POST, users=users)

        if form.is_valid():
            if multiple:
                getattr(obj, prop).clear()
                for user in form.cleaned_data["users"]:
                    getattr(obj, prop).add(user)
            else:
                setattr(obj, prop, form.cleaned_data["user"])

            obj.save()
            
            if isinstance(obj, Phase):
                if (
                    (
                        obj.status == PhaseStatuses.QA_TECH
                        or obj.status == PhaseStatuses.PENDING_TQA
                    )
                    and prop == "techqa_by"
                ) or (
                    (
                        obj.status == PhaseStatuses.QA_PRES
                        or obj.status == PhaseStatuses.PENDING_PQA
                    )
                    and prop == "presqa_by"
                ):
                    # Refire notifications
                    obj.refire_status_notification()

            log_system_activity(
                obj,
                "Altered assigned user for "
                + obj._meta.get_field(prop).verbose_name.title(),
                author=request.user,
            )
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        if multiple:
            form = AssignMultipleUser(users=users)
        else:
            form = AssignUser(users=users)

    context = {
        "form": form,
        "obj": obj,
        "field": obj._meta.get_field(prop).verbose_name.title(),
    }
    data["html_form"] = loader.render_to_string(
        "modals/assign_user_modal.html", context, request=request
    )
    return JsonResponse(data)


def _process_assign_contact(request, obj, prop, multiple=False, contacts=None):
    data = dict()
    if contacts is None:
        contacts = Contact.objects.all()
    if request.method == "POST":
        if multiple:
            form = AssignMultipleContacts(request.POST, contacts=contacts)
        else:
            form = AssignContact(request.POST, contacts=contacts)

        if form.is_valid():
            if multiple:
                getattr(obj, prop).clear()
                for user in form.cleaned_data["contacts"]:
                    getattr(obj, prop).add(user)
            else:
                setattr(obj, prop, form.cleaned_data["contact"])

            log_system_activity(
                obj,
                "Altered contact information for "
                + obj._meta.get_field(prop).verbose_name.title(),
                author=request.user,
            )
            obj.save()
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
    else:
        if multiple:
            form = AssignMultipleContacts(contacts=contacts)
        else:
            form = AssignContact(contacts=contacts)

    context = {
        "form": form,
        "obj": obj,
        "field": obj._meta.get_field(prop).verbose_name.title(),
    }
    data["html_form"] = loader.render_to_string(
        "modals/assign_contact_modal.html", context, request=request
    )
    return JsonResponse(data)
