"""Pre-import RM clients into CHAOTICA (see rm_sync.clients.sync_rm_clients).

python manage.py run_rm_clients --dry-run
"""

from django.core.management.base import BaseCommand

from rm_sync.clients import sync_rm_clients


class Command(BaseCommand):
    help = "Create/link CHAOTICA Clients from RM's /clients collection."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Report only; write nothing."
        )

    def handle(self, *args, **options):
        r = sync_rm_clients(dry_run=options["dry_run"])
        prefix = "[DRY RUN] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                "{}created={} linked={} skipped_no_name={} errors={}".format(
                    prefix, r.created, r.linked, r.skipped_no_name, r.errors
                )
            )
        )
