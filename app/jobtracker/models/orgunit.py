from django.db import models
from django.db.models import F, Q, Count, Case, When, Value, IntegerField, Prefetch
from django.db.models.functions import TruncDate, ExtractDay
from django.conf import settings
from chaotica_utils.utils import unique_slug_generator
from django.urls import reverse
from simple_history.models import HistoricalRecords
from guardian.shortcuts import (
    assign_perm,
    remove_perm,
    get_user_perms,
    get_users_with_perms,
)
from django.db.models import JSONField
import uuid, os, random
from chaotica_utils.models import User, get_sentinel_user, Holiday
from ..models import TimeSlot
from chaotica_utils.enums import UnitRoles, UpcomingAvailabilityRanges
from ..enums import PhaseStatuses
from django.utils import timezone
from datetime import timedelta, date, datetime
from decimal import Decimal
from django.templatetags.static import static
from django_bleach.models import BleachField
from django.db.models.functions import Lower
from django.contrib.auth.models import Permission
import pandas as pd
from collections import defaultdict


def _default_business_days():
    return [1, 2, 3, 4, 5]


def get_media_image_file_path(instance, filename):
    ext = filename.split(".")[-1]
    filename = "%s.%s" % (uuid.uuid4(), ext)
    return os.path.join("media/images", filename)


class OrganisationalUnit(models.Model):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(null=False, default="", unique=True)
    description = BleachField(default="", null=True)
    image = models.ImageField(
        default="default.jpg", upload_to=get_media_image_file_path
    )
    targetProfit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(37),
        verbose_name="Target Profit",
        help_text="The % target profit for this unit",
    )
    businessHours_startTime = models.TimeField("Start Time", default="09:00:00")
    businessHours_endTime = models.TimeField("End Time", default="17:30:00")
    businessHours_lunch_startTime = models.TimeField(
        "Lunch Start Time", default="12:00:00"
    )
    businessHours_lunch_endTime = models.TimeField("Lunch End Time", default="13:00:00")
    businessHours_days = JSONField(
        verbose_name="Days",
        null=True,
        blank=True,
        default=_default_business_days,
        help_text="An int array with the numbers equaling the day of the week. Sunday == 0, Monday == 1 etc",
    )
    approval_required = models.BooleanField(
        "Approval Required",
        default=True,
        help_text="Approval by a Manager is required to join the unit",
    )
    special_requirements = BleachField(blank=True, null=True)
    history = HistoricalRecords()
    lead = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="units_lead",
        null=True,
        on_delete=models.DO_NOTHING,
    )

    class Meta:
        ordering = [Lower("name")]
        permissions = (
            ("manage_members", "Assign Members"),
            # Job permissions
            ("can_view_jobs", "Can view jobs"),
            ("can_add_job", "Can add jobs"),
            ("can_update_job", "Can update jobs"),
            ("can_refire_notifications_job", "Can refire notifications for jobs"),
            ("can_delete_job", "Can delete jobs"),
            ("can_add_note_job", "Can add a note to jobs"),
            ("can_assign_poc_job", "Can assign a Point of Contact to jobs"),
            ("can_manage_framework_job", "Can assign a Point of Contact to jobs"),
            ("can_add_phases", "Can add phases"),
            ("can_delete_phases", "Can add phases"),
            ("can_schedule_job", "Can schedule phases"),
            ("can_deliver_job", "Can deliver a job"),
            ("view_users_schedule", "View Members Schedule"),
            ("view_job_schedule", "View a Job's Schedule"),
            ("can_scope_jobs", "Can scope jobs"),
            ("can_signoff_scopes", "Can signoff scopes"),
            ("can_signoff_own_scopes", "Can signoff own scopes"),
            ("can_tqa_jobs", "Can TQA jobs"),
            ("can_pqa_jobs", "Can PQA jobs"),
            # Notification pools
            ("notification_pool_scoping", "Scoping Pool"),
            ("notification_pool_scheduling", "Scheduling Pool"),
            ("notification_pool_tqa", "TQA Pool"),
            ("notification_pool_pqa", "PQA Pool"),
            # Leave
            (
                "can_view_all_leave_requests",
                "Can view all leave for members of the unit",
            ),
            ("can_approve_leave_requests", "Can approve leave requests"),
        )


    def get_working_days_in_range(self, start_date, end_date):
        working_days_list = []
        if not (isinstance(start_date, date) and isinstance(end_date, date)):
            raise TypeError("Both start_date and end_date must be date objects")

        # Ensure that the start date is before or equal to the end date.
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        # Make sure dates are in same TZ and at max range
        start_date = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )
        end_date = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

        # Now lets iter through and only add dates that we work
        current_date = start_date
        while current_date <= end_date:
            is_working_day = (current_date.weekday() + 1) in self.businessHours_days
            if is_working_day:
                working_days_list.append(current_date)

            current_date += timedelta(days=1)

        return working_days_list


    def sync_permissions(self):
        for user in self.get_allMembers():
            # Ensure the permissions are set right!
            existing_perms = list(
                get_user_perms(user, self).values_list("codename", flat=True)
            )

            expected_perms = []
            # get a combined list of perms from their roles...
            for ms in OrganisationalUnitMember.objects.filter(
                unit=self, member=user, left_date__isnull=True
            ):
                perm_objs = Permission.objects.filter(
                    pk__in=ms.roles.all().values_list("permissions").distinct()
                )
                for role_perm in perm_objs:
                    if role_perm.codename not in expected_perms:
                        expected_perms.append(role_perm.codename)

            if expected_perms:
                # First lets add missing perms...
                for new_perm in expected_perms:
                    if new_perm not in existing_perms:
                        assign_perm(new_perm, user, self)

                # Now lets remove old perms
                for old_perm in existing_perms:
                    if old_perm not in expected_perms:
                        remove_perm(old_perm, user, self)
            else:
                if existing_perms:
                    # We should not have any permissions! Clear them all
                    for perm in existing_perms:
                        remove_perm(perm, user, self)

    def __str__(self):
        return self.name

    def get_managers(self):
        ids = []
        for mgr in OrganisationalUnitMember.objects.filter(
            unit=self, role=UnitRoles.MANAGER
        ):
            if mgr.member.pk not in ids:
                ids.append(mgr.member.pk)
        if ids:
            return User.objects.filter(pk__in=ids)
        else:
            return User.objects.none()

    def get_consultants(self):
        ids = []
        for cons in OrganisationalUnitMember.objects.filter(
            unit=self,
            roles__in=UnitRoles.CONSULTANT,
            left_date__isnull=True,  # active only
        ):
            if cons.member.pk not in ids:
                ids.append(cons.member.pk)
        if ids:
            return User.objects.filter(pk__in=ids)
        else:
            return User.objects.none()

    def get_activeMembers(self):
        return User.objects.filter(pk__in=self.get_activeMembersPKs())

    def get_activeMembersPKs(self):
        return (
            self.members.filter(
                left_date__isnull=True,
                member__is_active=True,
            )
            .values("member")
            .distinct()
        )

    def get_activeMemberships(self):
        return self.members.filter(
            left_date__isnull=True,
            member__is_active=True,
        ).prefetch_related(
            "member",
            "member__unit_memberships",
            "roles",
            "member__manager",
            "member__timeslots",
            "member__timeslots__phase",
        )

    def get_active_members_with_perm(self, permission_str, include_su=False):
        members = self.get_activeMembers()  # Force evaluation
        if not members:
            return User.objects.none()

        users_with_perms = get_users_with_perms(
            self, with_superusers=include_su, only_with_perms_in=[permission_str]
        )

        if not users_with_perms:
            return User.objects.none()

        return User.objects.filter(pk__in=users_with_perms).distinct()

    def get_allMembers(self):
        ids = []
        return User.objects.filter(
            pk__in=self.members.all().values_list("member__pk", flat=True)
        )
        # for mgr in OrganisationalUnitMember.objects.filter(unit=self):
        #     if mgr.member.pk not in ids:
        #         ids.append(mgr.member.pk)
        # if ids:
        #     return User.objects.filter(pk__in=ids)
        # else:
        #     return User.objects.none()

    def get_absolute_url(self):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
            self.save()
        return reverse("organisationalunit_detail", kwargs={"slug": self.slug})

    def get_avatar_url(self):
        if self.image:
            return self.image.url
        else:
            rand = random.randint(1, 5)
            return static("assets/img/team-{}.jpg".format(rand))

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
        super().save(*args, **kwargs)
        # Resync permissions...
        self.sync_permissions()

    def calculate_bulk_utilization(self, start_date, end_date, user_ids=None):
        """
        Calculate utilization statistics for multiple users efficiently.

        Args:
            start_date: datetime object for the start of the period
            end_date: datetime object for the end of the period
            user_ids: optional list of user IDs to analyze. If None, analyzes all active users

        Returns:
            dict: User ID mapped to their utilization statistics
        """
        # Get users and their countries in one query
        users_query = self.get_activeMembers()
        if user_ids:
            users_query = users_query.filter(id__in=user_ids)

        users = users_query.values("id", "country")

        # Group users by country for efficient holiday lookup
        users_by_country = defaultdict(list)
        for user in users:
            users_by_country[user["country"]].append(user["id"])

        # Get all holidays for relevant countries in one query
        holidays_by_country = defaultdict(set)
        holidays = Holiday.objects.filter(
            country__in=users_by_country.keys(), date__range=(start_date, end_date)
        ).values("country", "date")

        for holiday in holidays:
            country = holiday["country"]
            date = (
                holiday["date"].date()
                if isinstance(holiday["date"], datetime)
                else holiday["date"]
            )
            holidays_by_country[country].add(date)

        # Get all timeslots for all users in one query
        timeslots = (
            TimeSlot.objects.filter(
                user_id__in=[u["id"] for u in users],
                start__date__lte=end_date,
                end__date__gte=start_date,
            )
            .annotate(
                date=TruncDate("start"),
                is_tentative=Case(
                    When(
                        phase__status__lt=PhaseStatuses.SCHEDULED_CONFIRMED,
                        then=Value(1),
                    ),
                    When(
                        phase__status__gte=PhaseStatuses.SCHEDULED_CONFIRMED,
                        then=Value(0),
                    ),
                    When(phase__isnull=True, then=Value(0)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                is_confirmed=Case(
                    When(
                        phase__status__gte=PhaseStatuses.SCHEDULED_CONFIRMED,
                        then=Value(1),
                    ),
                    When(
                        phase__status__lt=PhaseStatuses.SCHEDULED_CONFIRMED,
                        then=Value(0),
                    ),
                    When(phase__isnull=True, then=Value(0)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                is_non_delivery=Case(
                    When(phase__isnull=True, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            )
            .values(
                "user_id",
                "date",
                "is_tentative",
                "is_confirmed",
                "is_non_delivery",
                "start",
                "end",
            )
        )

        # Create date range DataFrame once
        date_range = pd.date_range(start=start_date, end=end_date, freq="D")
        dates_df = pd.DataFrame({"date": date_range})
        dates_df["date"] = dates_df["date"].dt.date
        dates_df["is_working_day"] = dates_df["date"].apply(
            lambda x: 1 if (x.weekday() + 1) in self.businessHours_days else 0
        )

        # Process each user's data
        results = {}

        # Group timeslots by user for efficient processing
        timeslots_by_user = defaultdict(list)
        for slot in timeslots:
            timeslots_by_user[slot["user_id"]].append(slot)

        for user in users:
            user_id = user["id"]
            user_country = user["country"]
            holiday_dates = holidays_by_country[user_country]

            # Create user-specific dates DataFrame with holidays
            user_dates_df = dates_df.copy()
            user_dates_df["is_holiday"] = user_dates_df["date"].apply(
                lambda x: 1 if x in holiday_dates else 0
            )

            # Process user's timeslots
            slots_data = []
            for slot in timeslots_by_user[user_id]:
                current_date = max(slot["start"].date(), start_date)
                end_date_slot = min(slot["end"].date(), end_date)

                while current_date <= end_date_slot:
                    if (
                        (current_date.weekday() + 1) in self.businessHours_days
                        and current_date not in holiday_dates
                    ):
                        slots_data.append(
                            {
                                "date": current_date,
                                "is_tentative": slot["is_tentative"],
                                "is_confirmed": slot["is_confirmed"],
                                "is_non_delivery": slot["is_non_delivery"],
                            }
                        )
                    current_date += timedelta(days=1)

            # Create and process user's slots DataFrame
            if slots_data:
                slots_df = pd.DataFrame(slots_data)
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
                final_df = user_dates_df.merge(
                    daily_stats, on="date", how="left"
                ).fillna(0)
            else:
                final_df = user_dates_df.copy()
                final_df["is_tentative"] = 0
                final_df["is_confirmed"] = 0
                final_df["is_non_delivery"] = 0

            # Calculate user statistics
            total_days = len(date_range)
            holiday_days = len(final_df[final_df["is_holiday"] > 0])
            non_working_days = len(final_df[final_df["is_working_day"] == 0])

            work_days = len(
                final_df[
                    (final_df["is_holiday"] == 0) & (final_df["is_working_day"] == 1)
                ]
            )

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

            results[user_id] = {
                "total_days": total_days,
                "holiday_days": holiday_days,
                "non_working_days": non_working_days,
                "working_days": work_days,
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

        return results

    def get_stats(self, start_date=None, end_date=None, user_ids=None):
        data = {
            "upcoming_availability": {},
        }
        # clean vars
        if not start_date:
            start_date = (timezone.now().date() - timedelta(days=30)).date()
        if not end_date:
            end_date = timezone.now().date().date()

        data["upcoming_availability"] = self.get_upcoming_availability(
            user_ids=user_ids
        )

        return data

    def get_upcoming_availability(self, user_ids=None):
        data = {}
        avail_start = (timezone.now() - timedelta(days=timezone.now().weekday())).date()

        for rang, days_ahead in UpcomingAvailabilityRanges.DEFAULT.items():
            avail = avail_start + timedelta(days=days_ahead)
            data[rang] = self.calculate_bulk_utilization(
                start_date=avail_start, end_date=avail, user_ids=user_ids
            )
            data[rang]["totals"] = {
                "non_delivery_days": 0,
                "scheduled_days": 0,
                "tentative_days": 0,
                "confirmed_days": 0,
                "available_days": 0,
                "working_days": 0,
            }
            for _, m in data[rang].items():
                data[rang]["totals"]["non_delivery_days"] += m["non_delivery_days"]
                data[rang]["totals"]["scheduled_days"] += m["scheduled_days"]
                data[rang]["totals"]["tentative_days"] += m["tentative_days"]
                data[rang]["totals"]["confirmed_days"] += m["confirmed_days"]
                data[rang]["totals"]["available_days"] += m["available_days"]
                data[rang]["totals"]["working_days"] += m["working_days"]

            data[rang]["totals"]["non_delivery_days_percentage"] = round(
                data[rang]["totals"]["non_delivery_days"]
                / data[rang]["totals"]["working_days"]
                * 100,
                1,
            )

            data[rang]["totals"]["scheduled_days_percentage"] = round(
                data[rang]["totals"]["scheduled_days"]
                / data[rang]["totals"]["working_days"]
                * 100,
                1,
            )

            data[rang]["totals"]["tentative_days_percentage"] = round(
                data[rang]["totals"]["tentative_days"]
                / data[rang]["totals"]["working_days"]
                * 100,
                1,
            )

            data[rang]["totals"]["confirmed_days_percentage"] = round(
                data[rang]["totals"]["confirmed_days"]
                / data[rang]["totals"]["working_days"]
                * 100,
                1,
            )

            data[rang]["totals"]["utilisation_percentage"] = round(
                data[rang]["totals"]["confirmed_days"]
                / data[rang]["totals"]["working_days"]
                * 100,
                1,
            )

            data[rang]["totals"]["available_days_percentage"] = round(
                data[rang]["totals"]["available_days"]
                / data[rang]["totals"]["working_days"]
                * 100,
                1,
            )
        return data

    def get_unit_weekly_schedule(
        self, filtered_users=None, start_date=None, end_date=None
    ):
        """
        Generate weekly schedule data for all members of an organizational unit.

        Args:
            self: OrganisationalUnit instance
            start_date: datetime.date (defaults to start of current week)
            end_date: datetime.date (defaults to end of current week)

        Returns:
            dict: Format as specified with users and their daily slots
        """

        # Default to current week if no dates provided
        if start_date is None:
            today = datetime.now().date()
            # Get Monday of current week (assuming week starts on Monday)
            start_date = today - timedelta(days=today.weekday())

        if end_date is None:
            end_date = start_date + timedelta(days=6)  # Sunday of the same week

        # Query for timeslots that overlap with our date range
        # This includes:
        # 1. Slots that start within the range
        # 2. Slots that end within the range
        # 3. Slots that start before and end after the range (span the entire range)
        timeslot_filter = Q(
            # Slot starts within range
            start__date__lte=end_date,
            end__date__gte=start_date,
        )

        # Single query to get all unit members with their timeslots for the date range
        # This is the most efficient approach - only 1 database query
        if filtered_users is not None:
            members = filtered_users.prefetch_related(
                Prefetch(
                    "timeslots",
                    queryset=TimeSlot.objects.filter(timeslot_filter).select_related(
                        "phase", "phase__job"
                    ),
                    to_attr="week_timeslots",
                )
            )
        else:
            members = (
                self.members.filter(member__is_active=True)
                .select_related("member")
                .prefetch_related(
                    Prefetch(
                        "member__timeslots",
                        queryset=TimeSlot.objects.filter(
                            timeslot_filter
                        ).select_related("phase", "phase__job"),
                        to_attr="week_timeslots",
                    )
                )
            )

        # Generate date range for the week
        date_range = []
        current_date = start_date
        while current_date <= end_date:
            date_range.append(current_date.strftime("%d/%m/%Y"))
            current_date += timedelta(days=1)

        # Build the result dictionary
        result = {}

        for member in members:
            user = member.member if hasattr(member, 'member') else member
            user_schedule = {}

            # Initialize all dates as empty
            for date_str in date_range:
                user_schedule[date_str] = ""
                        
            # Fill in the timeslots for each day they overlap
            for slot in user.week_timeslots:
                # Calculate which days this slot spans within our date range
                slot_start_date = max(slot.start.date(), start_date)
                slot_end_date = min(slot.end.date(), end_date)
                
                # Add this slot to every day it spans
                current_slot_date = slot_start_date
                while current_slot_date <= slot_end_date:
                    date_str = current_slot_date.strftime("%d/%m/%Y")
                    if user_schedule[date_str]:
                        user_schedule[date_str].append(slot)
                    else:
                        user_schedule[date_str] = [slot]
                    current_slot_date += timedelta(days=1)

            result[user.pk] = {}
            result[user.pk]["user"] = user
            result[user.pk]["schedule"] = user_schedule

        return result


class OrganisationalUnitRole(models.Model):
    name = models.CharField(verbose_name="Name", max_length=255, unique=True)
    bs_colour = models.CharField(
        verbose_name="Bootstrap Colour", max_length=255, default="info"
    )
    default_role = models.BooleanField("Default Role", default=False)
    manage_role = models.BooleanField("Manager Role", default=False)
    permissions = models.ManyToManyField(Permission)
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        ordering = [
            "name",
        ]

    def sync_default_permissions(self):
        for role in UnitRoles.DEFAULTS:
            if self.pk == role["pk"]:
                self.permissions.clear()
                for perm in UnitRoles.PERMISSIONS[role["pk"]][1]:
                    if perm:
                        codeword = perm
                        if "." in perm:
                            codeword = perm.split(".")[1]
                        if Permission.objects.filter(codename=codeword).exists():
                            permission = Permission.objects.get(codename=codeword)
                            self.permissions.add(permission)
                self.save()
                return True

        # If we reach this; this role isn't matched in code
        return False


class OrganisationalUnitMember(models.Model):
    unit = models.ForeignKey(
        OrganisationalUnit, on_delete=models.CASCADE, related_name="members"
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="unit_memberships",
        on_delete=models.CASCADE,
    )
    inviter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET(get_sentinel_user),
        related_name="unitmember_invites",
        null=True,
        blank=True,
    )
    roles = models.ManyToManyField(
        OrganisationalUnitRole, verbose_name="Roles", blank=True
    )
    add_date = models.DateTimeField(
        verbose_name="Date Added",
        help_text="Date the user was added to the unit",
        auto_now_add=True,
    )
    mod_date = models.DateTimeField(
        verbose_name="Date Modified",
        help_text="Last date the membership was modified",
        auto_now=True,
    )
    left_date = models.DateTimeField(
        verbose_name="Date Left",
        help_text="Date the user left the group",
        null=True,
        blank=True,
    )
    history = HistoricalRecords()

    class Meta:
        ordering = [
            "member",
        ]
        unique_together = [
            "unit",
            "member",
        ]
        get_latest_by = "mod_date"

    def getActiveRoles(self):
        return OrganisationalUnitMember.objects.filter(
            unit=self.unit,
            member=self.member,
            left_date__isnull=True,
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Lets resync the permissions!
        self.unit.sync_permissions()
