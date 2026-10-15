from chaotica_utils.mixins import SecurePermissionRequiredMixin as PermissionRequiredMixin, ObjectActivityMixin
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse, reverse_lazy
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.template import loader
from django.db.models import Count
from django.utils import timezone
from guardian.shortcuts import get_objects_for_user
from chaotica_utils.decorators import permission_required_or_403
from chaotica_utils.models import User
from chaotica_utils.views import ChaoticaBaseView, ProtectedDeleteMixin
from ..models import BillingCode, OrganisationalUnit
from ..forms import BillingCodeForm, InlineBillingCodeForm
import datetime
import logging


logger = logging.getLogger(__name__)


class BillingCodeBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = BillingCode
    fields = "__all__"
    permission_required = "jobtracker.view_billingcode"
    accept_global_perms = True
    return_403 = True

    def get_success_url(self):
        if "slug" in self.kwargs:
            slug = self.kwargs["slug"]
            return reverse_lazy("billingcode_detail", kwargs={"slug": slug})
        else:
            return reverse_lazy("billingcode_list")


class BillingCodeListView(BillingCodeBaseView, ListView):
    """List billing codes the current user can actually reach.

    Scoped via :meth:`BillingCodeManager.for_user` so a user only sees their
    unit's clients' codes plus client-less/internal codes — this replaces the
    previous site-wide list that exposed every client's codes.
    """

    def get_queryset(self):
        return (
            BillingCode.objects.for_user(self.request.user)
            .select_related("client")
            .annotate(
                job_count=Count("assignments__job", distinct=True),
                phase_count=Count("assignments__phase", distinct=True),
                project_count=Count("assignments__project", distinct=True),
            )
        )


class BillingCodeDetailView(ObjectActivityMixin, BillingCodeBaseView, PermissionRequiredMixin, DetailView):
    """View to list the details from one job.
    Use the 'job' variable in the template to access
    the specific job here and in the Views below"""

    permission_required = "jobtracker.view_billingcode"
    accept_global_perms = True
    return_403 = True
    slug_url_kwarg = "code"
    slug_field = "code"

    def get_queryset(self):
        # Scope by reachability so a direct URL can't leak another client's code.
        return BillingCode.objects.for_user(self.request.user).select_related(
            "client"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        code = self.object
        today = timezone.now().date()
        assignments = list(
            code.assignments.select_related(
                "job", "job__client", "phase", "phase__job", "project", "created_by"
            ).order_by("-start_date", "-created_at")
        )
        for a in assignments:
            a.is_current = (a.start_date is None or a.start_date <= today) and (
                a.end_date is None or a.end_date >= today
            )
        context["assignments"] = assignments
        context["current_assignment_count"] = sum(1 for a in assignments if a.is_current)
        context["job_assignment_count"] = sum(1 for a in assignments if a.job_id)
        context["phase_assignment_count"] = sum(1 for a in assignments if a.phase_id)
        context["project_assignment_count"] = sum(1 for a in assignments if a.project_id)

        return context


class BillingCodeCreateView(BillingCodeBaseView, PermissionRequiredMixin, CreateView):
    form_class = BillingCodeForm
    fields = None

    permission_required = "jobtracker.add_billingcode"
    accept_global_perms = True
    permission_object = BillingCode
    return_403 = True


class BillingCodeUpdateView(BillingCodeBaseView, PermissionRequiredMixin, UpdateView):
    form_class = BillingCodeForm
    fields = None

    permission_required = "jobtracker.change_billingcode"
    accept_global_perms = True
    return_403 = True
    slug_url_kwarg = "code"
    slug_field = "code"


class BillingCodeDeleteView(ProtectedDeleteMixin, BillingCodeBaseView, PermissionRequiredMixin, DeleteView):
    """View to delete a billing code."""

    permission_required = "jobtracker.delete_billingcode"
    accept_global_perms = True
    return_403 = True
    success_url = reverse_lazy("billingcode_list")
    slug_url_kwarg = "code"
    slug_field = "code"


@login_required
@permission_required_or_403("jobtracker.add_billingcode")
def billingcode_create_inline(request):
    """Create a billing code from inside the assign modal, returning JSON.

    Mirrors the ``js-submit-modal-form`` envelope loosely: on success returns
    ``{success, id, text}`` so the modal JS can inject the new code straight
    into the select2 without a page reload; on failure returns the field errors.
    Gated on ``add_billingcode`` (and per-client ``view_client`` in the form).
    """
    if request.method != "POST":
        return HttpResponseBadRequest()

    form = InlineBillingCodeForm(request.POST, prefix="newbc", user=request.user)
    if form.is_valid():
        bc = form.save()
        text = bc.code if not bc.client else f"{bc.code} — {bc.client}"
        return JsonResponse({"success": True, "id": bc.pk, "text": text})
    return JsonResponse(
        {"success": False, "errors": form.errors.get_json_data()}, status=400
    )


def _analytics_users(request):
    """Users an analytics viewer may aggregate over.

    Superusers span everyone; otherwise scope to active users in units the
    requester can view jobs in, so the roll-up stays permission-faithful and
    bounded.
    """
    if request.user.is_superuser:
        return User.objects.filter(is_active=True)
    units = get_objects_for_user(
        request.user, "jobtracker.can_view_jobs", klass=OrganisationalUnit
    )
    return User.objects.filter(
        is_active=True, unit_memberships__unit__in=units
    ).distinct()


def _analytics_range(request, default=None):
    from .helpers import _stats_range

    return _stats_range(request, default=default)


@login_required
@permission_required_or_403("jobtracker.view_billingcode")
def billingcode_analytics(request):
    """Sales/client analysis over billing-code usage.

    Aggregates scheduled hours per code across the viewer's reachable users
    within a date window, rolled up by client and chargeable vs internal.
    """
    from chaotica_utils.utils import build_code_analytics

    today = timezone.now().date()
    start, end, range_ctx = _analytics_range(
        request, default=(today.replace(day=1), today + datetime.timedelta(days=28))
    )
    users = _analytics_users(request)
    analytics = build_code_analytics(users, start, end)

    per_code = sorted(
        analytics["per_code"].values(),
        key=lambda c: c["hours"],
        reverse=True,
    )
    by_client = sorted(
        analytics["by_client"].values(),
        key=lambda b: b["hours"],
        reverse=True,
    )
    context = {
        "start_date": start,
        "end_date": end,
        "per_code": per_code,
        "by_client": by_client,
        "totals": analytics["totals"],
        "partial_url": reverse("billingcode_analytics"),
        **range_ctx,
    }
    return render(request, "jobtracker/billingcode_analytics.html", context)


@login_required
@permission_required_or_403("jobtracker.view_billingcode")
def billingcode_analytics_partial(request, code):
    """Analytics tab on a billing code: who booked against it, on what, when.

    Lazily loaded (JSON ``{html}``); scoped to codes and users the viewer can
    reach, same as the Billing Analytics page.
    """
    from chaotica_utils.utils import build_single_code_analytics

    billingcode = get_object_or_404(
        BillingCode.objects.for_user(request.user), code=code
    )
    # Default to the last 12 months (matches the "12m" preset).
    today = timezone.now().date()
    start, end, range_ctx = _analytics_range(
        request, default=(today - datetime.timedelta(days=365), today)
    )
    analytics = build_single_code_analytics(
        billingcode, _analytics_users(request), start, end
    )
    context = {
        "billingcode": billingcode,
        "start_date": start,
        "end_date": end,
        "analytics": analytics,
        "partial_url": reverse(
            "billingcode_analytics_partial", kwargs={"code": billingcode.code}
        ),
        **range_ctx,
    }
    html = loader.render_to_string(
        "partials/billingcode/code_analytics.html", context, request=request
    )
    return JsonResponse({"html": html})
