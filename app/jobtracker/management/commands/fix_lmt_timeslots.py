"""
Fix datetimes corrupted by the pytz LMT (Local Mean Time) bug.

When Django's make_aware() used pytz timezone objects via .replace(tzinfo=tz),
it applied historical LMT offsets instead of modern timezone offsets. This
caused stored UTC times to be slightly wrong (e.g., +1 minute for Europe/London).

This command scans TimeSlot, TimeSlotComment, and LeaveRequest for records
where undoing the LMT offset recovers a "round" naive time (seconds=0,
minutes divisible by 15), then computes the correct UTC.

Usage:
    python manage.py fix_lmt_timeslots          # dry-run (default)
    python manage.py fix_lmt_timeslots --fix    # apply corrections
"""
from datetime import datetime, timedelta

import pytz
import zoneinfo

from django.core.management.base import BaseCommand
from django.db import transaction


def get_lmt_offsets():
    """Compute the LMT utcoffset for every pytz common timezone.

    Returns a dict of {tz_name: timedelta} for timezones where the LMT
    offset differs from zero (i.e. not UTC/GMT).
    """
    offsets = {}
    for tz_name in pytz.common_timezones:
        dummy = datetime(2020, 1, 1).replace(tzinfo=pytz.timezone(tz_name))
        offset = dummy.utcoffset()
        if offset and offset.total_seconds() != 0:
            offsets[tz_name] = offset
    return offsets


class Command(BaseCommand):
    help = "Detect and fix datetimes corrupted by pytz LMT offset bug"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Apply corrections (default is dry-run)",
        )

    def handle(self, *args, **options):
        apply_fix = options["fix"]
        lmt_offsets = get_lmt_offsets()

        if apply_fix:
            self.stdout.write(self.style.WARNING("Running in FIX mode"))
        else:
            self.stdout.write("Running in DRY-RUN mode (use --fix to apply)")

        total_found = 0
        total_fixed = 0

        # Scan each model
        from jobtracker.models.timeslot import TimeSlot, TimeSlotComment
        from chaotica_utils.models.leave import LeaveRequest

        total_found += self._scan_model(
            TimeSlot, "user", ["start", "end"],
            "TimeSlot", lmt_offsets, apply_fix,
        )
        total_found += self._scan_model(
            TimeSlotComment, "user", ["start", "end"],
            "TimeSlotComment", lmt_offsets, apply_fix,
        )
        total_found += self._scan_model(
            LeaveRequest, "user", ["start_date", "end_date"],
            "LeaveRequest", lmt_offsets, apply_fix,
        )

        self.stdout.write("")
        if total_found == 0:
            self.stdout.write(self.style.SUCCESS("No corrupted records found."))
        elif apply_fix:
            self.stdout.write(self.style.SUCCESS(
                f"Fixed {total_found} corrupted field(s)."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"Found {total_found} corrupted field(s). "
                "Re-run with --fix to apply corrections."
            ))

    def _scan_model(self, model_class, user_field, date_fields, label,
                    lmt_offsets, apply_fix):
        """Scan a model for LMT-corrupted datetime fields.

        Returns the number of corrupted fields found.
        """
        found = 0
        utc = zoneinfo.ZoneInfo("UTC")

        # Group by timezone to avoid recomputing offsets per record
        for tz_name, lmt_offset in lmt_offsets.items():
            lookup = {f"{user_field}__pref_timezone": tz_name}
            records = model_class.objects.filter(**lookup).select_related(user_field)
            if not records.exists():
                continue

            correct_tz = zoneinfo.ZoneInfo(tz_name)

            with transaction.atomic():
                for record in records:
                    updates = {}
                    for field_name in date_fields:
                        val = getattr(record, field_name)
                        if val is None:
                            continue

                        stored_utc = val.replace(tzinfo=None)
                        # Recover the naive local time the user originally entered
                        naive_local = stored_utc + lmt_offset

                        # Only flag if naive time looks like a deliberate entry
                        # (seconds=0, minutes on a 15-min boundary)
                        if naive_local.second != 0:
                            continue
                        if naive_local.minute % 15 != 0:
                            continue

                        # Compute what the correct UTC should be
                        correct_aware = naive_local.replace(tzinfo=correct_tz)
                        correct_utc = correct_aware.astimezone(utc)

                        if correct_utc.replace(tzinfo=None) == stored_utc:
                            continue  # Already correct

                        found += 1
                        delta = val - correct_utc
                        user = getattr(record, user_field)
                        self.stdout.write(
                            f"  {label} pk={record.pk} {field_name}: "
                            f"{val.strftime('%Y-%m-%d %H:%M:%S')} UTC → "
                            f"{correct_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC "
                            f"(off by {delta}) "
                            f"[user={user.pk} tz={tz_name}]"
                        )

                        if apply_fix:
                            updates[field_name] = correct_utc

                    if updates and apply_fix:
                        for field_name, value in updates.items():
                            setattr(record, field_name, value)
                        record.save(update_fields=list(updates.keys()))

        return found
