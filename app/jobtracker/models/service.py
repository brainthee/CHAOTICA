from django.db import models
from ..enums import JobStatuses, PhaseStatuses, FeedbackType, LinkType, UserSkillRatings
from ..models.skill import Skill, UserSkill
from ..models.phase import Phase
from django.conf import settings
from django.db.models import Q
from chaotica_utils.utils import unique_slug_generator
from django.urls import reverse
from simple_history.models import HistoricalRecords
from django.db.models import JSONField
from django_bleach.models import BleachField
from django.db.models.functions import Lower
from chaotica_utils.models import User


class Service(models.Model):
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(null=False, default="", unique=True)
    owners = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, limit_choices_to={"is_active": True},
        help_text="Users responsible for the management of the service."
    )
    history = HistoricalRecords()

    description = BleachField(
        blank=True,
        null=True,
        help_text="Description of service",
    )

    link = models.URLField(
        max_length=2000,
        default="",
        null=True,
        blank=True,
        help_text="Link to service information",
    )

    skillsRequired = models.ManyToManyField(
        Skill, blank=True, related_name="services_skill_required",
        help_text="Skills required to perform this service",
    )
    skillsDesired = models.ManyToManyField(
        Skill, blank=True, related_name="services_skill_desired",
        help_text="Skills desired but not essential",
    )
    is_core = models.BooleanField(
        "Is Core Service", help_text="If checked, this service is considered critical",
        default=False
    )
    data = JSONField(verbose_name="Data", null=True, blank=True, default=dict)

    class Meta:
        ordering = [Lower("name")]
        permissions = (("assign_to_phase", "Assign To Phase"),)

    def __str__(self):
        return self.name

    def can_conduct(self):
        # Return users who have a userskill
        return User.objects.filter(
            skills__in=UserSkill.objects.filter(
                Q(rating=UserSkillRatings.CAN_DO_WITH_SUPPORT),
                skill__in=self.skillsRequired.all(),
            )
        )

    def can_lead(self):
        # Return users who have a userskill
        return User.objects.filter(
            skills__in=UserSkill.objects.filter(
                Q(rating=UserSkillRatings.SPECIALIST)
                | Q(rating=UserSkillRatings.CAN_DO_ALONE), 
                skill__in=self.skillsRequired.all(),
            )
        )

    def get_absolute_url(self):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
            self.save()
        return reverse("service_detail", kwargs={"slug": self.slug})

    def get_users_specialist(self):
        """Get users who are specialists in ALL required skills"""
        required_skills = self.skillsRequired.all()
        if not required_skills:
            return User.objects.none()

        users_with_all_specialist = []
        for user in User.objects.filter(skills__skill__in=required_skills).distinct():
            user_skills = UserSkill.objects.filter(user=user, skill__in=required_skills)
            if (user_skills.count() == required_skills.count() and
                user_skills.filter(rating=UserSkillRatings.SPECIALIST).count() == required_skills.count()):
                users_with_all_specialist.append(user.id)

        return User.objects.filter(id__in=users_with_all_specialist)

    def get_users_can_do_alone(self):
        """Get users who can do the service independently (all skills at CAN_DO_ALONE or higher)"""
        required_skills = self.skillsRequired.all()
        if not required_skills:
            return User.objects.none()

        users_can_do_alone = []
        for user in User.objects.filter(skills__skill__in=required_skills).distinct():
            user_skills = UserSkill.objects.filter(user=user, skill__in=required_skills)
            if (user_skills.count() == required_skills.count() and
                user_skills.filter(rating__in=[UserSkillRatings.SPECIALIST, UserSkillRatings.CAN_DO_ALONE]).count() == required_skills.count()):
                users_can_do_alone.append(user.id)

        return User.objects.filter(id__in=users_can_do_alone)

    def get_users_can_do_with_support(self):
        """Get users who have ALL required skills but need support in at least one"""
        required_skills = self.skillsRequired.all()
        if not required_skills:
            return User.objects.none()

        users_need_support = []
        for user in User.objects.filter(skills__skill__in=required_skills).distinct():
            user_skills = UserSkill.objects.filter(user=user, skill__in=required_skills)
            if user_skills.count() == required_skills.count():
                # Has all required skills, check if any need support
                if user_skills.filter(rating=UserSkillRatings.CAN_DO_WITH_SUPPORT).exists():
                    users_need_support.append(user.id)

        return User.objects.filter(id__in=users_need_support)

    def get_users_missing_skills(self):
        """Get users who have some but not all required skills"""
        required_skills = self.skillsRequired.all()
        if not required_skills:
            return User.objects.none()

        users_with_partial_skills = []
        for user in User.objects.filter(skills__skill__in=required_skills).distinct():
            user_skills = UserSkill.objects.filter(user=user, skill__in=required_skills)
            if user_skills.count() < required_skills.count():
                users_with_partial_skills.append(user.id)

        return User.objects.filter(id__in=users_with_partial_skills)

    def get_service_readiness_breakdown(self):
        """Get comprehensive breakdown of service readiness including desired skills"""
        required_skills = self.skillsRequired.all()
        desired_skills = self.skillsDesired.all()

        if not required_skills:
            return {
                'specialists': User.objects.none(),
                'independent_only': User.objects.none(),
                'support_only': User.objects.none(),
                'missing_skills': User.objects.none(),
                'total_capable': 0,
                'desired_skills_analysis': {}
            }

        specialists = self.get_users_specialist()
        independent = self.get_users_can_do_alone()
        need_support = self.get_users_can_do_with_support()
        missing_skills = self.get_users_missing_skills()

        # Remove specialists from independent count (they're already counted as specialists)
        independent_only = independent.exclude(id__in=specialists.values_list('id', flat=True))
        # Remove specialists and independent from support count
        support_only = need_support.exclude(id__in=specialists.values_list('id', flat=True)).exclude(id__in=independent.values_list('id', flat=True))

        # Analyze desired skills for capable users
        capable_users = specialists.union(independent_only, support_only)
        desired_skills_analysis = {}

        for skill in desired_skills:
            users_with_skill = capable_users.filter(
                skills__skill=skill
            ).distinct()

            skill_breakdown = {
                'total_with_skill': users_with_skill.count(),
                'specialists': users_with_skill.filter(
                    skills__skill=skill,
                    skills__rating=UserSkillRatings.SPECIALIST
                ),
                'independent': users_with_skill.filter(
                    skills__skill=skill,
                    skills__rating=UserSkillRatings.CAN_DO_ALONE
                ),
                'support_needed': users_with_skill.filter(
                    skills__skill=skill,
                    skills__rating=UserSkillRatings.CAN_DO_WITH_SUPPORT
                ),
                'coverage_percentage': round((users_with_skill.count() / capable_users.count() * 100), 1) if capable_users.count() > 0 else 0
            }
            desired_skills_analysis[skill] = skill_breakdown

        return {
            'specialists': specialists,
            'independent_only': independent_only,
            'support_only': support_only,
            'missing_skills': missing_skills,
            'total_capable': specialists.count() + independent_only.count() + support_only.count(),
            'desired_skills_analysis': desired_skills_analysis
        }

    def get_team_by_skill(self):
        """Get team members grouped by skill and competency level"""
        team_data = {}
        for skill in self.skillsRequired.all():
            team_data[skill] = {
                'specialists': UserSkill.objects.filter(
                    skill=skill,
                    rating=UserSkillRatings.SPECIALIST
                ).select_related('user'),
                'independent': UserSkill.objects.filter(
                    skill=skill,
                    rating=UserSkillRatings.CAN_DO_ALONE
                ).select_related('user'),
                'support_needed': UserSkill.objects.filter(
                    skill=skill,
                    rating=UserSkillRatings.CAN_DO_WITH_SUPPORT
                ).select_related('user'),
            }
        return team_data

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
        return super().save(*args, **kwargs)