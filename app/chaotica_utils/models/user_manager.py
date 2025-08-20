from django.db import models
from django.contrib.auth.models import UserManager
from django.db.models import (
    Q, Count, Sum, Case, When, Value, IntegerField, 
    DateField, F, Prefetch, Exists, OuterRef, BooleanField
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
        from .user import User
        
        # Ensure timezone-aware datetimes
        if not start_date.tzinfo:
            start_date = timezone.make_aware(
                datetime.combine(start_date, datetime.min.time())
            )
        if not end_date.tzinfo:
            end_date = timezone.make_aware(
                datetime.combine(end_date, datetime.max.time())
            )
        
        # Get user IDs upfront to avoid repeated queries
        user_ids = list(user_queryset.values_list('id', flat=True))
        
        # Clear any existing prefetch_related to avoid conflicts
        # Then prefetch all users with their relationships in a single query
        users = User.objects.filter(id__in=user_ids).select_related(
            'manager', 'acting_manager'
        ).prefetch_related(
            'unit_memberships__unit'
        )
        
        # Build user lookup dictionary
        user_dict = {user.id: user for user in users}
        
        # Get working days configuration
        if org:
            working_days = org.businessHours_days
        else:
            working_days = json.loads(config.DEFAULT_WORKING_DAYS)
        
        # Get unique countries for all users
        user_countries = users.values_list('country', flat=True).distinct()
        
        # Fetch ALL holidays in a single query
        holidays = Holiday.objects.filter(
            Q(country__in=user_countries) | Q(country__isnull=True),
            date__range=(start_date.date(), end_date.date())
        ).values('country', 'date')
        
        # Build holiday lookup by country
        holidays_by_country = defaultdict(set)
        global_holidays = set()
        
        for holiday in holidays:
            if holiday['country'] is None:
                global_holidays.add(holiday['date'])
            else:
                holidays_by_country[holiday['country']].add(holiday['date'])
        
        # Add global holidays to all countries
        for country in user_countries:
            holidays_by_country[country].update(global_holidays)
        
        # Generate date range
        date_range = []
        current = start_date.date()
        while current <= end_date.date():
            date_range.append(current)
            current += timedelta(days=1)
        
        total_days = len(date_range)
        
        # Fetch ALL timeslots in a SINGLE query with proper annotations
        timeslots = TimeSlot.objects.filter(
            user_id__in=user_ids,
            start__date__lte=end_date.date(),
            end__date__gte=start_date.date()
        ).select_related(
            'phase'
        ).annotate(
            is_tentative=Case(
                When(phase__isnull=False, 
                     phase__status__lt=PhaseStatuses.SCHEDULED_CONFIRMED, 
                     then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            ),
            is_confirmed=Case(
                When(phase__isnull=False,
                     phase__status__gte=PhaseStatuses.SCHEDULED_CONFIRMED,
                     then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            ),
            is_non_delivery=Case(
                When(phase__isnull=True, then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            )
        ).values(
            'user_id',
            'start',
            'end',
            'is_tentative',
            'is_confirmed',
            'is_non_delivery'
        )
        
        # Group timeslots by user_id in memory
        slots_by_user = defaultdict(list)
        for slot in timeslots:
            slots_by_user[slot['user_id']].append(slot)
        
        # Process statistics for each user
        user_stats = {}
        summary_totals = defaultdict(int)
        
        for user_id in user_ids:
            user = user_dict[user_id]
            user_holidays = holidays_by_country.get(user.country, set())
            user_holidays.update(global_holidays)
            
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
            user_slots = slots_by_user.get(user_id, [])
            days_with_slots = defaultdict(lambda: {
                'tentative': False,
                'confirmed': False,
                'non_delivery': False
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
                            days_with_slots[current_date]['tentative'] = True
                        if slot['is_confirmed']:
                            days_with_slots[current_date]['confirmed'] = True
                        if slot['is_non_delivery']:
                            days_with_slots[current_date]['non_delivery'] = True
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
                'user_id': user.id,
                'user': user,
                'user_email': user.email,
                'user_name': str(user),
                'main_org': user.unit_memberships.first().unit,
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
            
            user_stats[user.id] = user_data
            
            # Add to summary totals
            for key in ['working_days', 'available_days', 'scheduled_days', 
                       'tentative_days', 'confirmed_days', 'non_delivery_days']:
                summary_totals[key] += user_data[key]
        
        # Calculate summary statistics
        num_users = len(user_ids)
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
        if isinstance(start_date, datetime):
            if not start_date.tzinfo:
                start_date = timezone.make_aware(start_date)
        else:
            start_date = timezone.make_aware(
                datetime.combine(start_date, datetime.min.time())
            )
            
        if isinstance(end_date, datetime):
            if not end_date.tzinfo:
                end_date = timezone.make_aware(end_date)
        else:
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
        
        # Calculate the maximum date range needed
        max_days_ahead = max(UpcomingAvailabilityRanges.DEFAULT.values())
        max_end_date = avail_start + timedelta(days=max_days_ahead)
        
        # Get ALL data for the maximum range in one go
        all_range_data = self.calculate_bulk_utilization(
            user_queryset, avail_start, max_end_date, org
        )
        
        # Now calculate stats for each sub-range using the already fetched data
        for range_name, days_ahead in UpcomingAvailabilityRanges.DEFAULT.items():
            avail_end = avail_start + timedelta(days=days_ahead)
            # For efficiency, you could recalculate just the date range portion
            # but for now, let's call the method (it will reuse cached data if implemented)
            upcoming_availability[range_name] = self.calculate_bulk_utilization(
                user_queryset, avail_start, avail_end, org
            )
        
        return {
            'current': current_utilization,
            'upcoming_availability': upcoming_availability,
            'org': org,
            'user_count': len(current_utilization['by_user'])
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
        
        # Calculate all weeks in one batch if possible
        end_date = start_date + timedelta(weeks=weeks_ahead)
        
        # Get all data for the entire period
        full_period_stats = self.calculate_bulk_utilization(
            user_queryset, start_date, end_date
        )
        
        # Break down by week (this is simplified - you might want to recalculate per week)
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
    
    def prefetch_for_stats(self, queryset):
        """
        Helper method to prefetch all necessary related data for stats calculation.
        Returns an optimized queryset.
        """
        # Clear any existing prefetch configurations to avoid conflicts
        # by using only() to create a fresh queryset
        return queryset.only(
            'id', 'email', 'first_name', 'last_name', 'country', 
            'is_active', 'manager_id', 'acting_manager_id'
        ).select_related(
            'manager',
            'acting_manager'
        ).prefetch_related(
            'unit_memberships__unit'
        )