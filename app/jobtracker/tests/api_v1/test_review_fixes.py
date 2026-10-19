"""A10 review fixes: leave in schedules, deltas, sockets, Connected Apps,
ordering, costs, project dates, search, notifications."""

import secrets
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from constance.test import override_config
from django.test import override_settings
from django.utils import timezone
from oauth2_provider.models import AccessToken, Grant, RefreshToken

from chaotica_utils.enums import LeaveRequestTypes
from chaotica_utils.models import LeaveRequest, User, UserCost
from chaotica_utils.oauth import revoke_user_tokens
from chaotica_utils.realtime import issue_ticket, user_group
from chaotica_utils.views.connected_apps import connected_apps, own_connected_apps
from jobtracker.enums import JobStatuses, TimeSlotDeliveryRole
from jobtracker.models import Job, Project, ScheduleAction, TimeSlot
from notifications.models import Notification

from .helpers import ApiV1TestCase, make_member
from .test_oauth import IN_MEMORY_LAYER, OAuthBase
from .test_schedule import ScheduleBase


class ScheduleLeaveTests(ScheduleBase):
    def _leave(self, **kwargs):
        start = self.slot.start
        return LeaveRequest.objects.create(
            user=self.crew,
            start_date=start,
            end_date=start + timedelta(hours=8),
            type_of_leave=LeaveRequestTypes.SICK,
            notes="private",
            **kwargs,
        )

    def test_only_approved_leave_without_notes(self):
        approved = self._leave(authorised=True, authorised_by=self.superuser)
        self._leave()  # pending
        self._leave(authorised=True, cancelled=True)
        body = self.api.get("/api/v1/schedule/", self.window).json()
        self.assertEqual([lr["id"] for lr in body["leave"]], [approved.pk])
        self.assertEqual(body["leave"][0]["notes"], "")
        self.assertIsNone(body["leave"][0]["authorised_by"])

    def test_manager_sees_full_leave(self):
        self.crew.manager = self.viewer
        self.crew.save()
        pending = self._leave()
        body = self.api.get("/api/v1/schedule/", self.window).json()
        row = {lr["id"]: lr for lr in body["leave"]}[pending.pk]
        self.assertEqual(row["notes"], "private")


class ScheduleDeltaTests(ScheduleBase):
    def _action(self, slot):
        return ScheduleAction.objects.create(
            actor=self.superuser,
            job=self.job,
            payload=[
                {"model": "timeslot", "pk": slot.pk, "before": None, "after": {}}
            ],
        )

    def test_bad_since_is_400(self):
        resp = self.api.get("/api/v1/schedule/deltas/", {"since": "garbage"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"]["code"], "invalid")

    def test_scoped_deltas_skip_moved_slots(self):
        since = (timezone.now() - timedelta(minutes=1)).isoformat()
        self._action(self.slot)
        self._action(self.stranger_slot)  # logged on this job, now elsewhere
        body = self.api.get(
            "/api/v1/schedule/deltas/", {"since": since, "job": self.job.pk}
        ).json()
        sent = {s["id"] for d in body["deltas"] for s in d["timeslots"]}
        self.assertEqual(sent, {self.slot.pk})

    def test_inactive_users_left_out_unfiltered(self):
        self.crew.is_active = False
        self.crew.save()
        body = self.api.get("/api/v1/schedule/", self.window).json()
        self.assertNotIn(self.crew.pk, {u["user"] for u in body["users"]})


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYER)
class ScheduleSocketTests(ApiV1TestCase):
    def test_unread_push_keeps_scheduler_socket(self):
        from chaotica.asgi import application

        raw = issue_ticket(self.normal)

        async def run():
            comm = WebsocketCommunicator(
                application, f"/ws/schedule/global/?ticket={raw}"
            )
            connected, _ = await comm.connect()
            await get_channel_layer().group_send(
                user_group(self.normal.pk), {"type": "unread.changed"}
            )
            quiet = await comm.receive_nothing(timeout=0.3)
            alive = not comm.future.done()  # a missing handler kills it
            await comm.disconnect()
            return connected, quiet, alive

        with mock.patch("channels.db.close_old_connections"):
            connected, quiet, alive = async_to_sync(run)()
        self.assertTrue(connected)
        self.assertTrue(quiet)
        self.assertTrue(alive)


class ConnectedAppTests(OAuthBase):
    def _refresh_only(self, user):
        return RefreshToken.objects.create(
            user=user, application=self.app, token=secrets.token_urlsafe(20)
        )

    def test_refresh_only_sign_in_is_listed(self):
        self._refresh_only(self.normal)
        self.assertEqual([r["application_id"] for r in own_connected_apps(self.normal)],
                         [self.app.pk])
        app = next(a for a in connected_apps() if a.pk == self.app.pk)
        self.assertEqual(app.active_tokens, 1)

    def test_revoke_ends_refresh_and_codes(self):
        refresh = self._refresh_only(self.normal)
        Grant.objects.create(
            user=self.normal,
            application=self.app,
            code="c0de",
            expires=timezone.now() + timedelta(minutes=1),
            redirect_uri="https://lcars.example.com/callback",
            scope="read",
        )
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(revoke_user_tokens(self.normal, self.app), 1)
        refresh.refresh_from_db()
        self.assertIsNotNone(refresh.revoked)
        self.assertFalse(Grant.objects.filter(user=self.normal).exists())
        self.assertEqual(own_connected_apps(self.normal), [])

    def test_token_without_user_refused(self):
        raw = secrets.token_urlsafe(30)
        AccessToken.objects.create(
            user=None,
            application=self.app,
            token=raw,
            scope="read",
            expires=timezone.now() + timedelta(hours=1),
        )
        self.assertEqual(self.as_bearer(raw).get("/api/v1/me/").status_code, 401)


class ListOrderingTests(ApiV1TestCase):
    def test_jobs_newest_first_and_clients_by_name(self):
        unit_job = self.make_job()
        newer = self.make_job(unit=unit_job.unit)
        api = self.as_user(self.superuser)
        ids = [r["id"] for r in api.get("/api/v1/jobs/").json()["results"]]
        self.assertLess(ids.index(newer.pk), ids.index(unit_job.pk))
        names = [r["display"] if "display" in r else r["name"]
                 for r in api.get("/api/v1/clients/").json()["results"]]
        self.assertEqual(names, sorted(names))

    def test_ties_broken_by_pk(self):
        job = self.make_job()
        for _ in range(3):
            self.make_job(unit=job.unit, title="Same")
        api = self.as_user(self.superuser)
        rows = api.get("/api/v1/jobs/", {"ordering": "title"}).json()["results"]
        same = [r["id"] for r in rows if r["title"] == "Same"]
        self.assertEqual(same, sorted(same))


class CostAndDateTests(ApiV1TestCase):
    def test_slot_cost_uses_rate_in_force(self):
        job = self.make_job(status=JobStatuses.IN_PROGRESS)
        phase = self.make_phase(job)
        today = timezone.now().date()
        UserCost.objects.create(
            user=self.normal, effective_from=today - timedelta(days=60),
            cost_per_hour=Decimal("10"),
        )
        UserCost.objects.create(
            user=self.normal, effective_from=today - timedelta(days=10),
            cost_per_hour=Decimal("20"),
        )
        start = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)
        slot = TimeSlot.objects.create(
            user=self.normal, phase=phase, start=start, end=start + timedelta(hours=8)
        )
        hours = Decimal(slot.get_business_hours())
        self.assertEqual(slot.cost(), round(Decimal("20") * hours, 2))
        self.assertEqual(job.staff_cost(), slot.cost())

    def test_project_dates_first_delivery_last_report(self):
        project = Project.objects.create(title="P", created_by=self.superuser)
        base = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)
        for days, role in ((3, TimeSlotDeliveryRole.DELIVERY),
                           (1, TimeSlotDeliveryRole.DELIVERY),
                           (5, TimeSlotDeliveryRole.REPORTING),
                           (8, TimeSlotDeliveryRole.REPORTING)):
            TimeSlot.objects.create(
                user=self.normal, project=project, deliveryRole=role,
                start=base + timedelta(days=days),
                end=base + timedelta(days=days, hours=8),
            )
        expected_start = (base + timedelta(days=1)).date()
        expected_end = (base + timedelta(days=8, hours=8)).date() + timedelta(weeks=1)
        self.assertEqual(project.start_date(), expected_start)
        self.assertEqual(project.delivery_date(), expected_end)
        annotated = Project.objects.annotate(
            **Project.schedule_date_annotations()
        ).get(pk=project.pk)
        self.assertEqual(annotated.start_date(), expected_start)
        self.assertEqual(annotated.delivery_date(), expected_end)


class SearchAndNotificationTests(ApiV1TestCase):
    def test_search_skips_deleted_jobs(self):
        live = self.make_job(title="Zebra live")
        self.make_job(unit=live.unit, title="Zebra gone", status=JobStatuses.DELETED)
        body = self.as_user(self.superuser).get("/api/v1/search/", {"q": "zebra"}).json()
        jobs = next(g for g in body["groups"] if g["type"] == "jobs")
        self.assertEqual([r["display"].endswith("Zebra live") for r in jobs["results"]],
                         [True])

    def test_mark_read_pushes_badge(self):
        note = Notification.objects.create(user=self.normal, title="t", message="m")
        api = self.as_user(self.normal)
        with mock.patch("chaotica_utils.realtime.push_unread_changed") as push:
            with self.captureOnCommitCallbacks(execute=True):
                api.post(
                    "/api/v1/notifications/mark-read/", {"ids": [note.pk]},
                    format="json",
                )
        push.assert_called_once_with([self.normal.pk])
