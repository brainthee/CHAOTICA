"""
Fix phase scoping values that were saved as days instead of hours.

Before commit 30eb18e (2026-03-09), the scoping form displayed "Days" but
submitted the raw number directly into *_hours fields.  So a user entering
"5 days" at 7.5 hrs/day got 5.0 stored in delivery_hours — meaning 5 hours,
not 37.5.

Detection heuristic:
  For each non-zero scoping field, divide by hours_in_day.  If the result is
  a "clean" day value (whole number, or half-day like 0.5/1.5/2.5) then the
  stored value is already correct hours.  If instead the *raw stored value*
  itself looks like a clean day value (and dividing it by hours_in_day gives
  a fractional result), then it was almost certainly entered as days but saved
  as hours.  The fix is to multiply by hours_in_day.

Usage:
    python manage.py fix_scope_hours                # dry-run (default)
    python manage.py fix_scope_hours --fix          # apply corrections
    python manage.py fix_scope_hours --phase-id X   # check a single phase
"""
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


SCOPE_FIELDS = [
    "delivery_hours",
    "reporting_hours",
    "mgmt_hours",
    "qa_hours",
    "oversight_hours",
    "debrief_hours",
    "contingency_hours",
    "other_hours",
]

# A value "looks like days" if it's a clean number someone would type:
# whole numbers, or halves (0.5, 1.5, 2.5, ...).
# A value "looks like fractional days" when divided by hours_in_day gives
# something ugly like 0.667 or 1.333.
def _is_clean_day_value(value):
    """Would a human plausibly type this as a number of days?"""
    if value <= 0:
        return False
    # Check if it's a whole number or a half-day
    remainder = value % 1
    return remainder == Decimal("0") or remainder == Decimal("0.5")


def _is_fractional(value):
    """Does this look like a fractional result of bad division?"""
    if value <= 0:
        return False
    remainder = value % Decimal("0.5")
    # Allow small floating point tolerance
    return remainder > Decimal("0.01") and remainder < Decimal("0.49")


class Command(BaseCommand):
    help = "Detect and fix phase scoping values saved as days instead of hours"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Apply corrections (default is dry-run)",
        )
        parser.add_argument(
            "--phase-id",
            type=str,
            default=None,
            help="Only check a specific phase_id",
        )

    def handle(self, *args, **options):
        from jobtracker.models.phase import Phase

        apply_fix = options["fix"]
        phase_id_filter = options["phase_id"]

        if apply_fix:
            self.stdout.write(self.style.WARNING("=== FIX MODE — changes will be saved ===\n"))
        else:
            self.stdout.write("=== DRY-RUN MODE (use --fix to apply) ===\n")

        phases = Phase.objects.select_related("job", "job__client").all()
        if phase_id_filter:
            phases = phases.filter(phase_id=phase_id_filter)

        total_phases_affected = 0
        total_fields_fixed = 0

        for phase in phases:
            hours_in_day = phase.get_hours_in_day()
            if not hours_in_day or hours_in_day <= 0:
                continue

            phase_changes = {}

            for field in SCOPE_FIELDS:
                stored = getattr(phase, field)
                if stored is None or stored <= 0:
                    continue

                stored = Decimal(str(stored))

                # What this value looks like as days (if it were correct hours)
                as_days = stored / hours_in_day

                # The stored value IS the day value the user typed, and it
                # should have been multiplied by hours_in_day before saving.
                #
                # Heuristic: the stored value looks like a clean day entry AND
                # converting it to days gives a fractional/ugly result.
                intended_hours = stored * hours_in_day

                if _is_clean_day_value(stored) and _is_fractional(as_days):
                    phase_changes[field] = {
                        "stored": stored,
                        "as_days": round(as_days, 3),
                        "corrected": intended_hours,
                        "corrected_days": stored,  # what the user meant
                        "confidence": "HIGH",
                    }
                elif (
                    stored < hours_in_day
                    and _is_fractional(as_days)
                    and not _is_clean_day_value(as_days)
                ):
                    # Small values that aren't even 1 day — likely a day value
                    # under 1 day, e.g. 0.25 days stored as 0.25 hours
                    # Only flag if the raw value looks intentional as days
                    if _is_clean_day_value(stored):
                        phase_changes[field] = {
                            "stored": stored,
                            "as_days": round(as_days, 3),
                            "corrected": intended_hours,
                            "corrected_days": stored,
                            "confidence": "MEDIUM",
                        }

            if phase_changes:
                total_phases_affected += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"\n{phase.phase_id}: {phase.job.client} - {phase.title}"
                    )
                )
                self.stdout.write(
                    f"  Job: {phase.job}  |  Hours/day: {hours_in_day}"
                )
                self.stdout.write(
                    f"  Created: {phase.created_date.strftime('%Y-%m-%d') if phase.created_date else 'N/A'}"
                    f"  |  Last modified: {phase.last_modified.strftime('%Y-%m-%d') if phase.last_modified else 'N/A'}"
                )

                for field, info in phase_changes.items():
                    total_fields_fixed += 1
                    label = field.replace("_hours", "").replace("_", " ").title()
                    self.stdout.write(
                        f"  {label:>15}: {info['stored']}h "
                        f"(shows as {info['as_days']}d) → "
                        f"{info['corrected']}h "
                        f"({info['corrected_days']}d)  "
                        f"[{info['confidence']}]"
                    )

                if apply_fix:
                    with transaction.atomic():
                        for field, info in phase_changes.items():
                            setattr(phase, field, info["corrected"])
                        phase.save(update_fields=list(phase_changes.keys()))
                    self.stdout.write(self.style.SUCCESS("  → FIXED"))

        # Summary
        self.stdout.write("\n" + "=" * 60)
        if total_phases_affected == 0:
            self.stdout.write(self.style.SUCCESS("No affected phases found."))
        else:
            action = "Fixed" if apply_fix else "Found"
            self.stdout.write(
                f"{action} {total_fields_fixed} field(s) across "
                f"{total_phases_affected} phase(s)."
            )
            if not apply_fix:
                self.stdout.write(
                    self.style.WARNING("Re-run with --fix to apply corrections.")
                )
