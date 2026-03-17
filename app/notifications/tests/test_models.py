from datetime import timedelta

from django.test import TestCase
from django.db import IntegrityError
from django.utils import timezone

from chaotica_utils.models import User
from notifications.models import (
    Notification,
    NotificationSubscription,
    NotificationOptOut,
    NotificationCategory,
)
from notifications.enums import NotificationTypes


class NotificationModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )

    def test_creation(self):
        n = Notification.objects.create(
            user=self.user,
            title="Alert",
            message="Something happened",
        )
        self.assertIsNotNone(n.pk)
        self.assertEqual(n.user, self.user)
        self.assertEqual(n.title, "Alert")
        self.assertEqual(n.message, "Something happened")

    def test_str(self):
        n = Notification.objects.create(
            user=self.user,
            title="Test",
            message="msg",
        )
        self.assertEqual(str(n), f"Test - {self.user}")

    def test_get_human_timestamp_just_now(self):
        n = Notification.objects.create(
            user=self.user, title="T", message="M"
        )
        Notification.objects.filter(pk=n.pk).update(timestamp=timezone.now())
        n.refresh_from_db()
        self.assertEqual(n.get_human_timestamp(), "just now")

    def test_get_human_timestamp_minutes_ago(self):
        n = Notification.objects.create(
            user=self.user, title="T", message="M"
        )
        Notification.objects.filter(pk=n.pk).update(
            timestamp=timezone.now() - timedelta(minutes=5)
        )
        n.refresh_from_db()
        result = n.get_human_timestamp()
        self.assertIn("minute", result)

    def test_get_human_timestamp_hours_ago(self):
        n = Notification.objects.create(
            user=self.user, title="T", message="M"
        )
        Notification.objects.filter(pk=n.pk).update(
            timestamp=timezone.now() - timedelta(hours=2)
        )
        n.refresh_from_db()
        result = n.get_human_timestamp()
        self.assertIn("hour", result)

    def test_default_read_false(self):
        n = Notification.objects.create(
            user=self.user, title="T", message="M"
        )
        self.assertFalse(n.read)

    def test_default_is_emailed_false(self):
        n = Notification.objects.create(
            user=self.user, title="T", message="M"
        )
        self.assertFalse(n.is_emailed)

    def test_default_notification_type_system(self):
        n = Notification.objects.create(
            user=self.user, title="T", message="M"
        )
        self.assertEqual(n.notification_type, NotificationTypes.SYSTEM)

    def test_metadata_default_empty_dict(self):
        n = Notification.objects.create(
            user=self.user, title="T", message="M"
        )
        self.assertEqual(n.metadata, {})


class NotificationSubscriptionModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="sub@example.com",
            password="testpass123",
        )

    def test_creation(self):
        sub = NotificationSubscription.objects.create(
            user=self.user,
            notification_type=NotificationTypes.SYSTEM,
        )
        self.assertIsNotNone(sub.pk)

    def test_str_without_entity(self):
        sub = NotificationSubscription.objects.create(
            user=self.user,
            notification_type=NotificationTypes.SYSTEM,
        )
        result = str(sub)
        self.assertIn("System", result)
        self.assertNotIn("#", result)

    def test_str_with_entity(self):
        sub = NotificationSubscription.objects.create(
            user=self.user,
            notification_type=NotificationTypes.JOB_CREATED,
            entity_id=123,
            entity_type="Job",
        )
        result = str(sub)
        self.assertIn("Job #123", result)

    def test_unique_together_constraint(self):
        # MySQL allows duplicate NULL in unique constraints, so use non-null values
        NotificationSubscription.objects.create(
            user=self.user,
            notification_type=NotificationTypes.SYSTEM,
            entity_id=1,
            entity_type="Job",
        )
        with self.assertRaises(IntegrityError):
            NotificationSubscription.objects.create(
                user=self.user,
                notification_type=NotificationTypes.SYSTEM,
                entity_id=1,
                entity_type="Job",
            )

    def test_different_entity_allowed(self):
        NotificationSubscription.objects.create(
            user=self.user,
            notification_type=NotificationTypes.SYSTEM,
            entity_id=1,
            entity_type="Job",
        )
        sub2 = NotificationSubscription.objects.create(
            user=self.user,
            notification_type=NotificationTypes.SYSTEM,
            entity_id=2,
            entity_type="Job",
        )
        self.assertIsNotNone(sub2.pk)

    def test_default_email_enabled(self):
        sub = NotificationSubscription.objects.create(
            user=self.user,
            notification_type=NotificationTypes.SYSTEM,
        )
        self.assertTrue(sub.email_enabled)

    def test_default_in_app_enabled(self):
        sub = NotificationSubscription.objects.create(
            user=self.user,
            notification_type=NotificationTypes.SYSTEM,
        )
        self.assertTrue(sub.in_app_enabled)


class NotificationOptOutModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="optout@example.com",
            password="testpass123",
        )

    def test_creation(self):
        opt = NotificationOptOut.objects.create(
            user=self.user,
            notification_type=NotificationTypes.SYSTEM,
            entity_type="Job",
            entity_id=42,
        )
        self.assertIsNotNone(opt.pk)

    def test_unique_together_constraint(self):
        NotificationOptOut.objects.create(
            user=self.user,
            notification_type=NotificationTypes.SYSTEM,
            entity_type="Job",
            entity_id=42,
        )
        with self.assertRaises(IntegrityError):
            NotificationOptOut.objects.create(
                user=self.user,
                notification_type=NotificationTypes.SYSTEM,
                entity_type="Job",
                entity_id=42,
            )


class NotificationCategoryModelTests(TestCase):
    def test_creation(self):
        cat = NotificationCategory.objects.create(
            name="Test Category",
            description="A test category",
        )
        self.assertIsNotNone(cat.pk)

    def test_str(self):
        cat = NotificationCategory.objects.create(name="Test Category")
        self.assertEqual(str(cat), "Test Category")
