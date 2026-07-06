from django.test import TestCase

from chaotica_utils.models import User
from jobtracker.enums import QualificationStatus
from jobtracker.models import AwardingBody, Qualification, QualificationRecord, Service


class ServiceQualificationTests(TestCase):
    """Service <-> Qualification M2M and required-qualification readiness."""

    def setUp(self):
        self.body = AwardingBody.objects.create(name="CREST")
        self.qual_a = Qualification.objects.create(
            awarding_body=self.body, name="Certified Tester App", short_name="CCT APP"
        )
        self.qual_b = Qualification.objects.create(
            awarding_body=self.body, name="Certified Tester Inf", short_name="CCT INF"
        )
        self.service = Service.objects.create(name="Web Application Assessment")

        self.holder_all = User.objects.create_user(
            email="all@test.com", password="testpass123"
        )
        self.holder_partial = User.objects.create_user(
            email="partial@test.com", password="testpass123"
        )
        self.holder_none = User.objects.create_user(
            email="none@test.com", password="testpass123"
        )

    def _award(self, user, qual, status=QualificationStatus.AWARDED):
        return QualificationRecord.objects.create(
            user=user, qualification=qual, status=status
        )

    def test_can_assign_required_and_desired_qualifications(self):
        self.service.qualificationsRequired.add(self.qual_a)
        self.service.qualificationsDesired.add(self.qual_b)
        self.assertIn(self.qual_a, self.service.qualificationsRequired.all())
        self.assertIn(self.qual_b, self.service.qualificationsDesired.all())
        # reverse accessors
        self.assertIn(self.service, self.qual_a.services_qual_required.all())
        self.assertIn(self.service, self.qual_b.services_qual_desired.all())

    def test_no_required_quals_returns_empty(self):
        # A service with no required qualifications imposes no constraint.
        self.assertEqual(
            list(self.service.get_users_with_required_quals()), []
        )

    def test_user_holding_all_required_quals_included(self):
        self.service.qualificationsRequired.add(self.qual_a, self.qual_b)
        self._award(self.holder_all, self.qual_a)
        self._award(self.holder_all, self.qual_b)

        result = list(self.service.get_users_with_required_quals())
        self.assertIn(self.holder_all, result)

    def test_user_holding_partial_quals_excluded(self):
        self.service.qualificationsRequired.add(self.qual_a, self.qual_b)
        self._award(self.holder_partial, self.qual_a)  # only one of two

        result = list(self.service.get_users_with_required_quals())
        self.assertNotIn(self.holder_partial, result)

    def test_user_with_no_quals_excluded(self):
        self.service.qualificationsRequired.add(self.qual_a)
        result = list(self.service.get_users_with_required_quals())
        self.assertNotIn(self.holder_none, result)

    def test_non_awarded_status_does_not_count(self):
        self.service.qualificationsRequired.add(self.qual_a)
        self._award(self.holder_partial, self.qual_a, status=QualificationStatus.LAPSED)

        result = list(self.service.get_users_with_required_quals())
        self.assertNotIn(self.holder_partial, result)

    def test_inactive_user_excluded(self):
        self.service.qualificationsRequired.add(self.qual_a)
        self._award(self.holder_all, self.qual_a)
        self.holder_all.is_active = False
        self.holder_all.save()

        result = list(self.service.get_users_with_required_quals())
        self.assertNotIn(self.holder_all, result)
