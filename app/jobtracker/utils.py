import logging
import os
from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.http import HttpResponseForbidden, HttpResponseNotFound
from django.shortcuts import render
from django.template import loader
from chaotica_utils.views import page_defaults
from guardian.conf import settings as guardian_settings
from .models import Job, Phase, OrganisationalUnit, TimeSlot
from .forms import SchedulerFilter
from django.http import JsonResponse, HttpResponse
from django.db.models import Q
from chaotica_utils.models import User, UserJobLevel
from guardian.shortcuts import get_objects_for_user
from .models import (
    Job,
    TimeSlot,
    UserSkill,
    Phase,
    OrganisationalUnitMember,
    OrganisationalUnitRole,
    TimeSlotComment,
)
from .enums import UserSkillRatings
import logging
from chaotica_utils.utils import (
    clean_fullcalendar_datetime, is_ajax
)
from chaotica_utils.models import Holiday
from constance import config
from random import randrange



logger = logging.getLogger(__name__)
abspath = lambda *p: os.path.abspath(os.path.join(*p))


def get_unit_40x_or_None(
    request,
    perms,
    obj=None,
    login_url=None,
    redirect_field_name=None,
    return_403=False,
    return_404=False,
    accept_global_perms=False,
    any_perm=False,
):
    login_url = login_url or settings.LOGIN_URL
    redirect_field_name = redirect_field_name or REDIRECT_FIELD_NAME
    has_permissions = False

    if request.user.is_authenticated:
        # global perms check first (if accept_global_perms)
        if accept_global_perms:
            has_permissions = all(request.user.has_perm(perm) for perm in perms)
        # if still no permission granted, try obj perms
        if not has_permissions:
            if any_perm:
                has_permissions = any(request.user.has_perm(perm, obj) for perm in perms)
            else:
                has_permissions = all(request.user.has_perm(perm, obj) for perm in perms)
        # Ok, now lets check unit permissions...
        if not has_permissions:
            unit = None
            if obj:
                if isinstance(obj, Job):
                    unit = obj.unit
                if isinstance(obj, Phase):
                    unit = obj.job.unit
                if isinstance(obj, OrganisationalUnit):
                    unit = obj
            else:
                # get our own units
                membership = request.user.unit_memberships.first()
                unit = membership.unit if membership else None
            if unit:
                if any_perm:
                    has_permissions = any(
                        request.user.has_perm(perm, unit) for perm in perms
                    )
                else:
                    has_permissions = all(
                        request.user.has_perm(perm, unit) for perm in perms
                    )

    if not has_permissions:
        if return_403:
            if guardian_settings.RENDER_403:
                response = render(request, guardian_settings.TEMPLATE_403)
                response.status_code = 403
                return response
            elif guardian_settings.RAISE_403:
                raise PermissionDenied
            return HttpResponseForbidden()
        if return_404:
            if guardian_settings.RENDER_404:
                response = render(request, guardian_settings.TEMPLATE_404)
                response.status_code = 404
                return response
            elif guardian_settings.RAISE_404:
                raise ObjectDoesNotExist
            return HttpResponseNotFound()
        else:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(
                request.get_full_path(), login_url, redirect_field_name
            )




def _filter_users_on_query(request, cleaned_data=None):
    query = Q()


    show_inactive_users = cleaned_data.get("show_inactive_users")

    # Starting users filter
    users_pk = []
    # This pre-loads which users we can see the schedule of.
    # It's actually not ideal because if we view a job/phase,
    # but say we don't have permission to see the schedule of someone - we can't see a complete schedule for that job
    for org_unit in get_objects_for_user(
        request.user, "jobtracker.view_users_schedule"
    ):
        for user in org_unit.get_allMembers():
            if user.pk not in users_pk:
                users_pk.append(user.pk)

    onboarded_to = cleaned_data.get("onboarded_to")
    if onboarded_to:
        users_onboarded = []
        for client in onboarded_to:
            for onboarded in client.onboarded_users.all():
                if onboarded.is_active:
                    users_onboarded.append(onboarded.user.pk)
        query.add(Q(pk__in=users_onboarded), Q.AND)

    teams = cleaned_data.get("teams")
    if teams:
        users_memberof = []
        for team in teams:
            for usr in team.get_activeMembers():
                users_memberof.append(usr.pk)
        query.add(Q(pk__in=users_memberof), Q.AND)

    # If we're passed a job/phase ID - filter on that.
    jobs = cleaned_data.get("jobs")
    if jobs:
        for job in jobs:
            query.add(Q(pk__in=job.team()), Q.AND)

    phases = cleaned_data.get("phases")
    if phases:
        for phase in phases:
            query.add(Q(pk__in=phase.team()), Q.AND)

    if not jobs and not phases:
        query.add(Q(pk__in=users_pk), Q.AND)

    # Now lets apply the filters from the query...
    ## Filter users
    if not show_inactive_users:
        query.add(Q(is_active=True), Q.AND)

    users_q = cleaned_data.get("users")
    if users_q:
        query.add(Q(pk__in=users_q), Q.AND)

    ## Filter org unit
    org_units = cleaned_data.get("org_units")
    org_unit_roles = cleaned_data.get("org_unit_roles")

    if org_units:
        query.add(
            Q(
                unit_memberships__in=OrganisationalUnitMember.objects.filter(
                    unit__in=org_units,
                    roles__in=(
                        org_unit_roles
                        if org_unit_roles
                        else OrganisationalUnitRole.objects.all()
                    ),
                )
            ),
            Q.AND,
        )
    else:
        if org_unit_roles:
            query.add(
                Q(
                    unit_memberships__in=OrganisationalUnitMember.objects.filter(
                        roles__in=org_unit_roles,
                    )
                ),
                Q.AND,
            )

    ## Filter on skills
    skills_specialist = cleaned_data.get("skills_specialist")
    if skills_specialist:
        query.add(
            Q(
                skills__in=UserSkill.objects.filter(
                    skill__in=skills_specialist, rating=UserSkillRatings.SPECIALIST
                )
            ),
            Q.AND,
        )

    skills_can_do_alone = cleaned_data.get("skills_can_do_alone")
    if skills_can_do_alone:
        query.add(
            Q(
                skills__in=UserSkill.objects.filter(
                    skill__in=skills_can_do_alone,
                    rating=UserSkillRatings.CAN_DO_ALONE,
                )
            ),
            Q.AND,
        )

    skills_can_do_support = cleaned_data.get("skills_can_do_support")
    if skills_can_do_support:
        query.add(
            Q(
                skills__in=UserSkill.objects.filter(
                    skill__in=skills_can_do_support,
                    rating=UserSkillRatings.CAN_DO_WITH_SUPPORT,
                )
            ),
            Q.AND,
        )

    # Filter on service
    # This is a bit mind bending. Of the service(s) selected, each will have some desired/needed skills
    # We then need to select the users based off containing a skill in either desired or needed..
    services = cleaned_data.get("services")
    for service in services:
        query.add(Q(pk__in=service.can_conduct()), Q.AND)

    # Filter by job levels
    job_levels = cleaned_data.get("job_levels")
    if job_levels:
        users_with_job_levels = []
        for level in job_levels:
            current_assignments = UserJobLevel.objects.filter(
                job_level=level,
                is_current=True
            ).values_list('user_id', flat=True)
            users_with_job_levels.extend(current_assignments)
        if users_with_job_levels:
            query.add(Q(pk__in=users_with_job_levels), Q.AND)

    extra_users = cleaned_data.get("include_user")
    if extra_users:
        query.add(
            Q(pk__in=extra_users),
            Q.OR,
        )

    return (
        User.objects.filter(query)
        .distinct()
        .order_by("last_name", "first_name")
        .prefetch_related("timeslots")
    )


def merge_include_users(request, users):
    """Union any ?include_user=<pk> users into a scoped member list, so the
    schedule 'Add User' tool can surface someone not yet scheduled on the
    job/phase. Returns a User QuerySet (get_bulk_stats needs a queryset)."""
    ids = {u.pk for u in users}
    for i in request.GET.getlist("include_user"):
        if str(i).isdigit():
            ids.add(int(i))
    return User.objects.filter(pk__in=ids)


def assigned_role_map(job, phase=None):
    """Map user_pk -> [role labels] for a job (optionally a single phase).
    Account Manager / Deputy AM / Scoping come from the job; Lead / Author /
    Tech QA / Pres QA from the phase(s). Used to tag scheduler resources and to
    surface assigned-but-unscheduled people in the team allocation widget."""
    role_map = {}

    def _add(pk, label):
        if not pk:
            return
        lst = role_map.setdefault(pk, [])
        if label not in lst:
            lst.append(label)

    if job is not None:
        _add(job.account_manager_id, "Account Manager")
        _add(job.dep_account_manager_id, "Deputy AM")
        for sid in job.scoped_by.values_list("pk", flat=True):
            _add(sid, "Scoping")
        phases = [phase] if phase is not None else list(job.phases.all())
        for ph in phases:
            _add(ph.project_lead_id, "Lead")
            _add(ph.report_author_id, "Author")
            _add(ph.techqa_by_id, "Tech QA")
            _add(ph.presqa_by_id, "Pres QA")
    return role_map


def get_scheduler_members(request, filtered_users = None, start = None, end = None, use_filter_form=True, role_job=None, role_phase=None):
    data = []
    selected_phases = []
    cleaned_data = None

    if use_filter_form:
        filter_form = SchedulerFilter(request.GET)
        if filter_form.is_valid():
            cleaned_data = filter_form.clean()

            jobs = cleaned_data.get("jobs", [])
            for job in jobs:
                selected_phases.append(job)
            phases = cleaned_data.get("phases", [])
            for phase in phases:
                selected_phases.append(phase)

    if filtered_users is None:
        filtered_users = _filter_users_on_query(request, cleaned_data).prefetch_related(
            "unit_memberships", "unit_memberships__unit", "job_level_history", "job_level_history__job_level"
        )

    # Per-user role map for job/phase-scoped views (Account Manager / Lead /
    # Author / QA etc.), so each resource can be tagged with their role(s).
    role_map = assigned_role_map(role_job, role_phase) if role_job is not None else {}

    # Change FullCalendar format to DateTime
    if not start:
        start = clean_fullcalendar_datetime(request.GET.get("start", None))
    if not end:
        end = clean_fullcalendar_datetime(request.GET.get("end", None))

    stats = User.objects.get_bulk_stats(
        filtered_users,
        start_date=start,
        end_date=end,
    )

    # Check if we need to order by distance
    filter_by_city = cleaned_data.get("filter_by_city") if cleaned_data else None
    ordering = cleaned_data.get("ordering", "title") if cleaned_data else "title"
    ordering_direction = cleaned_data.get("ordering_direction", False) if cleaned_data else False
    
    if filter_by_city and ordering == "distance":
        # Sort users by distance to the selected city
        user_distance_pairs = []
        for user_id, user_stat in stats['current']['by_user'].items():
            user = user_stat['user']
            distance = user.get_distance_to_city(filter_by_city)
            user_distance_pairs.append((user_stat, distance))
        
        # Sort by distance (closest first by default, or farthest first if reverse)
        reverse_sort = ordering_direction
        user_distance_pairs.sort(key=lambda x: (x[1] is None, x[1] or float('inf')), reverse=reverse_sort)
    else:
        # Convert to list for consistent processing
        user_distance_pairs = [(user_stat, None) for user_stat in stats['current']['by_user'].values()]
        
        # Apply other ordering if not distance-based
        if ordering == "title":
            user_distance_pairs.sort(key=lambda x: x[0]['user_name'], reverse=ordering_direction)
        elif ordering == "last_name, first_name":
            user_distance_pairs.sort(key=lambda x: (x[0]['user'].last_name, x[0]['user'].first_name), reverse=ordering_direction)
        elif ordering == "availability":
            user_distance_pairs.sort(key=lambda x: x[0]['available_percentage'] or 0, reverse=ordering_direction)
        elif ordering == "util":
            user_distance_pairs.sort(key=lambda x: x[0]['utilisation_percentage'] or 0, reverse=ordering_direction)
        elif ordering == "seniority":
            # This would need to be implemented based on job levels
            pass

    for user_stat, distance in user_distance_pairs:
        user = user_stat['user']
        user_title = user_stat['user_name']
        main_org = user_stat['main_org']
        user_roles = role_map.get(user.pk, [])

        # Get user's current job level
        current_job_level = UserJobLevel.get_current_level(user)
        job_level_order = current_job_level.job_level.order if current_job_level else 999
        job_level_label = str(current_job_level.job_level) if current_job_level else "No Level"

        data.append(
            {
                "id": user.pk,
                "title": user_title,
                "roles": user_roles,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "availability": user_stat['available_percentage'] if user_stat['available_percentage'] else 0,
                "util": user_stat['utilisation_percentage'] if user_stat['utilisation_percentage'] else 0,
                "seniority": job_level_order,
                "job_level": job_level_label,
                "url": user.get_absolute_url(),
                "html_view": user.get_table_display_html(cleaned_data.get("compressed_view", False) if cleaned_data else False),
                "distance": round(distance, 1) if distance is not None else None,
                "distance_display": f"{round(distance, 1)} km" if distance is not None else "N/A",
                "businessHours": (
                    {
                        "startTime": main_org.businessHours_startTime,
                        "endTime": main_org.businessHours_endTime,
                        "daysOfWeek": main_org.businessHours_days,
                    }
                    if main_org
                    else {
                        "startTime": "",
                        "endTime": "",
                        "daysOfWeek": "",
                    }
                ),
                "workingHours": (
                    {
                        "startTime": main_org.businessHours_startTime,
                        "endTime": main_org.businessHours_endTime,
                        "daysOfWeek": main_org.businessHours_days,
                    }
                    if main_org
                    else {
                        "startTime": "",
                        "endTime": "",
                        "daysOfWeek": "",
                    }
                ),
            }
        )
    

    return JsonResponse(data, safe=False)


def get_scheduler_slots(request, filtered_users = None, start = None, end = None, use_filter_form=True, scope_phases=None, hard_scope=True):
    data = []
    selected_phases = []
    cleaned_data = None

    if use_filter_form:
        filter_form = SchedulerFilter(request.GET)
        if filter_form.is_valid():
            cleaned_data = filter_form.clean()

            jobs = cleaned_data.get("jobs", [])
            for job in jobs:
                selected_phases.append(job)
            phases = cleaned_data.get("phases", [])
            for phase in phases:
                selected_phases.append(phase)

    if filtered_users is None:
        filtered_users = _filter_users_on_query(request, cleaned_data).prefetch_related(
            "unit_memberships", "unit_memberships__unit", "job_level_history__job_level"
        )

    # "bounds" mode: return the real min/max extent of the relevant slots so the
    # UI's Fit control can zoom to the DATA AVAILABLE (not just the loaded buffer,
    # which makes repeated Fit creep outward).
    if request.GET.get("bounds"):
        from django.db.models import Min, Max
        bqs = TimeSlot.objects.filter(user__in=filtered_users)
        if scope_phases is not None:
            bqs = bqs.filter(phase_id__in=[p.pk for p in scope_phases])
        agg = bqs.aggregate(lo=Min("start"), hi=Max("end"))
        return JsonResponse({
            "start": agg["lo"].isoformat() if agg["lo"] else None,
            "end": agg["hi"].isoformat() if agg["hi"] else None,
        })

    # Change FullCalendar format to DateTime
    if not start:
        start = clean_fullcalendar_datetime(request.GET.get("start", None))
    if not end:
        end = clean_fullcalendar_datetime(request.GET.get("end", None))

    schedule_colours = {
        "SCHEDULE_COLOR_PHASE_CONFIRMED_AWAY": str(
            config.SCHEDULE_COLOR_PHASE_CONFIRMED_AWAY
        ),
        "SCHEDULE_COLOR_PHASE_CONFIRMED": str(config.SCHEDULE_COLOR_PHASE_CONFIRMED),
        "SCHEDULE_COLOR_PHASE_AWAY": str(config.SCHEDULE_COLOR_PHASE_AWAY),
        "SCHEDULE_COLOR_PHASE": str(config.SCHEDULE_COLOR_PHASE),
        "SCHEDULE_COLOR_PROJECT": str(config.SCHEDULE_COLOR_PROJECT),
        "SCHEDULE_COLOR_INTERNAL": str(config.SCHEDULE_COLOR_INTERNAL),
        "SCHEDULE_COLOR_COMMENT": str(config.SCHEDULE_COLOR_COMMENT),
    }

    compressed_view = cleaned_data.get("compressed_view", False) if cleaned_data else False

    scope_phase_ids = set(p.pk for p in scope_phases) if scope_phases is not None else None

    # Load the timeslots
    slot_qs = TimeSlot.objects.filter(
        user__in=filtered_users, end__gte=start, start__lte=end
    )
    if scope_phase_ids is not None and hard_scope:
        # Hard job/phase scope — restrict to that job/phase's slots only.
        slot_qs = slot_qs.filter(phase_id__in=scope_phase_ids)
    for slot in slot_qs.prefetch_related(
        "phase",
        "phase__job",
        "phase__job__client",
        "project",
        "slot_type",
        "user",
        "leaverequest",
    ):
        slot_json = slot.get_schedule_json(schedule_colours=schedule_colours, compressed_view=compressed_view)
        if selected_phases:
            if slot.phase and (
                slot.phase not in selected_phases
                and slot.phase.job not in selected_phases
            ):
                slot_json["display"] = "background"
        # Soft-scope: keep the member's other commitments visible but faded so
        # it's clear which blocks belong to this job/phase (vs. context).
        if scope_phase_ids is not None and not hard_scope and slot.phase_id not in scope_phase_ids:
            slot_json["out_of_scope"] = True
        data.append(slot_json)

    # Add the holidays
    holidays = Holiday.objects.filter(date__gte=start.date(), date__lte=end.date())
    for user in filtered_users:
        for hol in holidays:
            if user.country == hol.country:
                data.append(
                    {
                        "title": str(hol),
                        "start": hol.date,
                        "end": hol.date,
                        "allDay": True,
                        "display": "background",
                        "id": hol.pk,
                        "resourceId": user.pk,
                    }
                )

    # Add the comments
    for comment in TimeSlotComment.objects.filter(
        user__in=filtered_users, end__gte=start, start__lte=end
    ):
        data.append(comment.get_schedule_json(schedule_colours=schedule_colours))
    return JsonResponse(data, safe=False)