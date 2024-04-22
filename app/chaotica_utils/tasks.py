from django_cron import CronJobBase, Schedule
from django_countries import countries
from django.utils import timezone
import holidays


class task_update_holidays(CronJobBase):
    RUN_EVERY_DAYS = 1 # every 1st of the month
    schedule = Schedule(run_monthly_on_days=RUN_EVERY_DAYS)
    code = 'chaotica_utils.task_update_holidays'

    def do(self):
        from .models import Holiday, HolidayCountry

        now = timezone.now().today()
        years = [now.year, now.year + 1]
        # Lets make sure our countries list is up to date...
        for code, name in list(countries):
            HolidayCountry.objects.get_or_create(country=code)

        for country in HolidayCountry.objects.all():
            try:
                holiday_days = holidays.CountryHoliday(country.country.code)
                for subdiv in holiday_days.subdivisions:
                    dates = holidays.CountryHoliday(
                        country=country.country.code, subdiv=subdiv, years=years
                    )
                    for hol, desc in dates.items():
                        db_date, _ = Holiday.objects.get_or_create(
                            date=hol,
                            country=country,
                            reason=desc,
                        )
                        if subdiv not in db_date.subdivs:
                            db_date.subdivs.append(subdiv)
                            db_date.save()
            except NotImplementedError:
                pass


def task_send_notifications(notification, users_to_notify):
    for u in users_to_notify:
        # create a Notification..
        from .models import Notification
        Notification.objects.create(
            user=u,
            title=notification.title,
            icon=notification.icon,
            message=notification.message,
            link=notification.action_link,
            email_template=notification.email_template,
        )


class task_send_email_notifications(CronJobBase):
    RUN_EVERY_MINS = 1
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'chaotica_utils.task_send_email_notifications'

    def do(self):
        from .models import Notification
        for notification in Notification.objects.filter(is_emailed=False):
            notification.send_email()


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
