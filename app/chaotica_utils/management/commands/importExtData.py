from django.core.management.base import BaseCommand, CommandError
from chaotica_utils.models import *
from jobtracker.models import *
from chaotica_utils.enums import *
from jobtracker.enums import *
from django.conf import settings
import json
from pprint import pprint
from faker import Faker
import hashlib
import faker_microservice


class Command(BaseCommand):
    help = "Given a path; imports a load of JSON files to"

    def add_arguments(self, parser):
        parser.add_argument("directory", type=str)
        parser.add_argument("mode", type=str)

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.NOTICE('Loading files from "%s"' % options['directory'])
        )

        if options['mode'] == "users":
            # Lets load up users...
            with open(options['directory']+"users.json") as user_file:
                jUsers = json.load(user_file)

            for jUser in jUsers['data']:
                # load custom data
                with open(options['directory']+"users/"+str(jUser['id'])+"/custom_fields.json") as user_file2:
                    jUser_customFIelds = json.load(user_file2)

                self.stdout.write(
                    self.style.NOTICE('Processing user: "'+jUser['first_name']+' '+jUser['last_name']+'"')
                )
                if not User.objects.filter(external_id=str(jUser['id'])).exists():
                    # create faker profile
                    fake = Faker()
                    prof = fake.simple_profile()
                    name = prof['name'].split(' ')

                    dbUsr, dbUsrCreated = User.objects.get_or_create(
                        external_id=str(jUser['id']), first_name=name[0], last_name=name[1], 
                        email=prof['mail'], username=prof['mail'])
                    
                    self.stdout.write(
                        self.style.NOTICE('Created user: "' +dbUsr.first_name+" "+dbUsr.last_name+'"')
                    )
                else:
                    dbUsr = User.objects.get(external_id=str(jUser['id']))

                # set their role
                orgRole = UnitRoles.CONSULTANT

                if jUser['role'] == "Consultant":
                    grp = Group.objects.get(name=settings.GLOBAL_GROUP_PREFIX+"User")
                    dbUsr.groups.add(grp)
                elif jUser['role'] == "Account Manager":
                    grp = Group.objects.get(name=settings.GLOBAL_GROUP_PREFIX+"Sales Member")
                    dbUsr.groups.add(grp)
                    orgRole = UnitRoles.SALES
                elif jUser['role'] == "Service Delivery Team":
                    grp = Group.objects.get(name=settings.GLOBAL_GROUP_PREFIX+"Service Delivery")
                    dbUsr.groups.add(grp)
                    orgRole = UnitRoles.SERVICE_DELIVERY
                
                for customField in jUser_customFIelds['data']:
                    if customField['custom_field_name']=="Market Unit":
                        # Add to the right org unit...
                        if not OrganisationalUnitMember.objects.filter(member=dbUsr, unit__name=customField['value']).exists():
                            # Add them!
                            if OrganisationalUnit.objects.filter(name=customField['value']).exists():
                                orgUnit = OrganisationalUnit.objects.get(name=customField['value'])
                                # See if there are any members...
                                if not orgUnit.get_managers():
                                    orgRole = UnitRoles.MANAGER
                                    orgUnit.lead = dbUsr
                                    orgUnit.save()
                                orgMembership = OrganisationalUnitMember.objects.create(
                                    member=dbUsr, unit=orgUnit, role=orgRole)
                    if customField['custom_field_name']=="Certifications":
                        cert = customField['value']
                        # get cert
                        if cert:
                            if Certification.objects.filter(name=cert).exists():
                                dbCert = Certification.objects.get(name=cert)
                                if not UserCertification.objects.filter(certification=dbCert, user=dbUsr).exists():
                                    UserCertification.objects.create(certification=dbCert, user=dbUsr)

                    elif customField['custom_field_name'].startswith('Skills -'):
                        # Sort the skill..
                        if customField['value']:
                            skill = customField['value'].split(' - ')
                            if len(skill) > 1:
                                rating = UserSkillRatings.NO_EXPERIENCE
                                if customField['custom_field_name'] == "Skills - Advanced":
                                    rating = UserSkillRatings.SPECIALIST
                                elif customField['custom_field_name'] == "Skills - Intermediate":
                                    rating = UserSkillRatings.CAN_DO_ALONE
                                elif customField['custom_field_name'] == "Skills - Aspire":
                                    rating = UserSkillRatings.CAN_DO_WITH_SUPPORT

                                if SkillCategory.objects.filter(name=skill[0]).exists():
                                    dbSkillCat = SkillCategory.objects.get(name=skill[0])
                                    if Skill.objects.filter(name=skill[1], category=dbSkillCat).exists():
                                        dbSkill = Skill.objects.get(name=skill[1], category=dbSkillCat)
                                        if not UserSkill.objects.filter(user=dbUsr, skill=dbSkill).exists():
                                            # Add the skill!
                                            UserSkill.objects.create(user=dbUsr, skill=dbSkill,
                                                                        rating=rating)


                dbUsr.save()
        elif options['mode'] == "projects":
            # Lets load up users...
            with open(options['directory']+"projects.json") as proj_file:
                jProjs = json.load(proj_file)

            for jProj in jProjs['data']:
                fake = Faker()
                fake.add_provider(faker_microservice.Provider)
                id = jProj['id']
                name = jProj['name']
                client = jProj['client']
                startD = jProj['starts_at']
                endD = jProj['ends_at']
                # load custom data
                if not client:
                    continue
                # get the client...
                clientID = hashlib.sha256(client.encode('UTF-8')).hexdigest()
                if not Client.objects.filter(external_id=clientID).exists():
                    # Create it...
                    # Get a random am
                    ams = User.objects.filter(
                        groups__name=settings.GLOBAL_GROUP_PREFIX+"Sales Member",
                        unit_memberships__isnull=False)
                    amDb = ams[random.randint(0, ams.count()-1)]
                    clientDb = Client.objects.create(
                        name=fake.company(),
                        external_id=clientID,
                    )
                    clientDb.account_managers.add(amDb)
                    self.stdout.write(
                        self.style.NOTICE('Created client '+clientDb.name)
                    )
                else:
                    clientDb = Client.objects.get(external_id=clientID)

                # Check there's some contacts created...
                totalContacts = Contact.objects.filter(company=clientDb).count()
                if totalContacts < 5:
                    # Lets create it...
                    for contactNum in range(5 - totalContacts):
                        self.stdout.write(
                            self.style.NOTICE('Created contact '+clientDb.name)
                        )
                        cont = fake.profile()
                        contact = Contact.objects.create(
                            jobtitle=cont['job'], first_name=fake.first_name(), last_name=fake.last_name(),
                            phone=fake.phone_number(), email=fake.email(), company=clientDb,
                        )
                
                # get a random PoC
                pocs = Contact.objects.filter(company=clientDb)
                pocDb = pocs[random.randint(0, pocs.count()-1)]
                
                amDb = clientDb.account_managers.all().first()
                unitDb = amDb.unit_memberships.all().first().unit

                # Lets get a project!
                listOfJobs = [
                    "Webapp", "Pentest", "Red Team", "Build Review", "ITHC"
                ]
                title=fake.microservice() + random.choice(listOfJobs)
                if not Job.objects.filter(external_id=id).exists():
                    jobDb = Job.objects.create(
                        title=title,
                        external_id=id, client=clientDb,
                        start_date_set=startD, delivery_date_set=endD,
                        unit=unitDb, account_manager=amDb,
                        created_by=amDb, primary_client_poc=pocDb,
                    )
                else:
                    jobDb = Job.objects.get(external_id=id)
                
                # Lets create a phase...
                if not jobDb.phases.all():
                    # Figure out service
                    serv = None
                    for x in Service.objects.all():
                        if x.name in jobDb.title:
                            serv = x
                    if not serv:
                        # get a random service then!
                        serv = Service.objects.all()[random.randint(0, Service.objects.all().count()-1)]
                    
                    name = jobDb.title + " - " + serv.name

                    self.stdout.write(
                        self.style.NOTICE('Creating phase: "'+name)
                    )
                    phase = Phase.objects.create(
                        job=jobDb, phase_number=1, title=name, service=serv
                    )
                else:
                    # get the first phase....
                    phase = jobDb.phases.all().first()
                
                with open(options['directory']+"projects/"+str(jProj['id'])+"/custom_fields.json") as proj_file2:
                    jProj_customFIelds = json.load(proj_file2)
                with open(options['directory']+"projects/"+str(jProj['id'])+"/assignments.json") as proj_file3:
                    jProj_assignments = json.load(proj_file3)
                
                # Lets add the associations!
                for assignment in jProj_assignments['data']:
                    ass = jProj_assignments['data'][assignment][0]
                    if ass['user_id']:
                        if User.objects.filter(external_id=ass['user_id']).exists():
                            usr = User.objects.get(external_id=ass['user_id'])

                            if not TimeSlot.objects.filter(start=ass['starts_at'], end=ass['ends_at'],
                                                        user=usr, phase=phase).exists():
                                # add a slot
                                slot = TimeSlot.objects.create(start=ass['starts_at'], end=ass['ends_at'],
                                                               deliveryRole=TimeSlotDeliveryRole.DELIVERY,
                                                               slotType=TimeSlotType.DELIVERY,
                                                                user=usr, phase=phase)


                self.stdout.write(
                    self.style.NOTICE('Processing project: "'+client+': '+name+'" ('+startD+' - '+endD+')')
                )

                # if not User.objects.filter(external_id=str(jProj['id'])).exists():
                #     # create faker profile
                #     fake = Faker()
                #     prof = fake.simple_profile()
                #     name = prof['name'].split(' ')


