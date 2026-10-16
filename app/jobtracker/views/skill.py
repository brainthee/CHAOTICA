from chaotica_utils.mixins import SecurePermissionRequiredMixin as PermissionRequiredMixin, ObjectActivityMixin
from ..selectors.catalogue import (
    matrix_users,
    skill_matrix,
    skill_matrix_filter_options,
)
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic import TemplateView
from django.urls import reverse_lazy
from django.db.models import Prefetch
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from chaotica_utils.views import ChaoticaBaseView, ProtectedDeleteMixin
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
    


class SkillDetailView(ObjectActivityMixin, PrefetchRelatedMixin, SkillBaseView, PermissionRequiredMixin, DetailView):
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


class SkillDeleteView(ProtectedDeleteMixin, SkillBaseView, PermissionRequiredMixin, DeleteView):
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


class SkillCatDeleteView(ProtectedDeleteMixin, SkillCatBaseView, PermissionRequiredMixin, DeleteView):
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

        categories, matrix_data = skill_matrix(
            matrix_users(), unit_filter, team_filter, category_filter, role_filter
        )

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

        filter_options = skill_matrix_filter_options()
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
