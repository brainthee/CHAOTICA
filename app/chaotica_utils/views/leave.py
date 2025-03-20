from django.urls import reverse
from django.template import loader
from django.utils import timezone
from django.http import (
    HttpResponseForbidden,
    JsonResponse,
    HttpResponse,
    HttpResponseRedirect,
    HttpResponseBadRequest,
)
from ..forms import LeaveRequestForm
from dateutil.relativedelta import relativedelta
from ..models import LeaveRequest
from .common import page_defaults
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from guardian.shortcuts import get_objects_for_user
from django.shortcuts import get_object_or_404
from django.views.decorators.http import (
    require_http_methods,
    require_safe,
)


@login_required
@require_http_methods(["POST", "GET"])
def view_own_leave(request):
    context = {}
    leave_list = LeaveRequest.objects.filter(user=request.user)
    context = {
        "leave_list": leave_list,
    }
    template = loader.get_template("view_own_leave.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@login_required
@require_http_methods(["POST", "GET"])
def request_own_leave(request):
    if request.method == "POST":
        form = LeaveRequestForm(request.POST, request=request)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.user = request.user
            leave.save()
            leave.send_request_notification()
            return HttpResponseRedirect(reverse("view_own_leave"))
        else:
            # Redisplay form with errors
            form = LeaveRequestForm(request.POST, request=request)
    else:
        form = LeaveRequestForm(request=request)

    context = {"form": form}
    template = loader.get_template("forms/add_leave_form.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@login_required
@require_safe
def manage_leave(request):
    context = {}
    from jobtracker.models import OrganisationalUnit, TimeSlot

    units_with_perm = get_objects_for_user(
        request.user, "can_view_all_leave_requests", OrganisationalUnit
    )

    leave_list = (
        LeaveRequest.objects.filter(
            # Only show this last calendar's year...
            start_date__gte=timezone.now()
            - relativedelta(years=1),
        )
        .filter(
            Q(
                user__unit_memberships__unit__in=units_with_perm
            )  # Show leave requests for users we have permission over
            | Q(user__manager=request.user)  # where we're manager
            | Q(user__acting_manager=request.user)  # where we're acting manager
            | Q(user=request.user)  # and our own of course....
        )
        .prefetch_related("user", "user__unit_memberships", "user__timeslots")
    )
    pending_leave = leave_list.filter(authorised=False, cancelled=False, declined=False)
    leave_list = leave_list.exclude(authorised=False, cancelled=False, declined=False)
    context = {
        "leave_list": leave_list,
        "pending_leave": pending_leave,
    }
    template = loader.get_template("manage_leave.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@login_required
def manage_leave_auth_request(request, pk):
    leave = get_object_or_404(LeaveRequest, pk=pk)
    # First, check we're allowed to process this...
    if not leave.can_user_auth(request.user):
        return HttpResponseForbidden()

    # Okay, lets go!
    data = dict()
    if request.method == "POST":
        # We need to check which button was pressed... accept or reject!
        if request.POST.get("user_action") == "approve_action":
            # Approve it!
            leave.authorise(request.user)
            data["form_is_valid"] = True

        elif request.POST.get("user_action") == "reject_action":
            # Decline!
            leave.decline(request.user)
            data["form_is_valid"] = True
        else:
            # invalid choice...
            return HttpResponseBadRequest()

    context = {
        "leave": leave,
    }
    data["html_form"] = loader.render_to_string(
        "modals/leave_auth.html", context, request=request
    )
    return JsonResponse(data)


@login_required
@require_http_methods(["GET", "POST"])
def cancel_own_leave(request, pk):
    leave = get_object_or_404(LeaveRequest, pk=pk, user=request.user)

    # Okay, lets go!
    data = dict()
    if request.method == "POST":
        # First, check we're allowed to process this...
        if not leave.can_cancel():
            return HttpResponseForbidden()

        # We need to check which button was pressed... accept or reject!
        if request.POST.get("user_action") == "approve_action":
            # Approve it!
            leave.cancel()
            data["form_is_valid"] = True
        else:
            # invalid choice...
            return HttpResponseBadRequest()

    context = {
        "leave": leave,
    }
    data["html_form"] = loader.render_to_string(
        "modals/leave_cancel.html", context, request=request
    )
    return JsonResponse(data)
