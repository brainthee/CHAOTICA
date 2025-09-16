# management/commands/fix_escaped_html.py
from django.core.management.base import BaseCommand
from django.db import transaction
from html import unescape
from jobtracker.models.phase import Phase

class Command(BaseCommand):
    help = 'Fix escaped HTML in BleachField fields'

    def handle(self, *args, **options):
        fields_to_fix = [
            "location", 
            "test_target",
            "comm_reqs",
            "restrictions",
            "scheduling_requirements",
            "prerequisites",
        ] 
        
        with transaction.atomic():
            phases = Phase.objects.all()
            fixed_count = 0
            
            for phase in phases:
                updated = False
                
                for field_name in fields_to_fix:
                    field_value = getattr(phase, field_name)
                    
                    # Check if field contains escaped HTML
                    if field_value and ('&lt;' in field_value or '&gt;' in field_value or '&amp;' in field_value):
                        # Unescape the HTML
                        unescaped = unescape(field_value)
                        setattr(phase, field_name, unescaped)
                        updated = True
                        self.stdout.write(f"Fixing {field_name} for Phase {phase.id}")
                
                if updated:
                    phase.save()
                    fixed_count += 1
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully fixed {fixed_count} phases')
            )