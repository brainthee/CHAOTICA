"""Match RM users to existing CHAOTICA users by email and set their RM ID.

Direction/OU come from the market unit's ``RMUnitMap`` (not the CLI), so this can't flip a
UKI user to PULL: an existing record's direction is protected unless ``--force-direction``.

    # Preview all matches (writes nothing)
    python manage.py match_rm_users --dry-run

    # Adopt existing users by email; also create users missing from CHAOTICA
    python manage.py match_rm_users --create-missing

    # Scope to one market unit
    python manage.py match_rm_users --market-unit Prague --create-missing
"""

from django.core.management.base import BaseCommand

from rm_sync.users import match_rm_users


class Command(BaseCommand):
    help = "Match RM users to CHAOTICA users by email and set RM ID (direction from RMUnitMap)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Report only; write nothing."
        )
        parser.add_argument(
            "--market-unit",
            help="Only RM users in this Market Unit (e.g. 'UKI', 'Prague').",
        )
        parser.add_argument(
            "--create-missing",
            action="store_true",
            help="Also create CHAOTICA users for RM users with no email match.",
        )
        parser.add_argument(
            "--overwrite-rm-id",
            action="store_true",
            help="Overwrite an existing, different RM ID on a record.",
        )
        parser.add_argument(
            "--force-direction",
            action="store_true",
            help="Allow changing the direction of records that are already PUSH/PULL "
            "(off by default so existing config is never clobbered).",
        )

    def handle(self, *args, **options):
        r = match_rm_users(
            market_unit_filter=options.get("market_unit"),
            create_missing=options["create_missing"],
            force_direction=options["force_direction"],
            overwrite_rm_id=options["overwrite_rm_id"],
            dry_run=options["dry_run"],
        )
        prefix = "[DRY RUN] " if options["dry_run"] else ""
        self.stdout.write(
            "{}matched={} created={} maps_created={} rm_id_set={} rm_id_conflict={} "
            "direction_set={} direction_protected={} ou_set={} unmatched_rm={} "
            "no_email={} no_market_unit={} errors={}".format(
                prefix,
                r.matched,
                r.created,
                r.maps_created,
                r.rm_id_set,
                r.rm_id_conflict,
                r.direction_set,
                r.direction_protected,
                r.ou_set,
                r.unmatched_rm,
                r.skipped_no_email,
                r.skipped_no_market_unit,
                r.errors,
            )
        )
        if r.maps_created:
            self.stdout.write(
                self.style.WARNING(
                    "{} new market-unit map row(s) created with no OU — set their OU + "
                    "direction in admin, then run 'apply_rm_unit_maps'.".format(
                        r.maps_created
                    )
                )
            )
        self.stdout.write(self.style.SUCCESS("{}Done.".format(prefix)))
