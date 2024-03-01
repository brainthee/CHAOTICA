from chaotica_utils.impex.baseImporter import BaseImporter
from structlog import wrap_logger
import logging, csv, re
from django.utils import timezone
from datetime import time
from io import StringIO
from pprint import pprint
from chaotica_utils.models import User, Group, UserSkillRatings
from chaotica_utils.enums import UnitRoles
from jobtracker.enums import TimeSlotDeliveryRole, DefaultTimeSlotTypes
from jobtracker.models import TimeSlot, TimeSlotType, Service, Job, Phase, OrganisationalUnit, Client, Contact, Skill, SkillCategory, OrganisationalUnitMember, UserCertification, UserSkill, Certification

class SmartSheetCSVImporter(BaseImporter):

    def _convert_name_to_db_user(self, user):
        db_user = None
        if "@" in user:
            # it's an email...
            db_user, _ = User.objects.get_or_create(
                email__iexact=user,
                defaults = {
                    "email": user
                })
        else:
            # It's likely a name...
            user = user.split(' ')
            if len(user) == 2:
                # We can't add without an email so if we can't find a user, just add a note
                if User.objects.filter(first_name=user[0], last_name=user[1]).exists():
                    db_user = User.objects.filter(first_name=user[0], last_name=user[1])[0] # Yes yes, might be more than one 'John Doe' but yolo :D
        return db_user
    
    def _convert_date_to_datetime(self, dte):
        return timezone.datetime.strptime(dte, "%m/%d/%y")
    
    def _convert_date_to_datetime_startofday(self, dte):
        return timezone.datetime.combine(self._convert_date_to_datetime(dte), time.min)
    
    def _convert_date_to_datetime_endofday(self, dte):
        return timezone.datetime.combine(self._convert_date_to_datetime(dte), time.max)

    def import_data(self, data):
        log_stream = StringIO()    
        logging.basicConfig(stream=log_stream)
        logging.getLogger().setLevel(logging.INFO)
        log = wrap_logger(
            logging.getLogger(__name__),
        )

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

        log.info('Starting import')

        if not data:
            log.error('Data is null to SmartSheetCSVImporter')
            raise ValueError("Data is null to SmartSheetCSVImporter")
        
        for project_file in data:
            log.info('Processing '+str(project_file))
            decoded_file = project_file.read().decode('utf-8').splitlines()
            reader = csv.DictReader(decoded_file)
            projectData = None
            for row in reader:        
                # Ok, the format for export is ugly... we're going to process mainly by the `phase name` col
                if 'Phase Name' not in row:
                    log.warning("CSV doesn't contain an Phase Name field", row=row)
                    break

                # Lets see if we need to populate the basics... should only need to once
                if projectData == None:
                    if row['Client'].strip() is not None and row['Client'].strip() is not "":
                        clientName = row['Client'].strip()
                    else:
                        clientName = "Default Client"
                    projectData = {
                        "name": row['Project Name'],
                        "client": clientName,
                        "gtm": row['GTM'],
                        "lead": row['Project Lead'],
                        "op_id": row['Opportunity ID'],
                        "phases": {},
                    }
                
                if row['Phase Name'] in ignored_rows:
                    continue
                
                if row['Phase Name'] == "Summary":
                    # It's a summary row, lets populate some bits...
                    if row['Task Name'] == "WBS Code":
                        projectData['wbs'] = row['Status']
                    elif row['Task Name'] == "External Links":
                        projectData['external_links'] = row['Status']
                    elif row['Task Name'] == "Specific Requirements":
                        projectData['specific_reqs'] = row['Status']
                    elif row['Task Name'] == "Requested Test Date":
                        projectData['req_test_date'] = row['Status']
                    elif row['Task Name'] == "Days Testing":
                        projectData['days_testing'] = row['Status']
                    elif row['Task Name'] == "Days Reporting":
                        projectData['days_reporting'] = row['Status']
                    elif row['Task Name'] == "Maximum Career Level":
                        projectData['max_c_level'] = row['Status']
                    elif row['Task Name'] == "Booking Confirmation":
                        projectData['confirmed'] = row['Status']
                    elif row['Task Name'] == "Multiple Locations?":
                        projectData['mulitple_locs'] = row['Status']
                    elif row['Task Name'] == "Service Line":
                        projectData['service_lines'] = row['Status']
                    elif row['Task Name'] == "CHECK Reference":
                        projectData['check_ref'] = row['Status']

                elif row['Phase Name'] in projectData["phases"]:
                    phaseState = None
                    # It's a phase row... lets deal with it!
                    if row['Task Name'] == "Pre-Con Checks":
                        phaseState = "pre_con_checks"
                    elif row['Task Name'] == "Undertake Test":
                        phaseState = "testing"
                    elif row['Task Name'] == "Create Report":
                        phaseState = "reporting"
                    elif row['Task Name'] == "Tech QA":
                        phaseState = "tqa"
                    elif row['Task Name'] == "Pres QA":
                        phaseState = "pqa"
                    elif row['Task Name'] == "Report Delivery":
                        phaseState = "delivery"

                    if phaseState:
                        if phaseState not in projectData["phases"][row['Phase Name']]['state']:
                            projectData["phases"][row['Phase Name']]['state'][phaseState] = []

                        line_data = {
                            "status": row['Status'],
                            "start": row['Start'],
                            "end": row['Finish'],
                            "allocation": row['Allocation'],
                        }
                        assigned = [x.strip() for x in re.split(';|,', row['Assigned To'])]
                        line_data['assigned'] = assigned
                        projectData["phases"][row['Phase Name']]['state'][phaseState].append(line_data)

                else:
                    # In theory... any other task name should be a phase....
                    projectData["phases"][row['Phase Name']] = {
                        "state": {},
                    }

            pprint(projectData)
            if not projectData:
                log.warning('projectData is empty - something went wrong!')
                continue

            # Lets add the DB stuff!
            # Sync the client...
            log.info('Syncing Client...')
            db_client, db_client_created = Client.objects.get_or_create(
                name__iexact=projectData['client'],
                defaults = {
                    "name": projectData['client']
                })
            if db_client_created:
                log.info('Created Client: "' +db_client.name+'"')
            
            # Get the project lead...
            log.info('Syncing Project Lead...')

            db_lead = self._convert_name_to_db_user(projectData['lead']) # Only care about first one                    
            if db_lead:
                # Lets set them!
                log.info('Got lead: "' +str(db_lead)+'"')
            else:
                log.warning("Failed to find the lead in the DB: "+projectData['lead'])

            # Needs an account manager assigned - lets go with the AM in this sheet to start with!
            ams = [x.strip() for x in re.split(';|,', projectData['gtm'])]
            primary_am = None
            for am in ams:
                db_user_am, db_user_am_created = User.objects.get_or_create(
                    email__iexact=am,
                    defaults = {
                        "email": am
                    })
                if not primary_am:
                    primary_am = db_user_am
                if db_user_am_created:
                    log.info('Created user: "' +str(db_user_am)+'"')
                
                if db_user_am not in db_client.account_managers.all():
                    db_client.account_managers.add(db_user_am)
                    db_client.save()

            # Get default unit...
            db_unit = OrganisationalUnit.objects.get(pk=1)
            list_of_service_names = Service.objects.all().values_list('name', flat=True)
            
            log.info('Syncing Job...')        
            db_job, db_job_created = Job.objects.get_or_create(
                title=projectData['name'], client=db_client,
                unit=db_unit, account_manager=primary_am,
                created_by=primary_am,
            )
            if db_job_created:
                log.info('Created Job: "' +str(db_job)+'"')
            
            # Lets do phases...
            log.info('Syncing Phases...')     
            for phaseName, phaseData in projectData['phases'].items():
                db_service = Service.objects.get(name="Consultancy")

                # Lets see if we can do a better guess at the service...
                for svc in list_of_service_names:
                    if svc in phaseName:
                        db_service = Service.objects.get(name=svc)

                db_phase, db_phase_created = Phase.objects.get_or_create(
                    job=db_job, title=phaseName
                )
                if db_phase.service != db_service:
                    db_phase.service = db_service
                    
                # Lets set the lead
                if db_lead:
                    db_phase.project_lead = db_lead

                if db_phase_created:
                    log.info('Created Phase: "' +str(phaseName)+'"')

                # Lets update reporting info
                if "reporting" in phaseData['state']:
                    # We check for author here.
                    db_author = self._convert_name_to_db_user(phaseData['state']['reporting'][0]['assigned'][0]) # Only care about first one                    
                    if db_author:
                        # Lets set them!
                        db_phase.report_author = db_author

                    # Loop through each "line"
                    for state_line in phaseData['state']['reporting']:
                        # Lets set the schedule!
                        if state_line['allocation'] != "100%":
                            log.error("FOUND AN ALLOCATION NOT 100%!")
                        else:
                            # It's 100% - we have confidence to book it!
                            for assigned in state_line['assigned']:
                                db_assigned = self._convert_name_to_db_user(assigned)
                                if db_assigned and state_line['start'] and state_line['end']:
                                    _, _ = TimeSlot.objects.get_or_create(
                                        start=self._convert_date_to_datetime_startofday(state_line['start']), 
                                        end=self._convert_date_to_datetime_endofday(state_line['end']),
                                        deliveryRole=TimeSlotDeliveryRole.REPORTING,
                                        slot_type=TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.DELIVERY),
                                        user=db_assigned, phase=db_phase)
                    
                # Lets deal with TQA bits
                if "tqa" in phaseData['state']:
                    # Loop through each "line"
                    for state_line in phaseData['state']['tqa']:
                        # Lets set the TQA date if it's earlier than what we have!
                        if state_line['start']:
                            dt_start = self._convert_date_to_datetime(state_line['start']).date()
                            if not db_phase.due_to_techqa_set or dt_start < db_phase.due_to_techqa_set:
                                db_phase.due_to_techqa_set = dt_start
                                # Update the person too!
                                db_techqa = self._convert_name_to_db_user(state_line['assigned'][0]) # Only care about first one                  
                                if db_techqa:
                                    # Lets set them!
                                    db_phase.techqa_by = db_techqa

                        # Lets set the schedule!
                        if state_line['allocation'] != "100%":
                            log.error("FOUND AN ALLOCATION NOT 100%!")
                        else:
                            # It's 100% - we have confidence to book it!
                            for assigned in state_line['assigned']:
                                db_assigned = self._convert_name_to_db_user(assigned)
                                if db_assigned and state_line['start'] and state_line['end']:
                                    _, _ = TimeSlot.objects.get_or_create(
                                        start=self._convert_date_to_datetime_startofday(state_line['start']), 
                                        end=self._convert_date_to_datetime_endofday(state_line['end']),
                                        deliveryRole=TimeSlotDeliveryRole.QA,
                                        slot_type=TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.DELIVERY),
                                        user=db_assigned, phase=db_phase)
                    
                if "pqa" in phaseData['state']:
                    # Loop through each "line"
                    for state_line in phaseData['state']['pqa']:
                        # Lets set the TQA date if it's earlier than what we have!
                        if state_line['start']:
                            dt_start = self._convert_date_to_datetime(state_line['start']).date()
                            if not db_phase.due_to_presqa_set or dt_start < db_phase.due_to_presqa_set:
                                db_phase.due_to_presqa_set = dt_start
                                # Update the person too!
                                db_presqa = self._convert_name_to_db_user(state_line['assigned'][0]) # Only care about first one                  
                                if db_presqa:
                                    # Lets set them!
                                    db_phase.presqa_by = db_presqa

                        # Lets set the schedule!
                        if state_line['allocation'] != "100%":
                            log.error("FOUND AN ALLOCATION NOT 100%!")
                        else:
                            # It's 100% - we have confidence to book it!
                            for assigned in state_line['assigned']:
                                db_assigned = self._convert_name_to_db_user(assigned)
                                if db_assigned and state_line['start'] and state_line['end']:
                                    _, _ = TimeSlot.objects.get_or_create(
                                        start=self._convert_date_to_datetime_startofday(state_line['start']), 
                                        end=self._convert_date_to_datetime_endofday(state_line['end']),
                                        deliveryRole=TimeSlotDeliveryRole.QA,
                                        slot_type=TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.DELIVERY),
                                        user=db_assigned, phase=db_phase)

                    
                if "delivery" in phaseData['state']:
                    # Loop through each "line"
                    for state_line in phaseData['state']['delivery']:
                        # Lets set the TQA date if it's earlier than what we have!
                        if state_line['start']:
                            dt_start = self._convert_date_to_datetime(state_line['start']).date()
                            if not db_phase.desired_delivery_date or dt_start < db_phase.desired_delivery_date:
                                db_phase.desired_delivery_date = dt_start
                    
                if "testing" in phaseData['state']:
                    for state_line in phaseData['state']['testing']:
                        pprint(state_line)
                        # Lets set the TQA date if it's earlier than what we have!
                        if state_line['start']:
                            dt_start = self._convert_date_to_datetime(state_line['start']).date()
                            if not db_phase.desired_start_date or dt_start < db_phase.desired_start_date:
                                db_phase.desired_start_date = dt_start

                        # Lets set the schedule!
                        if state_line['allocation'] != "100%":
                            log.error("FOUND AN ALLOCATION NOT 100%!")
                        else:
                            # It's 100% - we have confidence to book it!
                            for assigned in state_line['assigned']:
                                db_assigned = self._convert_name_to_db_user(assigned)
                                if db_assigned and state_line['start'] and state_line['end']:
                                    _, _ = TimeSlot.objects.get_or_create(
                                        start=self._convert_date_to_datetime_startofday(state_line['start']), 
                                        end=self._convert_date_to_datetime_endofday(state_line['end']),
                                        deliveryRole=TimeSlotDeliveryRole.DELIVERY,
                                        slot_type=TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.DELIVERY),
                                        user=db_assigned, phase=db_phase)

                db_phase.save()
                # pprint(phaseData)

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



        return (log_stream.getvalue()+'.')[:-1]

    @property
    def importer_name(self):
        return "SmartSheet Exports"

    @property
    def importer_help(self):
        return "Export various sheets into a ZIP file."
