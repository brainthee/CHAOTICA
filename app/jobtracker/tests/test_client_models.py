from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from chaotica_utils.models import User
from jobtracker.models.client import Client, Contact, ClientOnboarding, FrameworkAgreement


class ClientTests(TestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            email="am@test.com", password="testpass123"
        )

    def test_creation_and_slug(self):
        client = Client.objects.create(name="Acme Corp")
        self.assertTrue(client.slug)

    def test_str(self):
        client = Client.objects.create(name="Acme Corp")
        self.assertEqual(str(client), "Acme Corp")

    def test_get_absolute_url(self):
        client = Client.objects.create(name="Acme Corp")
        url = client.get_absolute_url()
        self.assertIn(client.slug, url)

    def test_is_ready_for_jobs_with_am(self):
        client = Client.objects.create(name="Acme Corp")
        client.account_managers.add(self.user)
        self.assertTrue(client.is_ready_for_jobs())

    def test_is_ready_for_jobs_without_am(self):
        client = Client.objects.create(name="Acme Corp")
        self.assertFalse(client.is_ready_for_jobs())

    def test_merge_moves_contacts(self):
        client1 = Client.objects.create(name="Primary Client")
        client2 = Client.objects.create(name="Secondary Client")
        contact = Contact.objects.create(
            first_name="John", last_name="Doe", company=client2
        )
        client1.merge(client2)
        contact.refresh_from_db()
        self.assertEqual(contact.company, client1)

    def test_merge_moves_account_managers(self):
        client1 = Client.objects.create(name="Primary Client")
        client2 = Client.objects.create(name="Secondary Client")
        client2.account_managers.add(self.user)
        client1.merge(client2)
        self.assertIn(self.user, client1.account_managers.all())

    def test_merge_deletes_source(self):
        client1 = Client.objects.create(name="Primary Client")
        client2 = Client.objects.create(name="Secondary Client")
        client2_pk = client2.pk
        client1.merge(client2)
        self.assertFalse(Client.objects.filter(pk=client2_pk).exists())


class ContactTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client_obj = Client.objects.create(name="Test Client")

    def test_creation(self):
        contact = Contact.objects.create(
            first_name="John", last_name="Doe", company=self.client_obj
        )
        self.assertEqual(contact.first_name, "John")
        self.assertEqual(contact.last_name, "Doe")
        self.assertEqual(contact.company, self.client_obj)

    def test_get_full_name(self):
        contact = Contact.objects.create(
            first_name="John", last_name="Doe", company=self.client_obj
        )
        self.assertEqual(contact.get_full_name(), "John Doe")


class ClientOnboardingTests(TestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            email="user@test.com", password="testpass123"
        )
        self.client_obj = Client.objects.create(
            name="Test Client",
            onboarding_required=True,
            onboarding_reoccurring_renewal=True,
            onboarding_reqs_renewal=365,
            onboarding_reqs_reminder_days=30,
        )

    def _create_onboarding(self, **kwargs):
        defaults = {"user": self.user, "client": self.client_obj}
        defaults.update(kwargs)
        return ClientOnboarding.objects.create(**defaults)

    # --- status() tests ---

    def test_status_active(self):
        """Onboarded in the past, no recurring renewal -> active."""
        self.client_obj.onboarding_reoccurring_renewal = False
        self.client_obj.save()
        ob = self._create_onboarding(onboarded=timezone.now() - timedelta(days=10))
        self.assertEqual(ob.status(), "active")

    def test_status_pending(self):
        """Onboarded in the future -> pending."""
        ob = self._create_onboarding(onboarded=timezone.now() + timedelta(days=10))
        self.assertEqual(ob.status(), "pending")

    def test_status_offboarded(self):
        """Offboarded in the past -> offboarded."""
        ob = self._create_onboarding(
            onboarded=timezone.now() - timedelta(days=30),
            offboarded=timezone.now() - timedelta(days=1),
        )
        self.assertEqual(ob.status(), "offboarded")

    def test_status_stale_no_reqs_completed(self):
        """Recurring renewal required, reqs_completed=None -> stale."""
        ob = self._create_onboarding(
            onboarded=timezone.now() - timedelta(days=10),
            reqs_completed=None,
        )
        self.assertEqual(ob.status(), "stale")

    def test_status_stale_expired_renewal(self):
        """reqs_completed long ago, renewal period has passed -> stale."""
        ob = self._create_onboarding(
            onboarded=timezone.now() - timedelta(days=500),
            reqs_completed=timezone.now() - timedelta(days=400),
        )
        self.assertEqual(ob.status(), "stale")

    def test_status_active_renewed(self):
        """reqs_completed recently, renewal not yet due -> active."""
        ob = self._create_onboarding(
            onboarded=timezone.now() - timedelta(days=30),
            reqs_completed=timezone.now() - timedelta(days=10),
        )
        self.assertEqual(ob.status(), "active")

    def test_status_unknown_no_dates(self):
        """No onboarded, no offboarded -> unknown."""
        ob = self._create_onboarding()
        self.assertEqual(ob.status(), "unknown")

    # --- property tests ---

    def test_is_active_property(self):
        self.client_obj.onboarding_reoccurring_renewal = False
        self.client_obj.save()
        ob = self._create_onboarding(onboarded=timezone.now() - timedelta(days=10))
        self.assertTrue(ob.is_active)

    def test_is_stale_property(self):
        ob = self._create_onboarding(
            onboarded=timezone.now() - timedelta(days=10),
            reqs_completed=None,
        )
        self.assertTrue(ob.is_stale)

    def test_is_offboarded_property(self):
        ob = self._create_onboarding(
            onboarded=timezone.now() - timedelta(days=30),
            offboarded=timezone.now() - timedelta(days=1),
        )
        self.assertTrue(ob.is_offboarded)

    # --- days_till_renewal() tests ---

    def test_days_till_renewal_with_data(self):
        reqs_completed = timezone.now() - timedelta(days=100)
        ob = self._create_onboarding(
            onboarded=timezone.now() - timedelta(days=200),
            reqs_completed=reqs_completed,
        )
        expected = (reqs_completed + timedelta(days=365) - timezone.now()).days
        self.assertAlmostEqual(ob.days_till_renewal(), expected, delta=1)

    def test_days_till_renewal_no_renewal(self):
        self.client_obj.onboarding_reoccurring_renewal = False
        self.client_obj.save()
        ob = self._create_onboarding(
            onboarded=timezone.now() - timedelta(days=10),
        )
        self.assertEqual(ob.days_till_renewal(), 0)

    # --- is_due() tests ---

    def test_is_due_true(self):
        """reqs_completed long ago, past the renewal-reminder window -> True."""
        ob = self._create_onboarding(
            onboarded=timezone.now() - timedelta(days=500),
            reqs_completed=timezone.now() - timedelta(days=400),
        )
        self.assertTrue(ob.is_due())

    def test_is_due_false(self):
        """reqs_completed recently, well within window -> False."""
        ob = self._create_onboarding(
            onboarded=timezone.now() - timedelta(days=30),
            reqs_completed=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(ob.is_due())

    def test_is_due_no_recurring(self):
        """No recurring renewal -> False."""
        self.client_obj.onboarding_reoccurring_renewal = False
        self.client_obj.save()
        ob = self._create_onboarding(
            onboarded=timezone.now() - timedelta(days=30),
        )
        self.assertFalse(ob.is_due())


class FrameworkAgreementTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client_obj = Client.objects.create(name="Test Client")

    def test_creation(self):
        fa = FrameworkAgreement.objects.create(
            client=self.client_obj,
            name="FA 2025",
            start_date="2025-01-01",
            end_date="2025-12-31",
            total_days=100,
        )
        self.assertEqual(fa.name, "FA 2025")
        self.assertEqual(fa.total_days, 100)

    def test_str(self):
        fa = FrameworkAgreement.objects.create(
            client=self.client_obj,
            name="FA 2025",
            start_date="2025-01-01",
            end_date="2025-12-31",
            total_days=100,
        )
        self.assertEqual(str(fa), "FA 2025 (2025-01-01-2025-12-31)")

    def test_get_absolute_url(self):
        fa = FrameworkAgreement.objects.create(
            client=self.client_obj,
            name="FA 2025",
            start_date="2025-01-01",
            end_date="2025-12-31",
            total_days=100,
        )
        url = fa.get_absolute_url()
        self.assertIn(self.client_obj.slug, url)
        self.assertIn(str(fa.pk), url)
