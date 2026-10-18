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
from impersonate.signals import session_begin, session_end

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


def _audit_impersonation(impersonator, impersonating, request, started):
    from .models import AuditVerb, AuditCategory, AuditSeverity

    action = "started" if started else "stopped"
    record_audit(
        impersonating,
        AuditVerb.OTHER,
        message=f"Impersonation {action} by '{impersonator}'",
        actor=impersonator,
        category=AuditCategory.SECURITY,
        severity=AuditSeverity.WARNING,
        request=request,
        metadata={"impersonation": action},
    )


@receiver(session_begin, dispatch_uid="chaotica_utils.audit_impersonation_begin")
def audit_impersonation_begin(sender, impersonator, impersonating, request=None, **kwargs):
    _audit_impersonation(impersonator, impersonating, request, started=True)


@receiver(session_end, dispatch_uid="chaotica_utils.audit_impersonation_end")
def audit_impersonation_end(sender, impersonator, impersonating, request=None, **kwargs):
    _audit_impersonation(impersonator, impersonating, request, started=False)


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
    ("jobtracker", "BillingCodeAssignment"): "finance",
    ("chaotica_utils", "UserCost"): "finance",
    ("jobtracker", "Service"): "config",
    ("jobtracker", "Skill"): "config",
    ("jobtracker", "SkillCategory"): "config",
    ("jobtracker", "Team"): "config",
    ("jobtracker", "OrganisationalUnit"): "config",
    ("jobtracker", "OrganisationalUnitRole"): "security",
    ("notifications", "EmailTemplate"): "config",
    ("notifications", "SubscriptionRule"): "config",
    ("reporting", "Report"): "config",
    ("reporting", "ScheduledReport"): "config",
    ("oauth2_provider", "Application"): "security",  # Connected Apps
}

# (app_label, ModelName, m2m_field_name): AuditCategory value. Tracks
# add / remove / clear on the relation.
_AUDITED_M2M = {
    ("chaotica_utils", "User", "groups"): "security",  # global roles
    ("jobtracker", "OrganisationalUnitMember", "roles"): "security",
    ("jobtracker", "OrganisationalUnit", "leads"): "security",
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


# ---------------------------------------------------------------------------
# Deactivated accounts lose their OAuth2 app access straight away (DOT itself
# would keep honouring an issued token until it expires).
# ---------------------------------------------------------------------------


@receiver(pre_save, sender="chaotica_utils.User", dispatch_uid="oauth_note_active")
def _note_was_active(sender, instance, **kwargs):
    if instance.pk:
        instance._was_active = (
            sender.objects.filter(pk=instance.pk).values_list("is_active", flat=True).first()
        )


@receiver(post_save, sender="chaotica_utils.User", dispatch_uid="oauth_revoke_on_deactivate")
def _revoke_tokens_on_deactivate(sender, instance, created, **kwargs):
    if not created and getattr(instance, "_was_active", False) and not instance.is_active:
        from django.db import transaction

        from .oauth import revoke_user_tokens
        from .realtime import disconnect_user

        revoke_user_tokens(instance)
        transaction.on_commit(lambda: disconnect_user(instance.pk))


# ---------------------------------------------------------------------------
# CORS for Connected Apps: a browser app on a registered origin may call the
# API and the token endpoints (never other paths, never with cookies).
# ---------------------------------------------------------------------------

_APP_ORIGINS_KEY = "oauth_app_origins"


def connected_app_origins():
    from django.core.cache import cache

    origins = cache.get(_APP_ORIGINS_KEY)
    if origins is None:
        from oauth2_provider.models import get_application_model

        origins = set()
        for value in get_application_model().objects.values_list(
            "allowed_origins", flat=True
        ):
            origins.update(o.rstrip("/") for o in (value or "").split())
        cache.set(_APP_ORIGINS_KEY, origins, 3600)
    return origins


def _cors_for_connected_apps(sender, request, **kwargs):
    import re

    from constance import config
    from django.conf import settings

    if not config.API_OAUTH2_ENABLED:
        return False
    if not re.match(settings.CORS_URLS_REGEX, request.path_info):
        return False
    origin = request.headers.get("Origin", "").rstrip("/")
    return bool(origin) and origin in connected_app_origins()


def _forget_app_origins(sender, **kwargs):
    from django.core.cache import cache

    cache.delete(_APP_ORIGINS_KEY)


def connect_oauth_signals():
    from corsheaders.signals import check_request_enabled
    from django.db.models.signals import post_delete
    from oauth2_provider.models import get_application_model

    check_request_enabled.connect(
        _cors_for_connected_apps, dispatch_uid="cors_connected_apps"
    )
    app_model = get_application_model()
    post_save.connect(_forget_app_origins, sender=app_model, dispatch_uid="app_origins_save")
    post_delete.connect(
        _forget_app_origins, sender=app_model, dispatch_uid="app_origins_delete"
    )
