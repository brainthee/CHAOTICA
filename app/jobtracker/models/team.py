from django.db import models
from chaotica_utils.enums import UpcomingAvailabilityRanges
from chaotica_utils.models import Holiday, User
from ..enums import PhaseStatuses
from django.conf import settings
from django.templatetags.static import static
from chaotica_utils.utils import (
    unique_slug_generator,
    build_period_masks,
    calculate_utilisation,
    classify_delivery_slot,
)
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
from collections import defaultdict


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
        return self.active_memberships().values("user").distinct()

    def active_memberships(self):
        now = timezone.now()
        return self.users.filter(
            Q(left_at__isnull=True) | Q(left_at__gte=now),
            joined_at__lte=now,
            user__is_active=True,
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

        # Get all holidays for relevant countries in one query, including any
        # global (country=NULL) holidays that apply to everyone.
        holidays_by_country = defaultdict(set)
        global_holidays = set()
        holidays = Holiday.objects.filter(
            Q(country__in=users_by_country.keys()) | Q(country__isnull=True),
            date__range=(start_date, end_date),
        ).values("country", "date")

        for holiday in holidays:
            country = holiday["country"]
            date = (
                holiday["date"].date()
                if isinstance(holiday["date"], datetime)
                else holiday["date"]
            )
            if country is None:
                global_holidays.add(date)
            else:
                holidays_by_country[country].add(date)

        # Get all timeslots for all users in one query, reduced to the flags the
        # central engine needs (slot_type__is_working=False => non-working time).
        timeslots = TimeSlot.objects.filter(
            user_id__in=[u["id"] for u in users],
            start__date__lte=end_date,
            end__date__gte=start_date,
        ).values(
            "user_id",
            "start",
            "end",
            "phase__status",
            "project__state",
            "project__deliverable",
            "slot_type__is_working",
        )

        # A Team is not an OrganisationalUnit and has no business-hours config,
        # so utilisation uses the global default working days.
        working_days = json.loads(config.DEFAULT_WORKING_DAYS)

        # Group timeslots by user as engine-ready dicts.
        timeslots_by_user = defaultdict(list)
        for slot in timeslots:
            flags = classify_delivery_slot(slot)
            timeslots_by_user[slot["user_id"]].append(
                {
                    "start": slot["start"],
                    "end": slot["end"],
                    **flags,
                }
            )

        # Period masks depend only on working days + holidays, shared per
        # country — build once per country and reuse across users.
        masks_by_country = {}

        def _masks_for(country):
            if country not in masks_by_country:
                country_holidays = set(holidays_by_country.get(country, set()))
                country_holidays.update(global_holidays)
                masks_by_country[country] = build_period_masks(
                    start_date, end_date, working_days, country_holidays
                )
            return masks_by_country[country]

        results = {}
        for user in users:
            user_id = user["id"]
            results[user_id] = calculate_utilisation(
                timeslots_by_user.get(user_id, []),
                start_date,
                end_date,
                working_days,
                None,  # holidays already baked into the shared masks
                masks=_masks_for(user["country"]),
            )

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
            totals = {
                "non_delivery_days": 0,
                "scheduled_days": 0,
                "tentative_days": 0,
                "confirmed_days": 0,
                "available_days": 0,
                "working_days": 0,
                "effective_working_days": 0,
            }
            for uid, m in data[rang].items():
                if uid == "totals":
                    continue
                totals["non_delivery_days"] += m["non_delivery_days"]
                totals["scheduled_days"] += m["scheduled_days"]
                totals["tentative_days"] += m["tentative_days"]
                totals["confirmed_days"] += m["confirmed_days"]
                totals["available_days"] += m["available_days"]
                totals["working_days"] += m["working_days"]
                totals["effective_working_days"] += m["effective_working_days"]
            data[rang]["totals"] = totals

            working = totals["working_days"]
            effective = totals["effective_working_days"]

            def _pct(value, denom):
                return round(value / denom * 100, 1) if denom else 0

            # non-delivery includes non-working (leave) days, so it keeps the
            # nominal working-days denominator.
            totals["non_delivery_days_percentage"] = _pct(
                totals["non_delivery_days"], working
            )
            # Everything within the effective working days uses that denominator,
            # matching the central utilisation formula.
            totals["scheduled_days_percentage"] = _pct(
                totals["scheduled_days"], effective
            )
            totals["tentative_days_percentage"] = _pct(
                totals["tentative_days"], effective
            )
            totals["confirmed_days_percentage"] = _pct(
                totals["confirmed_days"], effective
            )
            totals["utilisation_percentage"] = _pct(totals["confirmed_days"], effective)
            totals["available_days_percentage"] = _pct(
                totals["available_days"], effective
            )
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
