"""Re-key imported RM leave by assignment id alone.

Leave used to be keyed on (assignment id, start date), so RM moving a leave's start date
imported a second copy. Leave rows now carry ``day=None`` and are updated in place. Where
an assignment already has several copies, the most recently synced one is kept (the next
sync brings it up to RM's current dates) and the older duplicates, with their timeslot and
leave request, are removed.
"""

from collections import defaultdict

from django.db import migrations


def rekey_leave(apps, schema_editor):
    RMInboundSlot = apps.get_model("rm_sync", "RMInboundSlot")
    LeaveRequest = apps.get_model("chaotica_utils", "LeaveRequest")
    TimeSlot = apps.get_model("jobtracker", "TimeSlot")

    groups = defaultdict(list)
    for row in RMInboundSlot.objects.all():
        if (row.rm_data or {}).get("kind") == "leave":
            groups[(row.record_id, row.rm_assignment_id)].append(row)

    for rows in groups.values():
        rows.sort(
            key=lambda r: (
                r.last_synced.timestamp() if r.last_synced else 0,
                r.day.toordinal() if r.day else 0,
            ),
            reverse=True,
        )
        keep, duplicates = rows[0], rows[1:]
        for dup in duplicates:
            LeaveRequest.objects.filter(timeslot_id=dup.timeslot_id).delete()
            TimeSlot.objects.filter(pk=dup.timeslot_id).delete()  # cascades the row
        if keep.day is not None:
            keep.day = None
            keep.save(update_fields=["day"])


def restore_day(apps, schema_editor):
    RMInboundSlot = apps.get_model("rm_sync", "RMInboundSlot")
    for row in RMInboundSlot.objects.filter(day__isnull=True).select_related("timeslot"):
        if (row.rm_data or {}).get("kind") == "leave":
            row.day = row.timeslot.start.date()
            row.save(update_fields=["day"])


class Migration(migrations.Migration):
    dependencies = [
        ("rm_sync", "0020_rmsyncrecord_rm_role"),
        ("chaotica_utils", "0040_resync_global_role_permissions_v2"),
    ]

    operations = [migrations.RunPython(rekey_leave, restore_day)]
