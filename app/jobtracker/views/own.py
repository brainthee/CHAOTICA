from guardian.mixins import PermissionRequiredMixin
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import ChaoticaBaseView
from ..models import QualificationRecord
from ..forms import OwnQualificationRecordForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
import logging
from django.template import loader
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods


logger = logging.getLogger(__name__)


class OwnQualificationRecordBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = QualificationRecord
    fields = "__all__"
    permission_required = "jobtracker.view_qualification"
    accept_global_perms = True
    return_403 = True


class OwnQualificationRecordListView(OwnQualificationRecordBaseView, ListView):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""

    def get_queryset(self):
        queryset = QualificationRecord.objects.filter(user=self.request.user)
        return queryset


# class OwnQualificationRecordDetailView(OwnQualificationRecordBaseView, PermissionRequiredMixin, DetailView):
#     """View to list the details from one job.
#     Use the 'job' variable in the template to access
#     the specific job here and in the Views below"""

#     permission_required = 'jobtracker.view_qualification'
#     accept_global_perms = True
#     return_403 = True


class OwnQualificationRecordCreateView(
    OwnQualificationRecordBaseView, PermissionRequiredMixin, CreateView
):
    form_class = OwnQualificationRecordForm
    fields = None
    permission_required = "jobtracker.add_qualification"
    accept_global_perms = True
    permission_object = QualificationRecord
    return_403 = True


@login_required
@require_http_methods(["POST", "GET"])
def add_own_qualification(request):
    data = dict()
    if request.method == "POST":
        form = OwnQualificationRecordForm(
            request.POST,
        )
        if form.is_valid():
            record = form.save(commit=False)
            record.user = request.user
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
        form = OwnQualificationRecordForm(request.POST, instance=record)
        if form.is_valid():
            updated_record = form.save(commit=False)
            updated_record.user = request.user
            # Check if the awarded_date has changed
            if (
                "awarded_date" in form.changed_data
                and updated_record.qualification.validity_period
            ):
                updated_record.lapse_date = (
                    updated_record.awarded_date
                    + updated_record.qualification.validity_period
                )

            updated_record.save()
            data["form_is_valid"] = True
    else:
        form = OwnQualificationRecordForm(instance=record)

    context = {"form": form}
    data["html_form"] = loader.render_to_string(
        "jobtracker/modals/qualificationrecord_form.html", context, request=request
    )
    return JsonResponse(data)
