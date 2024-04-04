from django_ical.views import ICalFeed
from .models import TimeSlot
from chaotica_utils.models import User
from chaotica_utils.utils import is_valid_uuid


class ScheduleFeed(ICalFeed):
    """
    A simple event calender
    """

    product_id = "-//chaotica.app//Schedule//EN"
    timezone = "UTC"
    file_name = "event.ics"

    def get_object(self, request, *args, **kwargs):
        return kwargs["cal_key"]

    def items(self, cal_key):
        # Lets check if the key is valid...
        if (
            is_valid_uuid(cal_key)
            and User.objects.filter(schedule_feed_id=cal_key).exists()
        ):
            return TimeSlot.objects.filter(user__schedule_feed_id=cal_key).order_by(
                "-start"
            )
        return TimeSlot.objects.none()

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
        return kwargs["cal_key"]

    def items(self, cal_key):
        # Lets check if the key is valid...
        if (
            is_valid_uuid(cal_key)
            and User.objects.filter(schedule_feed_family_id=cal_key).exists()
        ):
            return TimeSlot.objects.filter(
                user__schedule_feed_family_id=cal_key
            ).order_by("-start")
        return TimeSlot.objects.none()

    def _getEventTitle(self, item):
        data = ""
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
        return "https://www.google.com"

    def item_end_datetime(self, item):
        return item.end
