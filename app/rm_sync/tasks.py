from django_cron import CronJobBase, Schedule
from django.conf import settings
from constance import config
from django.utils import timezone
from chaotica_utils.models import User
from .models import RMSyncRecord, RMAssignable, RMAssignableSlot, RMTaskLock


class task_sync_rm_schedule(CronJobBase):
    RUN_EVERY_MINS = 2
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = "rm_sync.task_sync_rm_schedule"

    def do(self):
        # Check if we're enabled first...
        if not config.RM_SYNC_ENABLED:
            # RM Sync is disabled. Don't run
            return
        from pprint import pprint
        
        if RMTaskLock.objects.filter(task_id=task_sync_rm_schedule.code).exists():
            # Task already in flight. Ignore this run
            pprint("Lock exists")
            return
        
        task_lock = RMTaskLock.objects.create(task_id=task_sync_rm_schedule.code)

        try:
            for sync_record in RMSyncRecord.objects.filter(sync_enabled=True):
                sync_record.sync_records()
        finally:
            task_lock.delete()
