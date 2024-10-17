from django_cron import CronJobBase, Schedule
from django.conf import settings
from constance import config
from django.utils import timezone
from chaotica_utils.models import User
from .models import RMSyncRecord, RMAssignable, RMAssignableSlot, RMTaskLock


class task_sync_rm_schedule(CronJobBase):
    RUN_EVERY_MINS = 5
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = "rm_sync.task_sync_rm_schedule"

    def do(self):
        # Check if we're enabled first...
        if not config.RM_SYNC_ENABLED:
            # RM Sync is disabled. Don't run
            return "Task disabled due to site setting"
        
        if RMTaskLock.objects.filter(task_id=task_sync_rm_schedule.code).exists():
            # Check if the lock is stale...
            lock = RMTaskLock.objects.get(task_id=task_sync_rm_schedule.code)
            if lock.is_stale():
                # Lets reset all the locks
                RMSyncRecord.objects.filter(sync_in_progress=True).update(sync_in_progress=False)
                lock.delete()
            else:
                # Task already in flight. Ignore this run
                return "Task ignored - concurrent task running"
        
        task_lock = RMTaskLock.objects.create(task_id=task_sync_rm_schedule.code)

        try:
            for sync_record in RMSyncRecord.objects.filter(sync_enabled=True):
                sync_record.sync_records()
                task_lock.last_updated = timezone.now()
        finally:
            task_lock.delete()
        
        return "Task successfully run"
