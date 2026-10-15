from django.db import models
from chaotica_utils.enums import UpcomingAvailabilityRanges
from chaotica_utils.models import Holiday, User
from ..enums import PhaseStatuses, JobStatuses
from django.db.models import Count
from django.db.models.functions import TruncMonth
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

# Services shown individually on the team Stats radar; the rest become "Other".
SERVICE_BREAKDOWN_TOP_N = 8


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

    def calculate_bulk_utilization(
        self, start_date, end_date, user_ids=None, include_former=False
    ):
        """
        Calculate utilization statistics for multiple users efficiently.

        Args:
            start_date: datetime object for the start of the period
            end_date: datetime object for the end of the period
            user_ids: optional list of user IDs to analyze. If None, analyzes all active users
            include_former: also allow users who have left the team or been
                disabled (historical stats ranges)

        Returns:
            dict: User ID mapped to their utilization statistics
        """
        from ..models import TimeSlot

        # Get users and their countries in one query
        if include_former:
            users_query = User.objects.filter(pk__in=self.users.values("user"))
        else:
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

    def memberships_in_range(self, start_date, end_date):
        """Memberships overlapping ``start_date``..``end_date`` (inclusive),
        including people who have since left or been disabled. A blank
        ``joined_at`` / ``left_at`` is treated as open-ended."""
        return self.users.filter(
            Q(joined_at__isnull=True) | Q(joined_at__lte=end_date),
            Q(left_at__isnull=True) | Q(left_at__gte=start_date),
        ).select_related("user")

    def get_stats(self, start_date=None, end_date=None, user_ids=None):
        """Assemble the data used to render the team stats tab.

        Mirrors :meth:`OrganisationalUnit.get_stats`, but a Team has no
        job-ownership FK (there is no ``Job -> Team`` relation), so every
        aggregate is scoped through the team members' scheduled ``TimeSlot``s.

        Membership is date-aware: anyone whose membership overlaps the range
        is included (even if they have since left), but only time booked while
        they were a member counts. Each member therefore has a *window*
        (membership clipped to the range) and every slot-based aggregate is
        filtered to slots inside a member's window. Because a phase/job has
        many timeslots across members, counts use ``distinct=True``.

        ``upcoming_availability`` is forward-looking and always uses the
        current members, independent of the range.
        """
        from ..models import Phase, Job

        # clean vars
        if not start_date:
            start_date = (timezone.now() - timedelta(days=91)).date()
        if not end_date:
            end_date = timezone.now().date()
        if isinstance(start_date, datetime):
            start_date = start_date.date()
        if isinstance(end_date, datetime):
            end_date = end_date.date()
        if start_date > end_date:
            start_date, end_date = end_date, start_date

        memberships = self.memberships_in_range(start_date, end_date)
        if user_ids:
            memberships = memberships.filter(user_id__in=user_ids)

        # Per-user windows: membership clipped to the range. A user can hold
        # several (non-overlapping) memberships if they left and rejoined.
        windows = defaultdict(list)
        full_windows = defaultdict(list)  # unclipped, for delivery credit
        users = {}
        for ms in memberships:
            joined = ms.joined_at or start_date
            left = ms.left_at or end_date
            windows[ms.user_id].append((max(start_date, joined), min(end_date, left)))
            full_windows[ms.user_id].append((ms.joined_at, ms.left_at))
            users[ms.user_id] = ms.user

        def _slot_q(prefix, window_map):
            q = Q(pk__in=[])
            for uid, spans in window_map.items():
                for ws, we in spans:
                    cond = Q(**{f"{prefix}user_id": uid})
                    if we:
                        cond &= Q(**{f"{prefix}start__date__lte": we})
                    if ws:
                        cond &= Q(**{f"{prefix}end__date__gte": ws})
                    q |= cond
            return q

        # Slots booked inside a member's window within the range.
        phase_in_range = _slot_q("timeslots__", windows)
        job_in_range = _slot_q("phases__timeslots__", windows)
        # Slots booked at any point during their membership (a phase delivered
        # in range was usually tested before it).
        phase_while_member = _slot_q("timeslots__", full_windows)

        data = {
            "start_date": start_date,
            "end_date": end_date,
            "upcoming_availability": self.get_upcoming_availability(user_ids=user_ids),
            "summary": {},
            "member_utilisation": [],
            "delivery_throughput": {},
            "service_breakdown": [],
            "service_breakdown_max": 0,
            "job_status_breakdown": [],
        }

        # --- Member utilisation: one bulk call per distinct window ---
        uids_by_window = defaultdict(list)
        for uid, spans in windows.items():
            for span in spans:
                uids_by_window[span].append(uid)
        util = defaultdict(lambda: defaultdict(int))
        for (ws, we), uids in uids_by_window.items():
            for uid, m in self.calculate_bulk_utilization(
                ws, we, user_ids=uids, include_former=True
            ).items():
                for key, value in m.items():
                    if key.endswith("_days") and isinstance(value, int):
                        util[uid][key] += value

        team_confirmed = team_effective = 0
        for uid, user in users.items():
            m = util.get(uid, {})
            effective = m.get("effective_working_days", 0)
            confirmed = m.get("confirmed_days", 0)
            scheduled = m.get("scheduled_days", 0)
            team_confirmed += confirmed
            team_effective += effective
            spans = sorted(windows[uid])
            data["member_utilisation"].append(
                {
                    "user_id": uid,
                    "user": user,
                    "name": user.get_full_name() or str(user),
                    "confirmed_days": confirmed,
                    "scheduled_days": scheduled,
                    "available_days": m.get("available_days", 0),
                    "working_days": m.get("working_days", 0),
                    "effective_working_days": effective,
                    "confirmed_pct": (
                        round(confirmed / effective * 100, 1) if effective else 0
                    ),
                    "scheduled_pct": (
                        round(scheduled / effective * 100, 1) if effective else 0
                    ),
                    # Only a member for part of the range?
                    "window_start": spans[0][0],
                    "window_end": spans[-1][1],
                    "joined_in_range": spans[0][0] > start_date,
                    "left_in_range": spans[-1][1] < end_date,
                }
            )
        data["member_utilisation"].sort(key=lambda r: r["confirmed_pct"], reverse=True)

        # --- Service participation breakdown (phases worked in range) ---
        service_rows = (
            Phase.objects.filter(phase_in_range, service__isnull=False)
            .exclude(status__in=PhaseStatuses.IGNORED_STATUSES)
            .values("service__name")
            .annotate(participation_count=Count("id", distinct=True))
            .order_by("-participation_count")
        )
        breakdown = [
            {
                "name": row["service__name"],
                "participation_count": row["participation_count"],
            }
            for row in service_rows
        ]
        # Keep the radar readable: busiest services, long tail rolled up.
        if len(breakdown) > SERVICE_BREAKDOWN_TOP_N:
            tail = breakdown[SERVICE_BREAKDOWN_TOP_N:]
            breakdown = breakdown[:SERVICE_BREAKDOWN_TOP_N] + [
                {
                    "name": f"Other ({len(tail)} services)",
                    "participation_count": sum(r["participation_count"] for r in tail),
                }
            ]
        data["service_breakdown"] = breakdown
        data["service_breakdown_max"] = max(
            (r["participation_count"] for r in breakdown), default=0
        )

        # --- Job pipeline: jobs worked in range, by current status ---
        status_labels = dict(JobStatuses.CHOICES)
        status_colours = dict(JobStatuses.BS_COLOURS)
        job_rows = (
            Job.objects.filter(job_in_range)
            .values("status")
            .annotate(count=Count("pk", distinct=True))
        )
        counts_by_status = {row["status"]: row["count"] for row in job_rows}
        data["job_status_breakdown"] = [
            {
                "status": status,
                "label": status_labels.get(status, str(status)),
                "count": counts_by_status.get(status, 0),
                "bs_colour": status_colours.get(status, "secondary"),
            }
            for status in JobStatuses.ALL()
            if counts_by_status.get(status, 0) > 0
        ]

        # --- Delivery throughput: phases delivered per month in range ---
        delivered = Phase.objects.filter(
            phase_while_member,
            status=PhaseStatuses.DELIVERED,
            actual_delivery_date__date__range=(start_date, end_date),
        )
        per_month = {
            (
                row["month"].date()
                if isinstance(row["month"], datetime)
                else row["month"]
            ): row["count"]
            for row in delivered.annotate(month=TruncMonth("actual_delivery_date"))
            .values("month")
            .annotate(count=Count("id", distinct=True))
            if row["month"]
        }
        labels, counts = [], []
        month = start_date.replace(day=1)
        while month <= end_date:
            labels.append(month.strftime("%b %Y"))
            counts.append(per_month.get(month, 0))
            month = (month + timedelta(days=32)).replace(day=1)
        data["delivery_throughput"] = {
            "labels": labels if any(counts) else [],
            "counts": counts if any(counts) else [],
        }

        # --- Summary tiles ---
        data["summary"] = {
            "members": len(users),
            "jobs_worked": Job.objects.filter(job_in_range).distinct().count(),
            "phases_delivered": delivered.distinct().count(),
            "utilisation": (
                round(team_confirmed / team_effective * 100, 1) if team_effective else 0
            ),
        }

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
                "tentative_exclusive_days": 0,
                "internal_exclusive_days": 0,
                "non_working_slot_days": 0,
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
                totals["tentative_exclusive_days"] += m["tentative_exclusive_days"]
                totals["internal_exclusive_days"] += m["internal_exclusive_days"]
                totals["non_working_slot_days"] += m["non_working_slot_days"]
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
            # Stacked-chart split: confirmed / tentative / internal / available
            # are mutually exclusive over the effective days, so they sum to
            # 100% (leave is already outside the effective days).
            totals["tentative_exclusive_days_percentage"] = _pct(
                totals["tentative_exclusive_days"], effective
            )
            totals["internal_exclusive_days_percentage"] = _pct(
                totals["internal_exclusive_days"], effective
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
