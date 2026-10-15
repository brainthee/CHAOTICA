"""Site-wide loaded cost rate (LCR) management (Operations → Loaded Cost Rates).

Everything here is gated on ``jobtracker.can_view_loaded_costs``:

- the page lists active members of the units you hold it on (all units for a
  superuser or a global grant), filterable by unit, name and rate status;
- a person's rate can only be set when :func:`can_manage_user_lcr` allows it,
  i.e. you hold the permission on *every* unit they belong to and it isn't
  your own rate (the same rule as the API's ``set-cost`` action).
"""

from django.shortcuts import get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.template import loader
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from guardian.shortcuts import get_objects_for_user
from chaotica_utils.models import User, UserCost
from chaotica_utils.utils.common import can_manage_user_lcr
from chaotica_utils.views import page_defaults
from ..models import OrganisationalUnit, OrganisationalUnitMember
from ..forms import UserCostForm


LCR_PERM = "jobtracker.can_view_loaded_costs"
RATE_FILTERS = {"missing": "No rate set", "set": "Rate set"}


def lcr_units_for(user):
    """Units whose members' rates ``user`` may see. Memoised on the user so the
    menu check and the view share one lookup per request."""
    if not user.is_authenticated:
        return OrganisationalUnit.objects.none()
    if not hasattr(user, "_lcr_unit_ids"):
        user._lcr_unit_ids = set(
            get_objects_for_user(user, LCR_PERM, klass=OrganisationalUnit).values_list(
                "pk", flat=True
            )
        )
    return OrganisationalUnit.objects.filter(pk__in=user._lcr_unit_ids)


def can_view_any_lcr(user):
    return user.is_authenticated and lcr_units_for(user).exists()


def _global_lcr_access(user):
    return user.is_superuser or user.has_perm(LCR_PERM)


@login_required
def lcr_list(request):
    """Active members of the user's finance units with their current rate."""
    units = list(lcr_units_for(request.user).order_by("name"))
    if not units:
        return HttpResponseForbidden()
    unit_ids = {u.pk for u in units}

    selected_unit = None
    unit_slug = request.GET.get("unit") or ""
    if unit_slug:
        selected_unit = next((u for u in units if u.slug == unit_slug), None)
        if selected_unit is None:
            # Unknown, or a unit outside the user's remit.
            return HttpResponseForbidden()
    rate_filter = request.GET.get("rate") or ""
    if rate_filter not in RATE_FILTERS:
        rate_filter = ""
    q = (request.GET.get("q") or "").strip()

    scope_ids = {selected_unit.pk} if selected_unit else unit_ids
    people = User.objects.filter(
        is_active=True,
        unit_memberships__left_date__isnull=True,
        unit_memberships__unit_id__in=scope_ids,
    )
    if q:
        people = people.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
        )
    people = list(
        people.distinct()
        .select_related("city", "city__country", "manager")
        .order_by("last_name", "first_name", "email")
    )
    person_ids = [p.pk for p in people]

    # Every active unit each person sits in, for the Units column and the
    # "can set" rule (must hold the perm on all of them).
    units_by_user = {}
    for ms in (
        OrganisationalUnitMember.objects.filter(
            member_id__in=person_ids, left_date__isnull=True
        )
        .select_related("unit")
        .order_by("unit__name")
    ):
        units_by_user.setdefault(ms.member_id, []).append(ms.unit)

    # Current (latest-effective) rate per person, one query.
    latest = {}
    for uc in UserCost.objects.filter(user_id__in=person_ids).order_by(
        "user_id", "-effective_from"
    ):
        latest.setdefault(uc.user_id, uc)

    global_access = _global_lcr_access(request.user)
    rows = []
    for person in people:
        current = latest.get(person.pk)
        if rate_filter == "missing" and current is not None:
            continue
        if rate_filter == "set" and current is None:
            continue
        person_units = units_by_user.get(person.pk, [])
        rows.append(
            {
                "user": person,
                "units": person_units,
                "current": current,
                "can_set": request.user.is_superuser
                or (
                    person.pk != request.user.pk
                    and (global_access or all(u.pk in unit_ids for u in person_units))
                ),
            }
        )

    context = {
        "units": units,
        "selected_unit": selected_unit,
        "rate_filter": rate_filter,
        "rate_filters": RATE_FILTERS,
        "q": q,
        "rows": rows,
        "missing_count": sum(1 for r in rows if r["current"] is None),
        "lcr_unit_ids": unit_ids,
    }
    context = {**context, **page_defaults(request)}
    template = loader.get_template("jobtracker/lcr_list.html")
    return HttpResponse(template.render(context, request))


@login_required
def lcr_set(request, user_pk):
    """Modal: add a new date-effective rate for one person."""
    target = get_object_or_404(User, pk=user_pk)
    if not can_manage_user_lcr(request.user, target):
        return HttpResponseForbidden()

    data = dict()
    if request.method == "POST":
        form = UserCostForm(request.POST, user=target)
        if form.is_valid():
            form.save()
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
            data["form_errors"] = form.errors
    else:
        form = UserCostForm(user=target)

    context = {
        "target": target,
        "form": form,
        "history": UserCost.objects.filter(user=target).order_by("-effective_from"),
    }
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/lcr_set.html", context, request=request
    )
    return JsonResponse(data)
