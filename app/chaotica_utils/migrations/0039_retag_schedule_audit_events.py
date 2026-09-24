from django.db import migrations
from django.db.models import Q


# Prefixes written by TimeSlot.save()/delete() via log_system_activity.
_SLOT_PREFIXES = ("Slot created:", "Slot updated:", "Slot deleted:")


def _slot_message_filter():
    q = Q()
    for prefix in _SLOT_PREFIXES:
        q |= Q(message__startswith=prefix)
    return q


def retag_forwards(apps, schema_editor):
    """Move historical slot-change events into the SCHEDULE category/verb.

    Before this change, slot mutations were logged with the default
    ``general``/``other`` category/verb, so the Activity Log's "Schedule"
    filter never matched them despite the events existing. Re-tag only the
    rows that are unambiguously slot changes (matching message prefix AND
    still on the old default category/verb) so re-running is safe.
    """
    AuditEvent = apps.get_model("chaotica_utils", "AuditEvent")
    AuditEvent.objects.filter(_slot_message_filter()).filter(
        category="general", verb="other"
    ).update(category="schedule", verb="schedule")


def retag_backwards(apps, schema_editor):
    """Restore slot-change events to the previous default category/verb."""
    AuditEvent = apps.get_model("chaotica_utils", "AuditEvent")
    AuditEvent.objects.filter(_slot_message_filter()).filter(
        category="schedule", verb="schedule"
    ).update(category="general", verb="other")


class Migration(migrations.Migration):

    dependencies = [
        ("chaotica_utils", "0038_backfill_system_notes_to_audit"),
    ]

    operations = [
        migrations.RunPython(retag_forwards, retag_backwards),
    ]
