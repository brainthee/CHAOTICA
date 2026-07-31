"""Refresh RM-derived fields (state, deliverable, client, links) on all imported RM projects.

Handy after a schema change to backfill fields onto projects imported earlier, without
waiting for each to reappear in a schedule pull.

    python manage.py refresh_rm_projects --dry-run
"""

from django.core.management.base import BaseCommand

from rm_sync.inbound import refresh_rm_projects


class Command(BaseCommand):
    help = "Refresh state/deliverable/client/etc on all imported RM projects."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Report only; write nothing."
        )

    def handle(self, *args, **options):
        r = refresh_rm_projects(dry_run=options["dry_run"])
        prefix = "[DRY RUN] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                "{}checked={} updated={} skipped(ours)={} missing={} errors={}".format(
                    prefix,
                    r["checked"],
                    r["updated"],
                    r["skipped_chaotica"],
                    r["missing"],
                    r["errors"],
                )
            )
        )
