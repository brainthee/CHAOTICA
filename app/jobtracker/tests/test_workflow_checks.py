"""``can_to_*`` checks must not crash without a request.

Templates call them with no arguments (``{% if not job.can_to_scoping %}``),
and the API calls them with ``user=``.
"""

from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase

from chaotica_utils.middleware.common import set_current_user
from chaotica_utils.models import User
from jobtracker.enums import JobStatuses, PhaseStatuses
from jobtracker.models import Client, Job, OrganisationalUnit, Phase


class WorkflowChecksWithoutRequestTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="root@test.com", password="pw")
        self.qa = User.objects.create_user(email="qa@test.com", password="pw")
        self.other = User.objects.create_user(email="other@test.com", password="pw")
        self.unit = OrganisationalUnit.objects.create(name="Unit")
        self.client_obj = Client.objects.create(name="Client")
        self.job = Job.objects.create(
            unit=self.unit, client=self.client_obj, title="Job",
            created_by=self.admin, account_manager=self.admin,
        )
        self.addCleanup(set_current_user, None)

    def test_job_can_to_scoping_without_scoper(self):
        Job.objects.filter(pk=self.job.pk).update(status=JobStatuses.PENDING_SCOPE)
        self.job.refresh_from_db()
        self.assertIsInstance(self.job.can_to_scoping(), bool)
        self.assertFalse(self.job.can_to_scoping(user=self.other))
        self.assertTrue(self.job.can_to_scoping(user=self.admin))

    def _qa_phase(self, status, **people):
        Job.objects.filter(pk=self.job.pk).update(status=JobStatuses.IN_PROGRESS)
        phase = Phase.objects.create(job=self.job, title="P1", **people)
        Phase.objects.filter(pk=phase.pk).update(status=status)
        phase.refresh_from_db()
        return phase

    def test_phase_qa_update_checks(self):
        tqa = self._qa_phase(PhaseStatuses.QA_TECH, techqa_by=self.qa)
        self.assertIsInstance(tqa.can_to_tech_qa_updates(), bool)
        self.assertTrue(tqa.can_to_tech_qa_updates(user=self.qa))
        self.assertFalse(tqa.can_to_tech_qa_updates(user=self.other))

        pqa = self._qa_phase(PhaseStatuses.QA_PRES, presqa_by=self.qa)
        self.assertIsInstance(pqa.can_to_pres_qa_updates(), bool)
        self.assertTrue(pqa.can_to_pres_qa_updates(user=self.qa))
        self.assertFalse(pqa.can_to_pres_qa_updates(user=self.other))

    def test_status_button_partials_render(self):
        Job.objects.filter(pk=self.job.pk).update(status=JobStatuses.PENDING_SCOPE)
        self.job.refresh_from_db()
        request = RequestFactory().get("/")
        request.user = self.other
        set_current_user(self.other)
        render_to_string(
            "partials/job/status_buttons.html", {"job": self.job}, request=request
        )
        phase = self._qa_phase(PhaseStatuses.QA_TECH, techqa_by=self.qa)
        render_to_string(
            "partials/phase/status_buttons.html", {"phase": phase}, request=request
        )
