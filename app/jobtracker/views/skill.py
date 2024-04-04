from guardian.mixins import PermissionRequiredMixin
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from chaotica_utils.views import ChaoticaBaseView
from ..models import Skill, SkillCategory
from ..forms import SkillForm, SkillCatForm
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
        context["categories"] = SkillCategory.objects.all()
        return context


class SkillListView(SkillBaseView, ListView):
    """View to list all jobs.
    Use the 'job_list' variable in the template
    to access all job objects"""


class SkillDetailView(SkillBaseView, PermissionRequiredMixin, DetailView):
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
