"""Tests for the central audit trail (Phase 1): the writer service, actor
resolution, auth-event signals, the dual-write from ``log_system_activity``, and
the permission-scoped read helper."""

from django.conf import settings
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from chaotica_utils.enums import GlobalRoles
from chaotica_utils.models import (
    User,
    Group,
    Holiday,
    AuditEvent,
    AuditVerb,
    AuditCategory,
    AuditSource,
)
from chaotica_utils.audit import (
    record_audit,
    diff_model,
    audit_events_for,
    user_is_global_admin,
    UNSET,
)
from chaotica_utils.middleware.common import set_current_user
from chaotica_utils.views.common import log_system_activity


def _give_user_role(user):
    group, _ = Group.objects.get_or_create(
        name=settings.GLOBAL_GROUP_PREFIX + GlobalRoles.CHOICES[GlobalRoles.USER][1]
    )
    user.groups.add(group)


@override_settings(ALLOWED_HOSTS=["*", "testserver", "localhost"])
class AuditWriterTests(TestCase):
    def setUp(self):
        # First create_user is auto-promoted to superuser + Global: Admin.
        self.admin = User.objects.create_user(email="admin@test.com", password="pw12345")
        self.user = User.objects.create_user(email="user@test.com", password="pw12345")
        _give_user_role(self.user)
        # A concrete object to hang events on.
        self.target = Holiday.objects.create(date="2026-01-01", reason="Test Day")
        self.addCleanup(set_current_user, None)

    def test_explicit_actor_is_recorded(self):
        set_current_user(None)
        event = record_audit(
            self.target, AuditVerb.UPDATE, message="edited", actor=self.user
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.actor_repr, str(self.user))
        self.assertEqual(event.target_repr, str(self.target))
        self.assertEqual(event.target_id, str(self.target.pk))

    def test_actor_falls_back_to_thread_local(self):
        set_current_user(self.user)
        event = record_audit(self.target, AuditVerb.UPDATE, message="edited")
        self.assertEqual(event.actor, self.user)
        # Source inferred as WEB when a request user is present.
        self.assertEqual(event.source, AuditSource.WEB)

    def test_explicit_none_forces_system(self):
        set_current_user(self.user)
        event = record_audit(self.target, AuditVerb.SYNC, message="job", actor=None)
        self.assertIsNone(event.actor)
        self.assertEqual(event.actor_repr, "")
        self.assertTrue(event.is_system_note)
        self.assertEqual(event.source, AuditSource.SYSTEM)

    def test_unset_with_no_thread_local_is_system(self):
        set_current_user(None)
        event = record_audit(self.target, AuditVerb.OTHER, actor=UNSET)
        self.assertIsNone(event.actor)

    def test_secrets_are_scrubbed(self):
        event = record_audit(
            self.target,
            AuditVerb.OTHER,
            actor=self.user,
            changes={"password": "hunter2", "status": ["a", "b"]},
            metadata={"api_key": "abc123", "path": "/x"},
        )
        self.assertEqual(event.changes["password"], "***")
        self.assertEqual(event.changes["status"], ["a", "b"])
        self.assertEqual(event.metadata["api_key"], "***")
        self.assertEqual(event.metadata["path"], "/x")

    def test_write_never_raises(self):
        # A target with no pk / broken str shouldn't blow up the caller.
        class Broken:
            pk = None

            def __str__(self):
                raise ValueError("boom")

        # Should swallow and return None rather than propagate.
        self.assertIsNone(record_audit(Broken(), AuditVerb.OTHER))

    def test_diff_model_reports_only_changed_fields(self):
        # Load both from the DB so field values are properly typed (avoids a
        # string-vs-date artifact from the ``date="..."`` create kwarg).
        before = Holiday.objects.get(pk=self.target.pk)
        after = Holiday.objects.get(pk=self.target.pk)
        after.reason = "Changed Day"
        changes = diff_model(before, after)
        self.assertIn("reason", changes)
        self.assertEqual(changes["reason"], ["Test Day", "Changed Day"])
        self.assertNotIn("date", changes)

    def test_compatibility_aliases(self):
        event = record_audit(self.target, AuditVerb.OTHER, message="hi", actor=self.user)
        self.assertEqual(event.content, "hi")
        self.assertEqual(event.create_date, event.timestamp)
        self.assertEqual(event.author, self.user)
        self.assertFalse(event.is_system_note)


@override_settings(ALLOWED_HOSTS=["*", "testserver", "localhost"])
class AuditReadScopingTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email="admin@test.com", password="pw12345")
        self.user = User.objects.create_user(email="user@test.com", password="pw12345")
        _give_user_role(self.user)
        self.target = Holiday.objects.create(date="2026-02-01", reason="Scope Day")
        record_audit(self.target, AuditVerb.UPDATE, message="general", actor=self.admin)
        record_audit(
            self.target,
            AuditVerb.PERMISSION_CHANGE,
            message="security",
            actor=self.admin,
            category=AuditCategory.SECURITY,
        )
        self.addCleanup(set_current_user, None)

    def test_admin_check(self):
        self.assertTrue(user_is_global_admin(self.admin))
        self.assertFalse(user_is_global_admin(self.user))

    def test_non_admin_cannot_see_sensitive_rows(self):
        events = list(audit_events_for(self.target, self.user))
        cats = {e.category for e in events}
        self.assertIn(AuditCategory.GENERAL, cats)
        self.assertNotIn(AuditCategory.SECURITY, cats)

    def test_admin_sees_all_rows(self):
        events = list(audit_events_for(self.target, self.admin))
        cats = {e.category for e in events}
        self.assertIn(AuditCategory.GENERAL, cats)
        self.assertIn(AuditCategory.SECURITY, cats)


@override_settings(ALLOWED_HOSTS=["*", "testserver", "localhost"])
class LogSystemActivityTests(TestCase):
    """After the cutover, log_system_activity writes only an AuditEvent (system
    activity no longer creates a Note; user-authored notes are unaffected)."""

    def setUp(self):
        self.user = User.objects.create_user(email="admin@test.com", password="pw12345")
        self.target = Holiday.objects.create(date="2026-03-01", reason="Dual Day")
        self.addCleanup(set_current_user, None)

    def test_writes_audit_event_and_no_system_note(self):
        from chaotica_utils.models import Note

        event = log_system_activity(self.target, "Something happened", author=self.user)
        # Returns the AuditEvent (compat properties keep legacy callers working).
        self.assertEqual(event.content, "Something happened")
        self.assertEqual(event.actor, self.user)
        self.assertEqual(
            AuditEvent.objects.filter(message="Something happened").count(), 1
        )
        # No system Note is created anymore.
        self.assertEqual(Note.objects.filter(is_system_note=True).count(), 0)

    def test_uses_thread_local_when_author_missing(self):
        set_current_user(self.user)
        log_system_activity(self.target, "No author passed")
        event = AuditEvent.objects.filter(message="No author passed").first()
        self.assertIsNotNone(event)
        self.assertEqual(event.actor, self.user)


@override_settings(ALLOWED_HOSTS=["*", "testserver", "localhost"])
class AuthSignalAuditTests(TestCase):
    def setUp(self):
        # Custom SessionMiddleware rejects requests without a Host header.
        self.client = Client(HTTP_HOST="localhost")
        self.user = User.objects.create_user(email="admin@test.com", password="pw12345")

    def test_successful_login_is_audited(self):
        self.client.login(email="admin@test.com", password="pw12345")
        event = AuditEvent.objects.filter(verb=AuditVerb.LOGIN).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.category, AuditCategory.AUTH)
        self.assertEqual(event.actor, self.user)

    def test_failed_login_is_audited_without_password(self):
        self.client.login(email="admin@test.com", password="wrongpassword")
        event = AuditEvent.objects.filter(verb=AuditVerb.LOGIN_FAILED).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.category, AuditCategory.AUTH)
        self.assertIsNone(event.actor)  # SYSTEM: no authenticated user
        # The password must never be persisted anywhere on the event.
        blob = f"{event.message} {event.changes} {event.metadata}"
        self.assertNotIn("wrongpassword", blob)
        self.assertIn("admin@test.com", event.metadata.get("identifier", ""))
