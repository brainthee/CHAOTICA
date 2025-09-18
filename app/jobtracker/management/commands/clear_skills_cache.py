from django.core.management.base import BaseCommand
from django.core.cache import cache
import hashlib


class Command(BaseCommand):
    help = 'Clear the skills matrix cache'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Clear all cache (not just skills matrix)',
        )
        parser.add_argument(
            '--pattern',
            type=str,
            help='Clear cache keys matching a pattern (requires Redis cache backend)',
        )

    def handle(self, *args, **options):
        if options['all']:
            # Clear all cache
            cache.clear()
            self.stdout.write(self.style.SUCCESS('Successfully cleared all cache'))
        else:
            # Clear skills matrix specific cache
            cache.delete('skill_matrix_filter_options')
            self.stdout.write(self.style.SUCCESS('Cleared skill matrix filter options cache'))

            # Try to clear pattern-based keys if using Redis
            try:
                from django_redis import get_redis_connection
                con = get_redis_connection("default")

                if options['pattern']:
                    pattern = options['pattern']
                else:
                    pattern = "skill_matrix_*"

                # Find and delete all matching keys
                keys = con.keys(pattern)
                if keys:
                    con.delete(*keys)
                    self.stdout.write(self.style.SUCCESS(f'Cleared {len(keys)} cache keys matching "{pattern}"'))
                else:
                    self.stdout.write(self.style.WARNING(f'No cache keys found matching "{pattern}"'))

            except ImportError:
                self.stdout.write(self.style.WARNING('Redis cache backend not available. Only cleared known keys.'))
                self.stdout.write(self.style.WARNING('To clear all matrix caches, use --all flag or switch to Redis cache backend.'))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'Could not clear pattern-based cache: {e}'))

        self.stdout.write(self.style.SUCCESS('\nCache clearing complete!'))