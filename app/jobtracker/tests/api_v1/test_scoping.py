"""/api/v1/ scoping templates + calculator (#557)."""

from decimal import Decimal

from jobtracker.models.scoping import (
    CalcMode,
    ScopingCalcRole,
    ScopingField,
    ScopingFieldType,
    ScopingTemplate,
    SizingCombine,
)

from .helpers import ApiV1TestCase


class ScopingApiBase(ApiV1TestCase):
    def setUp(self):
        super().setUp()
        self.template = ScopingTemplate.objects.create(
            name="Web App",
            calc_mode=CalcMode.DECLARATIVE,
            sizing_combine=SizingCombine.MAX,
            reporting_expression="testing_days / 4",
        )
        ScopingField.objects.create(
            template=self.template, label="Pages", slug="pages",
            field_type=ScopingFieldType.NUMBER,
            calc_role=ScopingCalcRole.SIZING, rate=Decimal("15"),
        )
        ScopingField.objects.create(
            template=self.template, label="Inputs", slug="inputs",
            field_type=ScopingFieldType.NUMBER,
            calc_role=ScopingCalcRole.SIZING, rate=Decimal("200"),
        )
        self.inactive = ScopingTemplate.objects.create(
            name="Retired", is_active=False
        )


class ScopingTemplateListTests(ScopingApiBase):
    def test_list_returns_active_with_fields(self):
        su = self.as_user(self.superuser)
        body = su.get("/api/v1/scoping-templates/").json()
        names = {row["name"] for row in body["results"]}
        self.assertIn("Web App", names)
        self.assertNotIn("Retired", names)  # inactive excluded

    def test_detail_includes_fields_and_options(self):
        su = self.as_user(self.superuser)
        body = su.get(f"/api/v1/scoping-templates/{self.template.pk}/").json()
        slugs = {f["slug"] for f in body["fields"]}
        self.assertEqual(slugs, {"pages", "inputs"})

    def test_requires_auth(self):
        resp = self.client.get("/api/v1/scoping-templates/")
        self.assertEqual(resp.status_code, 401)


class ScopingCalculateTests(ScopingApiBase):
    def test_calculate_by_id(self):
        su = self.as_user(self.superuser)
        resp = su.post(
            "/api/v1/scoping/calculate/",
            {"template": self.template.pk, "answers": {"pages": 30, "inputs": 200}},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        # pages 30/15 = 2, inputs 200/200 = 1 -> max 2 testing days
        self.assertEqual(data["testing_days"], 2.0)
        self.assertEqual(data["reporting_days"], 0.5)
        self.assertEqual(data["delivery_hours"], 15.0)

    def test_calculate_by_slug(self):
        su = self.as_user(self.superuser)
        resp = su.post(
            "/api/v1/scoping/calculate/",
            {"template": self.template.slug, "answers": {"pages": 45}},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["testing_days"], 3.0)

    def test_unknown_template_404(self):
        su = self.as_user(self.superuser)
        resp = su.post(
            "/api/v1/scoping/calculate/",
            {"template": "no-such-template", "answers": {}},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_requires_auth(self):
        resp = self.client.post(
            "/api/v1/scoping/calculate/",
            {"template": self.template.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)
