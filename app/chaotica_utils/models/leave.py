from django.db import models
from ..enums import LeaveRequestTypes
from notifications.enums import NotificationTypes
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from notifications.utils import task_send_notifications
from jobtracker.enums import DefaultTimeSlotTypes
from business_duration import businessDuration
from django.contrib.auth import get_user_model
from constance import config


def get_sentinel_user():
    return get_user_model().objects.get_or_create(email="deleted@chaotica.app")[0]


class LeaveRequest(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="leave_records",
    )

    requested_on = models.DateTimeField(auto_now_add=True)
    start_date = models.DateTimeField(db_index=True)
    end_date = models.DateTimeField(db_index=True)

    type_of_leave = models.IntegerField(choices=LeaveRequestTypes.CHOICES)
    notes = models.TextField(blank=True)

    authorised = models.BooleanField(default=False)
    authorised_on = models.DateTimeField(null=True, blank=True)
    authorised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="leave_records_authorised",
        null=True,
        blank=True,
        on_delete=models.SET(get_sentinel_user),
    )

    timeslot = models.ForeignKey(
        "jobtracker.TimeSlot",
        related_name="leaverequest",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    cancelled = models.BooleanField(default=False)
    cancelled_on = models.DateTimeField(null=True, blank=True)

    declined = models.BooleanField(default=False)
    declined_on = models.DateTimeField(null=True, blank=True)
    declined_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="leave_records_declined",
        null=True,
        blank=True,
        on_delete=models.SET(get_sentinel_user),
    )

    class Meta:
        verbose_name = "Leave Request"
        ordering = ["-start_date"]

    def overlaps_work(self):
        return self.user.timeslots.filter(
            slot_type=DefaultTimeSlotTypes.DELIVERY,
            start__lte=self.end_date,
            end__gte=self.start_date,
        ).exists()

    def overlaps_confirmed_work(self):
        from jobtracker.enums import PhaseStatuses

        return self.user.timeslots.filter(
            slot_type=DefaultTimeSlotTypes.DELIVERY,
            phase__status__gte=PhaseStatuses.SCHEDULED_CONFIRMED,
            start__lte=self.end_date,
            end__gte=self.start_date,
        ).exists()

    def requested_late(self):
        return self.start_date < (
            self.requested_on + timedelta(days=config.LEAVE_DAYS_NOTICE)
        )

    def affected_days(self):
        unit = "hour"
        days = 0
        working_hours = self.user.get_working_hours()
        hours = businessDuration(
            self.start_date,
            self.end_date,
            unit=unit,
            starttime=working_hours["start"],
            endtime=working_hours["end"],
        )
        hours_in_working_day = (
            timezone.datetime.combine(timezone.now().date(), working_hours["end"])
            - timezone.datetime.combine(timezone.now().date(), working_hours["start"])
        ).total_seconds() / 3600
        if hours:
            days = hours / hours_in_working_day
        return round(days, 2)

    def can_cancel(self):
        # Only situ we can't cancel is if it's in the past or it's already cancelled.
        if self.start_date < timezone.now():
            return False
        if self.cancelled:
            return False
        return True

    def can_approve_by(self):
        from ..models import User

        # Update to reflect logic...
        user_pks = []
        if self.user.manager and self.user.manager.pk not in user_pks:
            user_pks.append(self.user.manager.pk)
        if self.user.acting_manager and self.user.acting_manager.pk not in user_pks:
            user_pks.append(self.user.acting_manager.pk)
        if not self.user.manager and not self.user.acting_manager:
            # No managers defined - can self approve
            user_pks.append(self.user.pk)

        return User.objects.filter(pk__in=user_pks).distinct()

    def can_user_auth(self, user):
        if self.cancelled:
            return False
        if user == self.user.manager or user == self.user.acting_manager:
            return True

        if (
            not self.user.manager and not self.user.acting_manager
        ) and user == self.user:
            # No managers defined - can self approve
            return True
        for membership in self.user.unit_memberships.all():
            # Check if user has permission in any of the units...
            if user.has_perm("can_approve_leave_requests", membership.unit):
                return True
        return False

    EMAIL_TEMPLATE = "emails/leave.html"

    def send_request_notification(self):
        from chaotica_utils.utils import AppNotification

        users_to_notify = self.can_approve_by()
        notification = AppNotification(
            notification_type=NotificationTypes.LEAVE_SUBMITTED,
            title=f"Leave Requested - {self.user}",
            message=f"{self.user} has requested leave. Please review the request",
            email_template=self.EMAIL_TEMPLATE,
            link=reverse("manage_leave"),
            entity_type=self.__class__.__name__,
            entity_id=self.pk,
            metadata={
                "leave": self,
            }
        )
        task_send_notifications(notification, users_to_notify)

    def send_approved_notification(self):
        from chaotica_utils.utils import AppNotification

        notification = AppNotification(
            notification_type=NotificationTypes.LEAVE_APPROVED,
            title=f"Leave Approved",
            message=f"Your leave ({self.start_date} - {self.end_date}) has been approved!",
            email_template=self.EMAIL_TEMPLATE,
            link=reverse("view_own_leave"),
            entity_type=self.__class__.__name__,
            entity_id=self.pk,
            metadata={
                "leave": self,
            }
        )
        task_send_notifications(notification)

    def send_declined_notification(self):
        from chaotica_utils.utils import AppNotification

        notification = AppNotification(
            notification_type=NotificationTypes.LEAVE_REJECTED,
            title=f"Leave Rejected",
            message=f"Your leave ({self.start_date} - {self.end_date}) has been declined. Please contact {self.declined_by} for information.",
            email_template=self.EMAIL_TEMPLATE,
            link=reverse("view_own_leave"),
            entity_type=self.__class__.__name__,
            entity_id=self.pk,
            metadata={
                "leave": self,
            }
        )
        task_send_notifications(notification)

    def send_cancelled_notification(self):
        from chaotica_utils.utils import AppNotification

        notification = AppNotification(
            notification_type=NotificationTypes.LEAVE_CANCELLED,
            title=f"Leave Cancelled",
            message=f"Your leave ({self.start_date} - {self.end_date}) has been cancelled.",
            email_template=self.EMAIL_TEMPLATE,
            link=reverse("view_own_leave"),
            entity_type=self.__class__.__name__,
            entity_id=self.pk,
            metadata={
                "leave": self,
            }
        )

        task_send_notifications(notification)


    def authorise(self, approved_by):
        from jobtracker.models.timeslot import TimeSlot, TimeSlotType

        if self.cancelled:
            # Can't auth at this stage
            return False
        if not self.authorised:
            # Set our important fields
            self.authorised = True
            self.authorised_by = approved_by
            self.authorised_on = timezone.now()
            # Lets add the timeslot...
            ts, ts_created = TimeSlot.objects.get_or_create(
                user=self.user,
                start=self.start_date,
                end=self.end_date,
                slot_type=TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.LEAVE),
            )
            self.timeslot = ts
            self.save()
            self.send_approved_notification()

    def decline(self, declined_by):
        pass

        if self.authorised or self.cancelled:
            # Can't decline at this stage
            return False
        if not self.declined:
            # Set our important fields
            self.declined = True
            self.declined_by = declined_by
            self.declined_on = timezone.now()
            self.save()
            self.send_declined_notification()

    def cancel(self):
        from jobtracker.models.timeslot import TimeSlot, TimeSlotType

        if not self.cancelled:
            # Set our important fields
            self.cancelled = True
            self.cancelled_on = timezone.now()
            self.authorised = False
            self.declined = False
            # Lets delete the timeslot...
            if self.timeslot:
                self.timeslot.delete()
            self.save()
            self.send_cancelled_notification()
