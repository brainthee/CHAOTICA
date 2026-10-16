import re

from django.template import loader
from django.db.models import Value, Q
from django.db.models.functions import Concat
from django.http import JsonResponse
from cities_light.models import City
from django.contrib.auth.decorators import login_required
from django_select2.views import AutoResponseView
from ..models import User
from ..utils import is_ajax
from ..selectors.search import resolve_goto, site_search as site_search_selector
from django.views.decorators.http import require_POST


######################################
# Autocomplete fields
######################################

SEARCH_REGEX = r".*{}.*"


@login_required
def city_autocomplete(request):
    term = request.GET.get("term", "").strip()
    if not term:
        return JsonResponse({"results": [], "pagination": {"more": False}})

    from django.db.models import Case, When, Value, IntegerField

    cities = (
        City.objects.filter(Q(name__icontains=term) | Q(search_names__icontains=term))
        .annotate(
            rank=Case(
                When(name__iexact=term, then=Value(0)),
                When(name__istartswith=term, then=Value(1)),
                When(name__icontains=term, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        )
        .select_related("country")
        .order_by("rank", "name")[:30]
    )

    results = [
        {"id": city.pk, "text": f"{city.name}, {city.country.name}"} for city in cities
    ]
    return JsonResponse({"results": results, "pagination": {"more": False}})


class UserAutocomplete(AutoResponseView):
    def get(self, request, *args, **kwargs):
        # Don't forget to filter out results depending on the visitor !
        if not request.user.is_authenticated:
            return JsonResponse({"results": [], "pagination": {"more": False}})

        # Get the search term
        self.term = request.GET.get("term", "")
        self.page_size = int(request.GET.get("page_size", 20))
        self.page = int(request.GET.get("page", 1))

        qs = (
            User.objects.filter(is_active=True)
            .annotate(full_name=Concat("first_name", Value(" "), "last_name"))
            .order_by("full_name")
        )

        if self.term:
            qs = qs.filter(
                Q(email__iregex=SEARCH_REGEX.format(re.escape(self.term)))
                | Q(full_name__iregex=SEARCH_REGEX.format(re.escape(self.term)))
                | Q(first_name__iregex=SEARCH_REGEX.format(re.escape(self.term)))
                | Q(last_name__iregex=SEARCH_REGEX.format(re.escape(self.term)))
                | (
                    Q(alias__iregex=SEARCH_REGEX.format(re.escape(self.term)))
                    & Q(alias__isnull=False)
                ),
            )

        # Pagination
        start = (self.page - 1) * self.page_size
        end = start + self.page_size

        results = []
        for user in qs[start:end]:
            results.append(
                {
                    "id": user.pk,
                    "text": str(user),
                }
            )

        has_more = qs.count() > end

        return JsonResponse({"results": results, "pagination": {"more": has_more}})


# Template context name for each search group.
_SEARCH_CONTEXT_KEYS = {
    "jobs": "search_jobs",
    "phases": "search_phases",
    "clients": "search_clients",
    "billing_codes": "search_billingCodes",
    "services": "search_services",
    "skills": "search_skills",
    "qualifications": "search_quals",
    "projects": "search_project",
    "users": "search_users",
}


@login_required
@require_POST
def site_search(request):
    q = request.POST.get("q", "").lower()
    groups = site_search_selector(request.user, q) if is_ajax(request) else {}
    context = {_SEARCH_CONTEXT_KEYS[k]: v for k, v in groups.items()}
    context["results_count"] = sum(len(v) for v in groups.values())
    context["q"] = q
    return JsonResponse(
        {
            "html_form": loader.render_to_string(
                "partials/search-results.html", context, request=request
            )
        }
    )


@login_required
def search_goto(request):
    """Resolve a typed Job ID or Phase ID straight to its canonical URL.

    Powers the "type an ID and hit Enter" quick-jump in the global search box.
    Scoped like the search itself, so it never leaks the existence of
    jobs/phases the user can't already see. Returns ``{"url": <url>}`` on a
    hit, or ``{"url": None}`` (HTTP 200) so the client can silently fall back
    to the normal search-results dropdown.
    """
    obj = resolve_goto(request.user, request.GET.get("q", ""))
    return JsonResponse({"url": obj.get_absolute_url() if obj else None})
