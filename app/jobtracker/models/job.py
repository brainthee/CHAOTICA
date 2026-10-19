from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db.models.signals import post_save
from django.dispatch import receiver
from ..enums import (
    JobStatuses,
    RestrictedClassifications,
    TimeSlotDeliveryRole,
    JobSupportRole,
    PhaseStatuses,
)
from ..models.client import FrameworkAgreement
from django_fsm import FSMIntegerField, transition, can_proceed
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
from simple_history.models import HistoricalRecords
from django.db.models import Exists, OuterRef, Q
from django.contrib.contenttypes.fields import GenericRelation
from model_utils.fields import MonitorField
from django.db.models import JSONField
from django.contrib import messages
import uuid
from chaotica_utils.models import AuditCategory, AuditVerb, Note, User, get_sentinel_user
from notifications.utils import AppNotification, send_notifications
from notifications.enums import NotificationTypes
from chaotica_utils.views import log_system_activity
from decimal import Decimal
from django_bleach.models import BleachField
from constance import config
from guardian.shortcuts import get_objects_for_user


def _acting_user(notify_request=None, user=None):
    """Who a ``can_to_*`` check is for: explicit ``user``, else the request's,
    else the current request user (templates call these with no arguments)."""
    if user is not None:
        return user
    if notify_request is not None:
        return notify_request.user
    from chaotica_utils.middleware.common import get_current_user

    return get_current_user()


class JobManager(models.Manager):

    def jobs_with_unit_permission(self, user, perm):
        from ..models import OrganisationalUnit

        units = get_objects_for_user(user, perm, klass=OrganisationalUnit)

        matches = self.filter(
            Q(unit__in=units),
            status__in=JobStatuses.ACTIVE_STATUSES,  # Include active job statuses only
        )
        return matches

    def jobs_for_user(self, user):
        # Job's we're interested in:
        # - Scheduled on
        # - Lead/Author of
        # - Scoped while before scoping approved

        from .phase import Phase
        from .timeslot import TimeSlot

        # Exists, not joins: phases × timeslots × scoped_by fanned big jobs
        # out into thousands of rows to DISTINCT away.
        matches = self.filter(
            Q(Exists(TimeSlot.objects.filter(phase__job=OuterRef("pk"), user=user)))
            | Q(
                Exists(
                    Phase.objects.filter(job=OuterRef("pk")).filter(
                        Q(report_author=user) | Q(project_lead=user)
                    )
                )
            )
            | Q(
                Exists(
                    Job.scoped_by.through.objects.filter(
                        job_id=OuterRef("pk"), user_id=user.pk
                    )
                )
            )
            | Q(account_manager=user)  # filter for account_manager
            | Q(dep_account_manager=user),  # filter for dep_account_manager
            status__in=JobStatuses.ACTIVE_STATUSES,  # Include active job statuses only
        )
        return matches


class Job(models.Model):
    STATE_ERROR = "Invalid state or permissions."

    objects = JobManager()

    # IDs
    id = models.IntegerField(editable=False, verbose_name="Job ID")
    db_id = models.AutoField(
        primary_key=True, editable=False, verbose_name="Database ID"
    )
    slug = models.UUIDField(
        default=uuid.uuid4, editable=False, unique=True, db_index=True
    )

    unit = models.ForeignKey(
        "OrganisationalUnit", related_name="jobs", on_delete=models.CASCADE
    )
    status = FSMIntegerField(
        verbose_name="Job Status",
        help_text="Current state of the job",
        choices=JobStatuses.CHOICES,
        default=JobStatuses.DRAFT,
    )
    status_changed_date = MonitorField(monitor="status")
    is_imported = models.BooleanField(default=False)
    external_id = models.CharField(
        verbose_name="External ID",
        db_index=True,
        unique=True,
        max_length=255,
        blank=True,
        null=True,
        default=None,
        help_text="Optional: External reference ID"
    )
    title = models.CharField("Job Title", max_length=250)
    history = HistoricalRecords()
    data = JSONField(verbose_name="Data", null=True, blank=True, default=dict)
    notes = GenericRelation(Note)
    desired_start_date = models.DateField(
        "Start Date",
        null=True,
        blank=True,
        help_text="If set, will override scheduled dates",
    )
    desired_delivery_date = models.DateField(
        "Delivery date",
        null=True,
        blank=True,
        db_index=True,
        help_text="If set, will override scheduled dates",
    )

    # Client fields
    client = models.ForeignKey("Client", related_name="jobs", on_delete=models.CASCADE)
    primary_client_poc = models.ForeignKey(
        "Contact",
        verbose_name="Primary Point of Contact",
        related_name="jobs_poc_for",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    additional_contacts = models.ManyToManyField(
        "Contact", related_name="jobs_contact_for", blank=True
    )
    associated_framework = models.ForeignKey(
        FrameworkAgreement,
        related_name="associated_jobs",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    # Sales fields
    revenue = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        null=True,
        blank=True,
        verbose_name="Sales Revenue",
        help_text="Optional: Cost of the job to the client",
    )
    support_premium_override = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Support Premium Override (%)",
        help_text="Per-job override of the support pool premium %. Blank = unit/global default.",
        validators=[MinValueValidator(Decimal("0"))],
    )
    support_profile = models.ForeignKey(
        "SupportProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="jobs",
        verbose_name="Support Profile",
        help_text="The unit support team (and premium) this job's pool uses.",
    )

    def get_effective_premium(self):
        """Resolve the support-pool premium % for this job.

        Precedence: per-job ``support_premium_override`` → the job's support
        profile's ``premium_percent`` → the unit's ``support_premium_default``
        → global constance ``SUPPORT_PREMIUM_DEFAULT``.
        Returns a Decimal percent (e.g. ``Decimal("8")``).
        """
        if self.support_premium_override is not None:
            return Decimal(self.support_premium_override)
        profile = self.support_profile
        if (
            profile is not None
            and profile.unit_id == self.unit_id
            and profile.premium_percent is not None
        ):
            return Decimal(profile.premium_percent)
        if self.unit_id and self.unit.support_premium_default is not None:
            return Decimal(self.unit.support_premium_default)
        return Decimal(str(config.SUPPORT_PREMIUM_DEFAULT))

    def get_support_budget(self, on_date=None):
        """Read-only computed support-team budget for this job. See
        :mod:`chaotica_utils.utils.support_budget`."""
        from chaotica_utils.utils.support_budget import build_job_support_budget

        return build_job_support_budget(self, on_date=on_date)

    def get_billing_assignments(self):
        """Billing-code assignments attached directly to this job."""
        return self.billing_code_assignments.select_related("code")

    @property
    def charge_codes(self):
        """Backwards-compatible accessor: the distinct billing codes on this job.

        Historically ``charge_codes`` was a ``ManyToManyField``; it is now backed
        by :class:`BillingCodeAssignment` rows. Kept as a property returning a
        queryset so existing call sites (``job.charge_codes.all``) keep working.
        """
        from ..models import BillingCode

        return BillingCode.objects.filter(assignments__job=self).distinct()

    def staff_cost(self):
        from chaotica_utils.models import UserCost

        from ..models import TimeSlot

        # One rates query for everyone, and one User instance per person so
        # the business-hours memo is shared (was ~4 queries per slot).
        slots = list(
            TimeSlot.objects.filter(phase__job=self).prefetch_related("user")
        )
        rates = {}
        for rate in UserCost.objects.filter(user_id__in={s.user_id for s in slots}):
            rates.setdefault(rate.user_id, []).append(rate)  # newest first
        return sum((slot.cost(rates.get(slot.user_id, [])) for slot in slots), 0)

    @property
    def profit_perc(self):
        if self.revenue:
            return round((self.profit / self.revenue) * 100, 2)
        else:
            return 0

    @property
    def profit(self):
        staff_cost = self.staff_cost()
        if self.revenue is not None:
            return self.revenue - staff_cost
        else:
            return 0 - staff_cost

    @property
    def average_day_rate(self):
        if not self.revenue:
            return Decimal(0)
        # Calculate profit and return as a Decimal
        # Profit is calculated as basically revenue - costs
        days = self.get_total_scoped_days()
        if days > 0:
            return round(self.revenue / days, 2)
        else:
            return Decimal(0)

    def has_staff_with_missing_costs(self):
        scheduled_users = self.team_scheduled()
        if scheduled_users:
            for user in scheduled_users:
                if user.current_cost() is None:
                    return True
        return False

    # People Fields
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Created By",
        related_name="jobs_created",
        on_delete=models.SET(get_sentinel_user),
    )
    account_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Account Manager",
        related_name="jobs_am_for",
        on_delete=models.SET(get_sentinel_user),
    )
    dep_account_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Deputy Account Manager",
        null=True,
        blank=True,
        related_name="jobs_dam_for",
        on_delete=models.SET(get_sentinel_user),
    )

    # Related jobs
    previous_jobs = models.ManyToManyField(
        "Job", related_name="associated_jobs", blank=True
    )
    links = models.ManyToManyField("Link", related_name="jobs", blank=True)

    # # Required Groups
    # associated_teams = models.ManyToManyField(
    #     Team,
    #     related_name='jobs',
    #     blank=True)
    # enforce_team_membership = models.BooleanField(default=False,
    #     help_text="Setting to true allows only users who are a member of the associated teams to be selected")

    ## General Scoping Fields
    scoped_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="engagements_that_scoped",
        limit_choices_to=models.Q(is_active=True),
        blank=True,
    )

    scoped_signed_off_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="engagements_that_signed_off_scope",
        limit_choices_to=models.Q(is_active=True),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )

    # Services that may be required - only used at draft and scoping stage
    indicative_services = models.ManyToManyField("Service", blank=True)

    # General engagement info
    additional_kit_required = models.BooleanField("Additional kit required", null=True)
    additional_kit_info = BleachField(null=True, blank=True)
    kit_sourced_by_client = models.BooleanField(default=False)

    # Restrictions
    is_restricted = models.BooleanField(
        "Is the engagement Protectively Marked", null=True
    )
    restricted_detail = models.IntegerField(
        "GSC level", choices=RestrictedClassifications.CHOICES, null=True, blank=True
    )

    # General scope info
    bespoke_project = models.BooleanField("Bespoke Project", default=False)
    report_to_third_party = models.BooleanField("Report to 3rd party", default=False)
    is_time_limited = models.BooleanField("Time Limited", default=False)
    retest_included = models.BooleanField(default=False)
    technically_complex_test = models.BooleanField(
        "Does the job involve complex tech", default=False
    )
    high_risk = models.BooleanField("High Risk", default=False)
    reasons_for_high_risk = BleachField(null=True, blank=True)

    # Main info
    overview = BleachField(blank=True, null=True)

    # Dates
    scoping_requested_on = models.DateTimeField(
        "Scoping requested on", null=True, blank=True
    )
    scoping_completed_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Job"
        ordering = ["-id"]

    def __str__(self):
        return "{id}: {title}".format(id=self.id, title=self.title)

    def short_str(self):
        return "{client}/{id}".format(client=self.client, id=self.id)

    def fire_status_notification(self, target_status):
        email_template = "emails/job_content.html"

        if target_status == JobStatuses.PENDING_SCOPE:
            # Notify scoping team
            notification = AppNotification(
                notification_type=NotificationTypes.JOB_PENDING_SCOPING,
                title="Job: Pending Scope",
                message=f"{self} has just been marked as ready to scope.",
                email_template=email_template,
                link=self.get_absolute_url(),
                entity_type=self.__class__.__name__,
                entity_id=self.id,
                metadata={
                    "job": self,
                }
            )

            send_notifications(notification, extra_recipients=config.NOTIFICATION_POOL_SCOPING_EMAIL_RCPTS)

        elif target_status == JobStatuses.PENDING_SCOPING_SIGNOFF:
            # Notify scoping team

            notification = AppNotification(
                notification_type=NotificationTypes.JOB_PENDING_SCOPE_SIGNOFF,
                title="Job: Scope Pending Signoff",
                message=f"{self} is ready for scope signoff.",
                email_template=email_template,
                link=self.get_absolute_url(),
                entity_type=self.__class__.__name__,
                entity_id=self.id,
                metadata={
                    "job": self,
                }
            )
            
            send_notifications(notification, extra_recipients=config.NOTIFICATION_POOL_SCOPING_EMAIL_RCPTS)

        elif target_status == JobStatuses.SCOPING_COMPLETE:
            # Notify scheduling team

            notification = AppNotification(
                notification_type=NotificationTypes.JOB_SCOPING_COMPLETE,
                title="Job: Ready to Schedule",
                message=f"The scope for {self} has been signed off and is ready for scheduling.",
                email_template=email_template,
                link=self.get_absolute_url(),
                entity_type=self.__class__.__name__,
                entity_id=self.id,
                metadata={
                    "job": self,
                }
            )

            send_notifications(notification, extra_recipients=config.NOTIFICATION_POOL_SCHEDULING_EMAIL_RCPTS)

    _start_date = models.DateField(
        "Start Date",
        null=True,
        blank=True,
        help_text="If left blank, this will be automatically determined from scheduled slots",
    )

    def start_date(self):
        if self.desired_start_date:
            return self.desired_start_date

        if self._start_date:
            return self._start_date

    def update_stored_dates(self):
        from ..models import TimeSlot

        # Start date first...
        # Calculate start from first delivery slot
        if TimeSlot.objects.filter(
            phase__job=self, deliveryRole=TimeSlotDeliveryRole.DELIVERY
        ).exists():
            self._start_date = (
                TimeSlot.objects.filter(
                    phase__job=self, deliveryRole=TimeSlotDeliveryRole.DELIVERY
                )
                .order_by("start")
                .first()
                .start.date()
            )

        self.save()

    _delivery_date = models.DateField(
        "Delivery date",
        null=True,
        blank=True,
        db_index=True,
        help_text="If left blank, this will be automatically determined from scheduled slots",
    )

    def delivery_date(self):
        if self.desired_delivery_date:
            return self.desired_delivery_date

        if self._delivery_date:
            return self._delivery_date

    @property
    def status_bs_colour(self):
        return JobStatuses.BS_COLOURS[self.status][1]

    @property
    def inScoping(self):
        return (
            self.status == JobStatuses.SCOPING
            or self.status == JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED
        )

    def isOverdue(self):
        today = timezone.now().date()
        if self.delivery_date() is not None:
            return self.delivery_date() <= today
        else:
            return False

    def get_user_notes(self):
        return [n for n in self.notes.all() if not n.is_system_note]

    def get_total_scoped_hours(self):
        phases = self.phases.all()
        total_scoped = Decimal(0.0)
        for phase in phases:
            total_scoped = total_scoped + phase.get_total_scoped_hours()
        return total_scoped

    def get_total_scoped_days(self):
        hid = self.get_hours_in_day()
        return round(self.get_total_scoped_hours() / hid, 2) if hid else 0

    # Gets scheduled users and assigned users (e.g. lead/author/qa etc)
    def team(self):
        from jobtracker.models import TimeSlot

        ids = set(
            TimeSlot.objects.filter(phase__job=self)
            .values_list('user_id', flat=True)
            .distinct()
        )

        # Phase-level roles — one query for all four fields
        for row in self.phases.values_list('project_lead', 'report_author', 'techqa_by', 'presqa_by'):
            ids.update(pk for pk in row if pk is not None)

        ids = list(ids)

        if self.created_by and self.created_by.pk not in ids:
            ids.append(self.created_by.pk)
        if self.account_manager and self.account_manager.pk not in ids:
            ids.append(self.account_manager.pk)
        if self.dep_account_manager and self.dep_account_manager.pk not in ids:
            ids.append(self.dep_account_manager.pk)
        for scoper in self.scoped_by.all():
            if scoper and scoper.pk not in ids:
                ids.append(scoper.pk)
        if self.scoped_signed_off_by and self.scoped_signed_off_by.pk not in ids:
            ids.append(self.scoped_signed_off_by.pk)
        if ids:
            return User.objects.filter(pk__in=ids)
        else:
            return User.objects.none()

    def phase_role_holder_ids(self):
        """PKs of users holding a phase role (lead / author / TQA / PQA)."""
        ids = set()
        for row in self.phases.values_list('project_lead', 'report_author', 'techqa_by', 'presqa_by'):
            ids.update(pk for pk in row if pk is not None)
        return ids

    def team_scheduled(self):
        from ..models import TimeSlot

        user_ids = (
            TimeSlot.objects.filter(phase__job=self)
            .values_list("user", flat=True)
            .distinct()
        )
        if user_ids:
            return User.objects.filter(pk__in=user_ids)
        else:
            return None

    def get_activeTimeSlotDeliveryRoles(self):
        from ..models import TimeSlot

        my_slots = (
            TimeSlot.objects.filter(phase__job=self)
            .values_list("deliveryRole", flat=True)
            .distinct()
        )
        return my_slots

    def get_hours_in_day(self):
        # Priority is client
        hours = self.client.hours_in_day
        if not hours:
            from django.conf import settings
            hours = Decimal(settings.DEFAULT_HOURS_IN_DAY)
        return hours

    def total_hrs_scheduled(self):
        from ..models import TimeSlot

        slots = TimeSlot.objects.filter(phase__job=self)
        total = Decimal()
        for slot in slots:
            total = total + slot.get_business_hours()
        return total

    def total_days_scheduled(self):
        hrs = self.total_hrs_scheduled()
        hid = self.get_hours_in_day()
        return round(hrs / hid, 1) if hid else 0

    def _get_scheduled_totals(self):
        # One pass over the job's slots (was one query per delivery role).
        if not hasattr(self, "_scheduled_totals_cache"):
            from ..models import TimeSlot

            totals = {}
            for slot in TimeSlot.objects.filter(phase__job=self).select_related("user"):
                role = slot.deliveryRole
                totals[role] = totals.get(role, Decimal(0)) + slot.get_business_hours()
            self._scheduled_totals_cache = totals
        return self._scheduled_totals_cache

    def get_all_total_scheduled_by_type(self):
        totals = self._get_scheduled_totals()
        return {role: totals.get(role, Decimal()) for role, _ in TimeSlotDeliveryRole.CHOICES}

    def get_total_scheduled_by_type(self, slot_type):
        return self._get_scheduled_totals().get(slot_type, Decimal())

    def get_all_total_scoped_by_type(self):
        data = dict()
        hours_in_day = self.get_hours_in_day()
        for state in TimeSlotDeliveryRole.CHOICES:
            hrs = self.get_total_scoped_by_type(state[0])
            data[state[0]] = {
                "type": state[1],
                "hrs": hrs,
                "days": round(hrs / hours_in_day, 2) if hours_in_day else 0,
            }
        return data

    def get_total_scoped_days_by_type(self, slot_type):
        return round(self.get_total_scoped_by_type(slot_type) / self.get_hours_in_day(), 2)

    def get_total_scheduled_days_by_type(self, slot_type):
        return round(self.get_total_scheduled_by_type(slot_type) / self.get_hours_in_day(), 2)

    def get_total_scoped_by_type(self, slot_type):
        phases = self.phases.all()
        total_scoped = Decimal(0.0)
        for phase in phases:
            # Ugly.... but yolo
            if slot_type == TimeSlotDeliveryRole.DELIVERY:
                total_scoped = total_scoped + phase.delivery_hours
            elif slot_type == TimeSlotDeliveryRole.REPORTING:
                total_scoped = total_scoped + phase.reporting_hours
            elif slot_type == TimeSlotDeliveryRole.MANAGEMENT:
                total_scoped = total_scoped + phase.mgmt_hours
            elif slot_type == TimeSlotDeliveryRole.QA:
                total_scoped = total_scoped + phase.qa_hours
            elif slot_type == TimeSlotDeliveryRole.OVERSIGHT:
                total_scoped = total_scoped + phase.oversight_hours
            elif slot_type == TimeSlotDeliveryRole.DEBRIEF:
                total_scoped = total_scoped + phase.debrief_hours
            elif slot_type == TimeSlotDeliveryRole.CONTINGENCY:
                total_scoped = total_scoped + phase.contingency_hours
            elif slot_type == TimeSlotDeliveryRole.OTHER:
                total_scoped = total_scoped + phase.other_hours
        return total_scoped

    def get_slot_type_usage_perc(self, slot_type):
        # First, get the total for the slot_type
        total_scoped = self.get_total_scoped_by_type(slot_type)
        # Now lets get the scheduled amount
        scheduled = self.get_total_scheduled_by_type(slot_type)
        if scheduled == 0.0:
            return 0
        if total_scoped == 0.0 and scheduled > 0.0:
            # Over scheduled and scope is zero
            return 100
        return round(100 * float(scheduled) / float(total_scoped), 2)

    def get_system_notes(self):
        from chaotica_utils.audit import object_audit_events

        return object_audit_events(self)

    def get_absolute_url(self):
        return reverse("job_detail", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        # This means that the model isn't saved to the database yet
        if self._state.adding:
            # Get the maximum display_id value from the database
            last_id = Job.objects.all().aggregate(largest=models.Max("id"))["largest"]

            # aggregate can return None! Check it first.
            # If it isn't none, just use the last ID specified (which should be the greatest) and add one to it
            if last_id is not None:
                self.id = last_id + 1
            else:
                # We haven't got any other jobs so lets just start from the default
                self.id = int(config.JOB_ID_START) + 1

        return super().save(*args, **kwargs)
    
    
    def follow(self, user):
        """Let a user follow this job/phase to receive notifications"""
        from notifications.models import NotificationSubscription
        from notifications.enums import NotificationTypes
        
        # Create subscriptions for relevant notification types
        notification_types = [
            NotificationTypes.JOB_STATUS_CHANGE,
            # Add other relevant notification types
        ]
        
        for notification_type in notification_types:
            NotificationSubscription.objects.get_or_create(
                user=user,
                notification_type=notification_type,
                entity_type=self.__class__.__name__,
                entity_id=self.id,
                defaults={
                    'email_enabled': True,
                    'in_app_enabled': True
                }
            )
        
        return True

    def unfollow(self, user):
        """Stop a user from following this job/phase"""
        from notifications.models import NotificationSubscription
        
        NotificationSubscription.objects.filter(
            user=user,
            entity_type=self.__class__.__name__,
            entity_id=self.id
        ).delete()
        
        return True

    #### FSM Methods
    MOVED_TO = "Moved to "

    # PENDING_SCOPE
    @transition(
        field=status, source=JobStatuses.DRAFT, target=JobStatuses.PENDING_SCOPE
    )
    def to_pending_scope(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + JobStatuses.CHOICES[JobStatuses.PENDING_SCOPE][1],
            author=user,
        )
        self.scoping_requested_on = timezone.now()
        self.fire_status_notification(JobStatuses.PENDING_SCOPE)

    def can_proceed_to_pending_scope(self):
        return can_proceed(self.to_pending_scope)

    def can_to_pending_scope(self, notify_request=None):
        _can_proceed = True
        primary_poc_required = False
        # Do logic checks
        ## Check if we have an account manager
        if not self.account_manager:
            if notify_request:
                messages.add_message(
                    notify_request, messages.ERROR, "No Account Manager assigned."
                )
            _can_proceed = False

        ## Check if we have a primary PoC
        if not self.primary_client_poc and primary_poc_required:
            if notify_request:
                messages.add_message(
                    notify_request,
                    messages.ERROR,
                    "No Client Point of Contact assigned.",
                )
            _can_proceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_pending_scope)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.STATE_ERROR)
            _can_proceed = False
        return _can_proceed

    # SCOPING
    @transition(
        field=status,
        source=[JobStatuses.PENDING_SCOPE, JobStatuses.SCOPING_COMPLETE, JobStatuses.PENDING_SCOPING_SIGNOFF],
        target=JobStatuses.SCOPING,
    )
    def to_scoping(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + JobStatuses.CHOICES[JobStatuses.SCOPING][1],
            author=user,
        )
        self.fire_status_notification(JobStatuses.SCOPING)

    def can_proceed_to_scoping(self):
        return can_proceed(self.to_scoping)

    def can_to_scoping(self, notify_request=None, user=None):
        _can_proceed = True
        user = _acting_user(notify_request, user)
        # Do logic checks
        # If no person is defined as scoped by, warn we'll set ourselves
        if self.status == JobStatuses.SCOPING_COMPLETE:
            if notify_request:
                messages.add_message(
                    notify_request,
                    messages.INFO,
                    "The scope will need to be signed off again.",
                )

        if not self.scoped_by.all() and user is not None:
            if user.has_perm("can_scope_jobs", self.unit):
                if notify_request:
                    messages.add_message(
                        notify_request,
                        messages.INFO,
                        "No one assigned to scope. You will automatically be assigned to scope this job.",
                    )
            else:
                if notify_request:
                    messages.add_message(
                        notify_request,
                        messages.ERROR,
                        "No one assigned to scope. You do not have permission to scope this job.",
                    )
                _can_proceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_scoping)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.STATE_ERROR)
            _can_proceed = False
        return _can_proceed

    # SCOPING_ADDITIONAL_INFO_REQUIRED
    @transition(
        field=status,
        source=JobStatuses.SCOPING,
        target=JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED,
    )
    def to_additional_scope_req(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO
            + JobStatuses.CHOICES[JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED][1],
            author=user,
        )
        self.fire_status_notification(JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED)

    def can_proceed_to_additional_scope_req(self):
        return can_proceed(self.to_additional_scope_req)

    def can_to_additional_scope_req(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_additional_scope_req)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.STATE_ERROR)
            _can_proceed = False
        return _can_proceed

    # PENDING_SCOPING_SIGNOFF
    @transition(
        field=status,
        source=[JobStatuses.SCOPING, JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED],
        target=JobStatuses.PENDING_SCOPING_SIGNOFF,
    )
    def to_scope_pending_signoff(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + JobStatuses.CHOICES[JobStatuses.PENDING_SCOPING_SIGNOFF][1],
            author=user,
        )
        self.fire_status_notification(JobStatuses.PENDING_SCOPING_SIGNOFF)

    def can_proceed_to_scope_pending_signoff(self):
        return can_proceed(self.to_scope_pending_signoff)

    def can_to_scope_pending_signoff(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        ## Check fields are populated
        if not self.overview:
            if notify_request:
                messages.add_message(
                    notify_request, messages.ERROR, "Job overview missing."
                )
            _can_proceed = False

        if (
            self.high_risk or self.technically_complex_test
        ) and not self.reasons_for_high_risk:
            if notify_request:
                messages.add_message(
                    notify_request,
                    messages.ERROR,
                    "Flagged as complex or high risk but no detail entered.",
                )
            _can_proceed = False

        if not self.phases.all():
            if notify_request:
                messages.add_message(
                    notify_request, messages.ERROR, "No phases defined"
                )
            _can_proceed = False

        for phase in self.phases.all().exclude(status__in=PhaseStatuses.INACTIVE_STATUSES):
            if phase.get_total_scoped_hours() == Decimal(0.0):
                if notify_request:
                    messages.add_message(
                        notify_request,
                        messages.WARNING,
                        "Phase with no hours: " + str(phase),
                    )

        # Do general check
        can_proceed_result = can_proceed(self.to_scope_pending_signoff)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.STATE_ERROR)
            _can_proceed = False
        return _can_proceed

    # SCOPING_COMPLETE
    @transition(
        field=status,
        source=JobStatuses.PENDING_SCOPING_SIGNOFF,
        target=JobStatuses.SCOPING_COMPLETE,
    )
    def to_scope_complete(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + JobStatuses.CHOICES[JobStatuses.SCOPING_COMPLETE][1],
            author=user,
        )
        self.scoping_completed_date = timezone.now()
        if user:
            self.scoped_signed_off_by = user

        # update all phases to pending scheduling
        for phase in self.phases.all():
            if phase.can_to_pending_sched():
                phase.to_pending_sched()
                phase.save()

        self.fire_status_notification(JobStatuses.SCOPING_COMPLETE)

    def can_proceed_to_scope_complete(self):
        return can_proceed(self.to_scope_complete)

    def can_to_scope_complete(self, notify_request=None):
        _can_proceed = True
        # Do logic checks
        #
        ## TODO: Setup a `can_signoff_own_scopes` permission
        if notify_request:
            # We have a request, check if we've scoped it...
            if notify_request.user.has_perm("can_signoff_scopes", self.unit):
                if notify_request.user in self.scoped_by.all():
                    # Yup, we've scoped it - check for permission...
                    if not notify_request.user.has_perm(
                        "can_signoff_own_scopes", self.unit
                    ):
                        messages.add_message(
                            notify_request,
                            messages.ERROR,
                            "You do not have permission to sign off your own scope.",
                        )
                        _can_proceed = False
                    else:
                        # We can sign off our own scopes - warn!
                        messages.add_message(
                            notify_request,
                            messages.INFO,
                            "Be aware - you are about to sign off your own scope!",
                        )
                else:
                    messages.add_message(
                        notify_request,
                        messages.INFO,
                        "This will assign you as approver to this scope",
                    )

            else:
                # We don't have permission to signoff scopes!
                messages.add_message(
                    notify_request,
                    messages.ERROR,
                    "You do not have permission to sign off scopes.",
                )
                _can_proceed = False

        ## Check fields are populated
        if not self.overview:
            if notify_request:
                messages.add_message(
                    notify_request, messages.ERROR, "Job overview missing."
                )
            _can_proceed = False

        if (
            self.high_risk or self.technically_complex_test
        ) and not self.reasons_for_high_risk:
            if notify_request:
                messages.add_message(
                    notify_request,
                    messages.ERROR,
                    "Flagged as complex or high risk but no detail entered.",
                )
            _can_proceed = False

        if not self.phases.all():
            if notify_request:
                messages.add_message(
                    notify_request, messages.ERROR, "No phases defined"
                )
            _can_proceed = False

        for phase in self.phases.all().exclude(status__in=PhaseStatuses.INACTIVE_STATUSES):
            if phase.get_total_scoped_hours() == Decimal(0.0):
                if notify_request:
                    messages.add_message(
                        notify_request,
                        messages.WARNING,
                        "Phase with no hours: " + str(phase),
                    )

        # Do general check
        can_proceed_result = can_proceed(self.to_scope_complete)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.STATE_ERROR)
            _can_proceed = False
        return _can_proceed

    # PENDING_START
    @transition(
        field=status,
        source=JobStatuses.SCOPING_COMPLETE,
        target=JobStatuses.PENDING_START,
    )
    def to_pending_start(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + JobStatuses.CHOICES[JobStatuses.PENDING_START][1],
            author=user,
        )
        self.fire_status_notification(JobStatuses.PENDING_START)

    def can_proceed_to_pending_start(self):
        return can_proceed(self.to_pending_start)

    def can_to_pending_start(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_pending_start)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.STATE_ERROR)
            _can_proceed = False
        return _can_proceed

    # IN_PROGRESS
    @transition(
        field=status,
        source=[JobStatuses.SCOPING_COMPLETE, JobStatuses.PENDING_START],
        target=JobStatuses.IN_PROGRESS,
    )
    def to_in_progress(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + JobStatuses.CHOICES[JobStatuses.IN_PROGRESS][1],
            author=user,
        )
        self.fire_status_notification(JobStatuses.IN_PROGRESS)

    def can_proceed_to_in_progress(self):
        return can_proceed(self.to_in_progress)

    def can_to_in_progress(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_in_progress)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.STATE_ERROR)
            _can_proceed = False
        return _can_proceed

    def new_phase_block_reason(self):
        """Why phases can't be added to this job right now, or ``None``.

        Phases can be added from Scoping through In Progress. A completed job
        must be reopened first so the new work is scoped and can't hide behind
        the Completed status (it'd be missing from the dashboard and queues).
        """
        if JobStatuses.SCOPING <= self.status <= JobStatuses.IN_PROGRESS:
            return None
        if self.status == JobStatuses.COMPLETED:
            return "This job is Completed. Reopen it to add more phases."
        if self.status < JobStatuses.SCOPING:
            return "Phases can be added once scoping has started."
        return "This job is {}, so phases can't be added.".format(
            self.get_status_display()
        )

    def all_phases_finished(self, exclude_phase=None):
        """True when no phase still needs work, so the job can be completed.

        Delivered, cancelled, deleted and archived phases count as finished;
        anything before delivery, or postponed, does not.
        """
        phases = self.phases.all()
        if exclude_phase is not None:
            phases = phases.exclude(pk=exclude_phase.pk)
        return not phases.filter(
            Q(status__lt=PhaseStatuses.DELIVERED) | Q(status=PhaseStatuses.POSTPONED)
        ).exists()

    def has_delivered_work(self, exclude_phase=None):
        """True if at least one phase was delivered (``exclude_phase`` is the
        one being delivered right now, which counts)."""
        if exclude_phase is not None:
            return True
        return self.phases.filter(
            Q(status=PhaseStatuses.DELIVERED)
            | Q(status=PhaseStatuses.ARCHIVED, actual_delivery_date__isnull=False)
        ).exists()

    # COMPLETED
    @transition(
        field=status, source=JobStatuses.IN_PROGRESS, target=JobStatuses.COMPLETED
    )
    def to_complete(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + JobStatuses.CHOICES[JobStatuses.COMPLETED][1],
            author=user,
        )
        self.fire_status_notification(JobStatuses.COMPLETED)

    def can_proceed_to_complete(self):
        return can_proceed(self.to_complete)

    def can_to_complete(self, notify_request=None, exclude_phase=None):
        _can_proceed = True
        # Do logic checks: the same rule as the automatic completion paths.
        # ``exclude_phase`` is the phase being delivered right now (its new
        # status isn't saved yet).
        if not self.all_phases_finished(exclude_phase=exclude_phase):
            if notify_request:
                messages.add_message(
                    notify_request,
                    messages.ERROR,
                    "One or more phases are still in progress (or postponed). "
                    "Deliver, cancel or delete them first.",
                )
            _can_proceed = False
        # A job whose phases were all cancelled delivered nothing — that isn't
        # "Completed" (it'd look like delivered work). It shows in the Stale
        # alarms for someone to close as Lost / delete, or add work to.
        elif not self.has_delivered_work(exclude_phase=exclude_phase):
            if notify_request:
                messages.add_message(
                    notify_request,
                    messages.ERROR,
                    "No phase on this job was delivered, so it can't be marked "
                    "Completed. Close it another way (e.g. Lost or Delete) instead.",
                )
            _can_proceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_complete)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.STATE_ERROR)
            _can_proceed = False
        return _can_proceed

    # REOPEN (COMPLETED -> SCOPING)
    @transition(
        field=status, source=JobStatuses.COMPLETED, target=JobStatuses.SCOPING
    )
    def to_reopen(self, user=None, reason=""):
        """Reopen a completed job for more work (e.g. a new phase).

        Goes back to Scoping (not In Progress) so the auto-complete cron can't
        immediately re-close it while every existing phase is still finished;
        the new work is scoped and signed off as normal.
        """
        log_system_activity(
            self,
            "Reopened: moved from {} to {}. Reason: {}".format(
                JobStatuses.CHOICES[JobStatuses.COMPLETED][1],
                JobStatuses.CHOICES[JobStatuses.SCOPING][1],
                reason or "none given",
            ),
            author=user,
            category=AuditCategory.WORKFLOW,
            verb=AuditVerb.STATUS_CHANGE,
        )
        self.fire_status_notification(JobStatuses.SCOPING)

    def can_proceed_to_reopen(self):
        return can_proceed(self.to_reopen)

    def can_to_reopen(self, notify_request=None):
        _can_proceed = True
        if notify_request:
            messages.add_message(
                notify_request,
                messages.INFO,
                "The job goes back to Scoping: add or update phases, then sign "
                "the scope off again. Delivered phases are left as they are.",
            )
        can_proceed_result = can_proceed(self.to_reopen)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.STATE_ERROR)
            _can_proceed = False
        return _can_proceed

    # REOPEN FOR A PHASE (COMPLETED -> IN_PROGRESS)
    @transition(
        field=status, source=JobStatuses.COMPLETED, target=JobStatuses.IN_PROGRESS
    )
    def to_reopen_for_phase(self, phase, user=None, reason=""):
        """A phase on this completed job was reopened (or found unfinished):
        put the job back In Progress so the phase is visible again. The
        auto-complete cron re-closes it once that phase is delivered."""
        log_system_activity(
            self,
            "Reopened: moved from {} to {} because {} was reopened. Reason: {}".format(
                JobStatuses.CHOICES[JobStatuses.COMPLETED][1],
                JobStatuses.CHOICES[JobStatuses.IN_PROGRESS][1],
                phase.phase_id,
                reason or "none given",
            ),
            author=user,
            category=AuditCategory.WORKFLOW,
            verb=AuditVerb.STATUS_CHANGE,
        )
        self.fire_status_notification(JobStatuses.IN_PROGRESS)

    # LOST
    @transition(
        field=status,
        source=[
            JobStatuses.DRAFT,
            JobStatuses.PENDING_SCOPE,
            JobStatuses.SCOPING,
            JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED,
            JobStatuses.SCOPING_COMPLETE,
            JobStatuses.PENDING_START,
        ],
        target=JobStatuses.LOST,
    )
    def to_lost(self, user=None):
        log_system_activity(
            self, self.MOVED_TO + JobStatuses.CHOICES[JobStatuses.LOST][1], author=user
        )
        # Cancel any remaining live phases. to_cancelled() also deletes the
        # phase's timeslots, so a lost job stops occupying the schedule
        # (BUG-006). The transition only sets the field in memory, so the
        # phase must be saved (T-01). Delivered/closed phases are left alone.
        for phase in self.phases.filter(status__lt=PhaseStatuses.DELIVERED).exclude(
            status__in=PhaseStatuses.INACTIVE_STATUSES
        ):
            if phase.can_to_cancelled():
                phase.to_cancelled(user=user)
                phase.save()
        self.fire_status_notification(JobStatuses.LOST)

    def can_proceed_to_lost(self):
        return can_proceed(self.to_lost)

    def can_to_lost(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_lost)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.STATE_ERROR)
            _can_proceed = False
        return _can_proceed

    # DELETED
    @transition(field=status, source="+", target=JobStatuses.DELETED)
    def to_delete(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + JobStatuses.CHOICES[JobStatuses.DELETED][1],
            author=user,
        )
        self.fire_status_notification(JobStatuses.DELETED)
        # Cascade the delete to all phases so they don't linger as active
        # phases generating notifications for a deleted job.
        for phase in self.phases.exclude(status=PhaseStatuses.DELETED):
            if phase.can_to_deleted():
                phase.to_deleted(user)
                phase.save()
        # Tidy up dangling subscriptions/opt-outs for this job (no FK cascade).
        from notifications.utils import remove_subscriptions_for_entity

        remove_subscriptions_for_entity(self)

    def can_proceed_to_delete(self):
        return can_proceed(self.to_delete)

    def can_to_delete(self, notify_request=None):
        _can_proceed = True
        # Do logic checks. Phases that are already deleted don't block it.
        for phase in self.phases.exclude(status=PhaseStatuses.DELETED):
            if not phase.can_to_deleted():
                if notify_request:
                    messages.add_message(
                        notify_request,
                        messages.ERROR,
                        "One or more child phases can not be deleted.",
                    )
                _can_proceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_delete)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.STATE_ERROR)
            _can_proceed = False
        return _can_proceed

    # ARCHIVED
    @transition(
        field=status,
        source=[JobStatuses.COMPLETED, JobStatuses.LOST],
        target=JobStatuses.ARCHIVED,
    )
    def to_archive(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + JobStatuses.CHOICES[JobStatuses.ARCHIVED][1],
            author=user,
        )
        self.fire_status_notification(JobStatuses.ARCHIVED)

    def can_proceed_to_archive(self):
        return can_proceed(self.to_archive)

    def can_to_archive(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_archive)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.STATE_ERROR)
            _can_proceed = False
        return _can_proceed


class JobSupportTeamRole(models.Model):
    job = models.ForeignKey(
        Job, on_delete=models.CASCADE, related_name="supporting_team"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="job_support_roles",
        null=True,
        blank=True,
        on_delete=models.SET(get_sentinel_user),
    )
    role = models.IntegerField(
        verbose_name="Role",
        choices=JobSupportRole.CHOICES,
        default=JobSupportRole.OTHER,
    )
    profile_percent = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("100"),
        verbose_name="Profile Allocation (%)",
        help_text="Coverage % (100 = full coverage). Drives this person's share of the support pool.",
        validators=[MinValueValidator(Decimal("0"))],
    )
    is_overridden = models.BooleanField(
        default=False,
        help_text="Set when this row is manually edited, so re-applying the unit "
        "support template leaves it untouched.",
    )
    allocated_hours = models.FloatField(
        verbose_name="Allocated Hours",
        help_text="Hours allocated to this person",
        default=0.0,
    )
    billed_hours = models.FloatField(
        verbose_name="Billed Hours",
        help_text="Hours actually billed from the allocated amount",
        default=0.0,
    )
    history = HistoricalRecords()

    class Meta:
        # One row per person per job: the engine keys members by user.
        unique_together = ["job", "user"]

    def used_perc(self):
        if self.allocated_hours > 0.0:
            return round(100 * self.billed_hours / self.allocated_hours, 2)
        else:
            return 0.0

    def drawn_hours(self):
        """Total hours drawn down from the ledger for this support role."""
        total = self.draws.aggregate(total=models.Sum("hours_drawn"))["total"]
        return total or Decimal("0")


class SupportBudgetDraw(models.Model):
    """A per-period 'cash-out' of budgeted support hours.

    Support members draw down hours each timesheet period. Each draw records
    the LCR it was cashed out at and its money value; remaining budget is
    always computed in money (budget_money − Σ money_drawn), never stored, so
    accumulation carries forward across periods and a later LCR change never
    re-prices past draws. Create draws via
    :func:`chaotica_utils.utils.support_budget.create_support_draw`, which
    enforces the remaining-budget limit.
    """

    support_role = models.ForeignKey(
        JobSupportTeamRole,
        # A cash-out is a financial record: a role with draws can't be deleted
        # (reverse the draws first).
        on_delete=models.PROTECT,
        related_name="draws",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="support_budget_draws",
        null=True,
        blank=True,
        on_delete=models.SET(get_sentinel_user),
        help_text="Denormalised from support_role.user for fast per-user queries.",
    )
    period_start = models.DateField(verbose_name="Period Start")
    period_end = models.DateField(verbose_name="Period End")
    hours_drawn = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name="Hours Drawn",
        help_text="Hours cashed out for this period.",
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    lcr_at_draw = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="LCR at Cash-out",
        help_text="Loaded cost rate (per hour) the hours were valued at.",
    )
    money_drawn = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        verbose_name="Value Drawn",
        help_text="hours_drawn × lcr_at_draw — what this draw consumed of the budget.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="+",
        null=True,
        blank=True,
        on_delete=models.SET(get_sentinel_user),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-period_start"]
        indexes = [
            models.Index(fields=["user", "period_start"]),
        ]

    def __str__(self):
        return "{} {} → {} ({}h)".format(
            str(self.user), self.period_start, self.period_end, self.hours_drawn
        )

    def clean(self):
        super().clean()
        if (
            self.period_start
            and self.period_end
            and self.period_start > self.period_end
        ):
            raise ValidationError(
                {"period_end": "The period end must be on or after its start."}
            )

    def save(self, *args, **kwargs):
        # Keep the denormalised user in sync with the support role.
        if self.user_id is None and self.support_role_id:
            self.user_id = self.support_role.user_id
        super().save(*args, **kwargs)


class SupportDrawDay(models.Model):
    """How a cash-out's hours sit on the timesheet: hours per working day.

    Planned once when the draw is made (whole free days first, see
    :func:`chaotica_utils.utils.support_budget.plan_draw_days`) so the
    Billing Codes page shows what was actually entered. Draws without day
    rows (made before this existed) are spread evenly across the period.
    """

    draw = models.ForeignKey(
        SupportBudgetDraw, on_delete=models.CASCADE, related_name="days"
    )
    day = models.DateField()
    hours = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        ordering = ["day"]
        unique_together = ["draw", "day"]

    def __str__(self):
        return "{} {}h".format(self.day, self.hours)


@receiver(post_save, sender=Job, dispatch_uid="apply_support_template_on_job_create")
def apply_support_template_on_job_create(sender, instance, created, **kwargs):
    """Seed a new job's support team from its unit's default support profile."""
    # Never fire during fixture/dump loads (related rows may not exist yet).
    if kwargs.get("raw"):
        return
    if not created or not instance.unit_id:
        return
    profile = instance.unit.get_default_support_profile()
    if profile is not None:
        profile.apply_to_job(instance)
