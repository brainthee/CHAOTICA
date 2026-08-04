from django.db import models
from django.db.models import F, Q, Count, Prefetch
from django.db.models.functions import ExtractDay, TruncMonth
from django.conf import settings
from chaotica_utils.utils import (
    unique_slug_generator,
    build_period_masks,
    calculate_utilisation,
    classify_delivery_slot,
)
from django.urls import reverse
from simple_history.models import HistoricalRecords
from guardian.shortcuts import (
    assign_perm,
    remove_perm,
    get_user_perms,
    get_users_with_perms,
)
from django.db.models import JSONField
import pytz
import uuid, os, random
from chaotica_utils.models import User, get_sentinel_user, Holiday
from ..models import TimeSlot
from chaotica_utils.enums import UnitRoles, UpcomingAvailabilityRanges
from ..enums import PhaseStatuses, JobStatuses
from django.utils import timezone
from datetime import timedelta, date, datetime
from decimal import Decimal
from django.templatetags.static import static
from django_bleach.models import BleachField
from django.db.models.functions import Lower
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.contrib.auth.models import Permission
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
    businessHours_timezone = models.CharField(
        verbose_name="Business Hours Timezone",
        max_length=63,
        choices=[(tz, tz) for tz in pytz.common_timezones],
        default="Europe/London",
        help_text="Timezone that business hours are defined in (e.g., Europe/London, Europe/Berlin)",
    )
    approval_required = models.BooleanField(
        "Approval Required",
        default=True,
        help_text="Approval by a Manager is required to join the unit",
    )
    special_requirements = BleachField(blank=True, null=True)
    history = HistoricalRecords()
    leads = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="units_lead",
        blank=True,
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
            ("can_manage_framework_job", "Can assign a framework to jobs"),
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
            ("can_deliver_jobs", "Can Deliver jobs"),
            ("can_conduct_review", "Can conduct reviews"),
            ("can_view_all_reviews", "Can view all reviews"),
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

    def sync_permissions(self, users=None):
        """Reconcile guardian object permissions from each member's roles.

        ``users`` optionally limits the work to specific members (``User``
        instances or pks); by default every member is reconciled. A membership
        change (``OrganisationalUnitMember.save``) passes just that one member
        so the common path stays O(1) instead of re-reconciling the whole unit
        on every save - which previously made bulk imports O(n^2).

        Reads are batched (one query for expected perms, one for existing) so a
        full sync is a handful of queries regardless of member count.
        """
        # Target member pks. ``self.members.all()`` (not filtered on left_date)
        # matches the old behaviour so members who have left still get their
        # stale permissions cleared.
        if users is None:
            target_ids = set(self.members.all().values_list("member__pk", flat=True))
        else:
            target_ids = {getattr(u, "pk", u) for u in users}
        if not target_ids:
            return

        # Expected perms per member, in a single query: only active memberships
        # contribute roles, so a left member ends up with an empty set.
        expected = defaultdict(set)
        for member_id, codename in OrganisationalUnitMember.objects.filter(
            unit=self, member_id__in=target_ids, left_date__isnull=True
        ).values_list("member_id", "roles__permissions__codename"):
            if codename:
                expected[member_id].add(codename)

        users_by_id = User.objects.in_bulk(target_ids)

        # Existing object perms. For a full sync, read everyone in one batched
        # query; for a targeted sync (a single member's save) read just those
        # users so the common path doesn't scan the whole unit (which would
        # reintroduce the O(n^2) behaviour this method is here to avoid).
        existing = defaultdict(set)
        if users is None:
            for user, perms in get_users_with_perms(
                self,
                attach_perms=True,
                with_superusers=False,
                with_group_users=False,
            ).items():
                if user.pk in target_ids:
                    existing[user.pk] = set(perms)
        else:
            for uid, user in users_by_id.items():
                existing[uid] = set(
                    get_user_perms(user, self).values_list("codename", flat=True)
                )
        # Group the changes by permission so we can assign/remove in bulk:
        # guardian's assign_perm/remove_perm accept a queryset of users, which
        # is one query per permission instead of one per (user, permission).
        to_assign = defaultdict(list)
        to_remove = defaultdict(list)
        for member_id in target_ids:
            if member_id not in users_by_id:
                continue
            want = expected.get(member_id, set())
            have = existing.get(member_id, set())
            for codename in want - have:
                to_assign[codename].append(member_id)
            for codename in have - want:
                to_remove[codename].append(member_id)

        # assign_perm accepts a queryset of users (bulk); remove_perm does not,
        # but removals only happen on role changes / leavers, not on import.
        for codename, uids in to_assign.items():
            assign_perm(codename, User.objects.filter(pk__in=uids), self)
        for codename, uids in to_remove.items():
            for user in User.objects.filter(pk__in=uids):
                remove_perm(codename, user, self)

    def ensure_lead_memberships(self):
        """Ensure every lead holds the management role on this unit.

        Being a lead should confer manager rights however the lead was assigned
        (unit creation, the edit form, the setup wizard, admin, shell, ...).
        Previously only ``OrganisationalUnitCreateView`` did this, so a lead
        added after creation had no ``manage_members`` permission and hit a 403
        when trying to add/import members. Idempotent - safe to call repeatedly.
        """
        management_role = OrganisationalUnitRole.objects.filter(
            manage_role=True
        ).first()
        if management_role is None:
            return
        for lead_user in self.leads.all():
            membership, _ = OrganisationalUnitMember.objects.get_or_create(
                unit=self, member=lead_user
            )
            membership.roles.add(management_role)
        # roles.add() doesn't trigger the member save() resync, so do it once here.
        self.sync_permissions()

    def __str__(self):
        return self.name

    def get_managers(self):
        # Members hold a ``roles`` m2m to OrganisationalUnitRole; a management
        # role is flagged via ``manage_role=True`` (same signal used by
        # ensure_lead_memberships / sync_default_permissions). The old code
        # filtered a non-existent ``role`` field against the UnitRoles enum,
        # which raised FieldError.
        return User.objects.filter(
            pk__in=OrganisationalUnitMember.objects.filter(
                unit=self,
                roles__manage_role=True,
                member__is_active=True,
            ).values("member")
        ).distinct()

    def get_consultants(self):
        ids = []
        for cons in OrganisationalUnitMember.objects.filter(
            unit=self,
            roles__in=UnitRoles.CONSULTANT,
            left_date__isnull=True,  # active only
            member__is_active=True,
        ):
            if cons.member.pk not in ids:
                ids.append(cons.member.pk)
        if ids:
            return User.objects.filter(pk__in=ids)
        else:
            return User.objects.none()

    def get_consultant_ids(self):
        """Active member user IDs holding the Consultant role.

        Utilisation aggregates are scoped to consultants because they are the
        only members who get booked onto delivery — including managers, sales,
        etc. would skew the percentage down. Matched by role NAME rather than pk
        so it survives role pk drift (see ``sync_default_permissions``).
        """
        return list(
            self.members.filter(
                left_date__isnull=True,
                member__is_active=True,
                roles__name__iexact="Consultant",
            )
            .values_list("member_id", flat=True)
            .distinct()
        )

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

    def get_activeMemberships(self, include_disabled=False):
        from chaotica_utils.models.job_levels import UserJobLevel

        members = self.members.filter(left_date__isnull=True)
        if not include_disabled:
            members = members.filter(member__is_active=True)
        return members.select_related(
            "member__city",
            "member__city__country",
            "member__manager",
        ).prefetch_related(
            Prefetch(
                "member__unit_memberships",
                queryset=OrganisationalUnitMember.objects.select_related("unit"),
            ),
            "roles",
            Prefetch(
                "member__job_level_history",
                queryset=UserJobLevel.objects.filter(is_current=True).select_related(
                    "job_level"
                ),
                to_attr="_current_levels",
            ),
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

        # Intersect the permission holders with the unit's active members so
        # deactivated users (or ex-members who still hold the guardian perm)
        # never surface in assignment dropdowns.
        return (
            User.objects.filter(pk__in=users_with_perms, is_active=True)
            .filter(pk__in=self.get_activeMembersPKs())
            .distinct()
            .get_default_order()
        )

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

        # Group timeslots by user as engine-ready dicts.
        timeslots_by_user = defaultdict(list)
        for slot in timeslots:
            timeslots_by_user[slot["user_id"]].append(
                {
                    "start": slot["start"],
                    "end": slot["end"],
                    **classify_delivery_slot(slot),
                }
            )

        # Period masks depend only on the unit's working days + holidays, which
        # are shared per country — build them once per country and reuse.
        working_days = self.businessHours_days
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

    def get_stats(
        self, start_date=None, end_date=None, user_ids=None, include_financials=False
    ):
        """Assemble the data used to render the unit stats tab.

        Returns a single dict so the offcanvas "Raw Data" view can serialise it
        directly. All heavy work (pandas utilisation, phase/job aggregates) is
        performed with bulk queries — no per-member loops that hit the DB.
        """
        from ..models import Phase

        # clean vars
        if not start_date:
            start_date = (timezone.now() - timedelta(days=30)).date()
        if not end_date:
            end_date = timezone.now().date()
        # Guard against strings coming from GET params
        if isinstance(start_date, datetime):
            start_date = start_date.date()
        if isinstance(end_date, datetime):
            end_date = end_date.date()

        # Utilisation is scoped to consultants — the only members who get booked
        # onto delivery, so including anyone else drags the percentages down.
        memberships = list(self.get_activeMemberships())
        consultant_ids = user_ids if user_ids is not None else self.get_consultant_ids()
        consultant_set = set(consultant_ids)

        data = {
            "upcoming_availability": self.get_upcoming_availability(
                user_ids=consultant_ids
            ),
            "summary": {},
            "member_utilisation": [],
            "delivery_throughput": {},
            "service_breakdown": [],
            "job_status_breakdown": [],
        }

        # --- Member utilisation over the selected range (single bulk call) ---
        util = (
            self.calculate_bulk_utilization(
                start_date, end_date, user_ids=consultant_ids
            )
            if consultant_ids
            else {}
        )
        total_confirmed = 0
        total_working = 0
        for ms in memberships:
            if ms.member_id not in consultant_set:
                continue
            m = util.get(ms.member_id, {})
            working = m.get("working_days", 0)
            # Effective working days (nominal working days minus leave/sick) is
            # the utilisation denominator; fall back to working days if absent.
            effective = m.get("effective_working_days", working)
            confirmed = m.get("confirmed_days", 0)
            scheduled = m.get("scheduled_days", 0)
            total_confirmed += confirmed
            total_working += effective
            data["member_utilisation"].append(
                {
                    "user_id": ms.member_id,
                    "name": ms.member.get_full_name() or str(ms.member),
                    "confirmed_days": confirmed,
                    "scheduled_days": scheduled,
                    "available_days": m.get("available_days", 0),
                    "working_days": working,
                    "effective_working_days": effective,
                    "confirmed_pct": (
                        round(confirmed / effective * 100, 1) if effective else 0
                    ),
                    "scheduled_pct": (
                        round(scheduled / effective * 100, 1) if effective else 0
                    ),
                }
            )
        data["member_utilisation"].sort(key=lambda r: r["confirmed_pct"], reverse=True)

        # --- Service participation breakdown (phases grouped by service) ---
        service_rows = (
            Phase.objects.filter(job__unit=self, service__isnull=False)
            .exclude(status__in=PhaseStatuses.IGNORED_STATUSES)
            .values("service__name")
            .annotate(participation_count=Count("id"))
            .order_by("-participation_count")
        )
        data["service_breakdown"] = [
            {
                "name": row["service__name"],
                "participation_count": row["participation_count"],
            }
            for row in service_rows
        ]

        # --- Job pipeline counts by status ---
        status_labels = dict(JobStatuses.CHOICES)
        status_colours = dict(JobStatuses.BS_COLOURS)
        job_rows = self.jobs.values("status").annotate(count=Count("id"))
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

        # --- Delivery throughput: phases delivered per month (last ~6 months) ---
        throughput_start = (timezone.now() - timedelta(days=182)).date()
        throughput_rows = (
            Phase.objects.filter(
                job__unit=self,
                status=PhaseStatuses.DELIVERED,
                actual_delivery_date__date__gte=throughput_start,
            )
            .annotate(month=TruncMonth("actual_delivery_date"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        data["delivery_throughput"] = {
            "labels": [
                row["month"].strftime("%b %Y")
                for row in throughput_rows
                if row["month"]
            ],
            "counts": [row["count"] for row in throughput_rows if row["month"]],
        }

        # --- Summary tiles ---
        phases_delivered = Phase.objects.filter(
            job__unit=self,
            status=PhaseStatuses.DELIVERED,
            actual_delivery_date__date__range=(start_date, end_date),
        ).count()
        summary = {
            "active_members": len(memberships),
            "consultants": len(consultant_ids),
            "active_jobs": self.jobs.filter(
                status__in=JobStatuses.ACTIVE_STATUSES
            ).count(),
            "phases_delivered": phases_delivered,
            "utilisation_4wk": data["upcoming_availability"]
            .get("fourweeks", {})
            .get("totals", {})
            .get("utilisation_percentage", 0),
        }
        if include_financials:
            # Single aggregate — deliberately avoids per-job staff_cost()/day-rate
            # which would be an N+1 over potentially hundreds of active jobs.
            from django.db.models import Sum

            total_revenue = self.jobs.filter(
                status__in=JobStatuses.ACTIVE_STATUSES
            ).aggregate(total=Sum("revenue"))["total"] or Decimal(0)
            summary["total_revenue"] = total_revenue
        data["summary"] = summary

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

            # Guard against a zero denominator (e.g. a unit with no consultants,
            # or a window where the scoped members have no working days).
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
            today = timezone.localdate()
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
            user = member.member if hasattr(member, "member") else member
            user_schedule = {}

            # Initialize all dates as empty
            for date_str in date_range:
                user_schedule[date_str] = ""

            # Fill in the timeslots for each day they overlap
            for slot in user.week_timeslots:
                # Calculate which days this slot spans within our date range
                # Convert to local time before extracting date to handle UTC offset
                slot_start_date = max(timezone.localtime(slot.start).date(), start_date)
                slot_end_date = min(timezone.localtime(slot.end).date(), end_date)

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
        # Match the role to its code definition by NAME, not pk. Relying on
        # self.pk == UnitRoles constant is fragile: if a role's database pk drifts
        # from its constant (as happened in production) the pk-indexed lookup
        # silently assigns another role's permission set.
        perms = UnitRoles.get_default_permissions_for_role(self.name)
        if perms is None:
            # Not a known default role — leave any custom permissions alone.
            return False

        self.permissions.clear()
        for perm in perms:
            if not perm:
                continue
            codeword = perm.split(".")[1] if "." in perm else perm
            if Permission.objects.filter(codename=codeword).exists():
                self.permissions.add(Permission.objects.get(codename=codeword))
        self.save()
        return True


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
        # Resync only this member's permissions - reconciling the whole unit on
        # every membership save made bulk operations O(n^2).
        self.unit.sync_permissions(users=[self.member_id])


@receiver(
    m2m_changed,
    sender=OrganisationalUnit.leads.through,
    dispatch_uid="sync_lead_memberships",
)
def sync_lead_memberships(sender, instance, action, **kwargs):
    """Grant manager rights to leads whenever the ``leads`` M2M changes.

    Covers every path that assigns a lead (edit form, setup wizard, admin,
    demo data, shell) - not just unit creation.
    """
    if action != "post_add":
        return
    if isinstance(instance, OrganisationalUnit):
        instance.ensure_lead_memberships()
    else:
        # Reverse side: ``instance`` is a User; pk_set holds the unit pks.
        for unit in OrganisationalUnit.objects.filter(
            pk__in=kwargs.get("pk_set") or []
        ):
            unit.ensure_lead_memberships()
