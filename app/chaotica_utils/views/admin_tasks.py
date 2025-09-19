from django.http import HttpResponseRedirect, HttpResponse, HttpResponseBadRequest, JsonResponse, FileResponse
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
import logging
from django.urls import reverse
from django.views.decorators.http import require_safe, require_http_methods
from ..tasks import *
from ..forms.common import DatabaseRestoreForm, MediaRestoreForm
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
    """
    Handle database backup creation and download.
    Creates a job on first request, checks status on subsequent requests.
    """
    
    # Get job ID from session
    job_id = request.session.get('db_backup_job_id')
    
    # Check if we should start a new backup
    start_new = request.GET.get('new', 'false').lower() == 'true'
    
    if start_new:
        # Explicitly requested new backup - create it
        job = ManualBackupJob.objects.create(
            user=request.user,
            backup_type='db',
            status='pending'
        )
        request.session['db_backup_job_id'] = str(job.id)
        
        logger.info(f"User {request.user} created database backup job {job.id}")
        
        return JsonResponse({
            'status': 'queued',
            'job_id': str(job.id),
            'message': 'Database backup job queued. It will be processed within the next minute.',
            'position': ManualBackupJob.objects.filter(
                status='pending',
                created_at__lt=job.created_at
            ).count() + 1
        })
    
    # Just checking status - don't create new job
    if not job_id:
        return JsonResponse({
            'status': 'no_job',
            'message': 'No backup job in progress.'
        })
    
    # Check existing job status
    try:
        job = ManualBackupJob.objects.get(id=job_id)
    except ManualBackupJob.DoesNotExist:
        del request.session['db_backup_job_id']
        return JsonResponse({
            'status': 'not_found',
            'message': 'No backup job found. Start a new backup?'
        })
    
    if job.status == 'pending':
        # Still in queue
        position = ManualBackupJob.objects.filter(
            status='pending',
            created_at__lt=job.created_at
        ).count() + 1
        
        return JsonResponse({
            'status': 'pending',
            'job_id': str(job.id),
            'message': f'Backup job is in queue (position {position})',
            'position': position
        })
    
    elif job.status == 'running':
        # Currently being processed
        duration = (timezone.now() - job.started_at).seconds if job.started_at else 0
        
        return JsonResponse({
            'status': 'running',
            'job_id': str(job.id),
            'message': f'Creating database backup... ({duration} seconds)',
            'duration': duration
        })
    
    elif job.status == 'complete':
        # Check if file still exists
        if not os.path.exists(job.file_path):
            # File was deleted, mark job and offer new backup
            job.delete()
            del request.session['db_backup_job_id']
            return JsonResponse({
                'status': 'expired',
                'message': 'Backup file expired. Please create a new backup.'
            })
        
        # Download the file
        if request.GET.get('download', 'false').lower() == 'true':
            try:
                # Clean up session
                del request.session['db_backup_job_id']
                
                # Serve the file
                response = FileResponse(
                    open(job.file_path, 'rb'),
                    content_type=job.get_content_type()
                )
                response['Content-Disposition'] = f'attachment; filename="{job.get_filename()}"'
                
                return response
                
            except Exception as e:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Error downloading file: {str(e)}'
                })
        
        # Return ready status
        file_size_mb = job.file_size / (1024 * 1024) if job.file_size else 0
        time_taken = (job.completed_at - job.started_at).seconds if job.completed_at and job.started_at else 0
        
        return JsonResponse({
            'status': 'ready',
            'job_id': str(job.id),
            'file_size_mb': f'{file_size_mb:.2f}',
            'time_taken': time_taken,
            'message': 'Database backup ready for download'
        })
    
    elif job.status == 'failed':
        # Clean up session
        del request.session['db_backup_job_id']
        
        return JsonResponse({
            'status': 'failed',
            'error': job.error_message,
            'message': 'Database backup creation failed'
        })
    
    return JsonResponse({
        'status': 'unknown',
        'message': 'Unknown job status'
    })


@superuser_required
@require_safe
def download_media_backup(request):
    """
    Handle media backup creation and download.
    Creates a job on first request, checks status on subsequent requests.
    """
    
    # Get job ID from session
    job_id = request.session.get('media_backup_job_id')
    
    # Check if we should start a new backup
    start_new = request.GET.get('new', 'false').lower() == 'true'
    
    if start_new:
        # Explicitly requested new backup - create it
        job = ManualBackupJob.objects.create(
            user=request.user,
            backup_type='media',
            status='pending'
        )
        request.session['media_backup_job_id'] = str(job.id)
        
        logger.info(f"User {request.user} created media backup job {job.id}")
        
        return JsonResponse({
            'status': 'queued',
            'job_id': str(job.id),
            'message': 'Media backup job queued. It will be processed within the next minute.',
            'position': ManualBackupJob.objects.filter(
                status='pending',
                created_at__lt=job.created_at
            ).count() + 1
        })
    
    # Just checking status - don't create new job
    if not job_id:
        return JsonResponse({
            'status': 'no_job',
            'message': 'No backup job in progress.'
        })
    
    # Check existing job status
    try:
        job = ManualBackupJob.objects.get(id=job_id)
    except ManualBackupJob.DoesNotExist:
        del request.session['media_backup_job_id']
        return JsonResponse({
            'status': 'not_found',
            'message': 'No backup job found. Start a new backup?'
        })
    
    if job.status == 'pending':
        # Still in queue
        position = ManualBackupJob.objects.filter(
            status='pending',
            created_at__lt=job.created_at
        ).count() + 1
        
        return JsonResponse({
            'status': 'pending',
            'job_id': str(job.id),
            'message': f'Backup job is in queue (position {position})',
            'position': position
        })
    
    elif job.status == 'running':
        # Currently being processed
        duration = (timezone.now() - job.started_at).seconds if job.started_at else 0
        
        return JsonResponse({
            'status': 'running',
            'job_id': str(job.id),
            'message': f'Creating backup... ({duration} seconds)',
            'duration': duration
        })
    
    elif job.status == 'complete':
        # Check if file still exists
        if not os.path.exists(job.file_path):
            # File was deleted, mark job and offer new backup
            job.delete()
            del request.session['media_backup_job_id']
            return JsonResponse({
                'status': 'expired',
                'message': 'Backup file expired. Please create a new backup.'
            })
        
        # Download the file
        if request.GET.get('download', 'false').lower() == 'true':
            try:
                # Clean up session
                del request.session['media_backup_job_id']
                
                # Serve the file
                response = FileResponse(
                    open(job.file_path, 'rb'),
                    content_type='application/gzip'
                )
                response['Content-Disposition'] = 'attachment; filename="media_backup.tar.gz"'
                
                # Schedule cleanup (we'll clean up old jobs in another cron job)
                
                return response
                
            except Exception as e:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Error downloading file: {str(e)}'
                })
        
        # Return ready status
        file_size_mb = job.file_size / (1024 * 1024) if job.file_size else 0
        time_taken = (job.completed_at - job.started_at).seconds if job.completed_at and job.started_at else 0
        
        return JsonResponse({
            'status': 'ready',
            'job_id': str(job.id),
            'file_size_mb': f'{file_size_mb:.2f}',
            'time_taken': time_taken,
            'message': 'Media backup ready for download'
        })
    
    elif job.status == 'failed':
        # Clean up session
        del request.session['media_backup_job_id']
        
        return JsonResponse({
            'status': 'failed',
            'error': job.error_message,
            'message': 'Media backup creation failed'
        })
    
    return JsonResponse({
        'status': 'unknown',
        'message': 'Unknown job status'
    })



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