"""Qualification-driven skill suggestions, 'one-of' requirement groups, and the
accept/dismiss UI."""

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from chaotica_utils.models import User
from jobtracker.enums import QualificationStatus, UserSkillRatings
from jobtracker.models import (
    AwardingBody,
    Qualification,
    QualificationRecord,
    QualificationSkill,
    Service,
    ServiceSkillRequirementGroup,
    SkillRatingSuggestion,
    UserSkill,
)
from jobtracker.models.skill import Skill, SkillCategory


class SkillSuggestionSignalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="tester@example.com", password="pw")
        self.body = AwardingBody.objects.create(name="Offensive Security")
        self.qual = Qualification.objects.create(
            awarding_body=self.body, name="Certified Professional", short_name="OSCP"
        )
        self.cat = SkillCategory.objects.create(name="Infrastructure")
        self.skill = Skill.objects.create(name="Active Directory Security", category=self.cat)
        QualificationSkill.objects.create(
            qualification=self.qual,
            skill=self.skill,
            suggested_rating=UserSkillRatings.CAN_DO_ALONE,
        )

    def _award(self, user=None):
        return QualificationRecord.objects.create(
            user=user or self.user,
            qualification=self.qual,
            status=QualificationStatus.AWARDED,
        )

    def test_award_creates_pending_suggestion(self):
        self._award()
        s = SkillRatingSuggestion.objects.get(user=self.user, skill=self.skill)
        self.assertEqual(s.status, SkillRatingSuggestion.PENDING)
        self.assertEqual(s.suggested_rating, UserSkillRatings.CAN_DO_ALONE)
        self.assertEqual(s.source, SkillRatingSuggestion.SOURCE_QUALIFICATION)

    def test_non_awarded_status_creates_nothing(self):
        QualificationRecord.objects.create(
            user=self.user, qualification=self.qual, status=QualificationStatus.IN_PROGRESS
        )
        self.assertFalse(SkillRatingSuggestion.objects.filter(user=self.user).exists())

    def test_resave_does_not_duplicate(self):
        rec = self._award()
        rec.save()
        rec.save()
        self.assertEqual(
            SkillRatingSuggestion.objects.filter(user=self.user, skill=self.skill).count(), 1
        )

    def test_no_suggestion_when_already_higher(self):
        UserSkill.objects.create(
            user=self.user, skill=self.skill, rating=UserSkillRatings.SPECIALIST
        )
        self._award()
        self.assertFalse(SkillRatingSuggestion.objects.filter(user=self.user).exists())

    def test_verification_required_waits_for_verification(self):
        self.qual.verification_required = True
        self.qual.save(update_fields=["verification_required"])
        rec = self._award()
        self.assertFalse(SkillRatingSuggestion.objects.filter(user=self.user).exists())
        rec.verified_by = self.user
        rec.verified_on = timezone.now()
        rec.save()
        self.assertTrue(SkillRatingSuggestion.objects.filter(user=self.user).exists())

    def test_dismissal_is_respected_on_resave(self):
        rec = self._award()
        s = SkillRatingSuggestion.objects.get(user=self.user, skill=self.skill)
        s.dismiss()
        rec.save()
        self.assertEqual(
            SkillRatingSuggestion.objects.filter(user=self.user, skill=self.skill).count(), 1
        )


class SkillSuggestionAcceptTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="a@example.com", password="pw")
        self.cat = SkillCategory.objects.create(name="Web")
        self.skill = Skill.objects.create(name="Core Web Vulnerabilities", category=self.cat)

    def _suggestion(self, rating):
        return SkillRatingSuggestion.objects.create(
            user=self.user, skill=self.skill, suggested_rating=rating
        )

    def test_accept_creates_userskill(self):
        s = self._suggestion(UserSkillRatings.CAN_DO_ALONE)
        s.accept()
        us = UserSkill.objects.get(user=self.user, skill=self.skill)
        self.assertEqual(us.rating, UserSkillRatings.CAN_DO_ALONE)
        s.refresh_from_db()
        self.assertEqual(s.status, SkillRatingSuggestion.ACCEPTED)

    def test_accept_raises_but_never_lowers(self):
        UserSkill.objects.create(
            user=self.user, skill=self.skill, rating=UserSkillRatings.SPECIALIST
        )
        s = self._suggestion(UserSkillRatings.CAN_DO_ALONE)
        s.accept()
        us = UserSkill.objects.get(user=self.user, skill=self.skill)
        self.assertEqual(us.rating, UserSkillRatings.SPECIALIST)


class OneOfRequirementGroupTests(TestCase):
    def setUp(self):
        self.cat = SkillCategory.objects.create(name="Mobile")
        self.ios = Skill.objects.create(name="iOS Application Security", category=self.cat)
        self.android = Skill.objects.create(name="Android Application Security", category=self.cat)
        self.user = User.objects.create_user(email="m@example.com", password="pw")
        self.other = User.objects.create_user(email="n@example.com", password="pw")
        self.service = Service.objects.create(name="Mobile Assessment")
        self.group = ServiceSkillRequirementGroup.objects.create(
            service=self.service, name="Mobile platform"
        )
        self.group.skills.add(self.ios, self.android)

    def test_any_one_platform_satisfies(self):
        UserSkill.objects.create(
            user=self.user, skill=self.ios, rating=UserSkillRatings.CAN_DO_ALONE
        )
        self.service.clear_cache()
        self.assertIn(self.user, self.service.can_conduct())
        self.assertNotIn(self.other, self.service.can_conduct())

    def test_rating_tier_respected(self):
        UserSkill.objects.create(
            user=self.user, skill=self.android, rating=UserSkillRatings.CAN_DO_WITH_SUPPORT
        )
        self.service.clear_cache()
        # satisfies 'can_conduct' (support) but not 'can_lead' (independent)
        self.assertIn(self.user, self.service.can_conduct())
        self.assertNotIn(self.user, self.service.can_lead())


class SkillSuggestionViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="v@example.com", password="pw")
        self.cat = SkillCategory.objects.create(name="Cloud")
        self.skill = Skill.objects.create(name="Cloud Config Review", category=self.cat)
        self.s = SkillRatingSuggestion.objects.create(
            user=self.user, skill=self.skill, suggested_rating=UserSkillRatings.CAN_DO_ALONE
        )
        self.client = Client(HTTP_HOST="127.0.0.1:8000")
        self.client.force_login(self.user)

    def test_list_renders(self):
        r = self.client.get(reverse("view_own_skill_suggestions"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Cloud Config Review")

    def test_accept_endpoint(self):
        r = self.client.post(reverse("accept_skill_suggestion", args=[self.s.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(UserSkill.objects.filter(user=self.user, skill=self.skill).exists())
        self.s.refresh_from_db()
        self.assertEqual(self.s.status, SkillRatingSuggestion.ACCEPTED)

    def test_dismiss_endpoint(self):
        r = self.client.post(reverse("dismiss_skill_suggestion", args=[self.s.pk]))
        self.assertEqual(r.status_code, 302)
        self.s.refresh_from_db()
        self.assertEqual(self.s.status, SkillRatingSuggestion.DISMISSED)
        self.assertFalse(UserSkill.objects.filter(user=self.user, skill=self.skill).exists())

    def test_cannot_touch_another_users_suggestion(self):
        intruder = User.objects.create_user(email="x@example.com", password="pw")
        c = Client(HTTP_HOST="127.0.0.1:8000")
        c.force_login(intruder)
        r = c.post(reverse("accept_skill_suggestion", args=[self.s.pk]))
        self.assertEqual(r.status_code, 404)
