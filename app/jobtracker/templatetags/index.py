from django import template
from chaotica_utils.enums import UnitRoles
import datetime

register = template.Library()


@register.filter
def index(indexable, i):
    return indexable[i]


@register.simple_tag
def get_objects_for_user(user, perms, obj):
    from guardian.shortcuts import get_objects_for_user

    return get_objects_for_user(user, perms, obj)


@register.simple_tag
def get_phases_for_user(user, phases):
    from guardian.shortcuts import get_objects_for_user
    from ..models import Job

    my_jobs = get_objects_for_user(user, "jobtracker.view_job", Job)
    return phases.prefetch_related(
        "timeslots",
        "job__client",
        "job__unit",
        "report_author",
        "project_lead",
    ).filter(job__in=my_jobs)


@register.simple_tag
def get_slot_type_usage_perc(obj, slot_type):
    return obj.get_slot_type_usage_perc(slot_type)


@register.simple_tag
def get_total_scheduled_by_type(obj, slot_type):
    return obj.get_total_scheduled_by_type(slot_type)


@register.simple_tag
def get_total_scoped_by_type(obj, slot_type):
    return obj.get_total_scoped_by_type(slot_type)


@register.simple_tag
def get_unit_role_display(role):
    return UnitRoles.CHOICES[role][1]


@register.simple_tag
def get_range_from_zero(number):
    rng = range(0, number, 1)
    return rng


@register.simple_tag
def get_range_from_one(number):
    rng = range(1, number + 1, 1)
    return rng


@register.simple_tag
def get_range_from_zero(number):
    rng = range(0, number + 1, 1)
    return rng


@register.simple_tag
def py_date_to_js_date(date):
    if date:
        if isinstance(date, datetime.datetime):
            return str(date.strftime("%Y-%m-%d"))
        elif isinstance(date, datetime.date):
            return str(date.strftime("%Y-%m-%d"))
        else:
            # Try and convert it to a datetime...
            return str(
                datetime.datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d")
            )
    else:
        return ""


# Bulk workflow eligibility filters
# These check if any phase can proceed without triggering side effects
@register.filter
def any_can_proceed_to_pending_sched(phases):
    try:
        return any(phase.can_proceed_to_pending_sched() for phase in phases)
    except:
        return False


@register.filter
def any_can_proceed_to_sched_confirmed(phases):
    try:
        return any(phase.can_proceed_to_sched_confirmed() for phase in phases)
    except:
        return False


@register.filter
def any_can_proceed_to_pre_checks(phases):
    try:
        return any(phase.can_proceed_to_pre_checks() for phase in phases)
    except:
        return False


@register.filter
def any_can_proceed_to_not_ready(phases):
    try:
        return any(phase.can_proceed_to_not_ready() for phase in phases)
    except:
        return False


@register.filter
def any_can_proceed_to_ready(phases):
    try:
        return any(phase.can_proceed_to_ready() for phase in phases)
    except:
        return False


@register.filter
def any_can_proceed_to_pending_tech_qa(phases):
    try:
        return any(phase.can_proceed_to_pending_tech_qa() for phase in phases)
    except:
        return False


@register.filter
def any_can_proceed_to_tech_qa(phases):
    try:
        return any(phase.can_proceed_to_tech_qa() for phase in phases)
    except:
        return False


@register.filter
def any_can_proceed_to_tech_qa_updates(phases):
    try:
        return any(phase.can_proceed_to_tech_qa_updates() for phase in phases)
    except:
        return False


@register.filter
def any_can_proceed_to_pending_pres_qa(phases):
    try:
        return any(phase.can_proceed_to_pending_pres_qa() for phase in phases)
    except:
        return False


@register.filter
def any_can_proceed_to_pres_qa(phases):
    try:
        return any(phase.can_proceed_to_pres_qa() for phase in phases)
    except:
        return False


@register.filter
def any_can_proceed_to_pres_qa_updates(phases):
    try:
        return any(phase.can_proceed_to_pres_qa_updates() for phase in phases)
    except:
        return False


@register.filter
def any_can_proceed_to_completed(phases):
    try:
        return any(phase.can_proceed_to_completed() for phase in phases)
    except:
        return False


@register.filter
def any_can_proceed_to_delivered(phases):
    try:
        return any(phase.can_proceed_to_delivered() for phase in phases)
    except:
        return False
