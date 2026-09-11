"""Tests for the versioned read-only /api/v1/ API.

Covers the guarantees that matter for this API: authentication is required,
endpoints are read-only, responses are clean JSON (no DataTables/HTML metadata),
access is scoped by the same guardian permissions the UI uses, and sensitive
fields are never serialized.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.test import override_settings
from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from cities_light.models import City, Country

from chaotica_utils.models import User, UserCost
from chaotica_utils.models.job_levels import JobLevel, UserJobLevel
from jobtracker.models import OrganisationalUnit, Skill, SkillCategory, UserSkill

from .api.v1.serializers import QualificationRecordSerializer, UserSerializer


# The custom SessionMiddleware validates the HTTP_HOST header (rejecting requests
# without one with a 400). Django's test client sends SERVER_NAME but no HTTP_HOST,
# so we set one explicitly; "testserver" is also pinned into ALLOWED_HOSTS for envs
# whose ALLOWED_HOSTS doesn't include a wildcard.
@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class APIV1BaseTest(APITestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient(HTTP_HOST="testserver")

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            email="admin@example.com", password="pw-admin"
        )
        cls.normal = User.objects.create_user(
            email="normal@example.com", password="pw-normal"
        )
        cls.category = SkillCategory.objects.create(name="Web")
        cls.skill = Skill.objects.create(name="XSS", category=cls.category)
        cls.user_skill = UserSkill.objects.create(
            user=cls.normal, skill=cls.skill, rating=2
        )


class AuthAndShapeTests(APIV1BaseTest):
    def test_requires_authentication(self):
        resp = self.client.get("/api/v1/skills/")
        self.assertIn(
            resp.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_token_obtain_and_use(self):
        resp = self.client.post(
            "/api/v1/auth/token/",
            {"username": "admin@example.com", "password": "pw-admin"},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("token", resp.data)

        token = resp.data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        listed = self.client.get("/api/v1/skills/")
        self.assertEqual(listed.status_code, status.HTTP_200_OK)

    def test_read_only_post_returns_405(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.post("/api/v1/skills/", {"name": "SQLi"})
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_clean_paginated_shape(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get("/api/v1/timeslot-types/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Standard DRF page-number shape, not the datatables shape.
        self.assertIn("count", resp.data)
        self.assertIn("results", resp.data)
        for row in resp.data["results"]:
            self.assertNotIn("DT_RowId", row)
            self.assertNotIn("DT_RowAttr", row)


class ScopingTests(APIV1BaseTest):
    def test_superuser_sees_all_skills(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get("/api/v1/skills/")
        self.assertEqual(resp.data["count"], 1)

    def test_unprivileged_user_sees_no_skills(self):
        # No guardian/global view_skill permission -> empty, never leaks.
        self.client.force_authenticate(self.normal)
        resp = self.client.get("/api/v1/skills/")
        self.assertEqual(resp.data["count"], 0)

    def test_user_sees_own_user_skill(self):
        self.client.force_authenticate(self.normal)
        resp = self.client.get("/api/v1/user-skills/")
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["user"], self.normal.pk)

    def test_user_does_not_see_others_user_skill(self):
        other = User.objects.create_user(
            email="other@example.com", password="pw-other"
        )
        UserSkill.objects.create(user=other, skill=self.skill, rating=3)
        self.client.force_authenticate(self.normal)
        resp = self.client.get("/api/v1/user-skills/")
        user_pks = {row["user"] for row in resp.data["results"]}
        self.assertNotIn(other.pk, user_pks)
        self.assertIn(self.normal.pk, user_pks)


class UserJobFieldsTests(APIV1BaseTest):
    def test_job_title_and_level_serialized(self):
        level = JobLevel.objects.create(
            short_label="JL5", long_label="Consultant", order=5
        )
        self.normal.job_title = "Senior Consultant"
        self.normal.save()
        UserJobLevel.objects.create(
            user=self.normal, job_level=level, is_current=True
        )

        self.client.force_authenticate(self.superuser)
        resp = self.client.get(f"/api/v1/users/{self.normal.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["job_title"], "Senior Consultant")
        self.assertEqual(resp.data["job_level"], "JL5")
        self.assertEqual(resp.data["job_level_label"], "Consultant")

    def test_level_null_when_unset(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get(f"/api/v1/users/{self.normal.pk}/")
        self.assertIsNone(resp.data["job_level"])
        self.assertIsNone(resp.data["job_level_label"])


class SetStatusActionTests(APIV1BaseTest):
    def _url(self, user):
        return f"/api/v1/users/{user.pk}/set-status/"

    def test_requires_manage_user_permission(self):
        # normal has no manage_user permission -> forbidden.
        self.client.force_authenticate(self.normal)
        resp = self.client.post(
            self._url(self.superuser), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_superuser_can_deactivate_and_reactivate(self):
        target = User.objects.create_user(
            email="target@example.com", password="pw", is_active=True
        )
        self.client.force_authenticate(self.superuser)

        resp = self.client.post(
            self._url(target), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["changed"])
        target.refresh_from_db()
        self.assertFalse(target.is_active)

        resp = self.client.post(
            self._url(target), {"is_active": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        target.refresh_from_db()
        self.assertTrue(target.is_active)

    def test_idempotent_no_op(self):
        target = User.objects.create_user(
            email="already@example.com", password="pw", is_active=True
        )
        self.client.force_authenticate(self.superuser)
        resp = self.client.post(
            self._url(target), {"is_active": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["changed"])

    def test_cannot_deactivate_self(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.post(
            self._url(self.superuser), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)

    def test_missing_body_is_400(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.post(self._url(self.normal), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_creation_still_blocked(self):
        # Enabling POST for the action must not open a user-creation route.
        self.client.force_authenticate(self.superuser)
        resp = self.client.post(
            "/api/v1/users/",
            {"email": "new@example.com", "first_name": "New"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class UpdateProfileActionTests(APIV1BaseTest):
    def _url(self, user):
        return f"/api/v1/users/{user.pk}/update-profile/"

    def test_stranger_forbidden(self):
        target = User.objects.create_user(email="t1@example.com", password="pw")
        self.client.force_authenticate(self.normal)
        resp = self.client.post(
            self._url(target), {"job_title": "Hacker"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_self_can_update_own_profile(self):
        self.client.force_authenticate(self.normal)
        resp = self.client.post(
            self._url(self.normal), {"job_title": "Consultant"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.normal.refresh_from_db()
        self.assertEqual(self.normal.job_title, "Consultant")

    def test_manager_can_update_report(self):
        report = User.objects.create_user(email="rep@example.com", password="pw")
        report.manager = self.normal
        report.save()
        self.client.force_authenticate(self.normal)
        resp = self.client.post(
            self._url(report), {"first_name": "Rep"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        report.refresh_from_db()
        self.assertEqual(report.first_name, "Rep")

    def test_superuser_sets_city_and_country(self):
        country = Country.objects.create(name="UK", slug="uk", continent="EU")
        city = City.objects.create(
            name="London", slug="london", display_name="London, UK", country=country
        )
        self.client.force_authenticate(self.superuser)
        resp = self.client.post(
            self._url(self.normal),
            {"city": city.pk, "country": "GB"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.normal.refresh_from_db()
        self.assertEqual(self.normal.city_id, city.pk)
        self.assertEqual(resp.data["city"], city.pk)
        self.assertEqual(resp.data["city_name"], "London")

    def test_status_not_writable_via_profile(self):
        # is_active must never be settable through the profile action.
        target = User.objects.create_user(
            email="act@example.com", password="pw", is_active=True
        )
        self.client.force_authenticate(self.superuser)
        resp = self.client.post(
            self._url(target), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        target.refresh_from_db()
        self.assertTrue(target.is_active)  # ignored, not applied


class SetJobLevelActionTests(APIV1BaseTest):
    def _url(self, user):
        return f"/api/v1/users/{user.pk}/set-job-level/"

    def setUp(self):
        super().setUp()
        self.jl5 = JobLevel.objects.create(
            short_label="JL5", long_label="Consultant", order=5
        )

    def test_non_manager_forbidden(self):
        # target has a manager who is NOT self.normal.
        boss = User.objects.create_user(email="boss@example.com", password="pw")
        target = User.objects.create_user(email="emp@example.com", password="pw")
        target.manager = boss
        target.save()
        self.client.force_authenticate(self.normal)
        resp = self.client.post(self._url(target), {"job_level": "JL5"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_superuser_sets_and_clears_level(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.post(
            self._url(self.normal), {"job_level": "JL5"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["changed"])
        self.assertEqual(resp.data["user"]["job_level"], "JL5")
        self.assertTrue(
            UserJobLevel.objects.filter(
                user=self.normal, is_current=True, job_level=self.jl5
            ).exists()
        )
        # Clear it.
        resp = self.client.post(
            self._url(self.normal), {"clear": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["changed"])
        self.assertIsNone(resp.data["user"]["job_level"])

    def test_unknown_label_400(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.post(
            self._url(self.normal), {"job_level": "JLX"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_idempotent_and_supersedes_on_change(self):
        # Re-posting the same level is a no-op; a different level creates a new
        # dated assignment and closes off the old one.
        jl6 = JobLevel.objects.create(short_label="JL6", long_label="Senior", order=6)
        self.client.force_authenticate(self.superuser)

        r1 = self.client.post(
            self._url(self.normal), {"job_level": "JL5", "effective_from": "2026-01-01"},
            format="json",
        )
        self.assertTrue(r1.data["changed"])
        # Same value again -> no change, no extra row.
        r2 = self.client.post(self._url(self.normal), {"job_level": "JL5"}, format="json")
        self.assertFalse(r2.data["changed"])
        self.assertEqual(
            UserJobLevel.objects.filter(user=self.normal).count(), 1
        )
        # Promote -> new current row, old one closed off (is_current=False).
        r3 = self.client.post(self._url(self.normal), {"job_level": "JL6"}, format="json")
        self.assertTrue(r3.data["changed"])
        self.assertEqual(r3.data["user"]["job_level"], "JL6")
        self.assertEqual(
            UserJobLevel.objects.filter(user=self.normal).count(), 2
        )
        self.assertEqual(
            UserJobLevel.objects.filter(user=self.normal, is_current=True).count(), 1
        )
        old = UserJobLevel.objects.get(user=self.normal, job_level=self.jl5)
        self.assertFalse(old.is_current)

    def test_future_effective_date_rejected(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.post(
            self._url(self.normal),
            {"job_level": "JL5", "effective_from": "2099-01-01"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class SetCostActionTests(APIV1BaseTest):
    def _url(self, user):
        return f"/api/v1/users/{user.pk}/set-cost/"

    def setUp(self):
        super().setUp()
        self.unit = OrganisationalUnit.objects.create(name="UKI-api")
        self.target = User.objects.create_user(email="cost@example.com", password="pw")
        self.unit.members.create(member=self.target)

    def _finance_user(self, email, global_perm=False, unit=None):
        u = User.objects.create_user(email=email, password="pw")
        if global_perm:
            u.user_permissions.add(
                Permission.objects.get(codename="can_view_loaded_costs")
            )
        if unit is not None:
            assign_perm("jobtracker.can_view_loaded_costs", u, unit)
        # Re-fetch to clear the permission cache on the instance.
        return User.objects.get(pk=u.pk)

    def test_no_finance_perm_forbidden(self):
        self.client.force_authenticate(self.normal)
        resp = self.client.post(
            self._url(self.target), {"cost_per_hour": "50.00"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_global_perm_allows(self):
        fin = self._finance_user("fin-global@example.com", global_perm=True)
        self.client.force_authenticate(fin)
        resp = self.client.post(
            self._url(self.target),
            {"cost_per_hour": "43.46", "effective_from": "2026-01-01"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["created"])
        self.assertEqual(
            UserCost.objects.get(user=self.target).cost_per_hour, Decimal("43.46")
        )

    def test_unit_perm_on_every_unit_allows(self):
        fin = self._finance_user("fin-unit@example.com", unit=self.unit)
        self.client.force_authenticate(fin)
        resp = self.client.post(
            self._url(self.target), {"cost_per_hour": "50.00"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_unit_perm_insufficient_when_target_in_other_unit(self):
        other = OrganisationalUnit.objects.create(name="Other-api")
        other.members.create(member=self.target)  # target now in two units
        fin = self._finance_user("fin-partial@example.com", unit=self.unit)
        self.client.force_authenticate(fin)
        resp = self.client.post(
            self._url(self.target), {"cost_per_hour": "50.00"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_repost_same_date_updates(self):
        self.client.force_authenticate(self.superuser)
        self.client.post(
            self._url(self.target),
            {"cost_per_hour": "40.00", "effective_from": "2026-01-01"},
            format="json",
        )
        resp = self.client.post(
            self._url(self.target),
            {"cost_per_hour": "60.00", "effective_from": "2026-01-01"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["changed"])
        self.assertFalse(resp.data["created"])
        self.assertEqual(UserCost.objects.filter(user=self.target).count(), 1)

    def test_unchanged_value_is_noop(self):
        # The import scenario: same rate re-posted (even on a later date) writes
        # nothing; a changed rate adds a new dated row that supersedes the old.
        self.client.force_authenticate(self.superuser)
        self.client.post(
            self._url(self.target),
            {"cost_per_hour": "50.00", "effective_from": "2026-01-01"},
            format="json",
        )
        # Same value, later run date -> no-op (no new row).
        resp = self.client.post(
            self._url(self.target),
            {"cost_per_hour": "50.00", "effective_from": "2026-06-01"},
            format="json",
        )
        self.assertFalse(resp.data["changed"])
        self.assertFalse(resp.data["created"])
        self.assertEqual(UserCost.objects.filter(user=self.target).count(), 1)
        # Changed value on a later date -> new row; both rows retained, and the
        # new rate is the one in force from that date on.
        resp = self.client.post(
            self._url(self.target),
            {"cost_per_hour": "55.00", "effective_from": "2026-06-01"},
            format="json",
        )
        self.assertTrue(resp.data["changed"])
        self.assertEqual(UserCost.objects.filter(user=self.target).count(), 2)
        self.assertEqual(
            UserCost.cost_on(self.target, date(2026, 7, 1)), Decimal("55.00")
        )
        self.assertEqual(
            UserCost.cost_on(self.target, date(2026, 3, 1)), Decimal("50.00")
        )


class ScheduleEndpointTests(APIV1BaseTest):
    """The read-only /api/v1/schedule/ feed + per-user /users/{id}/schedule/.

    Scoping mirrors the vis-timeline feeds: a caller sees a user's schedule only
    with ``view_users_schedule`` on a shared unit (or for themselves).
    """

    def setUp(self):
        super().setUp()
        from django.utils import timezone
        from datetime import timedelta
        from jobtracker.models import TimeSlot, TimeSlotType

        self.unit = OrganisationalUnit.objects.create(name="Sched-Unit")
        self.target = User.objects.create_user(
            email="sched-target@example.com", password="pw"
        )
        self.unit.members.create(member=self.target)

        self.slot_type = TimeSlotType.objects.create(name="Delivery-sched")
        base = timezone.now() + timedelta(days=2)
        self.slot = TimeSlot.objects.create(
            user=self.target,
            slot_type=self.slot_type,
            start=base,
            end=base + timedelta(hours=8),
        )

    def _viewer_with_perm(self, email):
        u = User.objects.create_user(email=email, password="pw")
        assign_perm("jobtracker.view_users_schedule", u, self.unit)
        return User.objects.get(pk=u.pk)

    # --- global /schedule/ ---------------------------------------------------

    def test_global_schedule_shape(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get("/api/v1/schedule/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for key in ("start", "end", "users", "timeslots", "leave", "holidays"):
            self.assertIn(key, resp.data)
        # Clean shape, no DataTables leakage.
        for row in resp.data["timeslots"]:
            self.assertNotIn("DT_RowId", row)

    def test_superuser_sees_target_slot(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get("/api/v1/schedule/")
        slot_ids = {row["id"] for row in resp.data["timeslots"]}
        self.assertIn(self.slot.pk, slot_ids)

    def test_unprivileged_user_sees_only_self(self):
        self.client.force_authenticate(self.normal)
        resp = self.client.get("/api/v1/schedule/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        slot_ids = {row["id"] for row in resp.data["timeslots"]}
        self.assertNotIn(self.slot.pk, slot_ids)
        # Availability rows are limited to the caller themselves.
        user_ids = {row["user"] for row in resp.data["users"]}
        self.assertNotIn(self.target.pk, user_ids)

    # --- per-user /users/{id}/schedule/ -------------------------------------

    def test_self_can_view_own_schedule(self):
        self.client.force_authenticate(self.target)
        resp = self.client.get(f"/api/v1/users/{self.target.pk}/schedule/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        slot_ids = {row["id"] for row in resp.data["timeslots"]}
        self.assertIn(self.slot.pk, slot_ids)

    def test_other_user_without_perm_forbidden(self):
        self.client.force_authenticate(self.normal)
        resp = self.client.get(f"/api/v1/users/{self.target.pk}/schedule/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_view_users_schedule_perm_allows(self):
        viewer = self._viewer_with_perm("sched-viewer@example.com")
        self.client.force_authenticate(viewer)
        resp = self.client.get(f"/api/v1/users/{self.target.pk}/schedule/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        slot_ids = {row["id"] for row in resp.data["timeslots"]}
        self.assertIn(self.slot.pk, slot_ids)

    # --- window params -------------------------------------------------------

    def test_invalid_start_returns_400(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get("/api/v1/schedule/?start=not-a-date")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_over_cap_window_returns_400(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get(
            "/api/v1/schedule/?start=2026-01-01&end=2027-06-01"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_integer_unit_param_returns_400(self):
        # Bad ?unit / ?user must 400, not 500 (ValueError from .filter()).
        self.client.force_authenticate(self.superuser)
        self.assertEqual(
            self.client.get("/api/v1/schedule/?unit=abc").status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.get("/api/v1/schedule/?user=abc").status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_unit_filter_narrows_to_unit_members(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.get(f"/api/v1/schedule/?unit={self.unit.pk}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        slot_ids = {row["id"] for row in resp.data["timeslots"]}
        self.assertIn(self.slot.pk, slot_ids)

    def test_non_numeric_user_pk_404s_at_routing(self):
        # lookup_value_regex = [0-9]+ means a non-numeric id never reaches the
        # view (no 500 from int(pk)).
        self.client.force_authenticate(self.superuser)
        resp = self.client.get("/api/v1/users/abc/schedule/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_read_only_post_returns_405(self):
        self.client.force_authenticate(self.superuser)
        resp = self.client.post("/api/v1/schedule/", {})
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class OrgUnitMembersActionTests(APIV1BaseTest):
    """The /api/v1/org-units/{id}/members/ action lists *current* members only."""

    def test_members_excludes_users_who_left(self):
        from django.utils import timezone

        unit = OrganisationalUnit.objects.create(name="Members-Unit")
        current = User.objects.create_user(email="cur@example.com", password="pw")
        left = User.objects.create_user(email="left@example.com", password="pw")
        unit.members.create(member=current)
        unit.members.create(member=left, left_date=timezone.now())

        self.client.force_authenticate(self.superuser)
        resp = self.client.get(f"/api/v1/org-units/{unit.pk}/members/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        member_ids = {row["user_id"] for row in resp.data}
        self.assertIn(current.pk, member_ids)
        self.assertNotIn(left.pk, member_ids)


class SensitiveFieldTests(APIV1BaseTest):
    def test_certificate_file_not_serialized(self):
        self.assertNotIn(
            "certificate_file", QualificationRecordSerializer().fields
        )

    def test_user_pii_not_serialized(self):
        fields = set(UserSerializer().fields)
        self.assertNotIn("phone_number", fields)
        self.assertEqual(
            fields,
            {
                "id",
                "first_name",
                "last_name",
                "email",
                "is_active",
                "job_title",
                "job_level",
                "job_level_label",
                # Org-chart location facts (non-PII, already shown across the UI).
                "city",
                "city_name",
                "country",
            },
        )
