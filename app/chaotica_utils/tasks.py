from datetime import date, timedelta
from celery import shared_task, current_task
from celery import Celery
from celery.result import AsyncResult
from celery.utils.log import get_task_logger
from django.db.models import Q
from django.utils import timezone
import pandas as pd
import holidays
from pprint import pprint


logger = get_task_logger("tasks")


@shared_task(track_started=True)
def task_update_holidays(self):
    from .models import Holiday, HolidayCountry
    now = timezone.now().today()
    years = [now.year, now.year+1]
    countries = HolidayCountry.objects.all()

    for country in countries:
        holiday_days = holidays.CountryHoliday(country.country.code)
        for subdiv in holiday_days.subdivisions:
            dates = holidays.CountryHoliday(country=country.country.code, subdiv=subdiv, years=years)
            for hol, desc in dates.items():
                db_date, created = Holiday.objects.get_or_create(date=hol, country=country, reason=desc,)
                if subdiv not in db_date.subdivs:
                    db_date.subdivs.append(subdiv)
                    db_date.save()


@shared_task(track_started=True, serializer="pickle")
def task_send_notifications(notification, users_to_notify):
    for u in users_to_notify:
        notification.send_to_user(u)