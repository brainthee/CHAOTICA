"""The signed-in user's own profile (``/api/v1/me/``)."""

from django.conf import settings
from django.db.models import Prefetch


def current_memberships(user):
    """The user's current unit memberships with units and roles loaded."""
    from jobtracker.models import OrganisationalUnitMember

    return list(
        OrganisationalUnitMember.objects.filter(member=user, left_date__isnull=True)
        .select_related("unit")
        .prefetch_related("roles")
        .order_by("unit__name")
    )


def global_role_names(user):
    prefix = settings.GLOBAL_GROUP_PREFIX
    return sorted(
        g.name[len(prefix) :] for g in user.groups.all() if g.name.startswith(prefix)
    )


def current_user_profile(user, policy):
    """Everything a client needs about the caller in one round trip.

    Plain data (refs are rendered by the serializer layer): the user, current
    memberships, managers, job level, global roles and capabilities.
    """
    from chaotica_utils.models import User, UserJobLevel

    user = (
        User.objects.select_related("manager", "acting_manager", "city")
        .prefetch_related(
            "groups",
            Prefetch(
                "job_level_history",
                queryset=UserJobLevel.objects.filter(is_current=True).select_related(
                    "job_level"
                ),
                to_attr="_current_levels",
            ),
        )
        .get(pk=user.pk)
    )
    level = user.get_current_level()
    return {
        "user": user,
        "job_level": level.job_level if level else None,
        "memberships": current_memberships(user),
        "global_roles": global_role_names(user),
        "capabilities": policy.global_capabilities(),
    }
