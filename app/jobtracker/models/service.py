from django.db import models
from ..enums import JobStatuses, PhaseStatuses, FeedbackType, LinkType, UserSkillRatings
from ..models.skill import Skill, UserSkill
from ..models.phase import Phase
from django.conf import settings
from django.db.models import Q
from chaotica_utils.utils import unique_slug_generator
from django.urls import reverse
from simple_history.models import HistoricalRecords
from django.db.models import JSONField
from django_bleach.models import BleachField
from django.db.models.functions import Lower
from chaotica_utils.models import User


class Service(models.Model):
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(null=False, default="", unique=True)
    owners = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, limit_choices_to={"is_active": True},
        help_text="Users responsible for the management of the service."
    )
    history = HistoricalRecords()

    description = BleachField(
        blank=True,
        null=True,
        help_text="Description of service",
    )

    link = models.URLField(
        max_length=2000,
        default="",
        null=True,
        blank=True,
        help_text="Link to service information",
    )

    skillsRequired = models.ManyToManyField(
        Skill, blank=True, related_name="services_skill_required",
        help_text="Skills required to perform this service",
    )
    skillsDesired = models.ManyToManyField(
        Skill, blank=True, related_name="services_skill_desired",
        help_text="Skills desired but not essential",
    )
    is_core = models.BooleanField(
        "Is Core Service", help_text="If checked, this service is considered critical",
        default=False
    )
    data = JSONField(verbose_name="Data", null=True, blank=True, default=dict)

    class Meta:
        ordering = [Lower("name")]
        permissions = (("assign_to_phase", "Assign To Phase"),)

    def __str__(self):
        return self.name

    def can_conduct(self):
        # Return users who have a userskill
        return User.objects.filter(
            skills__in=UserSkill.objects.filter(
                Q(rating=UserSkillRatings.CAN_DO_WITH_SUPPORT),
                skill__in=self.skillsRequired.all(),
            )
        )

    def can_lead(self):
        # Return users who have a userskill
        return User.objects.filter(
            skills__in=UserSkill.objects.filter(
                Q(rating=UserSkillRatings.SPECIALIST)
                | Q(rating=UserSkillRatings.CAN_DO_ALONE), 
                skill__in=self.skillsRequired.all(),
            )
        )

    def get_absolute_url(self):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
            self.save()
        return reverse("service_detail", kwargs={"slug": self.slug})

    def get_users_specialist(self):
        """Get users who are specialists in ALL required skills - optimized"""
        from django.db.models import Count, Q
        required_skills_count = self.skillsRequired.count()
        if not required_skills_count:
            return User.objects.none()

        return User.objects.filter(
            skills__skill__in=self.skillsRequired.all(),
            skills__rating=UserSkillRatings.SPECIALIST
        ).annotate(
            specialist_count=Count('skills', filter=Q(
                skills__skill__in=self.skillsRequired.all(),
                skills__rating=UserSkillRatings.SPECIALIST
            ))
        ).filter(specialist_count=required_skills_count).distinct()

    def get_users_can_do_alone(self):
        """Get users who can do the service independently - optimized"""
        from django.db.models import Count, Q
        required_skills_count = self.skillsRequired.count()
        if not required_skills_count:
            return User.objects.none()

        return User.objects.filter(
            skills__skill__in=self.skillsRequired.all(),
            skills__rating__in=[UserSkillRatings.SPECIALIST, UserSkillRatings.CAN_DO_ALONE]
        ).annotate(
            independent_count=Count('skills', filter=Q(
                skills__skill__in=self.skillsRequired.all(),
                skills__rating__in=[UserSkillRatings.SPECIALIST, UserSkillRatings.CAN_DO_ALONE]
            ))
        ).filter(independent_count=required_skills_count).distinct()

    def get_users_can_do_with_support(self):
        """Get users who have ALL required skills but need support - optimized"""
        from django.db.models import Count, Q
        required_skills_count = self.skillsRequired.count()
        if not required_skills_count:
            return User.objects.none()

        # Users who have all required skills
        users_with_all_skills = User.objects.filter(
            skills__skill__in=self.skillsRequired.all()
        ).annotate(
            total_skills_count=Count('skills', filter=Q(skills__skill__in=self.skillsRequired.all()))
        ).filter(total_skills_count=required_skills_count)

        # Of those, find users who have at least one skill requiring support
        return users_with_all_skills.filter(
            skills__skill__in=self.skillsRequired.all(),
            skills__rating=UserSkillRatings.CAN_DO_WITH_SUPPORT
        ).distinct()

    def get_users_missing_skills(self):
        """Get users who have some but not all required skills - optimized"""
        from django.db.models import Count, Q
        required_skills_count = self.skillsRequired.count()
        if not required_skills_count:
            return User.objects.none()

        return User.objects.filter(
            skills__skill__in=self.skillsRequired.all()
        ).annotate(
            partial_skills_count=Count('skills', filter=Q(skills__skill__in=self.skillsRequired.all()))
        ).filter(partial_skills_count__lt=required_skills_count).distinct()

    def get_service_readiness_breakdown(self):
        """Get comprehensive breakdown of service readiness including desired skills - cached and optimized"""
        from django.core.cache import cache
        from django.db.models import Count, Q

        cache_key = f"service_readiness_{self.id}_{self.skillsRequired.count()}_{self.skillsDesired.count()}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        required_skills = self.skillsRequired.all()
        desired_skills = self.skillsDesired.all()

        if not required_skills.exists():
            return {
                'specialists': User.objects.none(),
                'independent_only': User.objects.none(),
                'support_only': User.objects.none(),
                'missing_skills': User.objects.none(),
                'total_capable': 0,
                'desired_skills_analysis': {}
            }

        # Get all users with counts in a single query
        specialists = self.get_users_specialist()
        independent = self.get_users_can_do_alone()
        need_support = self.get_users_can_do_with_support()
        missing_skills = self.get_users_missing_skills()

        # Use exclude to avoid additional queries
        specialist_ids = list(specialists.values_list('id', flat=True))
        independent_ids = list(independent.values_list('id', flat=True))

        independent_only = independent.exclude(id__in=specialist_ids)
        support_only = need_support.exclude(id__in=specialist_ids + independent_ids)

        # Optimize desired skills analysis
        desired_skills_analysis = {}
        if desired_skills.exists():
            # Get all capable users in one query
            capable_user_ids = specialist_ids + list(independent_only.values_list('id', flat=True)) + list(support_only.values_list('id', flat=True))

            if capable_user_ids:
                # Single query to get all skill data
                skill_data = UserSkill.objects.filter(
                    user_id__in=capable_user_ids,
                    skill__in=desired_skills
                ).select_related('skill').values(
                    'skill__id', 'skill__name', 'rating'
                ).annotate(count=Count('id'))

                # Group by skill
                for skill in desired_skills:
                    skill_ratings = [d for d in skill_data if d['skill__id'] == skill.id]

                    total_with_skill = sum(d['count'] for d in skill_ratings)
                    specialists_count = sum(d['count'] for d in skill_ratings if d['rating'] == UserSkillRatings.SPECIALIST)
                    independent_count = sum(d['count'] for d in skill_ratings if d['rating'] == UserSkillRatings.CAN_DO_ALONE)
                    support_count = sum(d['count'] for d in skill_ratings if d['rating'] == UserSkillRatings.CAN_DO_WITH_SUPPORT)

                    desired_skills_analysis[skill] = {
                        'total_with_skill': total_with_skill,
                        'specialists_count': specialists_count,
                        'independent_count': independent_count,
                        'support_count': support_count,
                        'coverage_percentage': round((total_with_skill / len(capable_user_ids) * 100), 1) if capable_user_ids else 0
                    }

        result = {
            'specialists': specialists,
            'independent_only': independent_only,
            'support_only': support_only,
            'missing_skills': missing_skills,
            'total_capable': len(specialist_ids) + independent_only.count() + support_only.count(),
            'desired_skills_analysis': desired_skills_analysis
        }

        # Cache for 5 minutes
        cache.set(cache_key, result, 300)
        return result

    def get_team_by_skill(self):
        """Get team members grouped by skill and competency level"""
        team_data = {}
        for skill in self.skillsRequired.all():
            team_data[skill] = {
                'specialists': UserSkill.objects.filter(
                    skill=skill,
                    rating=UserSkillRatings.SPECIALIST
                ).select_related('user'),
                'independent': UserSkill.objects.filter(
                    skill=skill,
                    rating=UserSkillRatings.CAN_DO_ALONE
                ).select_related('user'),
                'support_needed': UserSkill.objects.filter(
                    skill=skill,
                    rating=UserSkillRatings.CAN_DO_WITH_SUPPORT
                ).select_related('user'),
            }
        return team_data

    def get_service_usage_analytics(self):
        """Get comprehensive analytics about service usage across phases/jobs - optimized and cached"""
        from django.core.cache import cache
        from django.db.models import Count, Sum, Avg, Q, F
        from django.utils import timezone
        from ..enums import PhaseStatuses, JobStatuses
        import datetime

        cache_key = f"service_analytics_{self.id}_{self.phases.count()}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        now = timezone.now()
        current_year = now.year
        last_month = now - datetime.timedelta(days=30)

        # Single query with all the data we need
        phases_qs = self.phases.select_related('job', 'job__client', 'job__unit')

        # Get all analytics in fewer queries - split aggregates to avoid conflicts
        all_phases_data = phases_qs.aggregate(
            total_count=Count('id'),
            active_count=Count('id', filter=Q(status__in=PhaseStatuses.ACTIVE_STATUSES)),
            completed_count=Count('id', filter=Q(status__in=PhaseStatuses.COMPLETE_STATUSES)),
            upcoming_count=Count('id', filter=Q(status__in=PhaseStatuses.PENDING_STATUSES)),
            recent_count=Count('id', filter=Q(actual_start_date__gte=last_month)),
            this_year_count=Count('id', filter=Q(actual_start_date__year=current_year)),
            on_time_count=Count('id', filter=Q(
                status__in=PhaseStatuses.COMPLETE_STATUSES,
                actual_delivery_date__lte=F('desired_delivery_date')
            )),
            delivery_hours=Sum('delivery_hours'),
            reporting_hours=Sum('reporting_hours'),
            mgmt_hours=Sum('mgmt_hours'),
            qa_hours=Sum('qa_hours'),
            oversight_hours=Sum('oversight_hours'),
            debrief_hours=Sum('debrief_hours'),
            contingency_hours=Sum('contingency_hours'),
            other_hours=Sum('other_hours'),
        )

        # Separate query for average duration on completed phases only
        avg_duration_data = phases_qs.filter(
            status__in=PhaseStatuses.COMPLETE_STATUSES
        ).aggregate(avg_duration=Avg('delivery_hours'))

        # Calculate total hours
        total_hours = sum(h for h in [
            all_phases_data['delivery_hours'], all_phases_data['reporting_hours'],
            all_phases_data['mgmt_hours'], all_phases_data['qa_hours'],
            all_phases_data['oversight_hours'], all_phases_data['debrief_hours'],
            all_phases_data['contingency_hours'], all_phases_data['other_hours']
        ] if h is not None)

        # Client and Unit breakdown in single queries
        client_breakdown = phases_qs.values('job__client__name', 'job__client__id').annotate(
            phase_count=Count('id'),
            total_hours=Sum('delivery_hours')
        ).order_by('-phase_count')[:10]  # Limit to top 10

        unit_breakdown = phases_qs.values('job__unit__name', 'job__unit__id').annotate(
            phase_count=Count('id'),
            total_hours=Sum('delivery_hours')
        ).order_by('-phase_count')[:10]  # Limit to top 10

        # Get querysets for template use
        active_phases = phases_qs.filter(status__in=PhaseStatuses.ACTIVE_STATUSES)
        completed_phases = phases_qs.filter(status__in=PhaseStatuses.COMPLETE_STATUSES)
        upcoming_phases = phases_qs.filter(status__in=PhaseStatuses.PENDING_STATUSES)

        result = {
            'total_phases': all_phases_data['total_count'],
            'active_phases': active_phases,
            'completed_phases': completed_phases,
            'upcoming_phases': upcoming_phases,
            'recent_phases': all_phases_data['recent_count'],
            'this_year_phases': all_phases_data['this_year_count'],
            'total_allocated_hours': total_hours,
            'client_breakdown': list(client_breakdown),
            'unit_breakdown': list(unit_breakdown),
            'completion_rate': round((all_phases_data['completed_count'] / all_phases_data['total_count'] * 100), 1) if all_phases_data['total_count'] > 0 else 0,
            'on_time_rate': round((all_phases_data['on_time_count'] / all_phases_data['completed_count'] * 100), 1) if all_phases_data['completed_count'] > 0 else 0,
            'avg_phase_duration': round(avg_duration_data['avg_duration'] or 0, 1),
        }

        # Cache for 10 minutes
        cache.set(cache_key, result, 600)
        return result

    def get_skills_coverage_analysis(self):
        """Comprehensive skills coverage analysis - optimized and cached"""
        from django.core.cache import cache
        from django.db.models import Count, Q, Case, When, IntegerField

        cache_key = f"skills_coverage_{self.id}_{self.skillsRequired.count()}_{self.skillsDesired.count()}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        # Get all users in the system with skills
        all_skilled_users = User.objects.filter(skills__isnull=False).distinct()

        # Analyze required skills coverage
        required_skills_analysis = {}
        for skill in self.skillsRequired.all():
            skill_users = UserSkill.objects.filter(skill=skill).select_related('user')

            # Count by competency level
            competency_breakdown = skill_users.aggregate(
                specialists=Count('id', filter=Q(rating=UserSkillRatings.SPECIALIST)),
                independent=Count('id', filter=Q(rating=UserSkillRatings.CAN_DO_ALONE)),
                support_needed=Count('id', filter=Q(rating=UserSkillRatings.CAN_DO_WITH_SUPPORT))
            )

            total_with_skill = sum(competency_breakdown.values())
            coverage_percentage = round((total_with_skill / all_skilled_users.count() * 100), 1) if all_skilled_users.count() > 0 else 0

            # Find training candidates (users close to having this skill)
            related_skills = Skill.objects.filter(category=skill.category).exclude(id=skill.id)
            training_candidates = User.objects.filter(
                skills__skill__in=related_skills
            ).exclude(
                skills__skill=skill  # Exclude users who already have this skill
            ).annotate(
                related_skills_count=Count('skills', filter=Q(skills__skill__in=related_skills))
            ).filter(related_skills_count__gte=1).distinct()[:5]  # Top 5 candidates

            required_skills_analysis[skill] = {
                'total_users': total_with_skill,
                'specialists': competency_breakdown['specialists'],
                'independent': competency_breakdown['independent'],
                'support_needed': competency_breakdown['support_needed'],
                'coverage_percentage': coverage_percentage,
                'training_candidates': training_candidates,
                'skill_gap': max(0, 3 - competency_breakdown['specialists']),  # Ideal: 3+ specialists
                'critical': competency_breakdown['specialists'] < 2,  # Critical if < 2 specialists
            }

        # Analyze desired skills coverage
        desired_skills_analysis = {}
        for skill in self.skillsDesired.all():
            skill_users = UserSkill.objects.filter(skill=skill).select_related('user')

            competency_breakdown = skill_users.aggregate(
                specialists=Count('id', filter=Q(rating=UserSkillRatings.SPECIALIST)),
                independent=Count('id', filter=Q(rating=UserSkillRatings.CAN_DO_ALONE)),
                support_needed=Count('id', filter=Q(rating=UserSkillRatings.CAN_DO_WITH_SUPPORT))
            )

            total_with_skill = sum(competency_breakdown.values())
            coverage_percentage = round((total_with_skill / all_skilled_users.count() * 100), 1) if all_skilled_users.count() > 0 else 0

            desired_skills_analysis[skill] = {
                'total_users': total_with_skill,
                'specialists': competency_breakdown['specialists'],
                'independent': competency_breakdown['independent'],
                'support_needed': competency_breakdown['support_needed'],
                'coverage_percentage': coverage_percentage,
                'opportunity_score': round((100 - coverage_percentage), 1),  # Higher = more opportunity
            }

        # Overall service coverage metrics
        required_skills_count = self.skillsRequired.count()
        critical_skills = sum(1 for analysis in required_skills_analysis.values() if analysis['critical'])
        avg_required_coverage = round(sum(analysis['coverage_percentage'] for analysis in required_skills_analysis.values()) / required_skills_count, 1) if required_skills_count > 0 else 0

        desired_skills_count = self.skillsDesired.count()
        avg_desired_coverage = round(sum(analysis['coverage_percentage'] for analysis in desired_skills_analysis.values()) / desired_skills_count, 1) if desired_skills_count > 0 else 0

        result = {
            'required_skills_analysis': required_skills_analysis,
            'desired_skills_analysis': desired_skills_analysis,
            'summary': {
                'total_skilled_users': all_skilled_users.count(),
                'required_skills_count': required_skills_count,
                'desired_skills_count': desired_skills_count,
                'critical_skills_count': critical_skills,
                'avg_required_coverage': avg_required_coverage,
                'avg_desired_coverage': avg_desired_coverage,
                'coverage_health': 'Good' if critical_skills == 0 and avg_required_coverage >= 60 else 'Needs Attention' if critical_skills <= 1 else 'Critical'
            }
        }

        # Cache for 15 minutes
        cache.set(cache_key, result, 900)
        return result

    def get_performance_metrics(self):
        """Comprehensive performance metrics and trends - optimized and cached"""
        from django.core.cache import cache
        from django.db.models import Count, Sum, Avg, Q, F, Case, When, IntegerField, DecimalField
        from django.utils import timezone
        from datetime import datetime, timedelta
        import calendar

        cache_key = f"performance_metrics_{self.id}_{self.phases.count()}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        now = timezone.now()
        current_year = now.year
        last_year = current_year - 1

        # Base queryset for completed phases
        completed_phases = self.phases.filter(
            status__in=PhaseStatuses.COMPLETE_STATUSES
        ).select_related('job', 'job__client')

        # Quality and delivery metrics
        quality_metrics = completed_phases.aggregate(
            total_completed=Count('id'),

            # Delivery performance
            on_time_deliveries=Count('id', filter=Q(actual_delivery_date__lte=F('desired_delivery_date'))),
            early_deliveries=Count('id', filter=Q(actual_delivery_date__lt=F('desired_delivery_date'))),
            late_deliveries=Count('id', filter=Q(actual_delivery_date__gt=F('desired_delivery_date'))),

            # Hours analysis
            total_delivery_hours=Sum('delivery_hours'),
            avg_delivery_hours=Avg('delivery_hours'),
            total_qa_hours=Sum('qa_hours'),
            avg_qa_hours=Avg('qa_hours'),

            # Remove efficiency calculation since estimated_hours field doesn't exist
        )

        # Monthly trend analysis for current year
        monthly_trends = []
        for month in range(1, 13):
            month_data = completed_phases.filter(
                actual_delivery_date__year=current_year,
                actual_delivery_date__month=month
            ).aggregate(
                phases_delivered=Count('id'),
                on_time_count=Count('id', filter=Q(actual_delivery_date__lte=F('desired_delivery_date'))),
                total_hours=Sum('delivery_hours'),
                avg_hours=Avg('delivery_hours'),
            )

            on_time_rate = 0
            if month_data['phases_delivered'] > 0:
                on_time_rate = round((month_data['on_time_count'] / month_data['phases_delivered'] * 100), 1)

            monthly_trends.append({
                'month': calendar.month_name[month],
                'month_num': month,
                'phases_delivered': month_data['phases_delivered'] or 0,
                'on_time_rate': on_time_rate,
                'total_hours': month_data['total_hours'] or 0,
                'avg_hours': round(month_data['avg_hours'] or 0, 1),
            })

        # Year-over-year comparison
        current_year_stats = completed_phases.filter(
            actual_delivery_date__year=current_year
        ).aggregate(
            phases=Count('id'),
            on_time=Count('id', filter=Q(actual_delivery_date__lte=F('desired_delivery_date'))),
            total_hours=Sum('delivery_hours'),
        )

        last_year_stats = completed_phases.filter(
            actual_delivery_date__year=last_year
        ).aggregate(
            phases=Count('id'),
            on_time=Count('id', filter=Q(actual_delivery_date__lte=F('desired_delivery_date'))),
            total_hours=Sum('delivery_hours'),
        )

        # Calculate year-over-year changes
        phases_change = 0
        on_time_change = 0
        hours_change = 0

        if last_year_stats['phases'] and last_year_stats['phases'] > 0:
            phases_change = round(((current_year_stats['phases'] - last_year_stats['phases']) / last_year_stats['phases'] * 100), 1)
            hours_change = round(((current_year_stats['total_hours'] or 0) - (last_year_stats['total_hours'] or 0)) / (last_year_stats['total_hours'] or 1) * 100, 1)

        if last_year_stats['on_time'] and last_year_stats['on_time'] > 0 and last_year_stats['phases'] > 0:
            last_year_rate = last_year_stats['on_time'] / last_year_stats['phases'] * 100
            current_year_rate = (current_year_stats['on_time'] / current_year_stats['phases'] * 100) if current_year_stats['phases'] > 0 else 0
            on_time_change = round(current_year_rate - last_year_rate, 1)

        # Client satisfaction and retest analysis
        client_metrics = {}
        for client_data in completed_phases.values('job__client__name', 'job__client__id').annotate(
            phase_count=Count('id'),
            on_time_count=Count('id', filter=Q(actual_delivery_date__lte=F('desired_delivery_date'))),
            avg_hours=Avg('delivery_hours'),
            total_hours=Sum('delivery_hours'),
        ).order_by('-phase_count')[:10]:

            client_name = client_data['job__client__name']
            on_time_rate = round((client_data['on_time_count'] / client_data['phase_count'] * 100), 1) if client_data['phase_count'] > 0 else 0

            client_metrics[client_name] = {
                'phases': client_data['phase_count'],
                'on_time_rate': on_time_rate,
                'avg_hours': round(client_data['avg_hours'] or 0, 1),
                'total_hours': client_data['total_hours'] or 0,
            }

        # Performance benchmarks and scoring
        total_completed = quality_metrics['total_completed'] or 0
        on_time_rate = round((quality_metrics['on_time_deliveries'] / total_completed * 100), 1) if total_completed > 0 else 0
        early_rate = round((quality_metrics['early_deliveries'] / total_completed * 100), 1) if total_completed > 0 else 0
        late_rate = round((quality_metrics['late_deliveries'] / total_completed * 100), 1) if total_completed > 0 else 0

        # Overall performance score (weighted average) - without efficiency since we don't have estimates
        performance_score = round((on_time_rate * 0.6 + early_rate * 0.4), 1)

        result = {
            'quality_metrics': {
                'total_completed': total_completed,
                'on_time_rate': on_time_rate,
                'early_rate': early_rate,
                'late_rate': late_rate,
                'performance_score': performance_score,
                'avg_delivery_hours': round(quality_metrics['avg_delivery_hours'] or 0, 1),
                'total_delivery_hours': quality_metrics['total_delivery_hours'] or 0,
            },
            'monthly_trends': monthly_trends,
            'year_comparison': {
                'current_year': current_year,
                'last_year': last_year,
                'phases_change': phases_change,
                'on_time_change': on_time_change,
                'hours_change': hours_change,
                'current_year_stats': current_year_stats,
                'last_year_stats': last_year_stats,
            },
            'client_metrics': client_metrics,
            'performance_grade': 'Excellent' if performance_score >= 90 else 'Good' if performance_score >= 75 else 'Fair' if performance_score >= 60 else 'Needs Improvement'
        }

        # Cache for 20 minutes
        cache.set(cache_key, result, 1200)
        return result

    def clear_cache(self):
        """Clear all cached data for this service"""
        from django.core.cache import cache
        # Clear service readiness cache
        cache.delete(f"service_readiness_{self.id}_{self.skillsRequired.count()}_{self.skillsDesired.count()}")
        # Clear analytics cache
        cache.delete(f"service_analytics_{self.id}_{self.phases.count()}")
        # Clear skills coverage cache
        cache.delete(f"skills_coverage_{self.id}_{self.skillsRequired.count()}_{self.skillsDesired.count()}")
        # Clear performance metrics cache
        cache.delete(f"performance_metrics_{self.id}_{self.phases.count()}")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
        # Clear cache when service is updated
        if self.pk:
            self.clear_cache()
        return super().save(*args, **kwargs)