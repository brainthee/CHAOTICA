"""Skills, services and qualifications: data shared by the catalogue pages
and /api/v1/."""

from datetime import timedelta

from django.db.models import (
    Case,
    Count,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from chaotica_utils.models import User

from ..enums import PhaseStatuses, QualificationStatus, UserSkillRatings
from ..models import Service, Skill, SkillCategory, UserSkill


def skill_matrix(users, unit=None, team=None, category=None, role=None):
    """Rows of the skills matrix: ``(categories, rows)`` where each row is
    ``{user, skills: {skill_id: {skill, user_skill, rating, interested}}}``.

    ``users`` is the starting set (the page passes every active user with a
    role; the API narrows it to people whose skills the viewer may see).
    Filters take a unit slug, team slug, category slug and unit-role id.
    """
    if unit:
        users = users.filter(
            unit_memberships__unit__slug=unit, unit_memberships__left_date__isnull=True
        )
    if team:
        users = users.filter(teams__team__slug=team, teams__left_at__isnull=True)
    if role:
        users = users.filter(
            unit_memberships__roles__id=role, unit_memberships__left_date__isnull=True
        )
    users = (
        users.distinct()
        .prefetch_related(
            Prefetch(
                "skills",
                queryset=UserSkill.objects.select_related(
                    "skill", "skill__category"
                ).only("skill", "rating", "interested_in_improving_skill", "user"),
            )
        )
        .get_default_order()
    )

    categories = SkillCategory.objects.all()
    if category:
        categories = categories.filter(slug=category)
    categories = list(
        categories.prefetch_related(
            Prefetch(
                "skills",
                queryset=Skill.objects.only(
                    "id", "name", "slug", "description", "category"
                ),
            )
        )
        .only("id", "name", "slug")
        .order_by("name")
    )

    rows = []
    for user in users:
        held = {us.skill_id: us for us in user.skills.all()}
        cells = {}
        for cat in categories:
            for skill in cat.skills.all():
                us = held.get(skill.id)
                cells[skill.id] = {
                    "skill": skill,
                    "user_skill": us,
                    "rating": us.rating if us else UserSkillRatings.NO_EXPERIENCE,
                    "interested": us.interested_in_improving_skill if us else False,
                }
        rows.append({"user": user, "skills": cells})
    return categories, rows


def skill_matrix_filter_options():
    from ..models import OrganisationalUnit, OrganisationalUnitRole, Team

    return {
        "all_units": list(
            OrganisationalUnit.objects.order_by("name").values("slug", "name")
        ),
        "all_teams": list(Team.objects.order_by("name").values("slug", "name")),
        "all_categories": list(
            SkillCategory.objects.order_by("name").values("slug", "name")
        ),
        "all_org_roles": list(
            OrganisationalUnitRole.objects.order_by("name").values("name", "id")
        ),
    }


def matrix_users():
    """The skills page's starting set: active users holding a global role."""
    return User.objects.filter(is_active=True, groups__isnull=False)


def service_list_with_risk():
    """Services annotated with specialist / skilled-people / active-phase
    counts and a 0 (critical) – 3 (low) risk score."""
    from ..models import Phase

    # One subquery per figure: three joined Counts multiplied required skills
    # × their user ratings × phases before counting (a ~0.6s cross join).
    def count(qs):
        counted = qs.order_by().values("_g").annotate(n=Count("pk")).values("n")
        return Coalesce(Subquery(counted, output_field=IntegerField()), 0)

    required = UserSkill.objects.filter(
        skill__services_skill_required=OuterRef("pk")
    ).annotate(_g=Value(1, output_field=IntegerField()))
    return (
        Service.objects.prefetch_related("skillsRequired", "skillsDesired", "owners")
        .annotate(
            specialist_count=count(
                required.filter(rating=UserSkillRatings.SPECIALIST)
            ),
            skilled_people_count=count(required),
            active_phases_count=count(
                Phase.objects.filter(
                    service=OuterRef("pk"), status__in=PhaseStatuses.SERVICE_ACTIVE
                ).annotate(_g=Value(1, output_field=IntegerField()))
            ),
            risk_score=Case(
                When(specialist_count=0, then=0),
                When(specialist_count=1, then=1),
                When(specialist_count=2, then=2),
                default=3,
                output_field=IntegerField(),
            ),
        )
        .order_by("-is_core", "risk_score", "name")
    )


def skill_rating_counts(skill):
    """``{rating: count}`` of active people holding ``skill``."""
    return dict(
        UserSkill.objects.filter(skill=skill, user__is_active=True)
        .values_list("rating")
        .annotate(n=Count("id"))
    )


def qualification_record_stats(qualification, today):
    """The qualification page's status counts in one query."""
    soon = today + timedelta(days=90)
    return qualification.users.aggregate(
        awarded=Count("id", filter=Q(status=QualificationStatus.AWARDED)),
        in_progress=Count(
            "id",
            filter=Q(
                status__in=[
                    QualificationStatus.IN_PROGRESS,
                    QualificationStatus.PENDING,
                ]
            ),
        ),
        lapsed=Count("id", filter=Q(status=QualificationStatus.LAPSED)),
        expiring_soon=Count(
            "id",
            filter=Q(
                status=QualificationStatus.AWARDED,
                lapse_date__isnull=False,
                lapse_date__lte=soon,
                lapse_date__gt=today,
            ),
        ),
    )
