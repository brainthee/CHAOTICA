import json
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse

from chaotica_utils.models import User
from jobtracker.models import Service
from jobtracker.models.scoping import (
    ScopingTemplate,
    ScopingField,
    ScopingMacro,
    ScopingFieldType,
    ScopingCalcRole,
    SizingCombine,
    CalcMode,
)
from jobtracker.scoping_engine import evaluate, bucket, round_half_up
from jobtracker.views_scoping import build_pack, import_pack


class ScopingEngineHelperTests(TestCase):
    def test_round_half_up(self):
        self.assertEqual(round_half_up(2.1), 2.5)
        self.assertEqual(round_half_up(2.0), 2.0)
        self.assertEqual(round_half_up(2.6), 3.0)

    def test_bucket(self):
        self.assertEqual(bucket(40, [50, 100, 1000], [1, 2, 5]), 1)
        self.assertEqual(bucket(75, [50, 100, 1000], [1, 2, 5]), 2)
        self.assertEqual(bucket(5000, [50, 100, 1000], [1, 2, 5]), 5)  # beyond last


class ScopingDeclarativeTests(TestCase):
    def setUp(self):
        self.t = ScopingTemplate.objects.create(
            name="Web App",
            calc_mode=CalcMode.DECLARATIVE,
            sizing_combine=SizingCombine.MAX,
            reporting_expression="testing_days / 4",
        )
        ScopingField.objects.create(
            template=self.t, label="Pages", slug="pages",
            field_type=ScopingFieldType.NUMBER,
            calc_role=ScopingCalcRole.SIZING, rate=Decimal("15"),
        )
        ScopingField.objects.create(
            template=self.t, label="Inputs", slug="inputs",
            field_type=ScopingFieldType.NUMBER,
            calc_role=ScopingCalcRole.SIZING, rate=Decimal("200"),
        )
        ScopingField.objects.create(
            template=self.t, label="2FA", slug="twofa",
            field_type=ScopingFieldType.BOOLEAN,
            calc_role=ScopingCalcRole.ADDITIVE, weight=Decimal("2"),
        )

    def test_max_sizing_plus_additive(self):
        # pages 30/15=2, inputs 200/200=1 -> max 2 ; +2 for 2FA = 4
        r = evaluate(self.t, {"pages": 30, "inputs": 200, "twofa": True})
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["testing_days"], 4.0)
        self.assertEqual(r["reporting_days"], 1.0)
        self.assertEqual(r["delivery_hours"], 30.0)   # 4 * 7.5
        self.assertEqual(r["reporting_hours"], 7.5)

    def test_additive_not_applied_when_false(self):
        r = evaluate(self.t, {"pages": 30, "inputs": 0, "twofa": False})
        self.assertEqual(r["testing_days"], 2.0)

    def test_sum_combine(self):
        self.t.sizing_combine = SizingCombine.SUM
        self.t.save()
        r = evaluate(self.t, {"pages": 30, "inputs": 200, "twofa": False})
        self.assertEqual(r["testing_days"], 3.0)  # 2 + 1

    def test_number_multiplier(self):
        ScopingField.objects.create(
            template=self.t, label="Roles", slug="roles",
            field_type=ScopingFieldType.NUMBER,
            calc_role=ScopingCalcRole.MULTIPLIER, weight=Decimal("0.1"),
        )
        # base max(2,1)=2, +0 additive, roles=2 -> +20% -> 2 * 1.2 = 2.4
        r = evaluate(self.t, {"pages": 30, "inputs": 0, "twofa": False, "roles": 2})
        self.assertEqual(r["testing_days"], 2.4)

    def test_required_field_error(self):
        f = self.t.fields.get(slug="pages")
        f.required = True
        f.save()
        r = evaluate(self.t, {"inputs": 10})
        self.assertTrue(any("Pages" in e for e in r["errors"]))


class ScopingExpressionTests(TestCase):
    def test_expression_with_bucket(self):
        t = ScopingTemplate.objects.create(
            name="Infra VA", calc_mode=CalcMode.EXPRESSION,
            testing_expression="bucket(ips, [50, 100, 1000], [1, 2, 5])",
            reporting_expression="ceil(testing_days / 4)",
        )
        ScopingField.objects.create(
            template=t, label="Live IPs", slug="ips",
            field_type=ScopingFieldType.NUMBER,
        )
        r = evaluate(t, {"ips": 75})
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["testing_days"], 2.0)
        self.assertEqual(r["reporting_days"], 1.0)

    def test_reporting_macro_precedence(self):
        macro = ScopingMacro.objects.create(
            name="Reporting Days", expression="ceil(testing_days / 2)"
        )
        t = ScopingTemplate.objects.create(
            name="With Macro", calc_mode=CalcMode.EXPRESSION,
            testing_expression="days", reporting_macro=macro,
            reporting_expression="testing_days / 99",  # should be ignored
        )
        ScopingField.objects.create(
            template=t, label="Days", slug="days", field_type=ScopingFieldType.NUMBER
        )
        r = evaluate(t, {"days": 5})
        self.assertEqual(r["testing_days"], 5.0)
        self.assertEqual(r["reporting_days"], 3.0)  # ceil(5/2) via macro, not 5/99

    def test_sandbox_rejects_dangerous_expression(self):
        t = ScopingTemplate.objects.create(
            name="Evil", calc_mode=CalcMode.EXPRESSION,
            testing_expression="__import__('os').system('echo hi')",
        )
        r = evaluate(t, {})
        # Must not raise; must surface an error and compute nothing.
        self.assertTrue(r["errors"])
        self.assertEqual(r["testing_days"], 0.0)

    def test_missing_expression_errors(self):
        t = ScopingTemplate.objects.create(
            name="Empty", calc_mode=CalcMode.EXPRESSION, testing_expression=""
        )
        r = evaluate(t, {})
        self.assertTrue(r["errors"])


class ScopingImportExportTests(TestCase):
    def _make_template(self):
        macro = ScopingMacro.objects.create(
            name="Rep Days", expression="ceil(testing_days / 4)"
        )
        t = ScopingTemplate.objects.create(
            name="Firewall Review", calc_mode=CalcMode.EXPRESSION,
            testing_expression="rules / 100", reporting_macro=macro,
        )
        ScopingField.objects.create(
            template=t, label="Rules", slug="rules",
            field_type=ScopingFieldType.NUMBER, required=True,
        )
        ScopingField.objects.create(
            template=t, label="Type", slug="fwtype",
            field_type=ScopingFieldType.SELECT,
            calc_role=ScopingCalcRole.NONE,
            options=[{"value": "cisco", "label": "Cisco", "weight": 0}],
        )
        return t

    def test_export_import_roundtrip(self):
        t = self._make_template()
        pack = build_pack([t])
        self.assertEqual(pack["chaotica_scoping_pack"], 1)
        self.assertEqual(len(pack["templates"]), 1)
        self.assertEqual(len(pack["macros"]), 1)

        # wipe and reimport
        ScopingTemplate.objects.all().delete()
        ScopingMacro.objects.all().delete()

        import_pack(pack)
        self.assertEqual(ScopingTemplate.objects.count(), 1)
        new_t = ScopingTemplate.objects.get(slug="firewall-review")
        self.assertEqual(new_t.fields.count(), 2)
        self.assertIsNotNone(new_t.reporting_macro)
        self.assertEqual(new_t.reporting_macro.expression, "ceil(testing_days / 4)")
        self.assertEqual(new_t.fields.get(slug="rules").required, True)

    def test_import_skips_existing_without_overwrite(self):
        t = self._make_template()
        pack = build_pack([t])
        report = import_pack(pack, overwrite=False)
        self.assertTrue(any("already exists" in line for line in report))
        self.assertEqual(ScopingTemplate.objects.count(), 1)

    def test_import_rejects_bad_pack(self):
        with self.assertRaises(ValueError):
            import_pack({"not": "a pack"})

    def test_reimport_overwrite_preserves_shared_macro_links(self):
        # Two templates sharing one macro; re-importing with overwrite must not
        # orphan the first template's macro FK (regression: delete+recreate -> SET_NULL).
        macro = ScopingMacro.objects.create(name="Rep", expression="ceil(testing_days/4)")
        for n in ("Alpha", "Beta"):
            t = ScopingTemplate.objects.create(
                name=n, calc_mode=CalcMode.EXPRESSION,
                testing_expression="1", reporting_macro=macro,
            )
            ScopingField.objects.create(template=t, label="X", slug="x")
        pack = build_pack(list(ScopingTemplate.objects.all()))

        import_pack(pack, overwrite=True)
        import_pack(pack, overwrite=True)  # twice, to be sure

        for slug in ("alpha", "beta"):
            self.assertIsNotNone(
                ScopingTemplate.objects.get(slug=slug).reporting_macro,
                "macro link lost for {}".format(slug),
            )
        self.assertEqual(ScopingMacro.objects.filter(slug="rep").count(), 1)

    def test_reimport_overwrite_preserves_service_link(self):
        t = self._make_template()
        svc = Service.objects.create(name="Attached", scoping_template=t)
        pack = build_pack([t])
        import_pack(pack, overwrite=True)
        svc.refresh_from_db()
        self.assertIsNotNone(svc.scoping_template)
        self.assertEqual(svc.scoping_template.slug, "firewall-review")


class ScopingViewTests(TestCase):
    """Smoke-test the management UI renders and the calc endpoint responds."""

    def setUp(self):
        self.client = Client(HTTP_HOST="localhost")
        self.admin = User.objects.create_superuser(
            email="admin@test.com", password="testpass123"
        )
        self.client.force_login(self.admin)
        self.t = ScopingTemplate.objects.create(
            name="Web App", calc_mode=CalcMode.DECLARATIVE,
            reporting_expression="testing_days / 4",
        )
        ScopingField.objects.create(
            template=self.t, label="Pages", slug="pages",
            field_type=ScopingFieldType.NUMBER,
            calc_role=ScopingCalcRole.SIZING, rate=Decimal("15"),
        )

    def test_list_renders(self):
        resp = self.client.get(reverse("scoping_template_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Web App")

    def test_create_renders(self):
        self.assertEqual(self.client.get(reverse("scoping_template_create")).status_code, 200)

    def test_edit_renders_with_test_panel(self):
        resp = self.client.get(reverse("scoping_template_edit", args=[self.t.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Test this template")

    def test_macro_pages_render(self):
        self.assertEqual(self.client.get(reverse("scoping_macro_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("scoping_macro_create")).status_code, 200)

    def test_import_page_renders(self):
        self.assertEqual(self.client.get(reverse("scoping_import")).status_code, 200)

    def test_calc_endpoint(self):
        resp = self.client.post(
            reverse("scoping_template_calc", args=[self.t.slug]),
            data=json.dumps({"answers": {"pages": 30}}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["testing_days"], 2.0)

    def test_export_endpoint(self):
        resp = self.client.get(reverse("scoping_template_export", args=[self.t.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attachment", resp["Content-Disposition"])
        self.assertEqual(json.loads(resp.content)["chaotica_scoping_pack"], 1)

    def test_requires_permission(self):
        plain = User.objects.create_user(email="plain@test.com", password="x")
        c = Client(HTTP_HOST="localhost")
        c.force_login(plain)
        self.assertEqual(c.get(reverse("scoping_template_list")).status_code, 403)


class ServiceScopingDetailTests(TestCase):
    """Per-service scoping from the Service detail page."""

    def setUp(self):
        self.client = Client(HTTP_HOST="localhost")
        self.admin = User.objects.create_superuser(
            email="admin@test.com", password="testpass123"
        )
        self.client.force_login(self.admin)
        self.service = Service.objects.create(name="Internal Infrastructure")
        self.template = ScopingTemplate.objects.create(name="Infra Template")

    def test_detail_shows_scoping_tab(self):
        resp = self.client.get(reverse("service_detail", args=[self.service.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Scoping")
        self.assertContains(resp, "No scoping template is attached")

    def test_attach_template(self):
        self.client.post(
            reverse("service_scoping_update", args=[self.service.slug]),
            {"action": "attach", "template": self.template.pk},
        )
        self.service.refresh_from_db()
        self.assertEqual(self.service.scoping_template, self.template)

    def test_detach_template(self):
        self.service.scoping_template = self.template
        self.service.save()
        self.client.post(
            reverse("service_scoping_update", args=[self.service.slug]),
            {"action": "detach"},
        )
        self.service.refresh_from_db()
        self.assertIsNone(self.service.scoping_template)

    def test_create_template_for_service(self):
        resp = self.client.post(
            reverse("service_scoping_update", args=[self.service.slug]),
            {"action": "create"},
        )
        self.service.refresh_from_db()
        self.assertIsNotNone(self.service.scoping_template)
        self.assertIn("Internal Infrastructure", self.service.scoping_template.name)
        self.assertEqual(resp.status_code, 302)  # redirects to builder

    def test_update_requires_permission(self):
        plain = User.objects.create_user(email="plain@test.com", password="x")
        c = Client(HTTP_HOST="localhost")
        c.force_login(plain)
        resp = c.post(
            reverse("service_scoping_update", args=[self.service.slug]),
            {"action": "detach"},
        )
        self.assertEqual(resp.status_code, 403)


class ServiceScopingLinkTests(TestCase):
    def test_service_template_fk(self):
        t = ScopingTemplate.objects.create(name="Linked")
        s = Service.objects.create(name="Linked Service", scoping_template=t)
        self.assertEqual(s.scoping_template, t)
        self.assertIn(s, t.services.all())

    def test_template_delete_sets_null(self):
        t = ScopingTemplate.objects.create(name="Temp")
        s = Service.objects.create(name="Svc", scoping_template=t)
        t.delete()
        s.refresh_from_db()
        self.assertIsNone(s.scoping_template)
