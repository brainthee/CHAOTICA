from django_cron import CronJobBase, Schedule
from django.core import management
from django.conf import settings
from .models import ManualBackupJob
from django.core.management import call_command
from django.utils import timezone
import tempfile
import os
import logging


logger = logging.getLogger(__name__)


class ProcessManualBackupJobs(CronJobBase):
    RUN_EVERY_MINS = 1  # Run every minute
    MIN_NUM_FAILURES = 3  # Retry failed jobs up to 3 times
    
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'chaotica_utils.process_manual_backup_jobs'
    
    def do(self):
        # Process pending media backup jobs
        pending_jobs = ManualBackupJob.objects.filter(status='pending')
        
        for job in pending_jobs[:1]:  # Process one at a time to avoid overload
            self.process_job(job)
    
    def process_job(self, job):
        """Process a single backup job"""
        logger.info(f"Processing backup job {job.id} for user {job.user}")
        
        # Mark as running
        job.status = 'running'
        job.started_at = timezone.now()
        job.save()
        
        try:
            if job.backup_type == 'media':
                self.create_media_backup(job)
            else:  # database
                self.create_database_backup(job)
            
            # Mark as complete
            job.status = 'complete'
            job.completed_at = timezone.now()
            job.save()
            
            logger.info(f"Backup job {job.id} completed successfully")
            
        except Exception as e:
            # Mark as failed
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = timezone.now()
            job.save()
            
            logger.error(f"Backup job {job.id} failed: {str(e)}")
    
    def create_media_backup(self, job):
        """Create media backup"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tar.gz') as tmp_file:
            temp_path = tmp_file.name
        
        try:
            call_command('mediabackup', '-z', '-O', temp_path)
            
            # Store file info
            job.file_path = temp_path
            job.file_size = os.path.getsize(temp_path)
            job.save()
            
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise
    
    def create_database_backup(self, job):
        """Create database backup"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.gz') as tmp_file:
            temp_path = tmp_file.name
        
        try:
            call_command('dbbackup', '-z', '-O', temp_path)
            
            # Store file info
            job.file_path = temp_path
            job.file_size = os.path.getsize(temp_path)
            job.save()
            
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise


# cron.py (add this as another cron job)
class CleanupOldBackups(CronJobBase):
    RUN_EVERY_MINS = 60  # Run every hour
    
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'chaotica_utils.cleanup_old_manual_backups'
    
    def do(self):
        # Delete backup files older than 2 hours
        cutoff_time = timezone.now() - timezone.timedelta(hours=2)
        
        old_jobs = ManualBackupJob.objects.filter(
            status='complete',
            completed_at__lt=cutoff_time
        )
        
        for job in old_jobs:
            if job.file_path and os.path.exists(job.file_path):
                try:
                    os.remove(job.file_path)
                    logger.info(f"Deleted old backup file: {job.file_path}")
                except Exception as e:
                    logger.error(f"Error deleting backup file {job.file_path}: {e}")
            
            job.delete()
        
        # Also clean up failed jobs older than 24 hours
        old_failed = ManualBackupJob.objects.filter(
            status='failed',
            completed_at__lt=timezone.now() - timezone.timedelta(hours=24)
        )
        old_failed.delete()


class task_backup_site(CronJobBase):
    # We want high resiliance so frequent backups!
    RUN_AT_TIMES = [
        '6:00', 
        '8:00', 
        '9:00', 
        '10:00', 
        '11:00', 
        '12:00', 
        '13:00', 
        '14:00', 
        '15:00', 
        '16:00', 
        '17:00', 
        '18:00', 
        '19:00', 
        '21:00', 
        '00:00' # 'just cause!
    ]
    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    code = 'chaotica_utils.task_backup_site'

    def do(self):
        if settings.DBBACKUP_ENABLED == "1" or settings.DBBACKUP_ENABLED:
            management.call_command('dbbackup', '-c')


class task_clean_historical_records(CronJobBase):
    RUN_AT_TIMES = [
        '6:00', 
    ]
    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    code = 'chaotica_utils.task_backup_site'

    def do(self):
        management.call_command('clean_duplicate_history', '--auto')
        management.call_command('clean_old_history', '--auto')


class task_update_phase_dates(CronJobBase):
    RUN_AT_TIMES = ['3:30',]
    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    code = 'chaotica_utils.task_update_phase_dates'

    def do(self):
        from jobtracker.models import Phase

        for phase in Phase.objects.all():
            phase.update_stored_dates()


class task_sync_global_permissions(CronJobBase):
    RUN_AT_TIMES = ['07:30',]
    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    code = 'chaotica_utils.task_sync_global_permissions'

    def do(self):
        from .models import Group

        for group in Group.objects.all():
            group.sync_global_permissions()


class task_sync_role_permissions_to_default(CronJobBase):
    RUN_AT_TIMES = ['07:30',]
    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    code = 'chaotica_utils.task_sync_role_permissions_to_default'

    def do(self):
        from jobtracker.models import OrganisationalUnitRole, OrganisationalUnit

        for unit in OrganisationalUnitRole.objects.all():
            unit.sync_default_permissions()
        # Now lets clean up the units
        for unit in OrganisationalUnit.objects.all():
            unit.sync_permissions()


class task_sync_role_permissions(CronJobBase):
    RUN_AT_TIMES = ['07:30',]
    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    code = 'chaotica_utils.task_sync_role_permissions'

    def do(self):
        from jobtracker.models import OrganisationalUnit

        for unit in OrganisationalUnit.objects.all():
            unit.sync_permissions()