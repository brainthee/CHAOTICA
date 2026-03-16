from guardian.mixins import PermissionRequiredMixin
from django.http import (
    JsonResponse,
)
from django.shortcuts import get_object_or_404
from guardian.shortcuts import get_objects_for_user
from guardian.decorators import permission_required_or_403
from django.views.decorators.http import (
    require_http_methods,
)
from django.template import loader
from chaotica_utils.views import log_system_activity, ChaoticaBaseView
from django.views.generic.list import ListView
from django.contrib import messages
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from ..models import (
    Client,
    ClientOnboarding,
    Contact,
    FrameworkAgreement,
    OrganisationalUnit,
)
from ..forms import (
    ClientForm,
    ClientOnboardingConfigForm,
    ClientOnboardingUserForm,
    ClientContactForm,
    ClientFrameworkForm,
    MergeClientForm,
)
from ..mixins import PrefetchRelatedMixin
from ..models import TimeSlot
from ..enums import TimeSlotDeliveryRole
from django.utils import timezone
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class ClientBaseView(PrefetchRelatedMixin, PermissionRequiredMixin, ChaoticaBaseView):
    prefetch_related = ["account_managers", "tech_account_managers", "jobs", "jobs__unit", "framework_agreements"]
    model = Client
    fields = "__all__"
    permission_required = "jobtracker.view_client"
    accept_global_perms = True
    return_403 = True

    def get_success_url(self):
        if "slug" in self.kwargs:
            slug = self.kwargs["slug"]
            return reverse_lazy("client_detail", kwargs={"slug": slug})
        else:
            return reverse_lazy("client_list")


class ClientListView(ClientBaseView, ListView):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""


class ClientDetailView(ClientBaseView, DetailView):
    """View to list the details from one job.
    Use the 'job' variable in the template to access
    the specific job here and in the Views below"""

    permission_required = "jobtracker.view_client"

    def get_context_data(self, **kwargs):
        context = super(ClientDetailView, self).get_context_data(**kwargs)
        # get a list of jobs we're allowed to view...
        my_jobs = get_objects_for_user(
            self.request.user, "jobtracker.view_job", context["client"].jobs.all()
        )
        context["allowedJobs"] = my_jobs

        # Bulk-compute framework allocation stats (1 query instead of 3N)
        frameworks = list(context["client"].framework_agreements.all())
        FrameworkAgreement.bulk_compute_days(frameworks)
        context["frameworks"] = frameworks

        return context


class ClientCreateView(ClientBaseView, CreateView):
    form_class = ClientForm
    fields = None

    permission_required = "jobtracker.add_client"
    accept_global_perms = True
    permission_object = OrganisationalUnit

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class ClientUpdateView(ClientBaseView, UpdateView):
    form_class = ClientForm
    fields = None

    permission_required = "jobtracker.change_client"


class ClientDeleteView(ClientBaseView, DeleteView):
    """View to delete a job"""

    permission_required = "jobtracker.delete_client"


@permission_required_or_403("jobtracker.change_client")
@require_http_methods(["GET", "POST"])
def client_onboarding_cfg(request, slug):
    client = get_object_or_404(Client, slug=slug)
    context = {}
    data = dict()
    if request.method == "POST":
        form = ClientOnboardingConfigForm(request.POST, instance=client)
        if form.is_valid():
            # Lets merge!
            form.save()
            data["form_is_valid"] = True
        else:
            # Merge failed!
            data["form_is_valid"] = False
    else:
        # Send the modal
        form = ClientOnboardingConfigForm(instance=client)

    context = {"form": form, "client": client}
    data["html_form"] = loader.render_to_string(
        "modals/client_onboarding_configuration.html", context, request=request
    )
    return JsonResponse(data)


@permission_required_or_403("jobtracker.change_client")
@require_http_methods(["GET", "POST"])
def client_onboarding_add_user(request, slug):
    client = get_object_or_404(Client, slug=slug)
    context = {}
    data = dict()
    if request.method == "POST":
        form = ClientOnboardingUserForm(request.POST, client=client)
        if form.is_valid():
            # Lets merge!
            form.save()
            data["form_is_valid"] = True
        else:
            # Merge failed!
            data["form_is_valid"] = False
    else:
        # Send the modal
        form = ClientOnboardingUserForm(client=client)

    context = {"form": form, "client": client}
    data["html_form"] = loader.render_to_string(
        "modals/client_onboarding_user.html", context, request=request
    )
    return JsonResponse(data)


@permission_required_or_403("jobtracker.change_client")
@require_http_methods(["GET", "POST"])
def client_onboarding_manage_user(request, slug, pk):
    client = get_object_or_404(Client, slug=slug)
    onboarding = get_object_or_404(ClientOnboarding, client=client, pk=pk)
    context = {}
    data = dict()
    if request.method == "POST":
        form = ClientOnboardingUserForm(request.POST, instance=onboarding, client=client)
        if form.is_valid():
            # Lets merge!
            form.save()
            data["form_is_valid"] = True
        else:
            # Merge failed!
            data["form_is_valid"] = False
    else:
        # Send the modal
        form = ClientOnboardingUserForm(instance=onboarding, client=client)

    context = {"form": form, "client": client}
    data["html_form"] = loader.render_to_string(
        "modals/client_onboarding_user.html", context, request=request
    )
    return JsonResponse(data)


@permission_required_or_403("jobtracker.change_client")
@require_http_methods(["GET", "POST"])
def client_onboarding_remove_user(request, slug, pk):
    client = get_object_or_404(Client, slug=slug)
    onboarding = get_object_or_404(ClientOnboarding, client=client, pk=pk)
    context = {}
    data = dict()
    if request.method == "POST":
        onboarding.delete()
        data["form_is_valid"] = True

    context = {"client": client}
    data["html_form"] = loader.render_to_string(
        "modals/client_onboarding_user_remove.html", context, request=request
    )
    return JsonResponse(data)


@permission_required_or_403("jobtracker.change_client")
@require_http_methods(["GET", "POST"])
def client_merge(request, slug):
    client = get_object_or_404(Client, slug=slug)
    context = {}
    data = dict()
    if request.method == "POST":
        form = MergeClientForm(request.POST)
        if form.is_valid():
            # Lets merge!
            client_to_merge = form.cleaned_data["client_to_merge"]
            if client_to_merge == client:
                # Same user. GTFO
                data["form_is_valid"] = False
                form.add_error("client_to_merge", "You can't merge to the same client!")
            elif not request.user.has_perm(
                "jobtracker.change_client", client_to_merge
            ) or not request.user.has_perm("jobtracker.delete_client", client_to_merge):
                # No perms. GTFO
                data["form_is_valid"] = False
                form.add_error(
                    "client_to_merge",
                    "You don't have change or delete permissions for the target client",
                )
            else:
                if client.merge(client_to_merge):
                    # Success
                    data["form_is_valid"] = True
                    messages.success(request, "Client merged")
                else:
                    # Merge failed!
                    data["form_is_valid"] = False
                    form.add_error("", "Failed to merge!")
    else:
        # Send the modal
        form = MergeClientForm()

    context = {"form": form, "client": client}
    data["html_form"] = loader.render_to_string(
        "modals/client_merge.html", context, request=request
    )
    return JsonResponse(data)


class ClientContactBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = Contact
    fields = "__all__"
    client_slug = None
    permission_required = "jobtracker.view_contact"
    accept_global_perms = True
    return_403 = True

    def get_success_url(self):
        pk = None
        if "pk" in self.kwargs:
            pk = self.kwargs["pk"]
        if "client_slug" in self.kwargs:
            client_slug = self.kwargs["client_slug"]

        if client_slug and pk:
            return reverse_lazy(
                "client_contact_detail", kwargs={"client_slug": client_slug, "pk": pk}
            )
        elif client_slug:
            return reverse_lazy("client_detail", kwargs={"slug": client_slug})
        else:
            return reverse_lazy("client_list")

    def get_context_data(self, **kwargs):
        context = super(ClientContactBaseView, self).get_context_data(**kwargs)
        if "client_slug" in self.kwargs:
            context["client"] = get_object_or_404(
                Client, slug=self.kwargs["client_slug"]
            )
        return context


class ClientContactListView(ClientContactBaseView, PermissionRequiredMixin, ListView):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""


class ClientContactDetailView(
    ClientContactBaseView, PermissionRequiredMixin, DetailView
):
    """View to list the details from one job.
    Use the 'job' variable in the template to access
    the specific job here and in the Views below"""


class ClientContactCreateView(
    ClientContactBaseView, PermissionRequiredMixin, CreateView
):
    form_class = ClientContactForm
    fields = None
    permission_object = Contact
    permission_required = "jobtracker.add_contact"

    def form_valid(self, form):
        form.instance.company = Client.objects.get(slug=self.kwargs["client_slug"])
        form.instance.save()
        log_system_activity(form.instance, "Created")
        return super(ClientContactCreateView, self).form_valid(form)

    def get_form_kwargs(self):
        kwargs = super(ClientContactCreateView, self).get_form_kwargs()
        if "client_slug" in self.kwargs:
            kwargs["client"] = get_object_or_404(
                Client, slug=self.kwargs["client_slug"]
            )
        return kwargs


class ClientContactUpdateView(
    ClientContactBaseView, PermissionRequiredMixin, UpdateView
):
    form_class = ClientContactForm
    fields = None


class ClientContactDeleteView(
    ClientContactBaseView, PermissionRequiredMixin, DeleteView
):
    def get_success_url(self):
        if "client_slug" in self.kwargs:
            client_slug = self.kwargs["client_slug"]

        if client_slug:
            return reverse_lazy("client_detail", kwargs={"slug": client_slug})
        else:
            return reverse_lazy("client_list")


class ClientFrameworkBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = FrameworkAgreement
    fields = "__all__"
    client_slug = None
    permission_required = "jobtracker.view_frameworkagreement"
    accept_global_perms = True
    return_403 = True

    def get_success_url(self):
        pk = None
        if "pk" in self.kwargs:
            pk = self.kwargs["pk"]
        if "client_slug" in self.kwargs:
            client_slug = self.kwargs["client_slug"]

        if client_slug and pk:
            return reverse_lazy(
                "client_framework_detail", kwargs={"client_slug": client_slug, "pk": pk}
            )
        elif client_slug:
            return reverse_lazy("client_detail", kwargs={"slug": client_slug})
        else:
            return reverse_lazy("client_list")

    def get_context_data(self, **kwargs):
        context = super(ClientFrameworkBaseView, self).get_context_data(**kwargs)
        if "client_slug" in self.kwargs:
            context["client"] = get_object_or_404(
                Client, slug=self.kwargs["client_slug"]
            )
        return context


class ClientFrameworkListView(
    ClientFrameworkBaseView, PermissionRequiredMixin, ListView
):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""


def _calc_days(slots, hours_in_day, filter_fn=None):
    """Calculate days from a list of timeslots, optionally filtered.
    Uses _cached_hours if available (pre-computed once per slot)."""
    total = Decimal()
    for s in slots:
        if filter_fn is None or filter_fn(s):
            total += getattr(s, '_cached_hours', s.get_business_hours())
    return round(total / hours_in_day, 1) if hours_in_day else 0


class ClientFrameworkDetailView(
    ClientFrameworkBaseView, PermissionRequiredMixin, DetailView
):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fw = self.object
        now = timezone.now()
        hours_in_day = fw.get_hours_in_day()

        all_slots = list(
            TimeSlot.objects.filter(
                phase__job__associated_framework=fw
            ).select_related('user', 'phase', 'phase__job', 'phase__service')
            .prefetch_related('user__unit_memberships__unit')
        )

        # Pre-compute business hours once per slot to avoid repeated calculation
        for slot in all_slots:
            slot._cached_hours = slot.get_business_hours()

        # Pre-compute summary stats so the template doesn't call model methods
        # (which would each re-query the database independently)
        fw.computed_days_used = _calc_days(all_slots, hours_in_day, lambda s: s.end < now)
        fw.computed_days_scheduled = _calc_days(all_slots, hours_in_day, lambda s: s.start >= now)
        fw.computed_days_available = fw.total_days - fw.computed_days_used - fw.computed_days_scheduled
        fw.computed_is_over_allocated = (fw.computed_days_used + fw.computed_days_scheduled) > fw.total_days

        context["TimeSlotDeliveryRoles"] = TimeSlotDeliveryRole.CHOICES

        # Per-job data with phase breakdown
        jobs_data = []
        for job in fw.associated_jobs.all().prefetch_related('phases'):
            job_slots = [s for s in all_slots if s.phase.job_id == job.pk]
            job_entry = {
                'job': job,
                'used_days': _calc_days(job_slots, hours_in_day, lambda s: s.end < now),
                'scheduled_days': _calc_days(job_slots, hours_in_day, lambda s: s.start >= now),
                'total_days': _calc_days(job_slots, hours_in_day),
                'phases': [],
            }
            for phase in job.phases.all():
                phase_slots = [s for s in job_slots if s.phase_id == phase.pk]
                if phase_slots:
                    job_entry['phases'].append({
                        'phase': phase,
                        'used_days': _calc_days(phase_slots, hours_in_day, lambda s: s.end < now),
                        'scheduled_days': _calc_days(phase_slots, hours_in_day, lambda s: s.start >= now),
                        'total_days': _calc_days(phase_slots, hours_in_day),
                    })
            jobs_data.append(job_entry)
        context['jobs_data'] = jobs_data

        # Per-user breakdown
        users_data = []
        users_by_id = {}
        for s in all_slots:
            if s.user_id not in users_by_id:
                users_by_id[s.user_id] = {'user': s.user, 'slots': []}
            users_by_id[s.user_id]['slots'].append(s)
        for data in users_by_id.values():
            users_data.append({
                'user': data['user'],
                'used_days': _calc_days(data['slots'], hours_in_day, lambda s: s.end < now),
                'scheduled_days': _calc_days(data['slots'], hours_in_day, lambda s: s.start >= now),
                'total_days': _calc_days(data['slots'], hours_in_day),
            })
        users_data.sort(key=lambda x: x['total_days'], reverse=True)
        context['users_data'] = users_data

        # Per-delivery-role breakdown
        roles_data = []
        for role_val, role_name in TimeSlotDeliveryRole.CHOICES:
            if role_val == 0:
                continue
            role_slots = [s for s in all_slots if s.deliveryRole == role_val]
            if role_slots:
                roles_data.append({
                    'role_name': role_name,
                    'used_days': _calc_days(role_slots, hours_in_day, lambda s: s.end < now),
                    'scheduled_days': _calc_days(role_slots, hours_in_day, lambda s: s.start >= now),
                    'total_days': _calc_days(role_slots, hours_in_day),
                })
        context['roles_data'] = roles_data

        # Totals for the roles breakdown footer
        context['roles_total_used'] = _calc_days(all_slots, hours_in_day, lambda s: s.end < now)
        context['roles_total_scheduled'] = _calc_days(all_slots, hours_in_day, lambda s: s.start >= now)
        context['roles_total'] = _calc_days(all_slots, hours_in_day)

        # Per-service breakdown
        services_by_id = {}
        for s in all_slots:
            svc = s.phase.service
            if svc is None:
                continue
            if svc.pk not in services_by_id:
                services_by_id[svc.pk] = {'service': svc, 'slots': []}
            services_by_id[svc.pk]['slots'].append(s)
        services_data = []
        for data in services_by_id.values():
            services_data.append({
                'service': data['service'],
                'used_days': _calc_days(data['slots'], hours_in_day, lambda s: s.end < now),
                'scheduled_days': _calc_days(data['slots'], hours_in_day, lambda s: s.start >= now),
                'total_days': _calc_days(data['slots'], hours_in_day),
            })
        services_data.sort(key=lambda x: x['total_days'], reverse=True)
        context['services_data'] = services_data

        # Monthly burn-down data (days consumed per month)
        monthly = {}
        for s in all_slots:
            if s.end >= now:
                continue
            month_key = s.start.strftime('%Y-%m')
            if month_key not in monthly:
                monthly[month_key] = []
            monthly[month_key].append(s)
        monthly_data = []
        for month_key in sorted(monthly.keys()):
            monthly_data.append({
                'month': month_key,
                'days': _calc_days(monthly[month_key], hours_in_day),
            })
        context['monthly_data'] = monthly_data

        # Running cumulative for burn-down
        cumulative = Decimal()
        for entry in monthly_data:
            cumulative += entry['days']
            entry['cumulative'] = cumulative

        # Avg stats
        job_count = len(jobs_data)
        phase_count = sum(len(j['phases']) for j in jobs_data)
        total_days = context['roles_total']
        context['avg_days_per_job'] = round(total_days / job_count, 1) if job_count else 0
        context['avg_days_per_phase'] = round(total_days / phase_count, 1) if phase_count else 0
        context['job_count'] = job_count
        context['phase_count'] = phase_count

        return context


class ClientFrameworkCreateView(
    ClientFrameworkBaseView, PermissionRequiredMixin, CreateView
):
    form_class = ClientFrameworkForm
    fields = None

    permission_required = "jobtracker.add_frameworkagreement"
    accept_global_perms = True
    permission_object = FrameworkAgreement
    return_403 = True

    def form_valid(self, form):
        form.instance.client = Client.objects.get(slug=self.kwargs["client_slug"])
        form.instance.save()
        log_system_activity(form.instance, "Created")
        return super(ClientFrameworkCreateView, self).form_valid(form)

    def get_form_kwargs(self):
        kwargs = super(ClientFrameworkCreateView, self).get_form_kwargs()
        if "client_slug" in self.kwargs:
            kwargs["client"] = get_object_or_404(
                Client, slug=self.kwargs["client_slug"]
            )
        return kwargs


class ClientFrameworkUpdateView(
    ClientFrameworkBaseView, PermissionRequiredMixin, UpdateView
):
    form_class = ClientFrameworkForm
    fields = None

    permission_required = "jobtracker.change_frameworkagreement"
    accept_global_perms = True
    return_403 = True


class ClientFrameworkDeleteView(
    ClientFrameworkBaseView, PermissionRequiredMixin, DeleteView
):

    permission_required = "jobtracker.delete_frameworkagreement"
    accept_global_perms = True
    return_403 = True

    def get_success_url(self):
        if "client_slug" in self.kwargs:
            client_slug = self.kwargs["client_slug"]

        if client_slug:
            return reverse_lazy("client_detail", kwargs={"slug": client_slug})
        else:
            return reverse_lazy("client_list")
