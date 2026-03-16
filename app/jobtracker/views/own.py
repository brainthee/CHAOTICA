from django.views.generic.list import ListView
from django.db.models import Q
from chaotica_utils.views import ChaoticaBaseView
from chaotica_utils.models import User
from ..models import QualificationRecord
from ..enums import QualificationStatus
from ..forms import OwnQualificationRecordForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.utils import timezone
from datetime import timedelta
import logging
from django.template import loader
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods


logger = logging.getLogger(__name__)


def _auto_calculate_lapse_date(record):
    """Auto-calculate lapse_date from awarded_date + validity_period if applicable."""
    if record.awarded_date and record.qualification.validity_period:
        days = record.qualification.validity_period
        if days > 36500:  # Cap at ~100 years
            return
        record.lapse_date = record.awarded_date + timedelta(days=days)


class OwnQualificationRecordBaseView(ChaoticaBaseView):
    model = QualificationRecord
    fields = "__all__"


class OwnQualificationRecordListView(OwnQualificationRecordBaseView, ListView):
    """View to list a user's own qualification records."""

    def get_queryset(self):
        return (
            QualificationRecord.objects.filter(user=self.request.user)
            .select_related("qualification", "qualification__awarding_body", "verified_by", "user")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        records = self.get_queryset()
        today = timezone.now().date()

        context["awarded_count"] = records.filter(
            status=QualificationStatus.AWARDED
        ).count()
        context["in_progress_count"] = records.filter(
            status__in=[QualificationStatus.IN_PROGRESS, QualificationStatus.PENDING]
        ).count()
        context["lapsed_count"] = records.filter(
            status=QualificationStatus.LAPSED
        ).count()

        expiring_qs = records.filter(
            status=QualificationStatus.AWARDED,
            lapse_date__isnull=False,
            lapse_date__lte=today + timedelta(days=90),
            lapse_date__gt=today,
        )
        context["expiring_count"] = expiring_qs.count()
        context["expiring_records"] = expiring_qs

        critical_qs = records.filter(
            status=QualificationStatus.AWARDED,
            lapse_date__isnull=False,
            lapse_date__lte=today + timedelta(days=30),
            lapse_date__gt=today,
        )
        context["critical_records"] = critical_qs

        # Check if user has direct reports for showing team link
        context["has_direct_reports"] = (
            self.request.user.users_managed.exists()
            or self.request.user.users_acting_managed.exists()
        )

        return context


@login_required
@require_http_methods(["POST", "GET"])
def add_own_qualification(request):
    data = dict()
    if request.method == "POST":
        form = OwnQualificationRecordForm(
            request.POST,
            request.FILES,
        )
        if form.is_valid():
            record = form.save(commit=False)
            record.user = request.user
            _auto_calculate_lapse_date(record)
            record.save()
            data["form_is_valid"] = True
    else:
        form = OwnQualificationRecordForm()

    context = {"form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/qualificationrecord_form.html", context, request=request
    )
    return JsonResponse(data)


@login_required
@require_http_methods(["POST", "GET"])
def update_own_qualification(request, pk):
    record = get_object_or_404(QualificationRecord, pk=pk, user=request.user)
    data = dict()
    if request.method == "POST":
        form = OwnQualificationRecordForm(request.POST, request.FILES, instance=record)
        if form.is_valid():
            updated_record = form.save(commit=False)
            updated_record.user = request.user
            if "awarded_date" in form.changed_data:
                _auto_calculate_lapse_date(updated_record)
            updated_record.save()
            data["form_is_valid"] = True
    else:
        form = OwnQualificationRecordForm(instance=record)

    context = {"form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/qualificationrecord_form.html", context, request=request
    )
    return JsonResponse(data)


@login_required
@require_http_methods(["POST"])
def transition_own_qualification(request, pk, action):
    """Quick-action endpoint for single-step status transitions."""
    record = get_object_or_404(QualificationRecord, pk=pk, user=request.user)

    target_status = QualificationStatus.QUICK_ACTIONS.get(action)
    if target_status is None:
        return JsonResponse({"error": "Unknown action '{}'.".format(action)}, status=400)

    current_label = record.get_status_display()
    target_label = dict(QualificationStatus.CHOICES).get(target_status, target_status)
    allowed = QualificationStatus.ALLOWED_TRANSITIONS.get(record.status, [])
    if target_status not in allowed:
        if allowed:
            allowed_labels = [dict(QualificationStatus.CHOICES).get(s, s) for s in allowed]
            return JsonResponse({
                "error": "Cannot move from '{}' to '{}'. Allowed transitions: {}.".format(
                    current_label, target_label, ", ".join(allowed_labels)
                )
            }, status=400)
        return JsonResponse({
            "error": "No transitions are available from '{}' status.".format(current_label)
        }, status=400)

    record.status = target_status
    today = timezone.now().date()

    # Set dates from POST data if provided
    if "attempt_date" in request.POST:
        try:
            record.attempt_date = timezone.datetime.strptime(
                request.POST["attempt_date"], "%Y-%m-%d"
            ).date()
        except (ValueError, TypeError):
            return JsonResponse({"error": "Invalid attempt date. Please use YYYY-MM-DD format."}, status=400)
        if record.attempt_date > today:
            return JsonResponse({"error": "Attempt date cannot be in the future."}, status=400)

    if "awarded_date" in request.POST:
        try:
            record.awarded_date = timezone.datetime.strptime(
                request.POST["awarded_date"], "%Y-%m-%d"
            ).date()
        except (ValueError, TypeError):
            return JsonResponse({"error": "Invalid awarded date. Please use YYYY-MM-DD format."}, status=400)
        if record.awarded_date > today:
            return JsonResponse({"error": "Awarded date cannot be in the future."}, status=400)
        if record.attempt_date and record.awarded_date < record.attempt_date:
            return JsonResponse({"error": "Awarded date cannot be before the attempt date ({}).".format(
                record.attempt_date.strftime("%d %b %Y")
            )}, status=400)
        _auto_calculate_lapse_date(record)

    if target_status == QualificationStatus.IN_PROGRESS:
        # Starting renewal — clear verification
        record.verified_by = None
        record.verified_on = None
    record.save()
    return JsonResponse({"success": True, "new_status": record.get_status_display()})


# --- Manager / Team views ---


class TeamQualificationListView(OwnQualificationRecordBaseView, ListView):
    """View for managers to see qualifications of their direct reports."""

    template_name = "jobtracker/team_qualificationrecord_list.html"

    def get_queryset(self):
        managed_users = User.objects.filter(
            Q(manager=self.request.user) | Q(acting_manager=self.request.user)
        )
        return (
            QualificationRecord.objects.filter(user__in=managed_users)
            .select_related(
                "qualification",
                "qualification__awarding_body",
                "user",
                "verified_by",
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        records = self.get_queryset()
        today = timezone.now().date()

        context["awarded_count"] = records.filter(
            status=QualificationStatus.AWARDED
        ).count()
        context["unverified_count"] = records.filter(
            status=QualificationStatus.AWARDED,
            verified_by__isnull=True,
            qualification__verification_required=True,
        ).count()
        context["expiring_count"] = records.filter(
            status=QualificationStatus.AWARDED,
            lapse_date__isnull=False,
            lapse_date__lte=today + timedelta(days=90),
            lapse_date__gt=today,
        ).count()
        context["lapsed_count"] = records.filter(
            status=QualificationStatus.LAPSED,
        ).count()

        context["unverified_records"] = records.filter(
            status=QualificationStatus.AWARDED,
            verified_by__isnull=True,
            qualification__verification_required=True,
        )

        return context


def _is_manager_of(request_user, target_user):
    """Check if request_user is the manager or acting_manager of target_user."""
    return (
        target_user.manager_id == request_user.pk
        or target_user.acting_manager_id == request_user.pk
    )


@login_required
@require_http_methods(["POST"])
def verify_qualification(request, pk):
    """Manager endpoint to verify an AWARDED qualification record."""
    record = get_object_or_404(
        QualificationRecord.objects.select_related("user"),
        pk=pk,
        status=QualificationStatus.AWARDED,
    )
    if not _is_manager_of(request.user, record.user):
        return HttpResponseForbidden("You are not this user's manager.")

    record.verified_by = request.user
    record.verified_on = timezone.now()
    record.save()
    return JsonResponse({"success": True})


@login_required
@require_http_methods(["POST"])
def unverify_qualification(request, pk):
    """Manager endpoint to remove verification from a qualification record."""
    record = get_object_or_404(
        QualificationRecord.objects.select_related("user"),
        pk=pk,
        status=QualificationStatus.AWARDED,
    )
    if not _is_manager_of(request.user, record.user):
        return HttpResponseForbidden("You are not this user's manager.")

    record.verified_by = None
    record.verified_on = None
    record.save()
    return JsonResponse({"success": True})
