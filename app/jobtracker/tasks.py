from datetime import date
from django_cron import CronJobBase, Schedule
from django.db.models import Q
from .enums import PhaseStatuses
from .models.phase import Phase


class task_progress_workflows(CronJobBase):
    RUN_EVERY_MINS = 1 # every 1st of the month
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'jobtracker.task_progress_workflows'

    def do(self):
        # Lets work through the different times we want to auto-progress!

        ## Move to checks if scheduling confirmed and < 5 days to start...
        for phase in Phase.objects.filter(status=PhaseStatuses.SCHEDULED_CONFIRMED):
            if phase.start_date:
                days_to_start = phase.start_date - date.today()
                if days_to_start.days < 7:
                    # Ok, we're in the time range... lets try and move!
                    if phase.can_to_pre_checks():
                        phase.to_pre_checks()
                        phase.save()

        # Lets see if we can auto-start any phases!
        for phase in Phase.objects.filter(status=PhaseStatuses.READY_TO_BEGIN):
            if phase.start_date and date.today() >= phase.start_date:
                # Ok, today is the day!
                if phase.can_to_in_progress():
                    phase.to_in_progress()
                    phase.save()

        # Lets see if we can archive any?
        for phase in Phase.objects.filter(
            Q(status=PhaseStatuses.DELIVERED) | Q(status=PhaseStatuses.CANCELLED)
        ):
            if phase.can_to_archived():
                phase.to_archived()
                phase.save()


class task_fire_job_notifications(CronJobBase):
    RUN_EVERY_MINS = 5 # every 1st of the month
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'jobtracker.task_fire_job_notifications'

    def do(self):
        # We want to fire notifications for these scenarios:
        # - Report late to TQA
        # - Report late to PQA
        # - Report late to Delivery
        # - Precons Due

        ## Report late to TQA
        for phase in Phase.objects.filter(
            Q(status=PhaseStatuses.IN_PROGRESS) | Q(status=PhaseStatuses.PENDING_TQA)
        ):
            if phase.is_tqa_late:
                # Ok, it's late. Lets fire a notification!
                phase.fire_late_to_tqa_notification()

        ## Report late to PQA
        for phase in Phase.objects.filter(
            Q(status=PhaseStatuses.PENDING_PQA)
            | Q(status=PhaseStatuses.QA_TECH)
            | Q(status=PhaseStatuses.QA_TECH_AUTHOR_UPDATES)
        ):
            if phase.is_pqa_late:
                # Ok, it's late. Lets fire a notification!
                phase.fire_late_to_pqa_notification()

        ## Report late to PQA
        for phase in Phase.objects.filter(
            Q(status=PhaseStatuses.PENDING_PQA)
            | Q(status=PhaseStatuses.QA_PRES)
            | Q(status=PhaseStatuses.QA_PRES_AUTHOR_UPDATES)
            | Q(status=PhaseStatuses.COMPLETED)
        ):
            if phase.is_delivery_late:
                # Ok, it's late. Lets fire a notification!
                phase.fire_late_to_delivery_notification()
