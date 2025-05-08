from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
import logging
from django.urls import reverse
from django.views.decorators.http import require_safe
from ..tasks import *
from django.contrib import messages
from notifications.utils import (
    AppNotification, send_notifications
)
from notifications.enums import NotificationTypes
from ..models import User


logger = logging.getLogger(__name__)


@staff_member_required
@require_safe
def admin_task_update_phase_dates(request):
    task_update_phase_dates().do()
    messages.success(request, "Phase dates updated")
    return HttpResponseRedirect(reverse("home"))


@staff_member_required
@require_safe
def admin_task_sync_global_permissions(request):
    task_sync_global_permissions().do()
    messages.success(request, "Global permissions sync'd")
    return HttpResponseRedirect(reverse("home"))


@staff_member_required
@require_safe
def admin_task_sync_role_permissions_to_default(request):
    task_sync_role_permissions_to_default().do()
    messages.success(request, "Role Permissions sync'd to default")
    return HttpResponseRedirect(reverse("home"))


@staff_member_required
@require_safe
def admin_task_sync_role_permissions(request):
    task_sync_role_permissions().do()
    messages.success(request, "Role Permissions sync'd")
    return HttpResponseRedirect(reverse("home"))


@staff_member_required
@require_safe
def admin_trigger_error(request):
    """
    Deliberately causes an error. Used to test error capturing

    Args:
        request (Request): A request object

    Returns:
        Exception: An error :)
    """
    division_by_zero = 1 / 0
    return division_by_zero


@login_required
@require_safe
def admin_send_test_notification(request):
    """
    Sends a test notification

    Args:
        request (Request): A request object

    Returns:
        HttpResponseRedirect: Redirect to the referer
    """
    notification = AppNotification(
        notification_type=NotificationTypes.LEAVE_APPROVED,
        title="Test Notification",
        message="This is a test notification. At ease.",
        email_template="emails/test_email.html",
        link=reverse("home"),
        entity_type=request.user.__class__.__name__,
        entity_id=request.user.pk,
    )
    send_notifications(notification, request.user)
    messages.success(request, "Test Notification Sent")
    return HttpResponseRedirect(request.META.get("HTTP_REFERER"))