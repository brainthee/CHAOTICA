"""T-13: resizable scheduler panels render their hooks.

The dragging itself is client-side (no JS harness); this pins the markup the
script relies on: the name-column CSS variable, the job/phase side-panel
splitter + collapse button, and the resize code in the shared init script.
"""
from django.test import Client, override_settings
from django.urls import reverse

from .test_schedule_history import ScheduleHistoryBase


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class SchedulerPanelTests(ScheduleHistoryBase):
    def setUp(self):
        super().setUp()
        self.http = Client(HTTP_HOST="localhost")
        self.http.force_login(self.actor)  # superuser

    def test_job_and_phase_pages_have_splitter(self):
        for url in (
            reverse("job_schedule", kwargs={"slug": self.job.slug}),
            reverse(
                "phase_schedule",
                kwargs={"job_slug": self.job.slug, "slug": self.phase.slug},
            ),
        ):
            resp = self.http.get(url)
            self.assertEqual(resp.status_code, 200, url)
            self.assertContains(resp, 'id="sched-split"')
            self.assertContains(resp, 'id="sched-split-handle"')
            self.assertContains(resp, 'id="sched-split-toggle"')
            self.assertContains(resp, "var(--sched-label-w)")
            self.assertContains(resp, "sched-panel-collapsed")

    def test_embedded_and_global_timelines_get_resize_code(self):
        for url in (
            reverse("job_detail", kwargs={"slug": self.job.slug}),
            reverse("view_scheduler") + "?nofilter=1",
        ):
            resp = self.http.get(url)
            self.assertEqual(resp.status_code, 200, url)
            self.assertContains(resp, "var(--sched-label-w)")
            self.assertContains(resp, "sched-label-w")
            self.assertContains(resp, "sched-embed-h")
            self.assertNotContains(resp, 'id="sched-split"')
