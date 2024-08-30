from chaotica_utils.impex.baseImporter import BaseImporter
from structlog import wrap_logger
import logging
import json
from django.utils import timezone
from django.conf import settings
from datetime import time
from django.db.models import Q
from io import StringIO
from pprint import pprint
from chaotica_utils.models import User, Group, LeaveRequest
from chaotica_utils.utils import NoColorFormatter
from chaotica_utils.enums import UnitRoles, LeaveRequestTypes
from chaotica_utils.views import log_system_activity
from jobtracker.models import (
    OrganisationalUnit,
    OrganisationalUnitMember,
    Client,
    Project,
    TimeSlot,
    TimeSlotType,
    Job,
    Phase,
    Service,
)
from jobtracker.enums import DefaultTimeSlotTypes, TimeSlotDeliveryRole
from django.core.files import File
from urllib.request import urlopen
from tempfile import NamedTemporaryFile


class ResourceManagerUserImporter(BaseImporter):

    def _convert_date_to_datetime(self, dte):
        try:
            return timezone.datetime.strptime(dte, "%m/%d/%y")
        except ValueError:
            return timezone.datetime.strptime(dte, "%Y-%m-%d")

    def _convert_date_to_datetime_startofday(self, dte):
        return timezone.datetime.combine(self._convert_date_to_datetime(dte), time.min)

    def _convert_date_to_datetime_endofday(self, dte):
        return timezone.datetime.combine(self._convert_date_to_datetime(dte), time.max)

    def import_data(self, request, data):
        # Messy I know...
        leave_mappings = {
            3554148: {
                "id": 3554148,
                "name": "Regular Vacation",
                "mapping": LeaveRequestTypes.ANNUAL_LEAVE,
            },
            3554149: {
                "id": 3554149,
                "name": "Sick Leave",
                "mapping": LeaveRequestTypes.SICK,
            },
            3627866: {
                "id": 3627866,
                "name": "Public Holiday",
                "mapping": LeaveRequestTypes.PUBLIC_HOLIDAY,
            },
            3629082: {
                "id": 3629082,
                "name": "Non-working Day",
                "mapping": LeaveRequestTypes.NON_WORKING,
            },
            5398051: {
                "id": 5398051,
                "name": "Paternity Leave",
                "mapping": LeaveRequestTypes.PATERNITY_MATERNITY,
            },
            7227966: {
                "id": 7227966,
                "name": "TOIL",
                "mapping": LeaveRequestTypes.TOIL,
            },
            7358397: {
                "id": 7358397,
                "name": "Regular Vacation (AM)",
                "mapping": LeaveRequestTypes.ANNUAL_LEAVE,
            },
            7358398: {
                "id": 7358398,
                "name": "Regular Vacation (PM)",
                "mapping": LeaveRequestTypes.ANNUAL_LEAVE,
            },
            7471523: {
                "id": 7471523,
                "name": "Bereavement Leave",
                "mapping": LeaveRequestTypes.COMPASSIONATE_LEAVE,
            },
            7471524: {
                "id": 7471524,
                "name": "Excused from Office",
                "mapping": LeaveRequestTypes.EXCUSED,
            },
            7471525: {
                "id": 7471525,
                "name": "Illness",
                "mapping": LeaveRequestTypes.SICK,
            },
            7471526: {
                "id": 7471526,
                "name": "Military Training",
                "mapping": LeaveRequestTypes.MILITARY_LEAVE,
            },
            7471527: {
                "id": 7471527,
                "name": "Other Approved Absence",
                "mapping": LeaveRequestTypes.OTHER_APPROVED,
            },
            7471528: {
                "id": 7471528,
                "name": "Overtime Vacation Taken",
                "mapping": LeaveRequestTypes.OVERTIME_LEAVE,
            },
            7471532: {
                "id": 7471532,
                "name": "Unpaid Absence",
                "mapping": LeaveRequestTypes.UNPAID_LEAVE,
            },
            7591503: {
                "id": 7591503,
                "name": "Jury Service",
                "mapping": LeaveRequestTypes.JURY_SERVICE,
            },
            7625621: {
                "id": 7625621,
                "name": "Medical Appointment",
                "mapping": LeaveRequestTypes.MEDICAL,
            },
            8398341: {
                "id": 8398341,
                "name": "Sabbatical Leave",
                "mapping": LeaveRequestTypes.SABBATICAL,
            },
        }
        log_stream = StringIO()
        logformatter = NoColorFormatter()
        stream_handler = logging.StreamHandler(log_stream)
        stream_handler.setFormatter(logformatter)

        log = logging.getLogger(__name__)
        log.setLevel(logging.INFO)
        log.addHandler(stream_handler)

        log.info("Starting import")

        if not data:
            log.error("Data is null to ResourceManagerUserImporter")
            raise ValueError("Data is null to ResourceManagerUserImporter")

        for user_file in data:
            log.info("Processing " + str(user_file))
            decoded_file = user_file.read().decode("utf-8")
            user_data = json.loads(decoded_file)

            if not user_data["email"].strip():
                log.warning(
                    "No email for this user: {display_name}. Skipping...".format(
                        user_data["display_name"].strip()
                    )
                )

            auth_email = user_data["email"].lower().strip()
            auth_email = auth_email.replace("accenture.com", "cyberdefense.global")
            auth_email = auth_email.replace("contextis.com", "cyberdefense.global")
            db_user, _ = User.objects.get_or_create(
                email__iexact=auth_email,
                defaults={
                    "email": auth_email,
                    "notification_email": user_data["email"].lower().strip(),
                    "external_id": user_data["id"],
                    "first_name": user_data["first_name"].strip(),
                    "last_name": user_data["last_name"].strip(),
                    "last_name": user_data["last_name"].strip(),
                },
            )

            if db_user.first_name != user_data["first_name"].strip():
                db_user.first_name = user_data["first_name"].strip()
            if db_user.last_name != user_data["last_name"].strip():
                db_user.last_name = user_data["last_name"].strip()

            if user_data["mobile_phone"]:
                db_user.phone_number = user_data["mobile_phone"].strip()

            if user_data["discipline"] == "Leavers" or user_data["archived"] == True:
                # User is archived; lets mark them inactive
                db_user.is_active = False

            # Deal with avatar pic
            if not db_user.profile_image and user_data["thumbnail"]:
                img_temp = NamedTemporaryFile(delete=True)
                img_temp.write(urlopen(user_data["thumbnail"]).read())
                img_temp.flush()
                db_user.profile_image.save(f"image_{db_user.pk}", File(img_temp))

            org_role = UnitRoles.CONSULTANT

            if user_data["role"] == "Consultant":
                grp = Group.objects.get(name=settings.GLOBAL_GROUP_PREFIX + "User")
                db_user.groups.add(grp)
            elif user_data["role"] == "Account Manager":
                grp = Group.objects.get(
                    name=settings.GLOBAL_GROUP_PREFIX + "Sales Member"
                )
                db_user.groups.add(grp)
                org_role = UnitRoles.SALES
            elif user_data["role"] == "Service Delivery Team":
                grp = Group.objects.get(
                    name=settings.GLOBAL_GROUP_PREFIX + "Service Delivery"
                )
                db_user.groups.add(grp)
                org_role = UnitRoles.SERVICE_DELIVERY
            else:
                log.warning("Found unknown role: {}".format(user_data["role"]))

            for custom_field in user_data["custom_field_values"]["data"]:

                if custom_field["custom_field_name"] == "Market Unit":
                    # Add to the right org unit...
                    if custom_field["value"]:
                        org_unit, _ = OrganisationalUnit.objects.get_or_create(
                            name=custom_field["value"].strip()
                        )

                        membership, _ = OrganisationalUnitMember.objects.get_or_create(
                            member=db_user, unit=org_unit
                        )
                        membership.roles.add(org_role)
                        membership.save()

                elif custom_field["custom_field_name"] == "Home Office Location":
                    if custom_field["value"]:
                        db_user.location = custom_field["value"].strip()

                elif custom_field["custom_field_name"] == "Client Onboarded":
                    if custom_field["value"]:
                        db_client, _ = Client.objects.get_or_create(
                            name=custom_field["value"].strip()
                        )
                        db_client.onboarded_users.add(db_user)
                        db_client.save()

            for assignment in user_data["assignments"]["data"]:
                # Lets see if there's a project!
                if Project.objects.filter(
                    external_id=assignment["assignable_id"]
                ).exists():
                    db_project = Project.objects.get(
                        external_id=assignment["assignable_id"]
                    )
                    # Lets create the timeslot!
                    _, _ = TimeSlot.objects.get_or_create(
                        start=self._convert_date_to_datetime_startofday(
                            assignment["starts_at"]
                        ),
                        end=self._convert_date_to_datetime_endofday(
                            assignment["ends_at"]
                        ),
                        slot_type=TimeSlotType.get_builtin_object(
                            DefaultTimeSlotTypes.INTERNAL_PROJECT
                        ),
                        user=db_user,
                        project=db_project,
                    )
                elif Job.objects.filter(
                    external_id=assignment["assignable_id"]
                ).exists():
                    db_job = Job.objects.get(external_id=assignment["assignable_id"])
                    # We only want to match jobs which don't have a sheet ID
                    # Without sheet data, we can only assume a single phase.
                    db_phase, db_phase_created = Phase.objects.get_or_create(
                        job=db_job,
                        title=db_job.title,
                        is_imported=True,
                    )
                    db_phase.service = Service.objects.get(name="Bespoke Consultancy")
                    db_phase.save()
                    if db_phase_created:
                        log.info('Created Phase: "' + db_job.title + '"')
                        log_system_activity(
                            db_phase,
                            "Imported Phase via RM User Allocation import",
                        )

                    # Lets create the timeslot!
                    _, _ = TimeSlot.objects.get_or_create(
                        start=self._convert_date_to_datetime_startofday(
                            assignment["starts_at"]
                        ),
                        end=self._convert_date_to_datetime_endofday(
                            assignment["ends_at"]
                        ),
                        slot_type=TimeSlotType.get_builtin_object(
                            DefaultTimeSlotTypes.DELIVERY
                        ),
                        user=db_user,
                        deliveryRole=TimeSlotDeliveryRole.DELIVERY,
                        phase=db_phase,
                    )
                elif assignment["assignable_id"] in leave_mappings:
                    # It's a kind of leave...
                    # Lets create the timeslot!
                    db_timeslot, _ = TimeSlot.objects.get_or_create(
                        start=self._convert_date_to_datetime_startofday(
                            assignment["starts_at"]
                        ),
                        end=self._convert_date_to_datetime_endofday(
                            assignment["ends_at"]
                        ),
                        slot_type=TimeSlotType.get_builtin_object(
                            DefaultTimeSlotTypes.LEAVE
                        ),
                        user=db_user,
                    )
                    _, _ = LeaveRequest.objects.get_or_create(
                        timeslot=db_timeslot,
                        user=db_user,
                        defaults={
                            "start_date":self._convert_date_to_datetime_startofday(
                                assignment["starts_at"]
                            ),
                            "end_date":self._convert_date_to_datetime_endofday(
                                assignment["ends_at"]
                            ),
                            "requested_on": self._convert_date_to_datetime_endofday(
                                assignment["created_at"].split("T")[0]
                            ),
                            "type_of_leave": leave_mappings[
                                assignment["assignable_id"]
                            ]["mapping"],
                            "notes": "Imported from RM",
                            "authorised": True,
                            "authorised_on": self._convert_date_to_datetime_endofday(
                                assignment["created_at"].split("T")[0]
                            ),
                        },
                    )

                    pass
                else:
                    # Unknown assignable_id!
                    log.warning(
                        "Unknown Unassignable ID: '{}'".format(
                            assignment["assignable_id"]
                        )
                    )

            db_user.save()

        return (log_stream.getvalue() + ".")[:-1]

    @property
    def importer_name(self):
        return "SmartSheet Exports"

    @property
    def importer_help(self):
        return "Export various sheets into a ZIP file."
