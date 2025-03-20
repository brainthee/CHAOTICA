from django import template
from django.utils import timezone
import pytz

register = template.Library()

@register.simple_tag
def can_be_managed_by(user, requesting_user):
    return user.can_be_managed_by(requesting_user)

@register.simple_tag
def get_utilisation_perc(user, org, start_date, end_date):
    return user.get_utilisation_perc(org, start_date, end_date)

@register.simple_tag
def get_available_days_in_range(user, start_date, end_date):
    return user.get_available_days_in_range(start_date, end_date)

@register.simple_tag
def get_user_working_days_range(user, org, start_date, end_date):
    return user.get_working_days_in_range(org, start_date, end_date)

@register.filter
def to_user_timezone(value, user_timezone=None):
    """Convert a datetime to the user's timezone."""
    if not value:
        return ""
    if user_timezone:
        return timezone.localtime(value, pytz.timezone(user_timezone))
    return timezone.localtime(value)