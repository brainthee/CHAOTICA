"""Inbound (PULL) sync: import a user's Resource Management schedule into CHAOTICA.

RM is treated as the source of truth for PULL users. RM assignments are resolved to one of:

* **Leave** — the ``assignable_id`` is an RM leave-type id → a CHAOTICA ``LEAVE`` timeslot +
  an authorised ``LeaveRequest`` (constructed directly; we deliberately do NOT call
  ``LeaveRequest.authorise()`` which has notification side effects).
* **CHAOTICA-origin project** — a project we pushed to RM (tagged ``CHAOTICA`` / carrying the
  RM warning marker / already mapped by an ``RMAssignable``). Skipped, to avoid re-importing
  our own pushed data (loop prevention).
* **RM-native project** — mirrored into a CHAOTICA internal ``Project`` (keyed by
  ``external_id``) with a link back to RM, and ``INTERNAL_PROJECT`` timeslots.

Every timeslot created here is tracked by an ``RMInboundSlot``. When the record is
authoritative, reconcile deletes only ``RMInboundSlot``-linked timeslots that no longer exist
in RM — never a CHAOTICA-native or PUSH-origin slot.
"""

import logging
import zoneinfo
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from constance import config
from django.utils import timezone

from chaotica_utils.enums import LeaveRequestTypes
from chaotica_utils.models import LeaveRequest, get_sentinel_user
from jobtracker.enums import DefaultTimeSlotTypes, TimeSlotDeliveryRole
from jobtracker.models import Project, TimeSlot, TimeSlotType

from .client import RMClient

logger = logging.getLogger("rm_sync")

# RM leave-type *name* → CHAOTICA LeaveRequestTypes. Matching by name (rather than the
# account-specific numeric ids in the old importer) keeps this durable across RM accounts.
LEAVE_NAME_MAP = {
    "Regular Vacation": LeaveRequestTypes.ANNUAL_LEAVE,
    "Regular Vacation (AM)": LeaveRequestTypes.ANNUAL_LEAVE,
    "Regular Vacation (PM)": LeaveRequestTypes.ANNUAL_LEAVE,
    "Sick Leave": LeaveRequestTypes.SICK,
    "Illness": LeaveRequestTypes.SICK,
    "Public Holiday": LeaveRequestTypes.PUBLIC_HOLIDAY,
    "Non-working Day": LeaveRequestTypes.NON_WORKING,
    "Paternity Leave": LeaveRequestTypes.PATERNITY_MATERNITY,
    "TOIL": LeaveRequestTypes.TOIL,
    "Bereavement Leave": LeaveRequestTypes.COMPASSIONATE_LEAVE,
    "Excused from Office": LeaveRequestTypes.EXCUSED,
    "Military Training": LeaveRequestTypes.MILITARY_LEAVE,
    "Other Approved Absence": LeaveRequestTypes.OTHER_APPROVED,
    "Overtime Vacation Taken": LeaveRequestTypes.OVERTIME_LEAVE,
    "Unpaid Absence": LeaveRequestTypes.UNPAID_LEAVE,
    "Jury Service": LeaveRequestTypes.JURY_SERVICE,
    "Medical Appointment": LeaveRequestTypes.MEDICAL,
    "Sabbatical Leave": LeaveRequestTypes.SABBATICAL,
}
DEFAULT_LEAVE_TYPE = LeaveRequestTypes.OTHER_APPROVED

DEFAULT_BUSINESS_START = time(9, 0)
DEFAULT_BUSINESS_END = time(17, 30)


@dataclass
class InboundResult:
    """Summary of an inbound sync run (also used for dry-run previews)."""

    created_projects: int = 0
    created_slots: int = 0
    created_leave: int = 0
    updated_slots: int = 0
    deleted_slots: int = 0
    skipped_chaotica_origin: int = 0
    skipped_unresolved: int = 0
    errors: int = 0
    details: list = field(default_factory=list)

    def note(self, msg):
        self.details.append(msg)
        logger.info(msg)


# --------------------------------------------------------------------------- helpers
def _business_tz(user):
    org = user.unit_memberships.first()
    if org and getattr(org.unit, "businessHours_timezone", None):
        try:
            return zoneinfo.ZoneInfo(org.unit.businessHours_timezone)
        except Exception:
            pass
    if getattr(user, "pref_timezone", None):
        try:
            return zoneinfo.ZoneInfo(str(user.pref_timezone))
        except Exception:
            pass
    return zoneinfo.ZoneInfo("UTC")


def _business_hours(user):
    org = user.unit_memberships.first()
    if org:
        return (
            org.unit.businessHours_startTime or DEFAULT_BUSINESS_START,
            org.unit.businessHours_endTime or DEFAULT_BUSINESS_END,
        )
    return DEFAULT_BUSINESS_START, DEFAULT_BUSINESS_END


def _working_days(user):
    """Set of ISO weekday numbers (Mon=1 .. Sun=7) that are working days for the user."""
    org = user.unit_memberships.first()
    if org and org.unit.businessHours_days:
        try:
            return {int(d) for d in org.unit.businessHours_days}
        except (TypeError, ValueError):
            pass
    return {1, 2, 3, 4, 5}


def _parse_date(value):
    """Parse RM's ISO ``YYYY-MM-DD`` date string."""
    return datetime.strptime(value, "%Y-%m-%d").date()


def _percent(assignment):
    if assignment.get("allocation_mode") == "percent":
        pct = assignment.get("percent")
        if pct is not None:
            return float(pct)
    return 1.0


def expand_assignment(assignment, user):
    """Yield ``(day, start_dt, end_dt)`` tz-aware spans for an assignment.

    Full allocations (>= 100%) become a single multi-day slot (matching the existing importer
    and keeping row counts low). Partial allocations fan out into per-working-day slots, each
    shortened to ``percent`` of that day's business hours so ``get_business_hours()`` — and
    therefore utilisation — is proportional automatically.
    """
    tz = _business_tz(user)
    start_date = _parse_date(assignment["starts_at"])
    end_date = _parse_date(assignment["ends_at"])
    pct = _percent(assignment)

    if pct >= 1.0:
        start_dt = datetime.combine(start_date, time.min, tzinfo=tz)
        end_dt = datetime.combine(end_date, time.max, tzinfo=tz)
        yield start_date, start_dt, end_dt
        return

    b_start, b_end = _business_hours(user)
    span_hours = (
        (b_end.hour * 60 + b_end.minute) - (b_start.hour * 60 + b_start.minute)
    ) / 60.0
    working = _working_days(user)
    d = start_date
    while d <= end_date:
        if (d.weekday() + 1) in working:
            start_dt = datetime.combine(d, b_start, tzinfo=tz)
            end_dt = start_dt + timedelta(hours=pct * span_hours)
            yield d, start_dt, end_dt
        d += timedelta(days=1)


def is_chaotica_origin(project):
    """Was this RM project created by CHAOTICA's push sync? (loop prevention)"""
    from .models import RMAssignable

    tags = project.get("tags")
    values = []
    if isinstance(tags, dict):
        values = [t.get("value") for t in tags.get("data", [])]
    elif isinstance(tags, list):
        values = [t if isinstance(t, str) else t.get("value") for t in tags]
    if "CHAOTICA" in values:
        return True
    desc = project.get("description") or ""
    if config.RM_WARNING_MSG and config.RM_WARNING_MSG in desc:
        return True
    if RMAssignable.objects.filter(rm_id=str(project.get("id"))).exists():
        return True
    return False


def _rm_project_overview(rm_project):
    bits = [rm_project.get("name", ""), "RM project #{}".format(rm_project["id"])]
    if rm_project.get("project_code"):
        bits.append("Code: {}".format(rm_project["project_code"]))
    if rm_project.get("client"):
        bits.append("Client: {}".format(rm_project["client"]))
    if rm_project.get("project_state"):
        bits.append("State: {}".format(rm_project["project_state"]))
    return " · ".join(b for b in bits if b)


def apply_rm_project_fields(project, rm_project, is_new):
    """Copy RM-authoritative fields onto a CHAOTICA Project (create or refresh).

    RM is the source of truth for PULL, so re-importing refreshes ``state``/``deliverable``/
    ``client``/``external_url``/``title``/``overview`` from RM. ``status`` (the CHAOTICA
    lifecycle) is only set on create or when still ``UNTRACKED`` — so a manually-managed
    lifecycle isn't clobbered on every pull. Returns the list of changed field names.
    """
    from .clients import get_or_create_client
    from jobtracker.enums import ProjectState, ProjectStatuses

    state = ProjectState.FROM_RM.get(
        rm_project.get("project_state"), ProjectState.INTERNAL
    )
    deliverable = (
        state != ProjectState.INTERNAL
    )  # Internal RM projects aren't client work
    values = {
        "title": rm_project.get("name") or "RM project {}".format(project.external_id),
        "state": state,
        "deliverable": deliverable,
        "client": get_or_create_client(rm_project.get("client")),
        "external_url": "https://app.rm.smartsheet.com/#/projects/{}".format(
            rm_project["id"]
        ),
        "overview": _rm_project_overview(rm_project),
        "data": {
            "rm_project": {
                k: rm_project.get(k)
                for k in (
                    "id",
                    "name",
                    "project_code",
                    "project_state",
                    "client",
                    "starts_at",
                    "ends_at",
                )
            }
        },
    }
    if is_new or project.status == ProjectStatuses.UNTRACKED:
        values["status"] = {
            ProjectState.CONFIRMED: ProjectStatuses.IN_PROGRESS,
            ProjectState.TENTATIVE: ProjectStatuses.PENDING,
            ProjectState.INTERNAL: ProjectStatuses.UNTRACKED,
        }[state]

    changed = []
    for field_name, value in values.items():
        if getattr(project, field_name) != value:
            setattr(project, field_name, value)
            changed.append(field_name)
    return changed


def refresh_rm_projects(client=None, dry_run=False):
    """Refresh RM-derived fields on *every* imported RM project (not just scheduled ones).

    Re-fetches each RM-sourced ``Project`` (identified by its RM ``external_url``) and reapplies
    state/deliverable/client/etc. Use this to backfill fields after a schema change without
    waiting for each project to reappear in a schedule pull. Returns a summary dict.
    """
    client = client or RMClient()
    from jobtracker.models import Project

    result = {
        "checked": 0,
        "updated": 0,
        "skipped_chaotica": 0,
        "missing": 0,
        "errors": 0,
    }
    qs = (
        Project.objects.filter(
            is_imported=True, external_url__icontains="rm.smartsheet.com"
        )
        .exclude(external_id__isnull=True)
        .exclude(external_id="")
    )
    for project in qs:
        try:
            result["checked"] += 1
            rm_project = client.get_project(project.external_id)
            if rm_project is None:
                result["missing"] += 1
                continue
            if is_chaotica_origin(rm_project):
                result["skipped_chaotica"] += 1
                continue
            changed = apply_rm_project_fields(project, rm_project, is_new=False)
            if changed:
                result["updated"] += 1
                if not dry_run:
                    project.save(update_fields=changed)
        except Exception:
            result["errors"] += 1
            logger.exception("Refresh error for project %s", project.external_id)
    return result


def _mirror_project(record, rm_project, dry_run):
    """Create — or refresh — a CHAOTICA internal Project mirroring an RM project."""
    external_id = str(rm_project["id"])
    existing = Project.objects.filter(external_id=external_id).first()
    if existing:
        # Refresh RM-derived fields so re-imports pick up state/deliverable/client changes.
        if not dry_run:
            changed = apply_rm_project_fields(existing, rm_project, is_new=False)
            if changed:
                existing.save(update_fields=changed)
        return existing, False
    if dry_run:
        return None, True

    org = record.user.unit_memberships.first()
    project = Project(
        external_id=external_id,
        is_imported=True,
        unit=org.unit if org else None,
        created_by=get_sentinel_user(),
    )
    apply_rm_project_fields(project, rm_project, is_new=True)
    project.save()
    return project, True


# --------------------------------------------------------------------------- main
def pull_user(record, client=None, dry_run=False):
    """Import ``record``'s RM schedule into CHAOTICA. Returns an ``InboundResult``."""
    client = client or RMClient()
    result = InboundResult()
    user = record.user

    if not record.rm_id:
        result.note("No RM ID for {} — skipping".format(user.email))
        return result

    # Verify the RM user
    r_user = client.get("/api/v1/users/{}".format(record.rm_id))
    if r_user.status_code != 200:
        result.note(
            "RM user {} returned {} — skipping".format(record.rm_id, r_user.status_code)
        )
        result.errors += 1
        return result
    rm_user = r_user.json()

    existing = {
        (r.rm_assignment_id, r.day): r
        for r in record.inbound_slots.select_related("timeslot")
    }
    seen = set()

    if rm_user.get("archived") or rm_user.get("deleted"):
        # User has left RM. Deactivate locally; assignments treated as empty so reconcile
        # (if authoritative) prunes their imported slots.
        result.note("RM user {} archived/deleted".format(record.rm_id))
        if not dry_run and user.is_active:
            user.is_active = False
            user.save(update_fields=["is_active"])
        assignments = []
    else:
        # Window is configurable: look back N days (0 = today onwards only) and
        # ahead M days. See RM_SYNC_PULL_LOOKBACK_DAYS / _LOOKAHEAD_DAYS.
        today = timezone.now().date()
        start = today - timedelta(days=max(0, int(config.RM_SYNC_PULL_LOOKBACK_DAYS)))
        end = today + timedelta(days=max(0, int(config.RM_SYNC_PULL_LOOKAHEAD_DAYS)))
        assignments = list(
            client.paginate(
                "/api/v1/users/{}/assignments".format(record.rm_id),
                {"from": start.strftime("%Y-%m-%d"), "to": end.strftime("%Y-%m-%d")},
            )
        )

    leave_ids = client.leave_type_ids()

    for assignment in assignments:
        try:
            _process_assignment(
                record, assignment, leave_ids, client, existing, seen, result, dry_run
            )
        except Exception as ex:  # per-assignment isolation
            result.errors += 1
            logger.exception(
                "Inbound error on assignment %s: %s", assignment.get("id"), ex
            )

    # Reconcile — authoritative PULL means RM wins, so drop imported slots gone from RM.
    if record.sync_authoritative:
        for key, inbound in existing.items():
            if key not in seen:
                result.deleted_slots += 1
                result.note(
                    "{} stale slot {}".format(
                        "Would delete" if dry_run else "Deleting", inbound.timeslot_id
                    )
                )
                if not dry_run:
                    _delete_inbound(inbound)

    if not dry_run:
        record.last_synced = timezone.now()
        record.last_sync_result = result.errors == 0
        record.save(update_fields=["last_synced", "last_sync_result"])
    return result


def _process_assignment(
    record, assignment, leave_ids, client, existing, seen, result, dry_run
):
    user = record.user
    aid = assignment["assignable_id"]

    if aid in leave_ids:
        _handle_leave(record, assignment, client, existing, seen, result, dry_run)
        return

    rm_project = client.get_project(aid)
    if rm_project is None:
        result.skipped_unresolved += 1
        return
    if is_chaotica_origin(rm_project):
        result.skipped_chaotica_origin += 1
        return

    project, created = _mirror_project(record, rm_project, dry_run)
    if created:
        result.created_projects += 1
    slot_type = TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.INTERNAL_PROJECT)

    for day, start_dt, end_dt in expand_assignment(assignment, user):
        key = (str(assignment["id"]), day)
        seen.add(key)
        inbound = existing.get(key)
        if inbound:
            _update_slot_times(inbound.timeslot, start_dt, end_dt, result, dry_run)
            continue
        if dry_run or project is None:
            result.created_slots += 1
            continue
        ts = TimeSlot.objects.create(
            user=user,
            slot_type=slot_type,
            project=project,
            start=start_dt,
            end=end_dt,
            deliveryRole=TimeSlotDeliveryRole.NA,
        )
        _register_inbound(record, ts, assignment, day, kind="project")
        result.created_slots += 1


def _handle_leave(record, assignment, client, existing, seen, result, dry_run):
    user = record.user
    tz = _business_tz(user)
    start_date = _parse_date(assignment["starts_at"])
    end_date = _parse_date(assignment["ends_at"])
    key = (str(assignment["id"]), start_date)
    seen.add(key)

    if key in existing:
        return  # leave slots are immutable once imported

    start_dt = datetime.combine(start_date, time.min, tzinfo=tz)
    end_dt = datetime.combine(end_date, time.max, tzinfo=tz)
    result.created_leave += 1
    if dry_run:
        return

    # Resolve the RM leave-type name → CHAOTICA type
    name = None
    for lt in client.leave_types():
        if lt["id"] == assignment["assignable_id"]:
            name = lt.get("name")
            break
    type_of_leave = LEAVE_NAME_MAP.get(name, DEFAULT_LEAVE_TYPE)

    ts = TimeSlot.objects.create(
        user=user,
        slot_type=TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.LEAVE),
        start=start_dt,
        end=end_dt,
    )
    LeaveRequest.objects.create(
        user=user,
        start_date=start_dt,
        end_date=end_dt,
        type_of_leave=type_of_leave,
        notes="Imported from RM",
        authorised=True,
        authorised_on=timezone.now(),
        timeslot=ts,
    )
    _register_inbound(
        record, ts, assignment, start_date, kind="leave", extra={"leave": name}
    )


def _update_slot_times(timeslot, start_dt, end_dt, result, dry_run):
    if timeslot.start != start_dt or timeslot.end != end_dt:
        result.updated_slots += 1
        if not dry_run:
            timeslot.start = start_dt
            timeslot.end = end_dt
            timeslot.save()


def _register_inbound(record, timeslot, assignment, day, kind, extra=None):
    from .models import RMInboundSlot

    data = {
        "assignable_id": assignment["assignable_id"],
        "percent": _percent(assignment),
        "kind": kind,
    }
    if extra:
        data.update(extra)
    RMInboundSlot.objects.create(
        timeslot=timeslot,
        record=record,
        rm_assignment_id=str(assignment["id"]),
        day=day,
        rm_data=data,
        last_synced=timezone.now(),
    )


def _delete_inbound(inbound):
    """Delete an inbound slot and any leave request that owns its timeslot."""
    ts = inbound.timeslot
    LeaveRequest.objects.filter(timeslot=ts).delete()
    ts.delete()  # cascades to RMInboundSlot
