from django.db import models
from chaotica_utils.enums import UpcomingAvailabilityRanges
from chaotica_utils.models import Holiday, User
from ..enums import PhaseStatuses
from django.conf import settings
from django.templatetags.static import static
from chaotica_utils.utils import unique_slug_generator
from django.utils import timezone
from django.urls import reverse
from simple_history.models import HistoricalRecords
from django.db.models import JSONField
from django.db.models.functions import Lower
from django.db.models import Q
import uuid, os, json
from datetime import timedelta, datetime
from django.db.models.signals import m2m_changed
from constance import config
from django.dispatch import receiver
from django_bleach.models import BleachField
from guardian.shortcuts import assign_perm, remove_perm, get_users_with_perms
from django_bleach.models import BleachField
from django.db.models.functions import Lower
import pandas as pd
from collections import defaultdict
from django.db.models import Q, Case, When, Value, IntegerField
from django.db.models.functions import TruncDate


def get_media_image_file_path(_, filename):
    ext = filename.split(".")[-1]
    filename = "%s.%s" % (uuid.uuid4(), ext)
    return os.path.join("images", filename)


class Team(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(null=False, default="", unique=True)
    description = BleachField(blank=True, null=True, default="")
    profile_image = models.ImageField(
        blank=True,
        upload_to=get_media_image_file_path,
    )
    cover_image = models.ImageField(
        blank=True,
        upload_to=get_media_image_file_path,
    )
    is_hidden = models.BooleanField(
        verbose_name="Hidden",
        help_text="Team is only visible to admins, owners and members",
        default=False,
    )
    owners = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        limit_choices_to={"is_active": True},
        help_text="Users responsible for the management of the team.",
    )
    history = HistoricalRecords()
    data = JSONField(verbose_name="Data", null=True, blank=True, default=dict)

    class Meta:
        ordering = [Lower("name")]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
        super(Team, self).save(*args, **kwargs)
    
    def get_activeMembers(self):
        return User.objects.filter(pk__in=self.get_activeMembersPKs())

    def get_activeMembersPKs(self):
        return (
            self.active_memberships()
            .values("user")
            .distinct()
        )

    def active_memberships(self):
        now = timezone.now()
        return self.users.filter(
            Q(left_at__isnull=True) | Q(left_at__gte=now), joined_at__lte=now
        )

    def get_absolute_url(self):
        return reverse(
            "team_detail",
            kwargs={"slug": self.slug},
        )

    def get_avatar_url(self):
        if self.profile_image:
            return self.profile_image.url
        else:
            return static("assets/img/team/avatar-rounded.webp")

    def get_cover_url(self):
        if self.cover_image:
            return self.cover_image.url
        else:
            return static("assets/img/bg/bg-11.png")

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
        from ..models import TimeSlot
        
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
        WORKING_DAYS = json.loads(config.DEFAULT_WORKING_DAYS)
        # Create date range DataFrame once
        date_range = pd.date_range(start=start_date, end=end_date, freq="D")
        dates_df = pd.DataFrame({"date": date_range})
        dates_df["date"] = dates_df["date"].dt.date
        # dates_df["is_working_day"] = dates_df["date"].apply(
        #     lambda x: 1 if (x.weekday() + 1) in self.businessHours_days else 0
        # )
        dates_df["is_working_day"] = dates_df["date"].apply(
            lambda x: 1 if (x.weekday() + 1) in WORKING_DAYS else 0
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
                        # (current_date.weekday() + 1) in self.businessHours_days and
                        (current_date.weekday() + 1) in WORKING_DAYS and
                        current_date not in holiday_dates
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
            ) if data[rang]["totals"]["working_days"] != 0 else 0

            data[rang]["totals"]["scheduled_days_percentage"] = round(
                data[rang]["totals"]["scheduled_days"]
                / data[rang]["totals"]["working_days"]
                * 100,
                1,
            ) if data[rang]["totals"]["working_days"] != 0 else 0

            data[rang]["totals"]["tentative_days_percentage"] = round(
                data[rang]["totals"]["tentative_days"]
                / data[rang]["totals"]["working_days"]
                * 100,
                1,
            ) if data[rang]["totals"]["working_days"] != 0 else 0

            data[rang]["totals"]["confirmed_days_percentage"] = round(
                data[rang]["totals"]["confirmed_days"]
                / data[rang]["totals"]["working_days"]
                * 100,
                1,
            ) if data[rang]["totals"]["working_days"] != 0 else 0

            data[rang]["totals"]["utilisation_percentage"] = round(
                data[rang]["totals"]["confirmed_days"]
                / data[rang]["totals"]["working_days"]
                * 100,
                1,
            ) if data[rang]["totals"]["working_days"] != 0 else 0

            data[rang]["totals"]["available_days_percentage"] = round(
                data[rang]["totals"]["available_days"]
                / data[rang]["totals"]["working_days"]
                * 100,
                1,
            ) if data[rang]["totals"]["working_days"] != 0 else 0
        return data


# method for updating
@receiver(m2m_changed, sender=Team.owners.through, dispatch_uid="update_owner_perms")
def update_owner_perms(sender, instance, **kwargs):
    if instance:
        for user in instance.owners.all():
            assign_perm("change_team", user, instance)
            assign_perm("delete_team", user, instance)
        all_perms = get_users_with_perms(instance, attach_perms=True)
        for user, perms in all_perms.items():
            if user not in instance.owners.all():
                for perm in perms:
                    remove_perm(perm, user, instance)


class TeamMember(models.Model):
    team = models.ForeignKey(Team, related_name="users", on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teams",
    )
    history = HistoricalRecords()

    last_updated_on = models.DateTimeField(auto_now=True)
    joined_at = models.DateField(
        "Joined",
        null=True,
        blank=True,
        help_text="Date this user joined the group",
    )
    left_at = models.DateField(
        "Left",
        null=True,
        blank=True,
        help_text="Date this user left the group",
    )

    class Meta:
        ordering = [
            "team",
            "user",
        ]

    def is_active(self):
        now = timezone.now().date()
        if (not self.left_at and self.joined_at <= now) or (
            self.joined_at <= now and self.left_at > now
        ):
            return True
        else:
            return False

    def __str__(self):
        return "%s - %s" % (
            self.user,
            self.team,
        )
