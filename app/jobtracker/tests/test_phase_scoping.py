"""Phase scoping capture, deliverable unlock, and section-edit modal views."""

import json
from decimal import Decimal

from django.core.cache import cache
from django.test import Client as TestHttpClient, TestCase
from django.urls import reverse

from chaotica_utils.models import User
from jobtracker.enums import PhaseStatuses
from jobtracker.forms import PhaseDeliverInlineForm
from jobtracker.models import Client, Job, OrganisationalUnit, Phase, Service
from jobtracker.models.scoping import (
    CalcMode,
    ScopingCalcRole,
    ScopingField,
    ScopingFieldType,
    ScopingTemplate,
    SizingCombine,
)


def _make_template():
    t = ScopingTemplate.objects.create(
        name="Web App",
        calc_mode=CalcMode.DECLARATIVE,
        sizing_combine=SizingCombine.MAX,
        reporting_expression="testing_days / 4",
    )
    ScopingField.objects.create(
        template=t, label="Pages", slug="pages",
        field_type=ScopingFieldType.NUMBER,
        calc_role=ScopingCalcRole.SIZING, rate=Decimal("15"),
    )
    ScopingField.objects.create(
        template=t, label="Inputs", slug="inputs",
        field_type=ScopingFieldType.NUMBER,
        calc_role=ScopingCalcRole.SIZING, rate=Decimal("200"),
    )
    return t


class PhaseScopingBase(TestCase):
    def setUp(self):
        cache.clear()
        # First user auto-promoted to superuser (first-user gotcha); keep it.
        self.admin = User.objects.create_user(email="admin@ps.com", password="pw")
        self.outsider = User.objects.create_user(email="out@ps.com", password="pw")
        self.outsider.is_superuser = False
        self.outsider.save()

        self.unit = OrganisationalUnit.objects.create(name="PS Unit")
        self.client_obj = Client.objects.create(name="PS Client")
        self.template = _make_template()
        self.service = Service.objects.create(name="Web App Test")
        self.service.scoping_template = self.template
        self.service.save()

        self.job = Job.objects.create(
            title="PS Job", unit=self.unit, client=self.client_obj,
            created_by=self.admin, account_manager=self.admin,
        )
        self.phase = Phase.objects.create(
            job=self.job, title="PS Phase", service=self.service,
            status=PhaseStatuses.IN_PROGRESS,
        )
        self.http = TestHttpClient(HTTP_HOST="localhost")
        self.http.force_login(self.admin)

    def _url(self, name, **extra):
        kwargs = {"job_slug": self.job.slug, "slug": self.phase.slug}
        kwargs.update(extra)
        return reverse(name, kwargs=kwargs)


class PhaseScopingCaptureTests(PhaseScopingBase):
    def test_save_answers_only(self):
        resp = self.http.post(
            self._url("phase_scoping_update"),
            data=json.dumps({"answers": {"pages": 30, "inputs": 200}, "apply": False}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.data["scoping_answers"]["pages"], 30)
        # Hours untouched when not applying.
        self.assertIn(self.phase.delivery_hours, (None, 0, 0.0))

    def test_apply_writes_hours_and_justification(self):
        resp = self.http.post(
            self._url("phase_scoping_update"),
            data=json.dumps({"answers": {"pages": 30, "inputs": 200}, "apply": True}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.phase.refresh_from_db()
        # pages 30/15 = 2 testing days -> 2 * 7.5 = 15 delivery hours
        self.assertEqual(float(self.phase.delivery_hours), 15.0)
        self.assertEqual(float(self.phase.reporting_hours), 3.75)  # 0.5 day * 7.5
        self.assertTrue(self.phase.data["scoping_justification"])
        self.assertEqual(self.phase.data["scoping_result"]["testing_days"], 2.0)

    def test_apply_blocked_when_hours_locked(self):
        self.phase.status = PhaseStatuses.PENDING_TQA  # CHANGEABLE_FIELDS == []
        self.phase.save()
        resp = self.http.post(
            self._url("phase_scoping_update"),
            data=json.dumps({"answers": {"pages": 30}, "apply": True}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.phase.refresh_from_db()
        self.assertIn(self.phase.delivery_hours, (None, 0, 0.0))

    def test_calc_endpoint(self):
        resp = self.http.post(
            self._url("phase_scoping_calc"),
            data=json.dumps({"answers": {"pages": 45}}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["testing_days"], 3.0)

    def test_no_template_graceful(self):
        self.service.scoping_template = None
        self.service.save()
        resp = self.http.post(
            self._url("phase_scoping_calc"),
            data=json.dumps({"answers": {}}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_requires_permission(self):
        self.http.force_login(self.outsider)
        resp = self.http.post(
            self._url("phase_scoping_update"),
            data=json.dumps({"answers": {}, "apply": False}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)


class DetailPageRenderTests(PhaseScopingBase):
    """Smoke-render the restructured detail pages (template syntax, url tags,
    json_script, the new scoping tab and section pencils)."""

    def test_phase_detail_renders_with_scoping_tab(self):
        resp = self.http.get(
            reverse("phase_detail", kwargs={
                "job_slug": self.job.slug, "slug": self.phase.slug
            })
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="scoping"')
        self.assertContains(resp, "phase-scope-answer")

    def test_job_detail_renders(self):
        resp = self.http.get(reverse("job_detail", kwargs={"slug": self.job.slug}))
        self.assertEqual(resp.status_code, 200)


class DeliverableUnlockTests(PhaseScopingBase):
    def test_form_editable_through_delivered(self):
        for status in range(PhaseStatuses.IN_PROGRESS, PhaseStatuses.DELIVERED + 1):
            self.phase.status = status
            form = PhaseDeliverInlineForm(instance=self.phase)
            self.assertFalse(
                form.fields["linkDeliverable"].disabled,
                "status %s should be editable" % status,
            )
            self.assertFalse(form.fields["number_of_reports"].disabled)

    def test_form_readonly_outside_window(self):
        for status in (PhaseStatuses.DRAFT, PhaseStatuses.CANCELLED,
                       PhaseStatuses.ARCHIVED):
            self.phase.status = status
            form = PhaseDeliverInlineForm(instance=self.phase)
            self.assertTrue(
                form.fields["linkDeliverable"].disabled,
                "status %s should be read-only" % status,
            )

    def test_report_metadata_round_trips(self):
        resp = self.http.post(
            self._url("phase_edit_delivery"),
            data={
                "linkDeliverable": "https://x/deliverable",
                "linkTechData": "https://x/tech",
                "linkReportData": "https://x/report",
                "number_of_reports": 3,
                "report_to_be_left_on_client_site": "on",
                "desired_delivery_date": "2026-12-01",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()["form_is_valid"])
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.number_of_reports, 3)
        self.assertTrue(self.phase.report_to_be_left_on_client_site)
        self.assertEqual(self.phase.linkDeliverable, "https://x/deliverable")

    def test_edit_delivery_blocked_outside_window(self):
        self.phase.status = PhaseStatuses.DRAFT
        self.phase.save()
        resp = self.http.post(
            self._url("phase_edit_delivery"),
            data={"number_of_reports": 9},
        )
        self.assertEqual(resp.status_code, 400)


class PhaseSectionEditTests(PhaseScopingBase):
    def test_get_returns_html_form(self):
        resp = self.http.get(
            self._url("phase_section_edit", section="details"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        html = resp.json()["html_form"]
        self.assertIn("<form", html)
        # Exactly one form — crispy must not nest a second <form> in the modal.
        self.assertEqual(html.count("<form"), 1)

    def test_post_saves_and_reports_valid(self):
        resp = self.http.post(
            self._url("phase_section_edit", section="details"),
            data={
                "phase_number": self.phase.phase_number or 1,
                "title": "Renamed phase",
                "service": self.service.pk,
            },
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()["form_is_valid"])
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.title, "Renamed phase")

    def test_unknown_section_bad_request(self):
        resp = self.http.get(self._url("phase_section_edit", section="bogus"))
        self.assertEqual(resp.status_code, 400)

    def test_requires_permission(self):
        self.http.force_login(self.outsider)
        resp = self.http.get(self._url("phase_section_edit", section="details"))
        self.assertEqual(resp.status_code, 403)
