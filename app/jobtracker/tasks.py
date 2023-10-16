from datetime import date
from celery import shared_task
from celery.utils.log import get_task_logger
from django.db.models import Q
from .enums import PhaseStatuses
from .models.phase import Phase


logger = get_task_logger("tasks")


@shared_task(track_started=True)
def task_progress_job_workflows():
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
        Q(status=PhaseStatuses.DELIVERED) | Q(status=PhaseStatuses.CANCELLED)):
        if phase.can_to_archived():
            phase.to_archived()
            phase.save()