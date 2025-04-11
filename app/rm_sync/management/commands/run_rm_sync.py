from django.core.management.base import BaseCommand
from constance import config
from ...models import *


class Command(BaseCommand):
    help = "Run a main sync process for RM"

    def handle(self, *args, **options):
        self.stdout.write("Starting RM sync")

        if not config.RM_SYNC_ENABLED:
            self.stdout.write(self.style.ERROR("RMSync not enabled"))
            return

        for sync_record in RMSyncRecord.objects.filter(sync_enabled=True):
            self.stdout.write(self.style.NOTICE(f"Processing {str(sync_record)}"))
            sync_record.sync_records(
                start_date=timezone.datetime(2024, 9, 1).date(),
                end_date=(timezone.now() + timedelta(days=365)).date(),
            )

        self.stdout.write(self.style.SUCCESS("RM Sync finished"))
