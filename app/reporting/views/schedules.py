from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods, require_POST

from ..models import Report, ScheduledReport
from ..forms import ScheduledReportForm
from ..permissions import can_edit_report


def _get_editable_report(request, uuid):
    report = get_object_or_404(Report, uuid=uuid)
    if not can_edit_report(request.user, report):
        raise PermissionDenied("You don't have permission to schedule this report.")
    return report


@login_required
@require_http_methods(["GET"])
def schedule_list(request, uuid):
    report = _get_editable_report(request, uuid)
    return render(request, 'reporting/schedule_list.html', {
        'report': report,
        'schedules': report.schedules.select_related('run_as_user', 'recipient_group').all(),
    })


@login_required
@require_http_methods(["GET", "POST"])
def schedule_create(request, uuid):
    report = _get_editable_report(request, uuid)
    if request.method == 'POST':
        form = ScheduledReportForm(request.POST, report=report)
        if form.is_valid():
            schedule = form.save(commit=False)
            schedule.report = report
            schedule.save()
            messages.success(request, f"Schedule '{schedule.name}' created.")
            return redirect('reporting:schedule_list', uuid=report.uuid)
    else:
        form = ScheduledReportForm(report=report, initial={'email_subject': report.name})
    return render(request, 'reporting/schedule_form.html', {
        'report': report, 'form': form, 'is_create': True,
    })


@login_required
@require_http_methods(["GET", "POST"])
def schedule_edit(request, uuid, pk):
    report = _get_editable_report(request, uuid)
    schedule = get_object_or_404(ScheduledReport, pk=pk, report=report)
    if request.method == 'POST':
        form = ScheduledReportForm(request.POST, instance=schedule, report=report)
        if form.is_valid():
            form.save()
            messages.success(request, f"Schedule '{schedule.name}' updated.")
            return redirect('reporting:schedule_list', uuid=report.uuid)
    else:
        form = ScheduledReportForm(instance=schedule, report=report)
    return render(request, 'reporting/schedule_form.html', {
        'report': report, 'form': form, 'schedule': schedule, 'is_create': False,
    })


@login_required
@require_POST
def schedule_delete(request, uuid, pk):
    report = _get_editable_report(request, uuid)
    schedule = get_object_or_404(ScheduledReport, pk=pk, report=report)
    name = schedule.name
    schedule.delete()
    messages.success(request, f"Schedule '{name}' deleted.")
    return redirect('reporting:schedule_list', uuid=report.uuid)
