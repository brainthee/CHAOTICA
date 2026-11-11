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
        help_text="A short description of the skill, incl. scope / techniques it covers",
        default="",
    )
    category = models.ForeignKey(
        SkillCategory, related_name="skills", on_delete=models.CASCADE
    )
    slug = models.SlugField(null=False, default="", unique=True)

    # Per-level behavioural descriptors — what each rating *means* for this skill.
    # These anchor self/manager ratings to concrete, observable behaviour instead
    # of a bare number. Left blank, the UI falls back to the global rating labels.
    rating_desc_support = models.TextField(
        "'Require Support' descriptor",
        blank=True,
        default="",
        help_text="What someone rated 'Require Support' (1) can do for this skill.",
    )
    rating_desc_independent = models.TextField(
        "'Independent' descriptor",
        blank=True,
        default="",
        help_text="What someone rated 'Independent' (2) can do for this skill.",
    )
    rating_desc_specialist = models.TextField(
        "'Specialist' descriptor",
        blank=True,
        default="",
        help_text="What someone rated 'Specialist' (3) can do for this skill.",
    )

    # Skill hierarchy support
    prerequisites = models.ManyToManyField(
        'self',
        blank=True,
        symmetrical=False,
        related_name='dependent_skills',
        help_text="Skills that should be learned before this one"
    )
    related_skills = models.ManyToManyField(
        'self',
        blank=True,
        symmetrical=True,
        help_text="Skills that are commonly used together"
    )

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

    def get_learning_path(self):
        """Get skills that should be learned before this one (recursive)"""
        path = []
        visited = set()

        def _get_prerequisites(skill):
            if skill.id in visited:
                return
            visited.add(skill.id)

            for prereq in skill.prerequisites.all():
                _get_prerequisites(prereq)
                if prereq not in path:
                    path.append(prereq)

        _get_prerequisites(self)
        return path

    def can_learn_now(self, user):
        """Check if user meets prerequisites to learn this skill"""
        user_skills = set(user.skills.values_list('skill_id', flat=True))
        required_skills = set(self.prerequisites.values_list('id', flat=True))
        return required_skills.issubset(user_skills)

    def get_next_skills(self):
        """Get skills that can be learned after mastering this one"""
        return self.dependent_skills.all()

    def descriptor_for_rating(self, rating):
        """Return the skill-specific behavioural descriptor for a rating value,
        falling back to the global rating label when none is configured."""
        mapping = {
            UserSkillRatings.CAN_DO_WITH_SUPPORT: self.rating_desc_support,
            UserSkillRatings.CAN_DO_ALONE: self.rating_desc_independent,
            UserSkillRatings.SPECIALIST: self.rating_desc_specialist,
        }
        text = mapping.get(rating, "")
        if text:
            return text
        return dict(UserSkillRatings.CHOICES).get(rating, "")

    @property
    def has_rating_descriptors(self):
        return bool(
            self.rating_desc_support
            or self.rating_desc_independent
            or self.rating_desc_specialist
        )


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


class SkillRatingSuggestion(models.Model):
    """A non-destructive, proposed skill rating for a user.

    Suggestions are generated automatically (e.g. when a qualification that
    evidences a skill is awarded) and never change a :class:`UserSkill` on their
    own. The user (or a manager) accepts or dismisses each one. Accepting only
    ever *raises* a rating — it never lowers an existing self-assessment.
    """

    PENDING = 0
    ACCEPTED = 1
    DISMISSED = 2
    STATUS_CHOICES = (
        (PENDING, "Pending"),
        (ACCEPTED, "Accepted"),
        (DISMISSED, "Dismissed"),
    )

    SOURCE_QUALIFICATION = "qualification"
    SOURCE_MANUAL = "manual"
    SOURCE_IMPORT = "import"
    SOURCE_CHOICES = (
        (SOURCE_QUALIFICATION, "Qualification awarded"),
        (SOURCE_MANUAL, "Manually suggested"),
        (SOURCE_IMPORT, "Imported"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="skill_suggestions",
    )
    skill = models.ForeignKey(
        Skill, on_delete=models.CASCADE, related_name="rating_suggestions"
    )
    suggested_rating = models.IntegerField(choices=UserSkillRatings.CHOICES)
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default=SOURCE_QUALIFICATION
    )
    source_qualification_record = models.ForeignKey(
        "jobtracker.QualificationRecord",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="skill_suggestions",
    )
    status = models.IntegerField(choices=STATUS_CHOICES, default=PENDING)
    message = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Human-readable reason for the suggestion.",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    resolved_on = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="skill_suggestions_resolved",
    )

    class Meta:
        ordering = ["-created_on"]
        indexes = [
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self):
        return "%s: %s → %s (%s)" % (
            self.user,
            self.skill,
            self.get_suggested_rating_display(),
            self.get_status_display(),
        )

    def accept(self, resolved_by=None):
        """Apply the suggestion: raise the user's rating to at least the
        suggested value (never lowering it), then mark the suggestion accepted.

        Returns the :class:`UserSkill` touched, or ``None`` if the suggestion
        was already superseded by a higher existing rating.
        """
        from django.utils import timezone

        user_skill, _created = UserSkill.objects.get_or_create(
            user=self.user,
            skill=self.skill,
            defaults={"rating": self.suggested_rating},
        )
        touched = user_skill
        if user_skill.rating < self.suggested_rating:
            user_skill.rating = self.suggested_rating
            user_skill.save(update_fields=["rating", "last_updated_on"])
        elif not _created:
            # Existing rating already meets/exceeds the suggestion — nothing to do.
            touched = None

        self.status = self.ACCEPTED
        self.resolved_on = timezone.now()
        self.resolved_by = resolved_by or self.user
        self.save(update_fields=["status", "resolved_on", "resolved_by"])
        return touched

    def dismiss(self, resolved_by=None):
        from django.utils import timezone

        self.status = self.DISMISSED
        self.resolved_on = timezone.now()
        self.resolved_by = resolved_by or self.user
        self.save(update_fields=["status", "resolved_on", "resolved_by"])
