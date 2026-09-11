"""Regression tests for BillingCode.jobs()/phases()/projects() target resolution.

Job and Project use a ``db_id`` primary key distinct from their business ``id``
field. ``BillingCode.jobs()`` used to resolve the FK values (which are PKs =
``db_id``) against the business ``id`` field, so a code would surface the *wrong*
job/project whenever some other record's business ``id`` collided with the
target's ``db_id``. This reproduces that collision.
"""

from django.test import TestCase

from chaotica_utils.models import User
from jobtracker.models import (
    BillingCode,
    BillingCodeAssignment,
    Client,
    Job,
    OrganisationalUnit,
    Phase,
)


class BillingCodeTargetResolutionTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_user(email="root-bct@test.com", password="pw")
        self.unit = OrganisationalUnit.objects.create(name="U-bct")
        self.client_obj = Client.objects.create(name="C-bct")

    def _job(self, business_id):
        return Job.objects.create(
            id=business_id,
            title="J%s" % business_id,
            client=self.client_obj,
            unit=self.unit,
            created_by=self.root,
            account_manager=self.root,
        )

    def test_jobs_resolves_by_pk_not_business_id(self):
        job_a = self._job(90000)
        # A second job whose *business id* equals job_a's *db_id* (PK). The old
        # id__in lookup would return this job for a code assigned to job_a.
        job_b = self._job(job_a.db_id)
        self.assertNotEqual(job_a.db_id, job_b.db_id)

        code = BillingCode.objects.create(code="X-JOB-1")
        BillingCodeAssignment.objects.create(code=code, job=job_a)

        result = list(code.jobs())
        self.assertEqual(result, [job_a])
        self.assertNotIn(job_b, result)

    def test_phases_resolve_correctly(self):
        job = self._job(90001)
        phase = Phase.objects.create(job=job, phase_number=1, title="P1")
        code = BillingCode.objects.create(code="X-PHASE-1")
        BillingCodeAssignment.objects.create(code=code, phase=phase)
        self.assertEqual(list(code.phases()), [phase])

    def test_charge_codes_reverse_matches(self):
        # Job.charge_codes should agree with BillingCode.jobs() (both by pk).
        job = self._job(90002)
        code = BillingCode.objects.create(code="X-JOB-2")
        BillingCodeAssignment.objects.create(code=code, job=job)
        self.assertIn(code, list(job.charge_codes))
        self.assertIn(job, list(code.jobs()))
