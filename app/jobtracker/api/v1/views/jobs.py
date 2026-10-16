"""Jobs and projects."""

from django.db.models import Count
from guardian.shortcuts import get_objects_for_user



from ....models import (
    Job,
    Project,
)
from ..base import BaseReadOnlyAPIViewSet
from ..serializers import (
    JobSerializer,
    ProjectSerializer,
)


# ---------------------------------------------------------------------------
# Foundation / coherence entities
# ---------------------------------------------------------------------------


class JobViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = JobSerializer

    def get_base_queryset(self):
        return Job.objects.select_related("unit", "client").annotate(
            phase_count=Count("phases", distinct=True)
        )

    def scope_queryset(self, queryset, user):
        # Faithful to JobPermissionRequiredMixin: unit `can_view_jobs` OR the
        # team-membership guest bypass (jobs_for_user).
        # ``jobs_for_user`` is a ``.distinct()`` queryset while
        # ``jobs_with_unit_permission`` is not; combining a distinct and a
        # non-distinct query with ``|`` raises "Cannot combine a unique query
        # with a non-unique query". Union the pks instead.
        allowed_ids = set(
            Job.objects.jobs_with_unit_permission(
                user, "jobtracker.can_view_jobs"
            ).values_list("pk", flat=True)
        )
        allowed_ids.update(
            Job.objects.jobs_for_user(user).values_list("pk", flat=True)
        )
        return queryset.filter(pk__in=allowed_ids)


class ProjectViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = ProjectSerializer

    def get_base_queryset(self):
        return Project.objects.select_related("unit", "primary_poc", "created_by")

    def scope_queryset(self, queryset, user):
        # Projects are gated by the ``view_project`` model permission (there is
        # no unit-level project permission), plus the team-membership bypass.
        # get_objects_for_user honours a global grant (returns all) or the
        # per-object grants otherwise, matching ProjectListView.
        allowed_ids = set(
            get_objects_for_user(
                user, "jobtracker.view_project", klass=Project
            ).values_list("pk", flat=True)
        )
        allowed_ids.update(
            Project.objects.projects_for_user(user).values_list("pk", flat=True)
        )
        return queryset.filter(pk__in=allowed_ids)
