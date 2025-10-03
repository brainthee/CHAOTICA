from django.core.management.base import BaseCommand
from constance import config


class Command(BaseCommand):
    help = 'Toggle or set maintenance mode'

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            nargs='?',
            choices=['on', 'off', 'toggle', 'status'],
            default='status',
            help='Action to perform: on, off, toggle, or status (default: status)',
        )

    def handle(self, *args, **options):
        action = options['action']

        if action == 'on':
            config.MAINTENANCE_MODE = True
            self.stdout.write(self.style.SUCCESS('Maintenance mode enabled'))
        elif action == 'off':
            config.MAINTENANCE_MODE = False
            self.stdout.write(self.style.SUCCESS('Maintenance mode disabled'))
        elif action == 'toggle':
            config.MAINTENANCE_MODE = not config.MAINTENANCE_MODE
            status = 'enabled' if config.MAINTENANCE_MODE else 'disabled'
            self.stdout.write(self.style.SUCCESS(f'Maintenance mode toggled: {status}'))
        elif action == 'status':
            status = 'enabled' if config.MAINTENANCE_MODE else 'disabled'
            self.stdout.write(f'Maintenance mode is currently: {status}')
