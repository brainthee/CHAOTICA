"""Backfill historical system Notes into the central AuditEvent trail.

System activity moved from ``Note(is_system_note=True)`` to ``AuditEvent`` in
this feature. User-authored notes (``is_system_note=False``) stay in the Note
model and are left untouched. Copies in batches and preserves each note's
original ``create_date`` as the event ``timestamp`` (temporarily disabling
``auto_now_add`` so bulk_create keeps the historical time rather than "now").
"""

from django.db import migrations


BATCH = 500


def backfill(apps, schema_editor):
    Note = apps.get_model("chaotica_utils", "Note")
    AuditEvent = apps.get_model("chaotica_utils", "AuditEvent")

    # Historical models built from migration state expose ``_default_manager``,
    # not necessarily ``objects`` (Note defines custom managers).
    note_mgr = Note._default_manager
    event_mgr = AuditEvent._default_manager

    ts_field = AuditEvent._meta.get_field("timestamp")
    ts_field.auto_now_add = False
    try:
        batch = []
        qs = note_mgr.filter(is_system_note=True).order_by("pk")
        for note in qs.iterator(chunk_size=BATCH):
            batch.append(
                AuditEvent(
                    timestamp=note.create_date,
                    actor_id=note.author_id,
                    actor_repr="",  # historical model has no display helper
                    verb="other",
                    category="general",
                    message=note.content or "",
                    target_content_type_id=note.content_type_id,
                    target_id=str(note.object_id),
                    target_repr="",
                    source="system",
                    severity=20,
                    metadata={"backfilled_note_id": note.pk},
                )
            )
            if len(batch) >= BATCH:
                event_mgr.bulk_create(batch)
                batch = []
        if batch:
            event_mgr.bulk_create(batch)
    finally:
        ts_field.auto_now_add = True


def unbackfill(apps, schema_editor):
    """Remove rows created by this backfill (identified by the metadata marker)."""
    AuditEvent = apps.get_model("chaotica_utils", "AuditEvent")
    AuditEvent._default_manager.filter(
        source="system", metadata__has_key="backfilled_note_id"
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("chaotica_utils", "0037_auditevent"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
