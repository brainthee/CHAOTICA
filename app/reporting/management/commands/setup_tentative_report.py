"""
Create (idempotently) the "Tentative Projects" report definition.

This is the report behind the weekly tentative-projects chaser email. It is a
pure data definition on the generic Phase data area - no bespoke report code -
so it can equally be built or tweaked by hand in the report wizard. Shipping it
as a command just makes it reproducible across environments.

Run ``setup_reporting_models`` first so the Phase data fields (including the
computed resolver fields) exist.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from reporting.models import (
    DataArea, DataField, FilterType, Report, ReportField, ReportFilter, ReportSort,
)
from jobtracker.enums import PhaseStatuses
from chaotica_utils.models import User

REPORT_NAME = "Tentative Projects"

# (field_path, custom_label) in display order - matches the chaser email table.
COLUMNS = [
    ("job__client__name", "Client"),
    ("job__id", "CHAOTICA ID"),
    ("title", "Project Name"),
    ("resolver:project_manager", "Project Manager"),
    ("service__name", "Project Type"),
    ("resolver:assigned_engineers", "Assigned To"),
    ("resolver:start_date", "Start Date"),
    ("resolver:days_testing", "Days Testing"),
    ("resolver:days_reporting", "Days Reporting"),
]


class Command(BaseCommand):
    help = 'Create or refresh the "Tentative Projects" report definition.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--owner',
            type=str,
            help='Email of the user to own the report (defaults to the first superuser).',
        )
        parser.add_argument(
            '--window-days',
            type=int,
            default=30,
            help='Rolling window length in days from today (default: 30).',
        )

    def handle(self, *args, **options):
        try:
            data_area = DataArea.objects.get(name='Phases')
        except DataArea.DoesNotExist:
            raise CommandError("Phase data area not found - run 'setup_reporting_models' first.")

        owner = self._resolve_owner(options.get('owner'))
        window = options['window_days']

        def field(path):
            try:
                return data_area.fields.get(field_path=path)
            except DataField.DoesNotExist:
                raise CommandError(
                    f"DataField '{path}' missing - run 'setup_reporting_models' first."
                )

        exact = FilterType.objects.filter(operator='exact', name='Equals').first()
        gte = FilterType.objects.filter(operator='gte').first()
        lte = FilterType.objects.filter(operator='lte').first()
        if not (exact and gte and lte):
            raise CommandError("Filter types missing - run 'setup_reporting_core' first.")

        with transaction.atomic():
            report, created = Report.objects.get_or_create(
                name=REPORT_NAME,
                owner=owner,
                defaults={
                    'description': 'Phases whose schedule is still tentative within a rolling window.',
                    'data_area': data_area,
                    'presentation_type': 'html',
                    'is_private': False,
                },
            )
            if not created:
                report.data_area = data_area
                report.presentation_type = 'html'
                report.is_private = False
                report.save()

            # Rebuild columns/filters/sorts so re-running reflects the latest definition.
            report.fields.all().delete()
            report.filters.all().delete()
            report.sorts.all().delete()

            for position, (path, label) in enumerate(COLUMNS):
                ReportField.objects.create(
                    report=report, data_field=field(path),
                    position=position, custom_label=label,
                )

            ReportFilter.objects.create(
                report=report, data_field=field('status'), filter_type=exact,
                value=str(PhaseStatuses.SCHEDULED_TENTATIVE), position=0,
            )
            ReportFilter.objects.create(
                report=report, data_field=field('_start_date'), filter_type=gte,
                value='today', position=1,
            )
            ReportFilter.objects.create(
                report=report, data_field=field('_start_date'), filter_type=lte,
                value=f'today+{window}d', position=2,
            )

            ReportSort.objects.create(
                report=report, data_field=field('job__client__name'), direction='asc', position=0,
            )
            ReportSort.objects.create(
                report=report, data_field=field('_start_date'), direction='asc', position=1,
            )

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f"{action} report '{REPORT_NAME}' (owner={owner}, window={window}d, uuid={report.uuid})"
        ))

    def _resolve_owner(self, email):
        if email:
            try:
                return User.objects.get(email=email)
            except User.DoesNotExist:
                raise CommandError(f"No user with email '{email}'.")
        owner = User.objects.filter(is_superuser=True).order_by('pk').first()
        if not owner:
            raise CommandError("No superuser found - pass --owner <email>.")
        return owner
