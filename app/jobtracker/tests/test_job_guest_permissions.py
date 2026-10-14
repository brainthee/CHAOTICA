"""Job team "guest" fallback: anyone on the team may view and add notes, but
only phase role holders (lead / author / TQA / PQA) get update rights."""

from django.test import override_settings
from django.urls import reverse

from chaotica_utils.models import User
from .test_schedule_history import ScheduleHistoryBase


@override_settings(ALLOWED_HOSTS=["*", "testserver"])
class JobGuestPermissionTests(ScheduleHistoryBase):
    def setUp(self):
        super().setUp()
        self.bookee = User.objects.create_user(email="bookee@test.com", password="pw12345")
        self._delivery_slot(user=self.bookee)
        self.lead = User.objects.create_user(email="lead@test.com", password="pw12345")
        self.phase.project_lead = self.lead
        self.phase.save()

    def _get(self, user, name, **kwargs):
        self.client.force_login(user)
        return self.client.get(reverse(name, kwargs=kwargs), HTTP_HOST="testserver")

    def test_bookee_can_view_job(self):
        self.assertEqual(self._get(self.bookee, "job_detail", slug=self.job.slug).status_code, 200)

    def test_bookee_passes_note_gate(self):
        # GET is a 400 from the view itself - i.e. the permission gate let it through.
        resp = self._get(self.bookee, "job_create_note", slug=self.job.slug)
        self.assertEqual(resp.status_code, 400)

    def test_bookee_cannot_update_job(self):
        resp = self._get(self.bookee, "job_link_add", slug=self.job.slug)
        self.assertEqual(resp.status_code, 403)

    def test_phase_lead_can_update_job(self):
        resp = self._get(self.lead, "job_link_add", slug=self.job.slug)
        self.assertEqual(resp.status_code, 200)

    def test_outsider_cannot_view(self):
        outsider = User.objects.create_user(email="out@test.com", password="pw12345")
        self.assertEqual(self._get(outsider, "job_detail", slug=self.job.slug).status_code, 403)
