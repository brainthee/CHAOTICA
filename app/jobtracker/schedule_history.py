"""Service layer for the scheduler version-control / live-delta primitive.

Every scheduler mutation calls :func:`record` at its success point, passing
before/after snapshots of the affected slots. That builds one reversible
:class:`~jobtracker.models.ScheduleAction` ("commit") and broadcasts it to open
viewers of the same scope. :func:`revert` applies the inverse of an action and
logs the inverse as its own (redoable) REVERT action.
"""
import logging
from django.db import transaction

from django.core.exceptions import PermissionDenied
from django.utils.dateparse import parse_datetime

from .models import (
    ScheduleAction,
    ScheduleActionType,
    TimeSlot,
    TimeSlotComment,
    Phase,
)

logger = logging.getLogger(__name__)

# Writable fields captured in a snapshot, per model.
_TIMESLOT_FIELDS = (
    "start",
    "end",
    "user_id",
    "slot_type_id",
    "phase_id",
    "project_id",
    "deliveryRole",
    "is_onsite",
)
_COMMENT_FIELDS = ("start", "end", "user_id", "comment")

_DT_FIELDS = ("start", "end")


def _dt(value):
    """Serialise a datetime field to an ISO string (or pass through)."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _fields(instance, names):
    data = {}
    for name in names:
        value = getattr(instance, name)
        if name in _DT_FIELDS:
            value = _dt(value)
        data[name] = value
    return data


def snapshot(slot):
    """Snapshot a TimeSlot's writable fields (with model + pk)."""
    return {"model": "timeslot", "pk": slot.pk, "fields": _fields(slot, _TIMESLOT_FIELDS)}


def snapshot_comment(comment):
    """Snapshot a TimeSlotComment's writable fields (with model + pk)."""
    return {
        "model": "timeslotcomment",
        "pk": comment.pk,
        "fields": _fields(comment, _COMMENT_FIELDS),
    }


def _apply_fields(fields):
    """Turn a stored field dict into kwargs suitable for model construction/update
    (parsing ISO datetimes back into datetime objects)."""
    out = dict(fields)
    for name in _DT_FIELDS:
        if name in out and out[name]:
            out[name] = parse_datetime(out[name])
    return out


def _derive_scope(payload):
    """Derive (job, phase) scope from the affected slots' phases.

    All slots in one phase → (job, phase). Multiple phases in one job → (job, None).
    Otherwise / no phase (project / comment / internal) → (None, None)."""
    phase_ids = set()
    for item in payload:
        if item["model"] != "timeslot":
            continue
        fields = item.get("after") or item.get("before") or {}
        if fields.get("phase_id"):
            phase_ids.add(fields["phase_id"])
    if not phase_ids:
        return None, None
    phases = list(Phase.objects.filter(pk__in=phase_ids).select_related("job"))
    if not phases:
        return None, None
    job_ids = {p.job_id for p in phases}
    job = phases[0].job if len(job_ids) == 1 else None
    phase = phases[0] if len(phase_ids) == 1 and len(phases) == 1 else None
    return job, phase


def _build_payload(items_before, items_after):
    """Diff two snapshot lists into per-item {model, pk, before, after} records.

    Keyed on (model, pk): after-only ⇒ create, before-only ⇒ delete, both ⇒ update.
    """
    before_map = {(s["model"], s["pk"]): s["fields"] for s in items_before}
    after_map = {(s["model"], s["pk"]): s["fields"] for s in items_after}
    keys = list(before_map.keys())
    for key in after_map:
        if key not in before_map:
            keys.append(key)
    payload = []
    for (model, pk) in keys:
        payload.append(
            {
                "model": model,
                "pk": pk,
                "before": before_map.get((model, pk)),
                "after": after_map.get((model, pk)),
            }
        )
    return payload


def _describe_item(item):
    before, after = item["before"], item["after"]
    if before is None and after is None:
        return None
    if before is None:
        return "added"
    if after is None:
        return "removed"
    return "changed"


# ---- Human-readable field-level diffs (for the history detail lines) ----------

def collect_payload_refs(actions):
    """Every user/slot-type/phase/project id referenced across these actions'
    payloads, so labels can be resolved in one batch (no per-row queries)."""
    refs = {"user": set(), "slot_type": set(), "phase": set(), "project": set()}
    key = {
        "user_id": "user",
        "slot_type_id": "slot_type",
        "phase_id": "phase",
        "project_id": "project",
    }
    for action in actions:
        for item in action.payload or []:
            for side in ("before", "after"):
                fields = item.get(side) or {}
                for field, bucket in key.items():
                    val = fields.get(field)
                    if val:
                        refs[bucket].add(val)
    return refs


def build_label_maps(refs):
    """Resolve the ids from :func:`collect_payload_refs` to display labels."""
    from chaotica_utils.models import User
    from .models import Phase, Project, TimeSlotType

    return {
        "user": {u.pk: str(u) for u in User.objects.filter(pk__in=refs["user"])},
        "slot_type": {
            t.pk: t.name for t in TimeSlotType.objects.filter(pk__in=refs["slot_type"])
        },
        "phase": {
            p.pk: str(p)
            for p in Phase.objects.select_related("job__client").filter(
                pk__in=refs["phase"]
            )
        },
        "project": {
            p.pk: str(p) for p in Project.objects.filter(pk__in=refs["project"])
        },
    }


def _fmt_dt(iso):
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    if not iso:
        return ""
    dt = parse_datetime(iso)
    if dt is None:
        return str(iso)
    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.strftime("%-d %b %Y, %H:%M")


def _fmt_range(start_iso, end_iso):
    start, end = _fmt_dt(start_iso), _fmt_dt(end_iso)
    if start and end:
        return "{} – {}".format(start, end)
    return start or end


def describe_action_details(action, labels):
    """Field-level change lines for an action, e.g.
    ``[{"label": "When", "from": "...", "to": "..."}]``. ``labels`` is the
    resolved map from :func:`build_label_maps`; missing ids degrade to blank."""
    from .enums import TimeSlotDeliveryRole

    roles = dict(TimeSlotDeliveryRole.CHOICES)
    lines = []
    for item in action.payload or []:
        before, after = item.get("before"), item.get("after")
        if before is None and after is None:
            continue
        if item.get("model") == "timeslotcomment":
            lines.extend(_comment_lines(before, after))
        else:
            lines.extend(_timeslot_lines(before, after, labels, roles))
    return lines


def _slot_summary(fields, labels, roles):
    """A compact one-line description of a slot's state."""
    bits = [_fmt_range(fields.get("start"), fields.get("end"))]
    type_label = labels["slot_type"].get(fields.get("slot_type_id"))
    if type_label:
        bits.append(type_label)
    role = fields.get("deliveryRole")
    if role:
        bits.append(roles.get(role, str(role)))
    if fields.get("is_onsite"):
        bits.append("On-site")
    return " · ".join(b for b in bits if b)


def _timeslot_lines(before, after, labels, roles):
    def loc(f):
        return "On-site" if f.get("is_onsite") else "Remote"

    def scope(f):
        if f.get("phase_id"):
            return labels["phase"].get(f["phase_id"], "")
        if f.get("project_id"):
            return labels["project"].get(f["project_id"], "")
        return ""

    if before is None:
        return [{"label": "Booked", "to": _slot_summary(after, labels, roles)}]
    if after is None:
        return [{"label": "Was", "from": _slot_summary(before, labels, roles)}]

    lines = []
    if before.get("start") != after.get("start") or before.get("end") != after.get("end"):
        lines.append({
            "label": "When",
            "from": _fmt_range(before.get("start"), before.get("end")),
            "to": _fmt_range(after.get("start"), after.get("end")),
        })
    if before.get("user_id") != after.get("user_id"):
        lines.append({
            "label": "Assignee",
            "from": labels["user"].get(before.get("user_id"), ""),
            "to": labels["user"].get(after.get("user_id"), ""),
        })
    if before.get("slot_type_id") != after.get("slot_type_id"):
        lines.append({
            "label": "Type",
            "from": labels["slot_type"].get(before.get("slot_type_id"), ""),
            "to": labels["slot_type"].get(after.get("slot_type_id"), ""),
        })
    if before.get("deliveryRole") != after.get("deliveryRole"):
        lines.append({
            "label": "Role",
            "from": roles.get(before.get("deliveryRole"), str(before.get("deliveryRole"))),
            "to": roles.get(after.get("deliveryRole"), str(after.get("deliveryRole"))),
        })
    if bool(before.get("is_onsite")) != bool(after.get("is_onsite")):
        lines.append({"label": "Location", "from": loc(before), "to": loc(after)})
    if (before.get("phase_id") != after.get("phase_id")
            or before.get("project_id") != after.get("project_id")):
        lines.append({"label": "Work", "from": scope(before), "to": scope(after)})
    return lines


def _comment_lines(before, after):
    if before is None:
        return [{"label": "Comment", "to": (after or {}).get("comment", "")}]
    if after is None:
        return [{"label": "Comment removed", "from": before.get("comment", "")}]
    lines = []
    if before.get("comment") != after.get("comment"):
        lines.append({
            "label": "Comment",
            "from": before.get("comment", ""),
            "to": after.get("comment", ""),
        })
    if before.get("start") != after.get("start") or before.get("end") != after.get("end"):
        lines.append({
            "label": "When",
            "from": _fmt_range(before.get("start"), before.get("end")),
            "to": _fmt_range(after.get("start"), after.get("end")),
        })
    return lines


def _summarise(action_type, payload):
    """Human-readable one-line summary for the history panel."""
    n = len(payload)
    plural = "s" if n != 1 else ""
    verbs = {
        ScheduleActionType.CREATE: "Created {} slot{}".format(n, plural),
        ScheduleActionType.UPDATE: "Updated {} slot{}".format(n, plural),
        ScheduleActionType.DELETE: "Deleted {} slot{}".format(n, plural),
        ScheduleActionType.MOVE: "Moved {} slot{}".format(n, plural),
        ScheduleActionType.CLEAR: "Cleared {} slot{}".format(n, plural),
        ScheduleActionType.BATCH: "Changed {} slot{}".format(n, plural),
        ScheduleActionType.REVERT: "Reverted {} slot{}".format(n, plural),
    }
    return verbs.get(action_type, "Changed {} slot{}".format(n, plural))


def is_forced(value):
    """Whether a request's ``force`` flag means "Save anyway". Only explicit
    truthy values count - "0" / "false" / "" must not bypass a warning."""
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def record(
    actor,
    action_type,
    items_before,
    items_after,
    forced=False,
    override_reason="",
    overridden="",
    summary=None,
):
    """Build one ScheduleAction from before/after snapshots and broadcast it.

    ``items_before`` / ``items_after`` are lists of :func:`snapshot` /
    :func:`snapshot_comment` results. Returns the created ScheduleAction, or None
    if the change was a no-op (empty payload).

    ``forced`` marks a save made past a bypassable warning; ``overridden`` is a
    short description of what was overridden (e.g. "overlap with 2 bookings;
    over scope") and ``override_reason`` the user's optional reason. A forced
    action is also written to the Activity Log as a warning-severity event.
    """
    payload = _build_payload(items_before, items_after)
    if not payload:
        return None
    job, phase = _derive_scope(payload)
    text = summary or _summarise(action_type, payload)
    if forced and overridden:
        text = "{} (overrode: {})".format(text, overridden)
    reason = (override_reason or "").strip() if forced else ""
    action = ScheduleAction.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        action_type=action_type,
        job=job,
        phase=phase,
        summary=text,
        payload=payload,
        forced=bool(forced),
        override_reason=reason,
    )
    if forced:
        _audit_override(action, actor, overridden, reason)
    _broadcast(action)
    return action


def _audit_override(action, actor, overridden, reason):
    """Activity Log entry for a warning that was overridden. ``record_audit``
    directly: ``log_system_activity`` doesn't pass ``severity`` through."""
    from chaotica_utils.audit import record_audit
    from chaotica_utils.models import AuditCategory, AuditSeverity, AuditVerb, User

    target = action.phase or action.job
    if target is None:
        uids = sorted(action._affected_user_ids())
        target = User.objects.filter(pk__in=uids[:1]).first()
    if target is None:
        return
    message = "Warning overridden: {}".format(overridden or "scheduling warning")
    if reason:
        message += " — reason: {}".format(reason)
    record_audit(
        target,
        AuditVerb.SCHEDULE,
        message=message,
        actor=actor if getattr(actor, "pk", None) else None,
        category=AuditCategory.SCHEDULE,
        severity=AuditSeverity.WARNING,
        metadata={
            "reason": reason,
            "mode": overridden,
            "schedule_action": action.pk,
            "summary": action.summary,
        },
    )


def _snap(instance):
    """Snapshot any slot instance, dispatching on its model."""
    if isinstance(instance, TimeSlot):
        return snapshot(instance)
    return snapshot_comment(instance)


def record_creates(actor, instances, action_type=ScheduleActionType.CREATE, **kwargs):
    """Record the creation of one or more slot/comment instances. ``kwargs``
    (forced / override_reason / overridden / summary) pass to :func:`record`."""
    afters = [_snap(i) for i in instances if i is not None and i.pk]
    if not afters:
        return None
    return record(actor, action_type, [], afters, **kwargs)


def record_deletes(actor, snapshots_before, action_type=ScheduleActionType.DELETE):
    """Record the deletion of instances (snapshots captured *before* delete)."""
    return record(actor, action_type, snapshots_before, [])


def _jsonable(data):
    """Coerce a get_schedule_json() dict into a JSON/msgpack-safe form (ISO dates)."""
    out = {}
    for key, value in data.items():
        if hasattr(value, "isoformat"):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out


def build_delta(action):
    """Turn a committed ScheduleAction into a client-applicable delta:
    ``upserts`` (full get_schedule_json dicts to add/update in the vis DataSet)
    and ``removals`` (model + pk so the client can remove slot-<pk>/cmt-<pk>)."""
    upserts = []
    removals = []
    for item in action.payload:
        model = item["model"]
        pk = item["pk"]
        if item["after"] is None:
            removals.append({"is_comment": model == "timeslotcomment", "id": pk})
            continue
        if model == "timeslot":
            obj = (
                TimeSlot.objects.filter(pk=pk)
                .select_related("phase__job", "project", "slot_type", "user")
                .first()
            )
        else:
            obj = TimeSlotComment.objects.filter(pk=pk).select_related("user").first()
        if obj is not None:
            upserts.append(_jsonable(obj.get_schedule_json()))
    return {
        "action_id": action.pk,
        "actor_id": action.actor_id,
        "action_type": action.action_type,
        "upserts": upserts,
        "removals": removals,
    }


def filter_delta_for_users(delta, viewable_user_pks):
    """Restrict a delta's ``upserts`` to slots for users the viewer may see.

    ``viewable_user_pks`` is the set of user PKs whose schedule the viewer may
    view (global scope). Pass ``None`` to skip filtering — used for job/phase
    scope, where the viewer is already authorised for the whole scope. Removals
    are left intact (they carry only a pk; applying an unknown removal is a
    client-side no-op)."""
    if viewable_user_pks is None:
        return delta
    upserts = [
        u for u in delta.get("upserts", []) if u.get("userId") in viewable_user_pks
    ]
    return {**delta, "upserts": upserts}


def can_revert(action, user):
    return action.can_revert(user)


def _get_instance(model_name, pk):
    model = TimeSlot if model_name == "timeslot" else TimeSlotComment
    try:
        return model.objects.get(pk=pk)
    except model.DoesNotExist:
        return None


def _recreate_timeslot(fields):
    kwargs = _apply_fields(fields)
    slot = TimeSlot(**kwargs)
    slot.save()
    return slot


def _recreate_comment(fields):
    kwargs = _apply_fields(fields)
    comment = TimeSlotComment(**kwargs)
    comment.save()
    return comment


def _restore_timeslot(pk, fields):
    slot = _get_instance("timeslot", pk)
    if slot is None:
        # Object gone — recreate it to restore the prior state.
        return _recreate_timeslot(fields)
    for name, value in _apply_fields(fields).items():
        setattr(slot, name, value)
    slot.save()
    return slot


def _restore_comment(pk, fields):
    comment = _get_instance("timeslotcomment", pk)
    if comment is None:
        return _recreate_comment(fields)
    for name, value in _apply_fields(fields).items():
        setattr(comment, name, value)
    comment.save()
    return comment


def revert(action, actor):
    """Apply the inverse of ``action`` and record it as a new REVERT action.

    Routes recreation/updates through ``save()`` so phase status/date recalc and
    activity logging fire. Marks ``action`` reverted and links the pair via
    ``reverted_by`` so the revert is itself redoable.
    """
    if not action.can_revert(actor):
        raise PermissionDenied("You can't revert this schedule change.")

    # Booking rule: undo can't put slots back on (or move slots of) a phase
    # that's since been finished / un-scoped, or a job that's no longer
    # active. Undoing a create (a delete) is still fine.
    from django.core.exceptions import ValidationError
    from .models import Phase

    phase_ids = set()
    for item in action.payload:
        if item["model"] != "timeslot" or item["before"] is None:
            continue
        for fields in (item["before"], item.get("after") or {}):
            if fields.get("phase_id"):
                phase_ids.add(fields["phase_id"])
    for phase in Phase.objects.filter(pk__in=phase_ids).select_related("job"):
        reason = phase.booking_block_reason()
        if reason:
            raise ValidationError(
                "Can't undo this change: {} can't be rescheduled. {}".format(phase, reason)
            )

    # Atomic so a refused restore (e.g. a slot on a now-closed phase raises
    # ValidationError) leaves nothing half-reverted.
    with transaction.atomic():
        inverse_before = []
        inverse_after = []

        for item in action.payload:
            model = item["model"]
            pk = item["pk"]
            before = item["before"]
            after = item["after"]

            if before is None:
                # Was a create → delete the object. Inverse looks like a delete.
                instance = _get_instance(model, pk)
                if instance is not None:
                    snap = snapshot(instance) if model == "timeslot" else snapshot_comment(instance)
                    inverse_before.append(snap)
                    instance.delete()
            elif after is None:
                # Was a delete → recreate from before. Inverse looks like a create.
                if model == "timeslot":
                    instance = _recreate_timeslot(before)
                    inverse_after.append(snapshot(instance))
                else:
                    instance = _recreate_comment(before)
                    inverse_after.append(snapshot_comment(instance))
            else:
                # Was an update → restore before. Inverse is update from after→before.
                if model == "timeslot":
                    current = _get_instance("timeslot", pk)
                    if current is not None:
                        inverse_before.append(snapshot(current))
                    instance = _restore_timeslot(pk, before)
                    inverse_after.append(snapshot(instance))
                else:
                    current = _get_instance("timeslotcomment", pk)
                    if current is not None:
                        inverse_before.append(snapshot_comment(current))
                    instance = _restore_comment(pk, before)
                    inverse_after.append(snapshot_comment(instance))

        action.reverted = True
        inverse = record(actor, ScheduleActionType.REVERT, inverse_before, inverse_after)
        if inverse is not None:
            action.reverted_by = inverse
        action.save(update_fields=["reverted", "reverted_by"])
    return inverse


def _broadcast(action):
    """Broadcast the committed action to open viewers of its scope group(s).

    Guarded so the version-control layer works without the Channels/ASGI
    deployment (Phase 3). Never lets a broadcast failure break a mutation.
    """
    try:
        from .broadcast import broadcast_action
    except Exception:  # pragma: no cover - channels not installed
        return
    try:
        broadcast_action(action)
    except Exception:  # pragma: no cover - channel layer unavailable
        logger.debug("ScheduleAction broadcast skipped", exc_info=True)
