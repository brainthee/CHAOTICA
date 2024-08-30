from django.db import models
from ..enums import (
    ProjectStatuses,
    RestrictedClassifications,
    TimeSlotDeliveryRole,
    JobSupportRole,
)
from ..models.client import FrameworkAgreement
from django_fsm import FSMIntegerField, transition, can_proceed
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
from simple_history.models import HistoricalRecords
from django.db.models import Q
from django.contrib.contenttypes.fields import GenericRelation
from model_utils.fields import MonitorField
from django.db.models import JSONField
from django.contrib import messages
import uuid
from chaotica_utils.models import Note, User, get_sentinel_user
from chaotica_utils.tasks import task_send_notifications
from chaotica_utils.views import log_system_activity
from datetime import timedelta
from decimal import Decimal
from django_bleach.models import BleachField
from constance import config
from guardian.shortcuts import get_objects_for_user


class ProjectManager(models.Manager):

    def projects_with_unit_permission(self, user, perm):
        from ..models import OrganisationalUnit

        units = get_objects_for_user(user, perm, klass=OrganisationalUnit)

        matches = (
            self.filter(Q(unit__in=units))
        )
        return matches

    def projects_for_user(self, user):
        # Job's we're interested in:
        # - Scheduled on
        # - Lead/Author of
        # - Scoped while before scoping approved

        matches = (
            self.filter(
                Q(phases__timeslots__user=user)  # Filter by scheduled
            )
            .distinct()
        )
        return matches


class Project(models.Model):
    STATE_ERROR = "Invalid state or permissions."

    objects = ProjectManager()

    # IDs
    id = models.IntegerField(editable=False, verbose_name="Project ID")
    db_id = models.AutoField(
        primary_key=True, editable=False, verbose_name="Database ID"
    )
    slug = models.UUIDField(
        default=uuid.uuid4, editable=False, unique=True, db_index=True
    )
    unit = models.ForeignKey(
        "OrganisationalUnit", related_name="projects", null=True, blank=True, on_delete=models.CASCADE
    )
    status = models.IntegerField(
        verbose_name="Job Status",
        help_text="Current state of the job",
        choices=ProjectStatuses.CHOICES,
        default=ProjectStatuses.UNTRACKED,
    )
    status_changed_date = MonitorField(monitor="status")
    is_imported = models.BooleanField(default=False)
    external_id = models.CharField(
        verbose_name="External ID",
        db_index=True,
        max_length=255,
        unique=True,
        blank=True,
        default="",
    )
    title = models.CharField("Project Title", max_length=250)
    history = HistoricalRecords()
    data = JSONField(verbose_name="Data", null=True, blank=True, default=dict)
    notes = GenericRelation(Note)
    desired_start_date = models.DateField(
        "Start Date",
        null=True,
        blank=True,
        help_text="If left blank, this will be automatically determined from scheduled slots",
    )
    desired_delivery_date = models.DateField(
        "Delivery date",
        null=True,
        blank=True,
        db_index=True,
        help_text="If left blank, this will be automatically determined from scheduled slots",
    )

    # Sales fields
    charge_codes = models.ManyToManyField(
        "BillingCode", verbose_name="Charge Code", related_name="projects", blank=True
    )

    # People Fields
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Created By",
        related_name="projects_created",
        on_delete=models.SET(get_sentinel_user),
    )
    primary_poc = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Primary Point of Contact",
        related_name="projects_poc_for",
        blank=True,
        null=True,
        on_delete=models.SET(get_sentinel_user),
    )
    # Main info
    overview = BleachField(blank=True, null=True)

    class Meta:
        verbose_name = "Project"
        ordering = ["-id"]

    def __str__(self):
        return "{id}: {title}".format(id=self.id, title=self.title)

    def get_absolute_url(self):
        return reverse("project_detail", kwargs={"slug": self.slug})

    def start_date(self):
        from ..models import TimeSlot

        if self.desired_start_date:
            return self.desired_start_date
        else:
            # Calculate start from first delivery slot
            if TimeSlot.objects.filter(
                phase__job=self, deliveryRole=TimeSlotDeliveryRole.DELIVERY
            ).exists():
                return (
                    TimeSlot.objects.filter(
                        phase__job=self, deliveryRole=TimeSlotDeliveryRole.DELIVERY
                    )
                    .order_by("-start")
                    .first()
                    .start.date()
                )
            else:
                # No slots - return None
                return None

    def delivery_date(self):
        from ..models import TimeSlot

        if self.desired_delivery_date:
            return self.desired_delivery_date
        else:
            # Calculate start from first delivery slot
            if TimeSlot.objects.filter(
                phase__job=self, deliveryRole=TimeSlotDeliveryRole.REPORTING
            ).exists():
                return TimeSlot.objects.filter(
                    phase__job=self, deliveryRole=TimeSlotDeliveryRole.REPORTING
                ).order_by("end").first().end.date() + timedelta(weeks=1)
            else:
                # No slots - return None
                return None

    @property
    def status_bs_colour(self):
        return ProjectStatuses.BS_COLOURS[self.status][1]

    @property
    def is_tracked(self):
        return self.status > ProjectStatuses.UNTRACKED
    
    def get_system_notes(self):
        return self.notes.filter(is_system_note=True)

    def get_user_notes(self):
        return self.notes.filter(is_system_note=False)
    
    def save(self, *args, **kwargs):
        # This means that the model isn't saved to the database yet
        if self._state.adding:
            # Get the maximum display_id value from the database
            last_id = Project.objects.all().aggregate(largest=models.Max("id"))["largest"]

            # aggregate can return None! Check it first.
            # If it isn't none, just use the last ID specified (which should be the greatest) and add one to it
            if last_id is not None:
                self.id = last_id + 1
            else:
                # We haven't got any other jobs so lets just start from the default
                self.id = int(config.PROJECT_ID_START) + 1

        return super().save(*args, **kwargs)