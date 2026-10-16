"""Jobs and projects."""

from django.db.models import Count


from ....models import (
    Job,
    Project,
)
from .. import filters
from ..base import BaseReadOnlyAPIViewSet
from ..serializers import (
    JobSerializer,
    ProjectSerializer,
)


class JobViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = JobSerializer
    policy_scope = "job.view"
    filterset_class = filters.JobFilter
    ordering_fields = (
        "id",
        "title",
        "status",
        "desired_start_date",
        "desired_delivery_date",
    )
    search_fields = ("title", "=id", "client__name")

    def get_base_queryset(self):
        return Job.objects.select_related("unit", "client", "account_manager").annotate(
            phase_count=Count("phases", distinct=True)
        )


class ProjectViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = ProjectSerializer
    policy_scope = "project.view"
    ordering_fields = ("id", "title", "status")
    search_fields = ("title", "=id")

    def get_base_queryset(self):
        return Project.objects.select_related("unit", "primary_poc", "created_by")
