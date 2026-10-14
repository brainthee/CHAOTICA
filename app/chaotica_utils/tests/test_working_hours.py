from datetime import time

from django.test import TestCase

from chaotica_utils.models import User


class DefaultWorkingHoursTests(TestCase):
    """A user with no unit membership falls back to the site default hours
    (previously raised TypeError, breaking range clears/bookings for them)."""

    def test_user_without_unit_gets_default_hours(self):
        user = User.objects.create_user(email="nounit@test.com", password="pw12345")
        self.assertEqual(
            user.get_working_hours(), {"start": time(9, 0), "end": time(17, 30)}
        )
