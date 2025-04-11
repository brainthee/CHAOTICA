from django_cron import CronJobBase, Schedule
from django.core import management
from django.conf import settings
from .models import Notification
import logging
import io
from logging import StreamHandler

        
class task_send_email_notifications(CronJobBase):
    RUN_EVERY_MINS = 1
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'notifications.task_send_email_notifications'

    def do(self):
        # Create a string buffer and a handler to capture logs
        log_stream = io.StringIO()
        handler = StreamHandler(log_stream)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        # Get the logger for the rm_sync module
        logger = logging.getLogger('notifications')
        logger.addHandler(handler)

        logger.info("Starting notification send run")

        for notification in Notification.objects.filter(is_emailed=False, should_email=True):
            logger.info(f"Sending {str(notification)}")
            notification.send_email()