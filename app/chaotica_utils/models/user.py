from django.db import models
from django.db.models import Q, Count, When, Case, Value, Avg
from django.db.models.functions import Lower, TruncDate, ExtractDay
from django.contrib.auth.models import AbstractUser, Permission
from django.templatetags.static import static
import uuid
import os, pytz
from ..enums import GlobalRoles, LeaveRequestTypes, UpcomingAvailabilityRanges
from ..utils import calculate_percentage
from .models import Note, Language
from .leave import LeaveRequest
from django.conf import settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from guardian.shortcuts import assign_perm
import django.contrib.auth
from guardian.shortcuts import get_objects_for_user
from django.utils import timezone
from datetime import timedelta, date, datetime
from dateutil.relativedelta import relativedelta
from phonenumber_field.modelfields import PhoneNumberField
from django_countries.fields import CountryField
from jobtracker.enums import UserSkillRatings, PhaseStatuses
from constance import config
from django.template.loader import render_to_string
import django.core.mail
from geopy.geocoders import Nominatim
import pandas as pd


def get_sentinel_user():
    return get_user_model().objects.get_or_create(email="deleted@chaotica.app")[0]


class Group(django.contrib.auth.models.Group):

    class Meta:
        proxy = True

    def getGlobalRoleINT(self):
        # If we're a global role group... return the int value
        for role in GlobalRoles.CHOICES:
            name_to_check = settings.GLOBAL_GROUP_PREFIX + role[1]
            if self.name == name_to_check:
                return role[0]
        return None

    def role_bs_colour(self):
        val = self.getGlobalRoleINT()
        if val != None:
            return GlobalRoles.BS_COLOURS[val][1]
        else:
            return ""

    def sync_global_permissions(self):
        for global_role in GlobalRoles.CHOICES:
            if self.name == settings.GLOBAL_GROUP_PREFIX + global_role[1]:
                # Ok, we match a global role..
                self.permissions.clear()
                for perm in GlobalRoles.PERMISSIONS[global_role[0]][1]:  # how ugly!
                    try:
                        assign_perm(perm, self, None)
                    except Permission.DoesNotExist:
                        pass  # ignore this for the moment!
                return True

        # If we reach this; this group isn't matched with a global role in code
        return False


class UserInvitation(models.Model):
    invited_email = models.EmailField(
        verbose_name="Email Address", max_length=255, unique=True
    )
    accepted = models.BooleanField(
        verbose_name="Accepted",
        help_text="Has the invitation been accepted",
        default=False,
    )
    invite_id = models.UUIDField(verbose_name="Invitation ID", default=uuid.uuid4)
    sent = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="users_invited",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )

    def is_expired(self):
        return self.expiry_date() <= timezone.now()

    def expiry_date(self):
        expiry_date = self.sent + timedelta(days=config.USER_INVITE_EXPIRY)
        return expiry_date

    def get_absolute_url(self):
        return reverse("signup", kwargs={"invite_id": self.invite_id})

    def send_email(self):
        from ..utils import ext_reverse

        if config.EMAIL_ENABLED:
            ## Email notification
            context = {}
            context["SITE_DOMAIN"] = settings.SITE_DOMAIN
            context["SITE_PROTO"] = settings.SITE_PROTO
            context["title"] = "You're invited to Chaotica"
            context["message"] = (
                "You've been invited to join Chaotica - (Centralised Hub for Assigning Operational Tasks, Interactive Calendaring and Alerts). Follow the link below to accept the invitation and setup your account."
            )
            context["action_link"] = ext_reverse(self.get_absolute_url())
            msg_html = render_to_string("emails/user_invite.html", context)
            django.core.mail.send_mail(
                subject=context["title"],
                message=context["message"],
                from_email=None,
                recipient_list=[self.invited_email],
                html_message=msg_html,
            )

            self.sent = timezone.now()
            self.save()


def get_media_profile_file_path(_, filename):
    ext = filename.split(".")[-1]
    filename = "%s.%s" % (uuid.uuid4(), ext)
    return os.path.join("profile_pics", filename)


class User(AbstractUser):
    # Fields to enforce email as the auth field
    username = None
    email = models.EmailField(
        "Email Address",
        unique=True,
        help_text="This is your authenticated email and can not be changed",
    )
    notification_email = models.EmailField(
        "Notification Email Address",
        blank=True,
        default="",
        help_text="If configured, email notifications go to this address rather than your account address.",
    )
    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET(get_sentinel_user),
        related_name="users_managed",
        null=True,
        blank=True,
    )
    acting_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET(get_sentinel_user),
        related_name="users_acting_managed",
        null=True,
        blank=True,
    )
    pref_timezone = models.CharField(
        verbose_name="Time Zone",
        max_length=255,
        null=True,
        blank=True,
        choices=[(tz, tz) for tz in pytz.common_timezones],
        default="UTC",
        help_text="User's preferred timezone for displaying dates and times",
    )
    job_title = models.CharField(
        verbose_name="Job Title", max_length=255, null=True, blank=True, default=""
    )
    location = models.CharField(
        verbose_name="Location", max_length=255, null=True, blank=True, default=""
    )
    longitude = models.DecimalField(
        max_digits=22, decimal_places=16, blank=True, null=True
    )
    latitude = models.DecimalField(
        max_digits=22, decimal_places=16, blank=True, null=True
    )

    country = CountryField(
        default="GB", help_text="Used to determine which holidays apply."
    )
    external_id = models.CharField(
        verbose_name="External ID",
        db_index=True,
        max_length=255,
        null=True,
        blank=True,
        default="",
    )
    phone_number = PhoneNumberField(blank=True)
    show_help = models.BooleanField(
        verbose_name="Show Helpful Tips", help_text="Should help be shown", default=True
    )
    site_theme = models.CharField(
        verbose_name="Site Theme", max_length=20, default="light"
    )
    schedule_feed_id = models.UUIDField(
        verbose_name="Calendar Feed Key", default=uuid.uuid4
    )
    schedule_feed_family_id = models.UUIDField(
        verbose_name="Calendar Feed Family Key", default=uuid.uuid4
    )
    groups = models.ManyToManyField(
        Group,
        verbose_name="groups",
        blank=True,
        help_text="The groups this user belongs to. A user will "
        "get all permissions granted to each of "
        "their groups.",
        related_name="user_set",
        related_query_name="user",
    )
    languages = models.ManyToManyField(Language, verbose_name="Languages", blank=True)
    profile_image = models.ImageField(
        blank=True,
        upload_to=get_media_profile_file_path,
    )
    contracted_leave = models.IntegerField(
        verbose_name="Contracted Leave",
        default=25,
        help_text="Days leave you are entitled to",
    )
    carry_over_leave = models.IntegerField(
        verbose_name="Leave Carried Over",
        default=0,
        help_text="Days leave carried over from previous period",
    )
    contracted_leave_renewal = models.DateField(
        verbose_name="Leave Renewal Date",
        default=date(day=1, month=9, year=2023),
        help_text="Date leave is reset",
    )

    profile_last_updated = models.DateField(
        verbose_name="Profile Last Updated", blank=True, null=True
    )

    class Meta:
        ordering = [Lower("last_name"), Lower("first_name")]
        permissions = (
            ("manage_user", "Can manage the user"),
            ("manage_leave", "Manage leave"),
            ("impersonate_users", "Can impersonate other users"),
            ("manage_site_settings", "Can change site settings"),
            ("view_activity_logs", "Can review the activity logs"),
        )

    def merge(self, user_to_merge):
        # Things to merge:
        # Timeslots
        # Leave
        # Job, Phase assignments
        # Org Unit memberships/roles
        # Qualifications

        ## Notes
        Note.objects.filter(author=user_to_merge).update(author=self)
        ## Manager
        User.objects.filter(manager=user_to_merge).update(manager=self)
        User.objects.filter(acting_manager=user_to_merge).update(acting_manager=self)
        ## UserCost
        UserCost.objects.filter(user=user_to_merge).update(user=self)
        ## Leave
        LeaveRequest.objects.filter(user=user_to_merge).update(user=self)
        LeaveRequest.objects.filter(authorised_by=user_to_merge).update(
            authorised_by=self
        )
        LeaveRequest.objects.filter(declined_by=user_to_merge).update(declined_by=self)
        ## Client
        from jobtracker.models.client import Client, ClientOnboarding

        for obj in Client.objects.filter(account_managers__in=[user_to_merge]):
            obj.account_managers.remove(user_to_merge)
            obj.account_managers.add(self)
            obj.save()
        for obj in Client.objects.filter(tech_account_managers__in=[user_to_merge]):
            obj.tech_account_managers.remove(user_to_merge)
            obj.tech_account_managers.add(self)
            obj.save()
        for obj in ClientOnboarding.objects.filter(user=user_to_merge):
            obj.user = self
            obj.save()
        ## Feedback
        from jobtracker.models.common import Feedback

        Feedback.objects.filter(author=user_to_merge).update(author=self)
        ## Job
        from jobtracker.models.job import Job

        Job.objects.filter(created_by=user_to_merge).update(created_by=self)
        Job.objects.filter(account_manager=user_to_merge).update(account_manager=self)
        Job.objects.filter(dep_account_manager=user_to_merge).update(
            dep_account_manager=self
        )
        for obj in Job.objects.filter(scoped_by__in=[user_to_merge]):
            obj.scoped_by.remove(user_to_merge)
            obj.scoped_by.add(self)
            obj.save()
        Job.objects.filter(scoped_signed_off_by=user_to_merge).update(
            scoped_signed_off_by=self
        )
        Job.objects.filter(created_by=user_to_merge).update(created_by=self)
        ## JobSupportTeamRole
        from jobtracker.models.job import JobSupportTeamRole

        JobSupportTeamRole.objects.filter(user=user_to_merge).update(user=self)
        ## JobSupportTeamRole
        from jobtracker.models.orgunit import (
            OrganisationalUnit,
            OrganisationalUnitMember,
        )

        OrganisationalUnit.objects.filter(lead=user_to_merge).update(lead=self)
        OrganisationalUnitMember.objects.filter(member=user_to_merge).update(
            member=self
        )
        OrganisationalUnitMember.objects.filter(inviter=user_to_merge).update(
            inviter=self
        )
        ## Phase
        from jobtracker.models.phase import Phase

        Phase.objects.filter(report_author=user_to_merge).update(report_author=self)
        Phase.objects.filter(project_lead=user_to_merge).update(project_lead=self)
        Phase.objects.filter(techqa_by=user_to_merge).update(techqa_by=self)
        Phase.objects.filter(presqa_by=user_to_merge).update(presqa_by=self)
        Phase.objects.filter(last_modified_by=user_to_merge).update(
            last_modified_by=self
        )
        ## Project
        from jobtracker.models.project import Project

        Project.objects.filter(created_by=user_to_merge).update(created_by=self)
        Project.objects.filter(primary_poc=user_to_merge).update(primary_poc=self)
        ## QualificationRecord
        from jobtracker.models.qualification import QualificationRecord

        QualificationRecord.objects.filter(user=user_to_merge).update(user=self)
        ## Service
        from jobtracker.models.service import Service

        for obj in Service.objects.filter(owners__in=[user_to_merge]):
            obj.owners.remove(user_to_merge)
            obj.owners.add(self)
            obj.save()
        ## TimeSlot
        from jobtracker.models.timeslot import TimeSlot

        TimeSlot.objects.filter(user=user_to_merge).update(user=self)

        # If we have got this far... delete the target user!
        user_to_merge.delete()

        return True

    def email_address(self):
        if self.notification_email:
            return self.notification_email
        else:
            return self.email

    def update_latlong(self):
        if self.location:
            try:
                loc = Nominatim(user_agent="CHAOTICA")
                getLoc = loc.geocode(self.location)
                self.longitude = getLoc.longitude
                self.latitude = getLoc.latitude
                self.save()
            except:
                pass  # Don't care.
        else:
            return None

    def skills_last_updated(self):
        if self.skills.all().count():
            return self.skills.order_by("-last_updated_on").first().last_updated_on
        else:
            return None

    def can_scope(self):
        from jobtracker.models.orgunit import OrganisationalUnit

        return get_objects_for_user(self, "can_scope_jobs", OrganisationalUnit)

    def can_signoff_scope(self):
        from jobtracker.models.orgunit import OrganisationalUnit

        return get_objects_for_user(self, "can_signoff_scopes", OrganisationalUnit)

    def can_tqa(self):
        from jobtracker.models.orgunit import OrganisationalUnit

        return get_objects_for_user(self, "can_tqa_jobs", OrganisationalUnit)

    def can_pqa(self):
        from jobtracker.models.orgunit import OrganisationalUnit

        return get_objects_for_user(self, "can_pqa_jobs", OrganisationalUnit)

    def _get_last_leave_renewal_date(self):
        today = timezone.now().date()
        renewal_date = self.contracted_leave_renewal.replace(year=today.year)
        if renewal_date < today:
            return renewal_date
        else:
            return renewal_date.replace(year=today.year - 1)

    def _get_next_leave_renewal_date(self):
        today = timezone.now().date()
        renewal_date = self.contracted_leave_renewal.replace(year=today.year)
        if renewal_date > today:
            return renewal_date
        else:
            return renewal_date.replace(year=today.year + 1)

    def remaining_leave(self):
        return self.contracted_leave - self.pending_leave() - self.used_leave()

    def pending_leave(self):
        total = 0
        for leave in self.leave_records.filter(
            type_of_leave__in=LeaveRequestTypes.COUNT_TOWARDS_LEAVE,
            cancelled=False,
            authorised=True,
            start_date__gte=self._get_last_leave_renewal_date(),
            end_date__lte=self._get_next_leave_renewal_date(),
        ).filter(start_date__gte=timezone.now()):
            total = total + leave.affected_days()
        return total

    def used_leave(self):
        total = 0
        for leave in self.leave_records.filter(
            type_of_leave__in=LeaveRequestTypes.COUNT_TOWARDS_LEAVE,
            cancelled=False,
            authorised=True,
            start_date__gte=self._get_last_leave_renewal_date(),
            end_date__lte=self._get_next_leave_renewal_date(),
        ).filter(start_date__lte=timezone.now(), end_date__lte=timezone.now()):
            total = total + leave.affected_days()
        return total

    def unread_notifications(self):
        return self.notification_set.filter(is_read=False)

    def get_avatar_url(self):
        if self.profile_image:
            return self.profile_image.url
        else:
            return static("assets/img/team/avatar-rounded.webp")

    def get_absolute_url(self):
        if self.email:
            return reverse("user_profile", kwargs={"email": self.email})
        else:
            return None
    
    def get_profile_url(self):
        if self.email:
            return reverse("user_profile", kwargs={"email": self.email})
        else:
            return None

    def get_edit_url(self):
        if self.email:
            return reverse("update_profile", kwargs={"email": self.email})
        else:
            return None

    def get_admin_url(self):
        if self.email:
            return reverse(
                "admin:%s_%s_change" % (self._meta.app_label, self._meta.model_name),
                args=[self.id],
            )
    
    def has_manager(self):
        return (self.manager or self.acting_manager)

    def can_be_managed_by(self, requesting_user):
        if not requesting_user:
            return False
        
        # Case 1: Self-management - user can always manage themselves
        if requesting_user.pk == self.pk:
            return True

        # Case 2: Manager relationship check
        # Check if requesting_user is the manager or acting_manager of target_user
        is_manager = hasattr(self, "manager") and self.manager == requesting_user
        is_acting_manager = (
            hasattr(self, "acting_manager") and self.acting_manager == requesting_user
        )

        if is_manager or is_acting_manager:
            return True

        # Case 3: Permission check - user has guardian permission
        if requesting_user.has_perm("chaotica_utils.manage_user"):
            return True

        return False

    def get_table_display_html(self):
        context = {}
        context["u"] = self
        html = render_to_string("partials/users/user_table_display.html", context)
        return html

    def get_profile_card_html(self):
        context = {}
        context["userProfile"] = self
        html = render_to_string("partials/users/user_profile_card.html", context)
        return html

    def get_reports(self):
        from jobtracker.enums import PhaseStatuses

        return (
            self.phase_where_report_author.prefetch_related(
                "job", "service", "feedback", "project_lead"
            )
            .filter(status__in=PhaseStatuses.ACTIVE_STATUSES)
            .order_by("-job__id", "-id")
        )

    def get_jobs(self):
        from jobtracker.models import Job

        return Job.objects.jobs_for_user(self).prefetch_related(
            "phases", "client", "unit"
        )

    def get_timeslot_comments(self, start=None, end=None):
        data = []
        today = timezone.now().today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        start = start or start_of_week
        end = end or end_of_week

        slots = self.timeslot_comments.filter(end__gte=start, start__lte=end)
        for slot in slots:
            slot_json = slot.get_schedule_json()
            # slot_json["display"] = "background"
            data.append(slot_json)
        return data

    def get_timeslots(self, start=None, end=None, selected_phases=[]):
        data = []
        today = timezone.now().today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        start = start or start_of_week
        end = end or end_of_week

        slots = self.timeslots.filter(end__gte=start, start__lte=end).prefetch_related(
            "phase", "phase__job"
        )
        for slot in slots:
            slot_json = slot.get_schedule_json()
            if selected_phases:
                if slot.phase and (
                    slot.phase not in selected_phases
                    and slot.phase.job not in selected_phases
                ):
                    slot_json["display"] = "background"
            data.append(slot_json)
        return data

    def get_timeslots_objs(self, start_date, end_date):
        """
        Gets all timeslots overlapping the range

        Args:
            start_date (datetime): Start of the date range to clear
            end_date (datetime): End of the date range to clear

        Returns:
            queryset: affected_timeslots - Lists of affected timeslots
        """
        from django.utils import timezone

        tz = timezone.get_current_timezone()
        if isinstance(start_date, date) and not isinstance(
            start_date, datetime.datetime
        ):
            start_date = datetime.datetime.combine(
                start_date, datetime.time.min
            ).replace(tzinfo=tz)
        elif isinstance(start_date, datetime.datetime) and start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=tz)

        # Convert end_date to datetime (end of day if it's a date object)
        if isinstance(end_date, date) and not isinstance(end_date, datetime.datetime):
            # If end_date is a date, use the end of that day (23:59:59)
            end_date = datetime.datetime.combine(end_date, datetime.time.max).replace(
                tzinfo=tz
            )
        elif isinstance(end_date, datetime.datetime) and end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=tz)

        # Validate dates
        if start_date >= end_date:
            raise ValueError("Start date must be before end date")

        # Find timeslots that overlap with the range
        queryset = self.timeslots.filter(start__lt=end_date, end__gt=start_date)
        return queryset

    def get_timeslot_comments_objs(self, start_date, end_date):
        """
        Gets all timeslot comments overlapping the range

        Args:
            start_date (datetime): Start of the date range to clear
            end_date (datetime): End of the date range to clear

        Returns:
            queryset: affected_timeslot_comments - Lists of affected timeslot comments
        """
        from django.utils import timezone

        tz = timezone.get_current_timezone()
        if isinstance(start_date, date) and not isinstance(
            start_date, datetime.datetime
        ):
            start_date = datetime.datetime.combine(
                start_date, datetime.time.min
            ).replace(tzinfo=tz)
        elif isinstance(start_date, datetime.datetime) and start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=tz)

        # Convert end_date to datetime (end of day if it's a date object)
        if isinstance(end_date, date) and not isinstance(end_date, datetime.datetime):
            # If end_date is a date, use the end of that day (23:59:59)
            end_date = datetime.datetime.combine(end_date, datetime.time.max).replace(
                tzinfo=tz
            )
        elif isinstance(end_date, datetime.datetime) and end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=tz)

        # Validate dates
        if start_date >= end_date:
            raise ValueError("Start date must be before end date")

        # Find timeslots that overlap with the range
        queryset = self.timeslot_comments.filter(start__lt=end_date, end__gt=start_date)
        return queryset

    def clear_timeslots_in_range(
        self, start_date, end_date, respect_working_hours=True
    ):
        """
        Clear timeslots in a date range for the user.
        This method handles partial overlaps by splitting timeslots as needed.

        Args:
            start_date (datetime): Start of the date range to clear
            end_date (datetime): End of the date range to clear

        Returns:
            tuple: (affected_timeslots, created_timeslots) - Lists of affected and newly created timeslots
        """
        from django.utils import timezone
        from django.db import transaction
        from jobtracker.models import TimeSlot
        from django.forms.models import model_to_dict

        # Ensure we have datetime objects with proper timezone
        tz = timezone.get_current_timezone()

        # Convert date to datetime (start of day)
        if isinstance(start_date, date) and not isinstance(
            start_date, datetime.datetime
        ):
            start_date = datetime.datetime.combine(
                start_date, datetime.time.min
            ).replace(tzinfo=tz)
        elif isinstance(start_date, datetime.datetime) and start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=tz)

        # Convert end_date to datetime (end of day if it's a date object)
        if isinstance(end_date, date) and not isinstance(end_date, datetime.datetime):
            # If end_date is a date, use the end of that day (23:59:59)
            end_date = datetime.datetime.combine(end_date, datetime.time.max).replace(
                tzinfo=tz
            )
        elif isinstance(end_date, datetime.datetime) and end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=tz)

        # Validate dates
        if start_date >= end_date:
            raise ValueError("Start date must be before end date")

        affected_timeslots = []
        created_timeslots = []

        # Find timeslots that overlap with the range
        queryset = self.timeslots.filter(start__lt=end_date, end__gt=start_date)

        # Process each overlapping timeslot
        with transaction.atomic():
            for slot in queryset:
                affected_timeslots.append(slot)

                # Case 1: Slot starts before range and ends after range (completely encompasses)
                if slot.start < start_date and slot.end > end_date:
                    # Create two new slots: one before and one after the range
                    slot_data = model_to_dict(
                        slot,
                        exclude=[
                            "id",
                            "start",
                            "end",
                            "user",
                            "slot_type",
                            "phase",
                            "project",
                        ],
                    )

                    # For the "before" slot, adjust the end time to working hours if needed
                    adjusted_end = self.adjust_to_working_hours(
                        start_date, is_end_time=True
                    )

                    # Only create "before" slot if it would have non-zero duration
                    if adjusted_end > slot.start:
                        before_slot = TimeSlot.objects.create(
                            user=slot.user,
                            slot_type=slot.slot_type,
                            phase=slot.phase,
                            project=slot.project,
                            start=slot.start,
                            end=adjusted_end,
                            **slot_data,
                        )
                        created_timeslots.append(before_slot)

                    # For the "after" slot, adjust the start time to working hours if needed
                    if respect_working_hours:
                        adjusted_start = self.get_next_workday_start(end_date)
                    else:
                        adjusted_start = datetime.datetime.combine(
                            end_date.date() + datetime.timedelta(days=1),
                            datetime.time.min,
                        ).replace(tzinfo=end_date.tzinfo)

                    # Only create "after" slot if it would have non-zero duration
                    if slot.end > adjusted_start:
                        after_slot = TimeSlot.objects.create(
                            user=slot.user,
                            start=adjusted_start,
                            slot_type=slot.slot_type,
                            phase=slot.phase,
                            project=slot.project,
                            end=slot.end,
                            **slot_data,
                        )
                        created_timeslots.append(after_slot)

                    slot.delete()

                # Case 2: Slot starts before range and ends within or at the end of range
                elif slot.start < start_date and slot.end <= end_date:
                    # Create one new slot before the range
                    slot_data = model_to_dict(
                        slot,
                        exclude=[
                            "id",
                            "start",
                            "end",
                            "user",
                            "slot_type",
                            "phase",
                            "project",
                        ],
                    )

                    # Adjust the end time to working hours if needed
                    adjusted_end = self.adjust_to_working_hours(
                        start_date, is_end_time=True
                    )

                    # Only create the new slot if it would have non-zero duration
                    if adjusted_end > slot.start:
                        before_slot = TimeSlot.objects.create(
                            user=slot.user,
                            start=slot.start,
                            slot_type=slot.slot_type,
                            phase=slot.phase,
                            project=slot.project,
                            end=adjusted_end,
                            **slot_data,
                        )
                        created_timeslots.append(before_slot)

                    slot.delete()

                # Case 3: Slot starts within or at start of range and ends after range
                elif slot.start >= start_date and slot.end > end_date:
                    # Determine the appropriate start time for the new slot
                    if respect_working_hours:
                        adjusted_start = self.get_next_workday_start(end_date)
                    else:
                        adjusted_start = datetime.datetime.combine(
                            end_date.date() + datetime.timedelta(days=1),
                            datetime.time.min,
                        ).replace(tzinfo=end_date.tzinfo)

                    # Special case: If the slot ends too close to the adjusted start, don't create a new slot
                    if (
                        slot.end - adjusted_start
                    ).total_seconds() < 900:  # Less than 15 minutes
                        slot.delete()
                    else:
                        # Create one new slot after the range
                        slot_data = model_to_dict(
                            slot,
                            exclude=[
                                "id",
                                "start",
                                "end",
                                "user",
                                "slot_type",
                                "phase",
                                "project",
                            ],
                        )

                        after_slot = TimeSlot.objects.create(
                            user=slot.user,
                            start=adjusted_start,
                            slot_type=slot.slot_type,
                            phase=slot.phase,
                            project=slot.project,
                            end=slot.end,
                            **slot_data,
                        )

                        created_timeslots.append(after_slot)
                        slot.delete()

                # Case 4: Slot is completely within the range
                else:
                    # Just delete the slot as it's completely covered by the range
                    slot.delete()

        return affected_timeslots, created_timeslots

    def clear_timeslot_comments_in_range(
        self, start_date, end_date, respect_working_hours=True
    ):
        """
        Clear timeslots in a date range for the user.
        This method handles partial overlaps by splitting timeslots as needed.

        Args:
            start_date (datetime): Start of the date range to clear
            end_date (datetime): End of the date range to clear

        Returns:
            tuple: (affected_timeslots, created_timeslots) - Lists of affected and newly created timeslots
        """
        from django.utils import timezone
        from django.db import transaction
        from jobtracker.models import TimeSlotComment
        from django.forms.models import model_to_dict

        # Ensure we have datetime objects with proper timezone
        tz = timezone.get_current_timezone()

        # Convert date to datetime (start of day)
        if isinstance(start_date, date) and not isinstance(
            start_date, datetime.datetime
        ):
            start_date = datetime.datetime.combine(
                start_date, datetime.time.min
            ).replace(tzinfo=tz)
        elif isinstance(start_date, datetime.datetime) and start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=tz)

        # Convert end_date to datetime (end of day if it's a date object)
        if isinstance(end_date, date) and not isinstance(end_date, datetime.datetime):
            # If end_date is a date, use the end of that day (23:59:59)
            end_date = datetime.datetime.combine(end_date, datetime.time.max).replace(
                tzinfo=tz
            )
        elif isinstance(end_date, datetime.datetime) and end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=tz)

        # Validate dates
        if start_date >= end_date:
            raise ValueError("Start date must be before end date")

        affected_timeslots = []
        created_timeslots = []

        # Find timeslots that overlap with the range
        queryset = self.timeslot_comments.filter(start__lt=end_date, end__gt=start_date)

        # Process each overlapping timeslot
        with transaction.atomic():
            for slot in queryset:
                affected_timeslots.append(slot)

                # Case 1: Slot starts before range and ends after range (completely encompasses)
                if slot.start < start_date and slot.end > end_date:
                    # Create two new slots: one before and one after the range
                    slot_data = model_to_dict(
                        slot, exclude=["id", "start", "end", "user"]
                    )

                    # For the "before" slot, adjust the end time to working hours if needed
                    adjusted_end = self.adjust_to_working_hours(
                        start_date, is_end_time=True
                    )

                    # Only create "before" slot if it would have non-zero duration
                    if adjusted_end > slot.start:
                        before_slot = TimeSlotComment.objects.create(
                            user=slot.user,
                            start=slot.start,
                            end=adjusted_end,
                            **slot_data,
                        )
                        created_timeslots.append(before_slot)

                    # For the "after" slot, adjust the start time to working hours if needed
                    if respect_working_hours:
                        adjusted_start = self.get_next_workday_start(end_date)
                    else:
                        adjusted_start = datetime.datetime.combine(
                            end_date.date() + datetime.timedelta(days=1),
                            datetime.time.min,
                        ).replace(tzinfo=end_date.tzinfo)

                    # Only create "after" slot if it would have non-zero duration
                    if slot.end > adjusted_start:
                        after_slot = TimeSlotComment.objects.create(
                            user=slot.user,
                            start=adjusted_start,
                            end=slot.end,
                            **slot_data,
                        )
                        created_timeslots.append(after_slot)

                    slot.delete()

                # Case 2: Slot starts before range and ends within or at the end of range
                elif slot.start < start_date and slot.end <= end_date:
                    # Create one new slot before the range
                    slot_data = model_to_dict(
                        slot, exclude=["id", "start", "end", "user"]
                    )

                    # Adjust the end time to working hours if needed
                    adjusted_end = self.adjust_to_working_hours(
                        start_date, is_end_time=True
                    )

                    # Only create the new slot if it would have non-zero duration
                    if adjusted_end > slot.start:
                        before_slot = TimeSlotComment.objects.create(
                            user=slot.user,
                            start=slot.start,
                            end=adjusted_end,
                            **slot_data,
                        )
                        created_timeslots.append(before_slot)

                    slot.delete()

                # Case 3: Slot starts within or at start of range and ends after range
                elif slot.start >= start_date and slot.end > end_date:
                    # Determine the appropriate start time for the new slot
                    if respect_working_hours:
                        adjusted_start = self.get_next_workday_start(end_date)
                    else:
                        adjusted_start = datetime.datetime.combine(
                            end_date.date() + datetime.timedelta(days=1),
                            datetime.time.min,
                        ).replace(tzinfo=end_date.tzinfo)

                    # Special case: If the slot ends too close to the adjusted start, don't create a new slot
                    if (
                        slot.end - adjusted_start
                    ).total_seconds() < 900:  # Less than 15 minutes
                        slot.delete()
                    else:
                        # Create one new slot after the range
                        slot_data = model_to_dict(
                            slot, exclude=["id", "start", "end", "user"]
                        )

                        after_slot = TimeSlotComment.objects.create(
                            user=slot.user,
                            start=adjusted_start,
                            end=slot.end,
                            **slot_data,
                        )

                        created_timeslots.append(after_slot)
                        slot.delete()

                # Case 4: Slot is completely within the range
                else:
                    # Just delete the slot as it's completely covered by the range
                    slot.delete()

        return affected_timeslots, created_timeslots

    def get_holidays(self, start=None, end=None):
        from ..models import Holiday

        data = []

        today = timezone.now().today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        start = start or start_of_week
        end = end or end_of_week

        slots = Holiday.objects.filter(
            Q(country=self.country) | Q(country__isnull=True),
            date__gte=start.date(),
            date__lte=end.date(),
        )
        for slot in slots:
            data.append(slot.get_schedule_json())
        return data

    def is_people_manager(self):
        if self.users_managed.exists() or self.users_acting_managed.exists():
            return True
        else:
            return False

    def save(self, *args, **kwargs):
        # Lets check if we're the only user...
        if User.objects.all().count() == 1:
            # We're the first real user. Bump us to superuser
            self.is_superuser = True
            self.is_staff = True
            super().save(*args, **kwargs)
            # Make sure they are a global admin too!
            g_admin, _ = Group.objects.get_or_create(
                name=settings.GLOBAL_GROUP_PREFIX
                + GlobalRoles.CHOICES[GlobalRoles.ADMIN][1]
            )
            self.groups.add(g_admin)
        return super().save(*args, **kwargs)

    def services_can_lead(self):
        from jobtracker.models import Service

        return Service.objects.filter(
            Q(skillsRequired__in=self.get_skills_specialist())
            | Q(skillsRequired__in=self.get_skills_alone())
        ).distinct()

    def services_can_contribute(self):
        from jobtracker.models import Service

        return Service.objects.filter(
            Q(skillsRequired__in=self.get_skills_support())
        ).distinct()

    def get_active_qualifications(self):
        from jobtracker.enums import QualificationStatus

        return self.qualifications.filter(
            status=QualificationStatus.AWARDED
        ).prefetch_related("qualification", "qualification__awarding_body")

    def get_skills_specialist(self):
        from jobtracker.models import Skill

        return (
            Skill.objects.filter(
                pk__in=self.skills.filter(rating=UserSkillRatings.SPECIALIST).values(
                    "skill"
                )
            )
            .prefetch_related("category")
            .distinct()
        )

    def get_skills_alone(self):
        from jobtracker.models import Skill

        return (
            Skill.objects.filter(
                pk__in=self.skills.filter(rating=UserSkillRatings.CAN_DO_ALONE).values(
                    "skill"
                )
            )
            .prefetch_related("category")
            .distinct()
        )

    def get_skills_support(self):
        from jobtracker.models import Skill

        return (
            Skill.objects.filter(
                pk__in=self.skills.filter(
                    rating=UserSkillRatings.CAN_DO_WITH_SUPPORT
                ).values("skill")
            )
            .prefetch_related("category")
            .distinct()
        )

    def __str__(self):
        if self.first_name and self.last_name:
            return "{} {}".format(self.first_name, self.last_name)
        else:
            return "{}".format(self.email)

    def get_average_qa_rating(
        self,
        qa_field,
        from_range=timezone.now() - relativedelta(months=12),
        to_range=timezone.now(),
    ):
        my_reports = (
            self.get_reports()
            .filter(
                actual_completed_date__gte=from_range,
                actual_completed_date__lte=to_range,
            )
            .only(qa_field, "job_id")
        )
        total_reports = 0
        combined_score = 0
        total_score = 0

        for report in my_reports:
            # check we've got rating!
            rating = getattr(report, qa_field)
            if rating:
                combined_score = combined_score + (int(rating))
                total_reports = total_reports + 1

        if total_reports > 0:
            total_score = combined_score / total_reports

        return total_score

    def get_average_techqa_feedback(
        self,
        from_range=timezone.now() - relativedelta(months=12),
        to_range=timezone.now(),
    ):
        return (
            self.get_reports()
            .filter(
                actual_completed_date__gte=from_range,
                actual_completed_date__lte=to_range,
            )
            .aggregate(avg_techqa_rating=Avg("techqa_report_rating"))[
                "avg_techqa_rating"
            ]
        )

    def get_average_presqa_feedback(
        self,
        from_range=timezone.now() - relativedelta(months=12),
        to_range=timezone.now(),
    ):
        return (
            self.get_reports()
            .filter(
                actual_completed_date__gte=from_range,
                actual_completed_date__lte=to_range,
            )
            .aggregate(avg_presqa_rating=Avg("presqa_report_rating"))[
                "avg_presqa_rating"
            ]
        )

    def get_combined_average_qa_rating_12mo(self):
        from_range = timezone.now() - relativedelta(months=12)
        to_range = timezone.now()

        data = (
            self.get_reports()
            .filter(
                actual_completed_date__gte=from_range,
                actual_completed_date__lte=to_range,
            )
            .aggregate(
                avg_presqa_rating=Avg("presqa_report_rating"),
                avg_techqa_rating=Avg("techqa_report_rating"),
            )
        )
        presqa_rating = data["avg_presqa_rating"] or 0
        techqa_rating = data["avg_techqa_rating"] or 0

        # Handle cases where one or both ratings could be None
        if presqa_rating is None and techqa_rating is None:
            return 0  # or None, depending on what makes sense for your application

        if presqa_rating is None:
            return techqa_rating  # Return only the techqa rating if presqa is None

        if techqa_rating is None:
            return presqa_rating  # Return only the presqa rating if techqa is None

        # If both ratings are available, return their average
        return (presqa_rating + techqa_rating) / 2

    def get_average_qa_rating_12mo(self, qa_field):
        from chaotica_utils.utils import last_day_of_month

        # Get the last 12 months of tech feedback
        months = []
        data = []
        today = timezone.now()
        for i in range(12, -1, -1):
            month = today - relativedelta(months=i)
            start_month = month + relativedelta(day=1)
            end_month = last_day_of_month(start_month)
            avg = self.get_average_qa_rating(
                qa_field, from_range=start_month, to_range=end_month
            )
            months.append(str(start_month.date()))
            data.append(avg)

        data = {
            "months": months,
            "data": data,
        }
        return data

    def get_average_techqa_feedback_12mo(self):
        return self.get_average_qa_rating_12mo("techqa_report_rating")

    def get_average_presqa_feedback_12mo(self):
        return self.get_average_qa_rating_12mo("presqa_report_rating")

    def current_cost(self):
        if self.costs.all().exists():
            return self.costs.all().last()
        else:
            return None

    def update_cost(self, cost, effective_from=timezone.now()):
        return UserCost.objects.create(
            user=self, effective_from=effective_from, cost_per_hour=cost
        )

    #### WORKING HOURS/DAYS STUFF
    ## Terms:
    ## working = when the business is open and staff "could" work
    ## available = when the individual is in work

    def get_working_hours(self):
        # Logic should be working hours from our org?
        data = dict()
        if self.unit_memberships.exists():
            data["start"] = self.unit_memberships.first().unit.businessHours_startTime
            data["end"] = self.unit_memberships.first().unit.businessHours_endTime
        else:
            # Do site defaults...
            data["start"] = timezone.datetime.time(9, 0, 0)
            data["end"] = timezone.datetime.time(17, 30, 0)
        return data

    # Helper function to adjust to working hours
    def adjust_to_working_hours(self, dt, is_end_time=False):
        """Adjust datetime to respect working hours"""
        working_hours = self.get_working_hours()

        day_start = datetime.datetime.combine(
            dt.date(), working_hours["start"]
        ).replace(tzinfo=dt.tzinfo)
        day_end = datetime.datetime.combine(dt.date(), working_hours["end"]).replace(
            tzinfo=dt.tzinfo
        )

        # If it's an end time and falls in the middle of a day, use end of workday
        if (
            is_end_time
            and dt.time() > working_hours["start"]
            and dt.time() < working_hours["end"]
        ):
            return day_end

        # If it's a start time and falls in the middle of a day, use start of workday
        if (
            not is_end_time
            and dt.time() > working_hours["start"]
            and dt.time() < working_hours["end"]
        ):
            return day_start

        # For start times: if before workday start, use workday start
        if not is_end_time and dt.time() < working_hours["start"]:
            return day_start

        # For end times: if after workday end, use workday end
        if is_end_time and dt.time() > working_hours["end"]:
            return day_end

        # For start times: if after workday end, use next day's workday start
        if not is_end_time and dt.time() > working_hours["end"]:
            next_day = (dt + datetime.timedelta(days=1)).date()
            return datetime.datetime.combine(next_day, working_hours["start"]).replace(
                tzinfo=dt.tzinfo
            )

        # For end times: if before workday start, use previous day's workday end
        if is_end_time and dt.time() < working_hours["start"]:
            prev_day = (dt - datetime.timedelta(days=1)).date()
            return datetime.datetime.combine(prev_day, working_hours["end"]).replace(
                tzinfo=dt.tzinfo
            )

        return dt

    # Helper function to get next workday start
    def get_next_workday_start(self, dt):
        """Get the start of the next workday"""
        next_day = (dt + datetime.timedelta(days=1)).date()
        working_hours = self.get_working_hours()
        return datetime.datetime.combine(next_day, working_hours["start"]).replace(
            tzinfo=dt.tzinfo
        )

    def get_working_days_in_range(
        self, org, start_date, end_date, org_working_days_list=None
    ):
        from ..models import Holiday

        days_list = []
        if not (isinstance(start_date, date) and isinstance(end_date, date)):
            raise TypeError(
                "Both start_date and end_date must be datetime.date objects"
            )

        # Ensure that the start date is before or equal to the end date.
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        # Make sure dates are in same TZ and at max range
        start_date = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )
        end_date = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

        # Get org dates as a starting point
        if not org_working_days_list:
            org_working_days_list = org.get_working_days_in_range(start_date, end_date)

        holidays = Holiday.objects.get_date_list(start_date, end_date, self.country)

        # Now lets iter through and only add dates that we work
        for current_date in org_working_days_list:
            is_working_day = current_date not in holidays
            if is_working_day:
                days_list.append(current_date)

        return days_list

    def get_non_delivery_days_in_range(self, start_date, end_date, working_days=None):
        from ..utils import make_datetime_tzaware
        from jobtracker.enums import (
            PhaseStatuses,
        )

        days_list = []
        if not (isinstance(start_date, date) and isinstance(end_date, date)):
            raise TypeError(
                "Both start_date and end_date must be datetime.date objects"
            )

        # Ensure that the start date is before or equal to the end date.
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        # Make sure dates are in same TZ and at max range
        start_date = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )
        end_date = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

        if not working_days:
            working_days = self.get_working_days_in_range(
                self.unit_memberships.first().unit, start_date, end_date
            )

        # Now lets iter through and only add dates that we work
        current_date = make_datetime_tzaware(
            timezone.datetime.combine(start_date, timezone.datetime.min.time())
            + timedelta(hours=12)
        )
        while current_date.date() <= end_date:
            if current_date.date() in working_days:
                is_confirmed_day = self.timeslots.filter(
                    (Q(start__lte=current_date) & Q(end__gte=current_date))
                    | (Q(start__lt=current_date) & Q(end__gt=current_date)),
                    phase__isnull=True,
                    project__isnull=True,
                    slot_type__is_delivery=False,
                ).exists()
                if is_confirmed_day:
                    days_list.append(current_date)

            current_date += timedelta(days=1)

        return days_list

    def get_delivery_confirmed_days_in_range(
        self, start_date, end_date, working_days=[]
    ):
        from ..utils import make_datetime_tzaware
        from jobtracker.enums import (
            PhaseStatuses,
        )

        days_list = []
        if not (isinstance(start_date, date) and isinstance(end_date, date)):
            raise TypeError(
                "Both start_date and end_date must be datetime.date objects"
            )

        # Ensure that the start date is before or equal to the end date.
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        # Make sure dates are in same TZ and at max range
        start_date = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )
        end_date = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

        if not working_days:
            working_days = self.get_working_days_in_range(
                self.unit_memberships.first().unit, start_date, end_date
            )

        # Now lets iter through and only add dates that we work
        current_date = make_datetime_tzaware(
            timezone.datetime.combine(start_date, timezone.datetime.min.time())
            + timedelta(hours=12)
        )
        while current_date.date() <= end_date:
            if current_date.date() in working_days:
                is_confirmed_day = self.timeslots.filter(
                    (Q(start__lte=current_date) & Q(end__gte=current_date))
                    | (Q(start__lt=current_date) & Q(end__gt=current_date)),
                    (
                        Q(phase__isnull=False)
                        & Q(phase__status__gte=PhaseStatuses.SCHEDULED_CONFIRMED)
                    )
                    | Q(project__isnull=False),
                ).exists()
                if is_confirmed_day:
                    days_list.append(current_date)

            current_date += timedelta(days=1)

        return days_list

    def get_delivery_tentative_days_in_range(
        self, start_date, end_date, working_days=[]
    ):
        from ..utils import make_datetime_tzaware
        from jobtracker.enums import (
            PhaseStatuses,
        )

        days_list = []
        if not (isinstance(start_date, date) and isinstance(end_date, date)):
            raise TypeError(
                "Both start_date and end_date must be datetime.date objects"
            )

        # Ensure that the start date is before or equal to the end date.
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        # Make sure dates are in same TZ and at max range
        start_date = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )
        end_date = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

        if not working_days:
            working_days = self.get_working_days_in_range(
                self.unit_memberships.first().unit, start_date, end_date
            )

        # Now lets iter through and only add dates that we work
        current_date = make_datetime_tzaware(
            timezone.datetime.combine(start_date, timezone.datetime.min.time())
            + timedelta(hours=12)
        )

        while current_date.date() <= end_date:
            if current_date.date() in working_days:
                is_confirmed_day = self.timeslots.filter(
                    (Q(start__lte=current_date) & Q(end__gte=current_date))
                    | (Q(start__lt=current_date) & Q(end__gt=current_date)),
                    slot_type__is_delivery=True,
                    phase__status__lt=PhaseStatuses.SCHEDULED_CONFIRMED,
                ).exists()
                if is_confirmed_day:
                    days_list.append(current_date)

            current_date += timedelta(days=1)

        return days_list

    def get_available_days_in_range(self, start_date, end_date, working_days=[]):
        from ..utils import make_datetime_tzaware

        days_list = []
        if not (isinstance(start_date, date) and isinstance(end_date, date)):
            raise TypeError(
                "Both start_date and end_date must be datetime.date objects"
            )

        # Ensure that the start date is before or equal to the end date.
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        # Make sure dates are in same TZ and at max range
        start_date = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )
        end_date = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

        if not working_days:
            working_days = self.get_working_days_in_range(
                self.unit_memberships.first().unit, start_date, end_date
            )

        # Now lets iter through and only add dates that we work
        current_date = make_datetime_tzaware(
            timezone.datetime.combine(start_date, timezone.datetime.min.time())
            + timedelta(hours=12)
        )
        while current_date.date() <= end_date:
            if current_date.date() in working_days:
                is_working_day = self.timeslots.filter(
                    (Q(start__lte=current_date) & Q(end__gte=current_date))
                    | (Q(start__lt=current_date) & Q(end__gt=current_date))
                ).exists()
                if not is_working_day:
                    days_list.append(current_date)

            current_date += timedelta(days=1)

        return days_list

    def get_scheduled_days_in_range(self, start_date, end_date):
        from ..utils import make_datetime_tzaware

        days_list = []
        if not (isinstance(start_date, date) and isinstance(end_date, date)):
            raise TypeError(
                "Both start_date and end_date must be datetime.date objects"
            )

        # Ensure that the start date is before or equal to the end date.
        if start_date > end_date:
            start_date, end_date = end_date, start_date

        # Now lets iter through and only add dates that we work
        current_date = make_datetime_tzaware(
            timezone.datetime.combine(start_date, timezone.datetime.min.time())
            + timedelta(hours=12)
        )
        while current_date.date() <= end_date:
            is_working_day = self.timeslots.filter(
                (Q(start__lte=current_date) & Q(end__gte=current_date))
                | (Q(start__lt=current_date) & Q(end__gt=current_date))
            ).exists()
            if is_working_day:
                days_list.append(current_date)

            current_date += timedelta(days=1)

        return days_list

    def get_availability(
        self, start_date, end_date, org=None, org_working_days_list=None
    ):
        data = {}

        if not org:
            org = self.unit_memberships.first().unit

        # Ensure that the start date is before or equal to the end date.
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        # Make sure dates are in same TZ and at max range
        start_date = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )
        end_date = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

        data["working_days_list"] = self.get_working_days_in_range(
            org, start_date, end_date, org_working_days_list=org_working_days_list
        )

        if len(data["working_days_list"]) > 0:
            data["scheduled_days_list"] = self.get_scheduled_days_in_range(
                start_date, end_date
            )
            data["scheduled_days_perc"] = round(
                len(data["scheduled_days_list"]) / len(data["working_days_list"]) * 100,
                1,
            )
            data["tentative_days_list"] = self.get_delivery_tentative_days_in_range(
                start_date, end_date, data["working_days_list"]
            )
            data["tentative_days_perc"] = round(
                len(data["tentative_days_list"]) / len(data["working_days_list"]) * 100,
                1,
            )
            data["confirmed_days_list"] = self.get_delivery_confirmed_days_in_range(
                start_date, end_date, data["working_days_list"]
            )
            data["confirmed_days_perc"] = round(
                len(data["confirmed_days_list"]) / len(data["working_days_list"]) * 100,
                1,
            )

            data["non_delivery_days_list"] = self.get_non_delivery_days_in_range(
                start_date, end_date, data["working_days_list"]
            )
            data["non_delivery_days_perc"] = round(
                len(data["non_delivery_days_list"])
                / len(data["working_days_list"])
                * 100,
                1,
            )

            data["available_days_list"] = self.get_available_days_in_range(
                start_date, end_date, data["working_days_list"]
            )
            data["available_days_perc"] = round(
                len(data["available_days_list"]) / len(data["working_days_list"]) * 100,
                1,
            )
        else:
            data["non_delivery_days_list"] = []
            data["non_delivery_days_perc"] = 0
            data["scheduled_days_list"] = []
            data["scheduled_days_perc"] = 0
            data["tentative_days_list"] = []
            data["tentative_days_perc"] = 0
            data["confirmed_days_list"] = []
            data["confirmed_days_perc"] = 0
            data["available_days_list"] = []
            data["available_days_perc"] = 0

        return data

    def get_utilisation_perc(self, org=None, start_date=None, end_date=None):
        util = 0
        if not start_date:
            start_date = (timezone.now().date() - timedelta(days=30)).date()
        if not end_date:
            end_date = timezone.now().date().date()

        # Ensure that the start date is before or equal to the end date.
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        # Make sure dates are in same TZ and at max range
        start_date = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )
        end_date = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

        if not org:
            org = self.unit_memberships.first().unit

        working_days_list = self.get_working_days_in_range(org, start_date, end_date)
        confirmed_days_list = self.get_delivery_confirmed_days_in_range(
            start_date, end_date, working_days_list
        )

        # util is calculated as
        if len(working_days_list) > 0:
            util = round(len(confirmed_days_list) / len(working_days_list) * 100, 1)

        return util

    def get_stats(self, org=None, start_date=None, end_date=None):
        data = {
            "ranged": {},
            "availability": {},
            "service_breakdown": {},
        }
        # clean vars
        if not start_date:
            start_date = timezone.now() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now()

        # Ensure that the start date is before or equal to the end date.
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        # Make sure dates are in same TZ and at max range
        start_date = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )
        end_date = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

        if not org:
            org = self.unit_memberships.first().unit

        # ranged stats
        data["ranged"]["org"] = org
        data["ranged"]["start_date"] = start_date
        data["ranged"]["end_date"] = end_date

        # TEMP REMOVE
        # data["ranged"]["working_days_list"] = self.get_working_days_in_range(
        #     org, start_date, end_date
        # )
        # data["ranged"]["scheduled_days_list"] = self.get_scheduled_days_in_range(
        #     start_date, end_date
        # )
        # data["ranged"]["confirmed_days_list"] = (
        #     self.get_delivery_confirmed_days_in_range(
        #         start_date, end_date, data["ranged"]["working_days_list"]
        #     )
        # )
        # data["ranged"]["utilisation_perc"] = 0
        # # util is calculated as
        # if len(data["ranged"]["working_days_list"]) > 0:
        #     data["ranged"]["utilisation_perc"] = round(
        #         len(data["ranged"]["confirmed_days_list"])
        #         / len(data["ranged"]["working_days_list"])
        #         * 100,
        #         1,
        #     )

        data["availability"] = self.calculate_user_utilization(start_date, end_date)

        # Get future availability
        data["upcoming_availability"] = self.get_upcoming_availability()

        # Get service breakdown
        # data["service_breakdown"] = self.get_service_breakdown(
        #     avail_start, avail_eightweeks
        # )

        return data

    def calculate_user_utilization(self, start_date, end_date, org=None):
        """
        Calculate utilization statistics for a user within a date range.

        Args:
            user_id: The ID of the user to analyze
            start_date: datetime object for the start of the period
            end_date: datetime object for the end of the period

        Returns:
            dict: Statistics including available_days, scheduled_days, tentative_days,
                confirmed_days, and non_delivery_days
        """
        # Prepare holiday bits
        from .models import Holiday

        holidays = Holiday.objects.filter(
            country=self.country, date__range=(start_date, end_date)
        ).values_list("date", flat=True)
        # Convert to set for faster lookups
        holiday_dates = set(
            h.date() if isinstance(h, timezone.datetime) else h for h in holidays
        )

        # Prepare org working_days
        if not org:
            org = self.unit_memberships.first().unit
        working_days = org.businessHours_days

        # First, get all timeslots that overlap with our date range
        timeslots = self.timeslots.filter(
            start__date__lte=end_date, end__date__gte=start_date
        ).annotate(
            date=TruncDate("start"),
            # Calculate if slot is tentative (phase status < 6)
            is_tentative=Case(
                When(
                    phase__status__lt=PhaseStatuses.SCHEDULED_CONFIRMED, then=Value(1)
                ),
                When(
                    phase__status__gte=PhaseStatuses.SCHEDULED_CONFIRMED, then=Value(0)
                ),
                When(phase__isnull=True, then=Value(0)),
                default=Value(0),
                output_field=models.IntegerField(),
            ),
            # Calculate if slot is confirmed (phase status >= 6)
            is_confirmed=Case(
                When(
                    phase__status__gte=PhaseStatuses.SCHEDULED_CONFIRMED, then=Value(1)
                ),
                When(
                    phase__status__lt=PhaseStatuses.SCHEDULED_CONFIRMED, then=Value(0)
                ),
                When(phase__isnull=True, then=Value(0)),
                default=Value(0),
                output_field=models.IntegerField(),
            ),
            # Calculate if slot has no phase (non-delivery)
            is_non_delivery=Case(
                When(phase__isnull=True, then=Value(1)),
                default=Value(0),
                output_field=models.IntegerField(),
            ),
        )

        # Create a DataFrame with all dates in range
        date_range = pd.date_range(start=start_date, end=end_date, freq="D")
        dates_df = pd.DataFrame({"date": date_range})
        # Convert to date (not datetime)
        dates_df["date"] = dates_df["date"].dt.date

        # Add holiday indicator
        dates_df["is_holiday"] = dates_df["date"].apply(
            lambda x: 1 if x in holiday_dates else 0
        )
        dates_df["is_working_day"] = dates_df["date"].apply(
            lambda x: 1 if (x.weekday() + 1) in working_days else 0
        )

        # Convert timeslots to DataFrame for easier date-wise aggregation
        slots_data = []
        for slot in timeslots:
            # Generate a row for each day the slot spans
            current_date = max(slot.start.date(), start_date.date())
            end_date_slot = min(slot.end.date(), end_date.date())

            while current_date <= end_date_slot:
                # Skip holidays when counting utilization
                if (
                    current_date.weekday() + 1
                ) in working_days and current_date not in holiday_dates:
                    slots_data.append(
                        {
                            "date": current_date,
                            "is_tentative": slot.is_tentative,
                            "is_confirmed": slot.is_confirmed,
                            "is_non_delivery": slot.is_non_delivery,
                        }
                    )
                current_date += timedelta(days=1)

        slots_df = pd.DataFrame(slots_data)

        # If we have any slots, merge and calculate daily statistics
        if len(slots_df) > 0:
            # Group by date and aggregate
            daily_stats = (
                slots_df.groupby("date")
                .agg(
                    {
                        "is_tentative": "sum",
                        "is_confirmed": "sum",
                        "is_non_delivery": "sum",
                    }
                )
                .reset_index()
            )

            # Merge with full date range
            final_df = dates_df.merge(daily_stats, on="date", how="left").fillna(0)
        else:
            # If no slots, create empty statistics
            final_df = dates_df.copy()
            final_df["is_tentative"] = 0
            final_df["is_confirmed"] = 0
            final_df["is_non_delivery"] = 0

        # Calculate statistics
        total_days = len(date_range)
        holiday_days = len(final_df[final_df["is_holiday"] > 0])
        non_working_days = len(final_df[final_df["is_working_day"] == 0])

        work_days = len(
            final_df[(final_df["is_holiday"] == 0) & (final_df["is_working_day"] == 1)]
        )

        # Only count scheduled days on working days that aren't holidays
        scheduled_days = len(
            final_df[
                (final_df["is_holiday"] == 0)
                & (final_df["is_working_day"] == 1)
                & (
                    (final_df["is_tentative"] > 0)
                    | (final_df["is_confirmed"] > 0)
                    | (final_df["is_non_delivery"] > 0)
                )
            ]
        )

        data = {
            "total_days": total_days,
            "working_days": work_days,
            "non_working_days": non_working_days,
            "holiday_days": holiday_days,
            "available_days": work_days - scheduled_days,
            "scheduled_days": scheduled_days,
            "tentative_days": len(
                final_df[
                    (final_df["is_holiday"] == 0)
                    & (final_df["is_working_day"] == 1)
                    & (final_df["is_tentative"] > 0)
                ]
            ),
            "confirmed_days": len(
                final_df[
                    (final_df["is_holiday"] == 0)
                    & (final_df["is_working_day"] == 1)
                    & (final_df["is_confirmed"] > 0)
                ]
            ),
            "non_delivery_days": len(
                final_df[
                    (final_df["is_holiday"] == 0)
                    & (final_df["is_working_day"] == 1)
                    & (final_df["is_non_delivery"] > 0)
                ]
            ),
        }

        ## Calculate percentages
        # Working perc (basically available working days minus holidays)
        data["working_percentage"] = calculate_percentage(
            data["working_days"], data["total_days"] - data["non_working_days"]
        )

        # util == working_days / confirmed
        data["utilisation_percentage"] = calculate_percentage(
            data["confirmed_days"], data["working_days"]
        )
        data["confirmed_percentage"] = calculate_percentage(
            data["confirmed_days"], data["working_days"]
        )
        data["tentative_percentage"] = calculate_percentage(
            data["tentative_days"], data["working_days"]
        )
        data["non_delivery_percentage"] = calculate_percentage(
            data["non_delivery_days"], data["working_days"]
        )
        data["available_percentage"] = calculate_percentage(
            data["available_days"], data["working_days"]
        )

        return data

    def get_upcoming_availability(self, org=None):
        data = {}
        # Get future availability
        # these values are not reliant on start_date and end_date
        avail_start = timezone.now() - timedelta(days=timezone.now().weekday())

        for rang, days_ahead in UpcomingAvailabilityRanges.DEFAULT.items():
            avail = avail_start + timedelta(days=days_ahead)

            data[rang] = self.calculate_user_utilization(avail_start, avail, org=org)

            # if len(data[rang]["working_days_list"]) > 0:
            #     data[rang]["utilisation_perc"] = round(
            #         len(data[rang]["confirmed_days_list"])
            #         / len(data[rang]["working_days_list"])
            #         * 100,
            #         1,
            #     )
            # else:
            #     data[rang]["utilisation_perc"] = 0

        return data

    def get_service_breakdown(self, start_date=None, end_date=None, rank_count=5):
        from jobtracker.models import Service

        top_services = Service.objects.annotate(
            participation_count=Count(
                "phases__timeslots",
                filter=Q(
                    phases__timeslots__user=self,
                    phases__timeslots__start__gte=start_date,
                    phases__timeslots__end__lte=end_date,
                ),
            )
        ).order_by("-participation_count")[:rank_count]

        (Q(start__gte=start_date) & Q(end__lte=end_date))
        return top_services


class UserCost(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET(get_sentinel_user),
        related_name="costs",
    )
    effective_from = models.DateField(
        verbose_name="Effective From",
        null=True,
        blank=True,
        help_text="Date cost applies from",
    )
    cost_per_hour = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Cost Per Hour",
        help_text="Cost of the user per hour",
    )

    class Meta:
        ordering = ["user", "-effective_from"]
        unique_together = ["user", "effective_from"]

    def __str__(self):
        return "{} {}".format(str(self.user), str(self.cost_per_hour))
