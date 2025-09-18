from guardian.mixins import PermissionRequiredMixin
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic import TemplateView
from django.urls import reverse_lazy
from django.db.models import Prefetch
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from chaotica_utils.views import ChaoticaBaseView
from chaotica_utils.models import User
from chaotica_utils.utils import get_sentinel_user
from ..models import Skill, SkillCategory, UserSkill
from ..forms import SkillForm, SkillCatForm
from ..mixins import PrefetchRelatedMixin
from ..enums import UserSkillRatings
import hashlib
import logging


logger = logging.getLogger(__name__)


class SkillBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = Skill
    fields = "__all__"
    permission_required = "jobtracker.view_skill"
    accept_global_perms = True
    return_403 = True
    success_url = reverse_lazy("skill_list")

    def get_context_data(self, **kwargs):
        context = super(SkillBaseView, self).get_context_data(**kwargs)
        # Get categories
        context["categories"] = SkillCategory.objects.all().prefetch_related("skills", "skills__users", "skills__users__user")
        return context


class SkillListView(SkillBaseView, ListView):
    # prefetch_related = ["category", "user_skill"]
    pass
    


class SkillDetailView(PrefetchRelatedMixin, SkillBaseView, PermissionRequiredMixin, DetailView):
    prefetch_related = ["category", "users"]
    """View to list the details from one job.
    Use the 'job' variable in the template to access
    the specific job here and in the Views below"""

    permission_required = "jobtracker.view_skill"
    accept_global_perms = True
    return_403 = True


class SkillCreateView(SkillBaseView, PermissionRequiredMixin, CreateView):
    form_class = SkillForm
    fields = None
    permission_required = "jobtracker.add_skill"
    accept_global_perms = True
    permission_object = Skill
    return_403 = True

    def get_context_data(self, **kwargs):
        context = super(SkillCreateView, self).get_context_data(**kwargs)
        # Get categories
        context["category"] = SkillCategory.objects.get(slug=self.kwargs["catSlug"])
        return context

    def form_valid(self, form):
        form.instance.category = SkillCategory.objects.get(slug=self.kwargs["catSlug"])
        return super(SkillCreateView, self).form_valid(form)


class SkillUpdateView(SkillBaseView, PermissionRequiredMixin, UpdateView):
    form_class = SkillForm
    fields = None
    permission_required = "jobtracker.change_skill"
    accept_global_perms = True
    return_403 = True


class SkillDeleteView(SkillBaseView, PermissionRequiredMixin, DeleteView):
    """View to delete a job"""

    permission_required = "jobtracker.delete_skill"
    accept_global_perms = True
    return_403 = True


class SkillCatBaseView(PermissionRequiredMixin, ChaoticaBaseView):
    model = SkillCategory
    fields = "__all__"
    permission_required = "jobtracker.view_skillcategory"
    return_403 = True
    accept_global_perms = True
    success_url = reverse_lazy("skill_list")


class SkillCatCreateView(SkillCatBaseView, PermissionRequiredMixin, CreateView):
    form_class = SkillCatForm
    fields = None
    permission_required = "jobtracker.add_skillcategory"
    permission_object = SkillCategory
    return_403 = True
    accept_global_perms = True


class SkillCatUpdateView(SkillCatBaseView, PermissionRequiredMixin, UpdateView):
    form_class = SkillCatForm
    fields = None
    permission_required = "jobtracker.change_skillcategory"
    return_403 = True
    accept_global_perms = True


class SkillCatDeleteView(SkillCatBaseView, PermissionRequiredMixin, DeleteView):
    """View to delete a job"""

    permission_required = "jobtracker.delete_skillcategory"
    return_403 = True
    accept_global_perms = True


class SkillMatrixView(PermissionRequiredMixin, ChaoticaBaseView, TemplateView):
    """View showing skills matrix for all users"""

    template_name = "jobtracker/skill_matrix.html"
    permission_required = "jobtracker.view_skill"
    accept_global_perms = True
    return_403 = True

    def get_cache_key(self, filters):
        """Generate a unique cache key based on filters"""
        filter_str = f"{filters.get('unit', '')}-{filters.get('team', '')}-{filters.get('category', '')}-{filters.get('role', '')}"
        return f"skill_matrix_{hashlib.md5(filter_str.encode()).hexdigest()}"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get filter parameters
        unit_filter = self.request.GET.get('unit')
        team_filter = self.request.GET.get('team')
        category_filter = self.request.GET.get('category')
        role_filter = self.request.GET.get('role')

        # Create filters dict for cache key
        filters = {
            'unit': unit_filter,
            'team': team_filter,
            'category': category_filter,
            'role': role_filter
        }

        # Try to get from cache first
        cache_key = self.get_cache_key(filters)
        # cached_data = cache.get(cache_key)
        cached_data = None

        if cached_data is not None:
            # Use cached data if available
            context.update(cached_data)
            context['from_cache'] = True
            return context

        # Start with active users
        users_query = User.objects.filter(
            is_active=True, groups__isnull=False,)

        # Apply unit filter
        if unit_filter:
            users_query = users_query.filter(
                unit_memberships__unit__slug=unit_filter,
                unit_memberships__left_date__isnull=True
            ).distinct()

        # Apply team filter
        if team_filter:
            users_query = users_query.filter(
                teams__team__slug=team_filter,
                teams__left_at__isnull=True
            ).distinct()

        # Apply org role filter
        if role_filter:
            users_query = users_query.filter(
                unit_memberships__roles__id=role_filter,
                unit_memberships__left_date__isnull=True
            ).distinct()

        # Get users with their skills - optimize with select_related and only()
        users = users_query.select_related().prefetch_related(
            Prefetch(
                'skills',
                queryset=UserSkill.objects.select_related('skill', 'skill__category').only(
                    'skill', 'rating', 'interested_in_improving_skill', 'user'
                )
            )
        ).get_default_order()

        # Get all skills organized by category (with optional category filter)
        categories_query = SkillCategory.objects.all()
        if category_filter:
            categories_query = categories_query.filter(slug=category_filter)

        categories = categories_query.prefetch_related(
            Prefetch(
                'skills',
                queryset=Skill.objects.only('id', 'name', 'slug', 'description', 'category')
            )
        ).only('id', 'name', 'slug').order_by('name')

        # Build matrix data
        matrix_data = []
        for user in users:
            user_skills = {us.skill.id: us for us in user.skills.all()}
            user_row = {
                'user': user,
                'skills': {}
            }

            for category in categories:
                for skill in category.skills.all():
                    user_skill = user_skills.get(skill.id)
                    user_row['skills'][skill.id] = {
                        'skill': skill,
                        'user_skill': user_skill,
                        'rating': user_skill.rating if user_skill else UserSkillRatings.NO_EXPERIENCE,
                        'interested': user_skill.interested_in_improving_skill if user_skill else False
                    }

            matrix_data.append(user_row)

        # Get filter options for the template
        from ..models import OrganisationalUnit, Team, OrganisationalUnitRole

        # Prepare cacheable data
        cacheable_data = {
            'matrix_data': matrix_data,
            'categories': list(categories),  # Convert to list for caching
            'rating_choices': UserSkillRatings.CHOICES,
        }

        # Cache the matrix data for 5 minutes
        # cache.set(cache_key, cacheable_data, 300)

        # Add non-cacheable data
        context.update(cacheable_data)

        # Filter options (these change less frequently, cache separately)
        filter_options_key = 'skill_matrix_filter_options'
        # filter_options = cache.get(filter_options_key)
        filter_options = None

        if filter_options is None:
            filter_options = {
                'all_units': list(OrganisationalUnit.objects.all().order_by('name').values('slug', 'name')),
                'all_teams': list(Team.objects.all().order_by('name').values('slug', 'name')),
                'all_categories': list(SkillCategory.objects.all().order_by('name').values('slug', 'name')),
                'all_org_roles': list(OrganisationalUnitRole.objects.all().order_by('name').values('name', 'id')),
            }
            # Cache filter options for 30 minutes
            # cache.set(filter_options_key, filter_options, 1800)

        context.update(filter_options)

        # Current filters
        context['current_unit'] = unit_filter
        context['current_team'] = team_filter
        context['current_category'] = category_filter
        context['current_role'] = role_filter
        context['from_cache'] = False

        return context


class SkillCategoryDetailView(PermissionRequiredMixin, ChaoticaBaseView, DetailView):
    """View for displaying category details with enhanced navigation"""

    model = SkillCategory
    template_name = "jobtracker/skillcategory_detail.html"
    permission_required = "jobtracker.view_skillcategory"
    accept_global_perms = True
    return_403 = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get all categories for navigation
        context['all_categories'] = SkillCategory.objects.all().order_by('name')

        # Get skills in this category with user data
        category = self.get_object()
        context['skills_with_users'] = category.skills.all().prefetch_related(
            'users__user',
            'services_skill_required',
            'services_skill_desired'
        )

        return context
