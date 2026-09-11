"""Smoke test for the generate_billing_test_data management command.

Builds a minimal in-window scenario (a UKI-style unit with a support template +
a member with an LCR; a client; a job with 2 phases + delivery timeslots) then
runs the command and asserts it produced valid, feature-exercising data and is
idempotent / clearable.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from chaotica_utils.models import User, UserCost
from chaotica_utils.utils import build_code_analytics
from jobtracker.enums import DefaultTimeSlotTypes, PhaseStatuses, TimeSlotDeliveryRole
from jobtracker.models import (
    BillingCode,
    BillingCodeAssignment,
    Client,
    Job,
    OrganisationalUnit,
    OrganisationalUnitSupportTemplateMember,
    Phase,
    TimeSlot,
    TimeSlotType,
)


def _recent_weekday(days_ago):
    d = timezone.now().date() - timedelta(days=days_ago)
    while d.weekday() >= 5:  # skip Sat/Sun so business hours > 0
        d -= timedelta(days=1)
    return d


class GenerateBillingTestDataTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_user(email="root-cmd@test.com", password="pw")
        self.unit = OrganisationalUnit.objects.create(name="UKI-cmd")
        self.member = User.objects.create_user(email="m-cmd@test.com", password="pw")
        self.unit.members.create(member=self.member)
        UserCost.objects.create(
            user=self.member, effective_from=timezone.now().date(),
            cost_per_hour=Decimal("50"),
        )
        OrganisationalUnitSupportTemplateMember.objects.create(
            unit=self.unit, user=self.member, profile_percent=Decimal("100")
        )
        self.client_obj = Client.objects.create(name="Acme-cmd")
        # Creating the job auto-applies the template (post_save signal).
        self.job = Job.objects.create(
            title="Cmd job", client=self.client_obj, unit=self.unit,
            created_by=self.root, account_manager=self.root, revenue=Decimal("0"),
        )
        delivery = TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.DELIVERY)
        for n, days_ago in enumerate((7, 6, 5), start=1):
            phase = Phase.objects.create(
                job=self.job, phase_number=n, title="P%d" % n,
                status=PhaseStatuses.SCHEDULED_CONFIRMED,
            )
            day = _recent_weekday(days_ago)
            TimeSlot.objects.create(
                user=self.member, phase=phase, slot_type=delivery,
                start=timezone.make_aware(datetime.combine(day, time(9, 0))),
                end=timezone.make_aware(datetime.combine(day, time(17, 0))),
                deliveryRole=TimeSlotDeliveryRole.DELIVERY,
            )

    def test_generates_valid_feature_data(self):
        call_command("generate_billing_test_data", force=True)

        # Revenue derived from scheduled days.
        self.job.refresh_from_db()
        self.assertGreater(self.job.revenue, 0)

        # Job-level code + assignment created.
        main = "%s-MAIN" % self.job.id
        self.assertTrue(BillingCode.objects.filter(code=main).exists())
        self.assertTrue(
            BillingCodeAssignment.objects.filter(code__code=main, job=self.job).exists()
        )

        # LCR resolves for the historical date -> support budget has hours.
        budget = self.job.get_support_budget()
        member = budget["per_member"][self.member.id]
        self.assertIsNotNone(member["budget_hours"])
        self.assertGreater(budget["pool"], 0)

        # Schedule maps to codes; the client shows in the by-client roll-up.
        window = timezone.now().date() - timedelta(days=180)
        analytics = build_code_analytics(
            User.objects.all(), window, timezone.now().date()
        )
        self.assertIn(self.client_obj.id, analytics["by_client"])

    def test_assignment_constraints_hold(self):
        # No IntegrityError on run == exactly-one-target + valid-range respected.
        call_command("generate_billing_test_data", force=True)
        for a in BillingCodeAssignment.objects.all():
            targets = [a.job_id, a.phase_id, a.project_id]
            self.assertEqual(sum(t is not None for t in targets), 1)
            if a.start_date and a.end_date:
                self.assertGreaterEqual(a.end_date, a.start_date)

    def test_idempotent_rerun(self):
        call_command("generate_billing_test_data", force=True)
        codes = BillingCode.objects.count()
        assignments = BillingCodeAssignment.objects.count()
        call_command("generate_billing_test_data", force=True)
        self.assertEqual(BillingCode.objects.count(), codes)
        self.assertEqual(BillingCodeAssignment.objects.count(), assignments)

    def test_clear_removes_generated(self):
        call_command("generate_billing_test_data", force=True)
        main = "%s-MAIN" % self.job.id
        self.assertTrue(BillingCode.objects.filter(code=main).exists())
        call_command("generate_billing_test_data", force=True, clear=True)
        self.assertFalse(BillingCode.objects.filter(code=main).exists())
