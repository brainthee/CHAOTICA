from django.db import models
from jobtracker.enums import TimeSlotDeliveryRole, PhaseStatuses
from django_fsm import FSMIntegerField, transition, can_proceed
from django.conf import settings
from constance import config
from django.utils import timezone
from chaotica_utils.utils import unique_slug_generator
from django.urls import reverse
from simple_history.models import HistoricalRecords
from django.db.models import Q
from django.contrib.contenttypes.fields import GenericRelation
from model_utils.fields import MonitorField
from django.db.models import JSONField
from bs4 import BeautifulSoup
from django.contrib import messages
from chaotica_utils.models import Note, User
from chaotica_utils.enums import NotificationTypes
from chaotica_utils.tasks import task_send_notifications
from chaotica_utils.utils import AppNotification
from chaotica_utils.views import log_system_activity
from datetime import timedelta
from decimal import Decimal
from django_bleach.models import BleachField
from ..models.job import Job
from ..enums import (
    BOOL_CHOICES,
    TechQARatings,
    PresQARatings,
    FeedbackType,
    JobStatuses,
)
from guardian.shortcuts import get_objects_for_user


class PhaseManager(models.Manager):

    def phases_with_unit_permission(self, user, perm):
        from ..models import OrganisationalUnit

        units = get_objects_for_user(user, perm, klass=OrganisationalUnit)

        matches = self.filter(
            Q(job__unit__in=units),
            status__in=PhaseStatuses.ACTIVE_STATUSES,  # Include active phase statuses only
            job__status__in=JobStatuses.ACTIVE_STATUSES,  # Include active job statuses only
        )
        return matches

    def phases_for_user(self, user):
        # Job's we're interested in:
        # - Scheduled on
        # - Lead/Author of
        # - Scoped while before scoping approved
        matches = self.filter(
            Q(timeslots__user=user)  # Filter by scheduled
            | Q(report_author=user)  # Filter for report author
            | Q(project_lead=user),  # filter for lead
            status__in=PhaseStatuses.ACTIVE_STATUSES,  # Include active phase statuses only
            job__status__in=JobStatuses.ACTIVE_STATUSES,  # Include active job statuses only
        ).distinct()
        return matches


class Phase(models.Model):
    objects = PhaseManager()
    job = models.ForeignKey(Job, related_name="phases", on_delete=models.CASCADE)

    # auto fields
    slug = models.SlugField(null=False, default="", unique=True)
    phase_id = models.CharField(max_length=100, unique=True, verbose_name="Phase ID")

    # misc fields
    history = HistoricalRecords()
    data = JSONField(verbose_name="Data", null=True, blank=True, default=dict)
    is_imported = models.BooleanField(default=False)
    notes = GenericRelation(Note)
    status = FSMIntegerField(
        choices=PhaseStatuses.CHOICES, db_index=True, default=PhaseStatuses.DRAFT
    )

    # Phase info
    phase_number = models.IntegerField(db_index=True, default=0)
    title = models.CharField(max_length=200)

    # General test info
    service = models.ForeignKey(
        "Service",
        null=True,
        blank=True,
        related_name="phases",
        on_delete=models.PROTECT,
    )
    description = BleachField(blank=True, null=True, default="")

    # Requirements
    test_target = BleachField("Test Target URL/IPs/Scope", blank=True, null=True)
    comm_reqs = BleachField("Communication Requirements", blank=True, null=True)

    restrictions = BleachField(
        "Time restrictions / Special requirements", blank=True, null=True
    )
    scheduling_requirements = BleachField(
        "Special requirements for scheduling", blank=True, null=True
    )
    prerequisites = BleachField("Pre-requisites", null=True, blank=True)

    # Key Users
    report_author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="phase_where_report_author",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    project_lead = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="phase_where_project_lead",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    techqa_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="techqaed_phases",
        verbose_name="Tech QA by",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    presqa_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="presqaed_phases",
        verbose_name="Pres QA by",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    required_tqa_updates = models.BooleanField("Required TQA Updates", default=False)
    required_pqa_updates = models.BooleanField("Required PQA Updates", default=False)

    # Logistics
    is_testing_onsite = models.BooleanField("Testing Onsite", default=False)
    is_reporting_onsite = models.BooleanField("Reporting Onsite", default=False)
    location = BleachField("Onsite Location", blank=True, null=True, default="")
    number_of_reports = models.IntegerField(
        default=1,
        help_text="If set to 0, this phase will not go through Technical or Presentation QA",
    )
    report_to_be_left_on_client_site = models.BooleanField(default=False)

    # links
    linkDeliverable = models.TextField(
        default="",
        null=True,
        blank=True,
        verbose_name="Link to Deliverable",
        help_text="Typically this is the content delivered to the client."
    )
    linkTechData = models.TextField(
        default="",
        null=True,
        blank=True,
        verbose_name="Link to Technical Data",
        help_text="All data generated during the job."
    )
    linkReportData = models.TextField(
        default="",
        null=True,
        blank=True,
        verbose_name="Link to Report Data",
        help_text="Data used to generate the report such as checklists or evidence."
    )

    # Desirable dates
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

    due_to_techqa_set = models.DateField(
        "Due to Tech QA",
        null=True,
        blank=True,
        help_text="If left blank, this will be automatically determined from the end of last day of reporting",
    )
    due_to_presqa_set = models.DateField(
        "Due to Pres QA",
        null=True,
        blank=True,
        help_text="If left blank, this will be automatically determined from the end of last day of reporting plus QA days",
    )

    # Status Change Dates
    actual_start_date = models.DateTimeField(
        "Actual start date", null=True, blank=True, db_index=True
    )
    actual_sent_to_tqa_date = models.DateTimeField(
        "Actual sent to TQA date", null=True, blank=True, db_index=True
    )
    actual_sent_to_pqa_date = models.DateTimeField(
        "Actual sent to PQA date", null=True, blank=True, db_index=True
    )
    actual_completed_date = models.DateTimeField(
        "Actual completed date", null=True, blank=True, db_index=True
    )
    actual_delivery_date = models.DateTimeField(
        "Actual delivered date", null=True, blank=True, db_index=True
    )

    cancellation_date = models.DateTimeField(null=True, blank=True)
    pre_checks_done_date = models.DateTimeField(null=True, blank=True)
    status_changed_date = MonitorField(monitor="status")

    def earliest_date(self):
        if self.start_date:
            return self.start_date
        elif self.job.start_date():
            return self.job.start_date()
        else:
            # return today's date
            return timezone.now().today()

    def earliest_scheduled_date(self):
        # Calculate start from first delivery slot
        if self.timeslots.filter(deliveryRole=TimeSlotDeliveryRole.DELIVERY).exists():
            return (
                self.timeslots.filter(deliveryRole=TimeSlotDeliveryRole.DELIVERY)
                .order_by("start")
                .first()
                .start.date()
            )
        else:
            # return today's date
            return timezone.now().today()

    @property
    def start_date(self):
        if self.desired_start_date:
            return self.desired_start_date
        else:
            # Calculate start from first delivery slot
            if self.timeslots.filter(
                deliveryRole=TimeSlotDeliveryRole.DELIVERY
            ).exists():
                return (
                    self.timeslots.filter(deliveryRole=TimeSlotDeliveryRole.DELIVERY)
                    .order_by("-start")
                    .first()
                    .start.date()
                )
            else:
                # No slots - return None
                return None

    @property
    def due_to_techqa(self):
        if self.number_of_reports == 0:
            return None
        if self.due_to_techqa_set:
            return self.due_to_techqa_set
        else:
            # Calculate start from last delivery slot
            if self.timeslots.filter(
                Q(deliveryRole=TimeSlotDeliveryRole.REPORTING)
                | Q(deliveryRole=TimeSlotDeliveryRole.DELIVERY)
            ).exists():
                return (
                    self.timeslots.filter(
                        Q(deliveryRole=TimeSlotDeliveryRole.REPORTING)
                        | Q(deliveryRole=TimeSlotDeliveryRole.DELIVERY)
                    )
                    .order_by("end")
                    .first()
                    .end
                ).date()
            else:
                # No slots - return None
                return None

    @property
    def due_to_presqa(self):
        if self.number_of_reports == 0:
            return None
        if self.due_to_presqa_set:
            return self.due_to_presqa_set
        else:
            # Calculate start from last delivery slot
            if self.timeslots.filter(
                Q(deliveryRole=TimeSlotDeliveryRole.REPORTING)
                | Q(deliveryRole=TimeSlotDeliveryRole.DELIVERY)
            ).exists():
                return (
                    self.timeslots.filter(
                        Q(deliveryRole=TimeSlotDeliveryRole.REPORTING)
                        | Q(deliveryRole=TimeSlotDeliveryRole.DELIVERY)
                    )
                    .order_by("end")
                    .first()
                    .end
                    + timedelta(days=5)
                ).date()
            else:
                # No slots - return None
                return None

    @property
    def delivery_date(self):
        if self.desired_delivery_date:
            return self.desired_delivery_date
        else:
            # Calculate start from first delivery slot
            if self.timeslots.filter(
                Q(deliveryRole=TimeSlotDeliveryRole.REPORTING)
                | Q(deliveryRole=TimeSlotDeliveryRole.DELIVERY)
            ).exists():
                return (
                    self.timeslots.filter(
                        Q(deliveryRole=TimeSlotDeliveryRole.REPORTING)
                        | Q(deliveryRole=TimeSlotDeliveryRole.DELIVERY)
                    )
                    .order_by("end")
                    .first()
                    .end
                    + timedelta(weeks=1)
                ).date()
            else:
                # No slots - return None
                return None

    @property
    def is_delivery_late(self):
        # This relies on delivery_date being valid (which needs it manually set or a timeslot...)
        if self.delivery_date:
            # If no reports - there's nothing to deliver!
            if self.number_of_reports > 0:
                # Two ways to be late - it's not delivered yet and it should have been...
                if self.status < PhaseStatuses.DELIVERED:
                    if self.delivery_date < timezone.now().today().date():
                        return True

                # Or it was delivered but beyond the actual time and we still want to mark it as late
                if (
                    self.actual_delivery_date
                    and self.delivery_date < self.actual_delivery_date.date()
                ):
                    return True
        return False

    @property
    def is_tqa_late(self):
        # This relies on due_to_techqa being valid (which needs it manually set or a timeslot...)
        if self.due_to_techqa:
            # Two ways to be late - it's not in tqa yet and it should have been...
            if self.number_of_reports > 0:
                if self.status < PhaseStatuses.QA_TECH:
                    if self.due_to_techqa < timezone.now().today().date():
                        return True

                # Or it was delivered but beyond the actual time and we still want to mark it as late
                if (
                    self.actual_sent_to_tqa_date
                    and self.due_to_techqa < self.actual_sent_to_tqa_date.date()
                ):
                    return True
        return False

    @property
    def is_pqa_late(self):
        # This relies on due_to_presqa being valid (which needs it manually set or a timeslot...)
        if self.due_to_presqa:
            # Two ways to be late - it's not in tqa yet and it should have been...
            if self.number_of_reports > 0:
                if self.status < PhaseStatuses.QA_PRES:
                    if self.due_to_presqa < timezone.now().today().date():
                        return True

                # Or it was delivered but beyond the actual time and we still want to mark it as late
                if (
                    self.actual_sent_to_pqa_date
                    and self.due_to_presqa < self.actual_sent_to_pqa_date.date()
                ):
                    return True
        return False

    # rating and feedback
    feedback_scope_correct = models.BooleanField(
        "Was scope correct?", choices=BOOL_CHOICES, default=None, null=True, blank=True
    )
    techqa_report_rating = models.IntegerField(
        "Report rating by person doing tech QA",
        choices=TechQARatings.CHOICES,
        null=True,
        blank=True,
    )
    presqa_report_rating = models.IntegerField(
        "PresQA report rating", choices=PresQARatings.CHOICES, null=True, blank=True
    )

    def feedback_scope(self):
        from ..models.common import Feedback

        return Feedback.objects.filter(phase=self, feedbackType=FeedbackType.SCOPE)

    def feedback_techqa(self):
        from ..models.common import Feedback

        return Feedback.objects.filter(phase=self, feedbackType=FeedbackType.TECH)

    def feedback_presqa(self):
        from ..models.common import Feedback

        return Feedback.objects.filter(phase=self, feedbackType=FeedbackType.PRES)

    # Scoped Time
    delivery_hours = models.DecimalField(
        "Delivery Hours",
        max_digits=6,
        default=0,
        decimal_places=3,
    )
    reporting_hours = models.DecimalField(
        "Reporting Hours",
        max_digits=6,
        default=0,
        decimal_places=3,
    )
    mgmt_hours = models.DecimalField(
        "Management Hours",
        max_digits=6,
        default=0,
        decimal_places=3,
    )
    qa_hours = models.DecimalField(
        "QA Hours",
        max_digits=6,
        default=0,
        decimal_places=3,
    )
    oversight_hours = models.DecimalField(
        "Oversight Hours",
        max_digits=6,
        default=0,
        decimal_places=3,
    )
    debrief_hours = models.DecimalField(
        "Debrief Hours",
        max_digits=6,
        default=0,
        decimal_places=3,
    )
    contingency_hours = models.DecimalField(
        "Contingency Hours",
        max_digits=6,
        default=0,
        decimal_places=3,
    )
    other_hours = models.DecimalField(
        "Other Hours",
        max_digits=6,
        default=0,
        decimal_places=3,
    )

    # notification fields
    notifications_workflow_last_fired = models.DateTimeField(blank=True, null=True)
    notifications_late_tqa_last_fired = models.DateTimeField(blank=True, null=True)
    notifications_late_pqa_last_fired = models.DateTimeField(blank=True, null=True)
    notifications_late_delivery_last_fired = models.DateTimeField(blank=True, null=True)

    # change control
    last_modified = models.DateTimeField(auto_now=True)
    last_modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.SET_NULL
    )
    created_date = models.DateTimeField(auto_now_add=True)

    def get_id(self):
        return "{job_id}-{phase_number}".format(
            job_id=self.job.id, phase_number=self.phase_number
        )

    class Meta:
        ordering = ("-job__id", "phase_number")
        unique_together = ("job", "phase_number")
        verbose_name = "Phase"
        permissions = ()

    def __str__(self):
        return "{id}: {title}".format(id=self.get_id(), title=self.title)

    ###########################################
    ## Notifications
    ###########################################

    ## Late to TQA
    def fire_late_to_tqa_notification(self):
        email_template = "emails/phase_content.html"
        now = timezone.now()

        if self.number_of_reports == 0:
            # No reports - nothing to fire!
            return

        if self.is_tqa_late and (
            self.status == PhaseStatuses.IN_PROGRESS
            or self.status == PhaseStatuses.PENDING_TQA
        ):
            # check if we should or not...
            hours_since = 0
            if self.notifications_late_tqa_last_fired:
                time_since = now - self.notifications_late_tqa_last_fired
                hours_since = time_since.days * 24 + time_since.seconds / 3600
            if (
                not self.notifications_late_tqa_last_fired
                or hours_since > config.TQA_LATE_HOURS
            ):
                # Ok, either it's been greater than config.TQA_LATE_HOURS or we haven't sent it...
                # We should tell the team!
                users_to_notify = self.team()
                notice = AppNotification(
                    NotificationTypes.PHASE,
                    "{phase} - is late to Tech QA".format(phase=self),
                    "{phase} is late to Technical QA. Please ensure you communicate with the team when it will be ready.".format(
                        phase=self
                    ),
                    email_template,
                    action_link=self.get_absolute_url(),
                    phase=self,
                )
                task_send_notifications(notice, users_to_notify)
                log_system_activity(self, "Sent TQA late notification")
                self.notifications_late_tqa_last_fired = now
                self.save()

    ## Late to PQA
    def fire_late_to_pqa_notification(self):
        email_template = "emails/phase_content.html"
        now = timezone.now()

        if self.number_of_reports == 0:
            # No reports - nothing to fire!
            return

        if self.is_pqa_late and (
            self.status == PhaseStatuses.PENDING_PQA
            or self.status == PhaseStatuses.QA_TECH
            or self.status == PhaseStatuses.QA_TECH_AUTHOR_UPDATES
        ):
            # check if we should or not...
            should_send = False
            hours_since = 0
            if self.notifications_late_pqa_last_fired:
                time_since = now - self.notifications_late_pqa_last_fired
                hours_since = time_since.days * 24 + time_since.seconds / 3600
            if (
                not self.notifications_late_pqa_last_fired
                or hours_since > config.PQA_LATE_HOURS
            ):
                # Ok, either it's been greater than config.PQA_LATE_HOURS or we haven't sent it...
                # We should tell the team!
                users_to_notify = self.team()
                notice = AppNotification(
                    NotificationTypes.PHASE,
                    "{phase} - is late to Pres QA".format(phase=self),
                    "{phase} is late to Presentation QA. Please ensure you communicate with the team when it will be ready.".format(
                        phase=self
                    ),
                    email_template,
                    action_link=self.get_absolute_url(),
                    phase=self,
                )
                task_send_notifications(notice, users_to_notify)
                log_system_activity(self, "Sent PQA late notification")
                self.notifications_late_pqa_last_fired = now
                self.save()

    ## Late to Delivery
    def fire_late_to_delivery_notification(self):
        email_template = "emails/phase_content.html"
        now = timezone.now()

        if self.number_of_reports == 0:
            # No reports - nothing to fire!
            return

        if self.is_delivery_late:
            # check if we should or not...
            hours_since = 0
            if self.notifications_late_delivery_last_fired:
                time_since = now - self.notifications_late_delivery_last_fired
                hours_since = time_since.days * 24 + time_since.seconds / 3600
            if (
                not self.notifications_late_delivery_last_fired
                or hours_since > config.DELIVERY_LATE_HOURS
            ):
                # Ok, either it's been greater than config.PQA_LATE_HOURS or we haven't sent it...
                # We should tell the team!
                users_to_notify = self.team()
                notice = AppNotification(
                    NotificationTypes.PHASE,
                    "{phase} - is late to Delivery".format(phase=self),
                    "{phase} is late to Delivery. Please ensure you communicate with the team when it will be ready.".format(
                        phase=self
                    ),
                    email_template,
                    action_link=self.get_absolute_url(),
                    phase=self,
                )
                task_send_notifications(notice, users_to_notify)
                log_system_activity(self, "Sent Delivery late notification")
                self.notifications_late_delivery_last_fired = now
                self.save()

    def refire_status_notification(self):
        self.fire_status_notification(self.status)

    def fire_status_notification(self, target_status):
        email_template = "emails/phase_content.html"

        if target_status == PhaseStatuses.PENDING_SCHED:
            users_to_notify = self.job.unit.get_active_members_with_perm(
                "notification_pool_scheduling"
            )
            
            notice = AppNotification(
                NotificationTypes.PHASE,
                "Phase Update - {phase} - Ready for scheduling".format(phase=self),
                "{phase} is ready for Scheduling".format(phase=self),
                email_template,
                action_link=self.get_absolute_url(),
                phase=self,
            )
            task_send_notifications(notice, users_to_notify, config.NOTIFICATION_POOL_SCHEDULING_EMAIL_RCPTS)
            # Lets also update the audit log
            for user in users_to_notify:
                log_system_activity(
                    self,
                    "Ready for Scheduling notification sent to {target}".format(
                        target=user.email
                    ),
                )
            if config.NOTIFICATION_POOL_SCHEDULING_EMAIL_RCPTS:
                log_system_activity(
                    self,
                    "Ready for scheduling notification sent to configured scheduling Pool",
                )

        elif target_status == PhaseStatuses.SCHEDULED_CONFIRMED:
            # Notify project team
            users_to_notify = self.team()
            notice = AppNotification(
                NotificationTypes.PHASE,
                "Phase Update - {phase} - Schedule Confirmed".format(phase=self),
                "The schedule for {phase} is confirmed.".format(phase=self),
                email_template,
                action_link=self.get_absolute_url(),
                phase=self,
            )
            task_send_notifications(notice, users_to_notify)
            # Lets also update the audit log
            for user in users_to_notify:
                log_system_activity(
                    self,
                    "Schedule Confirmed notification sent to {target}".format(
                        target=user.email
                    ),
                )

        elif target_status == PhaseStatuses.PRE_CHECKS:
            # Notify project team
            users_to_notify = self.team()
            notice = AppNotification(
                NotificationTypes.PHASE,
                "Phase Update - {phase} - Ready for Pre-Checks".format(phase=self),
                "{phase} is ready for Pre-checks".format(phase=self),
                email_template,
                action_link=self.get_absolute_url(),
                phase=self,
            )
            task_send_notifications(notice, users_to_notify)
            # Lets also update the audit log
            for user in users_to_notify:
                log_system_activity(
                    self,
                    "Pre-Checks notification sent to {target}".format(
                        target=user.email
                    ),
                )

        elif target_status == PhaseStatuses.CLIENT_NOT_READY:
            # Notify project team
            users_to_notify = self.team()
            notice = AppNotification(
                NotificationTypes.PHASE,
                "Phase Update - {phase} - Client Not Ready".format(phase=self),
                "{phase} has been marked as 'Client Not Ready'!".format(phase=self),
                email_template,
                action_link=self.get_absolute_url(),
                phase=self,
            )
            task_send_notifications(notice, users_to_notify)
            # Lets also update the audit log
            for user in users_to_notify:
                log_system_activity(
                    self,
                    "Client Not Ready notification sent to {target}".format(
                        target=user.email
                    ),
                )

        elif target_status == PhaseStatuses.READY_TO_BEGIN:
            # Notify project team
            users_to_notify = self.team()
            notice = AppNotification(
                NotificationTypes.PHASE,
                "Phase Update - {phase} - Ready To Begin!".format(phase=self),
                "Checks have been carried out and {phase} is ready to begin.".format(
                    phase=self
                ),
                email_template,
                action_link=self.get_absolute_url(),
                phase=self,
            )
            task_send_notifications(notice, users_to_notify)
            # Lets also update the audit log
            for user in users_to_notify:
                log_system_activity(
                    self,
                    "Ready to Begin notification sent to {target}".format(
                        target=user.email
                    ),
                )

        elif target_status == PhaseStatuses.IN_PROGRESS:
            # Notify project team
            users_to_notify = self.team()
            notice = AppNotification(
                NotificationTypes.PHASE,
                "Phase Update - {phase} - In Progress".format(phase=self),
                "{phase} has started".format(phase=self),
                email_template,
                action_link=self.get_absolute_url(),
                phase=self,
            )
            task_send_notifications(notice, users_to_notify)
            # Lets also update the audit log
            for user in users_to_notify:
                log_system_activity(
                    self,
                    "In Progress notification sent to {target}".format(
                        target=user.email
                    ),
                )

        elif target_status == PhaseStatuses.PENDING_TQA:
            # Notify qa team
            if not self.techqa_by:
                # users_to_notify = self.job.unit.get_active_members_with_perm(
                #     "can_tqa_jobs"
                # )
                users_to_notify = self.job.unit.get_active_members_with_perm(
                    "notification_pool_tqa"
                )
            else:
                users_to_notify = User.objects.filter(pk=self.techqa_by.pk)
            notice = AppNotification(
                NotificationTypes.PHASE,
                "Phase Update - {phase} - Ready for Tech QA".format(phase=self),
                "{phase} is ready for Technical QA".format(phase=self),
                email_template,
                action_link=self.get_absolute_url(),
                phase=self,
            )
            task_send_notifications(notice, users_to_notify, config.NOTIFICATION_POOL_TQA_EMAIL_RCPTS)
            # Lets also update the audit log
            for user in users_to_notify:
                log_system_activity(
                    self,
                    "Ready for TQA notification sent to {target}".format(
                        target=user.email
                    ),
                )
            if config.NOTIFICATION_POOL_TQA_EMAIL_RCPTS:
                log_system_activity(
                    self,
                    "Ready for TQA notification sent to configured TQA Pool",
                )


        elif target_status == PhaseStatuses.QA_TECH_AUTHOR_UPDATES:
            users_to_notify = User.objects.filter(pk=self.report_author.pk)
            notice = AppNotification(
                NotificationTypes.PHASE,
                "Phase Update - {phase} - Requires Author Updates".format(phase=self),
                "The report for {phase} requires technical updates.".format(phase=self),
                email_template,
                action_link=self.get_absolute_url(),
                phase=self,
            )
            task_send_notifications(notice, users_to_notify)
            # Lets also update the audit log
            for user in users_to_notify:
                log_system_activity(
                    self,
                    "Requires Author Updates notification sent to {target}".format(
                        target=user.email
                    ),
                )

        elif target_status == PhaseStatuses.PENDING_PQA:
            # Notify qa team
            if not self.presqa_by:
                # users_to_notify = self.job.unit.get_active_members_with_perm(
                #     "can_pqa_jobs"
                # )
                users_to_notify = self.job.unit.get_active_members_with_perm(
                    "notification_pool_pqa"
                )
            else:
                users_to_notify = User.objects.filter(pk=self.presqa_by.pk)
            notice = AppNotification(
                NotificationTypes.PHASE,
                "Phase Update - {phase} - Ready for Pres QA".format(phase=self),
                "{phase} is ready for Presentation QA".format(phase=self),
                email_template,
                action_link=self.get_absolute_url(),
                phase=self,
            )
            task_send_notifications(notice, users_to_notify, config.NOTIFICATION_POOL_PQA_EMAIL_RCPTS)
            # Lets also update the audit log
            for user in users_to_notify:
                log_system_activity(
                    self,
                    "Ready for PQA notification sent to {target}".format(
                        target=user.email
                    ),
                )
            if config.NOTIFICATION_POOL_PQA_EMAIL_RCPTS:
                log_system_activity(
                    self,
                    "Ready for TQA notification sent to configured PQA Pool",
                )

        elif target_status == PhaseStatuses.QA_PRES_AUTHOR_UPDATES:
            users_to_notify = User.objects.filter(pk=self.report_author.pk)
            notice = AppNotification(
                NotificationTypes.PHASE,
                "Phase Update - {phase} - Requires Author Updates".format(phase=self),
                "The report for {phase} requires presentation updates.".format(
                    phase=self
                ),
                email_template,
                action_link=self.get_absolute_url(),
                phase=self,
            )
            task_send_notifications(notice, users_to_notify)
            # Lets also update the audit log
            for user in users_to_notify:
                log_system_activity(
                    self,
                    "Requires Author Updates notification sent to {target}".format(
                        target=user.email
                    ),
                )

        elif target_status == PhaseStatuses.COMPLETED:
            # Notify project team
            users_to_notify = self.team()
            notice = AppNotification(
                NotificationTypes.PHASE,
                "Phase Update - {phase} - Complete".format(phase=self),
                "{phase} is ready for delivery".format(phase=self),
                email_template,
                action_link=self.get_absolute_url(),
                phase=self,
            )
            task_send_notifications(notice, users_to_notify)
            # Lets also update the audit log
            for user in users_to_notify:
                log_system_activity(
                    self,
                    "Completed notification sent to {target}".format(target=user.email),
                )

        elif target_status == PhaseStatuses.POSTPONED:
            users_to_notify = self.team()
            notice = AppNotification(
                NotificationTypes.PHASE,
                "Phase Update - {phase} - Postponed".format(phase=self),
                "{phase} has been postponed!".format(phase=self),
                email_template,
                action_link=self.get_absolute_url(),
                phase=self,
            )
            task_send_notifications(notice, users_to_notify)
            # Lets also update the audit log
            for user in users_to_notify:
                log_system_activity(
                    self,
                    "Postponed notification sent to {target}".format(target=user.email),
                )

    def summary(self):
        if self.description:
            soup = BeautifulSoup(self.description, "lxml")
            text = soup.find_all("p")[0].get_text()
            if len(text) > 100:
                text = text.partition(".")[0] + "."
            return text
        else:
            return ""

    def get_gantt_json(self):
        tasks = []
        from ..models.timeslot import TimeSlot

        for slot in TimeSlot.objects.filter(phase=self).order_by("deliveryRole"):
            user_text = str(slot.user)
            if slot.is_onsite:
                user_text = user_text + " (Onsite)"
            info = {
                "id": slot.pk,
                "user_id": slot.user.pk,
                "user": user_text,
                "slot_type_ID": slot.slot_type.pk,
                "slot_type_name": slot.slot_type.name,
                "delivery_role_id": slot.deliveryRole,
                "delivery_role": slot.get_deliveryRole_display(),
                "text": str(slot.phase.get_id())
                + " ("
                + str(slot.get_deliveryRole_display())
                + ")",
                "start_date": slot.start,
                "end_date": slot.end,
            }
            tasks.append(info)
        data = {
            "tasks": tasks,
        }
        return data

    # Gets scheduled users and assigned users (e.g. lead/author/qa etc)
    def team_pks(self):
        from ..models.timeslot import TimeSlot

        ids = []
        for slot in TimeSlot.objects.filter(phase=self):
            if slot.user.pk not in ids:
                ids.append(slot.user.pk)
        if self.job.account_manager and self.job.account_manager.pk not in ids:
            ids.append(self.job.account_manager.pk)
        if self.job.dep_account_manager and self.job.dep_account_manager.pk not in ids:
            ids.append(self.job.dep_account_manager.pk)
        if self.project_lead and self.project_lead.pk not in ids:
            ids.append(self.project_lead.pk)
        if self.report_author and self.report_author.pk not in ids:
            ids.append(self.report_author.pk)
        if self.techqa_by and self.techqa_by.pk not in ids:
            ids.append(self.techqa_by.pk)
        if self.presqa_by and self.presqa_by.pk not in ids:
            ids.append(self.presqa_by.pk)
        return ids

    # Gets scheduled users and assigned users (e.g. lead/author/qa etc)
    def team(self):
        """Gets scheduled users as well as specifically assigned users (lead, author, QA, Account Manager(s))

        Returns:
            User: List of Users
        """
        ids = self.team_pks()
        if ids:
            return User.objects.filter(pk__in=ids)
        else:
            return User.objects.none()

    def team_scheduled(self):
        from ..models import TimeSlot

        user_ids = (
            TimeSlot.objects.filter(phase=self)
            .values_list("user", flat=True)
            .distinct()
        )
        if user_ids:
            return User.objects.filter(pk__in=user_ids)
        else:
            return None

    def get_all_total_scheduled_by_type(self):
        data = dict()
        for state in TimeSlotDeliveryRole.CHOICES:
            data[state[0]] = self.get_total_scheduled_by_type(state[0])
        return data

    def get_total_scheduled_by_type(self, slot_type):
        from ..models.timeslot import TimeSlot

        slots = TimeSlot.objects.filter(phase=self, deliveryRole=slot_type)
        total = 0.0
        for slot in slots:
            diff = slot.get_business_hours()
            total = total + diff
        return total

    def get_total_scheduled_hours(self):
        total_scheduled = Decimal(0.0)
        for _, sch_hrs in self.get_all_total_scheduled_by_type().items():
            total_scheduled = total_scheduled + Decimal(sch_hrs)
        return round(total_scheduled, 2)

    def get_total_scoped_by_type(self, slot_type):
        total_scoped = Decimal(0.0)
        # Ugly.... but yolo
        if slot_type == TimeSlotDeliveryRole.DELIVERY:
            total_scoped = total_scoped + self.delivery_hours
        elif slot_type == TimeSlotDeliveryRole.REPORTING:
            total_scoped = total_scoped + self.reporting_hours
        elif slot_type == TimeSlotDeliveryRole.MANAGEMENT:
            total_scoped = total_scoped + self.mgmt_hours
        elif slot_type == TimeSlotDeliveryRole.QA:
            total_scoped = total_scoped + self.qa_hours
        elif slot_type == TimeSlotDeliveryRole.OVERSIGHT:
            total_scoped = total_scoped + self.oversight_hours
        elif slot_type == TimeSlotDeliveryRole.DEBRIEF:
            total_scoped = total_scoped + self.debrief_hours
        elif slot_type == TimeSlotDeliveryRole.CONTINGENCY:
            total_scoped = total_scoped + self.contingency_hours
        elif slot_type == TimeSlotDeliveryRole.OTHER:
            total_scoped = total_scoped + self.other_hours
        return total_scoped

    def get_total_scoped_hours(self):
        total_scoped = Decimal(0.0)
        for state in TimeSlotDeliveryRole.CHOICES:
            total_scoped = total_scoped + self.get_total_scoped_by_type(state[0])
        return round(total_scoped, 2)

    def get_all_total_scoped_by_type(self):
        data = dict()
        for state in TimeSlotDeliveryRole.CHOICES:
            data[state[0]] = {
                "type": state[1],
                "hrs": self.get_total_scoped_by_type(state[0]),
            }
        return data

    def get_slot_type_usage_perc(self, slot_type):
        # First, get the total for the slot_type
        total_scoped = self.get_total_scoped_by_type(slot_type)
        # Now lets get the scheduled amount
        scheduled = self.get_total_scheduled_by_type(slot_type)
        if scheduled == 0.0:
            return 0
        if total_scoped == 0.0 and scheduled > 0.0:
            # We've scoped 0 but scheduled. Lets make a superficial scope of 1 to show perc inc
            total_scoped = 10
        return round(100 * float(scheduled) / float(total_scoped), 2)

    def get_total_scheduled_perc(self):
        total_hours = self.get_total_scoped_hours()
        if total_hours > 0:
            # get total scheduled hours...
            total_scheduled = sum(self.get_all_total_scheduled_by_type().values())
            return round(100 * float(total_scheduled) / float(total_hours), 2)
        else:
            return 0

    def get_user_notes(self):
        return self.notes.filter(is_system_note=False)

    def get_system_notes(self):
        return self.notes.filter(is_system_note=True)

    def save(self, *args, **kwargs):
        if not self.phase_number:
            self.phase_number = self.job.phases.all().count() + 1
        if not self.phase_id:
            self.phase_id = self.get_id()
        # lets increment the phase_number
        if not self.slug:
            self.slug = unique_slug_generator(self, str(self.phase_id) + self.title)
        super(Phase, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse(
            "phase_detail", kwargs={"slug": self.slug, "job_slug": self.job.slug}
        )

    @property
    def status_bs_colour(self):
        return PhaseStatuses.BS_COLOURS[self.status][1]

    INVALID_STATE = "Invalid state or permissions."
    MOVED_TO = "Moved to "

    # PENDING_SCHED
    @transition(
        field=status,
        source=[
            PhaseStatuses.DRAFT,
            PhaseStatuses.SCHEDULED_TENTATIVE,
            PhaseStatuses.SCHEDULED_CONFIRMED,
            PhaseStatuses.POSTPONED,
        ],
        target=PhaseStatuses.PENDING_SCHED,
    )
    def to_pending_sched(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + PhaseStatuses.CHOICES[PhaseStatuses.PENDING_SCHED][1],
            author=user,
        )
        self.fire_status_notification(PhaseStatuses.PENDING_SCHED)

    def can_proceed_to_pending_sched(self):
        return can_proceed(self.to_pending_sched)

    def can_to_pending_sched(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_pending_sched)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed

    # SCHEDULED_TENTATIVE
    @transition(
        field=status,
        source=[PhaseStatuses.PENDING_SCHED, PhaseStatuses.SCHEDULED_CONFIRMED],
        target=PhaseStatuses.SCHEDULED_TENTATIVE,
    )
    def to_sched_tentative(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + PhaseStatuses.CHOICES[PhaseStatuses.SCHEDULED_TENTATIVE][1],
            author=user,
        )
        self.fire_status_notification(PhaseStatuses.SCHEDULED_TENTATIVE)

    def can_proceed_to_sched_tentative(self):
        return can_proceed(self.to_sched_tentative)

    def can_to_sched_tentative(self, notify_request=None):
        _can_proceed = True
        # Do logic checks
        # Check we've got slots! Can't move forward if no slots
        if not self.timeslots.all():
            if notify_request:
                messages.add_message(
                    notify_request, messages.ERROR, "No scheduled timeslots."
                )
            _can_proceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_sched_tentative)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed

    # SCHEDULED_CONFIRMED
    @transition(
        field=status,
        source=[PhaseStatuses.PENDING_SCHED, PhaseStatuses.SCHEDULED_TENTATIVE],
        target=PhaseStatuses.SCHEDULED_CONFIRMED,
    )
    def to_sched_confirmed(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + PhaseStatuses.CHOICES[PhaseStatuses.SCHEDULED_CONFIRMED][1],
            author=user,
        )
        # Ok, lets update our parent job to pending_start!
        if self.job.can_proceed_to_pending_start():
            self.job.to_pending_start()
            self.job.save()
        self.fire_status_notification(PhaseStatuses.SCHEDULED_CONFIRMED)

    def can_proceed_to_sched_confirmed(self):
        return can_proceed(self.to_sched_confirmed)

    def can_to_sched_confirmed(self, notify_request=None):
        _can_proceed = True
        # Do logic checks
        # Check we've got slots! Can't confirm if no slots...
        if not self.timeslots.all():
            if notify_request:
                messages.add_message(
                    notify_request, messages.ERROR, "No scheduled timeslots."
                )
            _can_proceed = False

        if not self.project_lead:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "No project lead.")
            _can_proceed = False

        if not self.report_author and self.number_of_reports > 0:
            if notify_request:
                messages.add_message(
                    notify_request,
                    messages.ERROR,
                    "More than one report required and no author defined.",
                )
            _can_proceed = False

        if self.number_of_reports == 0 and notify_request:
            messages.add_message(
                notify_request, messages.INFO, "Beware - no reports required!"
            )

        if self.job.status < JobStatuses.SCOPING_COMPLETE:
            if notify_request:
                messages.add_message(
                    notify_request,
                    messages.ERROR,
                    "Parent job not set to "
                    + JobStatuses.CHOICES[JobStatuses.SCOPING_COMPLETE][1],
                )
            _can_proceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_sched_confirmed)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed

    # PRE_CHECKS
    @transition(
        field=status,
        source=[
            PhaseStatuses.SCHEDULED_CONFIRMED,
        ],
        target=PhaseStatuses.PRE_CHECKS,
    )
    def to_pre_checks(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + PhaseStatuses.CHOICES[PhaseStatuses.PRE_CHECKS][1],
            author=user,
        )
        self.fire_status_notification(PhaseStatuses.PRE_CHECKS)

    def can_proceed_to_pre_checks(self):
        return can_proceed(self.to_pre_checks)

    def can_to_pre_checks(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_pre_checks)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed

    # CLIENT_NOT_READY
    @transition(
        field=status,
        source=[
            PhaseStatuses.PRE_CHECKS,
        ],
        target=PhaseStatuses.CLIENT_NOT_READY,
    )
    def to_not_ready(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + PhaseStatuses.CHOICES[PhaseStatuses.CLIENT_NOT_READY][1],
            author=user,
        )
        self.fire_status_notification(PhaseStatuses.CLIENT_NOT_READY)

    def can_proceed_to_not_ready(self):
        return can_proceed(self.to_not_ready)

    def can_to_not_ready(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_not_ready)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed

    # READY_TO_BEGIN
    @transition(
        field=status,
        source=[PhaseStatuses.PRE_CHECKS, PhaseStatuses.CLIENT_NOT_READY],
        target=PhaseStatuses.READY_TO_BEGIN,
    )
    def to_ready(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + PhaseStatuses.CHOICES[PhaseStatuses.READY_TO_BEGIN][1],
            author=user,
        )
        self.pre_checks_done_date = timezone.now()
        self.fire_status_notification(PhaseStatuses.READY_TO_BEGIN)

    def can_proceed_to_ready(self):
        return can_proceed(self.to_ready)

    def can_to_ready(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_ready)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed

    # IN_PROGRESS
    @transition(
        field=status,
        source=[
            PhaseStatuses.READY_TO_BEGIN,
        ],
        target=PhaseStatuses.IN_PROGRESS,
    )
    def to_in_progress(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + PhaseStatuses.CHOICES[PhaseStatuses.IN_PROGRESS][1],
            author=user,
        )
        self.actual_start_date = timezone.now()
        # lets make sure our parent job is in progress now!
        if self.job.status == JobStatuses.PENDING_START:
            if self.job.can_to_in_progress():
                self.job.to_in_progress()
                self.job.save()
        self.fire_status_notification(PhaseStatuses.IN_PROGRESS)

    def can_proceed_to_in_progress(self):
        return can_proceed(self.to_in_progress)

    def can_to_in_progress(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_in_progress)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed

    # PENDING_TQA
    @transition(
        field=status,
        source=[PhaseStatuses.IN_PROGRESS, PhaseStatuses.QA_TECH_AUTHOR_UPDATES],
        target=PhaseStatuses.PENDING_TQA,
    )
    def to_pending_tech_qa(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + PhaseStatuses.CHOICES[PhaseStatuses.PENDING_TQA][1],
            author=user,
        )
        self.actual_sent_to_tqa_date = timezone.now()
        self.fire_status_notification(PhaseStatuses.PENDING_TQA)

    def can_proceed_to_pending_tech_qa(self):
        return can_proceed(self.to_pending_tech_qa)

    def can_to_pending_tech_qa(self, notify_request=None):
        _can_proceed = True
        # Do logic checks
        if self.feedback_scope_correct is None:
            if notify_request:
                messages.add_message(
                    notify_request,
                    messages.ERROR,
                    "Please report if the scope was correct",
                )
            _can_proceed = False

        if self.feedback_scope_correct is False:
            # Check if there's any feedback since they've flagged it as wrong...
            if not self.feedback_scope():
                if notify_request:
                    messages.add_message(
                        notify_request,
                        messages.ERROR,
                        "Scope was incorrect but no feedback provided",
                    )
                _can_proceed = False

        if self.number_of_reports > 0:
            if not self.linkDeliverable:
                if notify_request:
                    messages.add_message(
                        notify_request, messages.ERROR, "Missing deliverable link"
                    )
                _can_proceed = False

            if not self.linkTechData:
                if notify_request:
                    messages.add_message(
                        notify_request, messages.ERROR, "Missing technical data link"
                    )
                _can_proceed = False

            if not self.linkReportData:
                if notify_request:
                    messages.add_message(
                        notify_request, messages.ERROR, "Missing report data link"
                    )
                _can_proceed = False
        else:
            if not self.linkDeliverable and notify_request:
                messages.add_message(
                    notify_request,
                    messages.INFO,
                    "Missing deliverable link. Is this intentional?",
                )

            if not self.linkTechData and notify_request:
                messages.add_message(
                    notify_request,
                    messages.INFO,
                    "Missing technical data link. Is this intentional?",
                )

            if not self.linkReportData and notify_request:
                messages.add_message(
                    notify_request,
                    messages.INFO,
                    "Missing report data link. Is this intentional?",
                )

        # Do general check
        can_proceed_result = can_proceed(self.to_pending_tech_qa)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed

    # QA_TECH
    @transition(
        field=status,
        source=[
            PhaseStatuses.PENDING_TQA,
        ],
        target=PhaseStatuses.QA_TECH,
    )
    def to_tech_qa(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + PhaseStatuses.CHOICES[PhaseStatuses.QA_TECH][1],
            author=user,
        )
        self.fire_status_notification(PhaseStatuses.QA_TECH)

    def can_proceed_to_tech_qa(self):
        return can_proceed(self.to_tech_qa)

    def can_to_tech_qa(self, notify_request=None):
        _can_proceed = True
        # Do logic checks
        if notify_request:
            if (
                self.techqa_by is None
                or notify_request.user.pk is not self.techqa_by.pk
            ):
                # Check if we have tqa perm...
                if notify_request.user.has_perm("can_tqa_jobs", self.job.unit):
                    # Can TQA jobs - don't block but tell them this will update it to them...
                    messages.add_message(
                        notify_request,
                        messages.INFO,
                        "You're not assigned to Tech QA this report. If you continue, it will be assigned to you.",
                    )
                else:
                    messages.add_message(
                        notify_request,
                        messages.ERROR,
                        "You're not assigned to Tech QA this report.",
                    )
                    _can_proceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_tech_qa)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed

    # QA_TECH_AUTHOR_UPDATES
    @transition(
        field=status,
        source=[
            PhaseStatuses.QA_TECH,
        ],
        target=PhaseStatuses.QA_TECH_AUTHOR_UPDATES,
    )
    def to_tech_qa_updates(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO
            + PhaseStatuses.CHOICES[PhaseStatuses.QA_TECH_AUTHOR_UPDATES][1],
            author=user,
        )
        self.required_tqa_updates = True
        self.fire_status_notification(PhaseStatuses.QA_TECH_AUTHOR_UPDATES)

    def can_proceed_to_tech_qa_updates(self):
        return can_proceed(self.to_tech_qa_updates)

    def can_to_tech_qa_updates(self, notify_request=None):
        _can_proceed = True
        # Do logic checks
        if not self.techqa_by:
            if notify_request:
                messages.add_message(
                    notify_request, messages.ERROR, "No one assigned to Tech QA."
                )
            _can_proceed = False
        else:
            # Check if we're the person...
            if notify_request.user != self.techqa_by:
                if notify_request:
                    # We're not the person doing the TQA!
                    messages.add_message(
                        notify_request, messages.ERROR, "Not assigned to Tech QA."
                    )
                _can_proceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_tech_qa_updates)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed

    # PENDING_PQA
    @transition(
        field=status,
        source=[PhaseStatuses.QA_TECH, PhaseStatuses.QA_PRES_AUTHOR_UPDATES],
        target=PhaseStatuses.PENDING_PQA,
    )
    def to_pending_pres_qa(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + PhaseStatuses.CHOICES[PhaseStatuses.PENDING_PQA][1],
            author=user,
        )
        self.actual_sent_to_pqa_date = timezone.now()
        self.fire_status_notification(PhaseStatuses.PENDING_PQA)

    def can_proceed_to_pending_pres_qa(self):
        return can_proceed(self.to_pending_pres_qa)

    def can_to_pending_pres_qa(self, notify_request=None):
        _can_proceed = True
        # Do logic checks
        # Lets check feedback/ratings have been left!
        if not self.feedback_techqa():
            if notify_request:
                messages.add_message(
                    notify_request, messages.ERROR, "No Tech QA feedback has been left"
                )
            _can_proceed = False

        # Make sure a rating has been left
        if self.techqa_report_rating == None:
            if notify_request:
                messages.add_message(
                    notify_request, messages.ERROR, "No Tech QA rating has been left"
                )
            _can_proceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_pending_pres_qa)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed

    # QA_PRES
    @transition(
        field=status,
        source=[
            PhaseStatuses.PENDING_PQA,
        ],
        target=PhaseStatuses.QA_PRES,
    )
    def to_pres_qa(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + PhaseStatuses.CHOICES[PhaseStatuses.QA_PRES][1],
            author=user,
        )
        self.fire_status_notification(PhaseStatuses.QA_PRES)

    def can_proceed_to_pres_qa(self):
        return can_proceed(self.to_pres_qa)

    def can_to_pres_qa(self, notify_request=None):
        _can_proceed = True
        # Do logic checks
        if notify_request:
            if (
                self.presqa_by is None
                or notify_request.user.pk is not self.presqa_by.pk
            ):
                # Check if we have tqa perm...
                if notify_request.user.has_perm("can_pqa_jobs", self.job.unit):
                    # Can TQA jobs - don't block but tell them this will update it to them...
                    messages.add_message(
                        notify_request,
                        messages.INFO,
                        "You're not assigned to Pres QA this report. If you continue, it will be assigned to you.",
                    )
                else:
                    messages.add_message(
                        notify_request,
                        messages.ERROR,
                        "You're not assigned to Pres QA this report.",
                    )
                    _can_proceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_pres_qa)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed

    # QA_PRES_AUTHOR_UPDATES
    @transition(
        field=status,
        source=[
            PhaseStatuses.QA_PRES,
        ],
        target=PhaseStatuses.QA_PRES_AUTHOR_UPDATES,
    )
    def to_pres_qa_updates(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO
            + PhaseStatuses.CHOICES[PhaseStatuses.QA_PRES_AUTHOR_UPDATES][1],
            author=user,
        )
        self.required_pqa_updates = True
        self.fire_status_notification(PhaseStatuses.QA_PRES_AUTHOR_UPDATES)

    def can_proceed_to_pres_qa_updates(self):
        return can_proceed(self.to_pres_qa_updates)

    def can_to_pres_qa_updates(self, notify_request=None):
        _can_proceed = True
        # Do logic checks
        if not self.presqa_by:
            if notify_request:
                messages.add_message(
                    notify_request, messages.ERROR, "No one assigned to Pres QA."
                )
            _can_proceed = False
        else:
            # Check if we're the person...
            if notify_request.user != self.presqa_by:
                # We're not the person doing the TQA!
                if notify_request:
                    messages.add_message(
                        notify_request, messages.ERROR, "Not assigned to Pres QA."
                    )
                _can_proceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_pres_qa_updates)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed

    # COMPLETED
    @transition(
        field=status,
        source=[PhaseStatuses.QA_PRES, PhaseStatuses.IN_PROGRESS],
        target=PhaseStatuses.COMPLETED,
    )
    def to_completed(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + PhaseStatuses.CHOICES[PhaseStatuses.DELIVERED][1],
            author=user,
        )
        self.actual_completed_date = timezone.now()
        self.fire_status_notification(PhaseStatuses.COMPLETED)

    def can_proceed_to_completed(self):
        if self.number_of_reports > 0 and self.status <= PhaseStatuses.QA_TECH:
            return False
        return can_proceed(self.to_completed)

    def can_to_completed(self, notify_request=None):
        _can_proceed = True
        # Do logic checks
        if self.number_of_reports > 0:
            if self.status <= PhaseStatuses.QA_TECH:
                if notify_request:
                    messages.add_message(
                        notify_request,
                        messages.ERROR,
                        "More than one report expected - must go through QA",
                    )
                _can_proceed = False

            if not self.presqa_by:
                if notify_request:
                    messages.add_message(
                        notify_request, messages.ERROR, "No one assigned to Pres QA."
                    )
                _can_proceed = False

            # Lets check feedback/ratings have been left!
            if not self.feedback_presqa():
                if notify_request:
                    messages.add_message(
                        notify_request,
                        messages.ERROR,
                        "No Pres QA feedback has been left",
                    )
                _can_proceed = False

            if self.presqa_report_rating == None:
                if notify_request:
                    messages.add_message(
                        notify_request,
                        messages.ERROR,
                        "No Pres QA rating has been left",
                    )
                _can_proceed = False

        else:
            # No reports - display a warning
            if notify_request:
                messages.add_message(
                    notify_request,
                    messages.INFO,
                    "Are you sure there is no report? This bypasses QA!",
                )

        # Do general check
        can_proceed_result = can_proceed(self.to_completed)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed

    # DELIVERED
    @transition(
        field=status, source=PhaseStatuses.COMPLETED, target=PhaseStatuses.DELIVERED
    )
    def to_delivered(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + PhaseStatuses.CHOICES[PhaseStatuses.DELIVERED][1],
            author=user,
        )
        self.actual_delivery_date = timezone.now()

        # Ok, check if all phases have completed...
        if (
            not self.job.phases.filter(status__lt=PhaseStatuses.DELIVERED)
            .exclude(pk=self.pk)
            .exists()
        ):
            if self.job.can_to_complete():
                self.job.to_complete()
                self.job.save()
        self.fire_status_notification(PhaseStatuses.DELIVERED)

    def can_proceed_to_delivered(self):
        if self.number_of_reports == 0:
            return can_proceed(self.to_delivered)
        else:
            if self.status == PhaseStatuses.COMPLETED:
                return can_proceed(self.to_delivered)
            else:
                return False

    def can_to_delivered(self, notify_request=None):
        _can_proceed = True
        # Do logic checks
        if notify_request:
            messages.add_message(
                notify_request,
                messages.INFO,
                "Are you sure all deliverables have been submitted to the client?",
            )

        # Do general check
        can_proceed_result = can_proceed(self.to_delivered)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed

    # CANCELLED
    @transition(field=status, source="+", target=PhaseStatuses.CANCELLED)
    def to_cancelled(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + PhaseStatuses.CHOICES[PhaseStatuses.CANCELLED][1],
            author=user,
        )
        self.cancellation_date = timezone.now()
        for slot in self.timeslots.all():
            slot.delete()

        self.fire_status_notification(PhaseStatuses.CANCELLED)

    def can_proceed_to_cancelled(self):
        return can_proceed(self.to_cancelled)

    def can_to_cancelled(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_cancelled)

        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        else:
            # Show a warning to the user that any timeslots will be erased
            if notify_request:
                messages.add_message(notify_request, messages.INFO, 
                                     "Warning - any scheduled timeslots will be deleted!")
        return _can_proceed

    # POSTPONED
    @transition(field=status, source="+", target=PhaseStatuses.POSTPONED)
    def to_postponed(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + PhaseStatuses.CHOICES[PhaseStatuses.POSTPONED][1],
            author=user,
        )
        self.fire_status_notification(PhaseStatuses.POSTPONED)

    def can_proceed_to_postponed(self):
        return can_proceed(self.to_postponed)

    def can_to_postponed(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_postponed)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed

    # DELETED
    @transition(field=status, source="+", target=PhaseStatuses.DELETED)
    def to_deleted(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + PhaseStatuses.CHOICES[PhaseStatuses.DELETED][1],
            author=user,
        )
        self.fire_status_notification(PhaseStatuses.DELETED)

    def can_proceed_to_deleted(self):
        return can_proceed(self.to_deleted)

    def can_to_deleted(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_deleted)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed

    # ARCHIVED
    @transition(
        field=status,
        source=[
            PhaseStatuses.DELIVERED,
            PhaseStatuses.DELETED,
            PhaseStatuses.CANCELLED,
        ],
        target=PhaseStatuses.ARCHIVED,
    )
    def to_archived(self, user=None):
        log_system_activity(
            self,
            self.MOVED_TO + PhaseStatuses.CHOICES[PhaseStatuses.ARCHIVED][1],
            author=user,
        )
        self.fire_status_notification(PhaseStatuses.ARCHIVED)

    def can_proceed_to_archived(self):
        return can_proceed(self.to_archived)

    def can_to_archived(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_archived)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, self.INVALID_STATE)
            _can_proceed = False
        return _can_proceed
