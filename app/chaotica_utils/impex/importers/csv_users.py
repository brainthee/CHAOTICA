import csv
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


class CSVUserImporter(BaseImporter):
    allowed_fields = [
        "email",
        "first_name",
        "last_name",
        "notification_email",
        "job_title",
        "location",
        "phone_number",
        "manager",
        "acting_manager",
        "contracted_leave",
        "carry_over_leave",
        "contracted_leave_renewal",
        "is_active",
        "is_staff",
        "is_superuser",
    ]

    def import_data(self, request, data):
        CREATE_NEW_USERS = False

        log_stream = StringIO()
        logformatter = NoColorFormatter()
        stream_handler = logging.StreamHandler(log_stream)
        stream_handler.setFormatter(logformatter)

        log = logging.getLogger(__name__)
        log.setLevel(logging.INFO)
        log.addHandler(stream_handler)

        log.info("Starting CSV User import")

        if not data:
            log.error("Data is null to CSVUserImporter")
            raise ValueError("Data is null to CSVUserImporter")

        for user_file in data:
            log.info("Processing " + str(user_file))
            decoded_file = user_file.read().decode("utf-8").splitlines()
            reader = csv.DictReader(decoded_file)
            for row in reader:
                if "email" not in row:
                    log.error("CSV doesn't contain an email coloumn. Aborting import")
                    break
                # First thing, see if the user exists...
                auth_email = row["email"].lower().strip()

                if not auth_email:
                    continue  # skip this duff record
                db_user_created = False
                if CREATE_NEW_USERS:
                    db_user, db_user_created = User.objects.get_or_create(
                        email__iexact=auth_email,
                        defaults={
                            "email": auth_email,
                        },
                    )
                else:
                    if User.objects.filter(email__iexact=auth_email).exists():
                        db_user = User.objects.get(email__iexact=auth_email)
                    else:
                        log.warn(
                            "User {} doesn't exist in CHAOTICA and CREATE_NEW_USERS is false. Skipping".format(
                                auth_email
                            )
                        )
                        continue

                if db_user_created:
                    log.info("Created user {}".format(auth_email))

                for header in row:
                    if header in CSVUserImporter.allowed_fields:
                        if header == "manager":
                            # translate manager email to
                            person = row[header].lower().strip()
                            db_target_person, db_target_person_created = (
                                User.objects.get_or_create(
                                    email__iexact=person,
                                    defaults={
                                        "email": person,
                                    },
                                )
                            )
                            if db_target_person_created:
                                log.info("Created manager {}".format(person))
                            db_user.manager = db_target_person
                        elif header == "acting_manager":
                            # translate manager email to
                            person = row[header].lower().strip()
                            db_target_person, db_target_person_created = (
                                User.objects.get_or_create(
                                    email__iexact=person,
                                    defaults={
                                        "email": person,
                                    },
                                )
                            )
                            if db_target_person_created:
                                log.info("Created acting manager {}".format(person))
                            db_user.acting_manager = db_target_person
                        else:
                            setattr(db_user, header, row[header])

                db_user.save()
                log.info("Updated {}".format(auth_email))

        return (log_stream.getvalue() + ".")[:-1]
