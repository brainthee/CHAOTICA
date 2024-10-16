from django.db import models
from django.conf import settings
from constance import config
from django.utils import timezone
from datetime import timedelta
import logging, requests, json
from chaotica_utils.utils import NoColorFormatter
from io import StringIO
import urllib3
from jobtracker.models import Phase, Project, TimeSlot, TimeSlotType
from jobtracker.enums import (
    DefaultTimeSlotTypes,
)
from chaotica_utils.utils import ext_reverse
from django.db.models.signals import pre_delete
from django.dispatch import receiver

urllib3.disable_warnings()


class RMTaskLock(models.Model):
    task_id = models.CharField(
        max_length=255,
        unique=True,
    )
    started = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    def is_stale(self):
        now = timezone.now()
        time_diff = (now - self.last_updated).total_seconds() / int(config.RM_SYNC_STALE_TIMEOUT) * 60
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

    def update_rm(self):
        PROXIES = None
        # PROXIES = {
        #     "http": "http://127.0.0.1:8080",
        #     "https": "http://127.0.0.1:8080",
        # }
        RM_HEADERS = {
            "Content-Type": "application/json; charset=utf-8",
            "auth": config.RM_SYNC_API_TOKEN,
        }
        VERIFY_TLS = False
        # Setup logging
        log_stream = StringIO()
        stream_handler = logging.StreamHandler(log_stream)
        stream_handler.setFormatter(NoColorFormatter())
        log = logging.getLogger(__name__)
        log.setLevel(logging.INFO)
        log.addHandler(stream_handler)
        if self.phase:
            log.info("Starting RM Sync for {}".format(self.phase))
        elif self.project:
            log.info("Starting RM Sync for {}".format(self.project))
        elif self.slotType:
            log.info("Starting RM Sync for {}".format(self.slotType))
        else:
            log.error("Told to start sync for a assignable with no project/phase")

        should_create = self.rm_id == None

        try:
            if self.rm_id:
                # Project should already exist...
                r_check_project = requests.get(
                    "{}/api/v1/projects/{}".format(config.RM_SYNC_API_SITE, self.rm_id),
                    headers=RM_HEADERS,
                    proxies=PROXIES,
                    verify=VERIFY_TLS,
                )
                if r_check_project.status_code != 200:
                    if r_check_project.status_code == 400:
                        log.error("Invalid JSON sent")
                        return False
                    if r_check_project.status_code == 401:
                        log.error("RM API Token Invalid")
                        return False
                    elif r_check_project.status_code == 404:
                        log.warning("RM project not found")
                        should_create = True
                    else:
                        log.error(
                            " ! Got a non-200 status code: {}".format(
                                r_check_project.status_code
                            )
                        )
                        return False
                # Ok - should have it!
                self.rm_data = r_check_project.json()

            if should_create:
                # Create the project!
                if self.phase:
                    data = {
                        "name": self.phase.title,
                        "project_code": self.phase.phase_id,
                        "tags": ["CHAOTICA"],
                        "client": str(self.phase.job.client),
                        "description": config.RM_WARNING_MSG
                        + " {}".format(ext_reverse(self.phase.get_absolute_url())),
                    }
                elif self.project:
                    data = {
                        "name": self.project.title,
                        "project_code": str(self.project.id),
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

                r_add_project = requests.post(
                    "{}/api/v1/projects".format(config.RM_SYNC_API_SITE, self.rm_id),
                    json=data,
                    headers=RM_HEADERS,
                    proxies=PROXIES,
                    verify=VERIFY_TLS,
                )
                if r_add_project.status_code != 200:
                    if r_add_project.status_code == 400:
                        log.error("Invalid JSON sent")
                        return False
                    if r_add_project.status_code == 401:
                        log.error("RM API Token Invalid")
                        return False
                    elif r_add_project.status_code == 404:
                        log.warning("RM project not found")
                        should_create = True
                    else:
                        log.warning(
                            " ! Got a non-200 status code: {}".format(
                                r_add_project.status_code
                            )
                        )
                        return False
                self.rm_data = r_add_project.json()
                self.rm_id = self.rm_data["id"]
                log.info("Created project in RM - id: {}".format(self.rm_data["id"]))
            self.last_sync_result = True

        except Exception as ex:
            # Something borked....
            from pprint import pprint

            pprint(ex)
            log.error("Sync error: {}".format(ex))
            self.last_sync_result = False

        finally:
            self.last_synced = timezone.now()
            self.save()
            print((log_stream.getvalue() + ".")[:-1])

    def delete_in_rm(self):
        PROXIES = None
        # PROXIES = {
        #     "http": "http://127.0.0.1:8080",
        #     "https": "http://127.0.0.1:8080",
        # }
        RM_HEADERS = {
            "Content-Type": "application/json; charset=utf-8",
            "auth": config.RM_SYNC_API_TOKEN,
        }
        VERIFY_TLS = False
        # Setup logging
        log_stream = StringIO()
        stream_handler = logging.StreamHandler(log_stream)
        stream_handler.setFormatter(NoColorFormatter())
        log = logging.getLogger(__name__)
        log.setLevel(logging.INFO)
        log.addHandler(stream_handler)
        if self.phase:
            log.info("Deleting RM project for {}".format(self.phase))
        elif self.project:
            log.info("Deleting RM project for {}".format(self.project))
        elif self.slotType:
            log.info("Deleting RM project for {}".format(self.slotType))
        else:
            log.error("Told to delete project for a assignable with no project/phase")

        try:
            if not self.rm_id:
                log.error("No ID to delete")
                return False
            else:
                r_delete_project = requests.delete(
                    "{}/api/v1/projects/{}".format(config.RM_SYNC_API_SITE, self.rm_id),
                    headers=RM_HEADERS,
                    proxies=PROXIES,
                    verify=VERIFY_TLS,
                )
                if r_delete_project.status_code != 200:
                    if r_delete_project.status_code == 400:
                        log.error("Invalid JSON sent")
                        return False
                    if r_delete_project.status_code == 401:
                        log.error("RM API Token Invalid")
                        return False
                    elif r_delete_project.status_code == 404:
                        log.warning("RM project not found")
                        self.rm_id = ""
                        return False
                    else:
                        log.warning(
                            " ! Got a non-200 status code: {}".format(
                                r_delete_project.status_code
                            )
                        )
                        return False
                log.info("Deleted project in RM - id: {}".format(self.rm_data["id"]))
                self.rm_id = None
            self.last_sync_result = False

        except Exception as ex:
            log.error("Sync error: {}".format(ex))
            self.last_sync_result = False
        finally:
            self.last_synced = timezone.now()
            self.save()
            print((log_stream.getvalue() + ".")[:-1])


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

    def update_rm_if_stale(self):
        if (
            not self.last_synced
            or not self.last_sync_result
            or self.last_synced < (timezone.now() - timedelta(days=1))
            or self.last_synced < self.slot.updated
        ):
            return self.update_rm()
        return False


    def update_rm(self):
        PROXIES = None
        # PROXIES = {
        #     "http": "http://127.0.0.1:8080",
        #     "https": "http://127.0.0.1:8080",
        # }
        RM_HEADERS = {
            "Content-Type": "application/json; charset=utf-8",
            "auth": config.RM_SYNC_API_TOKEN,
        }
        VERIFY_TLS = False
        # Setup logging
        log_stream = StringIO()
        stream_handler = logging.StreamHandler(log_stream)
        stream_handler.setFormatter(NoColorFormatter())
        log = logging.getLogger(__name__)
        log.setLevel(logging.INFO)
        log.addHandler(stream_handler)
        log.info("Starting RM Sync for {}".format(self.slot))

        should_create = self.rm_id == None
        # Get user ID:
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

        try:
            if self.rm_id:

                r_check_assignment = requests.get(
                    "{}/api/v1/users/{}/assignments/{}".format(
                        config.RM_SYNC_API_SITE, rm_user.rm_id, self.rm_id
                    ),
                    headers=RM_HEADERS,
                    proxies=PROXIES,
                    verify=VERIFY_TLS,
                )
                if r_check_assignment.status_code != 200:
                    if r_check_assignment.status_code == 400:
                        log.error("Invalid JSON sent")
                        return False
                    if r_check_assignment.status_code == 401:
                        log.error("RM API Token Invalid")
                        return False
                    elif r_check_assignment.status_code == 404:
                        log.warning("RM assignment not found")
                        should_create = True
                    else:
                        log.error(
                            " ! Got a non-200 status code: {}".format(
                                r_check_assignment.status_code
                            )
                        )
                        return False
                # Ok - should have it!
                self.rm_data = r_check_assignment.json()

                # Lets see if we should update!
                if not should_create and (
                    self.rm_data["starts_at"] != self.slot.start.strftime("%d-%m-%Y")
                    or self.rm_data["ends_at"] != self.slot.end.strftime("%d-%m-%Y")
                ):
                    # Dates are wrong - lets update
                    data = {
                        "starts_at": self.slot.start.strftime("%d-%m-%Y"),
                        "ends_at": self.slot.end.strftime("%d-%m-%Y"),
                        "user_id": rm_user.rm_id,
                    }
                    r_upd_assignment = requests.put(
                        "{}/api/v1/users/{}/assignments/{}".format(
                            config.RM_SYNC_API_SITE,
                            rm_user.rm_id,
                            self.rm_id
                        ),
                        json=data,
                        headers=RM_HEADERS,
                        proxies=PROXIES,
                        verify=VERIFY_TLS,
                    )
                    if r_upd_assignment.status_code != 200:
                        if r_upd_assignment.status_code == 400:
                            log.error("Invalid JSON sent")
                            return False
                        if r_upd_assignment.status_code == 401:
                            log.error("RM API Token Invalid")
                            return False
                        elif r_upd_assignment.status_code == 404:
                            log.warning("RM slot not found")
                            should_create = True
                        else:
                            log.warning(
                                " ! Got a non-200 status code: {}".format(
                                    r_upd_assignment.status_code
                                )
                            )
                            return False
                    self.rm_data = r_upd_assignment.json()
                    self.rm_id = self.rm_data["id"]
                    log.info("Updated assignment in RM - id: {}".format(self.rm_data["id"]))


            if should_create:
                # Create the assignment!
                data = {
                    "starts_at": self.slot.start.strftime("%d-%m-%Y"),
                    "ends_at": self.slot.end.strftime("%d-%m-%Y"),
                    "assignable_id": rm_ass.rm_id,
                    "user_id": rm_user.rm_id,
                    "note": config.RM_WARNING_MSG
                    + " {}".format(ext_reverse(rm_ass.get_absolute_url())),
                    "description": config.RM_WARNING_MSG
                    + " {}".format(ext_reverse(rm_ass.get_absolute_url())),
                }
                r_add_assignment = requests.post(
                    "{}/api/v1/users/{}/assignments".format(
                        config.RM_SYNC_API_SITE,
                        rm_user.rm_id,
                    ),
                    json=data,
                    headers=RM_HEADERS,
                    proxies=PROXIES,
                    verify=VERIFY_TLS,
                )
                if r_add_assignment.status_code != 200:
                    if r_add_assignment.status_code == 400:
                        log.error("Invalid JSON sent")
                        return False
                    if r_add_assignment.status_code == 401:
                        log.error("RM API Token Invalid")
                        return False
                    elif r_add_assignment.status_code == 404:
                        log.warning("RM slot not found")
                        should_create = True
                    else:
                        log.warning(
                            " ! Got a non-200 status code: {}".format(
                                r_add_assignment.status_code
                            )
                        )
                        return False
                self.rm_data = r_add_assignment.json()
                self.rm_id = self.rm_data["id"]
                log.info("Created assignment in RM - id: {}".format(self.rm_data["id"]))

            self.last_sync_result = True

        except Exception as ex:
            # Something borked....
            from pprint import pprint

            pprint(ex)
            log.error("Sync error: {}".format(ex))
            self.last_sync_result = False

        finally:
            self.last_synced = timezone.now()
            self.save()
            print((log_stream.getvalue() + ".")[:-1])

    def delete_in_rm(self):
        PROXIES = None
        # PROXIES = {
        #     "http": "http://127.0.0.1:8080",
        #     "https": "http://127.0.0.1:8080",
        # }
        RM_HEADERS = {
            "Content-Type": "application/json; charset=utf-8",
            "auth": config.RM_SYNC_API_TOKEN,
        }
        VERIFY_TLS = False
        # Setup logging
        log_stream = StringIO()
        stream_handler = logging.StreamHandler(log_stream)
        stream_handler.setFormatter(NoColorFormatter())
        log = logging.getLogger(__name__)
        log.setLevel(logging.INFO)
        log.addHandler(stream_handler)
        log.info("Deleting RM assignment for {}".format(self.slot))
        rm_user = RMSyncRecord.objects.get(user=self.slot.user)

        try:
            if not self.rm_id:
                log.error("No ID to delete")
                return False
            else:
                r_delete_ass = requests.delete(
                    "{}/api/v1/users/{}/assignments/{}".format(
                        config.RM_SYNC_API_SITE, rm_user.rm_id, self.rm_id
                    ),
                    headers=RM_HEADERS,
                    proxies=PROXIES,
                    verify=VERIFY_TLS,
                )
                if r_delete_ass.status_code != 200:
                    if r_delete_ass.status_code == 400:
                        log.error("Invalid JSON sent")
                        return False
                    if r_delete_ass.status_code == 401:
                        log.error("RM API Token Invalid")
                        return False
                    elif r_delete_ass.status_code == 404:
                        log.warning("RM assignment not found")
                    else:
                        log.warning(
                            " ! Got a non-200 status code: {}".format(
                                r_delete_ass.status_code
                            )
                        )
                        return False
                log.info("Deleted assignment in RM - id: {}".format(self.rm_data["id"]))
                self.rm_id = None
            self.last_sync_result = False

        except Exception as ex:
            log.error("Sync error: {}".format(ex))
            self.last_sync_result = False
        finally:
            self.last_synced = timezone.now()
            self.save()
            print((log_stream.getvalue() + ".")[:-1])
    

@receiver(pre_delete, sender=RMAssignableSlot)
def remove_assignment_from_rm_on_delete(sender, instance, **kwargs):
    instance.delete_in_rm()


class RMSyncRecord(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rm_sync_record",
    )
    rm_id = models.CharField(max_length=255, unique=True, help_text="User ID in Resource Manager")
    rm_data = models.JSONField(default=list, blank=True)

    last_synced = models.DateTimeField(null=True, blank=True)
    last_sync_result = models.BooleanField(default=False)
    sync_in_progress = models.BooleanField(default=False)

    sync_enabled = models.BooleanField(default=False, help_text="Should sync schedules")
    sync_authoritative = models.BooleanField(
        default=False,
        help_text="Removes all non-CHAOTICA time slots. Effectively takes full control.",
    )

    class Meta:
        ordering = ["user"]

    def __str__(self):
        return "({}) {}".format(self.rm_id, str(self.user))

    def sync_records(self):
        if self.sync_in_progress:
            # In progress - skip
            return
        
        self.sync_in_progress = True
        self.save()

        PROXIES = None
        # PROXIES = {
        #     "http": "http://127.0.0.1:8080",
        #     "https": "http://127.0.0.1:8080",
        # }
        RM_HEADERS = {
            "Content-Type": "application/json; charset=utf-8",
            "auth": config.RM_SYNC_API_TOKEN,
        }
        VERIFY_TLS = False

        # Setup logging
        log_stream = StringIO()
        stream_handler = logging.StreamHandler(log_stream)
        stream_handler.setFormatter(NoColorFormatter())
        log = logging.getLogger(__name__)
        log.setLevel(logging.INFO)
        log.addHandler(stream_handler)
        log.info("Starting RM Sync for {}".format(self.user))

        from pprint import pprint

        try:
            if not config.RM_SYNC_ENABLED:
                log.error("Sync disabled for site")
                return False
            if not config.RM_SYNC_API_TOKEN:
                log.error("Sync API token missing")
                return False
            if not self.sync_enabled:
                log.error("Sync disabled for user")
                return False
            if not self.rm_id:
                log.error("RM ID missing for user")
                return False

            # First - check if the defined user exists...
            log.info("- Checking RM user ID")
            r_check_user = requests.get(
                "{}/api/v1/users/{}".format(config.RM_SYNC_API_SITE, self.rm_id),
                headers=RM_HEADERS,
                proxies=PROXIES,
                verify=VERIFY_TLS,
            )
            if r_check_user.status_code != 200:
                if r_check_user.status_code == 401:
                    log.error("RM API Token Invalid")
                    return False
                elif r_check_user.status_code == 404:
                    log.error("RM user not found")
                    return False
                else:
                    log.warning(
                        " ! Got a non-200 status code: {}".format(
                            r_check_user.status_code
                        )
                    )
                    return False

            rm_user = r_check_user.json()
            # Check for things like deleted, archived, etc

            if rm_user["archived"]:
                log.error("RM user is archived. Stopping sync.")
                return False

            if rm_user["deleted"]:
                log.error("RM user is deleted. Stopping sync.")
                return False

            # Let's log the response just for info!
            self.rm_data = rm_user

            # Ok, RM user is good. Lets get our chaotica schedule for the next year.
            log.info("- Getting Chaotica schedule")
            ch_slots = self.user.get_timeslots_objs(
                start=timezone.now(), end=timezone.now() + timedelta(days=365)
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
                # Ok, if we're authoritive... we want to remove any slots we don't know about...
                # Now lets get RM schedule...
                log.info("- Getting RM schedule")
                r_schedule = requests.get(
                    "{}/api/v1/users/{}/assignments?from={}".format(
                        config.RM_SYNC_API_SITE,
                        self.rm_id,
                        timezone.now().strftime("%Y-%m-%d"),
                    ),
                    headers=RM_HEADERS,
                    proxies=PROXIES,
                    verify=VERIFY_TLS,
                )
                if r_schedule.status_code != 200:
                    log.warning(
                        " ! Got a non-200 status code: {}".format(
                            r_check_user.status_code
                        )
                    )
                    return False
                # Now we have it, lets go through...
                rm_schedule = r_schedule.json()
                for assignment in rm_schedule["data"]:
                    if not RMAssignableSlot.objects.filter(
                        rm_id=assignment["id"]
                    ).exists():
                        # This RM slot isn't known to chaotica...
                        log.warning(
                            "Found unknown slot: {}-{}: {}".format(
                                assignment["starts_at"],
                                assignment["ends_at"],
                                assignment["description"],
                            )
                        )
                        r_delete_ass = requests.delete(
                            "{}/api/v1/users/{}/assignments/{}".format(
                                config.RM_SYNC_API_SITE, self.rm_id, assignment["id"]
                            ),
                            headers=RM_HEADERS,
                            proxies=PROXIES,
                            verify=VERIFY_TLS,
                        )
                        if r_delete_ass.status_code != 200:
                            log.warning(
                                " ! Got a non-200 status code: {}".format(
                                    r_delete_ass.status_code
                                )
                            )

            self.last_sync_result = True
        except Exception as ex:
            # Something borked....
            from pprint import pprint

            pprint(ex)
            log.error("Sync error: {}".format(ex))
            self.last_sync_result = False

        finally:
            self.last_synced = timezone.now()
            self.sync_in_progress = False
            self.save()
            print((log_stream.getvalue() + ".")[:-1])
