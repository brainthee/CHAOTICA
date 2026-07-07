import re

from django.template import loader
from django.db.models import TextField, Value, Q
from django.db.models.functions import Concat, Lower
from django.http import JsonResponse
from cities_light.models import City
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django_select2.views import AutoResponseView
from ..models import User
from ..utils import is_ajax
from guardian.shortcuts import get_objects_for_user
from django.views.decorators.http import require_POST


######################################
# Autocomplete fields
######################################

SEARCH_REGEX = r'.*{}.*'

@login_required
def city_autocomplete(request):
    term = request.GET.get('term', '').strip()
    if not term:
        return JsonResponse({'results': [], 'pagination': {'more': False}})

    from django.db.models import Case, When, Value, IntegerField
    cities = City.objects.filter(
        Q(name__icontains=term) | Q(search_names__icontains=term)
    ).annotate(
        rank=Case(
            When(name__iexact=term, then=Value(0)),
            When(name__istartswith=term, then=Value(1)),
            When(name__icontains=term, then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )
    ).select_related('country').order_by('rank', 'name')[:30]

    results = [{'id': city.pk, 'text': f"{city.name}, {city.country.name}"} for city in cities]
    return JsonResponse({'results': results, 'pagination': {'more': False}})

class UserAutocomplete(AutoResponseView):
    def get(self, request, *args, **kwargs):
        # Don't forget to filter out results depending on the visitor !
        if not request.user.is_authenticated:
            return JsonResponse({'results': [], 'pagination': {'more': False}})

        # Get the search term
        self.term = request.GET.get('term', '')
        self.page_size = int(request.GET.get('page_size', 20))
        self.page = int(request.GET.get('page', 1))

        qs = User.objects.filter(is_active=True).annotate(
            full_name=Concat("first_name", Value(" "), "last_name")
        ).order_by("full_name")

        if self.term:
            qs = qs.filter(
                Q(email__iregex=SEARCH_REGEX.format(self.term))
                | Q(full_name__iregex=SEARCH_REGEX.format(self.term))
                | Q(first_name__iregex=SEARCH_REGEX.format(self.term))
                | Q(last_name__iregex=SEARCH_REGEX.format(self.term))
                | (Q(alias__iregex=SEARCH_REGEX.format(self.term)) & Q(alias__isnull=False)),
            )

        # Pagination
        start = (self.page - 1) * self.page_size
        end = start + self.page_size

        results = []
        for user in qs[start:end]:
            results.append({
                'id': user.pk,
                'text': str(user),
            })

        has_more = qs.count() > end

        return JsonResponse({
            'results': results,
            'pagination': {'more': has_more}
        })


@login_required
@require_POST
def site_search(request):
    data = {}
    context = {}
    q = request.POST.get("q", "").lower()
    results_count = 0
    result_limit = 100
    from jobtracker.models import (
        Job,
        Phase,
        Client,
        Service,
        Skill,
        BillingCode,
        Qualification,
        Project,
        OrganisationalUnit,
    )

    if is_ajax(request) and len(q) > 2:
        ## Jobs
        units_with_job_perms = get_objects_for_user(
            request.user, "jobtracker.can_view_jobs", OrganisationalUnit
        )

        # NOTE: each queryset is evaluated once with list() so the template can
        # iterate it and count it (via |length) without a second DB round-trip,
        # and select_related pulls in the relations the results partial renders
        # (job.client, phase.job/phase.job.client) to avoid per-row N+1 queries.
        jobs_search = list(
            Job.objects.filter(
                unit__in=units_with_job_perms,
            )
            .select_related("client")
            .annotate(
                lower_title=Lower("title"),
                lower_overview=Lower("overview"),
                lower_slug=Lower("slug"),
                lower_id=Lower("id"),
            )
            .filter(
                Q(lower_title__contains=q)
                | Q(lower_overview__contains=q)
                | Q(lower_slug__contains=q)
                | Q(lower_id__contains=q)
            )[:result_limit]
        )
        context["search_jobs"] = jobs_search
        results_count = results_count + len(jobs_search)

        ## Phases
        phases_search = list(
            Phase.objects.filter(
                job__unit__in=units_with_job_perms,
            )
            .select_related("job", "job__client")
            .annotate(
                lower_title=Lower("title"),
                lower_description=Lower("description"),
                lower_phase_id=Lower("phase_id"),
            )
            .filter(
                Q(lower_title__contains=q)
                | Q(lower_description__contains=q)
                | Q(lower_phase_id__contains=q)
            )[:result_limit]
        )
        context["search_phases"] = phases_search
        results_count = results_count + len(phases_search)

        ## Clients
        cl_search = list(
            get_objects_for_user(request.user, "jobtracker.view_client", Client)
            .annotate(lower_name=Lower("name"))
            .filter(Q(lower_name__contains=q))[:result_limit]
        )
        context["search_clients"] = cl_search
        results_count = results_count + len(cl_search)

        ## BillingCodes
        bc_search = list(
            get_objects_for_user(
                request.user, "jobtracker.view_billingcode", BillingCode
            )
            .annotate(lower_code=Lower("code"))
            .filter(Q(lower_code__contains=q))[:result_limit]
        )
        context["search_billingCodes"] = bc_search
        results_count = results_count + len(bc_search)

        ## Services
        sv_search = list(
            get_objects_for_user(request.user, "jobtracker.view_service", Service)
            .annotate(lower_name=Lower("name"))
            .filter(Q(lower_name__contains=q))[:result_limit]
        )
        context["search_services"] = sv_search
        results_count = results_count + len(sv_search)

        ## Skills
        sk_search = list(
            get_objects_for_user(request.user, "jobtracker.view_skill", Skill)
            .select_related("category")
            .annotate(lower_name=Lower("name"))
            .filter(Q(lower_name__contains=q))[:result_limit]
        )
        context["search_skills"] = sk_search
        results_count = results_count + len(sk_search)

        ## Qualifications
        qual_search = list(
            get_objects_for_user(
                request.user, "jobtracker.view_qualification", Qualification
            )
            .annotate(lower_name=Lower("name"))
            .filter(Q(lower_name__contains=q))[:result_limit]
        )
        context["search_quals"] = qual_search
        results_count = results_count + len(qual_search)

        ## Projects
        project_search = list(
            get_objects_for_user(request.user, "*", Project)
            .annotate(lower_title=Lower("title"))
            .filter(Q(lower_title__contains=q))[:result_limit]
        )
        context["search_project"] = project_search
        results_count = results_count + len(project_search)

        ## Users
        us_search = list(
            User.objects.annotate(
                full_name=Concat(
                    Lower("first_name"),
                    Value(" "),
                    Lower("last_name"),
                    output_field=TextField(),
                ),
                lower_email=Lower("email"),
                lower_notification_email=Lower("notification_email"),
                lower_alias=Lower("alias"),
            ).filter(
                Q(full_name__contains=q)
                | Q(lower_email__contains=q)
                | Q(lower_notification_email__contains=q)
                | (Q(lower_alias__contains=q) & Q(alias__isnull=False)),
                is_active=True,
            )[:result_limit]
        )
        context["search_users"] = us_search
        results_count = results_count + len(us_search)

    context["results_count"] = results_count

    context["q"] = q
    data["html_form"] = loader.render_to_string(
        "partials/search-results.html", context, request=request
    )

    return JsonResponse(data)


# Job IDs are plain integers (e.g. "1234"); Phase IDs are "<job id>-<phase
# number>" (e.g. "1234-1", the Phase.phase_id field).
_PHASE_ID_RE = re.compile(r"^\d+-\d+$")


@login_required
def search_goto(request):
    """Resolve a typed Job ID or Phase ID straight to its canonical URL.

    Powers the "type an ID and hit Enter" quick-jump in the global search box.
    The lookup is scoped to the units the user may view jobs in — identical to
    ``site_search`` — so it never leaks the existence of jobs/phases the user
    can't already see. Returns ``{"url": <absolute url>}`` on a hit, or
    ``{"url": None}`` (HTTP 200) so the client can silently fall back to the
    normal search-results dropdown.
    """
    from jobtracker.models import Job, Phase, OrganisationalUnit

    q = request.GET.get("q", "").strip()
    url = None

    if q:
        units_with_job_perms = get_objects_for_user(
            request.user, "jobtracker.can_view_jobs", OrganisationalUnit
        )
        if _PHASE_ID_RE.match(q):
            phase = (
                Phase.objects.filter(job__unit__in=units_with_job_perms, phase_id=q)
                .select_related("job")
                .first()
            )
            if phase:
                url = phase.get_absolute_url()
        elif q.isdigit():
            job = Job.objects.filter(
                unit__in=units_with_job_perms, id=int(q)
            ).first()
            if job:
                url = job.get_absolute_url()

    return JsonResponse({"url": url})
