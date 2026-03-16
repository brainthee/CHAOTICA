from guardian.mixins import PermissionRequiredMixin
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.utils import timezone
from django.db.models import Count, Q, Prefetch
from datetime import timedelta
from chaotica_utils.views import ChaoticaBaseView
from ..models import Qualification, AwardingBody, QualificationRecord, QualificationTag
from ..enums import QualificationStatus
from ..forms import QualificationForm, AwardingBodyForm
import logging


logger = logging.getLogger(__name__)


class QualificationAwardingBodyBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = AwardingBody
    fields = "__all__"
    permission_required = "jobtracker.view_awardingbody"
    return_403 = True
    accept_global_perms = True
    success_url = reverse_lazy("qualification_list")


class QualificationAwardingBodyCreateView(
    QualificationAwardingBodyBaseView, PermissionRequiredMixin, CreateView
):
    form_class = AwardingBodyForm
    fields = None
    permission_required = "jobtracker.add_awardingbody"
    permission_object = AwardingBody
    return_403 = True
    accept_global_perms = True


class QualificationAwardingUpdateView(
    QualificationAwardingBodyBaseView, PermissionRequiredMixin, UpdateView
):
    form_class = AwardingBodyForm
    fields = None
    permission_required = "jobtracker.change_awardingbody"
    return_403 = True
    accept_global_perms = True


class QualificationAwardingDeleteView(
    QualificationAwardingBodyBaseView, PermissionRequiredMixin, DeleteView
):
    permission_required = "jobtracker.delete_awardingbody"
    return_403 = True
    accept_global_perms = True


class QualificationBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = Qualification
    fields = "__all__"
    permission_required = "jobtracker.view_qualification"
    accept_global_perms = True
    return_403 = True

    def get_context_data(self, **kwargs):
        context = super(QualificationBaseView, self).get_context_data(**kwargs)
        context["awarding_bodies"] = AwardingBody.objects.all()
        return context

    def get_success_url(self):
        if "slug" in self.kwargs and "bodySlug" in self.kwargs:
            slug = self.kwargs["slug"]
            bodySlug = self.kwargs["bodySlug"]
            return reverse_lazy(
                "qualification_detail", kwargs={"bodySlug": bodySlug, "slug": slug}
            )
        else:
            return reverse_lazy("qualification_list")


class QualificationListView(QualificationBaseView, ListView):
    """View to list all qualifications with stats."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()

        # Annotated qualifications prefetched onto awarding bodies
        annotated_quals = Qualification.objects.annotate(
            annotated_awarded_count=Count(
                "users",
                filter=Q(users__status=QualificationStatus.AWARDED),
            ),
            annotated_total_records=Count("users"),
        )
        context["awarding_bodies"] = AwardingBody.objects.prefetch_related(
            Prefetch("qualifications", queryset=annotated_quals)
        )

        # Global stats
        all_records = QualificationRecord.objects.all()
        context["total_qualifications"] = Qualification.objects.count()
        context["total_qualified_users"] = (
            all_records.filter(status=QualificationStatus.AWARDED)
            .values("user")
            .distinct()
            .count()
        )
        context["total_expiring_soon"] = all_records.filter(
            status=QualificationStatus.AWARDED,
            lapse_date__isnull=False,
            lapse_date__lte=today + timedelta(days=90),
            lapse_date__gt=today,
        ).count()
        context["total_lapsed"] = all_records.filter(
            status=QualificationStatus.LAPSED,
        ).count()

        # Tags for filtering
        context["tags"] = QualificationTag.objects.all()

        return context


class QualificationDetailView(
    QualificationBaseView, PermissionRequiredMixin, DetailView
):
    permission_required = "jobtracker.view_qualification"
    accept_global_perms = True
    return_403 = True

    def get_queryset(self):
        return Qualification.objects.select_related("awarding_body")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qualification = self.object
        today = timezone.now().date()

        records = qualification.users.select_related("user", "verified_by").order_by("-awarded_date")

        # Status counts
        context["awarded_count"] = records.filter(
            status=QualificationStatus.AWARDED
        ).count()
        context["in_progress_count"] = records.filter(
            status__in=[QualificationStatus.IN_PROGRESS, QualificationStatus.PENDING]
        ).count()
        context["lapsed_count"] = records.filter(
            status=QualificationStatus.LAPSED
        ).count()
        context["expiring_soon_count"] = records.filter(
            status=QualificationStatus.AWARDED,
            lapse_date__isnull=False,
            lapse_date__lte=today + timedelta(days=90),
            lapse_date__gt=today,
        ).count()

        # Record sets for tabs
        context["awarded_records"] = records.filter(
            status=QualificationStatus.AWARDED
        )
        context["in_progress_records"] = records.filter(
            status__in=[
                QualificationStatus.IN_PROGRESS,
                QualificationStatus.PENDING,
                QualificationStatus.ATTEMPTED,
            ]
        )
        context["all_records"] = records

        return context


class QualificationCreateView(
    QualificationBaseView, PermissionRequiredMixin, CreateView
):
    form_class = QualificationForm
    fields = None
    permission_required = "jobtracker.add_qualification"
    accept_global_perms = True
    permission_object = Qualification
    return_403 = True

    def get_context_data(self, **kwargs):
        context = super(QualificationCreateView, self).get_context_data(**kwargs)
        context["awardingbody"] = AwardingBody.objects.get(slug=self.kwargs["bodySlug"])
        return context

    def form_valid(self, form):
        form.instance.awarding_body = AwardingBody.objects.get(
            slug=self.kwargs["bodySlug"]
        )
        return super(QualificationCreateView, self).form_valid(form)


class QualificationUpdateView(
    QualificationBaseView, PermissionRequiredMixin, UpdateView
):
    form_class = QualificationForm
    fields = None

    permission_required = "jobtracker.change_qualification"
    accept_global_perms = True
    return_403 = True


class QualificationDeleteView(
    QualificationBaseView, PermissionRequiredMixin, DeleteView
):
    permission_required = "jobtracker.delete_qualification"
    accept_global_perms = True
    return_403 = True
