from chaotica_utils.impex.baseImporter import BaseImporter
from structlog import wrap_logger
import logging, csv, re, json
from django.utils import timezone
from django.db.models import Q
from datetime import time
from io import StringIO
from pprint import pprint
from chaotica_utils.models import User
from django.utils.timezone import make_aware
from chaotica_utils.views import log_system_activity
from chaotica_utils.utils import NoColorFormatter
from django.conf import settings
from jobtracker.enums import (
    TimeSlotDeliveryRole,
    DefaultTimeSlotTypes,
    PhaseStatuses,
    JobStatuses,
)
from jobtracker.models import (
    TimeSlot,
    TimeSlotType,
    Service,
    Project,
    Job,
    Phase,
    OrganisationalUnit,
    Client,
)


class SmartSheetCSVImporter(BaseImporter):

    def _convert_name_to_db_user(self, log, file, user):
        if not user:
            return None
        db_user = None
        email = None
        name = None
        if "@" in user:
            # it's an email...
            email = user.lower().replace("accenture.com", "cyberdefense.global")
            email = email.replace("contextis.com", "cyberdefense.global")

            email_parts = email.split("@")
            name = email_parts[0].split(".")
        else:
            # It's a name...
            name = user.split(" ")
            email = "{}.{}@{}".format(
                name[0].lower(), name[-1].lower(), "cyberdefense.global"
            )
        existingUser = User.objects.filter(
            Q(first_name=name[0].title(), last_name=name[-1].title()) |
            Q(email=email)
        )
        if existingUser.exists():
            db_user = existingUser.first()
        else:
            db_user, db_user_created = User.objects.get_or_create(
                email__iexact=email,
                defaults={
                    "email": email,
                    "first_name": name[0].title(),
                    "last_name": name[-1].title(),
                },
            )
            if db_user_created:
                log.info("Created user {} from raw: {}".format(str(db_user), user))
                log_system_activity(
                    db_user,
                    "Imported user via SmartSheetCSV import from file: {}".format(file),
                )
        return db_user

    def _convert_date_to_datetime(self, dte):
        return timezone.datetime.strptime(dte, "%m/%d/%y")

    def _convert_date_to_datetime_startofday(self, dte):
        return make_aware(
            timezone.datetime.combine(self._convert_date_to_datetime(dte), time.min)
        )

    def _convert_date_to_datetime_endofday(self, dte):
        return make_aware(
            timezone.datetime.combine(self._convert_date_to_datetime(dte), time.max)
        )

    def import_data(self, request, data):
        log_stream = StringIO()
        logformatter = NoColorFormatter()
        stream_handler = logging.StreamHandler(log_stream)
        stream_handler.setFormatter(logformatter)

        log = logging.getLogger(__name__)
        log.setLevel(logging.INFO)
        log.addHandler(stream_handler)

        bad_values = [
            "<<CLIENT>>",
            "#REF",
            "",
            "<<Project Name>>",
            "<<EXTERNAL LINKS>>",
            "<<Project Lead>>",
            "<<GTM>>",
            "<<Opportunity ID>>",
            "#PERMISSION ERROR",
            "#NO MATCH",
            "Report Author",
            "<<Report Author>>",
            "Technical Reviewer",
            "Additional Testers",
            "Project Lead",
            "Presentation Reviewer",
            "GTM",
        ]

        ignored_rows = [
            "",
            "Navigation",
            "Resources",
            "Resources Test 1",
            "Resources Test 2",
            "Resources Test 3",
            "Resources Test 4",
            "Resources Test 5",
            "AARO Pentesting",
        ]

        log.info("Starting import")

        if not data:
            log.error("Data is null to SmartSheetCSVImporter")
            raise ValueError("Data is null to SmartSheetCSVImporter")
        
        files_total = len(data)
        files_imported = 0
        skipped_files = []

        for project_file in data:
            log.info("Processing JOB " + str(project_file))
            decoded_file = project_file.read().decode("utf-8").splitlines()
            file_id = str(project_file).removesuffix(".csv")
            reader = csv.DictReader(decoded_file)
            projectData = None
            for row in reader:
                # Ok, the format for export is ugly... we're going to process mainly by the `phase name` col
                if "Phase Name" not in row:
                    log.warning("CSV doesn't contain a Phase Name field")
                    break

                # Lets see if we need to populate the basics... should only need to once
                if projectData == None:
                    clientName = row["Client"].strip()
                    if not clientName:
                        clientName = "Default Client"

                    projectData = {
                        "name": row["Project Name"].strip(),
                        "sheet_id": file_id,
                        "filename": str(project_file),
                        "client": clientName,
                        "gtm": row["GTM"].strip(),
                        "lead": row["Project Lead"].strip(),
                        "author": row["Report Author"].strip(),
                        "op_id": row["Opportunity ID"].strip(),
                        "onsite_remote": row["Onsite/Remote"].strip(),
                        "phases": {},
                    }

                if row["Phase Name"] in ignored_rows:
                    continue

                if row["Phase Name"] == "Summary":
                    # It's a summary row, lets populate some bits...
                    if row["Task Name"] == "WBS Code":
                        projectData["wbs"] = row["Status"].strip()
                    elif row["Task Name"] == "External Links":
                        projectData["external_links"] = row["Status"].strip()
                    elif row["Task Name"] == "Specific Requirements":
                        projectData["specific_reqs"] = row["Status"].strip()
                    elif row["Task Name"] == "Requested Test Date":
                        projectData["req_test_date"] = row["Status"].strip()
                    elif row["Task Name"] == "Days Testing":
                        projectData["days_testing"] = row["Status"].strip()
                    elif row["Task Name"] == "Days Reporting":
                        projectData["days_reporting"] = row["Status"].strip()
                    elif row["Task Name"] == "Maximum Career Level":
                        projectData["max_c_level"] = row["Status"].strip()
                    elif row["Task Name"] == "Booking Confirmation":
                        projectData["confirmed"] = row["Status"].strip()
                    elif row["Task Name"] == "Multiple Locations?":
                        projectData["mulitple_locs"] = row["Status"].strip()
                    elif row["Task Name"] == "Address":
                        projectData["address"] = row["Status"].strip()
                    elif row["Task Name"] == "Service Line":
                        projectData["service_lines"] = row["Status"].strip()
                    elif row["Task Name"] == "CHECK Reference":
                        projectData["check_ref"] = row["Status"].strip()

                elif row["Phase Name"] not in projectData["phases"]:
                    # In theory... any other task name should be a phase....
                    projectData["phases"][row["Phase Name"].strip()] = {
                        "state": {},
                    }

                if row["Phase Name"] in projectData["phases"]:
                    phaseState = None
                    # It's a phase row... lets deal with it!
                    if "Pre-Con Checks" in row["Task Name"]:
                        phaseState = "pre_con_checks"
                    elif "Undertake Test" in row["Task Name"]:
                        phaseState = "testing"
                    elif "Create Report" in row["Task Name"]:
                        phaseState = "reporting"
                    elif "Tech QA" in row["Task Name"]:
                        phaseState = "tqa"
                    elif "Pres QA" in row["Task Name"]:
                        phaseState = "pqa"
                    elif "Report Delivery" in row["Task Name"]:
                        phaseState = "delivery"

                    if phaseState:
                        if (
                            phaseState
                            not in projectData["phases"][row["Phase Name"].strip()]["state"]
                        ):
                            projectData["phases"][row["Phase Name"].strip()]["state"][
                                phaseState
                            ] = []

                        line_data = {
                            "status": row["Status"].strip(),
                            "start": row["Start"].strip(),
                            "end": row["Finish"].strip(),
                            "allocation": row["Allocation"].strip(),
                            "external_links": row["External Link"].strip(),
                        }
                        assigned = [
                            x.strip() for x in re.split(";|,", row["Assigned To"].strip())
                        ]
                        line_data["assigned"] = assigned
                        projectData["phases"][row["Phase Name"].strip()]["state"][
                            phaseState
                        ].append(line_data)

            if not projectData:
                log.warning("projectData is empty - something went wrong! - skipping " + str(project_file))
                skipped_files.append(str(project_file))
                continue
            if "external_links" not in projectData:
                log.warning("projectData is malformed - suspect file isn't pentest - skipping " + str(project_file))
                skipped_files.append(str(project_file))
                continue


            # Lets add the DB stuff!
            # Sync the client...
            log.info("Syncing Client...")
            if projectData["client"] in bad_values:
                log.warning("Bad client name - skipping " + projectData["filename"])
                skipped_files.append(projectData["filename"])
                continue

            db_client, db_client_created = Client.objects.get_or_create(
                name__iexact=projectData["client"],
                defaults={"name": projectData["client"]},
            )
            if db_client_created:
                log.info('Created Client: "' + db_client.name + '"')
                log_system_activity(
                    db_client,
                    "Imported Client via SmartSheetCSV import from file: {}".format(
                        projectData["filename"]
                    ),
                )

            job_lead = None
            job_author = None
            # Get the project lead according to job. Used incase other info isn't available...
            if projectData["lead"] not in bad_values:
                job_lead = self._convert_name_to_db_user(
                    log, projectData["filename"], projectData["lead"]
                )
            if projectData["author"] not in bad_values:
                job_author = self._convert_name_to_db_user(
                    log, projectData["filename"], projectData["author"]
                )

            # Needs an account manager assigned - lets go with the AM in this sheet to start with!
            ams = [x.strip() for x in re.split(";|,", projectData["gtm"])]
            primary_am = None
            for am in ams:
                if am in bad_values:
                    log.warning("Bad am name - {} " + am)
                    continue

                db_user_am = self._convert_name_to_db_user(
                    log, projectData["filename"], am
                )
                if not primary_am:
                    primary_am = db_user_am

                if db_user_am not in db_client.account_managers.all():
                    db_client.account_managers.add(db_user_am)
                    db_client.save()
            if not primary_am:
                log.warning("No valid AM - skipping " + projectData["filename"])
                skipped_files.append(projectData["filename"])
                continue

            # Get default unit...
            # TODO - FIX THIS DON'T DEFAULT DUH!
            # Lets get the first org unit of the PAM:
            if primary_am.unit_memberships.all().count():
                db_unit = primary_am.unit_memberships.first().unit
            else:
                db_unit = OrganisationalUnit.objects.get(name="UKI")

            list_of_service_names = Service.objects.all().values_list("name", flat=True)

            log.info("Syncing Job...")
            if projectData["name"] in bad_values:
                log.warning("Bad job name '{}' - skipping {}".format(projectData["name"], projectData["filename"]))
                skipped_files.append(projectData["filename"])
                continue
            # Ok, lets see if there's a project with this ID!
            if Project.objects.filter(external_id=projectData["sheet_id"]).exists():
                # Weird?
                log.warning("ID found in Projects?! '{}' - skipping {}".format(projectData["name"], projectData["filename"]))
                skipped_files.append(projectData["filename"])
                continue
            # Ok, lets see if there's a Job with this ID!
            elif Job.objects.filter(external_id=projectData["sheet_id"]).exists():
                db_job = Job.objects.get(external_id=projectData["sheet_id"])
            else:
                # We don't have a Job or Project with this ID!?
                db_job, db_job_created = Job.objects.get_or_create(
                    title=projectData["name"].strip(),
                    is_imported=True,
                    defaults={
                        "external_id":projectData["sheet_id"],
                        "account_manager":primary_am,
                        "created_by":primary_am,
                        "client":db_client,
                        "unit":db_unit,
                    }
                )
                if db_job_created:
                    log.info('Created Job: "' + str(db_job) + '"')
                    log_system_activity(
                        db_job,
                        "Job imported via SmartSheetCSV from file: {}".format(
                            projectData["filename"]
                        ),
                    )
                log.warning("ID not found in Projects or Jobs! '{}' {}".format(projectData["name"], projectData["filename"]))

            # Lets update some info...
            db_job.client = db_client
            db_job.unit = db_unit
            db_job.account_manager = primary_am
            db_job.created_by = primary_am
            db_job.overview = """
            <p><i>Nb: Imported from SmartSheets CSV file: '{}'</i></p>
            <p><b>External Links:</b> {}</p>
            <p><b>Specific Requirements:</b> {}</p>
            """.format(
                projectData["filename"],
                projectData["external_links"],
                projectData["specific_reqs"],
            )
            db_job.save()

            # Lets do phases...
            log.info("Syncing Phases...")
            for phaseName, phaseData in projectData["phases"].items():
                log.info("Processing phase {}".format(phaseName))
                # This is the default consultancy to fall to
                db_service = Service.objects.get(name="Bespoke Consultancy")

                # First, lets check this is a valid phase!
                # This isn't some dev interview - lets not be clever
                bad_phase_names = [
                    "Test 1",
                    "Test 2",
                    "Test 3",
                    "Test 4",
                    "Test 5",
                ]
                phase_stages = [
                    "delivery",
                    "pqa",
                    "reporting",
                    "testing",
                    "tqa",
                    "pre_con_checks",
                ]
                # Ok, so the test to see if we should ignore it is the following criteria must be met:
                # - Default phase name
                # - No dates
                # - Default assigned names
                # - All statuses 'Not Started'
                shouldIgnore = True
                if phaseName in bad_phase_names:
                    log.debug("Phase matches bad phase name")
                    for stage in phase_stages:
                        if stage not in phaseData["state"]:
                            # This stage isn't in.... we should prob skip?
                            break
                        if (
                            phaseData["state"][stage][0]["end"] == ""
                            and phaseData["state"][stage][0]["start"] == ""
                        ):
                            log.debug("Both dates empty for {}".format(stage))
                            # Ok, so far so good... check the names!
                            for assignedPerson in phaseData["state"][stage][0][
                                "assigned"
                            ]:
                                if assignedPerson not in bad_values:
                                    # Ok, see something different! This is weird?!
                                    log.debug(
                                        "Not skipping because non default names exist..."
                                    )
                                    shouldIgnore = False
                            # Also check status
                            if phaseData["state"][stage][0]["status"] != "Not Started":
                                shouldIgnore = False
                                log.debug(
                                    "Not skipping because status is {}".format(
                                        phaseData["state"][stage][0]["status"]
                                    )
                                )
                        else:
                            shouldIgnore = False
                            log.debug("Not skipping because dates are not empty")
                else:
                    log.debug("Not skipping because phase name is good")
                    shouldIgnore = False

                if shouldIgnore:
                    log.info("Skipping template phase: {}".format(phaseName))
                    continue

                # Lets see if we can do a better guess at the service...
                for svc in list_of_service_names:
                    if svc in phaseName:
                        db_service = Service.objects.get(name=svc)

                db_phase, db_phase_created = Phase.objects.get_or_create(
                    job=db_job, title=phaseName, is_imported=True,
                )
                if db_phase.service != db_service:
                    db_phase.service = db_service

                # Lets update some info...
                db_phase.description = """
                <p><i>Nb: Imported from SmartSheets CSV file: '{}'</i></p>
                """.format(
                    projectData["filename"]
                )

                db_phase.location = projectData["address"]
                db_phase.save()

                if db_phase_created:
                    log.info('Created Phase: "' + str(phaseName) + '"')
                    log_system_activity(
                        db_phase,
                        "Imported Phase via SmartSheetCSV import from file: {}".format(
                            projectData["filename"]
                        ),
                    )

                # Lets update precon info
                if "pre_con_checks" in phaseData["state"]:
                    phase_scope = phaseData["state"]["pre_con_checks"][0][
                        "external_links"
                    ]
                    db_phase.description += """
                    <p><b>External Links:</b> {}</i></p>
                    """.format(
                        phase_scope
                    )
                    db_phase.save()

                # Lets update reporting info
                if "reporting" in phaseData["state"]:
                    # We check for author here.
                    if phaseData["state"]["reporting"][0]["assigned"][0] not in bad_values:
                        db_author = self._convert_name_to_db_user(
                            log,
                            projectData["filename"],
                            phaseData["state"]["reporting"][0]["assigned"][0],
                        )  # Only care about first one
                        db_phase.report_author = db_author

                    # Loop through each "line"
                    for state_line in phaseData["state"]["reporting"]:
                        if state_line["external_links"]:
                            db_phase.linkDeliverable = state_line["external_links"]
                        # Lets set the schedule!
                        if state_line["allocation"] not in ["100%", "0%"]:
                            log.error(
                                "FOUND A {} ALLOCATION NOT 100%: {}".format(
                                    "reporting", state_line["allocation"]
                                )
                            )
                        else:
                            # It's 100% - we have confidence to book it!
                            for assigned in state_line["assigned"]:
                                if assigned in bad_values:
                                    continue
                                db_assigned = self._convert_name_to_db_user(
                                    log, projectData["filename"], assigned
                                )
                                if (
                                    db_assigned
                                    and state_line["start"]
                                    and state_line["end"]
                                ):
                                    # If this is the first line AND we have time, lets assume we're lead!
                                    if state_line == phaseData["state"]["reporting"][0]:
                                        db_phase.report_author = db_assigned

                                    _, _ = TimeSlot.objects.get_or_create(
                                        start=self._convert_date_to_datetime_startofday(
                                            state_line["start"]
                                        ),
                                        end=self._convert_date_to_datetime_endofday(
                                            state_line["end"]
                                        ),
                                        deliveryRole=TimeSlotDeliveryRole.REPORTING,
                                        slot_type=TimeSlotType.get_builtin_object(
                                            DefaultTimeSlotTypes.DELIVERY
                                        ),
                                        user=db_assigned,
                                        phase=db_phase,
                                    )

                # Lets deal with TQA bits
                if "tqa" in phaseData["state"]:
                    # Loop through each "line"
                    for state_line in phaseData["state"]["tqa"]:
                        # Lets set the TQA date if it's earlier than what we have!
                        if state_line["start"]:
                            dt_start = self._convert_date_to_datetime(
                                state_line["start"]
                            ).date()
                            if (
                                not db_phase.due_to_techqa_set
                                or dt_start < db_phase.due_to_techqa_set
                            ):
                                db_phase.due_to_techqa_set = dt_start
                                # Update the person too!
                                if state_line["assigned"][0] not in bad_values:
                                    db_techqa = self._convert_name_to_db_user(
                                        log,
                                        projectData["filename"],
                                        state_line["assigned"][0],
                                    )  # Only care about first one
                                    db_phase.techqa_by = db_techqa
                        # Don't create schedules for TQA'ers

                        # for assigned in state_line["assigned"]:
                        #     if assigned in bad_values:
                        #         continue
                        #     db_assigned = self._convert_name_to_db_user(
                        #         log, projectData["filename"], assigned
                        #     )
                        #     if (
                        #         db_assigned
                        #         and state_line["start"]
                        #         and state_line["end"]
                        #     ):
                        #         _, _ = TimeSlot.objects.get_or_create(
                        #             start=self._convert_date_to_datetime_startofday(
                        #                 state_line["start"]
                        #             ),
                        #             end=self._convert_date_to_datetime_endofday(
                        #                 state_line["end"]
                        #             ),
                        #             deliveryRole=TimeSlotDeliveryRole.QA,
                        #             slot_type=TimeSlotType.get_builtin_object(
                        #                 DefaultTimeSlotTypes.DELIVERY
                        #             ),
                        #             user=db_assigned,
                        #             phase=db_phase,
                        #         )

                if "pqa" in phaseData["state"]:
                    # Loop through each "line"
                    for state_line in phaseData["state"]["pqa"]:
                        # Lets set the TQA date if it's earlier than what we have!
                        if state_line["start"]:
                            dt_start = self._convert_date_to_datetime(
                                state_line["start"]
                            ).date()
                            if (
                                not db_phase.due_to_presqa_set
                                or dt_start < db_phase.due_to_presqa_set
                            ):
                                db_phase.due_to_presqa_set = dt_start
                                # Update the person too!
                                if state_line["assigned"][0] not in bad_values:
                                    db_presqa = self._convert_name_to_db_user(
                                        log,
                                        projectData["filename"],
                                        state_line["assigned"][0],
                                    )  # Only care about first one
                                    db_phase.presqa_by = db_presqa
                        # Don't create schedules for PQA'ers

                        # for assigned in state_line["assigned"]:
                        #     if assigned in bad_values:
                        #         continue
                        #     db_assigned = self._convert_name_to_db_user(
                        #         log, projectData["filename"], assigned
                        #     )
                        #     if (
                        #         db_assigned
                        #         and state_line["start"]
                        #         and state_line["end"]
                        #     ):
                        #         _, _ = TimeSlot.objects.get_or_create(
                        #             start=self._convert_date_to_datetime_startofday(
                        #                 state_line["start"]
                        #             ),
                        #             end=self._convert_date_to_datetime_endofday(
                        #                 state_line["end"]
                        #             ),
                        #             deliveryRole=TimeSlotDeliveryRole.QA,
                        #             slot_type=TimeSlotType.get_builtin_object(
                        #                 DefaultTimeSlotTypes.DELIVERY
                        #             ),
                        #             user=db_assigned,
                        #             phase=db_phase,
                        #         )

                if "delivery" in phaseData["state"]:
                    # Loop through each "line"
                    for state_line in phaseData["state"]["delivery"]:
                        # Lets set the TQA date if it's earlier than what we have!
                        if state_line["start"]:
                            dt_start = self._convert_date_to_datetime(
                                state_line["start"]
                            ).date()
                            if (
                                not db_phase.desired_delivery_date
                                or dt_start < db_phase.desired_delivery_date
                            ):
                                db_phase.desired_delivery_date = dt_start

                if "testing" in phaseData["state"]:
                    for state_line in phaseData["state"]["testing"]:
                        # Lets set the TQA date if it's earlier than what we have!
                        if state_line["start"]:
                            dt_start = self._convert_date_to_datetime(
                                state_line["start"]
                            ).date()
                            if (
                                not db_phase.desired_start_date
                                or dt_start < db_phase.desired_start_date
                            ):
                                db_phase.desired_start_date = dt_start

                        # Lets set the schedule!
                        if state_line["allocation"] != "100%":
                            log.error(
                                "FOUND A {} ALLOCATION NOT 100%: {}".format(
                                    "testing", state_line["allocation"]
                                )
                            )
                        else:
                            # It's 100% - we have confidence to book it!
                            for assigned in state_line["assigned"]:
                                if assigned in bad_values:
                                    continue
                                db_assigned = self._convert_name_to_db_user(
                                    log, projectData["filename"], assigned
                                )
                                if (
                                    db_assigned
                                    and state_line["start"]
                                    and state_line["end"]
                                ):
                                    # If this is the first line AND we have time, lets assume we're lead!
                                    if state_line == phaseData["state"]["testing"][0]:
                                        db_phase.project_lead = db_assigned

                                    _, _ = TimeSlot.objects.get_or_create(
                                        start=self._convert_date_to_datetime_startofday(
                                            state_line["start"]
                                        ),
                                        end=self._convert_date_to_datetime_endofday(
                                            state_line["end"]
                                        ),
                                        deliveryRole=TimeSlotDeliveryRole.DELIVERY,
                                        slot_type=TimeSlotType.get_builtin_object(
                                            DefaultTimeSlotTypes.DELIVERY
                                        ),
                                        user=db_assigned,
                                        phase=db_phase,
                                    )
                
                # Ok, lets see if author or lead isn't set and we can set it:
                if ( job_lead and db_phase.project_lead is None):
                    db_phase.project_lead = job_lead
                    
                if ( job_author and db_phase.report_author is None):
                    db_phase.report_author = job_author                    
                
                # Lets try and sort the phase status...
                # Lets check if delivered first!
                if (
                    "delivery" in phaseData["state"]
                    and phaseData["state"]["delivery"][0]["status"] == "Complete"
                ):
                    # Ok, phase is delivered
                    log.info("Phase marked as DELIVERED")
                    db_phase.status = PhaseStatuses.DELIVERED

                elif (
                    "pqa" in phaseData["state"]
                    and phaseData["state"]["pqa"][0]["status"] == "Complete"
                ):
                    # Ok, phase is complete
                    log.info("Phase marked as COMPLETED")
                    db_phase.status = PhaseStatuses.COMPLETED
                elif (
                    "pqa" in phaseData["state"]
                    and phaseData["state"]["pqa"][0]["status"] == "In Progress"
                ):
                    # Ok, phase is pending QA
                    log.info("Phase marked as PENDING_PQA")
                    db_phase.status = PhaseStatuses.PENDING_PQA

                elif (
                    "tqa" in phaseData["state"]
                    and phaseData["state"]["tqa"][0]["status"] == "Complete"
                ):
                    # Ok, phase is complete
                    log.info("Phase marked as PENDING_PQA")
                    db_phase.status = PhaseStatuses.PENDING_PQA
                elif (
                    "tqa" in phaseData["state"]
                    and phaseData["state"]["tqa"][0]["status"] == "In Progress"
                ):
                    # Ok, phase is complete
                    log.info("Phase marked as PENDING_TQA")
                    db_phase.status = PhaseStatuses.PENDING_TQA

                elif (
                    "reporting" in phaseData["state"]
                    and phaseData["state"]["reporting"][0]["status"] == "Complete"
                ):
                    log.info("Phase marked as PENDING_TQA")
                    db_phase.status = PhaseStatuses.PENDING_TQA
                elif (
                    "reporting" in phaseData["state"]
                    and phaseData["state"]["reporting"][0]["status"] == "In Progress"
                ):
                    # Ok, phase is complete
                    log.info("Phase marked as Reporting/IN_PROGRESS")
                    db_phase.status = PhaseStatuses.IN_PROGRESS

                elif (
                    "testing" in phaseData["state"]
                    and phaseData["state"]["testing"][0]["status"] == "Complete"
                ):
                    log.info("Phase marked as IN_PROGRESS")
                    db_phase.status = PhaseStatuses.IN_PROGRESS
                elif (
                    "testing" in phaseData["state"]
                    and phaseData["state"]["testing"][0]["status"] == "In Progress"
                ):
                    # Ok, phase is complete
                    log.info("Phase marked as IN_PROGRESS")
                    db_phase.status = PhaseStatuses.IN_PROGRESS

                elif (
                    "pre_con_checks" in phaseData["state"]
                    and phaseData["state"]["pre_con_checks"][0]["status"] == "Complete"
                ):
                    log.info("Phase marked as READY_TO_BEGIN")
                    db_phase.status = PhaseStatuses.READY_TO_BEGIN
                elif (
                    "pre_con_checks" in phaseData["state"]
                    and phaseData["state"]["pre_con_checks"][0]["status"]
                    == "In Progress"
                ):
                    # Ok, phase is complete
                    log.info("Phase marked as PRE_CHECKS")
                    db_phase.status = PhaseStatuses.PRE_CHECKS
                else:
                    # Ok so lets see if there's dates for testing...
                    if (
                        "testing" in phaseData["state"]
                        and phaseData["state"]["testing"][0]["start"] != ""
                        and phaseData["state"]["testing"][0]["end"] != ""
                    ):
                        # We have dates... lets set to scheduled...
                        log.info("Phase marked as SCHEDULED")
                        db_phase.status = PhaseStatuses.SCHEDULED_CONFIRMED
                    else:
                        # Keep as Draft!
                        log.info("Phase marked as DRAFT")
                        db_phase.status = PhaseStatuses.DRAFT

                db_phase.save()

                # email = row['Email'] if row['Email'] else None
                # user_id = row['User ID'] if row['User ID'] else None
                # name = row['Team Member'] if row['Team Member'] else None

                # if not email or not user_id or not name:
                #     log.warning("Row contains an empty email, userid or name", row=row)
                #     continue

                # db_user, db_user_created = User.objects.get_or_create(email=email)
                # db_user.external_id=str(user_id),
                # db_user.first_name=name.split(' ')[0]
                # db_user.last_name=name.split(' ')[1]
                # db_user.save()
                # if db_user_created:
                #     log.info('Created user: "' +db_user.first_name+" "+db_user.last_name+'"')

            # Now lets make sure the Job status matches the phases...
            # db_job.status == JobStatuses.IN_PROGRESS
            # db_job.save()
            status_to_set = JobStatuses.COMPLETED
            if db_job.phases.all().count() > 0:
                is_completed = True
                for phase in db_job.phases.all():
                    if phase.status < PhaseStatuses.COMPLETED:
                        is_completed = False
                if is_completed:
                    status_to_set = JobStatuses.COMPLETED
                else:
                    for phase in db_job.phases.all():
                        # If completed and status to set is not lower...
                        if (
                            phase.status >= PhaseStatuses.COMPLETED
                            and not status_to_set < JobStatuses.COMPLETED
                        ):
                            status_to_set = JobStatuses.IN_PROGRESS
                        elif (  # Else if any of them are in progress or above, mark the job as in progress!
                            phase.status >= PhaseStatuses.IN_PROGRESS
                            and not status_to_set < JobStatuses.IN_PROGRESS
                        ):
                            status_to_set = JobStatuses.IN_PROGRESS

                        elif (  # Else mark it as pending start if any of the phases are ready to start
                            phase.status >= PhaseStatuses.PRE_CHECKS
                            and not status_to_set < JobStatuses.PENDING_START
                        ):
                            status_to_set = JobStatuses.PENDING_START

            else:
                # No phases, therefore waiting for scoping?
                status_to_set = JobStatuses.PENDING_SCOPE
            db_job.status = status_to_set
            db_job.save()
            files_imported = files_imported + 1

        log.info("{} files successfully imported of {} provided".format(
            str(files_imported), str(files_total)
        ))
        log.warning("Skipped summary:")
        for bad_filename in skipped_files:
            log.warning(" - {}".format(bad_filename))

        return (log_stream.getvalue() + ".")[:-1]

    @property
    def importer_name(self):
        return "SmartSheet Exports"

    @property
    def importer_help(self):
        return "Export various sheets into a ZIP file."
