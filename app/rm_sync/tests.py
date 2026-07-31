"""Tests for the RM (Smartsheet Resource Management) two-way sync.

Inbound/user tests drive the logic through a ``FakeClient`` so they never touch the network;
they exercise mapping, loop prevention, proportional allocation, reconcile scoping and the
user-import safety guard. A separate test covers the read-only write guard on the real
``RMClient``.
"""

from datetime import date, timedelta
from unittest.mock import patch

from constance.test import override_config
from django.test import TestCase
from django.utils import timezone

from chaotica_utils.enums import LeaveRequestTypes
from chaotica_utils.models import LeaveRequest, User
from jobtracker.enums import DefaultTimeSlotTypes
from jobtracker.models import OrganisationalUnit, Project, TimeSlot, TimeSlotType

from .client import RMClient, RMReadOnlyError
from .enums import RMSyncDirection
from .models import RMInboundSlot, RMSyncRecord, RMUnitMap


def _seed_timeslot_types():
    for d in DefaultTimeSlotTypes.DEFAULTS:
        fields = {k: v for k, v in d.items() if k != "pk"}
        TimeSlotType.objects.update_or_create(pk=d["pk"], defaults=fields)


def _seed_unit_roles():
    from chaotica_utils.enums import UnitRoles
    from jobtracker.models import OrganisationalUnitRole

    for role in UnitRoles.DEFAULTS:
        if role["pk"] == 0:
            continue
        OrganisationalUnitRole.objects.update_or_create(
            pk=role["pk"], defaults={"name": role["name"]}
        )


class FakeResp:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data or {}

    def json(self):
        return self._data


class FakeClient:
    """Minimal stand-in for RMClient covering the methods inbound/users call."""

    def __init__(
        self,
        rm_user=None,
        assignments=None,
        projects=None,
        leave_types=None,
        users=None,
    ):
        self._rm_user = (
            rm_user if rm_user is not None else {"archived": False, "deleted": False}
        )
        self._assignments = assignments or []
        self._projects = projects or {}
        self._leave_types = leave_types or []
        self._users = users or []
        # Records the params of the last /assignments pull, for window assertions.
        self.assignment_params = None

    def get(self, path, params=None):
        return FakeResp(200, self._rm_user)

    def paginate(self, path, params=None):
        if path == "/api/v1/users":
            return iter(self._users)
        if "/assignments" in path:
            self.assignment_params = params
            return iter(self._assignments)
        return iter([])

    def leave_type_ids(self):
        return {lt["id"] for lt in self._leave_types}

    def leave_types(self):
        return list(self._leave_types)

    def get_project(self, pid):
        return self._projects.get(pid)


def _mk_user(**kwargs):
    """Create a User without ``force_insert``.

    ``User.save()`` double-calls ``super().save()`` when exactly one user exists (the
    first-user→superuser bootstrap); with ``User.objects.create()``'s ``force_insert=True``
    that second call re-inserts the same PK and raises a duplicate-key error. Plain
    ``instance.save()`` updates on the second call instead, so this mirrors how the real
    ``sync_rm_users`` creates users.
    """
    user = User(**kwargs)
    user.save()
    return user


def _assignment(aid, assignable_id, start, end, percent=1.0):
    return {
        "id": aid,
        "assignable_id": assignable_id,
        "starts_at": start,
        "ends_at": end,
        "allocation_mode": "percent",
        "percent": percent,
    }


class RMSyncTestBase(TestCase):
    def setUp(self):
        _seed_timeslot_types()
        _seed_unit_roles()


class InboundPullTests(RMSyncTestBase):
    def setUp(self):
        super().setUp()
        self.user = _mk_user(
            email="euperson@example.com", first_name="Eu", last_name="Person"
        )
        self.record = RMSyncRecord.objects.create(
            user=self.user,
            rm_id="100",
            direction=RMSyncDirection.PULL,
            sync_authoritative=True,
        )
        self.today = date.today()

    def _fut(self, days):
        return (self.today + timedelta(days=days)).strftime("%Y-%m-%d")

    def test_pull_window_defaults_forward_only(self):
        # Default config: from today (lookback 0) to today+365.
        client = FakeClient(assignments=[])
        self.record.pull_records(client=client)
        self.assertEqual(
            client.assignment_params["from"], self.today.strftime("%Y-%m-%d")
        )
        self.assertEqual(
            client.assignment_params["to"],
            (self.today + timedelta(days=365)).strftime("%Y-%m-%d"),
        )

    @override_config(RM_SYNC_PULL_LOOKBACK_DAYS=365, RM_SYNC_PULL_LOOKAHEAD_DAYS=30)
    def test_pull_window_respects_lookback_config(self):
        # Configured to pull the last year plus 30 days ahead.
        client = FakeClient(assignments=[])
        self.record.pull_records(client=client)
        self.assertEqual(
            client.assignment_params["from"],
            (self.today - timedelta(days=365)).strftime("%Y-%m-%d"),
        )
        self.assertEqual(
            client.assignment_params["to"],
            (self.today + timedelta(days=30)).strftime("%Y-%m-%d"),
        )

    def test_rm_native_project_creates_project_and_slot(self):
        from jobtracker.enums import ProjectState

        client = FakeClient(
            assignments=[_assignment(1, 500, self._fut(1), self._fut(5))],
            projects={
                500: {
                    "id": 500,
                    "name": "Heineken VM",
                    "project_code": "ID1",
                    "project_state": "Confirmed",
                    "description": "",
                }
            },
        )
        res = self.record.pull_records(client=client)
        self.assertEqual(res.created_projects, 1)
        self.assertEqual(res.created_slots, 1)
        project = Project.objects.get(external_id="500")
        self.assertEqual(TimeSlot.objects.filter(user=self.user).count(), 1)
        self.assertEqual(RMInboundSlot.objects.filter(record=self.record).count(), 1)
        # RM "Confirmed" → Confirmed state + deliverable → counts as delivery.
        self.assertEqual(project.state, ProjectState.CONFIRMED)
        self.assertTrue(project.deliverable)
        self.assertTrue(project.counts_as_delivery())

    def test_rm_internal_project_not_deliverable(self):
        from jobtracker.enums import ProjectState

        client = FakeClient(
            assignments=[_assignment(1, 510, self._fut(1), self._fut(5))],
            projects={
                510: {
                    "id": 510,
                    "name": "Internal R&D",
                    "project_state": "Internal",
                    "description": "",
                }
            },
        )
        self.record.pull_records(client=client)
        project = Project.objects.get(external_id="510")
        self.assertEqual(project.state, ProjectState.INTERNAL)
        self.assertFalse(project.deliverable)
        self.assertFalse(project.counts_as_delivery())

    def test_reimport_refreshes_existing_project_state(self):
        from jobtracker.enums import ProjectState

        # First import as Internal (non-deliverable).
        c1 = FakeClient(
            assignments=[_assignment(1, 520, self._fut(1), self._fut(5))],
            projects={
                520: {
                    "id": 520,
                    "name": "Grows Up",
                    "project_state": "Internal",
                    "description": "",
                }
            },
        )
        self.record.pull_records(client=c1)
        p = Project.objects.get(external_id="520")
        self.assertEqual(p.state, ProjectState.INTERNAL)
        self.assertFalse(p.deliverable)

        # RM later flips it to Confirmed — a re-import must update the existing project.
        c2 = FakeClient(
            assignments=[_assignment(1, 520, self._fut(1), self._fut(5))],
            projects={
                520: {
                    "id": 520,
                    "name": "Grows Up",
                    "project_state": "Confirmed",
                    "description": "",
                }
            },
        )
        res = self.record.pull_records(client=c2)
        self.assertEqual(res.created_projects, 0)  # not re-created
        p.refresh_from_db()
        self.assertEqual(p.state, ProjectState.CONFIRMED)
        self.assertTrue(p.deliverable)

    def test_mirrored_project_links_client(self):
        from jobtracker.models import Client

        client = FakeClient(
            assignments=[_assignment(1, 500, self._fut(1), self._fut(5))],
            projects={
                500: {
                    "id": 500,
                    "name": "Acme Pentest",
                    "client": "Acme Corp",
                    "description": "",
                }
            },
        )
        self.record.pull_records(client=client)
        project = Project.objects.get(external_id="500")
        self.assertIsNotNone(project.client)
        self.assertEqual(project.client.name, "Acme Corp")
        self.assertTrue(Client.objects.filter(name="Acme Corp").exists())

    def test_loop_prevention_skips_chaotica_origin(self):
        from constance import config

        client = FakeClient(
            assignments=[_assignment(1, 501, self._fut(1), self._fut(5))],
            projects={
                501: {
                    "id": 501,
                    "name": "Ours",
                    "description": config.RM_WARNING_MSG + " x",
                }
            },
        )
        res = self.record.pull_records(client=client)
        self.assertEqual(res.skipped_chaotica_origin, 1)
        self.assertEqual(res.created_projects, 0)
        self.assertEqual(TimeSlot.objects.filter(user=self.user).count(), 0)

    def test_loop_prevention_via_tags(self):
        client = FakeClient(
            assignments=[_assignment(1, 502, self._fut(1), self._fut(5))],
            projects={
                502: {
                    "id": 502,
                    "name": "Ours",
                    "tags": ["CHAOTICA"],
                    "description": "",
                }
            },
        )
        res = self.record.pull_records(client=client)
        self.assertEqual(res.skipped_chaotica_origin, 1)

    def test_leave_mapping_by_name(self):
        client = FakeClient(
            assignments=[_assignment(1, 900, self._fut(1), self._fut(3))],
            leave_types=[{"id": 900, "name": "Sick Leave"}],
        )
        res = self.record.pull_records(client=client)
        self.assertEqual(res.created_leave, 1)
        lr = LeaveRequest.objects.get(user=self.user)
        self.assertEqual(lr.type_of_leave, LeaveRequestTypes.SICK)
        self.assertTrue(lr.authorised)

    def test_proportional_partial_allocation_fans_out(self):
        # A 50% allocation across a Mon–Fri week → per-working-day shortened slots.
        monday = self.today + timedelta(days=(7 - self.today.weekday()))  # next Monday
        friday = monday + timedelta(days=4)
        client = FakeClient(
            assignments=[
                _assignment(
                    1,
                    500,
                    monday.strftime("%Y-%m-%d"),
                    friday.strftime("%Y-%m-%d"),
                    percent=0.5,
                )
            ],
            projects={500: {"id": 500, "name": "PartTime", "description": ""}},
        )
        res = self.record.pull_records(client=client)
        self.assertEqual(res.created_slots, 5)  # 5 working days
        slot = TimeSlot.objects.filter(user=self.user).first()
        # Each day is shortened to ~half the business day, so < a full 8.5h day.
        self.assertLess(float(slot.get_business_hours()), 5.0)

    def test_reconcile_only_touches_inbound_slots(self):
        # A CHAOTICA-native slot (no RMInboundSlot) must survive an authoritative pull.
        native_type = TimeSlotType.get_builtin_object(
            DefaultTimeSlotTypes.INTERNAL_PROJECT
        )
        native_project = Project.objects.create(title="Native", created_by=self.user)
        native = TimeSlot.objects.create(
            user=self.user,
            slot_type=native_type,
            project=native_project,
            start=timezone.now(),
            end=timezone.now() + timedelta(hours=1),
        )
        # An inbound slot for an assignment that no longer exists in RM.
        stale_project = Project.objects.create(
            title="Stale", created_by=self.user, external_id="777"
        )
        stale = TimeSlot.objects.create(
            user=self.user,
            slot_type=native_type,
            project=stale_project,
            start=timezone.now(),
            end=timezone.now() + timedelta(hours=1),
        )
        RMInboundSlot.objects.create(
            timeslot=stale,
            record=self.record,
            rm_assignment_id="55",
            day=self.today,
            rm_data={},
        )
        client = FakeClient(assignments=[])  # RM now has no assignments
        res = self.record.pull_records(client=client)
        self.assertEqual(res.deleted_slots, 1)
        self.assertFalse(TimeSlot.objects.filter(pk=stale.pk).exists())
        self.assertTrue(
            TimeSlot.objects.filter(pk=native.pk).exists()
        )  # native survives

    def test_non_authoritative_pull_never_deletes(self):
        self.record.sync_authoritative = False
        self.record.save()
        native_type = TimeSlotType.get_builtin_object(
            DefaultTimeSlotTypes.INTERNAL_PROJECT
        )
        proj = Project.objects.create(
            title="Stale", created_by=self.user, external_id="778"
        )
        ts = TimeSlot.objects.create(
            user=self.user,
            slot_type=native_type,
            project=proj,
            start=timezone.now(),
            end=timezone.now() + timedelta(hours=1),
        )
        RMInboundSlot.objects.create(
            timeslot=ts,
            record=self.record,
            rm_assignment_id="66",
            day=self.today,
            rm_data={},
        )
        res = self.record.pull_records(client=FakeClient(assignments=[]))
        self.assertEqual(res.deleted_slots, 0)
        self.assertTrue(TimeSlot.objects.filter(pk=ts.pk).exists())


def _rm_user(uid, email, market_unit="UKI", role="Consultant", **extra):
    u = {
        "id": uid,
        "email": email,
        "first_name": "A",
        "last_name": "B",
        "role": role,
        "custom_field_values": {
            "data": [{"custom_field_name": "Market Unit", "value": market_unit}]
        },
    }
    u.update(extra)
    return u


class UserImportTests(RMSyncTestBase):
    def setUp(self):
        super().setUp()
        from .models import RMUnitMap

        self.ou = OrganisationalUnit.objects.create(name="EU - Iberia")
        # Iberia is mapped + enabled → PULL; other market units auto-create null-OU rows.
        RMUnitMap.objects.create(
            market_unit="Iberia",
            unit=self.ou,
            direction=RMSyncDirection.PULL,
            enabled=True,
        )

    def test_creates_pull_user_and_assigns_mapped_ou(self):
        from .users import import_rm_users

        client = FakeClient(
            users=[
                _rm_user(
                    1,
                    "new@example.com",
                    market_unit="Iberia",
                    role="Service Delivery Team",
                )
            ]
        )
        res = import_rm_users(client=client, create_missing=True)
        self.assertEqual(res.created, 1)
        user = User.objects.get(email="new@example.com")
        self.assertTrue(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.external_id, "1")
        self.assertEqual(user.rm_sync_record.direction, RMSyncDirection.PULL)
        self.assertEqual(user.rm_sync_record.market_unit, "Iberia")
        self.assertEqual(user.rm_sync_record.rm_role, "Service Delivery Team")
        membership = user.unit_memberships.get(unit=self.ou)
        # RM "Service Delivery Team" → CHAOTICA "Service Delivery" org-unit role.
        self.assertTrue(membership.roles.filter(name="Service Delivery").exists())

    def test_unmapped_market_unit_autocreates_map_and_imports_ou_less(self):
        from .models import RMUnitMap
        from .users import import_rm_users

        client = FakeClient(
            users=[_rm_user(2, "prg@example.com", market_unit="Prague")]
        )
        res = import_rm_users(client=client, create_missing=True)
        self.assertEqual(res.created, 1)
        self.assertEqual(res.maps_created, 1)
        self.assertTrue(
            RMUnitMap.objects.filter(market_unit="Prague", unit=None).exists()
        )
        user = User.objects.get(email="prg@example.com")
        # No OU (unit unmapped) and direction stays OFF until the map is filled in + applied.
        self.assertFalse(user.unit_memberships.exists())
        self.assertEqual(user.rm_sync_record.direction, RMSyncDirection.OFF)

    def test_no_market_unit_skipped(self):
        from .users import import_rm_users

        client = FakeClient(users=[_rm_user(3, "x@example.com", market_unit="")])
        res = import_rm_users(client=client, create_missing=True)
        self.assertEqual(res.created, 0)
        self.assertEqual(res.skipped_no_market_unit, 1)


class MatchUsersTests(RMSyncTestBase):
    def setUp(self):
        super().setUp()
        from .models import RMUnitMap

        self.uki_ou = OrganisationalUnit.objects.create(name="UK & Ireland")
        RMUnitMap.objects.create(
            market_unit="UKI",
            unit=self.uki_ou,
            direction=RMSyncDirection.PUSH,
            enabled=True,
        )

    def test_adopts_existing_user_sets_rm_id_and_map_direction(self):
        from .users import match_rm_users

        user = _mk_user(email="match@example.com")
        client = FakeClient(
            users=[_rm_user(42, "match@example.com", market_unit="UKI")]
        )
        res = match_rm_users(client=client)
        self.assertEqual(res.matched, 1)
        rec = RMSyncRecord.objects.get(user=user)
        self.assertEqual(rec.rm_id, "42")
        self.assertEqual(rec.market_unit, "UKI")
        self.assertEqual(rec.direction, RMSyncDirection.PUSH)  # from the UKI map

    def test_existing_direction_never_clobbered(self):
        # A UKI user already on PUSH must not be flipped even if the map said PULL.
        from .models import RMUnitMap
        from .users import match_rm_users

        RMUnitMap.objects.filter(market_unit="UKI").update(
            direction=RMSyncDirection.PULL
        )
        user = _mk_user(email="uki@example.com")
        RMSyncRecord.objects.create(
            user=user, rm_id="42", direction=RMSyncDirection.PUSH
        )
        client = FakeClient(users=[_rm_user(42, "uki@example.com", market_unit="UKI")])
        res = match_rm_users(client=client)  # no --force-direction
        self.assertEqual(res.direction_protected, 1)
        self.assertEqual(
            RMSyncRecord.objects.get(user=user).direction, RMSyncDirection.PUSH
        )

    def test_force_direction_allows_change(self):
        from .models import RMUnitMap
        from .users import match_rm_users

        RMUnitMap.objects.filter(market_unit="UKI").update(
            direction=RMSyncDirection.PULL
        )
        user = _mk_user(email="f@example.com")
        RMSyncRecord.objects.create(
            user=user, rm_id="42", direction=RMSyncDirection.PUSH
        )
        client = FakeClient(users=[_rm_user(42, "f@example.com", market_unit="UKI")])
        match_rm_users(client=client, force_direction=True)
        self.assertEqual(
            RMSyncRecord.objects.get(user=user).direction, RMSyncDirection.PULL
        )

    def test_market_unit_filter_and_unmatched(self):
        from .users import match_rm_users

        _mk_user(email="here@example.com")
        client = FakeClient(
            users=[
                _rm_user(1, "here@example.com", market_unit="UKI"),
                _rm_user(2, "elsewhere@example.com", market_unit="Iberia"),
                _rm_user(3, "nouser@example.com", market_unit="UKI"),
            ]
        )
        res = match_rm_users(client=client, market_unit_filter="UKI")
        self.assertEqual(res.matched, 1)  # only the UKI user that exists
        self.assertEqual(res.unmatched_rm, 1)  # UKI user with no CHAOTICA account
        self.assertFalse(
            RMSyncRecord.objects.filter(rm_id="2").exists()
        )  # Iberia filtered out

    def test_rm_id_conflict_not_overwritten_by_default(self):
        from .users import match_rm_users

        user = _mk_user(email="c@example.com")
        RMSyncRecord.objects.create(
            user=user, rm_id="999", direction=RMSyncDirection.OFF
        )
        client = FakeClient(users=[_rm_user(42, "c@example.com", market_unit="UKI")])
        res = match_rm_users(client=client)
        self.assertEqual(res.rm_id_conflict, 1)
        self.assertEqual(RMSyncRecord.objects.get(user=user).rm_id, "999")  # unchanged


class ApplyUnitMapTests(RMSyncTestBase):
    def test_apply_sets_ou_and_direction(self):
        from .models import RMUnitMap
        from .users import apply_rm_unit_maps

        ou = OrganisationalUnit.objects.create(name="EU - Nordics")
        user = _mk_user(email="n@example.com")
        RMSyncRecord.objects.create(
            user=user,
            rm_id="7",
            market_unit="Nordics",
            rm_role="Consultant",
            direction=RMSyncDirection.OFF,
        )
        # Map filled in + enabled after the user was imported OU-less.
        RMUnitMap.objects.create(
            market_unit="Nordics", unit=ou, direction=RMSyncDirection.PULL, enabled=True
        )
        res = apply_rm_unit_maps()
        self.assertEqual(res.ou_set, 1)
        self.assertEqual(res.direction_set, 1)
        user.refresh_from_db()
        membership = user.unit_memberships.get(unit=ou)
        self.assertEqual(user.rm_sync_record.direction, RMSyncDirection.PULL)
        # RM role → org-unit role applied when the OU is assigned.
        self.assertTrue(membership.roles.filter(name="Consultant").exists())


class ReadOnlyGuardTests(TestCase):
    def test_write_blocked_when_read_only(self):
        client = RMClient(token="x", site="https://example.invalid")
        with patch.object(RMClient, "read_only", property(lambda self: True)):
            with self.assertRaises(RMReadOnlyError):
                client.post("/api/v1/projects", json={"a": 1})
            with self.assertRaises(RMReadOnlyError):
                client.delete("/api/v1/projects/1")
