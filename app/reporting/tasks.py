from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone
from django.conf import settings
from django_cron import CronJobBase, Schedule
from celery import shared_task
import logging
import os

from .models import ReportSchedule, SavedReportOutput
from .engine import ReportEngine
from .formatters import get_formatter

logger = logging.getLogger(__name__)

@shared_task
def generate_scheduled_report(schedule_id):
    """Generate and send a scheduled report"""
    try:
        # Get the schedule
        schedule = ReportSchedule.objects.get(pk=schedule_id)
        report = schedule.report
        
        # Check if schedule is enabled
        if not schedule.enabled:
            logger.info(f"Scheduled report {schedule_id} is disabled, skipping")
            return
        
        # Execute the report
        engine = ReportEngine(report, report.created_by)
        report_data = engine.execute(schedule.parameters)
        
        # Generate the report in the appropriate format
        formatter = get_formatter('excel', report, report_data)
        report_file = formatter.get_file()
        
        # Save the generated report
        output = SavedReportOutput(
            report=report,
            schedule=schedule,
            created_by=report.created_by,
            format='excel',
            file_size=report_file.getbuffer().nbytes,
            parameters=schedule.parameters
        )
        
        # Save the file content
        filename = f"{formatter.filename}.xlsx"
        output.file.save(filename, report_file)
        
        # Send email with the report if recipients are specified
        if schedule.recipients.exists():
            send_report_email(output, schedule)
        
        # Update the last run time
        schedule.last_run = timezone.now()
        schedule.save(update_fields=['last_run'])
        
        logger.info(f"Scheduled report {schedule_id} generated successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error generating scheduled report {schedule_id}: {e}")
        return False

def send_report_email(report_output, schedule):
    """Send an email with the report attached"""
    try:
        # Get list of recipient email addresses
        recipients = [user.email for user in schedule.recipients.filter(is_active=True)]
        
        if not recipients:
            logger.warning(f"No active recipients for scheduled report {schedule.id}")
            return
        
        # Prepare email subject and body
        subject = schedule.email_subject or f"Scheduled Report: {schedule.report.name}"
        
        # Render email content
        context = {
            'schedule': schedule,
            'report': schedule.report,
            'report_output': report_output,
            'generated_at': timezone.now(),
        }
        
        html_content = schedule.email_body or render_to_string(
            'reporting/emails/scheduled_report.html', 
            context
        )
        
        # Create email message
        email = EmailMessage(
            subject=subject,
            body=html_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        email.content_subtype = "html"  # Main content is now HTML
        
        # Attach the report if requested
        if schedule.include_as_attachment and report_output.file:
            attachment_name = os.path.basename(report_output.file.name)
            email.attach_file(report_output.file.path, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        # Send the email
        email.send(fail_silently=False)
        logger.info(f"Scheduled report {schedule.id} email sent to {len(recipients)} recipients")
        
    except Exception as e:
        logger.error(f"Error sending scheduled report email: {e}")


class ProcessScheduledReportsCronJob(CronJobBase):
    """Cron job to process scheduled reports"""
    RUN_EVERY_MINS = 60  # Run every hour
    
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'reporting.process_scheduled_reports'
    
    def do(self):
        today = timezone.now().date()
        current_time = timezone.now()
        weekday = today.weekday()  # 0 = Monday, 6 = Sunday
        
        # Find all schedules that should run
        # Daily schedules
        daily_schedules = ReportSchedule.objects.filter(
            enabled=True,
            frequency='daily'
        )
        
        # Weekly schedules for current day of week
        weekly_schedules = ReportSchedule.objects.filter(
            enabled=True,
            frequency='weekly',
            day_of_week=weekday
        )
        
        # Monthly schedules for current day of month
        monthly_schedules = ReportSchedule.objects.filter(
            enabled=True,
            frequency='monthly',
            day_of_month=today.day
        )
        
        all_schedules = list(daily_schedules) + list(weekly_schedules) + list(monthly_schedules)
        
        # Process all applicable schedules
        for schedule in all_schedules:
            # Check if it has already run today
            if schedule.last_run and schedule.last_run.date() == today:
                logger.info(f"Schedule {schedule.id} already run today, skipping")
                continue
                
            # Queue the report generation task
            generate_scheduled_report.delay(schedule.id)
            
        return f"Scheduled {len(all_schedules)} reports for processing"