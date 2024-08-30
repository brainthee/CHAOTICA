from chaotica_utils.impex.baseImporter import BaseImporter
import logging
import json
from django.utils import timezone
from datetime import time
from io import StringIO
from pprint import pprint
from chaotica_utils.models import User, get_sentinel_user
from chaotica_utils.utils import NoColorFormatter
from jobtracker.models import (
    OrganisationalUnit,
    OrganisationalUnitMember,
    Project,
    Job,
    Client,
    Phase,
    Service,
)
from chaotica_utils.views import log_system_activity


class ResourceManagerProjectImporter(BaseImporter):

    def _convert_date_to_datetime(self, dte):
        return timezone.datetime.strptime(dte, "%m/%d/%y")

    def _convert_date_to_datetime_startofday(self, dte):
        return timezone.datetime.combine(self._convert_date_to_datetime(dte), time.min)

    def _convert_date_to_datetime_endofday(self, dte):
        return timezone.datetime.combine(self._convert_date_to_datetime(dte), time.max)

    def import_data(self, request, data):
        log_stream = StringIO()
        logformatter = NoColorFormatter()
        stream_handler = logging.StreamHandler(log_stream)
        stream_handler.setFormatter(logformatter)

        log = logging.getLogger(__name__)
        log.setLevel(logging.INFO)
        log.addHandler(stream_handler)

        log.info("Starting import")

        if not data:
            log.error("Data is null to ResourceManagerProjectImporter")
            raise ValueError("Data is null to ResourceManagerProjectImporter")

        for project_file in data:
            log.info("Processing " + str(project_file))
            decoded_file = project_file.read().decode("utf-8")
            project_data = json.loads(decoded_file)

            for project in project_data["data"]:
                # So there are a few types:
                # Import client if it's defined...
                if (
                    project["project_state"] == "Internal"
                    or (
                        project["project_state"] == "Tentative"
                        and not project["mapped_sheet_id"]
                    )
                    or (
                        project["project_state"] == "Confirmed"
                        and not project["mapped_sheet_id"]
                        and not project["client"]
                        and not project["owner_name"]
                    )
                ):
                    # Process internal projects differently...
                    # Lets setup a project!
                    db_project, db_project_created = Project.objects.get_or_create(
                        title=project["name"].strip(),
                        external_id=project["id"],
                        created_by=request.user,
                    )
                    db_project.data = project
                    db_project.save()
                    if db_project_created:
                        log.info('Created Project: "' + db_project.title + '"')
                        log_system_activity(
                            db_project,
                            "Imported Project via RMProjectJson import from project: {}".format(
                                project["name"].strip()
                            ),
                        )
                else:
                    # For the moment, also skip if only no client
                    if not project["client"]:
                        log.warning(
                            "No client defined - setting default " + project["name"].strip()
                        )
                        db_client, _ = Client.objects.get_or_create(
                            name="Unknown Client"
                        )
                    else:
                        db_client, db_client_created = Client.objects.get_or_create(
                            name__iexact=project["client"].strip(),
                            defaults={"name": project["client"].strip()},
                        )
                        if db_client_created:
                            log.info('Created Client: "' + db_client.name + '"')
                            log_system_activity(
                                db_client,
                                "Imported Client via RMProjectJson import from project: {}".format(
                                    project["name"].strip()
                                ),
                            )

                    is_rt = False

                    if not project["owner_name"]:
                        log.warning(
                            "No owner defined - setting default " + project["name"].strip()
                        )
                        primary_am = get_sentinel_user()
                    else:
                        # get Owner
                        if not User.objects.filter(
                            external_id=project["owner_id"]
                        ).exists():
                            log.warning(
                                "Can't find owner:" + str(project["owner_name"].strip())
                            )
                            continue

                        primary_am = User.objects.get(external_id=project["owner_id"])
                        if project["owner_name"].strip() in [
                            "Rob Downie",
                            "Jason Cook",
                            "Owen Wright",
                        ]:
                            is_rt = True

                    if primary_am.unit_memberships.all().count():
                        db_unit = primary_am.unit_memberships.first().unit
                    else:
                        db_unit, _ = OrganisationalUnit.objects.get_or_create(
                            name="Unknown Unit"
                        )
                        
                    title = project["name"].strip()

                    if project["mapped_sheet_id"]:
                        # If it's got a sheet... clean it up as it's probably not a weird block
                        while title.startswith(db_client.name + " - "):
                            title = title.removeprefix(db_client.name + " - ")
                        while title.startswith(db_client.name):
                            title = title.removeprefix(db_client.name)
                        title = title.removesuffix(" - AARO Pentest")
                        title = title.strip()
                        title = title.strip("-")

                    # create the basic job...
                    db_job, db_job_created = Job.objects.get_or_create(
                        title=title.strip(),
                        is_imported=True,
                        defaults={
                            "client": db_client,
                            "unit": db_unit,
                            "account_manager": primary_am,
                            "created_by": primary_am,
                            "external_id": project["mapped_sheet_id"] if project["mapped_sheet_id"] else project["id"],
                        }
                    )
                    db_job.data = project
                    db_job.save()
                    if db_job_created:
                        log.info('Created Job: "' + str(db_job) + '"')
                        log_system_activity(
                            db_job,
                            "Job imported via RMProjectJson from project: {}".format(
                                project["name"].strip()
                            ),
                        )
                    if project["mapped_sheet_id"]:
                        db_job.external_id = project["mapped_sheet_id"]
                        log_system_activity(
                            db_job,
                            "External ID: {}".format(project["mapped_sheet_id"]),
                        )
                        db_job.save()
                    else:
                        # No mapped sheet. See if it's a RT...
                        if is_rt:
                            # It is. Lets make a single phase just to populate...
                            db_service = Service.objects.get(name="Red Team")
                            if "Purple" in title:
                                db_service = Service.objects.get(name="Purple Team")

                            db_phase, db_phase_created = Phase.objects.get_or_create(
                                job=db_job,
                                title=title,
                                is_imported=True,
                            )
                            if db_phase.service != db_service:
                                db_phase.service = db_service
                                db_phase.save()

                            if db_phase_created:
                                log.info('Created Phase: "' + project["name"] + '"')
                                log_system_activity(
                                    db_phase,
                                    "Imported Phase via RMProjectJson import from project: {}".format(
                                        project["name"]
                                    ),
                                )

        return (log_stream.getvalue() + ".")[:-1]

    @property
    def importer_name(self):
        return "SmartSheet Exports"

    @property
    def importer_help(self):
        return "Export various sheets into a ZIP file."
