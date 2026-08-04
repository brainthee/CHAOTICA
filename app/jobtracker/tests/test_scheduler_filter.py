"""Tests for SchedulerFilter's tolerance of stale PKs in a saved default view.

Regression: the scheduler stores a user's saved "default view" as raw PKs. With
the stock ``ModelMultipleChoiceField``, a single stale PK (a teammate who left,
a deleted job/phase) made the whole form invalid, so every filter was silently
dropped and the user fell back to the full unfiltered schedule. The lenient
fields drop only the stale entries and keep the rest of the filter working.
"""
from django.http import QueryDict
from django.test import TestCase

from chaotica_utils.models import User
from jobtracker.models import OrganisationalUnit
from jobtracker.forms import SchedulerFilter


class SchedulerFilterLenientTests(TestCase):
    def setUp(self):
        super().setUp()
        self.active = User.objects.create_user(
            email="active@test.com", password="pw12345"
        )
        self.gone = User.objects.create_user(
            email="gone@test.com", password="pw12345"
        )
        self.unit = OrganisationalUnit.objects.create(name="Unit A")

    def _bind(self, **params):
        qd = QueryDict(mutable=True)
        for key, values in params.items():
            qd.setlist(key, values if isinstance(values, list) else [values])
        return SchedulerFilter(qd)

    def test_deactivated_user_pk_is_dropped_not_fatal(self):
        # gone@ is excluded from the field queryset once deactivated.
        self.gone.is_active = False
        self.gone.save()

        form = self._bind(users=[str(self.active.pk), str(self.gone.pk)])

        self.assertTrue(form.is_valid(), form.errors)
        selected = list(form.cleaned_data["users"])
        self.assertEqual(selected, [self.active])

    def test_nonexistent_pk_is_dropped(self):
        form = self._bind(users=[str(self.active.pk), "99999999"])

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(list(form.cleaned_data["users"]), [self.active])

    def test_malformed_pk_is_dropped(self):
        # Hand-edited/garbage URL value must not 500 or invalidate the form.
        form = self._bind(users=[str(self.active.pk), "not-a-pk"])

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(list(form.cleaned_data["users"]), [self.active])

    def test_other_filters_survive_a_stale_user(self):
        # The key regression: a stale user PK must not wipe *other* filters.
        self.gone.is_active = False
        self.gone.save()

        form = self._bind(
            users=[str(self.active.pk), str(self.gone.pk)],
            org_units=[str(self.unit.pk)],
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(list(form.cleaned_data["users"]), [self.active])
        self.assertEqual(list(form.cleaned_data["org_units"]), [self.unit])

    def test_stale_single_choice_becomes_none(self):
        # filter_by_city pointing at a deleted City must not invalidate the form.
        form = self._bind(filter_by_city="99999999")

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["filter_by_city"])
