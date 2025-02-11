from django.db import models
from ..enums import UserSkillRatings
from chaotica_utils.utils import unique_slug_generator
from django.conf import settings
from django.db.models import Q, Count
from django.urls import reverse
from django.db.models.functions import Lower


class SkillCategory(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(
        help_text="A short description of the category", default=""
    )
    slug = models.SlugField(null=False, default="", unique=True)

    def __str__(self):
        return "%s" % (self.name)

    class Meta:
        verbose_name_plural = "Skill Categories"
        ordering = [Lower("name")]
        permissions = ()

    def get_users_can_do_alone(self):
        return (
            self.skills.all()
            .filter(users__rating=UserSkillRatings.CAN_DO_ALONE)
            .values("users")
        )

    def get_users_can_do_with_support(self):
        return (
            self.skills.all()
            .filter(users__rating=UserSkillRatings.CAN_DO_WITH_SUPPORT)
            .values("users")
        )

    def get_users_specialist(self):
        return (
            self.skills.all()
            .filter(users__rating=UserSkillRatings.SPECIALIST)
            .values("users")
        )

    def get_rating_counts(self):
        """
        Returns a dictionary with total counts for each rating.
        """
        ratings = (
            self.skills.values("users__rating").annotate(count=Count("id")).order_by()
        )
        return dict((r["users__rating"], r["count"]) for r in ratings)

    def get_users_breakdown_perc(self):
        rating_counts = self.get_rating_counts()

        total_users = (
            rating_counts.get(UserSkillRatings.CAN_DO_ALONE, 0)
            + rating_counts.get(UserSkillRatings.CAN_DO_WITH_SUPPORT, 0)
            + rating_counts.get(UserSkillRatings.SPECIALIST, 0)
        )

        data = {}
        data["total_users"] = total_users
        data["can_do_with_support"] = 0
        data["can_do_alone"] = 0
        data["specialist"] = 0
        data["can_do_with_support_perc"] = 0
        data["can_do_alone_perc"] = 0
        data["specialist_perc"] = 0

        if total_users > 0:
            data["can_do_with_support_perc"] = round(
                (rating_counts.get(UserSkillRatings.CAN_DO_WITH_SUPPORT, 0) / total_users)
                * 100,
                2,
            )
            data["can_do_alone_perc"] = round(
                (rating_counts.get(UserSkillRatings.CAN_DO_ALONE, 0) / total_users) * 100, 2
            )
            data["specialist_perc"] = round(
                (rating_counts.get(UserSkillRatings.SPECIALIST, 0) / total_users) * 100, 2
            )
        return data

    def get_users(self):
        return (
            self.skills.all()
            .filter(
                Q(users__rating=UserSkillRatings.CAN_DO_ALONE)
                | Q(users__rating=UserSkillRatings.CAN_DO_WITH_SUPPORT)
                | Q(users__rating=UserSkillRatings.SPECIALIST),
            )
            .values("users")
        )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
        return super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("skillcategory_detail", kwargs={"slug": self.slug})


class Skill(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(
        help_text="A short description of the skill", default=""
    )
    category = models.ForeignKey(
        SkillCategory, related_name="skills", on_delete=models.CASCADE
    )
    slug = models.SlugField(null=False, default="", unique=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug_generator(
                self, self.category.name + "-" + self.name
            )
        return super().save(*args, **kwargs)

    def __unicode__(self):
        return "%s - %s" % (self.name, self.category)

    def __str__(self):
        return "%s - %s" % (self.category, self.name)

    class Meta:
        ordering = [Lower("category"), Lower("name")]
        unique_together = (("category", "name"),)
        permissions = (
            ## Defaults
            # ('view_skill', 'View Skill'),
            # ('add_skill', 'Add Skill'),
            # ('change_skill', 'Change Skill'),
            # ('delete_skill'', 'Delete Skill'),
            ## Extra
            ("view_users_skill", "View Users with Skill"),
        )

    def get_rating_counts(self):
        """
        Returns a dictionary with total counts for each rating.
        """
        ratings = self.users.values("rating").annotate(count=Count("id")).order_by()
        return dict((r["rating"], r["count"]) for r in ratings)

    def get_users_breakdown_perc(self):

        rating_counts = self.get_rating_counts()

        total_users = (
            rating_counts.get(UserSkillRatings.CAN_DO_ALONE, 0)
            + rating_counts.get(UserSkillRatings.CAN_DO_WITH_SUPPORT, 0)
            + rating_counts.get(UserSkillRatings.SPECIALIST, 0)
        )

        data = {}
        data["total_users"] = total_users
        data["can_do_with_support"] = rating_counts.get(
            UserSkillRatings.CAN_DO_WITH_SUPPORT, 0
        )
        data["can_do_alone"] = rating_counts.get(UserSkillRatings.CAN_DO_ALONE, 0)
        data["specialist"] = rating_counts.get(UserSkillRatings.SPECIALIST, 0)
        data["can_do_with_support_perc"] = 0
        data["can_do_alone_perc"] = 0
        data["specialist_perc"] = 0

        if total_users > 0:
            data["can_do_with_support_perc"] = round(
                (
                    rating_counts.get(UserSkillRatings.CAN_DO_WITH_SUPPORT, 0)
                    / total_users
                )
                * 100,
                2,
            )
            data["can_do_alone_perc"] = round(
                (rating_counts.get(UserSkillRatings.CAN_DO_ALONE, 0) / total_users)
                * 100,
                2,
            )
            data["specialist_perc"] = round(
                (rating_counts.get(UserSkillRatings.SPECIALIST, 0) / total_users) * 100,
                2,
            )
        return data

    def get_users_can_do_alone(self):
        return self.users.filter(
            rating=UserSkillRatings.CAN_DO_ALONE
        ).prefetch_related("user", "user__unit_memberships")

    def get_users_can_do_with_support(self):
        return self.users.filter(
            rating=UserSkillRatings.CAN_DO_WITH_SUPPORT
        ).prefetch_related("user", "user__unit_memberships")

    def get_users_specialist(self):
        return self.users.filter(
            rating=UserSkillRatings.SPECIALIST
        ).prefetch_related("user", "user__unit_memberships")

    def get_users(self):
        return self.users.filter(
            Q(rating=UserSkillRatings.CAN_DO_ALONE)
            | Q(rating=UserSkillRatings.CAN_DO_WITH_SUPPORT)
            | Q(rating=UserSkillRatings.SPECIALIST)
        ).prefetch_related("user", "user__unit_memberships", "user__unit_memberships__unit")

    def get_absolute_url(self):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
            self.save()
        return reverse("skill_detail", kwargs={"slug": self.slug})


class UserSkill(models.Model):
    skill = models.ForeignKey(Skill, related_name="users", on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        limit_choices_to=(models.Q(is_active=True)),
        on_delete=models.CASCADE,
        related_name="skills",
    )
    rating = models.IntegerField(
        choices=UserSkillRatings.CHOICES, default=UserSkillRatings.NO_EXPERIENCE
    )
    interested_in_improving_skill = models.BooleanField(default=False)
    last_updated_on = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return "%s %s - %s: %s" % (
            self.user.first_name,
            self.user.last_name,
            self.skill,
            self.get_rating_display(),
        )

    class Meta:
        ordering = [
            "-rating",
            "user",
        ]
        unique_together = (
            (
                "user",
                "skill",
            ),
        )
