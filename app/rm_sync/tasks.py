from django_cron import CronJobBase, Schedule
from django.conf import settings
from constance import config
from django.utils import timezone
from chaotica_utils.models import User
from .models import RMSyncRecord, RMAssignable, RMAssignableSlot, RMTaskLock
import logging
import io
from logging import StreamHandler


class task_sync_rm_schedule(CronJobBase):
    RUN_EVERY_MINS = 5
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = "rm_sync.task_sync_rm_schedule"

    def do(self):
        # Create a string buffer and a handler to capture logs
        log_stream = io.StringIO()
        handler = StreamHandler(log_stream)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        # Get the logger for the rm_sync module
        logger = logging.getLogger('rm_sync')
        logger.addHandler(handler)

        # Check if we're enabled first...
        if not config.RM_SYNC_ENABLED:
            # RM Sync is disabled. Don't run
            logger.info("Task disabled due to site setting")
            return log_stream.getvalue()
        
        if RMTaskLock.objects.filter(task_id=task_sync_rm_schedule.code).exists():
            # Check if the lock is stale...
            lock = RMTaskLock.objects.get(task_id=task_sync_rm_schedule.code)
            if lock.is_stale():
                # Lets reset all the locks
                logger.info("Found stale lock. Resetting all sync_in_progress flags and locks.")
                RMSyncRecord.objects.filter(sync_in_progress=True).update(sync_in_progress=False)
                lock.delete()
            else:
                # Task already in flight. Ignore this run
                logger.info("Task ignored - concurrent task running")
                return log_stream.getvalue()
        
        task_lock = RMTaskLock.objects.create(task_id=task_sync_rm_schedule.code)
        logger.info(f"Created task lock: {task_lock.task_id}")

        try:
            for sync_record in RMSyncRecord.objects.filter(sync_enabled=True):
                sync_record.sync_records()
                task_lock.last_updated = timezone.now()
                task_lock.save(update_fields=['last_updated'])

            logger.info("Task successfully completed")

        except Exception as ex:
            logger.exception("Exception happened in sync_records")
        
        finally:
            if 'task_lock' in locals() and task_lock:
                task_lock.delete()
                logger.info("Task lock released")
            
            # Get the log contents
            log_contents = log_stream.getvalue()
            
        return log_contents