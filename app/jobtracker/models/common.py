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


class Link(models.Model):
    url = models.URLField(max_length=2000, default="", null=True, blank=True, verbose_name="URL")
    title = models.CharField(max_length=255, help_text="Title of the link when other.")
    linkType = models.IntegerField(verbose_name="Link Type", help_text="Type of link",
                                     choices=LinkType.CHOICES, default=LinkType.LN_OTHER)

    def __str__(self):
        return self.url


class Service(models.Model):
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(null=False, default='', unique=True)
    owners = models.ManyToManyField(settings.AUTH_USER_MODEL,
        blank=True, limit_choices_to={'is_active': True})
    history = HistoricalRecords()
    skillsRequired = models.ManyToManyField(Skill,
        blank=True, related_name="services_skill_required")
    skillsDesired = models.ManyToManyField(Skill,
        blank=True, related_name="services_skill_desired")
    data = JSONField(verbose_name="Data", null=True, blank=True, default=dict)

    class Meta:
        ordering = [Lower('name')]
        permissions = (
            ('assign_to_phase', 'Assign To Phase'),
        )
    
    def __str__(self):
        return self.name
    
    def users_can_conduct(self):
        # Return users who have a userskill 
        return User.objects.filter(
            skills__in=UserSkill.objects.filter(
                Q(rating=UserSkillRatings.CAN_DO_ALONE) | 
                Q(rating=UserSkillRatings.CAN_DO_WITH_SUPPORT) | 
                Q(rating=UserSkillRatings.SPECIALIST),
                skill__in=self.skillsRequired.all()))
    
    def users_can_lead(self):
        # Return users who have a userskill 
        return User.objects.filter(
            skills__in=UserSkill.objects.filter(
                Q(rating=UserSkillRatings.CAN_DO_ALONE) | 
                Q(rating=UserSkillRatings.SPECIALIST),
                skill__in=self.skillsRequired.all()))
        
    def get_absolute_url(self):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
            self.save()
        return reverse('service_detail', kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
        return super().save(*args, **kwargs)


class WorkflowTask(models.Model):
    WF_JOB = 1
    WF_PHASE = 2
    CHOICES = (
        (WF_JOB, "Job"),
        (WF_PHASE, "Phase"),
    )
    appliedModel = models.IntegerField(verbose_name="Applicable Model",
                            choices=CHOICES, default=WF_JOB)
    status = models.IntegerField(verbose_name="Status", default=0)
    task = models.CharField('Task', max_length=255)

    def get_status_str(self):
        if self.appliedModel == WorkflowTask.WF_JOB:
            return JobStatuses.CHOICES[self.status][1]
        elif self.appliedModel == WorkflowTask.WF_PHASE:
            return PhaseStatuses.CHOICES[self.status][1]
        else:
            return self.status


class Feedback(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='written_feedback',
        on_delete=models.PROTECT)
    
    phase = models.ForeignKey(
        Phase,
        related_name='feedback',
        on_delete=models.PROTECT)
    
    feedbackType = models.IntegerField(verbose_name="Type", help_text="Type of feedback",
        choices=FeedbackType.CHOICES, default=FeedbackType.OTHER)
        
    body = BleachField()
    created_on = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ['-created_on']
        permissions = ()

    def __str__(self):
        return 'Feedback {} by {}'.format(self.body, self.author.get_full_name())