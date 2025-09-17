from django.http import JsonResponse
from django.db.models import Q
from django_select2.views import AutoResponseView
from django.contrib.auth.mixins import LoginRequiredMixin
from guardian.shortcuts import get_objects_for_user

from ..models import Skill, Team, Service, OrganisationalUnit, OrganisationalUnitRole, Client, Project, Job, BillingCode, Phase


SEARCH_REGEX = r'.*{}.*'
        

################################################
## Job Autocompletes
################################################


class JobBillingCodeAutocomplete(AutoResponseView):
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'results': [], 'pagination': {'more': False}})

        # Get parameters
        self.term = request.GET.get('term', '')
        job_slug = request.GET.get('slug', None)
        self.page_size = int(request.GET.get('page_size', 20))
        self.page = int(request.GET.get('page', 1))

        if not job_slug:
            return JsonResponse({'results': [], 'pagination': {'more': False}})

        # TODO: return only if job allowed
        try:
            job = Job.objects.get(slug=job_slug)
        except Job.DoesNotExist:
            return JsonResponse({'results': [], 'pagination': {'more': False}})

        qs = BillingCode.objects.filter(Q(client=job.client) | Q(client__isnull=True))

        if self.term:
            qs = qs.filter(code__istartswith=self.term)

        # Pagination
        start = (self.page - 1) * self.page_size
        end = start + self.page_size

        results = []
        for bc in qs[start:end]:
            results.append({
                'id': bc.pk,
                'text': bc.get_html_label() if hasattr(bc, 'get_html_label') else str(bc),
            })

        has_more = qs.count() > end

        return JsonResponse({
            'results': results,
            'pagination': {'more': has_more}
        })


class JobAutocomplete(AutoResponseView):
    def get(self, request, *args, **kwargs):
        # Don't forget to filter out results depending on the visitor !
        if not request.user.is_authenticated:
            return JsonResponse({'results': [], 'pagination': {'more': False}})

        # Get parameters
        self.term = request.GET.get('term', '')
        self.page_size = int(request.GET.get('page_size', 20))
        self.page = int(request.GET.get('page', 1))

        units_with_job_perms = get_objects_for_user(
            request.user, "jobtracker.can_view_jobs", OrganisationalUnit
        )

        qs = Job.objects.filter(
            unit__in=units_with_job_perms,
        )
        if self.term:
            qs = qs.filter(
                Q(title__iregex=SEARCH_REGEX.format(self.term))
                | Q(slug__iregex=SEARCH_REGEX.format(self.term))
                | Q(id__iregex=SEARCH_REGEX.format(self.term)),
            )

        # Pagination
        start = (self.page - 1) * self.page_size
        end = start + self.page_size

        results = []
        for job in qs[start:end]:
            results.append({
                'id': job.pk,
                'text': str(job),
            })

        has_more = qs.count() > end

        return JsonResponse({
            'results': results,
            'pagination': {'more': has_more}
        })


class PhaseAutocomplete(AutoResponseView):
    def get(self, request, *args, **kwargs):
        # Don't forget to filter out results depending on the visitor !
        if not request.user.is_authenticated:
            return JsonResponse({'results': [], 'pagination': {'more': False}})

        # Get parameters
        self.term = request.GET.get('term', '')
        self.page_size = int(request.GET.get('page_size', 20))
        self.page = int(request.GET.get('page', 1))

        qs = Phase.objects.phases_with_unit_permission(
            request.user, "jobtracker.can_view_jobs"
        )
        if self.term:
            qs = qs.filter(
                Q(title__iregex=SEARCH_REGEX.format(self.term))
                | Q(phase_id__iregex=SEARCH_REGEX.format(self.term))
                | Q(job__id__iregex=SEARCH_REGEX.format(self.term))
            )

        # Pagination
        start = (self.page - 1) * self.page_size
        end = start + self.page_size

        results = []
        for phase in qs[start:end]:
            results.append({
                'id': phase.pk,
                'text': str(phase),
            })

        has_more = qs.count() > end

        return JsonResponse({
            'results': results,
            'pagination': {'more': has_more}
        })


class ProjectAutocomplete(AutoResponseView):
    def get(self, request, *args, **kwargs):
        # Don't forget to filter out results depending on the visitor !
        if not request.user.is_authenticated:
            return JsonResponse({'results': [], 'pagination': {'more': False}})

        # Get parameters
        self.term = request.GET.get('term', '')
        self.page_size = int(request.GET.get('page_size', 20))
        self.page = int(request.GET.get('page', 1))

        qs = Project.objects.all().order_by('-id')
        if self.term:
            qs = qs.filter(
                Q(title__iregex=SEARCH_REGEX.format(self.term)) |
                Q(id__iregex=SEARCH_REGEX.format(self.term))
            )

        # Pagination
        start = (self.page - 1) * self.page_size
        end = start + self.page_size

        results = []
        for project in qs[start:end]:
            results.append({
                'id': project.pk,
                'text': str(project),
            })

        has_more = qs.count() > end

        return JsonResponse({
            'results': results,
            'pagination': {'more': has_more}
        })
        

class SkillAutocomplete(LoginRequiredMixin, AutoResponseView):
    """
    Autocomplete view for Skills with case-insensitive search.
    Searches both skill name and category name.
    """

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'results': [], 'pagination': {'more': False}})

        # Get parameters
        self.term = request.GET.get('term', '')
        self.page_size = int(request.GET.get('page_size', 20))
        self.page = int(request.GET.get('page', 1))

        # Get base queryset with prefetch
        qs = Skill.objects.all().prefetch_related("category").order_by("category", "name")

        # Apply case-insensitive search using iregex for MySQL compatibility
        if self.term:
            qs = qs.filter(
                Q(name__iregex=SEARCH_REGEX.format(self.term)) |
                Q(category__name__iregex=SEARCH_REGEX.format(self.term))
            )

        # Order by name for consistent results
        qs = qs.order_by('name')

        # Pagination
        start = (self.page - 1) * self.page_size
        end = start + self.page_size

        results = []
        for skill in qs[start:end]:
            results.append({
                'id': skill.pk,
                'text': f"{skill.category.name} - {skill.name}",
            })

        has_more = qs.count() > end

        return JsonResponse({
            'results': results,
            'pagination': {'more': has_more}
        })


class TeamAutocomplete(LoginRequiredMixin, AutoResponseView):
    """
    Autocomplete view for Teams with case-insensitive search.
    """

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'results': [], 'pagination': {'more': False}})

        # Get parameters
        self.term = request.GET.get('term', '')
        self.page_size = int(request.GET.get('page_size', 20))
        self.page = int(request.GET.get('page', 1))

        # Get base queryset
        qs = Team.objects.all().order_by("name")

        # Apply case-insensitive search
        if self.term:
            qs = qs.filter(name__iregex=SEARCH_REGEX.format(self.term))

        # Order by name
        qs = qs.order_by('name')

        # Pagination
        start = (self.page - 1) * self.page_size
        end = start + self.page_size

        results = []
        for team in qs[start:end]:
            results.append({
                'id': team.pk,
                'text': team.name,
            })

        has_more = qs.count() > end

        return JsonResponse({
            'results': results,
            'pagination': {'more': has_more}
        })


class ServiceAutocomplete(LoginRequiredMixin, AutoResponseView):
    """
    Autocomplete view for Services with case-insensitive search.
    """

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'results': [], 'pagination': {'more': False}})

        # Get parameters
        self.term = request.GET.get('term', '')
        self.page_size = int(request.GET.get('page_size', 20))
        self.page = int(request.GET.get('page', 1))

        # Check user permissions for services
        qs = get_objects_for_user(request.user, "jobtracker.view_service", Service)

        # Apply case-insensitive search
        if self.term:
            qs = qs.filter(name__iregex=SEARCH_REGEX.format(self.term))

        # Order by name
        qs = qs.order_by('name')

        # Pagination
        start = (self.page - 1) * self.page_size
        end = start + self.page_size

        results = []
        for service in qs[start:end]:
            results.append({
                'id': service.pk,
                'text': service.name,
            })

        has_more = qs.count() > end

        return JsonResponse({
            'results': results,
            'pagination': {'more': has_more}
        })


class OrganisationalUnitAutocomplete(LoginRequiredMixin, AutoResponseView):
    """
    Autocomplete view for Organisational Units with case-insensitive search.
    """

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'results': [], 'pagination': {'more': False}})

        # Get parameters
        self.term = request.GET.get('term', '')
        self.page_size = int(request.GET.get('page_size', 20))
        self.page = int(request.GET.get('page', 1))

        # Get base queryset
        qs = OrganisationalUnit.objects.all()

        # Apply case-insensitive search
        if self.term:
            qs = qs.filter(name__iregex=SEARCH_REGEX.format(self.term))

        # Order by name
        qs = qs.order_by('name')

        # Pagination
        start = (self.page - 1) * self.page_size
        end = start + self.page_size

        results = []
        for unit in qs[start:end]:
            results.append({
                'id': unit.pk,
                'text': unit.name,
            })

        has_more = qs.count() > end

        return JsonResponse({
            'results': results,
            'pagination': {'more': has_more}
        })


class OrganisationalUnitRoleAutocomplete(LoginRequiredMixin, AutoResponseView):
    """
    Autocomplete view for Organisational Unit Roles with case-insensitive search.
    """

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'results': [], 'pagination': {'more': False}})

        # Get parameters
        self.term = request.GET.get('term', '')
        self.page_size = int(request.GET.get('page_size', 20))
        self.page = int(request.GET.get('page', 1))

        # Get base queryset
        qs = OrganisationalUnitRole.objects.all()

        # Apply case-insensitive search
        if self.term:
            qs = qs.filter(name__iregex=SEARCH_REGEX.format(self.term))

        # Order by name
        qs = qs.order_by('name')

        # Pagination
        start = (self.page - 1) * self.page_size
        end = start + self.page_size

        results = []
        for role in qs[start:end]:
            results.append({
                'id': role.pk,
                'text': role.name,
            })

        has_more = qs.count() > end

        return JsonResponse({
            'results': results,
            'pagination': {'more': has_more}
        })


class ClientAutocomplete(LoginRequiredMixin, AutoResponseView):
    """
    Autocomplete view for Clients with case-insensitive search.
    Searches both name and short_name fields.
    """

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'results': [], 'pagination': {'more': False}})

        # Get parameters
        self.term = request.GET.get('term', '')
        self.page_size = int(request.GET.get('page_size', 20))
        self.page = int(request.GET.get('page', 1))

        # Check user permissions for clients and filter for onboarded users
        qs = get_objects_for_user(request.user, "jobtracker.view_client", Client)
        # qs = qs.filter(onboarded_users__isnull=False).distinct()

        # Apply case-insensitive search
        if self.term:
            qs = qs.filter(
                Q(name__iregex=SEARCH_REGEX.format(self.term)) |
                Q(short_name__iregex=SEARCH_REGEX.format(self.term))
            )

        # Order by name
        qs = qs.order_by('name')

        # Pagination
        start = (self.page - 1) * self.page_size
        end = start + self.page_size

        results = []
        for client in qs[start:end]:
            display_name = client.name
            if client.short_name and client.short_name != client.name:
                display_name = f"{client.name} ({client.short_name})"

            results.append({
                'id': client.pk,
                'text': display_name,
            })

        has_more = qs.count() > end

        return JsonResponse({
            'results': results,
            'pagination': {'more': has_more}
        })
