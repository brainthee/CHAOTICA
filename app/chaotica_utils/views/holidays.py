from guardian.mixins import PermissionRequiredMixin
from guardian.decorators import permission_required_or_403
from django.views.generic.list import ListView
from django.template import loader
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import log_system_activity, ChaoticaBaseView
from ..models import Holiday
from ..forms.common import HolidayForm, HolidayImportLibForm
import logging
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import (
    require_safe,
)
from django.http import (
    HttpResponse,
    JsonResponse,
)
import holidays
from django.utils import timezone
from django.contrib import messages

logger = logging.getLogger(__name__)
from django.shortcuts import get_object_or_404


class HolidayBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = Holiday
    fields = "__all__"
    permission_required = "chaotica_utils.view_holiday"
    accept_global_perms = True
    return_403 = True

    def get_context_data(self, **kwargs):
        context = super(HolidayBaseView, self).get_context_data(**kwargs)
        return context

    def get_success_url(self):
        if "pk" in self.kwargs:
            pk = self.kwargs["pk"]
            return reverse_lazy("holiday_detail", kwargs={"pk": pk})
        else:
            return reverse_lazy("holiday_list")


class HolidayListView(HolidayBaseView, ListView):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""


class HolidayDetailView(HolidayBaseView, PermissionRequiredMixin, DetailView):
    """View to list the details from one job.
    Use the 'job' variable in the template to access
    the specific job here and in the Views below"""

    permission_required = "chaotica_utils.view_holiday"
    accept_global_perms = True
    return_403 = True


@permission_required_or_403("chaotica_utils.add_holiday")
def holiday_create(request):
    data = dict()
    if request.method == "POST":
        form = HolidayForm(request.POST)
        if form.is_valid():
            holiday = form.save()
            log_system_activity(
                holiday,
                "{user} added {holiday}.".format(
                    user=request.user,
                    holiday=holiday,
                ),
                author=request.user,
            )
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
            data["form_errors"] = form.errors
    else:
        # Send the modal
        form = HolidayForm()

    context = {"holiday_form": form}
    data["html_form"] = loader.render_to_string(
        "modals/holiday_form.html", context, request=request
    )
    return JsonResponse(data)


@permission_required_or_403("chaotica_utils.change_holiday")
def holiday_edit(request, pk):
    holiday = get_object_or_404(Holiday, pk=pk)
    data = dict()
    if request.method == "POST":
        form = HolidayForm(request.POST, instance=holiday)
        if form.is_valid():
            holiday = form.save()
            log_system_activity(
                holiday,
                "{user} changed {holiday}.".format(
                    user=request.user,
                    holiday=holiday,
                ),
                author=request.user,
            )
            data["form_is_valid"] = True
        else:
            data["form_is_valid"] = False
            data["form_errors"] = form.errors
    else:
        # Send the modal
        form = HolidayForm(instance=holiday)

    context = {"holiday_form": form, "holiday": holiday}
    data["html_form"] = loader.render_to_string(
        "modals/holiday_form.html", context, request=request
    )
    return JsonResponse(data)


@permission_required_or_403("chaotica_utils.delete_holiday")
def holiday_delete(request, pk):
    holiday = get_object_or_404(Holiday, pk=pk)
    data = dict()
    if request.method == "POST":
        holiday.delete()
        data["form_is_valid"] = True

    context = {"holiday": holiday}
    data["html_form"] = loader.render_to_string(
        "modals/holiday_delete.html", context, request=request
    )
    return JsonResponse(data)


@permission_required_or_403("chaotica_utils.add_holiday")
def holiday_import_lib(request):
    data = dict()
    now = timezone.now().today()
    years = [now.year, now.year + 1]
    if request.method == "POST":
        form = HolidayImportLibForm(request.POST)
        try:
            holidays_created = 0
            holidays_processed = 0
            if form.is_valid():
                holiday_days = holidays.CountryHoliday(form.cleaned_data["country"])
                for subdiv in holiday_days.subdivisions:
                    dates = holidays.CountryHoliday(
                        country=form.cleaned_data["country"], subdiv=subdiv, years=years
                    )
                    for hol, desc in dates.items():
                        db_date, db_holiday_created = Holiday.objects.get_or_create(
                            date=hol,
                            country=form.cleaned_data["country"],
                            reason=desc,
                        )
                        if db_holiday_created:
                            holidays_created += 1
                        holidays_processed += 1
                        if subdiv not in db_date.subdivs:
                            db_date.subdivs.append(subdiv)
                            db_date.save()
                data["form_is_valid"] = True
        except Exception as ex:
            data["form_is_valid"] = True
            messages.warning(request, "Error: {}".format(str(ex)))
        else:
            data["form_is_valid"] = False
            data["form_errors"] = form.errors
    else:
        # Send the modal
        form = HolidayImportLibForm()

    context = {"form": form}
    data["html_form"] = loader.render_to_string(
        "modals/holiday_import_lib.html", context, request=request
    )
    return JsonResponse(data)


class HolidayCreateView(HolidayBaseView, PermissionRequiredMixin, CreateView):
    form_class = HolidayForm
    fields = None
    permission_required = "chaotica_utils.add_holiday"
    accept_global_perms = True
    permission_object = Holiday
    return_403 = True

    def get_context_data(self, **kwargs):
        context = super(HolidayCreateView, self).get_context_data(**kwargs)
        return context

    def form_valid(self, form):
        return super(HolidayCreateView, self).form_valid(form)


class HolidayUpdateView(HolidayBaseView, PermissionRequiredMixin, UpdateView):
    form_class = HolidayForm
    fields = None

    permission_required = "chaotica_utils.change_holiday"
    accept_global_perms = True
    return_403 = True


class HolidayDeleteView(HolidayBaseView, PermissionRequiredMixin, DeleteView):
    """View to delete a job"""

    permission_required = "chaotica_utils.delete_holiday"
    accept_global_perms = True
    return_403 = True
