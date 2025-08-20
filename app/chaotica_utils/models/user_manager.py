from django.db import models
from django.contrib.auth.models import UserManager
from django.db.models import (
    Q, Count, Sum, Case, When, Value, IntegerField, 
    DateField, F, Prefetch, Exists, OuterRef
)
from django.db.models.functions import TruncDate
from datetime import timedelta, datetime
import json
from django.utils import timezone
from collections import defaultdict
from constance import config


class CustomUserQuerySet(models.QuerySet):
    def get_default_order(self):
        return self.order_by("first_name", "last_name")


class CustomUserManager(UserManager):

    def get_queryset(self):
        return CustomUserQuerySet(self.model, using=self._db)
    
    def get_default_order(self):
        return self.get_queryset().get_default_order()
        
    def calculate_bulk_utilization(self, user_queryset, start_date, end_date, org=None):
        """
        Calculate utilization statistics for multiple users efficiently.
        
        Args:
            user_queryset: QuerySet of users to analyze
            start_date: datetime object for the start of the period
            end_date: datetime object for the end of the period
            org: Optional organizational unit for working days
            
        Returns:
            dict: {
                'summary': aggregate statistics across all users,
                'by_user': detailed breakdown per user
            }
        """
        from chaotica_utils.models import Holiday
        from jobtracker.models import TimeSlot
        from jobtracker.enums import PhaseStatuses
        
        # Ensure timezone-aware datetimes
        if not start_date.tzinfo:
            start_date = timezone.make_aware(
                datetime.combine(start_date, datetime.min.time())
            )
        if not end_date.tzinfo:
            end_date = timezone.make_aware(
                datetime.combine(end_date, datetime.max.time())
            )
        
        # Prefetch user data with required relationships
        users = user_queryset.select_related(
            'manager', 'acting_manager'
        ).prefetch_related(
            'unit_memberships__unit'
        )
        
        # Get working days configuration
        if org:
            working_days = org.businessHours_days
        else:
            working_days = json.loads(config.DEFAULT_WORKING_DAYS)
        
        # Fetch all holidays for relevant countries in one query
        user_countries = users.values_list('country', flat=True).distinct()
        holidays_by_country = defaultdict(set)
        
        holidays = Holiday.objects.filter(
            Q(country__in=user_countries) | Q(country__isnull=True),
            date__range=(start_date.date(), end_date.date())
        ).values('country', 'date')
        
        for holiday in holidays:
            country = holiday['country'] or 'ALL'
            holidays_by_country[country].add(holiday['date'])
            if country == 'ALL':
                # Global holidays apply to all countries
                for c in user_countries:
                    holidays_by_country[c].add(holiday['date'])
        
        # Calculate total days and working days
        date_range = []
        current = start_date.date()
        while current <= end_date.date():
            date_range.append(current)
            current += timedelta(days=1)
        
        total_days = len(date_range)
        
        # Fetch all timeslots for all users in one query with annotations
        timeslots = TimeSlot.objects.filter(
            user__in=users,
            start__date__lte=end_date,
            end__date__gte=start_date
        ).select_related(
            'phase', 'user', 'user__unit_memberships', 'user__unit_memberships__unit'
        ).annotate(
            is_tentative=Case(
                When(phase__isnull=False, 
                     phase__status__lt=PhaseStatuses.SCHEDULED_CONFIRMED, 
                     then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            ),
            is_confirmed=Case(
                When(phase__isnull=False,
                     phase__status__gte=PhaseStatuses.SCHEDULED_CONFIRMED,
                     then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            ),
            is_non_delivery=Case(
                When(phase__isnull=True, then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            )
        ).values(
            'user_id',
            'start',
            'end',
            'is_tentative',
            'is_confirmed',
            'is_non_delivery'
        )
        
        # Process timeslots by user
        slots_by_user = defaultdict(list)
        for slot in timeslots:
            slots_by_user[slot['user_id']].append(slot)
        
        # Calculate statistics for each user
        user_stats = {}
        summary_totals = defaultdict(int)
        
        for user in users:
            user_holidays = holidays_by_country.get(user.country, set())
            
            # Calculate working days for this user
            working_days_count = 0
            non_working_days_count = 0
            holiday_days_count = 0
            
            for date in date_range:
                is_holiday = date in user_holidays
                is_working_day = (date.weekday() + 1) in working_days
                
                if is_holiday:
                    holiday_days_count += 1
                elif not is_working_day:
                    non_working_days_count += 1
                else:
                    working_days_count += 1
            
            # Process timeslots for this user
            user_slots = slots_by_user.get(user.pk, [])
            days_with_slots = defaultdict(lambda: {
                'tentative': 0,
                'confirmed': 0,
                'non_delivery': 0
            })
            
            for slot in user_slots:
                # Calculate which days this slot spans
                slot_start = max(slot['start'].date(), start_date.date())
                slot_end = min(slot['end'].date(), end_date.date())
                
                current_date = slot_start
                while current_date <= slot_end:
                    # Skip non-working days and holidays
                    if (current_date.weekday() + 1) in working_days and \
                       current_date not in user_holidays:
                        if slot['is_tentative']:
                            days_with_slots[current_date]['tentative'] = 1
                        if slot['is_confirmed']:
                            days_with_slots[current_date]['confirmed'] = 1
                        if slot['is_non_delivery']:
                            days_with_slots[current_date]['non_delivery'] = 1
                    current_date += timedelta(days=1)
            
            # Count days by type
            scheduled_days = len(days_with_slots)
            tentative_days = sum(1 for d in days_with_slots.values() if d['tentative'])
            confirmed_days = sum(1 for d in days_with_slots.values() if d['confirmed'])
            non_delivery_days = sum(1 for d in days_with_slots.values() if d['non_delivery'])
            available_days = working_days_count - scheduled_days
            
            # Calculate percentages
            def safe_percentage(numerator, denominator):
                return round((numerator / denominator * 100), 2) if denominator > 0 else 0
            
            user_data = {
                'user_id': user.pk,
                'user_email': user.email,
                'user_name': str(user),
                'user': user,
                'main_org': user.unit_memberships.first(),
                'total_days': total_days,
                'working_days': working_days_count,
                'non_working_days': non_working_days_count,
                'holiday_days': holiday_days_count,
                'available_days': available_days,
                'scheduled_days': scheduled_days,
                'tentative_days': tentative_days,
                'confirmed_days': confirmed_days,
                'non_delivery_days': non_delivery_days,
                'working_percentage': safe_percentage(
                    working_days_count, 
                    total_days - non_working_days_count
                ),
                'utilisation_percentage': safe_percentage(confirmed_days, working_days_count),
                'confirmed_percentage': safe_percentage(confirmed_days, working_days_count),
                'tentative_percentage': safe_percentage(tentative_days, working_days_count),
                'non_delivery_percentage': safe_percentage(non_delivery_days, working_days_count),
                'available_percentage': safe_percentage(available_days, working_days_count),
            }
            
            user_stats[user.pk] = user_data
            
            # Add to summary totals
            for key in ['working_days', 'available_days', 'scheduled_days', 
                       'tentative_days', 'confirmed_days', 'non_delivery_days']:
                summary_totals[key] += user_data[key]
        
        # Calculate summary statistics
        num_users = len(users)
        total_working_days = summary_totals['working_days']
        
        summary = {
            'num_users': num_users,
            'total_days': total_days,
            'avg_working_days': round(summary_totals['working_days'] / num_users, 2) if num_users > 0 else 0,
            'total_available_days': summary_totals['available_days'],
            'total_scheduled_days': summary_totals['scheduled_days'],
            'total_tentative_days': summary_totals['tentative_days'],
            'total_confirmed_days': summary_totals['confirmed_days'],
            'total_non_delivery_days': summary_totals['non_delivery_days'],
            'avg_utilisation_percentage': round(
                (summary_totals['confirmed_days'] / total_working_days * 100), 2
            ) if total_working_days > 0 else 0,
            'avg_available_percentage': round(
                (summary_totals['available_days'] / total_working_days * 100), 2
            ) if total_working_days > 0 else 0,
        }
        
        return {
            'summary': summary,
            'by_user': user_stats,
            'date_range': {
                'start': start_date,
                'end': end_date
            }
        }
    
    def get_bulk_stats(self, user_queryset, start_date=None, end_date=None, org=None):
        """
        Get comprehensive stats for multiple users efficiently.
        
        Args:
            user_queryset: QuerySet of users
            start_date: Start date for analysis (defaults to 30 days ago)
            end_date: End date for analysis (defaults to today)
            org: Optional organizational unit
            
        Returns:
            dict: Statistics including utilization and upcoming availability
        """
        from datetime import timedelta
        from django.utils import timezone
        from ..enums import UpcomingAvailabilityRanges
        
        # Set default dates if not provided
        if not start_date:
            start_date = timezone.now() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now()
        
        # Ensure correct date ordering
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        
        # Make timezone-aware
        start_date = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )
        end_date = timezone.make_aware(
            datetime.combine(end_date, datetime.max.time())
        )
        
        # Get current utilization
        current_utilization = self.calculate_bulk_utilization(
            user_queryset, start_date, end_date, org
        )
        
        # Calculate upcoming availability for different ranges
        upcoming_availability = {}
        avail_start = timezone.now() - timedelta(days=timezone.now().weekday())
        
        for range_name, days_ahead in UpcomingAvailabilityRanges.DEFAULT.items():
            avail_end = avail_start + timedelta(days=days_ahead)
            upcoming_availability[range_name] = self.calculate_bulk_utilization(
                user_queryset, avail_start, avail_end, org
            )
        
        return {
            'current': current_utilization,
            'upcoming_availability': upcoming_availability,
            'org': org,
            'user_count': user_queryset.count()
        }
    
    def get_team_availability_summary(self, user_queryset, weeks_ahead=8):
        """
        Get a week-by-week availability summary for a team.
        
        Args:
            user_queryset: QuerySet of users
            weeks_ahead: Number of weeks to look ahead
            
        Returns:
            list: Weekly availability data
        """
        from django.utils import timezone
        
        weekly_data = []
        start_date = timezone.now().date()
        start_date = start_date - timedelta(days=start_date.weekday())  # Start of week
        
        for week in range(weeks_ahead):
            week_start = start_date + timedelta(weeks=week)
            week_end = week_start + timedelta(days=6)
            
            week_stats = self.calculate_bulk_utilization(
                user_queryset, week_start, week_end
            )
            
            weekly_data.append({
                'week_start': week_start,
                'week_end': week_end,
                'week_number': week_start.isocalendar()[1],
                'year': week_start.year,
                'summary': week_stats['summary']
            })
        
        return weekly_data