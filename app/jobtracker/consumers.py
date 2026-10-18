"""WebSocket consumer for live scheduler delta updates.

A client opens a socket for the scope it is viewing (global / job / phase). On
connect we authorise against the same ``view_job_schedule`` permission the
members/slots read views enforce, then join the scope's broadcast group. When a
mutation commits a ScheduleAction, :mod:`jobtracker.broadcast` fans the delta out
to the relevant group(s) and each connected client applies it to its vis DataSet.
"""
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async

from .utils import (
    can_view_job_schedule as _can_view_job,
    viewable_schedule_user_pks,
)
from .schedule_history import filter_delta_for_users
from chaotica_utils.realtime import user_group


class ScheduleConsumer(AsyncJsonWebsocketConsumer):
    group_name = None
    # Set for the global scope: user PKs whose slots this connection may see, so
    # the shared global broadcast is filtered per-connection. None for job/phase
    # scopes (the whole scope is already authorised in _resolve_group).
    viewable_user_pks = None

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close()
            return

        group = await self._resolve_group(user)
        if group is None:
            await self.close()
            return

        self.group_name = group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        # Also on the user's own group, so revoking their access closes it.
        self.user_group = user_group(user.pk)
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        if getattr(self, "user_group", None):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)

    async def force_disconnect(self, event):
        await _force_disconnect(self, event)

    @database_sync_to_async
    def _resolve_group(self, user):
        """Authorise the requested scope and return its broadcast group name, or
        None if the user may not view it."""
        from .models import Job, Phase

        kwargs = self.scope["url_route"]["kwargs"]
        job_id = kwargs.get("job_id")
        phase_id = kwargs.get("phase_id")

        if phase_id:
            phase = Phase.objects.select_related("job__unit").filter(pk=phase_id).first()
            if not phase or not _can_view_job(user, phase.job):
                return None
            return "schedule_phase_{}".format(phase_id)

        if job_id:
            job = Job.objects.select_related("unit").filter(pk=job_id).first()
            if not job or not _can_view_job(user, job):
                return None
            return "schedule_job_{}".format(job_id)

        # Global scope — any authenticated user may join, but the shared global
        # broadcast must be filtered to the slots this user could see in the
        # calendar (mirrors the global slots view's view_users_schedule filter).
        self.viewable_user_pks = viewable_schedule_user_pks(user)
        return "schedule_global"

    # Group message handler: broadcast.py sends {"type": "schedule.delta", ...}.
    async def schedule_delta(self, event):
        delta = filter_delta_for_users(event["delta"], self.viewable_user_pks)
        await self.send_json({"type": "delta", "delta": delta})


class MeConsumer(AsyncJsonWebsocketConsumer):
    """``ws/me/``: the signed-in user's own live channel. Sends
    ``{"type": "unread", "count": N}`` on connect and whenever their
    notifications change."""

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close()
            return
        self.group_name = user_group(user.pk)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self._send_unread()

    async def disconnect(self, code):
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    @database_sync_to_async
    def _unread(self):
        from notifications.selectors import unread_count

        return unread_count(self.scope["user"])

    async def _send_unread(self):
        await self.send_json({"type": "unread", "count": await self._unread()})

    async def unread_changed(self, event):
        await self._send_unread()

    async def force_disconnect(self, event):
        await _force_disconnect(self, event)


async def _force_disconnect(consumer, event):
    if event.get("ticket_only") and not consumer.scope.get("ws_ticket"):
        return
    await consumer.close(code=4401)
