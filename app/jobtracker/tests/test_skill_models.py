from django.test import TestCase
from django.db import IntegrityError

from chaotica_utils.models import User
from jobtracker.models.skill import SkillCategory, Skill, UserSkill
from jobtracker.enums import UserSkillRatings


class SkillCategoryModelTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            email="s1@example.com", password="testpass123"
        )
        self.user2 = User.objects.create_user(
            email="s2@example.com", password="testpass123"
        )
        self.user3 = User.objects.create_user(
            email="s3@example.com", password="testpass123"
        )

    def test_creation_and_slug(self):
        cat = SkillCategory.objects.create(name="Web Testing")
        self.assertIsNotNone(cat.pk)
        self.assertTrue(cat.slug)

    def test_str(self):
        cat = SkillCategory.objects.create(name="Network Testing")
        self.assertEqual(str(cat), "Network Testing")

    def test_get_absolute_url(self):
        cat = SkillCategory.objects.create(name="Mobile Testing")
        url = cat.get_absolute_url()
        self.assertIn(cat.slug, url)

    def test_get_users_breakdown_perc_empty(self):
        cat = SkillCategory.objects.create(name="Empty Category")
        data = cat.get_users_breakdown_perc()
        self.assertEqual(data["total_users"], 0)
        self.assertEqual(data["can_do_alone_perc"], 0)
        self.assertEqual(data["can_do_with_support_perc"], 0)
        self.assertEqual(data["specialist_perc"], 0)

    def test_get_users_breakdown_perc_with_data(self):
        cat = SkillCategory.objects.create(name="Perc Category")
        skill = Skill.objects.create(name="Perc Skill", category=cat)
        UserSkill.objects.create(
            user=self.user1, skill=skill, rating=UserSkillRatings.CAN_DO_ALONE
        )
        UserSkill.objects.create(
            user=self.user2, skill=skill, rating=UserSkillRatings.SPECIALIST
        )
        data = cat.get_users_breakdown_perc()
        self.assertEqual(data["total_users"], 2)
        self.assertGreater(data["can_do_alone_perc"], 0)
        self.assertGreater(data["specialist_perc"], 0)


class SkillModelTests(TestCase):
    def setUp(self):
        self.category = SkillCategory.objects.create(name="Security")
        self.user1 = User.objects.create_user(
            email="su1@example.com", password="testpass123"
        )
        self.user2 = User.objects.create_user(
            email="su2@example.com", password="testpass123"
        )
        self.user3 = User.objects.create_user(
            email="su3@example.com", password="testpass123"
        )

    def test_creation_and_slug(self):
        skill = Skill.objects.create(name="Pen Testing", category=self.category)
        self.assertTrue(skill.slug)
        # Slug should be based on "category-name"
        self.assertIn("security", skill.slug.lower())

    def test_str(self):
        skill = Skill.objects.create(name="Code Review", category=self.category)
        self.assertEqual(str(skill), f"{self.category} - Code Review")

    def test_unique_together(self):
        Skill.objects.create(name="UniqueSkill", category=self.category)
        with self.assertRaises(IntegrityError):
            Skill.objects.create(name="UniqueSkill", category=self.category)

    def test_get_absolute_url(self):
        skill = Skill.objects.create(name="URL Skill", category=self.category)
        url = skill.get_absolute_url()
        self.assertIn(skill.slug, url)

    def test_get_rating_counts_empty(self):
        skill = Skill.objects.create(name="Empty Skill", category=self.category)
        counts = skill.get_rating_counts()
        self.assertEqual(len(counts), 0)

    def test_get_rating_counts_with_data(self):
        skill = Skill.objects.create(name="Counted Skill", category=self.category)
        UserSkill.objects.create(
            user=self.user1, skill=skill, rating=UserSkillRatings.CAN_DO_ALONE
        )
        UserSkill.objects.create(
            user=self.user2, skill=skill, rating=UserSkillRatings.CAN_DO_ALONE
        )
        UserSkill.objects.create(
            user=self.user3, skill=skill, rating=UserSkillRatings.SPECIALIST
        )
        counts = skill.get_rating_counts()
        self.assertEqual(counts[UserSkillRatings.CAN_DO_ALONE], 2)
        self.assertEqual(counts[UserSkillRatings.SPECIALIST], 1)

    def test_get_users_breakdown_perc_empty(self):
        skill = Skill.objects.create(name="NoUsers Skill", category=self.category)
        data = skill.get_users_breakdown_perc()
        self.assertEqual(data["total_users"], 0)
        self.assertEqual(data["can_do_alone_perc"], 0)
        self.assertEqual(data["can_do_with_support_perc"], 0)
        self.assertEqual(data["specialist_perc"], 0)

    def test_get_users_breakdown_perc_with_data(self):
        skill = Skill.objects.create(name="PercData Skill", category=self.category)
        UserSkill.objects.create(
            user=self.user1, skill=skill, rating=UserSkillRatings.CAN_DO_ALONE
        )
        UserSkill.objects.create(
            user=self.user2, skill=skill, rating=UserSkillRatings.SPECIALIST
        )
        data = skill.get_users_breakdown_perc()
        self.assertEqual(data["total_users"], 2)
        self.assertEqual(data["can_do_alone"], 1)
        self.assertEqual(data["specialist"], 1)
        self.assertEqual(data["can_do_alone_perc"], 50.0)
        self.assertEqual(data["specialist_perc"], 50.0)

    def test_get_users_can_do_alone(self):
        skill = Skill.objects.create(name="Alone Skill", category=self.category)
        UserSkill.objects.create(
            user=self.user1, skill=skill, rating=UserSkillRatings.CAN_DO_ALONE
        )
        UserSkill.objects.create(
            user=self.user2, skill=skill, rating=UserSkillRatings.NO_EXPERIENCE
        )
        qs = skill.get_users_can_do_alone()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().user, self.user1)

    def test_get_users_can_do_with_support(self):
        skill = Skill.objects.create(name="Support Skill", category=self.category)
        UserSkill.objects.create(
            user=self.user1, skill=skill, rating=UserSkillRatings.CAN_DO_WITH_SUPPORT
        )
        qs = skill.get_users_can_do_with_support()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().user, self.user1)

    def test_get_users_specialist(self):
        skill = Skill.objects.create(name="Spec Skill", category=self.category)
        UserSkill.objects.create(
            user=self.user1, skill=skill, rating=UserSkillRatings.SPECIALIST
        )
        qs = skill.get_users_specialist()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().user, self.user1)

    def test_get_users_excludes_no_experience(self):
        skill = Skill.objects.create(name="Exclude Skill", category=self.category)
        UserSkill.objects.create(
            user=self.user1, skill=skill, rating=UserSkillRatings.NO_EXPERIENCE
        )
        qs = skill.get_users()
        self.assertEqual(qs.count(), 0)

    def test_get_learning_path_no_prereqs(self):
        skill = Skill.objects.create(name="NoPrereq Skill", category=self.category)
        path = skill.get_learning_path()
        self.assertEqual(path, [])

    def test_get_learning_path_linear(self):
        a = Skill.objects.create(name="LP A", category=self.category)
        b = Skill.objects.create(name="LP B", category=self.category)
        c = Skill.objects.create(name="LP C", category=self.category)
        b.prerequisites.add(a)
        c.prerequisites.add(b)
        path = c.get_learning_path()
        self.assertEqual(path, [a, b])

    def test_get_learning_path_cycle_detection(self):
        a = Skill.objects.create(name="Cycle A", category=self.category)
        b = Skill.objects.create(name="Cycle B", category=self.category)
        a.prerequisites.add(b)
        b.prerequisites.add(a)
        # Should not infinite loop; just verify it returns without error
        path = a.get_learning_path()
        self.assertIsInstance(path, list)

    def test_can_learn_now_no_prereqs(self):
        skill = Skill.objects.create(name="NoReq Skill", category=self.category)
        self.assertTrue(skill.can_learn_now(self.user1))

    def test_can_learn_now_met(self):
        prereq = Skill.objects.create(name="Prereq Met", category=self.category)
        skill = Skill.objects.create(name="Main Met", category=self.category)
        skill.prerequisites.add(prereq)
        # User has the prerequisite skill (any rating creates the record)
        UserSkill.objects.create(
            user=self.user1, skill=prereq, rating=UserSkillRatings.CAN_DO_ALONE
        )
        self.assertTrue(skill.can_learn_now(self.user1))

    def test_can_learn_now_not_met(self):
        prereq = Skill.objects.create(name="Prereq Unmet", category=self.category)
        skill = Skill.objects.create(name="Main Unmet", category=self.category)
        skill.prerequisites.add(prereq)
        # User does NOT have the prerequisite
        self.assertFalse(skill.can_learn_now(self.user1))

    def test_get_next_skills(self):
        a = Skill.objects.create(name="Next A", category=self.category)
        b = Skill.objects.create(name="Next B", category=self.category)
        b.prerequisites.add(a)
        next_skills = a.get_next_skills()
        self.assertIn(b, next_skills)


class UserSkillModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="us@example.com", password="testpass123"
        )
        self.category = SkillCategory.objects.create(name="US Category")
        self.skill = Skill.objects.create(name="US Skill", category=self.category)

    def test_creation(self):
        us = UserSkill.objects.create(user=self.user, skill=self.skill)
        self.assertIsNotNone(us.pk)

    def test_unique_together(self):
        UserSkill.objects.create(user=self.user, skill=self.skill)
        with self.assertRaises(IntegrityError):
            UserSkill.objects.create(user=self.user, skill=self.skill)

    def test_default_rating(self):
        us = UserSkill.objects.create(user=self.user, skill=self.skill)
        self.assertEqual(us.rating, UserSkillRatings.NO_EXPERIENCE)
