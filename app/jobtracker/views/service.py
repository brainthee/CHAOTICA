from chaotica_utils.mixins import SecurePermissionRequiredMixin as PermissionRequiredMixin, ObjectActivityMixin
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.template import loader
from chaotica_utils.decorators import permission_required_or_403
from chaotica_utils.views import ChaoticaBaseView, ProtectedDeleteMixin
from ..models import Service
from ..enums import PhaseStatuses
from ..forms import ServiceForm
from ..mixins import PrefetchRelatedMixin
from ..utils import phases_visible_to
import logging


logger = logging.getLogger(__name__)


class ServiceBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = Service
    fields = "__all__"
    permission_required = "jobtracker.view_service"
    accept_global_perms = True
    return_403 = True

    def get_success_url(self):
        if "slug" in self.kwargs:
            slug = self.kwargs["slug"]
            return reverse_lazy("service_detail", kwargs={"slug": slug})
        else:
            return reverse_lazy("service_list")


class ServiceListView(ServiceBaseView, ListView):
    """Enhanced view to list services with core service focus and risk assessment"""

    def get_queryset(self):
        from django.db.models import Count, Q, Case, When, IntegerField
        from ..enums import UserSkillRatings

        # Optimize queryset with annotations for risk assessment
        return Service.objects.select_related().prefetch_related(
            'skillsRequired', 'skillsDesired', 'owners'
        ).annotate(
            # Count specialists for risk assessment
            specialist_count=Count(
                'skillsRequired__users',
                filter=Q(skillsRequired__users__rating=UserSkillRatings.SPECIALIST),
                distinct=True
            ),
            # Count total people with skills
            skilled_people_count=Count(
                'skillsRequired__users',
                distinct=True
            ),
            # Count active phases
            active_phases_count=Count(
                'phases',
                filter=Q(phases__status__in=PhaseStatuses.SERVICE_ACTIVE),
                distinct=True
            ),
            # Risk score calculation (0 = high risk, higher = lower risk)
            risk_score=Case(
                When(specialist_count=0, then=0),  # Critical risk
                When(specialist_count=1, then=1),  # High risk
                When(specialist_count=2, then=2),  # Medium risk
                default=3,  # Low risk
                output_field=IntegerField()
            )
        ).order_by('-is_core', 'risk_score', 'name')  # Core services first, then by risk

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Separate core and non-core services for better presentation
        services = context['service_list'].order_by("name")
        context['core_services'] = [s for s in services if s.is_core]
        context['other_services'] = [s for s in services if not s.is_core]

        # Risk statistics
        core_at_risk = sum(1 for s in context['core_services'] if s.risk_score <= 1)
        context['risk_stats'] = {
            'total_core_services': len(context['core_services']),
            'core_at_risk': core_at_risk,
            'risk_percentage': round((core_at_risk / len(context['core_services']) * 100), 1) if context['core_services'] else 0
        }

        return context


class ServiceDetailView(
    ObjectActivityMixin, PrefetchRelatedMixin, ServiceBaseView, PermissionRequiredMixin, DetailView
):
    prefetch_related = [
        "owners",
        "skillsRequired",
        "skillsDesired",
        "qualificationsRequired",
        "qualificationsDesired",
    ]
    """View to list the details from one job.
    Use the 'job' variable in the template to access
    the specific job here and in the Views below"""

    permission_required = "jobtracker.view_service"
    accept_global_perms = True
    return_403 = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Users holding ALL qualifications required to deliver this service.
        context["users_with_required_quals"] = list(
            self.object.get_users_with_required_quals()
        )
        # Jobs tab: summary, badges and lists all cover only the phases on
        # jobs the viewer can see (the lists load per bucket on demand).
        context["analytics"] = self.object.get_service_usage_analytics(
            phases=phases_visible_to(self.request.user, self.object.phases.all()),
            cache_scope="user{}".format(self.request.user.pk),
        )
        return context


class ServiceCreateView(ServiceBaseView, PermissionRequiredMixin, CreateView):
    form_class = ServiceForm
    fields = None

    permission_required = "jobtracker.add_service"
    accept_global_perms = True
    permission_object = Service
    return_403 = True


class ServiceUpdateView(ServiceBaseView, PermissionRequiredMixin, UpdateView):
    form_class = ServiceForm
    fields = None

    permission_required = "jobtracker.change_service"
    accept_global_perms = True
    return_403 = True


class ServiceDeleteView(ProtectedDeleteMixin, ServiceBaseView, PermissionRequiredMixin, DeleteView):
    """View to delete a service."""

    permission_required = "jobtracker.delete_service"
    accept_global_perms = True
    return_403 = True
    success_url = reverse_lazy("service_list")


SERVICE_PHASE_BUCKETS = {
    "active": PhaseStatuses.SERVICE_ACTIVE,
    "upcoming": PhaseStatuses.SERVICE_UPCOMING,
    "completed": PhaseStatuses.SERVICE_COMPLETED,
    "all": None,
}


@login_required
@permission_required_or_403(
    "jobtracker.view_service", (Service, "slug", "slug"), accept_global_perms=True
)
def service_phases_partial(request, slug, bucket):
    """One of the service page's Active / Upcoming / Completed / All phase
    lists, limited to phases on jobs the viewer can see."""
    if bucket not in SERVICE_PHASE_BUCKETS:
        raise Http404
    service = get_object_or_404(Service, slug=slug)
    phases = phases_visible_to(request.user, service.phases.all())
    statuses = SERVICE_PHASE_BUCKETS[bucket]
    if statuses is not None:
        phases = phases.filter(status__in=statuses)
    html = loader.render_to_string(
        "partials/phase/phase_list_table.html",
        {"phases": phases, "no_schedule_bar": 1},
        request=request,
    )
    return JsonResponse({"html": html})
