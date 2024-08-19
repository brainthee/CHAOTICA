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
    data = JSONField(verbose_name="Data", null=True, blank=True, default=dict)

    class Meta:
        ordering = [Lower("name")]
        permissions = (("assign_to_phase", "Assign To Phase"),)

    def __str__(self):
        return self.name

    def users_can_conduct(self):
        # Return users who have a userskill
        return User.objects.filter(
            skills__in=UserSkill.objects.filter(
                Q(rating=UserSkillRatings.CAN_DO_ALONE)
                | Q(rating=UserSkillRatings.CAN_DO_WITH_SUPPORT)
                | Q(rating=UserSkillRatings.SPECIALIST),
                skill__in=self.skillsRequired.all(),
            )
        )

    def users_can_lead(self):
        # Return users who have a userskill
        return User.objects.filter(
            skills__in=UserSkill.objects.filter(
                Q(rating=UserSkillRatings.CAN_DO_ALONE)
                | Q(rating=UserSkillRatings.SPECIALIST),
                skill__in=self.skillsRequired.all(),
            )
        )

    def get_absolute_url(self):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
            self.save()
        return reverse("service_detail", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
        return super().save(*args, **kwargs)