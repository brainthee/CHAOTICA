from django.db import models
from ..enums import (
    ProjectStatuses,
    ProjectState,
    TimeSlotDeliveryRole,
)
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
from simple_history.models import HistoricalRecords
from django.db.models import Q
from django.contrib.contenttypes.fields import GenericRelation
from model_utils.fields import MonitorField
from django.db.models import JSONField
import uuid
from chaotica_utils.models import Note, get_sentinel_user
from datetime import timedelta
from django.db.models.functions import Lower
from django_bleach.models import BleachField
from constance import config
from guardian.shortcuts import get_objects_for_user


class ProjectManager(models.Manager):

    def projects_with_unit_permission(self, user, perm):
        from ..models import OrganisationalUnit

        units = get_objects_for_user(user, perm, klass=OrganisationalUnit)

        matches = self.filter(Q(unit__in=units))
        return matches

    def projects_for_user(self, user):
        # Job's we're interested in:
        # - Scheduled on
        # - Lead/Author of
        # - Scoped while before scoping approved

        # Projects link to timeslots directly (there is no Project->phases
        # relation), so scope by the project's own scheduled slots.
        matches = self.filter(Q(timeslots__user=user)).distinct()  # Filter by scheduled
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
        "OrganisationalUnit",
        related_name="projects",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    client = models.ForeignKey(
        "Client",
        related_name="projects",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Optional client this project is associated with.",
    )
    status = models.IntegerField(
        verbose_name="Job Status",
        help_text="Current state of the job",
        choices=ProjectStatuses.CHOICES,
        default=ProjectStatuses.UNTRACKED,
    )
    status_changed_date = MonitorField(monitor="status")
    state = models.IntegerField(
        verbose_name="Project State",
        help_text="Commercial certainty (mirrors RM). Confirmed + deliverable counts toward utilisation.",
        choices=ProjectState.CHOICES,
        default=ProjectState.INTERNAL,
    )
    deliverable = models.BooleanField(
        default=False,
        help_text="This is client-deliverable work — confirmed deliverable time counts toward utilisation.",
    )
    is_imported = models.BooleanField(default=False)
    external_id = models.CharField(
        verbose_name="External ID",
        db_index=True,
        max_length=255,
        unique=True,
        blank=True,
        null=True,
        default=None,
    )
    title = models.CharField("Project Title", max_length=250)
    external_url = models.URLField(
        verbose_name="External URL",
        max_length=500,
        blank=True,
        null=True,
        default=None,
        help_text="Link back to the source system this project was imported from (e.g. RM).",
    )
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
        ordering = [Lower("title")]

    @property
    def charge_codes(self):
        """Backwards-compatible accessor: the distinct billing codes on this project.

        Now backed by :class:`BillingCodeAssignment` rows; kept as a property
        returning a queryset so ``project.charge_codes.all`` keeps working.
        """
        from ..models import BillingCode

        return BillingCode.objects.filter(assignments__project=self).distinct()

    def get_billing_assignments(self):
        """Billing-code assignments attached directly to this project."""
        return self.billing_code_assignments.select_related("code")

    def is_chargable(self):
        return self.billing_code_assignments.exists()

    def __str__(self):
        return "{id}: {title}".format(id=self.id, title=self.title)

    def get_absolute_url(self):
        return reverse("project_detail", kwargs={"slug": self.slug})

    def start_date(self):
        from ..models import TimeSlot

        if self.desired_start_date:
            return self.desired_start_date
        else:
            # Calculate start from first delivery slot. Timeslots link to a
            # project directly (phase__job resolves to a Job, not a Project).
            slots = TimeSlot.objects.filter(
                project=self, deliveryRole=TimeSlotDeliveryRole.DELIVERY
            ).order_by("-start")
            first = slots.first()
            if first:
                return first.start.date()
            else:
                # No slots - return None
                return None

    def delivery_date(self):
        from ..models import TimeSlot

        if self.desired_delivery_date:
            return self.desired_delivery_date
        else:
            # Calculate delivery from last reporting slot. Timeslots link to a
            # project directly (phase__job resolves to a Job, not a Project).
            slot = (
                TimeSlot.objects.filter(
                    project=self, deliveryRole=TimeSlotDeliveryRole.REPORTING
                )
                .order_by("end")
                .first()
            )
            if slot:
                return slot.end.date() + timedelta(weeks=1)
            else:
                # No slots - return None
                return None

    @property
    def status_bs_colour(self):
        return ProjectStatuses.BS_COLOURS[self.status][1]

    @property
    def state_bs_colour(self):
        return ProjectState.BS_COLOURS[self.state][1]

    @property
    def state_is_confirmed(self):
        return self.state == ProjectState.CONFIRMED

    @property
    def state_is_tentative(self):
        return self.state == ProjectState.TENTATIVE

    def counts_as_delivery(self):
        """A confirmed, deliverable project counts toward utilisation like confirmed delivery."""
        return self.deliverable and self.state == ProjectState.CONFIRMED

    @property
    def is_tracked(self):
        return self.status > ProjectStatuses.UNTRACKED

    def get_hours_in_day(self):
        """Day divisor for converting timeslot hours into whole days.

        Mirrors ``FrameworkAgreement.get_hours_in_day`` — use the client's
        configured hours-in-day when a client is set, otherwise fall back to
        the global ``DEFAULT_HOURS_IN_DAY`` constance value. Guards against a
        zero/blank value so callers never divide by zero.
        """
        if self.client and self.client.hours_in_day:
            return self.client.hours_in_day
        return Decimal(str(config.DEFAULT_HOURS_IN_DAY))

    def get_stats(self):
        """Day-based delivery stats aggregated from this project's timeslots.

        Projects link to ``TimeSlot``s directly (no phases, no revenue, and a
        ``deliveryRole`` on each slot), so this mirrors the framework detail
        view's ``_calc_days`` aggregation rather than the per-user availability
        engine. All work is computed from a single prefetched slot list — the
        business hours of each slot are cached once so the repeated filtered
        day sums don't re-query the DB.
        """
        from chaotica_utils.utils import slots_to_days, classify_delivery_slot

        hours_in_day = self.get_hours_in_day()
        now = timezone.now()

        slots = list(self.timeslots.select_related("user", "phase"))
        for s in slots:
            s._cached_hours = s.get_business_hours()

        def used_fn(s):
            return s.end < now

        def sched_fn(s):
            return s.start >= now

        # --- Confirmed / tentative split via the shared classification ---
        # A project slot's confirmation is driven by the project state +
        # deliverable flag (and the phase status if the slot happens to link a
        # phase), keeping this consistent with utilisation.
        confirmed_slots = []
        tentative_slots = []
        for s in slots:
            flags = classify_delivery_slot(
                {
                    "phase__status": s.phase.status if s.phase_id else None,
                    "project__state": self.state,
                    "project__deliverable": self.deliverable,
                    "slot_type__is_working": None,
                }
            )
            if flags["is_confirmed"]:
                confirmed_slots.append(s)
            elif flags["is_tentative"]:
                tentative_slots.append(s)

        summary = {
            "total_days": slots_to_days(slots, hours_in_day),
            "used_days": slots_to_days(slots, hours_in_day, used_fn),
            "scheduled_days": slots_to_days(slots, hours_in_day, sched_fn),
            "team_size": len({s.user_id for s in slots}),
            "confirmed_days": slots_to_days(confirmed_slots, hours_in_day),
            "tentative_days": slots_to_days(tentative_slots, hours_in_day),
        }

        # --- Per-user breakdown (mirrors the framework view) ---
        role_labels = dict(TimeSlotDeliveryRole.CHOICES)
        users_by_id = {}
        for s in slots:
            if s.user_id not in users_by_id:
                users_by_id[s.user_id] = {"user": s.user, "slots": []}
            users_by_id[s.user_id]["slots"].append(s)
        users_data = []
        for data in users_by_id.values():
            member_roles = sorted(
                {
                    role_labels.get(sl.deliveryRole)
                    for sl in data["slots"]
                    if sl.deliveryRole
                }
            )
            users_data.append(
                {
                    "user": data["user"],
                    "used_days": slots_to_days(data["slots"], hours_in_day, used_fn),
                    "scheduled_days": slots_to_days(
                        data["slots"], hours_in_day, sched_fn
                    ),
                    "total_days": slots_to_days(data["slots"], hours_in_day),
                    "roles": member_roles,
                }
            )
        users_data.sort(key=lambda x: x["total_days"], reverse=True)
        # Share of the project's total days, so the member tables can render a
        # simple proportional progress bar without template-side arithmetic.
        project_total = summary["total_days"] or 0
        for entry in users_data:
            entry["pct"] = (
                round(entry["total_days"] / project_total * 100, 1)
                if project_total
                else 0
            )

        # --- Per-delivery-role breakdown (role 0 = None is skipped) ---
        roles_data = []
        for role_val, role_name in TimeSlotDeliveryRole.CHOICES:
            if role_val == 0:
                continue
            role_slots = [s for s in slots if s.deliveryRole == role_val]
            if role_slots:
                roles_data.append(
                    {
                        "role_name": role_name,
                        "used_days": slots_to_days(role_slots, hours_in_day, used_fn),
                        "scheduled_days": slots_to_days(
                            role_slots, hours_in_day, sched_fn
                        ),
                        "total_days": slots_to_days(role_slots, hours_in_day),
                    }
                )

        # --- Monthly burn-down (days consumed per past month + cumulative) ---
        monthly = {}
        for s in slots:
            if s.end >= now:
                continue
            month_key = s.start.strftime("%Y-%m")
            monthly.setdefault(month_key, []).append(s)
        # Walk every month from the first to the last consumed month so gap
        # months render as empty (0 days) rather than being skipped, which
        # would make the burn-down jump across missing months.
        monthly_data = []
        if monthly:
            keys = sorted(monthly.keys())
            year, month = (int(p) for p in keys[0].split("-"))
            last_year, last_month = (int(p) for p in keys[-1].split("-"))
            cumulative = Decimal()
            while (year, month) <= (last_year, last_month):
                month_key = "%04d-%02d" % (year, month)
                days = slots_to_days(monthly.get(month_key, []), hours_in_day)
                cumulative += Decimal(str(days))
                monthly_data.append(
                    {
                        "month": month_key,
                        "days": days,
                        "cumulative": round(cumulative, 1),
                    }
                )
                month += 1
                if month > 12:
                    month = 1
                    year += 1

        return {
            "summary": summary,
            "users_data": users_data,
            "roles_data": roles_data,
            "roles_total_used": summary["used_days"],
            "roles_total_scheduled": summary["scheduled_days"],
            "roles_total": summary["total_days"],
            "monthly_data": monthly_data,
        }

    def get_system_notes(self):
        from chaotica_utils.audit import object_audit_events

        return object_audit_events(self)

    def get_user_notes(self):
        return self.notes.filter(is_system_note=False)

    def save(self, *args, **kwargs):
        # This means that the model isn't saved to the database yet
        if self._state.adding:
            # Get the maximum display_id value from the database
            last_id = Project.objects.all().aggregate(largest=models.Max("id"))[
                "largest"
            ]

            # aggregate can return None! Check it first.
            # If it isn't none, just use the last ID specified (which should be the greatest) and add one to it
            if last_id is not None:
                self.id = last_id + 1
            else:
                # We haven't got any other jobs so lets just start from the default
                self.id = int(config.PROJECT_ID_START) + 1

        return super().save(*args, **kwargs)
