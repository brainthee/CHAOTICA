from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"^ws/schedule/global/$", consumers.ScheduleConsumer.as_asgi()),
    re_path(r"^ws/schedule/job/(?P<job_id>\d+)/$", consumers.ScheduleConsumer.as_asgi()),
    re_path(r"^ws/schedule/phase/(?P<phase_id>\d+)/$", consumers.ScheduleConsumer.as_asgi()),
]
