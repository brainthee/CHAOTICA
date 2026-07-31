"""Apply RMUnitMap OU + direction onto the imported users of each market unit.

Run this after filling in the OU (and direction, and enabling) on the map rows that
``run_rm_users`` / ``match_rm_users`` auto-created.

    python manage.py apply_rm_unit_maps --dry-run
"""

from django.core.management.base import BaseCommand

from rm_sync.users import apply_rm_unit_maps


class Command(BaseCommand):
    help = "Assign OU + direction to users from their market unit's RMUnitMap."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Report only; write nothing."
        )
        parser.add_argument(
            "--force-direction",
            action="store_true",
            help="Allow changing an already-PUSH/PULL record's direction (default off).",
        )

    def handle(self, *args, **options):
        r = apply_rm_unit_maps(
            force_direction=options["force_direction"], dry_run=options["dry_run"]
        )
        prefix = "[DRY RUN] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                "{}records={} ou_set={} direction_set={} direction_protected={} errors={}".format(
                    prefix,
                    r.records,
                    r.ou_set,
                    r.direction_set,
                    r.direction_protected,
                    r.errors,
                )
            )
        )
