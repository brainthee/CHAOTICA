"""Import / adopt RM users into CHAOTICA, grouped by RM **Market Unit**.

RM's "Market Unit" custom field (``UKI``, ``Iberia``, ``Prague``, ``Nordics``, …) is a clean,
coarse grouping that maps naturally onto CHAOTICA org units. An :class:`RMUnitMap` row ties a
market unit to an OU **and** a sync direction (e.g. ``UKI`` → PUSH so CHAOTICA stays
authoritative; EU units → PULL so RM is authoritative).

Design rules (safety first — these exist because an earlier unscoped run flipped UKI users to
PULL):

* **Never clobber an existing direction.** A record that is already PUSH/PULL is left alone
  unless ``force_direction`` is set. Import only *sets* direction on new / ``OFF`` records.
* **Adopting existing users is additive.** Matching by email only fills a blank ``rm_id`` /
  ``market_unit``; it never repoints a real user. ``create_missing`` only affects users with
  no CHAOTICA match.
* **Import before mapping.** Every market unit seen gets an :class:`RMUnitMap` row auto-created
  with ``unit=None, direction=OFF, enabled=False`` so an admin can map it later and run
  :func:`apply_rm_unit_maps`. Users are imported even before their unit is mapped (OU-less).
* **OU assignment is non-invasive.** A user is only added to the mapped OU if they currently
  have no unit membership, so real users keep their existing units.
"""

import logging
from dataclasses import dataclass, field

from constance import config
from django.db.models import Q

from chaotica_utils.enums import GlobalRoles
from chaotica_utils.models import User

from .client import RMClient
from .enums import RMSyncDirection

logger = logging.getLogger("rm_sync")

# Legacy domain rewrite (opt-in via RM_SYNC_DOMAIN_REWRITE).
_DOMAIN_REWRITES = (
    ("accenture.com", "cyberdefense.global"),
    ("contextis.com", "cyberdefense.global"),
)

# RM 'role' → CHAOTICA OrganisationalUnitRole *name* (matched by name, not pk, since role
# pks can drift). Applied to a user's org-unit membership on import / apply.
RM_ROLE_MAP = {
    "Consultant": "Consultant",
    "Account Manager": "Sales",
    "Service Delivery Team": "Service Delivery",
}


def _ensure_default_global_role(user):
    """Give a freshly created RM user the base ('User') global role.

    Global roles are Django groups prefixed with ``GLOBAL_GROUP_PREFIX``; without at
    least the default one a user has no site-wide access at all. Mirrors the onboarding
    pre-load flow (``_preload_unit_member``) so RM-created accounts behave like users
    created any other way. No-op if they already hold any global role.
    """
    from django.conf import settings
    from django.contrib.auth.models import Group

    if user.groups.filter(name__startswith=settings.GLOBAL_GROUP_PREFIX).exists():
        return  # already has a global role — don't clobber
    name = settings.GLOBAL_GROUP_PREFIX + dict(GlobalRoles.CHOICES).get(
        GlobalRoles.DEFAULT_ROLE, "User"
    )
    grp = Group.objects.filter(name=name).first()
    if grp:
        user.groups.add(grp)


def _resolve_role(rm_role):
    """Resolve an RM role string to a CHAOTICA OrganisationalUnitRole (or None)."""
    name = RM_ROLE_MAP.get((rm_role or "").strip())
    if not name:
        return None
    from jobtracker.models import OrganisationalUnitRole

    return OrganisationalUnitRole.objects.filter(name=name).first()


@dataclass
class ImportResult:
    matched: int = 0  # existing CHAOTICA user matched by email
    created: int = 0  # new user created (create_missing)
    maps_created: int = 0  # new RMUnitMap rows auto-created for admin to fill in
    rm_id_set: int = 0
    rm_id_conflict: int = 0  # record already had a different rm_id (not overwritten)
    direction_set: int = 0
    direction_protected: int = 0  # existing PUSH/PULL left untouched
    ou_set: int = 0
    unmatched_rm: int = 0  # no CHAOTICA user and not creating
    skipped_no_email: int = 0
    skipped_no_market_unit: int = 0
    active_matches: int = 0  # matched users that look like real accounts (heads-up)
    errors: int = 0
    details: list = field(default_factory=list)

    def note(self, msg):
        self.details.append(msg)
        logger.info(msg)


# --------------------------------------------------------------------------- helpers
def _normalise_email(rm_user):
    email = (rm_user.get("email") or "").lower().strip()
    if email and config.RM_SYNC_DOMAIN_REWRITE:
        for src, dst in _DOMAIN_REWRITES:
            email = email.replace(src, dst)
    return email


def _market_unit(rm_user):
    """Extract the 'Market Unit' custom-field value from an RM user, or '' if absent."""
    cfv = rm_user.get("custom_field_values")
    entries = []
    if isinstance(cfv, dict):
        entries = cfv.get("data", [])
    elif isinstance(cfv, list):
        entries = cfv
    for entry in entries:
        name = entry.get("custom_field_name") or entry.get("name")
        if name == "Market Unit" and entry.get("value"):
            return str(entry["value"]).strip()
    return ""


def _looks_active(user):
    """Heuristic: does this look like a real account (vs an RM-only placeholder)?"""
    if user.has_usable_password() or user.last_login is not None:
        return True
    return user.timeslots.filter(rm_inbound__isnull=True).exists()


def _get_or_create_unit_map(market_unit, result, dry_run=False, seen_new=None):
    from .models import RMUnitMap

    if dry_run:
        umap = RMUnitMap.objects.filter(market_unit=market_unit).first()
        if umap is None and seen_new is not None and market_unit not in seen_new:
            seen_new.add(market_unit)
            result.maps_created += 1  # would be created (counted once per market unit)
        return umap
    umap, created = RMUnitMap.objects.get_or_create(
        market_unit=market_unit,
        defaults={"unit": None, "direction": RMSyncDirection.OFF, "enabled": False},
    )
    if created:
        result.maps_created += 1
    return umap


def _ensure_ou(user, unit, role=None):
    """Add the user to ``unit`` (non-invasively) and set their org-unit ``role``.

    Membership is only *created* if the user has no unit membership at all — so a real user
    already in another unit is left alone. If they are already in this unit, we still make sure
    the mapped role is present. ``membership.save()`` re-syncs that member's guardian
    permissions from their roles (per-member, so bulk import stays O(n)).
    """
    from jobtracker.models import OrganisationalUnitMember

    if unit is None:
        return False

    membership = user.unit_memberships.filter(unit=unit).first()
    if membership is None:
        if user.unit_memberships.exists():
            return False  # non-invasive: user already belongs to another unit
        membership = OrganisationalUnitMember.objects.create(member=user, unit=unit)
        changed = True
    else:
        changed = False

    if role is not None and not membership.roles.filter(pk=role.pk).exists():
        membership.roles.add(role)
        membership.save()  # sync this member's permissions from their roles
        changed = True
    return changed


def _apply_direction(rec, direction, force_direction, result):
    """Set ``rec.direction`` from a map, honouring the protect-existing-direction rule."""
    if direction is None or direction == RMSyncDirection.OFF:
        return False
    if rec.direction != RMSyncDirection.OFF and not force_direction:
        result.direction_protected += 1
        return False
    if rec.direction != direction:
        rec.direction = direction
        result.direction_set += 1
        return True
    return False


# --------------------------------------------------------------------------- core
def import_rm_users(
    client=None,
    create_missing=False,
    market_unit_filter=None,
    force_direction=False,
    overwrite_rm_id=False,
    dry_run=False,
):
    """Walk RM users, adopt/create the CHAOTICA side, and set rm_id/market_unit/direction/OU.

    See module docstring for the safety rules. Returns an :class:`ImportResult`.
    """
    client = client or RMClient()
    result = ImportResult()
    seen_new_maps = set()

    from .models import RMSyncRecord

    for rm_user in client.paginate(
        "/api/v1/users", {"per_page": 500, "fields": "custom_field_values"}
    ):
        try:
            market_unit = _market_unit(rm_user)
            if market_unit_filter and market_unit.lower() != market_unit_filter.lower():
                continue
            if not market_unit:
                result.skipped_no_market_unit += 1
                continue

            email = _normalise_email(rm_user)
            if not email:
                result.skipped_no_email += 1
                continue

            rm_id = str(rm_user["id"])
            rm_role = (rm_user.get("role") or "").strip()
            umap = _get_or_create_unit_map(
                market_unit, result, dry_run=dry_run, seen_new=seen_new_maps
            )
            target_direction = (
                umap.direction
                if (umap and umap.enabled and umap.unit_id is not None)
                else None
            )
            target_unit = umap.unit if (umap and umap.enabled) else None

            user = User.objects.filter(
                Q(email__iexact=email) | Q(notification_email__iexact=email)
            ).first()

            if user is None:
                if not create_missing:
                    result.unmatched_rm += 1
                    continue
                result.created += 1
                if dry_run:
                    continue
                user = User(
                    email=email,
                    first_name=(rm_user.get("first_name") or "").strip(),
                    last_name=(rm_user.get("last_name") or "").strip(),
                    is_active=True,
                )
                user.set_unusable_password()
                user.external_id = rm_id
                user.save()
                _ensure_default_global_role(user)
            else:
                result.matched += 1
                if _looks_active(user):
                    result.active_matches += 1
                if not user.external_id and not dry_run:
                    user.external_id = rm_id
                    user.save(update_fields=["external_id"])

            if dry_run:
                # Account for what would change without writing.
                rec = RMSyncRecord.objects.filter(user=user).first()
                if rec is None or not rec.rm_id:
                    result.rm_id_set += 1
                if target_direction:
                    if (
                        rec is None
                        or rec.direction == RMSyncDirection.OFF
                        or force_direction
                    ):
                        result.direction_set += 1
                    else:
                        result.direction_protected += 1
                continue

            _apply_record(
                user,
                rm_id,
                market_unit,
                rm_role,
                target_direction,
                target_unit,
                force_direction,
                overwrite_rm_id,
                result,
            )
        except Exception as ex:
            result.errors += 1
            logger.exception("Import error for RM user %s: %s", rm_user.get("id"), ex)

    return result


def _apply_record(
    user,
    rm_id,
    market_unit,
    rm_role,
    target_direction,
    target_unit,
    force_direction,
    overwrite_rm_id,
    result,
):
    from .models import RMSyncRecord

    role = _resolve_role(rm_role)

    rec = RMSyncRecord.objects.filter(user=user).first()
    if rec is None:
        rec = RMSyncRecord(
            user=user, rm_id=rm_id, market_unit=market_unit, rm_role=rm_role
        )
        result.rm_id_set += 1
        _apply_direction(rec, target_direction, force_direction, result)
        rec.save()
        if _ensure_ou(user, target_unit, role=role):
            result.ou_set += 1
        return

    changed = []
    if rec.rm_id != rm_id:
        if rec.rm_id and not overwrite_rm_id:
            result.rm_id_conflict += 1
            result.note(
                "rm_id conflict for {}: existing {} vs RM {} (use --overwrite-rm-id)".format(
                    user.email, rec.rm_id, rm_id
                )
            )
        else:
            rec.rm_id = rm_id
            changed.append("rm_id")
            result.rm_id_set += 1
    if rec.market_unit != market_unit:
        rec.market_unit = market_unit
        changed.append("market_unit")
    if rm_role and rec.rm_role != rm_role:
        rec.rm_role = rm_role
        changed.append("rm_role")
    if _apply_direction(rec, target_direction, force_direction, result):
        changed.append("direction")
    if changed:
        rec.save(update_fields=changed)
    if _ensure_ou(user, target_unit, role=role):
        result.ou_set += 1


# --------------------------------------------------------------------------- wrappers
def sync_rm_users(client=None, dry_run=False):
    """Adopt existing + create missing RM users (used by the cron task and run_rm_users)."""
    return import_rm_users(client=client, create_missing=True, dry_run=dry_run)


def match_rm_users(
    client=None,
    market_unit_filter=None,
    create_missing=False,
    force_direction=False,
    overwrite_rm_id=False,
    dry_run=False,
):
    """Adopt existing CHAOTICA users by email (optionally creating missing ones)."""
    return import_rm_users(
        client=client,
        create_missing=create_missing,
        market_unit_filter=market_unit_filter,
        force_direction=force_direction,
        overwrite_rm_id=overwrite_rm_id,
        dry_run=dry_run,
    )


# --------------------------------------------------------------------------- apply maps
@dataclass
class ApplyResult:
    ou_set: int = 0
    direction_set: int = 0
    direction_protected: int = 0
    records: int = 0
    errors: int = 0


def apply_rm_unit_maps(force_direction=False, dry_run=False):
    """Push each enabled RMUnitMap's OU + direction onto its market unit's users.

    Run this after an admin has filled in the OU / direction on the auto-created map rows.
    Honours the protect-existing-direction rule; OU assignment stays non-invasive.
    """
    from .models import RMSyncRecord, RMUnitMap

    result = ApplyResult()
    for umap in RMUnitMap.objects.filter(enabled=True, unit__isnull=False):
        for rec in RMSyncRecord.objects.filter(
            market_unit=umap.market_unit
        ).select_related("user"):
            try:
                result.records += 1
                # Direction
                if umap.direction != RMSyncDirection.OFF:
                    if rec.direction != RMSyncDirection.OFF and not force_direction:
                        result.direction_protected += 1
                    elif rec.direction != umap.direction:
                        result.direction_set += 1
                        if not dry_run:
                            rec.direction = umap.direction
                            rec.save(update_fields=["direction"])
                # OU (+ mapped role from the user's RM role)
                if not rec.user.unit_memberships.exists():
                    result.ou_set += 1
                    if not dry_run:
                        _ensure_ou(rec.user, umap.unit, role=_resolve_role(rec.rm_role))
            except Exception:
                result.errors += 1
                logger.exception("apply_rm_unit_maps error for %s", rec.user)
    return result
