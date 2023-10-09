from django_ical.views import ICalFeed
from .models import TimeSlot
from chaotica_utils.models import User
from pprint import pprint

class ScheduleFeed(ICalFeed):
    """
    A simple event calender
    """
    product_id = '-//chaotica.app//Schedule//EN'
    timezone = 'UTC'
    file_name = "event.ics"

    def get_object(self, request, *args, **kwargs):
        return kwargs['calKey']

    def items(self, calKey):
        return TimeSlot.objects.filter(user__schedule_feed_id=calKey).order_by('-start')

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
    product_id = '-//chaotica.app//Schedule//EN'
    timezone = 'UTC'
    file_name = "event.ics"

    def get_object(self, request, *args, **kwargs):
        return kwargs['calKey']

    def items(self, calKey):
        return TimeSlot.objects.filter(user__schedule_feed_family_id=calKey).order_by('-start')

    def item_title(self, item):
        if item.is_onsite:
            return "Onsite"
        else:
            return "Remote"

    def item_description(self, item):
        if item.is_confirmed:
            return "Confirmed Work"
        else:
            return "Tentative"

    def item_start_datetime(self, item):
        return item.start

    def item_link(self, item):
        return "https://www.google.com"

    def item_end_datetime(self, item):
        return item.end