from django.http import HttpResponse, HttpResponseForbidden, JsonResponse, Http404
from django.template import loader
from django.contrib.auth.decorators import login_required
import logging
from chaotica_utils.views import page_defaults
from django.views.decorators.http import require_safe
from jobtracker.selectors.dashboard import (
    DASHBOARD_TABS,
    DashboardScope,
    consultant_stats,
    qa_feedback,
    team_leave_requests,
    team_members,
)

logger = logging.getLogger(__name__)

# Pending scheduling
# Pending TQA
# Pending PQA
# Upcoming Phases
# List of inflight jobs
# Late Jobs
# This Week's jobs (schedule based)
# AM View?
# People Lead


#: How often the dashboard re-fetches the visible tab (milliseconds).
DASHBOARD_REFRESH_MS = 3 * 60 * 1000


@login_required
@require_safe
def index(request):
    """First paint only: which tabs exist, their badge counts (COUNT queries),
    which opens first, and the consultant stats. Tab contents load on demand
    (``dashboard_tab``) and refresh themselves while visible."""
    scope = DashboardScope(request.user)
    context = {
        "can_scope": scope.can_scope,
        "can_signoff_scope": scope.can_signoff_scope,
        "can_tqa": scope.can_tqa,
        "can_pqa": scope.can_pqa,
        "can_deliver": scope.can_deliver,
        "is_people_manager": scope.is_people_manager,
        "upcoming_reports_date": scope.upcoming_reports_date(),
        "refresh_ms": DASHBOARD_REFRESH_MS,
    }
    counts = {}
    for key, (method, audience, _tmpl) in DASHBOARD_TABS.items():
        if audience is None or getattr(scope, audience):
            counts[key] = getattr(scope, method)().count()
    context["tab_counts"] = counts

    # Alarms open first when there's overdue work. Most users with alarms
    # have them, so fetch the lists once and render the visible tab inline
    # (no second request); the lists double as the badge counts.
    alarm_ctx = scope.alarm_context()
    context["alarm_count"] = alarm_ctx["alarm_count"]
    context["stale_alarm_count"] = alarm_ctx["stale_alarm_count"]
    context["show_alarms_first"] = alarm_ctx["alarm_count"] > 0
    if context["show_alarms_first"]:
        context["alarms_html"] = loader.render_to_string(
            "partials/alarms_table.html", alarm_ctx, request=request
        )

    # NB: "My Team" / "Team Leave Requests" have their own lazy views
    # (team_tab / team_leave_tab) - the two heaviest panels.

    context["consultant_stats"] = consultant_stats(request.user)
    context.update(qa_feedback(request.user))

    context = {**context, **page_defaults(request)}
    template = loader.get_template("dashboard_index.html")
    return HttpResponse(template.render(context, request))


@login_required
@require_safe
def dashboard_tab(request, key):
    """One dashboard tab's content, for lazy load and auto-refresh:
    ``{"html": ..., "count": N}`` (alarms add ``stale``)."""
    scope = DashboardScope(request.user)
    if key == "alarms":
        ctx = scope.alarm_context()
        html = loader.render_to_string("partials/alarms_table.html", ctx, request=request)
        return JsonResponse(
            {"html": html, "count": ctx["alarm_count"], "stale": ctx["stale_alarm_count"]}
        )
    if key not in DASHBOARD_TABS:
        raise Http404()
    method, audience, template = DASHBOARD_TABS[key]
    if audience is not None and not getattr(scope, audience):
        return HttpResponseForbidden()
    items = list(getattr(scope, method)())
    html = loader.render_to_string(
        template,
        {"items": items, "tab_key": key},
        request=request,
    )
    return JsonResponse({"html": html, "count": len(items)})


@login_required
@require_safe
def team_tab(request):
    """Lazy-loaded content for the dashboard "My Team" tab.

    Rendered on demand (first tab-show) rather than as part of index() so the
    initial dashboard load doesn't build a large card per direct report.
    """
    if not request.user.is_people_manager():
        return HttpResponseForbidden()

    team = team_members(request.user)
    template = loader.get_template("partials/team_dashboard.html")
    return HttpResponse(template.render({"team": team}, request))


@login_required
@require_safe
def team_leave_tab(request):
    """Lazy-loaded content for the dashboard "Team Leave Requests" tab.

    The overlap-with-scheduled-work badge is resolved with an Exists() subquery
    annotation (overlaps_work_ann) instead of a per-row .exists() call.
    """
    if not request.user.is_people_manager():
        return HttpResponseForbidden()

    team_leave = team_leave_requests(request.user)
    template = loader.get_template("partials/team_leave_table.html")
    return HttpResponse(template.render({"team_leave": team_leave}, request))
