from chaotica_utils.mixins import SecurePermissionRequiredMixin as PermissionRequiredMixin, ObjectActivityMixin
import csv
from ..selectors.clients import framework_usage
from django.http import (
    JsonResponse,
    HttpResponse,
)
from django.shortcuts import get_object_or_404, redirect
from guardian.shortcuts import get_objects_for_user
from chaotica_utils.decorators import permission_required_or_403
from django.views.decorators.http import (
    require_http_methods,
)
from django.template import loader
from chaotica_utils.views import log_system_activity, ChaoticaBaseView, ProtectedDeleteMixin, SoftDeleteViewMixin
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


class ClientDetailView(ObjectActivityMixin, ClientBaseView, DetailView):
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


class ClientDeleteView(SoftDeleteViewMixin, ClientBaseView, DeleteView):
    """Soft-delete a client (preserves its jobs/history)."""

    permission_required = "jobtracker.delete_client"
    success_url = reverse_lazy("client_list")


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


@permission_required_or_403(
    "jobtracker.view_client", (Client, "slug", "slug"), accept_global_perms=True
)
@require_http_methods(["GET"])
def client_onboarding_export(request, slug):
    client = get_object_or_404(Client, slug=slug)
    onboardings = (
        ClientOnboarding.objects.filter(client=client)
        .select_related("user")
        .order_by("user__last_name", "user__first_name")
    )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        'attachment; filename="{}-onboarding.csv"'.format(client.slug)
    )

    writer = csv.writer(response)
    writer.writerow([
        "Full Name", "Email", "Onboarded Date", "Requirements Completed",
        "Status", "Days Until Renewal"
    ])
    for ob in onboardings:
        renewal_days = ob.days_till_renewal() if hasattr(ob, "days_till_renewal") else ""
        writer.writerow([
            ob.user.get_full_name(),
            ob.user.email,
            ob.onboarded.strftime("%Y-%m-%d") if ob.onboarded else "",
            ob.reqs_completed.strftime("%Y-%m-%d") if ob.reqs_completed else "",
            ob.status(),
            renewal_days,
        ])
    return response


@permission_required_or_403(
    "jobtracker.view_client", (Client, "slug", "slug"), accept_global_perms=True
)
@require_http_methods(["GET", "POST"])
def client_schedule_export(request, slug):
    from ..schedule_export import build_schedule_xlsx
    from datetime import date, timedelta
    client = get_object_or_404(Client, slug=slug)

    if request.method == "POST":
        start_str = request.POST.get("start_date", "")
        end_str = request.POST.get("end_date", "")
        framework_id = request.POST.get("framework", "")

        try:
            start_date = date.fromisoformat(start_str)
            end_date = date.fromisoformat(end_str)
        except ValueError:
            messages.error(request, "Invalid date range.")
            return redirect("client_detail", slug=client.slug)

        qs = TimeSlot.objects.filter(
            phase__job__client=client,
            start__date__gte=start_date,
            end__date__lte=end_date,
        )
        framework_label = "All"
        if framework_id:
            qs = qs.filter(phase__job__associated_framework_id=framework_id)
            fw = client.framework_agreements.filter(pk=framework_id).first()
            if fw:
                framework_label = str(fw)

        filename = "schedule-{}".format(client.slug)
        title = "Schedule — {}".format(client)
        header_rows = [
            ("Client", str(client)),
            ("Date Range", "{} to {}".format(
                start_date.strftime("%d %b %Y"), end_date.strftime("%d %b %Y")
            )),
            ("Framework", framework_label),
        ]
        return build_schedule_xlsx(qs, filename, title=title, header_rows=header_rows)

    frameworks = client.framework_agreements.all()
    default_start = (timezone.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    default_end = (timezone.now() + timedelta(days=90)).strftime("%Y-%m-%d")
    data = {
        "html_form": loader.render_to_string(
            "jobtracker/modals/client_schedule_export.html",
            {"client": client, "frameworks": frameworks,
             "default_start": default_start, "default_end": default_end},
            request=request,
        )
    }
    return JsonResponse(data)


@permission_required_or_403("jobtracker.change_client")
@require_http_methods(["GET", "POST"])
def client_merge(request, slug):
    client = get_object_or_404(Client, slug=slug)
    context = {}
    data = dict()
    if request.method == "POST":
        form = MergeClientForm(request.POST, user=request.user)
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
        form = MergeClientForm(user=request.user)

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

    def get_queryset(self):
        # Records belong to the client in the URL: without this, any pk under
        # any client slug resolved (view, edit and delete alike).
        qs = super().get_queryset()
        if "client_slug" in self.kwargs:
            qs = qs.filter(company__slug=self.kwargs["client_slug"])
        return qs

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
    ProtectedDeleteMixin, ClientContactBaseView, PermissionRequiredMixin, DeleteView
):
    # Base view only grants view_contact; deleting must require delete_contact.
    permission_required = "jobtracker.delete_contact"

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

    def get_queryset(self):
        # Records belong to the client in the URL: without this, any pk under
        # any client slug resolved (view, edit and delete alike).
        qs = super().get_queryset()
        if "client_slug" in self.kwargs:
            qs = qs.filter(client__slug=self.kwargs["client_slug"])
        return qs

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


# The day-summing helper is shared with ``Project.get_stats`` so the behaviour
# stays identical in one place. Kept aliased as ``_calc_days`` for the existing
# call sites below.
from chaotica_utils.utils import slots_to_days as _calc_days


class ClientFrameworkDetailView(
    ClientFrameworkBaseView, PermissionRequiredMixin, DetailView
):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(framework_usage(self.object))
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
    ProtectedDeleteMixin, ClientFrameworkBaseView, PermissionRequiredMixin, DeleteView
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
