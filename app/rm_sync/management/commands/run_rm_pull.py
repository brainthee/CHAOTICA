"""Run the inbound (RM → CHAOTICA) sync for PULL users.

Useful for validating against a production RM token from a non-production instance: with
``RM_SYNC_READ_ONLY`` on, no writes ever reach RM, and ``--dry-run`` additionally makes no
changes to CHAOTICA — it just reports what *would* happen.

    python manage.py run_rm_pull --dry-run
    python manage.py run_rm_pull --user someone@example.com
"""

from django.core.management.base import BaseCommand

from rm_sync.client import RMClient
from rm_sync.enums import RMSyncDirection
from rm_sync.models import RMSyncRecord


class Command(BaseCommand):
    help = "Run inbound RM → CHAOTICA sync for PULL users."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing to CHAOTICA.",
        )
        parser.add_argument(
            "--user",
            help="Limit to a single user by email.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        client = RMClient()

        records = RMSyncRecord.objects.filter(direction=RMSyncDirection.PULL)
        if options.get("user"):
            records = records.filter(user__email__iexact=options["user"])

        if not records.exists():
            self.stdout.write(self.style.WARNING("No PULL records found."))
            return

        totals = {}
        for record in records:
            result = record.pull_records(client=client, dry_run=dry_run)
            self.stdout.write(
                "{}: +{} projects, +{} slots, +{} leave, ~{} updated, -{} deleted, "
                "{} skipped(ours), {} unresolved, {} errors".format(
                    record.user.email,
                    result.created_projects,
                    result.created_slots,
                    result.created_leave,
                    result.updated_slots,
                    result.deleted_slots,
                    result.skipped_chaotica_origin,
                    result.skipped_unresolved,
                    result.errors,
                )
            )
            for k in (
                "created_projects",
                "created_slots",
                "created_leave",
                "updated_slots",
                "deleted_slots",
                "skipped_chaotica_origin",
                "skipped_unresolved",
                "errors",
            ):
                totals[k] = totals.get(k, 0) + getattr(result, k)

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS("{}Totals: {}".format(prefix, totals)))
