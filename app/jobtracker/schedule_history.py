"""Service layer for the scheduler version-control / live-delta primitive.

Every scheduler mutation calls :func:`record` at its success point, passing
before/after snapshots of the affected slots. That builds one reversible
:class:`~jobtracker.models.ScheduleAction` ("commit") and broadcasts it to open
viewers of the same scope. :func:`revert` applies the inverse of an action and
logs the inverse as its own (redoable) REVERT action.
"""
import logging

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


def record(actor, action_type, items_before, items_after):
    """Build one ScheduleAction from before/after snapshots and broadcast it.

    ``items_before`` / ``items_after`` are lists of :func:`snapshot` /
    :func:`snapshot_comment` results. Returns the created ScheduleAction, or None
    if the change was a no-op (empty payload).
    """
    payload = _build_payload(items_before, items_after)
    if not payload:
        return None
    job, phase = _derive_scope(payload)
    action = ScheduleAction.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        action_type=action_type,
        job=job,
        phase=phase,
        summary=_summarise(action_type, payload),
        payload=payload,
    )
    _broadcast(action)
    return action


def _snap(instance):
    """Snapshot any slot instance, dispatching on its model."""
    if isinstance(instance, TimeSlot):
        return snapshot(instance)
    return snapshot_comment(instance)


def record_creates(actor, instances, action_type=ScheduleActionType.CREATE):
    """Record the creation of one or more slot/comment instances."""
    afters = [_snap(i) for i in instances if i is not None and i.pk]
    if not afters:
        return None
    return record(actor, action_type, [], afters)


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
