from django_ical.views import ICalFeed
from .models import TimeSlot
from chaotica_utils.models import User, Note
from chaotica_utils.utils import is_valid_uuid
from constance import config
from django.http import HttpResponseNotFound
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

# Time window for feed items
FEED_PAST_DAYS = 90
FEED_FUTURE_DAYS = 365


def _get_client_ip(request):
    """Extract client IP from request, respecting X-Forwarded-For behind proxy."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _log_feed_access(user, request, feed_type):
    """Log a calendar feed access as a system note against the user."""
    ip = _get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    ct = ContentType.objects.get_for_model(User)
    Note.objects.create(
        content_type=ct,
        object_id=user.pk,
        is_system_note=True,
        content=f"Calendar feed accessed: {feed_type} | IP: {ip} | UA: {user_agent}",
    )


def _get_time_window():
    """Return the (start, end) datetime window for feed items."""
    now = timezone.now()
    return (now - timedelta(days=FEED_PAST_DAYS), now + timedelta(days=FEED_FUTURE_DAYS))


def _resolve_feed_user(cal_key, feed_id_field, enabled_field):
    """Validate the cal_key and return the User if the feed is enabled, else None."""
    if not is_valid_uuid(cal_key):
        return None
    try:
        return User.objects.get(**{feed_id_field: cal_key, enabled_field: True})
    except User.DoesNotExist:
        return None


# ── Gating wrapper views ──
# These are what the URL conf points to. They check site-wide and per-user
# settings BEFORE handing off to the ICalFeed, returning a hard 404 if
# the feed is disabled.

_schedule_feed_instance = None
_family_feed_instance = None


def schedule_feed_view(request, cal_key):
    """Gating view for the schedule calendar feed."""
    if not config.CALENDAR_FEED_ENABLED:
        return HttpResponseNotFound()
    user = _resolve_feed_user(cal_key, "schedule_feed_id", "schedule_feed_enabled")
    if user is None:
        return HttpResponseNotFound()
    _log_feed_access(user, request, "schedule")
    # Stash the resolved user on the request so the ICalFeed can use it
    request._feed_user = user
    global _schedule_feed_instance
    if _schedule_feed_instance is None:
        _schedule_feed_instance = ScheduleFeed()
    return _schedule_feed_instance(request, cal_key=cal_key)


def family_feed_view(request, cal_key):
    """Gating view for the family calendar feed."""
    if not config.CALENDAR_FAMILY_FEED_ENABLED:
        return HttpResponseNotFound()
    user = _resolve_feed_user(
        cal_key, "schedule_feed_family_id", "schedule_feed_family_enabled"
    )
    if user is None:
        return HttpResponseNotFound()
    _log_feed_access(user, request, "family")
    request._feed_user = user
    global _family_feed_instance
    if _family_feed_instance is None:
        _family_feed_instance = ScheduleFamilyFeed()
    return _family_feed_instance(request, cal_key=cal_key)


# ── ICalFeed classes ──
# These only handle the iCal rendering. All auth/gating is done above.

class ScheduleFeed(ICalFeed):
    """
    A simple event calender
    """

    product_id = "-//chaotica.app//Schedule//EN"
    timezone = "UTC"
    file_name = "event.ics"

    def get_object(self, request, *args, **kwargs):
        return request._feed_user

    def items(self, user):
        start, end = _get_time_window()
        return TimeSlot.objects.filter(
            user=user, start__lte=end, end__gte=start
        ).order_by("-start")

    def item_title(self, item):
        return str(item)

    def item_description(self, item):
        return str(item)

    def item_start_datetime(self, item):
        return item.start

    def item_link(self, item):
        return item.get_target_url()

    def item_end_datetime(self, item):
        return item.end


class ScheduleFamilyFeed(ICalFeed):
    """
    A simple calendar showing job status (remote, onsite)
    """

    product_id = "-//chaotica.app//Schedule//EN"
    timezone = "UTC"
    file_name = "event.ics"

    def get_object(self, request, *args, **kwargs):
        return request._feed_user

    def items(self, user):
        start, end = _get_time_window()
        return TimeSlot.objects.filter(
            user=user, start__lte=end, end__gte=start
        ).order_by("-start")

    def _getEventTitle(self, item):
        if item.is_onsite:
            data = "Onsite"
        else:
            data = "Remote"

        if item.is_confirmed:
            data = data + " - Confirmed"
        else:
            data = data + " - Tentative"

        return data

    def item_title(self, item):
        return self._getEventTitle(item)

    def item_description(self, item):
        return self._getEventTitle(item)

    def item_start_datetime(self, item):
        return item.start

    def item_link(self, item):
        return ""

    def item_end_datetime(self, item):
        return item.end
