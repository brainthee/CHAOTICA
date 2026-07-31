from django.db import models
from django.conf import settings
from constance import config
from django.utils import timezone
from datetime import timedelta
import logging
from jobtracker.models import (
    OrganisationalUnit,
    Phase,
    Project,
    TimeSlot,
    TimeSlotType,
)
from jobtracker.enums import (
    DefaultTimeSlotTypes,
)
from chaotica_utils.utils import ext_reverse
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .client import RMClient, RMReadOnlyError
from .enums import RMSyncDirection

logger = logging.getLogger(__name__)


class RMUnitMap(models.Model):
    """Maps an RM "Market Unit" (e.g. ``UKI``, ``Iberia``, ``Prague``) to a CHAOTICA
    OrganisationalUnit **and** a default sync direction.

    Market Unit is a coarse, clean grouping in RM (unlike city-level ``location``), so it maps
    naturally onto OUs. The direction lets each market unit be authoritative in the right
    place — e.g. ``UKI`` → PUSH (CHAOTICA owns the schedule), EU units → PULL (RM owns it).

    Import auto-creates a row (``unit=None``, ``direction=OFF``, ``enabled=False``) for every
    market unit it sees, so an admin can fill in the OU + direction and then run
    ``apply_rm_unit_maps`` to push those onto the imported users.
    """

    market_unit = models.CharField(
        max_length=255,
        unique=True,
        help_text="RM 'Market Unit' custom-field value, e.g. 'UKI' or 'Iberia'.",
    )
    unit = models.ForeignKey(
        OrganisationalUnit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rm_unit_maps",
        help_text="CHAOTICA org unit these users belong to. Leave blank to map later.",
    )
    direction = models.IntegerField(
        choices=RMSyncDirection.CHOICES,
        default=RMSyncDirection.OFF,
        help_text="Sync direction applied to users in this market unit.",
    )
    enabled = models.BooleanField(
        default=False,
        help_text="Only enabled maps assign OU/direction when applying.",
    )

    class Meta:
        ordering = ["market_unit"]

    def __str__(self):
        return "{} → {} ({})".format(
            self.market_unit, self.unit, self.get_direction_display()
        )


class RMTaskLock(models.Model):
    task_id = models.CharField(
        max_length=255,
        unique=True,
    )
    started = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    def is_stale(self):
        now = timezone.now()
        time_diff = (
            (now - self.last_updated).total_seconds()
            / int(config.RM_SYNC_STALE_TIMEOUT)
            * 60
        )
        return time_diff > 1


class RMAssignable(models.Model):
    phase = models.OneToOneField(
        Phase,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="rm_assignable",
    )
    project = models.OneToOneField(
        Project,
        related_name="rm_assignable",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    slotType = models.OneToOneField(
        TimeSlotType,
        related_name="rm_assignable",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    rm_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        unique=True,
        help_text="Assignable ID in Resource Manager",
    )
    rm_data = models.JSONField(default=list, blank=True)

    last_synced = models.DateTimeField(null=True, blank=True)
    last_sync_result = models.BooleanField(default=False)

    class Meta:
        ordering = ["rm_id"]

    def __str__(self):
        if self.project:
            return "({}) {}".format(self.rm_id, str(self.project))
        elif self.phase:
            return "({}) {}".format(self.rm_id, str(self.phase))
        elif self.slotType:
            return "({}) {}".format(self.rm_id, str(self.slotType))
        else:
            return "({}) {}".format(self.rm_id, "Unknown")

    def get_absolute_url(self):
        if self.phase:
            return self.phase.get_absolute_url()
        elif self.project:
            return self.project.get_absolute_url()
        else:
            return "/"

    def update_rm_if_stale(self):
        if (
            not self.last_synced
            or not self.last_sync_result
            or self.last_synced < (timezone.now() - timedelta(days=1))
        ):
            return self.update_rm()
        return False

    def update_rm(self, client=None):
        """Create/verify the RM project mirroring this CHAOTICA assignable (push)."""
        client = client or RMClient()
        log = logger

        if self.phase:
            log.info("Starting RM Sync for %s", self.phase)
        elif self.project:
            log.info("Starting RM Sync for %s", self.project)
        elif self.slotType:
            log.info("Starting RM Sync for %s", self.slotType)
        else:
            log.error("Told to start sync for an assignable with no project/phase")

        should_create = self.rm_id is None

        try:
            if self.rm_id:
                # Project should already exist...
                r_check = client.get("/api/v1/projects/{}".format(self.rm_id))
                if r_check.status_code != 200:
                    if r_check.status_code == 400:
                        log.error("Invalid JSON sent")
                        return False
                    if r_check.status_code == 401:
                        log.error("RM API Token Invalid")
                        return False
                    elif r_check.status_code == 404:
                        log.warning("RM project not found")
                        should_create = True
                    else:
                        log.error(
                            " ! Got a non-200 status code: %s", r_check.status_code
                        )
                        return False
                else:
                    self.rm_data = r_check.json()

            if should_create:
                # Create the project!
                if self.phase:
                    data = {
                        "name": self.phase.title,
                        "project_code": self.phase.phase_id,
                        "project_state": (
                            "Confirmed" if self.phase.is_confirmed() else "Tentative"
                        ),
                        "tags": ["CHAOTICA"],
                        "client": str(self.phase.job.client),
                        "description": config.RM_WARNING_MSG
                        + " {}".format(ext_reverse(self.phase.get_absolute_url())),
                    }
                elif self.project:
                    data = {
                        "name": self.project.title,
                        "project_code": str(self.project.id),
                        "project_state": (
                            "Confirmed" if self.project.is_chargable() else "Internal"
                        ),
                        "tags": ["CHAOTICA"],
                        "description": config.RM_WARNING_MSG
                        + " {}".format(ext_reverse(self.project.get_absolute_url())),
                    }
                elif self.slotType:
                    data = {
                        "name": str(self.slotType),
                        "project_code": str(self.slotType.pk),
                        "project_state": "Internal",
                        "tags": ["CHAOTICA"],
                        "description": config.RM_WARNING_MSG
                        + " {}".format(ext_reverse("/")),
                    }
                else:
                    log.error("No phase or project assigned")
                    return False

                r_add = client.post("/api/v1/projects", json=data)
                if r_add.status_code != 200:
                    if r_add.status_code == 400:
                        log.error("Invalid JSON sent")
                        return False
                    if r_add.status_code == 401:
                        log.error("RM API Token Invalid")
                        return False
                    else:
                        log.warning(
                            " ! Got a non-200 status code: %s", r_add.status_code
                        )
                        return False
                self.rm_data = r_add.json()
                self.rm_id = self.rm_data["id"]
                log.info("Created project in RM - id: %s", self.rm_data["id"])
            self.last_sync_result = True

        except RMReadOnlyError as ex:
            log.warning("Skipped RM write (read-only): %s", ex)
            self.last_sync_result = False
        except Exception as ex:
            log.error("Sync error: %s", ex)
            self.last_sync_result = False
        finally:
            self.last_synced = timezone.now()
            self.save()

    def delete_in_rm(self, client=None):
        client = client or RMClient()
        log = logger
        log.info("Deleting RM project for %s", self)

        try:
            if not self.rm_id:
                log.error("No ID to delete")
                return False
            r_delete = client.delete("/api/v1/projects/{}".format(self.rm_id))
            if r_delete.status_code != 200:
                if r_delete.status_code == 400:
                    log.error("Invalid JSON sent")
                    return False
                if r_delete.status_code == 401:
                    log.error("RM API Token Invalid")
                    return False
                elif r_delete.status_code == 404:
                    log.warning("RM project not found")
                    self.rm_id = ""
                    return False
                else:
                    log.warning(
                        " ! Got a non-200 status code: %s", r_delete.status_code
                    )
                    return False
            log.info("Deleted project in RM - id: %s", self.rm_id)
            self.rm_id = None
            self.last_sync_result = False

        except RMReadOnlyError as ex:
            log.warning("Skipped RM delete (read-only): %s", ex)
        except Exception as ex:
            log.error("Sync error: %s", ex)
            self.last_sync_result = False
        finally:
            self.last_synced = timezone.now()
            self.save()


class RMAssignableSlot(models.Model):
    slot = models.OneToOneField(
        TimeSlot,
        on_delete=models.CASCADE,
        related_name="rm_assignable",
        blank=False,
        primary_key=True,
    )
    rm_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        unique=True,
        help_text="Assignable ID in Resource Manager",
    )
    rm_data = models.JSONField(default=list, blank=True)

    last_synced = models.DateTimeField(null=True, blank=True)
    last_sync_result = models.BooleanField(default=False)

    class Meta:
        ordering = ["rm_id"]

    def __str__(self):
        return "({}) {}".format(self.rm_id, str(self.slot))

    def update_rm_if_stale(self):
        if (
            not self.last_synced
            or not self.last_sync_result
            or self.last_synced < (timezone.now() - timedelta(days=1))
            or self.last_synced < self.slot.updated
        ):
            return self.update_rm()
        return False

    def update_rm(self, client=None):
        """Create/update the RM assignment mirroring this CHAOTICA timeslot (push).

        Note: RM assignment writes use ``%d-%m-%Y`` dates — this is the format the live
        production push has always used and RM accepts it, so it is intentionally left
        unchanged here. (Inbound reads parse RM's ISO ``%Y-%m-%d`` dates separately.)
        """
        client = client or RMClient()
        log = logger
        log.info("Starting RM Sync for %s", self.slot)

        should_create = self.rm_id is None
        rm_user = RMSyncRecord.objects.get(user=self.slot.user)

        if self.slot.is_delivery():
            rm_ass = RMAssignable.objects.get(phase=self.slot.phase)
        elif self.slot.is_project():
            rm_ass = RMAssignable.objects.get(project=self.slot.project)
        else:
            rm_ass = RMAssignable.objects.get(slotType=self.slot.slot_type)

        if not rm_ass:
            log.warning("Nothing to assign to currently")
            return False

        starts_at = timezone.localtime(self.slot.start).strftime("%d-%m-%Y")
        ends_at = timezone.localtime(self.slot.end).strftime("%d-%m-%Y")

        try:
            if self.rm_id:
                r_check = client.get(
                    "/api/v1/users/{}/assignments/{}".format(rm_user.rm_id, self.rm_id)
                )
                if r_check.status_code != 200:
                    if r_check.status_code == 400:
                        log.error("Invalid JSON sent")
                        return False
                    if r_check.status_code == 401:
                        log.error("RM API Token Invalid")
                        return False
                    elif r_check.status_code == 404:
                        log.warning("RM assignment not found")
                        should_create = True
                    else:
                        log.error(
                            " ! Got a non-200 status code: %s", r_check.status_code
                        )
                        return False
                else:
                    self.rm_data = r_check.json()

                # Lets see if we should update!
                if not should_create and (
                    self.rm_data["starts_at"] != starts_at
                    or self.rm_data["ends_at"] != ends_at
                ):
                    data = {
                        "starts_at": starts_at,
                        "ends_at": ends_at,
                        "user_id": rm_user.rm_id,
                    }
                    r_upd = client.put(
                        "/api/v1/users/{}/assignments/{}".format(
                            rm_user.rm_id, self.rm_id
                        ),
                        json=data,
                    )
                    if r_upd.status_code != 200:
                        if r_upd.status_code == 400:
                            log.error("Invalid JSON sent")
                            return False
                        if r_upd.status_code == 401:
                            log.error("RM API Token Invalid")
                            return False
                        elif r_upd.status_code == 404:
                            log.warning("RM slot not found")
                            should_create = True
                        else:
                            log.warning(
                                " ! Got a non-200 status code: %s", r_upd.status_code
                            )
                            return False
                    else:
                        self.rm_data = r_upd.json()
                        self.rm_id = self.rm_data["id"]
                        log.info(
                            "Updated assignment in RM - id: %s", self.rm_data["id"]
                        )

            if should_create:
                data = {
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "assignable_id": rm_ass.rm_id,
                    "user_id": rm_user.rm_id,
                    "note": config.RM_WARNING_MSG
                    + " {}".format(ext_reverse(rm_ass.get_absolute_url())),
                    "description": config.RM_WARNING_MSG
                    + " {}".format(ext_reverse(rm_ass.get_absolute_url())),
                }
                r_add = client.post(
                    "/api/v1/users/{}/assignments".format(rm_user.rm_id), json=data
                )
                if r_add.status_code != 200:
                    if r_add.status_code == 400:
                        log.error("Invalid JSON sent")
                        return False
                    if r_add.status_code == 401:
                        log.error("RM API Token Invalid")
                        return False
                    else:
                        log.warning(
                            " ! Got a non-200 status code: %s", r_add.status_code
                        )
                        return False
                self.rm_data = r_add.json()
                self.rm_id = self.rm_data["id"]
                log.info("Created assignment in RM - id: %s", self.rm_data["id"])

            self.last_sync_result = True

        except RMReadOnlyError as ex:
            log.warning("Skipped RM write (read-only): %s", ex)
            self.last_sync_result = False
        except Exception as ex:
            log.error("Sync error: %s", ex)
            self.last_sync_result = False
        finally:
            self.last_synced = timezone.now()
            self.save()

    def delete_in_rm(self, client=None):
        client = client or RMClient()
        log = logger
        log.info("Deleting RM assignment for %s", self.slot)

        if not RMSyncRecord.objects.filter(user=self.slot.user).exists():
            return False
        rm_user = RMSyncRecord.objects.get(user=self.slot.user)

        try:
            if not self.rm_id:
                log.error("No ID to delete")
                return False
            r_delete = client.delete(
                "/api/v1/users/{}/assignments/{}".format(rm_user.rm_id, self.rm_id)
            )
            if r_delete.status_code != 200:
                if r_delete.status_code == 400:
                    log.error("Invalid JSON sent")
                    return False
                if r_delete.status_code == 401:
                    log.error("RM API Token Invalid")
                    return False
                elif r_delete.status_code == 404:
                    log.warning("RM assignment not found")
                else:
                    log.warning(
                        " ! Got a non-200 status code: %s", r_delete.status_code
                    )
                    return False
            log.info("Deleted assignment in RM - id: %s", self.rm_id)
            self.rm_id = None
            self.last_sync_result = False

        except RMReadOnlyError as ex:
            log.warning("Skipped RM delete (read-only): %s", ex)
        except Exception as ex:
            log.error("Sync error: %s", ex)
            self.last_sync_result = False
        finally:
            self.last_synced = timezone.now()
            self.save()


@receiver(pre_delete, sender=RMAssignableSlot)
def remove_assignment_from_rm_on_delete(sender, instance, **kwargs):
    instance.delete_in_rm()


class RMInboundSlot(models.Model):
    """Maps a CHAOTICA TimeSlot created by an inbound (PULL) sync back to its RM assignment.

    Deliberately NOT ``RMAssignableSlot`` (which is push-oriented, 1:1 with a TimeSlot and has
    a *unique* ``rm_id``). A single RM assignment can fan out into many CHAOTICA day-slots
    (partial allocations — see ``inbound.py``), so ``rm_assignment_id`` here is indexed but
    **not unique**. Only these rows are ever touched by inbound reconcile, which guarantees a
    PULL sync can never delete a CHAOTICA-native or PUSH-origin slot.
    """

    timeslot = models.OneToOneField(
        TimeSlot,
        on_delete=models.CASCADE,
        related_name="rm_inbound",
        primary_key=True,
    )
    record = models.ForeignKey(
        "RMSyncRecord",
        on_delete=models.CASCADE,
        related_name="inbound_slots",
    )
    rm_assignment_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Assignment ID in Resource Manager (not unique — may fan out to N slots).",
    )
    day = models.DateField(
        null=True,
        blank=True,
        help_text="For fanned-out partial allocations, the day this slot represents.",
    )
    rm_data = models.JSONField(default=dict, blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["record", "rm_assignment_id", "day"]
        unique_together = (("record", "rm_assignment_id", "day"),)

    def __str__(self):
        return "RM assignment {} → {}".format(self.rm_assignment_id, self.timeslot)


class RMSyncRecord(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rm_sync_record",
    )
    rm_id = models.CharField(
        max_length=255, unique=True, help_text="User ID in Resource Manager"
    )
    rm_data = models.JSONField(default=list, blank=True)
    market_unit = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="RM 'Market Unit' for this user (drives OU/direction via RMUnitMap).",
    )
    rm_role = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="RM 'role' for this user (mapped to an org-unit role on their membership).",
    )

    last_synced = models.DateTimeField(null=True, blank=True)
    last_sync_result = models.BooleanField(default=False)
    sync_in_progress = models.BooleanField(default=False)

    direction = models.IntegerField(
        choices=RMSyncDirection.CHOICES,
        default=RMSyncDirection.OFF,
        help_text=(
            "OFF = no sync. PUSH = CHAOTICA is the source of truth (mirror to RM). "
            "PULL = RM is the source of truth (import into CHAOTICA)."
        ),
    )
    sync_authoritative = models.BooleanField(
        default=False,
        help_text=(
            "Prune the destination to match the source. For PUSH: delete RM assignments "
            "unknown to CHAOTICA. For PULL: delete CHAOTICA RM-origin slots absent from RM. "
            "When off, the sync only adds/updates and never deletes."
        ),
    )

    class Meta:
        ordering = ["user"]

    def __str__(self):
        return "({}) {}".format(self.rm_id, str(self.user))

    @property
    def sync_enabled(self):
        """Backwards-compatible helper: is this record participating in any sync?"""
        return self.direction != RMSyncDirection.OFF

    def pull_records(self, client=None, dry_run=False):
        """Import this user's RM schedule into CHAOTICA (RM → CHAOTICA).

        Delegates to ``rm_sync.inbound`` (imported lazily to avoid a circular import).
        Returns an ``InboundResult`` summarising created/updated/deleted/skipped items.
        """
        from .inbound import pull_user

        return pull_user(self, client=client, dry_run=dry_run)

    def sync_records(self, start_date=None, end_date=None):
        """Push this user's CHAOTICA schedule to RM (and, if authoritative, prune RM)."""
        if start_date is None:
            start_date = timezone.now().date()
        if end_date is None:
            end_date = (timezone.now() + timedelta(days=365)).date()

        log = logger

        if self.sync_in_progress:
            # In progress - skip
            return

        log.info("Starting sync for user: %s (RM ID: %s)", self.user.email, self.rm_id)

        self.sync_in_progress = True
        self.save()

        client = RMClient()

        try:
            if not config.RM_SYNC_ENABLED:
                log.error("Sync disabled for site")
                return False
            if not config.RM_SYNC_API_TOKEN:
                log.error("Sync API token missing")
                return False
            if self.direction != RMSyncDirection.PUSH:
                log.error("Push sync not enabled for user (direction != PUSH)")
                return False
            if not self.rm_id:
                log.error("RM ID missing for user")
                return False

            # First - check if the defined user exists...
            log.info("- Checking RM user ID")
            r_check_user = client.get("/api/v1/users/{}".format(self.rm_id))
            if r_check_user.status_code != 200:
                if r_check_user.status_code == 401:
                    log.error("RM API Token Invalid")
                    return False
                elif r_check_user.status_code == 404:
                    log.error("RM user not found")
                    return False
                else:
                    log.warning(
                        " ! Got a non-200 status code: %s", r_check_user.status_code
                    )
                    return False

            rm_user = r_check_user.json()

            if rm_user["archived"]:
                log.info("RM user is archived. Stopping sync.")
                return False

            if rm_user["deleted"]:
                log.info("RM user is deleted. Stopping sync.")
                return False

            # Let's log the response just for info!
            self.rm_data = rm_user

            # Ok, RM user is good. Lets get our chaotica schedule for the next year.
            log.info("- Getting Chaotica schedule")
            ch_slots = self.user.get_timeslots_objs(
                start_date=start_date,
                end_date=end_date,
            )

            # OK NOW FOR THE BIG BIT!!!
            for slot in ch_slots:
                # Check we've got an assignable first!
                ch_assignable = None
                if slot.is_delivery():
                    ch_assignable, _ = RMAssignable.objects.get_or_create(
                        phase=slot.phase
                    )
                elif slot.is_project():
                    ch_assignable, _ = RMAssignable.objects.get_or_create(
                        project=slot.project
                    )
                elif slot.is_internal():
                    ch_assignable, _ = RMAssignable.objects.get_or_create(
                        slotType=slot.slot_type
                    )

                if ch_assignable:
                    ch_assignable.update_rm_if_stale()

                # Check if we're already in the list...
                ch_a_slot, _ = RMAssignableSlot.objects.get_or_create(slot=slot)
                ch_a_slot.update_rm_if_stale()

            if self.sync_authoritative:
                # Ok, if we're authoritative... we want to remove any slots we don't
                # know about. Get the RM schedule (paginated) and delete anything CHAOTICA
                # isn't tracking.
                log.info("- Getting RM schedule")
                for assignment in client.paginate(
                    "/api/v1/users/{}/assignments".format(self.rm_id),
                    {"from": timezone.now().strftime("%Y-%m-%d")},
                ):
                    if not RMAssignableSlot.objects.filter(
                        rm_id=assignment["id"]
                    ).exists():
                        # This RM slot isn't known to chaotica...
                        log.warning(
                            "Found unknown slot: %s-%s: %s",
                            assignment["starts_at"],
                            assignment["ends_at"],
                            assignment.get("description"),
                        )
                        r_delete = client.delete(
                            "/api/v1/users/{}/assignments/{}".format(
                                self.rm_id, assignment["id"]
                            )
                        )
                        if r_delete.status_code != 200:
                            log.warning(
                                " ! Got a non-200 status code: %s",
                                r_delete.status_code,
                            )

            self.last_sync_result = True

        except RMReadOnlyError as ex:
            log.warning("Skipped RM write (read-only): %s", ex)
            self.last_sync_result = False
        except Exception as ex:
            log.exception("Sync error: %s", ex)
            self.last_sync_result = False

        finally:
            self.last_synced = timezone.now()
            self.sync_in_progress = False
            self.save()
