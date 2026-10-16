"""Skills, services and qualifications (A7)."""

from datetime import date

from django.contrib.auth.models import Permission
from django.urls import reverse

from chaotica_utils.models import User
from jobtracker.enums import QualificationStatus, UserSkillRatings
from jobtracker.models import (
    AwardingBody,
    Qualification,
    QualificationRecord,
    Service,
    Skill,
    SkillCategory,
    UserSkill,
)

from .helpers import ApiV1TestCase


class CatalogueBase(ApiV1TestCase):
    def setUp(self):
        super().setUp()
        self.cat = SkillCategory.objects.create(name="Web")
        self.skill = Skill.objects.create(name="XSS", category=self.cat)
        self.service = Service.objects.create(name="Web App Test")
        self.service.skillsRequired.add(self.skill)
        self.boss = User.objects.create_user(email="boss@example.com", password="pw")
        self.report = User.objects.create_user(email="rep@example.com", password="pw")
        self.report.manager = self.boss
        self.report.save()
        self.other = User.objects.create_user(email="oth@example.com", password="pw")
        UserSkill.objects.create(
            user=self.report, skill=self.skill, rating=UserSkillRatings.SPECIALIST
        )
        UserSkill.objects.create(
            user=self.other, skill=self.skill, rating=UserSkillRatings.CAN_DO_ALONE
        )
        self.su = self.as_user(self.superuser)


class SkillTests(CatalogueBase):
    def test_detail(self):
        body = self.su.get(f"/api/v1/skills/{self.skill.pk}/").json()
        self.assertEqual(
            [s["id"] for s in body["services_required"]], [self.service.pk]
        )
        self.assertEqual(body["rating_counts"][str(UserSkillRatings.SPECIALIST)], 1)

    def test_users_scoped_like_user_skills(self):
        boss = User.objects.get(pk=self.boss.pk)
        boss.user_permissions.add(Permission.objects.get(codename="view_skill"))
        boss = User.objects.get(pk=self.boss.pk)
        rows = self.as_user(boss).get(f"/api/v1/skills/{self.skill.pk}/users/").json()
        self.assertEqual([r["user"]["id"] for r in rows["results"]], [self.report.pk])
        rows = self.su.get(f"/api/v1/skills/{self.skill.pk}/users/").json()
        self.assertEqual(rows["count"], 2)

    def test_matrix(self):
        body = self.su.get("/api/v1/skills/matrix/").json()
        self.assertEqual(body["categories"][0]["skills"][0]["id"], self.skill.pk)
        # Only users holding a global role appear (as on the page).
        self.assertIn("rating_choices", body)
        self.assertIn("all_units", body["filters"])

    def test_page_still_renders(self):
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(reverse("skill_matrix")).status_code, 200)
        resp = self.client.get(self.skill.get_absolute_url())
        self.assertEqual(resp.status_code, 200)


class ServiceTests(CatalogueBase):
    def test_list_has_risk(self):
        row = self.su.get("/api/v1/services/").json()["results"][0]
        self.assertEqual(row["specialist_count"], 1)
        self.assertEqual(row["risk_score"], 1)

    def test_coverage_names_only_with_permission(self):
        body = self.su.get(f"/api/v1/services/{self.service.pk}/coverage/").json()
        self.assertEqual(body["counts"]["specialists"], 1)
        self.assertEqual(body["people"]["specialists"][0]["id"], self.report.pk)
        self.assertEqual(body["required_skills"][0]["skill"]["id"], self.skill.pk)

    def test_metrics_and_phases(self):
        job = self.make_job()
        phase = self.make_phase(job, service=self.service)
        body = self.su.get(f"/api/v1/services/{self.service.pk}/metrics/").json()
        self.assertIn("performance", body)
        self.assertEqual(body["usage"]["total_phases"], 1)
        phases = self.su.get(f"/api/v1/services/{self.service.pk}/phases/").json()
        self.assertEqual([p["id"] for p in phases["results"]], [phase.pk])
        self.assertEqual(
            self.su.get(
                f"/api/v1/services/{self.service.pk}/phases/?bucket=x"
            ).status_code,
            400,
        )

    def test_page_metrics_scoped_to_visible_phases(self):
        """The Performance tab listed clients/hours of every phase."""
        job = self.make_job()
        self.make_phase(job, service=self.service)
        visible = self.service.phases.none()
        metrics = self.service.get_performance_metrics(phases=visible, cache_scope="t")
        self.assertEqual(metrics["quality_metrics"]["total_completed"], 0)
        self.client.force_login(self.superuser)
        self.assertEqual(
            self.client.get(self.service.get_absolute_url()).status_code, 200
        )


class QualificationTests(CatalogueBase):
    def test_detail_and_records(self):
        body_ = AwardingBody.objects.create(name="OffSec")
        qual = Qualification.objects.create(name="OSCP", awarding_body=body_)
        QualificationRecord.objects.create(
            qualification=qual,
            user=self.report,
            status=QualificationStatus.AWARDED,
            awarded_date=date(2025, 1, 1),
        )
        QualificationRecord.objects.create(
            qualification=qual, user=self.other, status=QualificationStatus.LAPSED
        )
        body = self.su.get(f"/api/v1/qualifications/{qual.pk}/").json()
        self.assertEqual(body["record_counts"]["awarded"], 1)
        self.assertEqual(body["record_counts"]["lapsed"], 1)
        boss_records = self.as_user(self.boss).get(
            f"/api/v1/qualifications/{qual.pk}/records/"
        )
        # boss lacks view_qualification -> the qualification itself is hidden
        self.assertEqual(boss_records.status_code, 404)
        self.assertEqual(
            self.su.get(f"/api/v1/qualifications/{qual.pk}/records/").json()["count"], 2
        )
        bodies = self.su.get("/api/v1/awarding-bodies/").json()["results"]
        self.assertEqual([b["name"] for b in bodies], ["OffSec"])
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(qual.get_absolute_url()).status_code, 200)
