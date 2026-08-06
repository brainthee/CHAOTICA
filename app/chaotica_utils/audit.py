"""Central audit-trail writer service.

The single entry point is :func:`record_audit`; thin wrappers
(:func:`audit_create`, :func:`audit_update`, :func:`audit_delete`,
:func:`audit_status`) exist for readability at call sites. The read helper
:func:`audit_events_for` returns a permission-scoped queryset for the UI.

Design notes:
- Actor is resolved from the request thread-local unless passed explicitly, so
  most call sites need not thread ``request.user`` through.
- Writes never raise into the caller: an audit failure must not break a
  business transaction.
- ``changes``/``metadata`` are scrubbed of anything that looks like a secret.
- Model/middleware imports are lazy so this module is safe to import from
  models, signals, tasks, and views without circular-import risk.
"""

import logging

logger = logging.getLogger(__name__)

# Sentinel distinguishing "actor not supplied" (resolve from thread-local) from
# "explicitly SYSTEM" (actor=None).
UNSET = object()

# Substrings that mark a dict key as sensitive; its value is redacted.
_SECRET_HINTS = ("password", "passwd", "secret", "token", "api_key", "apikey", "credential")


def _scrub(data):
    """Redact secret-looking values from a dict (shallow + one level of nesting)."""
    if not isinstance(data, dict):
        return data
    cleaned = {}
    for key, value in data.items():
        lowered = str(key).lower()
        if any(hint in lowered for hint in _SECRET_HINTS):
            cleaned[key] = "***"
        elif isinstance(value, dict):
            cleaned[key] = _scrub(value)
        else:
            cleaned[key] = value
    return cleaned


def _resolve_actor(actor):
    from .middleware.common import get_current_user

    if actor is not UNSET:
        return actor  # explicit user, or explicit None (=SYSTEM)
    user = get_current_user()
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return user


def _infer_source(actor):
    from .models import AuditSource

    if actor is not None and getattr(actor, "is_authenticated", False):
        return AuditSource.WEB
    # No request user: distinguish a background worker from plain system code.
    try:
        from celery import current_task

        if current_task is not None and getattr(current_task, "request", None) and current_task.request.id:
            return AuditSource.CELERY
    except Exception:
        pass
    return AuditSource.SYSTEM


def _target_bits(target):
    """Return (content_type, str(pk), repr) for a model instance, or (None, None, "")."""
    if target is None:
        return None, None, ""
    from django.contrib.contenttypes.models import ContentType

    try:
        ct = ContentType.objects.get_for_model(target.__class__)
        pk = getattr(target, "pk", None)
        return ct, (str(pk) if pk is not None else None), str(target)[:255]
    except Exception:
        return None, None, str(target)[:255]


def record_audit(
    target,
    verb,
    *,
    message="",
    actor=UNSET,
    category=None,
    changes=None,
    source=None,
    severity=None,
    metadata=None,
    request=None,
):
    """Write an :class:`AuditEvent`. Returns the instance, or ``None`` on failure.

    ``actor`` defaults to the request thread-local user; pass ``None`` to force
    a SYSTEM event, or a specific user to override.
    """
    try:
        from .models import AuditEvent, AuditCategory, AuditSeverity

        resolved_actor = _resolve_actor(actor)
        if source is None:
            source = _infer_source(resolved_actor)
        if category is None:
            category = AuditCategory.GENERAL
        if severity is None:
            severity = AuditSeverity.INFO

        ct, target_id, target_repr = _target_bits(target)

        meta = dict(metadata) if metadata else {}
        if request is not None:
            meta.setdefault("ip", _client_ip(request))
            meta.setdefault("path", request.path)

        event = AuditEvent(
            actor=resolved_actor,
            actor_repr=(str(resolved_actor)[:255] if resolved_actor else ""),
            verb=verb,
            category=category,
            message=message or "",
            target_content_type=ct,
            target_id=target_id,
            target_repr=target_repr,
            source=source,
            severity=severity,
            changes=_scrub(changes) if changes else None,
            metadata=_scrub(meta) if meta else None,
        )
        event.save()
        return event
    except Exception:
        logger.exception("Failed to record audit event (verb=%s)", verb)
        return None


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# --- Convenience wrappers -----------------------------------------------------


def audit_create(target, *, message="", category=None, **kwargs):
    from .models import AuditVerb

    return record_audit(target, AuditVerb.CREATE, message=message, category=category, **kwargs)


def audit_update(target, *, changes=None, message="", category=None, **kwargs):
    from .models import AuditVerb

    return record_audit(
        target, AuditVerb.UPDATE, message=message, category=category, changes=changes, **kwargs
    )


def audit_delete(target, *, message="", category=None, **kwargs):
    from .models import AuditVerb

    return record_audit(target, AuditVerb.DELETE, message=message, category=category, **kwargs)


def audit_status(target, old, new, *, message="", category=None, **kwargs):
    from .models import AuditVerb

    return record_audit(
        target,
        AuditVerb.STATUS_CHANGE,
        message=message,
        category=category,
        changes={"status": [old, new]},
        **kwargs,
    )


# --- Diff helper --------------------------------------------------------------


def diff_model(old_instance, new_instance, fields=None):
    """Return a diff-only dict ``{field: [old, new]}`` of changed concrete fields.

    FK fields are compared by their raw ``*_id`` value (JSON-serialisable).
    """
    if old_instance is None or new_instance is None:
        return {}
    changes = {}
    for field in new_instance._meta.concrete_fields:
        if fields is not None and field.name not in fields:
            continue
        attname = field.attname  # ``*_id`` for FKs, field name otherwise
        old_value = getattr(old_instance, attname, None)
        new_value = getattr(new_instance, attname, None)
        if old_value != new_value:
            changes[field.name] = [_jsonify(old_value), _jsonify(new_value)]
    return changes


def _jsonify(value):
    from decimal import Decimal
    from datetime import date, datetime, time
    from uuid import UUID

    if isinstance(value, (Decimal, UUID, datetime, date, time)):
        return str(value)
    return value


# --- Read helpers -------------------------------------------------------------


def user_is_global_admin(user):
    from django.conf import settings
    from .enums import GlobalRoles

    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(
        name=settings.GLOBAL_GROUP_PREFIX + GlobalRoles.CHOICES[GlobalRoles.ADMIN][1]
    ).exists()


def audit_events_for(obj, viewer, limit=200):
    """Permission-scoped AuditEvents for ``obj``, newest first.

    Non-admins never see AUTH/SECURITY/FINANCE rows even on an object they can
    otherwise view.
    """
    from django.contrib.contenttypes.models import ContentType
    from .models import AuditEvent, SENSITIVE_CATEGORIES

    ct = ContentType.objects.get_for_model(obj.__class__)
    qs = AuditEvent.objects.filter(target_content_type=ct, target_id=str(obj.pk))
    if not user_is_global_admin(viewer):
        qs = qs.exclude(category__in=SENSITIVE_CATEGORIES)
    return qs[:limit]
