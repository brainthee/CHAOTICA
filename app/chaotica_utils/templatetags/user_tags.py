from django import template
from django.utils import timezone
import pytz

register = template.Library()

@register.simple_tag
def can_be_managed_by(user, requesting_user):
    return user.can_be_managed_by(requesting_user)

@register.simple_tag
def get_utilisation_perc(user, start_date, end_date):
    return user.get_utilisation_perc(start_date, end_date)

@register.filter
def to_user_timezone(value, user_timezone=None):
    """Convert a datetime to the user's timezone."""
    if not value:
        return ""
    if user_timezone:
        return timezone.localtime(value, pytz.timezone(user_timezone))
    return timezone.localtime(value)