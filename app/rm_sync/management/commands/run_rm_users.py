"""Import/refresh RM users (adopt existing by email + create missing), grouped by Market Unit.

See rm_sync.users.import_rm_users. Direction/OU come from each market unit's RMUnitMap;
existing PUSH/PULL records are never re-pointed (config-safe).

    python manage.py run_rm_users --dry-run
"""

from django.core.management.base import BaseCommand

from rm_sync.users import import_rm_users


class Command(BaseCommand):
    help = "Adopt + create CHAOTICA users for RM users, grouped by Market Unit."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing to CHAOTICA.",
        )
        parser.add_argument(
            "--market-unit",
            help="Only RM users in this Market Unit (e.g. 'Prague').",
        )
        parser.add_argument(
            "--force-direction",
            action="store_true",
            help="Allow changing an already-PUSH/PULL record's direction (default off).",
        )

    def handle(self, *args, **options):
        r = import_rm_users(
            create_missing=True,
            market_unit_filter=options.get("market_unit"),
            force_direction=options["force_direction"],
            dry_run=options["dry_run"],
        )
        prefix = "[DRY RUN] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                "{}matched={} created={} maps_created={} rm_id_set={} direction_set={} "
                "direction_protected={} ou_set={} no_email={} no_market_unit={} errors={}".format(
                    prefix,
                    r.matched,
                    r.created,
                    r.maps_created,
                    r.rm_id_set,
                    r.direction_set,
                    r.direction_protected,
                    r.ou_set,
                    r.skipped_no_email,
                    r.skipped_no_market_unit,
                    r.errors,
                )
            )
        )
        if r.maps_created:
            self.stdout.write(
                self.style.WARNING(
                    "{} new market-unit map row(s) created with no OU — set OU + direction "
                    "in admin, then run 'apply_rm_unit_maps'.".format(r.maps_created)
                )
            )
