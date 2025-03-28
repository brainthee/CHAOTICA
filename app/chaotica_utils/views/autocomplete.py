from django.template import loader
from django.db.models import TextField, Value, Q
from django.db.models.functions import Concat, Lower
from django.http import JsonResponse
from ..models import User
from ..utils import is_ajax
from dal import autocomplete
from django.contrib.auth.decorators import login_required
from guardian.shortcuts import get_objects_for_user
from django.views.decorators.http import require_POST


######################################
# Autocomplete fields
######################################


class UserAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        # Don't forget to filter out results depending on the visitor !
        if not self.request.user.is_authenticated:
            return User.objects.none()
        # TODO: Do permission checks...
        qs = User.objects.all().annotate(
            full_name=Concat("first_name", Value(" "), "last_name")
        )
        if self.q:
            qs = qs.filter(
                Q(email__icontains=self.q)
                | Q(full_name__icontains=self.q)
                | Q(first_name__icontains=self.q)
                | Q(last_name__icontains=self.q),
                is_active=True,
            )
        return qs


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
        Accreditation,
        Project,
        OrganisationalUnit,
    )

    if is_ajax(request) and len(q) > 2:
        ## Jobs
        units_with_job_perms = get_objects_for_user(
            request.user, "jobtracker.can_view_jobs", OrganisationalUnit
        )

        jobs_search = (
            Job.objects.filter(
                unit__in=units_with_job_perms,
            )
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
            )
        )[:result_limit]
        context["search_jobs"] = jobs_search
        results_count = results_count + jobs_search.count()

        ## Phases
        phases_search = (
            Phase.objects.filter(
                job__unit__in=units_with_job_perms,
            )
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
        results_count = results_count + phases_search.count()

        ## Clients
        cl_search = (
            get_objects_for_user(request.user, "jobtracker.view_client", Client)
            .annotate(lower_name=Lower("name"))
            .filter(Q(lower_name__contains=q))
        )[:result_limit]
        context["search_clients"] = cl_search
        results_count = results_count + cl_search.count()

        ## BillingCodes
        bc_search = (
            get_objects_for_user(
                request.user, "jobtracker.view_billingcode", BillingCode
            )
            .annotate(lower_code=Lower("code"))
            .filter(Q(lower_code__contains=q))
        )[:result_limit]
        context["search_billingCodes"] = bc_search
        results_count = results_count + bc_search.count()

        ## Services
        sv_search = (
            get_objects_for_user(request.user, "jobtracker.view_service", Service)
            .annotate(lower_name=Lower("name"))
            .filter(Q(lower_name__contains=q))
        )[:result_limit]
        context["search_services"] = sv_search
        results_count = results_count + sv_search.count()

        ## Skills
        sk_search = (
            get_objects_for_user(request.user, "jobtracker.view_skill", Skill)
            .annotate(lower_name=Lower("name"))
            .filter(Q(lower_name__contains=q))
        )[:result_limit]
        context["search_skills"] = sk_search
        results_count = results_count + sk_search.count()

        ## Qualifications
        qual_search = (
            get_objects_for_user(
                request.user, "jobtracker.view_qualification", Qualification
            )
            .annotate(lower_name=Lower("name"))
            .filter(Q(lower_name__contains=q))
        )[:result_limit]
        context["search_quals"] = qual_search
        results_count = results_count + qual_search.count()

        ## Accreditation
        accred_search = (
            get_objects_for_user(
                request.user, "jobtracker.view_accreditation", Accreditation
            )
            .annotate(lower_name=Lower("name"))
            .filter(Q(lower_name__contains=q))
        )[:result_limit]
        context["search_accred"] = accred_search
        results_count = results_count + accred_search.count()

        ## Projects
        project_search = (
            get_objects_for_user(request.user, "*", Project)
            .annotate(lower_title=Lower("title"))
            .filter(Q(lower_title__contains=q))
        )[:result_limit]
        context["search_project"] = project_search
        results_count = results_count + project_search.count()

        ## Users
        us_search = User.objects.annotate(
            full_name=Concat(
                Lower("first_name"),
                Value(" "),
                Lower("last_name"),
                output_field=TextField(),
            ),
            lower_email=Lower("email"),
            lower_notification_email=Lower("notification_email"),
        ).filter(
            Q(full_name__contains=q)
            | Q(lower_email__contains=q)
            | Q(lower_notification_email__contains=q)
        )[
            :result_limit
        ]
        context["search_users"] = us_search
        results_count = results_count + us_search.count()

    context["results_count"] = results_count

    context["q"] = q
    data["html_form"] = loader.render_to_string(
        "partials/search-results.html", context, request=request
    )

    return JsonResponse(data)
