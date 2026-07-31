from django.db import models
from django.contrib.auth.models import BaseUserManager
from django.db.models import Q
from datetime import timedelta, datetime
import json
from django.utils import timezone
from collections import defaultdict
from constance import config


class CustomUserQuerySet(models.QuerySet):
    def get_default_order(self):
        return self.order_by("first_name", "last_name")


class CustomUserManager(BaseUserManager):

    def get_queryset(self):
        return CustomUserQuerySet(self.model, using=self._db)

    def get_default_order(self):
        return self.get_queryset().get_default_order()

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Create and save a superuser with the given email and password.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)

    def create_user(self, email, password=None, **extra_fields):
        """
        Create and save a user with the given email and password.
        """
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def calculate_bulk_utilization(
        self, user_queryset, start_date, end_date, org=None, _user_dict=None
    ):
        """
        Calculate utilization statistics for multiple users efficiently.

        Args:
            user_queryset: QuerySet of users to analyze
            start_date: datetime object for the start of the period
            end_date: datetime object for the end of the period
            org: Optional organizational unit for working days

        Returns:
            dict: {
                'summary': aggregate statistics across all users,
                'by_user': detailed breakdown per user
            }
        """
        from chaotica_utils.models import Holiday
        from jobtracker.models import TimeSlot
        from .user import User
        from ..utils import (
            build_period_masks,
            calculate_utilisation,
            aggregate_utilisation,
            classify_delivery_slot,
        )

        # Ensure timezone-aware datetimes
        if not start_date.tzinfo:
            start_date = timezone.make_aware(
                datetime.combine(start_date, datetime.min.time())
            )
        if not end_date.tzinfo:
            end_date = timezone.make_aware(
                datetime.combine(end_date, datetime.max.time())
            )

        user_ids = list(user_queryset.values_list("id", flat=True))

        if _user_dict is None:
            _user_dict = {
                u.id: u
                for u in User.objects.filter(id__in=user_ids)
                .select_related("manager", "acting_manager", "city", "city__country")
                .prefetch_related("unit_memberships__unit")
            }

        user_dict = _user_dict

        # Get working days configuration
        if org:
            working_days = org.businessHours_days
        else:
            working_days = json.loads(config.DEFAULT_WORKING_DAYS)

        # Get unique countries for all users
        user_countries = {u.country for u in user_dict.values()}

        # Fetch ALL holidays in a single query
        holidays = Holiday.objects.filter(
            Q(country__in=user_countries) | Q(country__isnull=True),
            date__range=(start_date.date(), end_date.date()),
        ).values("country", "date")

        # Build holiday lookup by country
        holidays_by_country = defaultdict(set)
        global_holidays = set()

        for holiday in holidays:
            if holiday["country"] is None:
                global_holidays.add(holiday["date"])
            else:
                holidays_by_country[holiday["country"]].add(holiday["date"])

        # Add global holidays to all countries
        for country in user_countries:
            holidays_by_country[country].update(global_holidays)

        total_days = (end_date.date() - start_date.date()).days + 1

        # Fetch ALL timeslots in a SINGLE query, reduced to the flags the
        # central engine needs (slot_type__is_working=False => non-working time).
        timeslots = TimeSlot.objects.filter(
            user_id__in=user_ids,
            start__date__lte=end_date.date(),
            end__date__gte=start_date.date(),
        ).values(
            "user_id",
            "start",
            "end",
            "phase__status",
            "project__state",
            "project__deliverable",
            "slot_type__is_working",
        )

        # Group timeslots by user_id in memory, as engine-ready dicts.
        slots_by_user = defaultdict(list)
        for slot in timeslots:
            slots_by_user[slot["user_id"]].append(
                {
                    "start": slot["start"],
                    "end": slot["end"],
                    **classify_delivery_slot(slot),
                }
            )

        # Period masks depend only on working_days + holidays, which are shared
        # per country — build them once per country and reuse across users.
        masks_by_country = {}

        def _masks_for(country):
            if country not in masks_by_country:
                country_holidays = set(holidays_by_country.get(country, set()))
                country_holidays.update(global_holidays)
                masks_by_country[country] = build_period_masks(
                    start_date, end_date, working_days, country_holidays
                )
            return masks_by_country[country]

        # Process statistics for each user via the central engine.
        user_stats = {}
        for user_id in user_ids:
            user = user_dict.get(user_id)
            if user is None:
                # The id list and the user_dict snapshot are two separate reads,
                # so they can drift if a user is deactivated/removed (e.g. by a
                # concurrent import) in between. Skip anyone missing from the
                # snapshot rather than 500-ing the whole batch.
                continue
            masks = _masks_for(user.country)

            user_data = calculate_utilisation(
                slots_by_user.get(user_id, []),
                start_date,
                end_date,
                working_days,
                None,  # holidays already baked into the shared masks
                masks=masks,
            )
            user_data.update(
                {
                    "user_id": user.id,
                    "user": user,
                    "user_email": user.email,
                    "user_name": str(user),
                    "main_org": (
                        membership.unit
                        if (membership := user.unit_memberships.first())
                        else None
                    ),
                }
            )
            user_stats[user.id] = user_data

        summary = aggregate_utilisation(user_stats.values())
        summary["total_days"] = total_days

        return {
            "summary": summary,
            "by_user": user_stats,
            "date_range": {"start": start_date, "end": end_date},
        }

    def get_bulk_stats(self, user_queryset, start_date=None, end_date=None, org=None):
        """
        Get comprehensive stats for multiple users efficiently.

        Args:
            user_queryset: QuerySet of users
            start_date: Start date for analysis (defaults to 30 days ago)
            end_date: End date for analysis (defaults to today)
            org: Optional organizational unit

        Returns:
            dict: Statistics including utilization and upcoming availability
        """
        from datetime import timedelta
        from django.utils import timezone
        from ..enums import UpcomingAvailabilityRanges

        # Set default dates if not provided
        if not start_date:
            start_date = timezone.now() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now()

        # Ensure correct date ordering
        if start_date > end_date:
            start_date, end_date = end_date, start_date

        # Make timezone-aware
        if isinstance(start_date, datetime):
            if not start_date.tzinfo:
                start_date = timezone.make_aware(start_date)
        else:
            start_date = timezone.make_aware(
                datetime.combine(start_date, datetime.min.time())
            )

        if isinstance(end_date, datetime):
            if not end_date.tzinfo:
                end_date = timezone.make_aware(end_date)
        else:
            end_date = timezone.make_aware(
                datetime.combine(end_date, datetime.max.time())
            )

        # Build the user dict once and reuse across all calculate_bulk_utilization calls
        from .user import User

        user_ids = list(user_queryset.values_list("id", flat=True))
        shared_user_dict = {
            u.id: u
            for u in User.objects.filter(id__in=user_ids)
            .select_related("manager", "acting_manager", "city", "city__country")
            .prefetch_related("unit_memberships__unit")
        }

        current_utilization = self.calculate_bulk_utilization(
            user_queryset, start_date, end_date, org, _user_dict=shared_user_dict
        )

        upcoming_availability = {}
        avail_start = timezone.now() - timedelta(days=timezone.now().weekday())

        max_days_ahead = max(UpcomingAvailabilityRanges.DEFAULT.values())
        max_end_date = avail_start + timedelta(days=max_days_ahead)

        all_range_data = self.calculate_bulk_utilization(
            user_queryset, avail_start, max_end_date, org, _user_dict=shared_user_dict
        )

        for range_name, days_ahead in UpcomingAvailabilityRanges.DEFAULT.items():
            avail_end = avail_start + timedelta(days=days_ahead)
            upcoming_availability[range_name] = self.calculate_bulk_utilization(
                user_queryset, avail_start, avail_end, org, _user_dict=shared_user_dict
            )

        return {
            "current": current_utilization,
            "upcoming_availability": upcoming_availability,
            "org": org,
            "user_count": len(current_utilization["by_user"]),
        }

    def get_team_availability_summary(self, user_queryset, weeks_ahead=8):
        """
        Get a week-by-week availability summary for a team.

        Args:
            user_queryset: QuerySet of users
            weeks_ahead: Number of weeks to look ahead

        Returns:
            list: Weekly availability data
        """
        from django.utils import timezone

        weekly_data = []
        start_date = timezone.now().date()
        start_date = start_date - timedelta(days=start_date.weekday())  # Start of week

        # Calculate all weeks in one batch if possible
        end_date = start_date + timedelta(weeks=weeks_ahead)

        # Get all data for the entire period
        full_period_stats = self.calculate_bulk_utilization(
            user_queryset, start_date, end_date
        )

        # Break down by week (this is simplified - you might want to recalculate per week)
        for week in range(weeks_ahead):
            week_start = start_date + timedelta(weeks=week)
            week_end = week_start + timedelta(days=6)

            week_stats = self.calculate_bulk_utilization(
                user_queryset, week_start, week_end
            )

            weekly_data.append(
                {
                    "week_start": week_start,
                    "week_end": week_end,
                    "week_number": week_start.isocalendar()[1],
                    "year": week_start.year,
                    "summary": week_stats["summary"],
                }
            )

        return weekly_data

    def prefetch_for_stats(self, queryset):
        """
        Helper method to prefetch all necessary related data for stats calculation.
        Returns an optimized queryset.
        """
        # Clear any existing prefetch configurations to avoid conflicts
        # by using only() to create a fresh queryset
        return (
            queryset.only(
                "id",
                "email",
                "first_name",
                "last_name",
                "country",
                "is_active",
                "manager_id",
                "acting_manager_id",
            )
            .select_related("manager", "acting_manager")
            .prefetch_related("unit_memberships__unit")
        )
