"""Signal receivers that feed the central audit trail.

- Auth events (login / logout / failed login) auto-connect via ``@receiver``.
- Finance/config model CRUD and M2M relation changes are connected explicitly
  by :func:`connect_audit_signals`, called from ``ChaoticaUtilsConfig.ready()``
  (so it runs once the app registry is populated).
"""

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.db.models.signals import pre_save, post_save, pre_delete, m2m_changed
from django.dispatch import receiver

from .audit import record_audit, diff_model


@receiver(user_logged_in)
def audit_user_logged_in(sender, request, user, **kwargs):
    from .models import AuditVerb, AuditCategory

    record_audit(
        user,
        AuditVerb.LOGIN,
        message="Signed in",
        actor=user,
        category=AuditCategory.AUTH,
        request=request,
    )


@receiver(user_logged_out)
def audit_user_logged_out(sender, request, user, **kwargs):
    from .models import AuditVerb, AuditCategory

    # ``user`` can be None if the session was already anonymous.
    if user is None:
        return
    record_audit(
        user,
        AuditVerb.LOGOUT,
        message="Signed out",
        actor=user,
        category=AuditCategory.AUTH,
        request=request,
    )


@receiver(user_login_failed)
def audit_user_login_failed(sender, credentials=None, request=None, **kwargs):
    from .models import AuditVerb, AuditCategory, AuditSeverity

    # Never persist the password: capture only the attempted identifier.
    credentials = credentials or {}
    identifier = (
        credentials.get("username")
        or credentials.get("email")
        or credentials.get("upn")
        or "unknown"
    )
    record_audit(
        None,
        AuditVerb.LOGIN_FAILED,
        message=f"Failed login attempt for '{identifier}'",
        actor=None,
        category=AuditCategory.AUTH,
        severity=AuditSeverity.WARNING,
        request=request,
        metadata={"identifier": identifier},
    )


# ---------------------------------------------------------------------------
# Phase 2: finance / config model CRUD + M2M relation changes.
#
# Declarative registries keep "add a model to the audit trail" a one-line
# change. ``connect_audit_signals`` wires the generic handlers below to each
# named model/relation with a stable ``dispatch_uid`` so re-entry is a no-op.
# ---------------------------------------------------------------------------

# (app_label, ModelName): AuditCategory value. Tracks create / update (diffed)
# / delete on plain models.
_AUDITED_MODELS = {
    ("jobtracker", "BillingCode"): "finance",
    ("chaotica_utils", "UserCost"): "finance",
    ("jobtracker", "Service"): "config",
    ("jobtracker", "Skill"): "config",
    ("jobtracker", "SkillCategory"): "config",
    ("jobtracker", "Team"): "config",
    ("jobtracker", "OrganisationalUnit"): "config",
    ("jobtracker", "OrganisationalUnitRole"): "security",
    ("notifications", "EmailTemplate"): "config",
}

# (app_label, ModelName, m2m_field_name): AuditCategory value. Tracks
# add / remove / clear on the relation.
_AUDITED_M2M = {
    ("chaotica_utils", "User", "groups"): "security",  # global roles
    ("jobtracker", "OrganisationalUnitMember", "roles"): "security",
    ("jobtracker", "OrganisationalUnit", "leads"): "security",
    ("jobtracker", "Job", "charge_codes"): "finance",
    ("jobtracker", "Skill", "prerequisites"): "config",
    ("jobtracker", "Skill", "related_skills"): "config",
}


def _audit_pre_save(sender, instance, **kwargs):
    """Snapshot the pre-change row so ``post_save`` can diff an update."""
    if instance.pk is None:
        instance._audit_old = None
        return
    try:
        instance._audit_old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        instance._audit_old = None


def _audit_post_save(sender, instance, created, category, **kwargs):
    from .models import AuditVerb

    verbose = instance._meta.verbose_name
    if created:
        record_audit(
            instance,
            AuditVerb.CREATE,
            message=f"{verbose} created: {instance}",
            category=category,
        )
        return
    old = getattr(instance, "_audit_old", None)
    changes = diff_model(old, instance) if old is not None else None
    if not changes:
        return  # no tracked field actually changed
    record_audit(
        instance,
        AuditVerb.UPDATE,
        message=f"{verbose} updated: {instance}",
        category=category,
        changes=changes,
    )


def _audit_pre_delete(sender, instance, category, **kwargs):
    from .models import AuditVerb

    verbose = instance._meta.verbose_name
    record_audit(
        instance,
        AuditVerb.DELETE,
        message=f"{verbose} deleted: {instance}",
        category=category,
    )


def _audit_m2m_changed(sender, instance, action, pk_set, field_name, category, **kwargs):
    from .models import AuditVerb

    if action not in ("post_add", "post_remove", "post_clear"):
        return
    if action in ("post_add", "post_remove") and not pk_set:
        return
    verb = AuditVerb.ASSIGN if action == "post_add" else AuditVerb.UNASSIGN
    ids = sorted(pk_set) if pk_set else []
    key = {
        "post_add": "added",
        "post_remove": "removed",
        "post_clear": "cleared",
    }[action]
    record_audit(
        instance,
        verb,
        message=f"{field_name} {key} on {instance}",
        category=category,
        changes={field_name: {key: ids}},
    )


def connect_audit_signals():
    """Wire the finance/config CRUD + M2M handlers. Idempotent."""
    from django.apps import apps
    from functools import partial

    for (app_label, model_name), category in _AUDITED_MODELS.items():
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            continue
        uid = f"audit_{app_label}_{model_name}"
        pre_save.connect(
            _audit_pre_save, sender=model, dispatch_uid=uid + "_presave", weak=False
        )
        post_save.connect(
            partial(_audit_post_save, category=category),
            sender=model,
            dispatch_uid=uid + "_postsave",
            weak=False,
        )
        pre_delete.connect(
            partial(_audit_pre_delete, category=category),
            sender=model,
            dispatch_uid=uid + "_predelete",
            weak=False,
        )

    for (app_label, model_name, field_name), category in _AUDITED_M2M.items():
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            continue
        through = getattr(model, field_name).through
        m2m_changed.connect(
            partial(_audit_m2m_changed, field_name=field_name, category=category),
            sender=through,
            dispatch_uid=f"audit_m2m_{app_label}_{model_name}_{field_name}",
            weak=False,
        )
