from django_cron import CronJobBase, Schedule
from django.core import management
from django_countries import countries
from django.conf import settings
from constance import config
from django.utils import timezone
import holidays
import email.utils
from django.template.loader import render_to_string
from django.core.mail import send_mail


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


def task_send_notifications(notification, users_to_notify, additional_mails=None):
    for u in users_to_notify:
        # create a Notification..
        from .models import Notification
        _ = Notification.objects.create(
            user=u,
            title=notification.title,
            icon=notification.icon,
            message=notification.message,
            link=notification.action_link,
            email_template=notification.email_template,
        )
    
    if additional_mails:
        addresses = email.utils.getaddresses([additional_mails])
        for _, email_address in addresses:
            if email_address:
                context = {}
                context["SITE_DOMAIN"] = settings.SITE_DOMAIN
                context["SITE_PROTO"] = settings.SITE_PROTO
                context["title"] = notification.title
                context["message"] = notification.message
                context["icon"] = notification.icon
                context["action_link"] = notification.action_link
                context["user"] = ""
                msg_html = render_to_string(notification.email_template, context)
                send_mail(
                    subject=notification.title,
                    message=notification.message,
                    from_email=None,
                    recipient_list=[email_address],
                    html_message=msg_html,
                )
        
        
class task_send_email_notifications(CronJobBase):
    RUN_EVERY_MINS = 1
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'chaotica_utils.task_send_email_notifications'

    def do(self):
        from .models import Notification
        for notification in Notification.objects.filter(is_emailed=False):
            notification.send_email()

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