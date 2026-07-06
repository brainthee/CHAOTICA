from django.test import Client, TestCase
from django.urls import reverse

from chaotica_utils.models import User
from jobtracker.models import AwardingBody, Qualification
from jobtracker.models.skill import Skill, SkillCategory


class QualificationSkillModelTests(TestCase):
    """Qualification.demonstrated_skills M2M and its reverse accessor."""

    def setUp(self):
        self.body = AwardingBody.objects.create(name="Offensive Security")
        self.qual = Qualification.objects.create(
            awarding_body=self.body, name="Certified Professional", short_name="OSCP"
        )
        self.category = SkillCategory.objects.create(name="Infrastructure")
        self.skill_a = Skill.objects.create(name="External Infra", category=self.category)
        self.skill_b = Skill.objects.create(name="Internal Infra", category=self.category)

    def test_assign_demonstrated_skills(self):
        self.qual.demonstrated_skills.add(self.skill_a, self.skill_b)
        self.assertEqual(self.qual.demonstrated_skills.count(), 2)
        self.assertIn(self.skill_a, self.qual.demonstrated_skills.all())

    def test_reverse_accessor(self):
        self.qual.demonstrated_skills.add(self.skill_a)
        # skill.qualifications is the reverse of Qualification.demonstrated_skills
        self.assertIn(self.qual, self.skill_a.qualifications.all())
        self.assertNotIn(self.qual, self.skill_b.qualifications.all())

    def test_default_empty(self):
        self.assertEqual(self.qual.demonstrated_skills.count(), 0)
        self.assertEqual(self.skill_a.qualifications.count(), 0)


class QualificationSkillRenderTests(TestCase):
    """Smoke tests that the new detail blocks render."""

    def setUp(self):
        # The project's custom SessionMiddleware rejects requests with no Host
        # header, so give the test client an explicit host (matches ALLOWED_HOSTS).
        self.client = Client(HTTP_HOST="web")
        self.superuser = User.objects.create_superuser(
            email="admin@test.com", password="testpass123"
        )
        self.client.force_login(self.superuser)

        self.body = AwardingBody.objects.create(name="Offensive Security")
        self.qual = Qualification.objects.create(
            awarding_body=self.body, name="Certified Professional", short_name="OSCP"
        )
        self.category = SkillCategory.objects.create(name="Infrastructure")
        self.skill = Skill.objects.create(name="External Infra", category=self.category)
        self.qual.demonstrated_skills.add(self.skill)

    def test_qualification_detail_shows_skills_block(self):
        url = reverse(
            "qualification_detail",
            kwargs={"bodySlug": self.body.slug, "slug": self.qual.slug},
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Skills Demonstrated")
        self.assertContains(resp, self.skill.name)

    def test_skill_detail_shows_qualifications_block(self):
        url = reverse("skill_detail", kwargs={"slug": self.skill.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Evidenced By")
        self.assertContains(resp, str(self.qual))
