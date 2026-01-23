import csv
import sys
from datetime import datetime, timedelta, date
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Prefetch
from django.utils import timezone
from jobtracker.models import Job, TimeSlot, Client
from jobtracker.enums import JobStatuses
from typing import List, Tuple, Union


class Command(BaseCommand):
    help = 'Generate a weekly aggregation report showing active projects and consultants for a specific client'

    def add_arguments(self, parser):
        # Client identification (one required)
        client_group = parser.add_mutually_exclusive_group(required=True)
        client_group.add_argument(
            '--client-id',
            type=int,
            help='Client ID to generate report for'
        )
        client_group.add_argument(
            '--client-name',
            type=str,
            help='Client name to generate report for (case-insensitive)'
        )

        # Date range (both required)
        parser.add_argument(
            '--start-date',
            type=str,
            required=True,
            help='Start date for report (YYYY-MM-DD format)'
        )
        parser.add_argument(
            '--end-date',
            type=str,
            required=True,
            help='End date for report (YYYY-MM-DD format)'
        )

        # Optional output file
        parser.add_argument(
            '--output',
            type=str,
            help='Output CSV file path (defaults to stdout)'
        )

        # Verbose flag
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output for debugging'
        )

    def handle(self, *args, **options):
        # Extract and validate arguments
        client_id = options.get('client_id')
        client_name = options.get('client_name')
        start_date_str = options['start_date']
        end_date_str = options['end_date']
        output_file = options.get('output')
        verbose = options['verbose']

        # Parse and validate dates
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            raise CommandError(f'Invalid start date format: {start_date_str}. Expected YYYY-MM-DD')

        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            raise CommandError(f'Invalid end date format: {end_date_str}. Expected YYYY-MM-DD')

        if start_date > end_date:
            raise CommandError(f'Start date ({start_date}) must be before or equal to end date ({end_date})')

        # Look up client
        try:
            if client_id:
                client = Client.objects.get(id=client_id)
                if verbose:
                    self.stdout.write(f'Found client by ID: {client.name} (ID: {client.id})')
            else:
                client = Client.objects.get(name__iexact=client_name)
                if verbose:
                    self.stdout.write(f'Found client by name: {client.name} (ID: {client.id})')
        except Client.DoesNotExist:
            if client_id:
                raise CommandError(f'Client with ID {client_id} not found')
            else:
                raise CommandError(f'Client with name "{client_name}" not found')

        if verbose:
            self.stdout.write(f'Generating report for: {client.name}')
            self.stdout.write(f'Date range: {start_date} to {end_date}')

        # Convert dates to datetime for query (start of day and end of day)
        start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        end_datetime = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

        # Build efficient query with prefetch
        jobs = Job.objects.filter(
            client=client,
            # status__in=JobStatuses.ACTIVE_STATUSES
        ).prefetch_related(
            Prefetch(
                'phases__timeslots',
                queryset=TimeSlot.objects.filter(
                    start__lte=end_datetime,
                    end__gte=start_datetime
                ).select_related('user')
            )
        ).prefetch_related('phases')

        if verbose:
            self.stdout.write(f'Found {jobs.count()} active jobs for {client.name}')

        # Count total timeslots in range for verbose output
        if verbose:
            total_timeslots = sum(
                sum(phase.timeslots.count() for phase in job.phases.all())
                for job in jobs
            )
            self.stdout.write(f'Found {total_timeslots} timeslots in date range')

        # Generate week boundaries and aggregate data
        weeks_data = self.generate_weekly_aggregation(jobs, start_date, end_date)

        # Generate CSV output
        self.generate_csv_output(weeks_data, output_file, verbose)

        if verbose:
            self.stdout.write(self.style.SUCCESS('Report generation complete!'))

    DateLike = Union[date, datetime]

    def get_week_boundaries(self, start_date: DateLike, end_date: DateLike) -> List[Tuple[date, date]]:
        """
        Generate (week_start, week_end) tuples for ISO weeks.
        Weeks run Monday-Sunday (inclusive).
        Tuples are clipped to the provided [start_date, end_date] range.
        """
        # Normalize to `date` (avoids aware/naive datetime comparison issues)
        if isinstance(start_date, datetime):
            start_date = start_date.date()
        if isinstance(end_date, datetime):
            end_date = end_date.date()

        if start_date > end_date:
            return []

        weeks: List[Tuple[date, date]] = []

        # Find the Monday of the week containing start_date
        current_week_start = start_date - timedelta(days=start_date.weekday())  # Mon=0..Sun=6

        while current_week_start <= end_date:
            current_week_end = current_week_start + timedelta(days=6)  # Sunday

            # Clip to actual date range
            week_start = max(current_week_start, start_date)
            week_end = min(current_week_end, end_date)

            weeks.append((week_start, week_end))

            # Move to next Monday
            current_week_start += timedelta(days=7)

        return weeks

    def is_timeslot_in_week(self, timeslot, week_start, week_end):
        """
        Check if a timeslot overlaps with the given week boundary.
        Convert datetime to date for comparison.
        """
        slot_start_date = timeslot.start.date()
        slot_end_date = timeslot.end.date()

        # Check for overlap: slot starts before week ends AND slot ends after week starts
        return slot_start_date <= week_end and slot_end_date >= week_start

    def generate_weekly_aggregation(self, jobs, start_date, end_date):
        """
        Generate weekly aggregation data for all weeks in the date range.
        Returns a list of dicts with week_start, week_end, active_jobs, consultants_scheduled.
        """
        weeks = self.get_week_boundaries(start_date, end_date)
        weeks_data = []

        for week_start, week_end in weeks:
            active_jobs_in_week = set()
            active_phases_in_week = set()
            consultants_in_week = set()

            # Iterate through all jobs and their phases
            for job in jobs:
                job_has_timeslot_this_week = False

                for phase in job.phases.all():
                    for timeslot in phase.timeslots.all():
                        if self.is_timeslot_in_week(timeslot, week_start, week_end):
                            job_has_timeslot_this_week = True
                            consultants_in_week.add(timeslot.user.id)
                            active_phases_in_week.add(phase.id)

                if job_has_timeslot_this_week:
                    active_jobs_in_week.add(job.id)

            weeks_data.append({
                'week_start': week_start,
                'week_end': week_end,
                'active_jobs': len(active_jobs_in_week),
                'active_phases': len(active_phases_in_week),
                'consultants_scheduled': len(consultants_in_week)
            })

        return weeks_data

    def generate_csv_output(self, weeks_data, output_file, verbose):
        """
        Generate CSV output from weekly aggregation data.
        Writes to file if output_file is provided, otherwise to stdout.
        """
        # Determine output destination
        if output_file:
            try:
                output = open(output_file, 'w', newline='')
                if verbose:
                    self.stdout.write(f'Writing report to: {output_file}')
            except IOError as e:
                raise CommandError(f'Could not open output file {output_file}: {e}')
        else:
            output = sys.stdout
            if verbose:
                self.stdout.write('Writing report to stdout')

        try:
            writer = csv.writer(output)

            # Write header
            writer.writerow([
                'Week Start Date',
                'Week End Date',
                'Active Jobs',
                'Active Phases',
                'Consultants Scheduled'
            ])

            # Write data rows
            for week in weeks_data:
                writer.writerow([
                    week['week_start'].strftime('%Y-%m-%d'),
                    week['week_end'].strftime('%Y-%m-%d'),
                    week['active_jobs'],
                    week['active_phases'],
                    week['consultants_scheduled']
                ])

            # Write summary row if we have data
            if weeks_data:
                total_weeks = len(weeks_data)
                avg_projects = sum(w['active_jobs'] for w in weeks_data) / total_weeks
                avg_phases = sum(w['active_phases'] for w in weeks_data) / total_weeks
                avg_consultants = sum(w['consultants_scheduled'] for w in weeks_data) / total_weeks

                writer.writerow([])  # Empty row for separation
                writer.writerow(['Summary', '', '', ''])
                writer.writerow(['Total Weeks', total_weeks, '', ''])
                writer.writerow(['Average Active Projects', f'{avg_projects:.2f}', '', ''])
                writer.writerow(['Average Consultants Scheduled', f'{avg_consultants:.2f}', '', ''])

        finally:
            if output_file:
                output.close()
