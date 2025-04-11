from django.core.management.base import BaseCommand
from constance import config
from ...models import *

class Command(BaseCommand):
    help = 'Clear RM assignable data from CHAOTICA and RM'

    def handle(self, *args, **options):
        self.stdout.write('Clearing RM data...')

        if not config.RM_SYNC_ENABLED:
            self.stdout.write(self.style.ERROR('RMSync not enabled'))
            return
            
        for sync_record in RMAssignableSlot.objects.all():
            self.stdout.write(self.style.NOTICE(f"Processing slot {str(sync_record)}"))
            sync_record.delete_in_rm()
            sync_record.delete()
        for sync_record in RMAssignable.objects.all():
            self.stdout.write(self.style.NOTICE(f"Processing assignable {str(sync_record)}"))
            sync_record.delete_in_rm()
            sync_record.delete()
            
            
        self.stdout.write(self.style.SUCCESS('RM data cleared'))
    