from django.core.management.base import BaseCommand

from notifications.seed_email_templates import seed_email_templates


class Command(BaseCommand):
    help = 'Seed/refresh EmailTemplate rows from the filesystem email templates.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help='Overwrite templates even if an admin has customised them.',
        )

    def handle(self, *args, **options):
        summary = seed_email_templates(force=options['force'], stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS(
            f"Done. Created {summary['created']}, updated {summary['updated']}, "
            f"skipped {summary['skipped']}, missing {summary['missing']}."
        ))
