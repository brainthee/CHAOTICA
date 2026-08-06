"""Signal receivers that feed the central audit trail.

Phase 1 wires authentication events (login / logout / failed login). Later
phases add finance/config ``post_save``/``pre_delete`` and ``m2m_changed``
handlers here. Connected from ``ChaoticaUtilsConfig.ready()``.
"""

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from .audit import record_audit


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
