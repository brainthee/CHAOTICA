from django.db import models
from ..enums import QualificationStatus
from django.conf import settings
from chaotica_utils.utils import unique_slug_generator
from django.utils import timezone
from django.urls import reverse
from django.core.exceptions import ValidationError
from simple_history.models import HistoricalRecords
from django.db.models.functions import Lower
from django.db.models import Count, Q
from model_utils.fields import MonitorField
from datetime import timedelta


class QualificationTag(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(null=False, default="", unique=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
        return super().save(*args, **kwargs)

    def __str__(self):
        return "%s" % (self.name)

    class Meta:
        ordering = [Lower("name")]


class AwardingBody(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(null=False, default="", unique=True)
    description = models.TextField(blank=True, default="")
    url = models.URLField(
        max_length=2000, blank=True, null=True, verbose_name="Website URL"
    )
    logo = models.ImageField(upload_to="awarding_bodies/", blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
        return super().save(*args, **kwargs)

    def __str__(self):
        return "%s" % (self.name)

    class Meta:
        ordering = [Lower("name")]
        unique_together = (("name"), ("slug"))
        verbose_name_plural = "Awarding bodies"


class Qualification(models.Model):
    awarding_body = models.ForeignKey(
        AwardingBody, related_name="qualifications", on_delete=models.PROTECT
    )
    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=200, default="")
    slug = models.SlugField(null=False, default="", unique=True)
    tags = models.ManyToManyField(QualificationTag, verbose_name="Tags", blank=True)
    description = models.TextField(blank=True, default="")
    validity_period = models.IntegerField(
        "Validity Period",
        help_text="How many days the qualification is valid for. If left empty, it does not expire.",
        null=True,
        blank=True,
    )
    verification_required = models.BooleanField(
        "Manager Verification Required",
        default=False,
        help_text="If enabled, awarded records require manager verification.",
    )

    url = models.URLField(
        max_length=2000,
        default="",
        null=True,
        blank=True,
        verbose_name="Qualification URL",
    )
    guidance_url = models.URLField(
        max_length=2000, default="", null=True, blank=True, verbose_name="Guidance URL"
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
        return super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse(
            "qualification_detail",
            kwargs={"bodySlug": self.awarding_body.slug, "slug": self.slug},
        )

    def __str__(self):
        if self.short_name:
            return "%s (%s)" % (self.name, self.short_name)
        else:
            return "%s" % (self.name)

    @property
    def validity_period_display(self):
        if not self.validity_period:
            return "Does not expire"
        years = self.validity_period // 365
        remaining_days = self.validity_period % 365
        months = remaining_days // 30
        days = remaining_days % 30
        parts = []
        if years:
            parts.append(f"{years} year{'s' if years != 1 else ''}")
        if months:
            parts.append(f"{months} month{'s' if months != 1 else ''}")
        if days:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        return ", ".join(parts) if parts else "Does not expire"

    def awarded_count(self):
        return self.users.filter(status=QualificationStatus.AWARDED).count()

    def in_progress_count(self):
        return self.users.filter(
            status__in=[QualificationStatus.IN_PROGRESS, QualificationStatus.PENDING]
        ).count()

    def lapsed_count(self):
        return self.users.filter(status=QualificationStatus.LAPSED).count()

    def expiring_soon_count(self, days=90):
        today = timezone.now().date()
        return self.users.filter(
            status=QualificationStatus.AWARDED,
            lapse_date__isnull=False,
            lapse_date__lte=today + timedelta(days=days),
            lapse_date__gt=today,
        ).count()

    class Meta:
        ordering = [Lower("awarding_body"), Lower("name")]
        unique_together = (("name"), ("slug"))
        permissions = (("view_users_qualifications", "View Users with Qualification"),)


class QualificationRecord(models.Model):
    qualification = models.ForeignKey(
        Qualification, related_name="users", on_delete=models.PROTECT
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="qualifications",
    )
    status = models.IntegerField(
        choices=QualificationStatus.CHOICES, default=QualificationStatus.UNKNOWN
    )
    history = HistoricalRecords()

    last_updated_on = models.DateTimeField(auto_now=True)
    status_changed_date = MonitorField(monitor="status")
    attempt_date = models.DateField(
        "Date of Attempt", null=True, blank=True, help_text="Date of the attempt."
    )
    awarded_date = models.DateField(
        "Date Awarded",
        null=True,
        blank=True,
        help_text="Date this qualification was awarded. Validity period will be calculated from this if appropriate.",
    )
    lapse_date = models.DateField(
        "Date Lapses",
        null=True,
        blank=True,
        help_text="Date this qualification will lapse. Calculated from the Validity period.",
    )
    certificate_number = models.CharField(
        "Certificate/Registration Number",
        max_length=200,
        blank=True,
        default="",
    )
    notes = models.TextField(blank=True, default="")
    certificate_file = models.FileField(
        upload_to="certificates/", blank=True, null=True
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="qualification_verifications",
    )
    verified_on = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = [
            "qualification",
            "user",
        ]

    def clean(self):
        super().clean()
        if not self.user_id:
            return  # User not yet assigned (will be set in view)
        active_statuses = [
            QualificationStatus.AWARDED,
            QualificationStatus.IN_PROGRESS,
            QualificationStatus.PENDING,
        ]
        if self.status in active_statuses:
            existing = QualificationRecord.objects.filter(
                qualification=self.qualification,
                user=self.user,
                status__in=active_statuses,
            ).exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError(
                    "You already have an active record for this qualification."
                )

    @property
    def status_bs_colour(self):
        return QualificationStatus.BS_COLOURS[self.status][1]

    def is_lapsed(self):
        if self.lapse_date:
            return self.lapse_date <= timezone.now().date()
        return False

    def days_to_lapse(self):
        if not self.lapse_date:
            return 9999
        days = (self.lapse_date - timezone.now().date()).days
        if days < 0:
            return 0
        return days

    @property
    def expiry_urgency(self):
        if not self.lapse_date:
            return "no_expiry"
        days = self.days_to_lapse()
        if days == 0:
            return "expired"
        elif days <= 30:
            return "critical"
        elif days <= 90:
            return "warning"
        else:
            return "ok"

    def __str__(self):
        return "%s - %s (%s)" % (
            self.user,
            self.qualification,
            self.get_status_display(),
        )
