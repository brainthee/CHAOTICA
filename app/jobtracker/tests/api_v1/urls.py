"""Test-only routes: probes for behaviour every /api/v1/ view inherits."""

from datetime import timedelta

from django.urls import include, path
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from jobtracker.api.v1.base import ApiV1Mixin
from jobtracker.enums import DefaultTimeSlotTypes
from jobtracker.models import TimeSlot, TimeSlotType


class ProbeView(ApiV1Mixin, APIView):
    def get(self, request):
        now = timezone.now()
        return Response(
            {
                "tz": timezone.get_current_timezone_name(),
                "now": serializers.DateTimeField().to_representation(now),
            }
        )

    def post(self, request):
        start = timezone.now().replace(microsecond=0)
        slot = TimeSlot.objects.create(
            user=request.user,
            slot_type=TimeSlotType.get_builtin_object(
                DefaultTimeSlotTypes.INTERNAL_PROJECT
            ),
            start=start,
            end=start + timedelta(hours=1),
        )
        return Response({"id": slot.pk})


urlpatterns = [
    path("api/v1/_probe/", ProbeView.as_view()),
    path("", include("chaotica.urls")),
]
