from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.template import loader
from chaotica_utils.views import page_defaults
import logging
from django.contrib.auth.decorators import login_required
import uuid
from django.contrib import messages

logger = logging.getLogger(__name__)


@login_required
def reset_cal_feed(request):
    # Okay, lets go!
    data = dict()
    if request.method == "POST":
        data["form_is_valid"] = False
        # We need to check which button was pressed... accept or reject!
        if request.POST.get("user_action") == "approve_action":
            # Approve it!
            request.user.schedule_feed_id = uuid.uuid4()
            request.user.save()
            data["form_is_valid"] = True
            data["next"] = reverse("view_own_profile")

    context = {}
    data["html_form"] = loader.render_to_string(
        "modals/feed_reset.html", context, request=request
    )
    return JsonResponse(data)


@login_required
def reset_cal_family_feed(request):
    # Okay, lets go!
    data = dict()
    if request.method == "POST":
        data["form_is_valid"] = False
        # We need to check which button was pressed... accept or reject!
        if request.POST.get("user_action") == "approve_action":
            # Approve it!
            request.user.schedule_feed_family_id = uuid.uuid4()
            request.user.save()
            data["form_is_valid"] = True
            data["next"] = reverse("view_own_profile")

    context = {}
    data["html_form"] = loader.render_to_string(
        "modals/feed_family_reset.html", context, request=request
    )
    return JsonResponse(data)


@login_required
def toggle_cal_feed(request):
    if request.method == "POST":
        request.user.schedule_feed_enabled = not request.user.schedule_feed_enabled
        request.user.save(update_fields=["schedule_feed_enabled"])
        if request.user.schedule_feed_enabled:
            messages.success(request, "Calendar feed enabled.")
        else:
            messages.info(request, "Calendar feed disabled.")
    return HttpResponseRedirect(reverse("view_own_profile") + "#feeds")


@login_required
def toggle_cal_family_feed(request):
    if request.method == "POST":
        request.user.schedule_feed_family_enabled = not request.user.schedule_feed_family_enabled
        request.user.save(update_fields=["schedule_feed_family_enabled"])
        if request.user.schedule_feed_family_enabled:
            messages.success(request, "Family calendar feed enabled.")
        else:
            messages.info(request, "Family calendar feed disabled.")
    return HttpResponseRedirect(reverse("view_own_profile") + "#feeds")


@login_required
def view_stats(request):
    context = {}
    template = loader.get_template("stats.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@login_required
def view_reports(request):
    context = {}
    template = loader.get_template("reports.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))
