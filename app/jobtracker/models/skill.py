from django.db import models
from ..enums import UserSkillRatings
from chaotica_utils.utils import unique_slug_generator
from django.conf import settings
from django.db.models import Q
from django.urls import reverse
from django.db.models.functions import Lower

class SkillCategory(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(null=False, default='', unique=True)

    def __str__(self):
        return '%s' % (self.name)

    class Meta:
        verbose_name_plural = "Skill Categories"
        ordering = [Lower('name')]
        permissions = ()    

    def get_users_can_do_alone(self):
        return UserSkill.objects.filter(skill__in=self.skills.all(), rating=UserSkillRatings.CAN_DO_ALONE)

    def get_users_can_do_with_support(self):
        return UserSkill.objects.filter(skill__in=self.skills.all(), rating=UserSkillRatings.CAN_DO_WITH_SUPPORT)

    def get_users_specialist(self):
        return UserSkill.objects.filter(skill__in=self.skills.all(), rating=UserSkillRatings.SPECIALIST)

    def get_users_breakdown_perc(self):
        total_users = self.get_users().count()
        data = {}
        data['total_users'] = total_users
        if total_users > 0:
            data['can_do_with_support'] = round((self.get_users_can_do_with_support().count() / total_users) * 100, 2)
            data['can_do_alone'] = round((self.get_users_can_do_alone().count() / total_users) * 100, 2)
            data['specialist'] = round((self.get_users_specialist().count() / total_users) * 100, 2)
        else:
            data['can_do_with_support'] = 0
            data['can_do_alone'] = 0
            data['specialist'] = 0
        return data


    def get_users(self):
        return UserSkill.objects.filter(
            Q(rating=UserSkillRatings.CAN_DO_ALONE) | 
            Q(rating=UserSkillRatings.CAN_DO_WITH_SUPPORT) | 
            Q(rating=UserSkillRatings.SPECIALIST),
            skill__in=self.skills.all())

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
        return super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("skillcategory_detail", kwargs={"slug": self.slug})


class Skill(models.Model):
    name = models.CharField(max_length=200)
    category = models.ForeignKey(SkillCategory, related_name="skills", on_delete=models.CASCADE)
    slug = models.SlugField(null=False, default='', unique=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.category.name+"-"+self.name)
        return super().save(*args, **kwargs)

    def __unicode__(self):
        return u'%s - %s' % (self.name, self.category)

    def __str__(self):
        return '%s - %s' % (self.category, self.name)

    class Meta:
        ordering = [Lower('category'), Lower('name')]
        unique_together = (('category', 'name'), )
        permissions = (
            ## Defaults
            # ('view_skill', 'View Skill'),
            # ('add_skill', 'Add Skill'),
            # ('change_skill', 'Change Skill'),
            # ('delete_skill'', 'Delete Skill'),
            ## Extra
            ('view_users_skill', 'View Users with Skill'),
        )    

    def get_users_can_do_alone(self):
        return UserSkill.objects.filter(skill=self, rating=UserSkillRatings.CAN_DO_ALONE)

    def get_users_can_do_with_support(self):
        return UserSkill.objects.filter(skill=self, rating=UserSkillRatings.CAN_DO_WITH_SUPPORT)

    def get_users_specialist(self):
        return UserSkill.objects.filter(skill=self, rating=UserSkillRatings.SPECIALIST)

    def get_users(self):
        return UserSkill.objects.filter(
            Q(rating=UserSkillRatings.CAN_DO_ALONE) | 
            Q(rating=UserSkillRatings.CAN_DO_WITH_SUPPORT) | 
            Q(rating=UserSkillRatings.SPECIALIST),
            skill=self)

    def get_absolute_url(self):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
            self.save()
        return reverse("skill_detail", kwargs={"slug": self.slug})


class UserSkill(models.Model):
    skill = models.ForeignKey(Skill, related_name='users', on_delete=models.PROTECT)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        limit_choices_to=(
            models.Q(is_active=True)
        ),
        on_delete=models.CASCADE,
        related_name="skills",
    )
    rating = models.IntegerField(choices=UserSkillRatings.CHOICES, default=UserSkillRatings.NO_EXPERIENCE)
    interested_in_improving_skill = models.BooleanField(default=False)
    last_updated_on = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return u'%s %s - %s: %s' % (self.user.first_name, self.user.last_name,
                                    self.skill, self.get_rating_display())

    class Meta:
        ordering = ['-rating', 'user', ]
        unique_together = (('user', 'skill',),)