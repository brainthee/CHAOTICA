"""Jobs & phases (A3): detail, sub-resources, gating, parity with the pages."""

from datetime import date, timedelta
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from chaotica_utils.audit import record_audit
from chaotica_utils.models import AuditCategory, AuditVerb, User
from jobtracker.enums import (
    DefaultTimeSlotTypes,
    JobStatuses,
    PhaseStatuses,
    TimeSlotDeliveryRole,
)
from jobtracker.models import Phase, TimeSlot, TimeSlotType
from jobtracker.selectors.schedule import job_team

from .helpers import ApiV1TestCase, make_member


class JobPhaseBase(ApiV1TestCase):
    def setUp(self):
        super().setUp()
        self.job = self.make_job(
            title="Bridge Audit",
            status=JobStatuses.IN_PROGRESS,
            revenue=Decimal("10000"),
            high_risk=True,
        )
        self.phase = self.make_phase(
            self.job,
            title="External",
            delivery_hours=Decimal("16"),
            desired_delivery_date=date(2026, 3, 1),
        )
        self.member = make_member(
            User.objects.create_user(email="crew@example.com", password="pw"),
            self.job.unit,
        )
        start = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)
        TimeSlot.objects.create(
            user=self.member,
            phase=self.phase,
            slot_type=TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.DELIVERY),
            deliveryRole=TimeSlotDeliveryRole.DELIVERY,
            start=start,
            end=start + timedelta(hours=8),
        )
        self.su = self.as_user(self.superuser)
        self.crew = self.as_user(self.member)


class JobDetailTests(JobPhaseBase):
    def test_detail_shape(self):
        body = self.su.get(f"/api/v1/jobs/{self.job.pk}/").json()
        self.assertEqual(body["job_id"], self.job.id)
        self.assertIn("High Risk", body["warnings"])
        self.assertEqual(body["scoped_days"], float(self.job.get_total_scoped_days()))
        self.assertEqual(body["workflow"]["status"], JobStatuses.IN_PROGRESS)
        self.assertTrue(body["capabilities"]["can_update"])
        self.assertEqual(body["billing"], [])
        self.assertIsNone(body["primary_poc"])

    def test_list_has_dates_and_orders_by_delivery(self):
        later = self.make_job(desired_delivery_date=date(2027, 1, 1))
        self.job.desired_delivery_date = date(2026, 6, 1)
        self.job.save()
        rows = self.su.get("/api/v1/jobs/?ordering=-delivery_date").json()["results"]
        self.assertEqual(rows[0]["id"], later.pk)
        self.assertIn("delivery_date", rows[0])

    def test_detail_query_budget(self):
        self.su.get(f"/api/v1/jobs/{self.job.pk}/")
        with self.assertNumQueries(13):
            self.su.get(f"/api/v1/jobs/{self.job.pk}/")

    def test_capabilities_follow_unit_role(self):
        # Consultants hold can_update_job on their unit, as on the job page.
        body = self.crew.get(f"/api/v1/jobs/{self.job.pk}/").json()
        self.assertTrue(body["capabilities"]["can_update"])
        self.assertTrue(body["capabilities"]["can_view_schedule"])
        self.assertFalse(body["capabilities"]["can_view_loaded_costs"])

    def test_outsider_404(self):
        outsider = User.objects.create_user(email="out@example.com", password="pw")
        resp = self.as_user(outsider).get(f"/api/v1/jobs/{self.job.pk}/")
        self.assertEqual(resp.status_code, 404)
        resp = self.as_user(outsider).get(f"/api/v1/jobs/{self.job.pk}/team/")
        self.assertEqual(resp.status_code, 404)


class JobSubResourceTests(JobPhaseBase):
    def test_phases(self):
        body = self.crew.get(f"/api/v1/jobs/{self.job.pk}/phases/").json()
        self.assertEqual([r["id"] for r in body["results"]], [self.phase.pk])

    def test_team_matches_page(self):
        body = self.crew.get(f"/api/v1/jobs/{self.job.pk}/team/").json()
        _labels, entries = job_team(self.job)
        self.assertEqual(
            {m["user"]["id"] for m in body}, {e["user"].pk for e in entries}
        )
        me = next(m for m in body if m["user"]["id"] == self.member.pk)
        self.assertEqual(me["roles"][0]["role"], TimeSlotDeliveryRole.DELIVERY)
        self.assertEqual(me["phases"][0]["phase"]["id"], self.phase.pk)
        # The page still renders from the same selector.
        self.client.force_login(self.member)
        page = self.client.get(reverse("view_job_team", kwargs={"slug": self.job.slug}))
        self.assertEqual(page.status_code, 200)

    def test_sales_finance_gated(self):
        crew = self.crew.get(f"/api/v1/jobs/{self.job.pk}/sales/").json()
        self.assertEqual(crew["revenue"], 10000.0)
        self.assertIsNone(crew["staff_cost"])
        self.assertIsNone(crew["profit"])
        self.assertFalse(crew["includes_finance"])
        su = self.su.get(f"/api/v1/jobs/{self.job.pk}/sales/").json()
        self.assertIsNotNone(su["staff_cost"])
        self.assertTrue(su["includes_finance"])

    def test_support_team(self):
        resp = self.crew.get(f"/api/v1/jobs/{self.job.pk}/support-team/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    def test_notes(self):
        self.job.notes.create(author=self.superuser, content="Kickoff done")
        self.job.notes.create(
            author=self.superuser, content="auto", is_system_note=True
        )
        body = self.crew.get(f"/api/v1/jobs/{self.job.pk}/notes/").json()
        self.assertEqual([n["content"] for n in body["results"]], ["Kickoff done"])
        self.assertEqual(body["results"][0]["author"]["id"], self.superuser.pk)

    def test_activity_hides_sensitive_from_non_admins(self):
        record_audit(
            self.job, AuditVerb.UPDATE, message="title changed", actor=self.superuser
        )
        record_audit(
            self.job,
            AuditVerb.UPDATE,
            message="cost changed",
            actor=self.superuser,
            category=AuditCategory.FINANCE,
        )
        crew = self.crew.get(f"/api/v1/jobs/{self.job.pk}/activity/").json()
        messages = {e["message"] for e in crew["results"]}
        self.assertIn("title changed", messages)
        self.assertNotIn("cost changed", messages)
        su = self.su.get(f"/api/v1/jobs/{self.job.pk}/activity/").json()
        self.assertIn("cost changed", {e["message"] for e in su["results"]})
        self.assertEqual(su["results"][0]["actor"]["id"], self.superuser.pk)


class PhaseDetailTests(JobPhaseBase):
    def test_detail_shape(self):
        body = self.crew.get(f"/api/v1/phases/{self.phase.pk}/").json()
        self.assertEqual(body["client"]["id"], self.job.client.pk)
        self.assertEqual(body["scoped_hours"], 16.0)
        self.assertEqual(body["scoped_days"], float(self.phase.get_total_scoped_days()))
        self.assertGreater(body["scheduled_hours"], 0)
        self.assertTrue(body["missing_billing_code"])
        self.assertEqual(body["concurrent_phases"], [])
        self.assertEqual(body["workflow"]["status"], PhaseStatuses.DRAFT)
        self.assertIn("can_update", body["capabilities"])
        self.assertIn("is_delivery_late", body)

    def test_team(self):
        from jobtracker.selectors.schedule import phase_team

        body = self.crew.get(f"/api/v1/phases/{self.phase.pk}/team/").json()
        _labels, entries = phase_team(self.phase)
        self.assertEqual(
            [m["user"]["id"] for m in body], [e["user"].pk for e in entries]
        )
        booked = next(m for m in body if m["user"]["id"] == self.member.pk)
        self.assertFalse(booked["unscheduled"])

    def test_feedback(self):
        self.phase.feedback.create(author=self.superuser, body="Nice report")
        body = self.crew.get(f"/api/v1/phases/{self.phase.pk}/feedback/").json()
        self.assertEqual(body["feedback"][0]["body"], "Nice report")
        self.assertIsNone(body["techqa_report_rating"])

    def test_list_orders_by_delivery_date(self):
        other = self.make_phase(self.job, desired_delivery_date=date(2025, 1, 1))
        rows = self.su.get("/api/v1/phases/?ordering=delivery_date").json()["results"]
        self.assertEqual([r["id"] for r in rows][:2], [other.pk, self.phase.pk])

    def test_page_still_renders(self):
        self.client.force_login(self.superuser)
        resp = self.client.get(self.phase.get_absolute_url())
        self.assertEqual(resp.status_code, 200)


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
class JobPagesStillRenderTests(JobPhaseBase):
    def test_job_detail_and_sales_pages(self):
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(self.job.get_absolute_url()).status_code, 200)
        resp = self.client.get(
            reverse("view_job_sales", kwargs={"slug": self.job.slug})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Phase.objects.count(), 1)
