"""Missing-billing-code warnings: a phase "needs a code" when neither it nor its
job has any assignment. Warned (never blocked) in the confirm modals, as
banners on the job/phase pages and as a dashboard alarm."""

from datetime import timedelta

from django.test import TestCase, Client as TestHttpClient
from django.urls import reverse
from django.utils import timezone

from chaotica_utils.models import User
from chaotica_utils.views.entropy import compute_entropy
from jobtracker.enums import (
    DefaultTimeSlotTypes,
    JobStatuses,
    PhaseStatuses,
    TimeSlotDeliveryRole,
)
from jobtracker.models import (
    BillingCode,
    BillingCodeAssignment,
    Client,
    Job,
    OrganisationalUnit,
    Phase,
    TimeSlot,
    TimeSlotType,
)

WARNING = "No billing code is set for this phase or its job"


class BillingCodeWarningTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser(email="root@test.com", password="pw")
        self.unit = OrganisationalUnit.objects.create(name="Unit")
        self.client_obj = Client.objects.create(name="Acme")
        self.job = Job.objects.create(
            title="Test job", client=self.client_obj, unit=self.unit,
            created_by=self.root, account_manager=self.root,
        )
        Job.objects.filter(pk=self.job.pk).update(status=JobStatuses.SCOPING_COMPLETE)
        self.job.refresh_from_db()
        self.phase = Phase.objects.create(
            job=self.job, title="P1", status=PhaseStatuses.SCHEDULED_TENTATIVE,
            project_lead=self.root, report_author=self.root,
        )
        start = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)
        TimeSlot.objects.create(
            user=self.root, phase=self.phase, start=start,
            end=start + timedelta(hours=8),
            slot_type=TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.DELIVERY),
            deliveryRole=TimeSlotDeliveryRole.DELIVERY,
        )
        self.code = BillingCode.objects.create(code="A-1", client=self.client_obj)
        self.http = TestHttpClient(HTTP_HOST="localhost")
        self.http.force_login(self.root)

    def _confirm_url(self):
        return reverse(
            "phase_update_workflow",
            kwargs={
                "job_slug": self.job.slug,
                "slug": self.phase.slug,
                "new_state": PhaseStatuses.SCHEDULED_CONFIRMED,
            },
        )

    # --- helpers ------------------------------------------------------------

    def test_has_billing_code(self):
        self.assertFalse(self.phase.has_billing_code())
        self.assertTrue(
            Phase.objects.filter(Phase.missing_billing_code_q(), pk=self.phase.pk).exists()
        )
        a = BillingCodeAssignment.objects.create(code=self.code, job=self.job)
        self.assertTrue(self.phase.has_billing_code())
        self.assertFalse(
            Phase.objects.filter(Phase.missing_billing_code_q(), pk=self.phase.pk).exists()
        )
        a.delete()
        BillingCodeAssignment.objects.create(code=self.code, phase=self.phase)
        self.assertTrue(self.phase.has_billing_code())
        self.assertFalse(
            Phase.objects.filter(Phase.missing_billing_code_q(), pk=self.phase.pk).exists()
        )

    # --- confirm modals -----------------------------------------------------

    def test_confirm_modal_warns_but_allows(self):
        html = self.http.get(self._confirm_url()).json()["html_form"]
        self.assertIn(WARNING, html)
        self.assertIn("Advance Status", html)
        self.http.post(self._confirm_url())
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.status, PhaseStatuses.SCHEDULED_CONFIRMED)

    def test_confirm_modal_quiet_when_coded(self):
        BillingCodeAssignment.objects.create(code=self.code, job=self.job)
        html = self.http.get(self._confirm_url()).json()["html_form"]
        self.assertNotIn(WARNING, html)

    def test_bulk_modal_flags_phase(self):
        url = reverse(
            "phases_bulk_workflow_modal",
            kwargs={"job_slug": self.job.slug, "new_state": PhaseStatuses.SCHEDULED_CONFIRMED},
        )
        html = self.http.get(url).json()["html_form"]
        self.assertIn("No billing code</span>", html)
        self.assertIn("1 eligible phase has no billing code", html)
        BillingCodeAssignment.objects.create(code=self.code, phase=self.phase)
        html = self.http.get(url).json()["html_form"]
        self.assertNotIn("No billing code</span>", html)

    # --- banners ------------------------------------------------------------

    def test_job_and_phase_banners(self):
        job_url = reverse("job_detail", kwargs={"slug": self.job.slug})
        body = self.http.get(job_url).content.decode()
        self.assertIn("<strong>No billing code:</strong>", body)
        body = self.http.get(self.phase.get_absolute_url()).content.decode()
        self.assertIn("<strong>No billing code:</strong>", body)

        BillingCodeAssignment.objects.create(code=self.code, job=self.job)
        self.assertNotIn(
            "<strong>No billing code:</strong>", self.http.get(job_url).content.decode()
        )
        self.assertNotIn(
            "<strong>No billing code:</strong>",
            self.http.get(self.phase.get_absolute_url()).content.decode(),
        )

    def test_no_banner_for_inactive_phase(self):
        Phase.objects.filter(pk=self.phase.pk).update(status=PhaseStatuses.CANCELLED)
        body = self.http.get(
            reverse("job_detail", kwargs={"slug": self.job.slug})
        ).content.decode()
        self.assertNotIn("<strong>No billing code:</strong>", body)

    # --- dashboard alarm ----------------------------------------------------

    def test_dashboard_alarm_and_entropy(self):
        Job.objects.filter(pk=self.job.pk).update(status=JobStatuses.IN_PROGRESS)
        resp = self.http.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Phases with No Billing Code", resp.content.decode())
        result = compute_entropy(self.root)
        self.assertIsInstance(result, dict)

        BillingCodeAssignment.objects.create(code=self.code, job=self.job)
        resp = self.http.get(reverse("dashboard"))
        self.assertNotIn("Phases with No Billing Code", resp.content.decode())
