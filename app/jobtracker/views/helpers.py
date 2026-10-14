from django.http import JsonResponse
from django.template import loader
from ..models import Contact, Phase, Job
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
    help_text = ""
    if users is None:
        if prop == "techqa_by" and isinstance(obj, Phase):
            users = obj.job.unit.get_active_members_with_perm("can_tqa_jobs")
            help_text = "Showing users with permission to do Tech QA"
        elif prop == "presqa_by" and isinstance(obj, Phase):
            users = obj.job.unit.get_active_members_with_perm("can_pqa_jobs")
            help_text = "Showing users with permission to do Pres QA"
        elif prop == "scoped_by" and isinstance(obj, Job):
            users = obj.unit.get_active_members_with_perm("can_scope_jobs")
            help_text = "Showing users with permission to Scope Jobs"
        elif prop == "scoped_signed_off_by" and isinstance(obj, Job):
            users = obj.unit.get_active_members_with_perm("can_signoff_scopes")
            help_text = "Showing users with permission to Signoff Scopes"
        else:
            users = User.objects.filter(is_active=True)

    if request.method == "POST":
        if multiple:
            form = AssignMultipleUser(request.POST, users=users, help_text=help_text)
        else:
            form = AssignUser(request.POST, users=users, help_text=help_text)

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
            form = AssignMultipleUser(users=users, help_text=help_text)
        else:
            form = AssignUser(users=users, help_text=help_text)

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


def _render_cohort_billing(request, user_qs, partial_url):
    """Team / org-unit Billing tab: hours per member and per code for a
    timesheet period, from the same engine as each member's own Billing Codes
    page. Returns the partial's ``JsonResponse({"html": ...})``."""
    from chaotica_utils.utils import build_cohort_code_allocation
    from chaotica_utils.utils.periods import parse_period_range, period_nav_context

    start, end = parse_period_range(request.GET)
    users = list(user_qs.select_related("manager", "acting_manager"))
    cohort = build_cohort_code_allocation(users, start, end)
    per_code = sorted(
        cohort["per_code"].values(), key=lambda c: str(c["code"].code).lower()
    )
    context = period_nav_context(start, end)
    context.update(
        {
            "rows": cohort["rows"],
            "per_code": per_code,
            "totals": cohort["totals"],
            "partial_url": partial_url,
            # Link to a member's own Billing Codes page only where it'd open.
            "manageable_ids": {
                u.pk for u in users if u.can_be_managed_by(request.user)
            },
        }
    )
    html = loader.render_to_string(
        "partials/billing/cohort_allocation.html", context, request=request
    )
    return JsonResponse({"html": html})
