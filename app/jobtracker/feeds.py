from django_ical.views import ICalFeed
from .models import TimeSlot
from chaotica_utils.models import User
from pprint import pprint
from django.http import HttpResponseForbidden

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
        # Lets check if the key is valid...
        if User.objects.filter(schedule_feed_id=calKey).exists():
            return TimeSlot.objects.filter(user__schedule_feed_id=calKey).order_by('-start')
        else:
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
    product_id = '-//chaotica.app//Schedule//EN'
    timezone = 'UTC'
    file_name = "event.ics"

    def get_object(self, request, *args, **kwargs):
        return kwargs['calKey']

    def items(self, calKey):
        return TimeSlot.objects.filter(user__schedule_feed_family_id=calKey).order_by('-start')
    
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