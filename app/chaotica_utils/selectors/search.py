"""Global site search and the "type an ID, jump to it" lookup.

Shared by the header search box (``views/autocomplete.py``) and
``/api/v1/search/``. Scoping is the search box's: jobs and phases by
``can_view_jobs`` on the unit, catalogue items by their ``view_*`` perms, and
active users for everyone (identity only — see the API debt register).
"""

import re

from django.db.models import Q, TextField, Value
from django.db.models.functions import Concat, Lower
from guardian.shortcuts import get_objects_for_user

from ..models import User

MIN_QUERY_LENGTH = 3
DEFAULT_LIMIT = 100

# Job IDs are plain integers (e.g. "1234"); Phase IDs are "<job id>-<phase
# number>" (e.g. "1234-1", the Phase.phase_id field).
PHASE_ID_RE = re.compile(r"^\d+-\d+$")


def _job_units(user, policy=None):
    from jobtracker.models import OrganisationalUnit

    if policy is not None:
        return policy.units("jobtracker.can_view_jobs")
    return get_objects_for_user(user, "jobtracker.can_view_jobs", OrganisationalUnit)


def site_search(user, q, limit=DEFAULT_LIMIT, policy=None):
    """``{group: [objects]}`` matching ``q`` (case-insensitive contains).

    Returns ``{}`` for queries shorter than :data:`MIN_QUERY_LENGTH`. Each list
    is evaluated, at most ``limit`` long, with the relations the results render.
    """
    from jobtracker.models import (
        BillingCode,
        Client,
        Job,
        Phase,
        Project,
        Qualification,
        Service,
        Skill,
    )

    q = (q or "").strip().lower()
    if len(q) < MIN_QUERY_LENGTH:
        return {}
    units = _job_units(user, policy)

    def by_name(model, perm, field="name"):
        return (
            get_objects_for_user(user, perm, model)
            .annotate(_lower=Lower(field))
            .filter(_lower__contains=q)
        )

    return {
        "jobs": list(
            Job.objects.filter(unit__in=units)
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
            )[:limit]
        ),
        "phases": list(
            Phase.objects.filter(job__unit__in=units)
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
            )[:limit]
        ),
        "clients": list(by_name(Client, "jobtracker.view_client")[:limit]),
        "billing_codes": list(
            by_name(BillingCode, "jobtracker.view_billingcode", "code")[:limit]
        ),
        "services": list(by_name(Service, "jobtracker.view_service")[:limit]),
        "skills": list(
            by_name(Skill, "jobtracker.view_skill").select_related("category")[:limit]
        ),
        "qualifications": list(
            by_name(Qualification, "jobtracker.view_qualification").select_related(
                "awarding_body"
            )[:limit]
        ),
        "projects": list(
            get_objects_for_user(user, "*", Project)
            .annotate(_lower=Lower("title"))
            .filter(_lower__contains=q)[:limit]
        ),
        "users": list(
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
            )[
                :limit
            ]
        ),
    }


def resolve_goto(user, q, policy=None):
    """The job (``"1234"``) or phase (``"1234-1"``) ``q`` names, if the user
    can see it via the search scope; else ``None``."""
    from jobtracker.models import Job, Phase

    q = (q or "").strip()
    if not q:
        return None
    units = _job_units(user, policy)
    if PHASE_ID_RE.match(q):
        return (
            Phase.objects.filter(job__unit__in=units, phase_id=q)
            .select_related("job")
            .first()
        )
    if q.isdigit():
        return Job.objects.filter(unit__in=units, id=int(q)).first()
    return None
