from .models import *
from datetime import date, timedelta
from celery import shared_task, current_task
from celery import Celery
from celery.result import AsyncResult
from celery.utils.log import get_task_logger
from django.db.models import Q
from django.utils import timezone


logger = get_task_logger("tasks")


@shared_task(track_started=True)
def task_progress_job_workflows():
    # Lets work through the different times we want to auto-progress!

    ## Move to checks if scheduling confirmed and < 5 days to start...
    phasesToChecks = Phase.objects.filter(status=PhaseStatuses.SCHEDULED_CONFIRMED)
    for phase in phasesToChecks:
        if phase.start_date:
            daysToStart = phase.start_date - date.today()
            if daysToStart.days < 7:
                # Ok, we're in the time range... lets try and move!
                if phase.can_to_pre_checks():
                    phase.to_pre_checks()
                    phase.save()
    
    # Lets see if we can auto-start any phases!
    phasesToInprogress = Phase.objects.filter(status=PhaseStatuses.READY_TO_BEGIN)
    for phase in phasesToInprogress:
        if phase.start_date:
            if date.today() >= phase.start_date:
                # Ok, today is the day!
                if phase.can_to_in_progress():
                    phase.to_in_progress()
                    phase.save()
    
    # Lets see if we can archive any?
    phasesToArchive = Phase.objects.filter(
        Q(status=PhaseStatuses.DELIVERED) | Q(status=PhaseStatuses.CANCELLED))
    for phase in phasesToArchive:
        if phase.can_to_archived():
            phase.to_archived()
            phase.save()