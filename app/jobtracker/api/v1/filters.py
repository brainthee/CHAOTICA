"""List filters for /api/v1/.

Filters only ever narrow the viewset's already-scoped queryset. ``me`` is
accepted wherever a user id is (``?lead=me``, ``?involving=me``).
"""

import django_filters
from django.db.models import Q
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter

from chaotica_utils.models import User
from chaotica_utils.models.leave import LeaveRequest

from ...models import Job, Phase, Service, Skill, TimeSlot
from ...selectors.involvement import job_involvement_q, phase_involvement_q


class QSearchFilter(SearchFilter):
    """Free-text search on ``?q=`` (the views' ``search_fields``)."""

    search_param = "q"


class NumberInFilter(django_filters.BaseInFilter, django_filters.NumberFilter):
    """``?status__in=1,2,3``"""


def _resolve_user(request, value):
    if value == "me":
        return request.user
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError({"user": ["Expected a user id or 'me'."]})


class MeOrIdFilter(django_filters.CharFilter):
    """A user id, or ``me`` for the caller."""

    def filter(self, qs, value):
        if value in (None, ""):
            return qs
        user = _resolve_user(self.parent.request, value)
        return qs.filter(**{self.field_name: user})


class MeFilter(django_filters.CharFilter):
    """Accepts only ``me``; applies ``method(qs, user)``."""

    def __init__(self, *args, predicate=None, **kwargs):
        self.predicate = predicate
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if value in (None, ""):
            return qs
        if value != "me":
            raise ValidationError({self.field_name: ["Only 'me' is supported."]})
        return qs.filter(self.predicate(self.parent.request.user)).distinct()


class JobFilter(django_filters.FilterSet):
    status__in = NumberInFilter(field_name="status", lookup_expr="in")
    unit = django_filters.NumberFilter(field_name="unit_id")
    client = django_filters.NumberFilter(field_name="client_id")
    account_manager = MeOrIdFilter(field_name="account_manager")
    involving = MeFilter(predicate=job_involvement_q)
    desired_start_after = django_filters.DateFilter(
        field_name="desired_start_date", lookup_expr="gte"
    )
    desired_start_before = django_filters.DateFilter(
        field_name="desired_start_date", lookup_expr="lte"
    )

    class Meta:
        model = Job
        fields = ["status"]


class PhaseFilter(django_filters.FilterSet):
    job = django_filters.NumberFilter(field_name="job_id")
    status__in = NumberInFilter(field_name="status", lookup_expr="in")
    service = django_filters.NumberFilter(field_name="service_id")
    unit = django_filters.NumberFilter(field_name="job__unit_id")
    client = django_filters.NumberFilter(field_name="job__client_id")
    lead = MeOrIdFilter(field_name="project_lead")
    author = MeOrIdFilter(field_name="report_author")
    techqa_by = MeOrIdFilter(field_name="techqa_by")
    presqa_by = MeOrIdFilter(field_name="presqa_by")
    involving = MeFilter(predicate=phase_involvement_q)

    class Meta:
        model = Phase
        fields = ["status"]


class TimeSlotFilter(django_filters.FilterSet):
    """``start``/``end`` select slots overlapping the window."""

    start = django_filters.IsoDateTimeFilter(field_name="end", lookup_expr="gt")
    end = django_filters.IsoDateTimeFilter(field_name="start", lookup_expr="lt")
    user = MeOrIdFilter(field_name="user")
    phase = django_filters.NumberFilter(field_name="phase_id")
    project = django_filters.NumberFilter(field_name="project_id")
    slot_type = django_filters.NumberFilter(field_name="slot_type_id")

    class Meta:
        model = TimeSlot
        fields = []


LEAVE_STATUS = {
    "pending": Q(authorised=False, declined=False, cancelled=False),
    "authorised": Q(authorised=True, cancelled=False),
    "declined": Q(declined=True),
    "cancelled": Q(cancelled=True),
}


class LeaveRequestFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        choices=[(k, k) for k in LEAVE_STATUS], method="filter_status"
    )
    user = MeOrIdFilter(field_name="user")
    reports_of = MeFilter(
        predicate=lambda u: Q(user__manager=u) | Q(user__acting_manager=u)
    )
    start = django_filters.DateFilter(field_name="end_date", lookup_expr="gte")
    end = django_filters.DateFilter(field_name="start_date", lookup_expr="lte")

    class Meta:
        model = LeaveRequest
        fields = []

    def filter_status(self, qs, name, value):
        return qs.filter(LEAVE_STATUS[value])


class UserFilter(django_filters.FilterSet):
    unit = django_filters.NumberFilter(method="filter_unit")
    manages = MeFilter(
        field_name="manages",
        predicate=lambda u: Q(manager=u) | Q(acting_manager=u),
    )
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = User
        fields = ["is_active"]

    def filter_unit(self, qs, name, value):
        return qs.filter(
            unit_memberships__unit_id=value, unit_memberships__left_date__isnull=True
        ).distinct()


class SkillFilter(django_filters.FilterSet):
    category = django_filters.NumberFilter(field_name="category_id")

    class Meta:
        model = Skill
        fields = []


class ServiceFilter(django_filters.FilterSet):
    core = django_filters.BooleanFilter(field_name="is_core")

    class Meta:
        model = Service
        fields = []
