from ..models import *
from django.conf import settings as django_settings
from datetime import timedelta, time, timezone, datetime
from uuid import UUID
import re, logging
from datetime import time
from ..enums import GlobalRoles
from django.utils.text import slugify
from menu import MenuItem
from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from django.utils.dateparse import (
    parse_date,
    parse_datetime,
    parse_duration,
    parse_time,
)
from django.utils.timezone import is_aware, make_aware, now


def can_manage_user(requesting_user, target_user):
    """
    Determines if requesting_user has permission to manage target_user.

    Permission is granted if any of these conditions are met:
    1. requesting_user is the same as target_user (self-management)
    2. requesting_user is the manager or acting_manager of target_user
    3. requesting_user has the "manage_user" guardian permission

    Args:
        requesting_user: The User object requesting to manage another user
        target_user: Either a User object or an email string

    Returns:
        User: User object if requesting_user can manage target_user, None otherwise
    """
    from ..models import User

    # Ensure requesting_user is valid
    if not requesting_user or not requesting_user.is_authenticated:
        return None

    # Convert target_user to a User object if it's an email string
    if isinstance(target_user, str):
        try:
            target_user = User.objects.prefetch_related(
                "unit_memberships",
                "skills",
            ).get(email=target_user)
        except User.DoesNotExist:
            return None  # Target user doesn't exist

    # Ensure target_user is a valid User object
    if not target_user or not isinstance(target_user, User):
        return None

    # Finally, use the model class to ensure consistency
    if target_user.can_be_managed_by(requesting_user):
        return target_user
    else:
        # All conditions failed, return None
        return None


def get_start_of_week(dt=None):
    """
    Returns the start (Monday) of the current week.
    If a datetime is provided, returns the start of that week instead.

    Args:
        dt (datetime, optional): A datetime object. Defaults to None (uses current date).

    Returns:
        datetime.date: The Monday of the specified week at midnight.
    """
    if dt is None:
        dt = datetime.now()

    # Weekday is 0 for Monday, 6 for Sunday in the datetime module
    start_of_week = dt.date() - timedelta(days=dt.weekday())

    return start_of_week


def calculate_percentage(part, whole, decimal_places=1):
    """
    Calculate percentage with specified decimal places.

    Args:
        part (float|int): The partial value
        whole (float|int): The total value
        decimal_places (int, optional): Number of decimal places to round to. Defaults to 1.

    Returns:
        float: The calculated percentage rounded to specified decimal places

    Raises:
        ZeroDivisionError: If whole is zero
        ValueError: If decimal_places is negative
    """
    if whole == 0:
        raise ZeroDivisionError("Cannot calculate percentage with zero total")

    if decimal_places < 0:
        raise ValueError("Decimal places must be non-negative")

    try:
        percentage = (part / whole) * 100
        return round(percentage, decimal_places)
    except TypeError:
        raise TypeError("Part and whole must be numeric values")


class NoColorFormatter(logging.Formatter):
    """
    Log formatter that strips terminal colour
    escape codes from the log message.
    """

    # Regex for ANSI colour codes
    ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

    def format(self, record):
        """Return logger message with terminal escapes removed."""
        return "%s %s %s" % (
            datetime.strftime(now(), "%Y-%m-%d %H:%M:%S"),
            re.sub(self.ANSI_RE, "", record.levelname),
            record.msg,
        )


def unique_slug_generator(instance, value=None):
    """Creates a unique slug

    Args:
        instance (_type_): _description_
        value (_type_, optional): _description_. Defaults to None.

    Returns:
        _type_: _description_
    """
    slug = slugify(value)
    new_slug = slug
    Klass = instance.__class__
    numb = 1
    while Klass.objects.filter(slug=new_slug).exists():
        new_slug = "{slug}-{num}".format(slug=slug, num=numb)
        numb += 1
    return new_slug


class RoleMenuItem(MenuItem):
    """Custom MenuItem that checks permissions based on the view associated
    with a URL"""

    def check(self, request):
        if self.requiredRole and request.user.is_authenticated:
            if self.requiredRole == "*":
                self.visible = request.user.groups.filter().exists()
            else:
                self.visible = request.user.groups.filter(
                    name=settings.GLOBAL_GROUP_PREFIX
                    + GlobalRoles.CHOICES[self.requiredRole][1]
                ).exists()
        else:
            self.visible = False


class PermMenuItem(MenuItem):
    """Custom MenuItem that checks permissions based on the view associated
    with a URL"""

    def check(self, request):
        if self.perm and request.user.is_authenticated:
            self.visible = request.user.has_perm(self.perm)
        else:
            self.visible = False


def clean_fullcalendar_datetime(date):
    # 2023-10-23T00:00:00+01:00
    # 2023-10-23T00:00:00+01:00
    # 2023-10-30T00:00:00Z
    # 2023-10-30T00:00:00Z
    if date == None:
        return None
    try:
        datetime_pattern = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")
        dt_format = "%Y-%m-%dT%H:%M:%S"
        ret = datetime.strptime(datetime_pattern.search(date).group(), dt_format)
        if not is_aware(ret):
            ret = make_aware(ret)
        return ret
    except (ValueError, AttributeError):
        raise SuspiciousOperation()


def clean_int(value):
    """
    Tries to convert the value to an int and raises SuspiciousOperation if it fails
    """
    if value == None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        raise SuspiciousOperation()


def clean_date(value):
    """
    Tries to convert the value to a Date and raises SuspiciousOperation if it fails
    """
    if value == None:
        return None
    try:
        return parse_date(value)
    except ValueError:
        raise SuspiciousOperation()


def clean_datetime(value):
    """
    Tries to convert the value to a DateTime and raises SuspiciousOperation if it fails
    """
    if value == None:
        return None
    try:
        ret = parse_datetime(value)
        if not is_aware(ret):
            ret = make_aware(ret)
        return ret
    except ValueError:
        raise SuspiciousOperation()


def make_datetime_tzaware(value, tzinfo=timezone.utc):
    """
    Makes the DateTime TZ aware and raises SuspiciousOperation if it fails
    """
    if value == None:
        return None
    try:
        if not is_aware(value):
            value = make_aware(value, timezone=tzinfo)
        return value
    except ValueError:
        raise SuspiciousOperation()


def clean_time(value):
    """
    Tries to convert the value to a Time and raises SuspiciousOperation if it fails
    """
    if value == None:
        return None
    try:
        return parse_time(value)
    except ValueError:
        raise SuspiciousOperation()


def clean_duration(value):
    """
    Tries to convert the value to a Duration and raises SuspiciousOperation if it fails
    """
    if value == None:
        return None
    try:
        return parse_duration(value)
    except ValueError:
        raise SuspiciousOperation()


def datetime_startofday(dte):
    return make_datetime_tzaware(datetime.combine(dte, time.min))


def datetime_endofday(dte):
    return make_datetime_tzaware(datetime.combine(dte, time.max))


def is_valid_uuid(uuid_to_test, version=4):
    """
    Check if uuid_to_test is a valid UUID.

     Parameters
    ----------
    uuid_to_test : str
    version : {1, 2, 3, 4}

     Returns
    -------
    `True` if uuid_to_test is a valid UUID, otherwise `False`.

     Examples
    --------
    >>> is_valid_uuid('c9bf9e57-1685-4c89-bafb-ff5af830be8a')
    True
    >>> is_valid_uuid('c9bf9e58')
    False
    """

    try:
        uuid_obj = UUID(uuid_to_test, version=version)
    except ValueError:
        return False
    return str(uuid_obj) == uuid_to_test


def ext_reverse(reversed_url):
    return "{}://{}{}".format(
        django_settings.SITE_PROTO, django_settings.SITE_DOMAIN, reversed_url
    )


def is_ajax(request):
    return request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest"


def last_day_of_month(any_day):
    # The day 28 exists in every month. 4 days later, it's always next month
    next_month = any_day.replace(day=28) + timedelta(days=4)
    # subtracting the number of the current day brings us back one month
    return next_month - timedelta(days=next_month.day)


def get_week(day=None):
    if not day:
        day = now()
    start = day - timedelta(days=day.weekday())
    end = start + timedelta(days=6)
    return { 'start': start, 'end': end}