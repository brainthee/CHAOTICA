from django.http import HttpResponseRedirect, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
import logging
from django.urls import reverse
from django.views.decorators.http import require_safe, require_http_methods
from ..tasks import *
from ..forms import DatabaseRestoreForm, MediaRestoreForm
from django.contrib import messages
from notifications.utils import (
    AppNotification, send_notifications
)
from notifications.enums import NotificationTypes
from ..models import User
from ..decorators import superuser_required
import tempfile
import os
from django.core.management import call_command
from django.shortcuts import render
import tarfile


logger = logging.getLogger(__name__)


@staff_member_required
@require_safe
def admin_task_update_phase_dates(request):
    task_update_phase_dates().do()
    messages.success(request, "Phase dates updated")
    return HttpResponseRedirect(reverse("home"))


@superuser_required
@require_safe
def download_db_backup(request):
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.sql.gz') as tmp_file:
        temp_path = tmp_file.name
    
    try:
        # Run the backup command
        call_command('dbbackup', '-z', '-O', temp_path)
        
        # Read the file and prepare response
        with open(temp_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/gzip')
            response['Content-Disposition'] = 'attachment; filename="db_backup.sql.gz"'
        
        return response
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_path):
            os.remove(temp_path)


@superuser_required
@require_http_methods(["POST"])
def restore_db_backup(request):    
    if request.method != 'POST':
        return HttpResponseBadRequest("POST request required")
    
    # Check if this is the confirmation step
    is_confirmation_step = request.POST.get('db_confirmed_restore', 'false').lower() == 'true'
    
    # Create form instance
    form = DatabaseRestoreForm(request.POST, request.FILES)
    
    # Validate form
    if not form.is_valid():
        return JsonResponse({
            'status': 'error',
            'errors': form.errors,
            'message': 'Validation failed'
        }, status=400)
    
    backup_file = form.cleaned_data['backup_file']

    # Step 1: Request confirmation
    if not is_confirmation_step:        
        return JsonResponse({
            'status': 'confirmation_required',
            'message': 'Please confirm database restore',
            'details': {
                'filename': backup_file.name,
                'size_mb': f"{backup_file.size / (1024 * 1024):.2f}",
                'warning': 'This will permanently overwrite all current database data.'
            }
        })
    
    # Step 2: Perform restore (after confirmation)
    if not form.cleaned_data.get('confirm'):
        return JsonResponse({
            'status': 'error',
            'message': 'Confirmation required to proceed with restore'
        }, status=400)
    
    # Save uploaded file to temporary location
    with tempfile.NamedTemporaryFile(delete=False, suffix='.gz') as tmp_file:
        for chunk in backup_file.chunks():
            tmp_file.write(chunk)
        temp_path = tmp_file.name
    
    try:        
        # Run the restore command
        call_command('dbrestore', '-z', '-I', temp_path, '--noinput')
        
        return JsonResponse({
            'status': 'success',
            'message': 'Database restored successfully',
            'details': {
                'filename': backup_file.name,
                'size': backup_file.size,
                'restored_by': request.user.username,
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Restore failed: {str(e)}'
        }, status=400)
        
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
            logger.debug(f"Cleaned up temporary file: {temp_path}")


@superuser_required
@require_http_methods(["POST"])
def restore_media_backup(request):    
    if request.method != 'POST':
        return HttpResponseBadRequest("POST request required")
    
    # Check if this is the confirmation step
    is_confirmation_step = request.POST.get('media_confirmed_restore', 'false').lower() == 'true'
    
    # Create form instance
    form = MediaRestoreForm(request.POST, request.FILES)
    
    # Validate form
    if not form.is_valid():
        return JsonResponse({
            'status': 'error',
            'errors': form.errors,
            'message': 'Validation failed'
        }, status=400)
    
    backup_file = form.cleaned_data['backup_file']
    
    # Step 1: Request confirmation
    if not is_confirmation_step:        
        # Try to get file count from the archive
        file_count = None
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tar.gz') as tmp_file:
            for chunk in backup_file.chunks():
                tmp_file.write(chunk)
            temp_path = tmp_file.name
        
        try:
            with tarfile.open(temp_path, 'r:gz') as tar:
                file_count = len(tar.getmembers())
        except:
            pass
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        
        details = {
            'filename': backup_file.name,
            'size_mb': f"{backup_file.size / (1024 * 1024):.2f}",
            'warning': 'This will permanently overwrite all current media files.'
        }
        
        if file_count:
            details['file_count'] = file_count
        
        return JsonResponse({
            'status': 'confirmation_required',
            'message': 'Please confirm media restore',
            'details': details
        })
    
    # Step 2: Perform restore (after confirmation)
    if not form.cleaned_data.get('confirm'):
        return JsonResponse({
            'status': 'error',
            'message': 'Confirmation required to proceed with media restore'
        }, status=400)
    
    # Save uploaded file to temporary location
    with tempfile.NamedTemporaryFile(delete=False, suffix='.tar.gz') as tmp_file:
        for chunk in backup_file.chunks():
            tmp_file.write(chunk)
        temp_path = tmp_file.name
    
    try:        
        # Run the media restore command
        call_command('mediarestore', '-z', '-I', temp_path, '--noinput')
        
        return JsonResponse({
            'status': 'success',
            'message': 'Media files restored successfully',
            'details': {
                'filename': backup_file.name,
                'size': backup_file.size,
                'restored_by': request.user.username,
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Media restore failed: {str(e)}'
        }, status=400)
        
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
            logger.debug(f"Cleaned up temporary file: {temp_path}")



@superuser_required
@require_safe
def download_media_backup(request):
    with tempfile.NamedTemporaryFile(delete=False, suffix='.tar.gz') as tmp_file:
        temp_path = tmp_file.name
    
    try:
        call_command('mediabackup', '-z', '-O', temp_path)
        
        with open(temp_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/gzip')
            response['Content-Disposition'] = 'attachment; filename="media_backup.tar.gz"'
        return response
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


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