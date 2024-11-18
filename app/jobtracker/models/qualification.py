from django.db import models
from ..enums import QualificationStatus
from django.conf import settings
from chaotica_utils.utils import unique_slug_generator
from django.utils import timezone
from django.urls import reverse
from simple_history.models import HistoricalRecords
from django.db.models.functions import Lower
from model_utils.fields import MonitorField


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

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
        return super().save(*args, **kwargs)

    def __str__(self):
        return "%s" % (self.name)

    class Meta:
        ordering = [Lower("name")]
        unique_together = (("name"), ("slug"))


class Qualification(models.Model):
    awarding_body = models.ForeignKey(
        AwardingBody, related_name="qualifications", on_delete=models.PROTECT
    )
    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=200, default="")
    slug = models.SlugField(null=False, default="", unique=True)
    tags = models.ManyToManyField(QualificationTag, verbose_name="Tags", blank=True)
    validity_period = models.IntegerField(
        "Validity Period",
        help_text="How many days the qualification is valid for. If left empty, it does not expire.",
        null=True,
        blank=True,
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

    class Meta:
        ordering = [
            "qualification",
            "user",
        ]

    @property
    def status_bs_colour(self):
        return QualificationStatus.BS_COLOURS[self.status][1]

    def is_lapsed(self):
        if self.lapse_date:
            if self.status != QualificationStatus.LAPSED:
                # Update the status since we're here...
                self.status = QualificationStatus.LAPSED
                self.save()
            return self.lapse_date > timezone.now().today()
        else:
            return False

    def days_to_lapse(self):
        if not self.is_lapsed():
            if self.lapse_date:
                days = (timezone.now().today() - self.lapse_date).days
                return days
            else:
                return 9999  # lots - no lapse date
        else:
            return 0

    def __str__(self):
        return "%s - %s (%s)" % (
            self.user,
            self.qualification,
            self.get_status_display(),
        )
