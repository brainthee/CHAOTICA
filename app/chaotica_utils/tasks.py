from datetime import date, timedelta
from celery import shared_task, current_task
from celery import Celery
from celery.result import AsyncResult
from celery.utils.log import get_task_logger
from django.db.models import Q
from django_countries import countries
from django.utils import timezone
import pandas as pd
import holidays


logger = get_task_logger("tasks")


@shared_task(track_started=True)
def task_update_holidays():
    from .models import Holiday, HolidayCountry
    now = timezone.now().today()
    years = [now.year, now.year+1]
    # Lets make sure our countries list is up to date...
    for code, name in list(countries):
        HolidayCountry.objects.get_or_create(country=code)

    for country in HolidayCountry.objects.all():
        try:
            holiday_days = holidays.CountryHoliday(country.country.code)
            for subdiv in holiday_days.subdivisions:
                dates = holidays.CountryHoliday(country=country.country.code, subdiv=subdiv, years=years)
                for hol, desc in dates.items():
                    db_date, _ = Holiday.objects.get_or_create(date=hol, country=country, reason=desc,)
                    if subdiv not in db_date.subdivs:
                        db_date.subdivs.append(subdiv)
                        db_date.save()
        except NotImplementedError:
            pass


@shared_task(track_started=True, serializer="pickle")
def task_send_notifications(notification, users_to_notify):
    for u in users_to_notify:
        notification.send_to_user(u)


@shared_task(track_started=True, serializer="pickle")
def task_sync_global_permissions():
    from .models import Group
    for group in Group.objects.all():
        group.sync_global_permissions()


@shared_task(track_started=True, serializer="pickle")
def task_sync_role_permissions_to_default():
    from jobtracker.models import OrganisationalUnitRole, OrganisationalUnit
    for unit in OrganisationalUnitRole.objects.all():
        unit.sync_default_permissions()
    # Now lets clean up the units
    for unit in OrganisationalUnit.objects.all():
        unit.sync_permissions()


@shared_task(track_started=True, serializer="pickle")
def task_sync_role_permissions():
    from jobtracker.models import OrganisationalUnit
    for unit in OrganisationalUnit.objects.all():
        unit.sync_permissions()