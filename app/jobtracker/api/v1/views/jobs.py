"""Jobs and projects."""

from django.db.models import Count
from django.db.models.functions import Coalesce
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ....models import Job, Phase, Project
from ....utils import merge_include_users
from ....selectors.jobs import (
    can_view_loaded_costs,
    job_sales_summary,
    job_support_roles,
)
from ....selectors.schedule import job_team
from .. import filters
from ..base import BaseReadOnlyAPIViewSet
from ..serializers import (
    JobDetailSerializer,
    JobSalesSerializer,
    JobSerializer,
    JobTeamMemberSerializer,
    PhaseSerializer,
    ProjectSerializer,
    ScheduleSerializer,
    SupportRoleSerializer,
)
from ._engagement import NotesActivityMixin
from ..schedule import (
    SCHEDULE_QUERY_PARAMS,
    build_schedule_payload,
    parse_schedule_window,
)


def _truthy(value):
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


SCHEDULE_PARAMS = SCHEDULE_QUERY_PARAMS + [
    OpenApiParameter(
        "hard",
        bool,
        description="Only this schedule's slots (default: also the people's "
        "other commitments, flagged via ``scope``).",
    ),
    OpenApiParameter(
        "include_user",
        int,
        many=True,
        description="Also show these people (if you can see their schedule).",
    ),
]


FINANCE_FIELDS = ("staff_cost", "profit", "profit_perc", "meets_target", "support_pool")


class JobViewSet(NotesActivityMixin, BaseReadOnlyAPIViewSet):
    serializer_class = JobSerializer
    policy_scope = "job.view"
    filterset_class = filters.JobFilter
    ordering_fields = (
        "id",
        "title",
        "status",
        "desired_start_date",
        "desired_delivery_date",
        "start_date",
        "delivery_date",
    )
    ordering_aliases = {"start_date": "start_on", "delivery_date": "delivery_on"}
    ordering = ("-pk",)  # newest first, as the job list always was
    search_fields = ("title", "=id", "client__name", "unit__name")

    def get_serializer_class(self):
        return JobDetailSerializer if self.action == "retrieve" else JobSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "policy": self.policy}

    def get_base_queryset(self):
        qs = Job.objects.select_related("unit", "client", "account_manager").annotate(
            phase_count=Count("phases", distinct=True),
            start_on=Coalesce("desired_start_date", "_start_date"),
            delivery_on=Coalesce("desired_delivery_date", "_delivery_date"),
        )
        if self.action == "retrieve":
            qs = qs.select_related(
                "dep_account_manager",
                "created_by",
                "scoped_signed_off_by",
                "primary_client_poc__company",
                "associated_framework__client",
            ).prefetch_related(
                "scoped_by",
                "additional_contacts__company",
                "previous_jobs",
                "indicative_services",
                "links",
                "billing_code_assignments__code",
                "phases",
            )
        return qs

    @extend_schema(responses=PhaseSerializer(many=True), summary="Phases of a job")
    @action(detail=True, methods=["get"], filter_backends=[])
    def phases(self, request, pk=None):
        job = self.get_object()
        phases = self.policy.scope(
            "phase.view",
            Phase.objects.filter(job=job).select_related(
                "job__client",
                "service",
                "project_lead",
                "report_author",
                "techqa_by",
                "presqa_by",
            ),
        ).order_by("phase_number")
        page = self.paginate_queryset(phases)
        return self.get_paginated_response(
            PhaseSerializer(page, many=True, context=self.get_serializer_context()).data
        )

    @extend_schema(
        parameters=SCHEDULE_PARAMS,
        responses=ScheduleSerializer,
        summary="Job schedule window",
    )
    @action(detail=True, methods=["get"], filter_backends=[], pagination_class=None)
    def schedule(self, request, pk=None):
        job = self.get_object()
        if not self.policy.can("job.view_schedule", job):
            raise PermissionDenied("You can't view this job's schedule.")
        start, end = parse_schedule_window(request)
        users = merge_include_users(request._request, job.team_scheduled())
        return Response(
            build_schedule_payload(
                users,
                start,
                end,
                scope_phases=job.phases.all(),
                hard_scope=_truthy(request.query_params.get("hard")),
                request=request,
            )
        )

    @extend_schema(responses=JobTeamMemberSerializer(many=True), summary="Job team")
    @action(detail=True, methods=["get"], filter_backends=[], pagination_class=None)
    def team(self, request, pk=None):
        job = self.get_object()
        if not self.policy.can("job.view_schedule", job):
            raise PermissionDenied("You can't view this job's schedule.")
        _labels, entries = job_team(job)
        return Response(
            JobTeamMemberSerializer(
                entries, many=True, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(responses=JobSalesSerializer, summary="Sales summary")
    @action(detail=True, methods=["get"], filter_backends=[], pagination_class=None)
    def sales(self, request, pk=None):
        job = self.get_object()
        finance = can_view_loaded_costs(request.user, job)
        summary = job_sales_summary(job, include_costs=finance)
        if not finance:
            # The main UI shows staff cost and profit to every job viewer;
            # the API keeps cost-derived figures for finance (debt register).
            summary.update({key: None for key in FINANCE_FIELDS})
        summary["support_members"] = [
            {
                "user": m["user"],
                "role": m["role"],
                "share_percent": m["share_percent"],
                "budget_money": m["budget_money"] if finance else None,
                "budget_days": m["budget_days"] if finance else None,
            }
            for m in summary["support_members"]
        ]
        summary["includes_finance"] = finance
        return Response(
            JobSalesSerializer(summary, context=self.get_serializer_context()).data
        )

    @extend_schema(responses=SupportRoleSerializer(many=True), summary="Support team")
    @action(
        detail=True,
        methods=["get"],
        url_path="support-team",
        filter_backends=[],
        pagination_class=None,
    )
    def support_team(self, request, pk=None):
        job = self.get_object()
        finance = can_view_loaded_costs(request.user, job)
        roles = job_support_roles(job, request.user, finance)
        context = {**self.get_serializer_context(), "can_view_money": finance}
        return Response(SupportRoleSerializer(roles, many=True, context=context).data)


class ProjectViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = ProjectSerializer
    policy_scope = "project.view"
    ordering_fields = ("id", "title", "status")
    search_fields = ("title", "=id")

    def get_base_queryset(self):
        return Project.objects.select_related(
            "unit", "primary_poc", "created_by"
        ).annotate(**Project.schedule_date_annotations())

    @extend_schema(
        parameters=SCHEDULE_QUERY_PARAMS,
        responses=ScheduleSerializer,
        summary="Project schedule window",
    )
    @action(detail=True, methods=["get"], filter_backends=[], pagination_class=None)
    def schedule(self, request, pk=None):
        project = self.get_object()
        # As the project page's schedule tab: global view_project.
        if not request.user.has_perm("jobtracker.view_project"):
            raise PermissionDenied("You can't view project schedules.")
        from ....views.project import _project_scheduled_users

        start, end = parse_schedule_window(request)
        users = _project_scheduled_users(project)
        return Response(
            build_schedule_payload(
                users, start, end, scope_projects=[project], request=request
            )
        )
