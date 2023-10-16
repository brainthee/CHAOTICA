from django.core.management.base import BaseCommand
from chaotica_utils.models import User, Group, UserSkillRatings
from jobtracker.models import TimeSlot, Service, Job, Phase, OrganisationalUnit, Client, Contact, Skill, SkillCategory, OrganisationalUnitMember, UserCertification, UserSkill, Certification
from chaotica_utils.enums import UnitRoles
from jobtracker.enums import TimeSlotDeliveryRole, TimeSlotType
from django.conf import settings
import json, random
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
                j_users = json.load(user_file)

            for j_user in j_users['data']:
                # load custom data
                with open(options['directory']+"users/"+str(j_user['id'])+"/custom_fields.json") as user_file2:
                    j_user_custom_fields = json.load(user_file2)

                self.stdout.write(
                    self.style.NOTICE('Processing user: "'+j_user['first_name']+' '+j_user['last_name']+'"')
                )
                if not User.objects.filter(external_id=str(j_user['id'])).exists():
                    # create faker profile
                    fake = Faker()
                    prof = fake.simple_profile()
                    name = prof['name'].split(' ')

                    db_user, _ = User.objects.get_or_create(
                        external_id=str(j_user['id']), first_name=name[0], last_name=name[1], 
                        email=prof['mail'], username=prof['mail'])
                    
                    self.stdout.write(
                        self.style.NOTICE('Created user: "' +db_user.first_name+" "+db_user.last_name+'"')
                    )
                else:
                    db_user = User.objects.get(external_id=str(j_user['id']))

                # set their role
                org_role = UnitRoles.CONSULTANT

                if j_user['role'] == "Consultant":
                    grp = Group.objects.get(name=settings.GLOBAL_GROUP_PREFIX+"User")
                    db_user.groups.add(grp)
                elif j_user['role'] == "Account Manager":
                    grp = Group.objects.get(name=settings.GLOBAL_GROUP_PREFIX+"Sales Member")
                    db_user.groups.add(grp)
                    org_role = UnitRoles.SALES
                elif j_user['role'] == "Service Delivery Team":
                    grp = Group.objects.get(name=settings.GLOBAL_GROUP_PREFIX+"Service Delivery")
                    db_user.groups.add(grp)
                    org_role = UnitRoles.SERVICE_DELIVERY
                
                for custom_field in j_user_custom_fields['data']:
                    if custom_field['custom_field_name']=="Market Unit":
                        # Add to the right org unit...
                        if not OrganisationalUnitMember.objects.filter(member=db_user, unit__name=custom_field['value']).exists():
                            # Add them!
                            if OrganisationalUnit.objects.filter(name=custom_field['value']).exists():
                                org_unit = OrganisationalUnit.objects.get(name=custom_field['value'])
                                # See if there are any members...
                                if not org_unit.get_managers():
                                    org_role = UnitRoles.MANAGER
                                    org_unit.lead = db_user
                                    org_unit.save()
                                OrganisationalUnitMember.objects.create(
                                    member=db_user, unit=org_unit, role=org_role)
                    if custom_field['custom_field_name']=="Certifications":
                        cert = custom_field['value']
                        # get cert
                        if cert:
                            if Certification.objects.filter(name=cert).exists():
                                db_cert = Certification.objects.get(name=cert)
                                if not UserCertification.objects.filter(certification=db_cert, user=db_user).exists():
                                    UserCertification.objects.create(certification=db_cert, user=db_user)

                    elif custom_field['custom_field_name'].startswith('Skills -'):
                        # Sort the skill..
                        if custom_field['value']:
                            skill = custom_field['value'].split(' - ')
                            if len(skill) > 1:
                                rating = UserSkillRatings.NO_EXPERIENCE
                                if custom_field['custom_field_name'] == "Skills - Advanced":
                                    rating = UserSkillRatings.SPECIALIST
                                elif custom_field['custom_field_name'] == "Skills - Intermediate":
                                    rating = UserSkillRatings.CAN_DO_ALONE
                                elif custom_field['custom_field_name'] == "Skills - Aspire":
                                    rating = UserSkillRatings.CAN_DO_WITH_SUPPORT

                                if SkillCategory.objects.filter(name=skill[0]).exists():
                                    db_skill_cat = SkillCategory.objects.get(name=skill[0])
                                    if Skill.objects.filter(name=skill[1], category=db_skill_cat).exists():
                                        db_skill = Skill.objects.get(name=skill[1], category=db_skill_cat)
                                        if not UserSkill.objects.filter(user=db_user, skill=db_skill).exists():
                                            # Add the skill!
                                            UserSkill.objects.create(user=db_user, skill=db_skill,
                                                                        rating=rating)


                db_user.save()
        elif options['mode'] == "projects":
            # Lets load up users...
            with open(options['directory']+"projects.json") as proj_file:
                j_projs = json.load(proj_file)

            for j_proj in j_projs['data']:
                fake = Faker()
                fake.add_provider(faker_microservice.Provider)
                j_proj_id = j_proj['id']
                name = j_proj['name']
                client = j_proj['client']
                start_date = j_proj['starts_at']
                end_date = j_proj['ends_at']
                # load custom data
                if not client:
                    continue
                # get the client...
                client_id = hashlib.sha256(client.encode('UTF-8')).hexdigest()
                if not Client.objects.filter(external_id=client_id).exists():
                    # Create it...
                    # Get a random am
                    ams = User.objects.filter(
                        groups__name=settings.GLOBAL_GROUP_PREFIX+"Sales Member",
                        unit_memberships__isnull=False)
                    am_db = ams[random.randint(0, ams.count()-1)]
                    client_db = Client.objects.create(
                        name=fake.company(),
                        external_id=client_id,
                    )
                    client_db.account_managers.add(am_db)
                    self.stdout.write(
                        self.style.NOTICE('Created client '+client_db.name)
                    )
                else:
                    client_db = Client.objects.get(external_id=client_id)

                # Check there's some contacts created...
                total_contacts = Contact.objects.filter(company=client_db).count()
                if total_contacts < 5:
                    # Lets create it...
                    for _ in range(5 - total_contacts):
                        self.stdout.write(
                            self.style.NOTICE('Created contact '+client_db.name)
                        )
                        cont = fake.profile()
                        Contact.objects.create(
                            jobtitle=cont['job'], first_name=fake.first_name(), last_name=fake.last_name(),
                            phone=fake.phone_number(), email=fake.email(), company=client_db,
                        )
                
                # get a random PoC
                pocs = Contact.objects.filter(company=client_db)
                poc_db = pocs[random.randint(0, pocs.count()-1)]
                
                am_db = client_db.account_managers.all().first()
                unit_db = am_db.unit_memberships.all().first().unit

                # Lets get a project!
                list_of_jobs = [
                    "Webapp", "Pentest", "Red Team", "Build Review", "ITHC"
                ]
                title=fake.microservice() + random.choice(list_of_jobs)
                if not Job.objects.filter(external_id=j_proj_id).exists():
                    job_db = Job.objects.create(
                        title=title,
                        external_id=j_proj_id, client=client_db,
                        desired_start_date=start_date, desired_delivery_date=end_date,
                        unit=unit_db, account_manager=am_db,
                        created_by=am_db, primary_client_poc=poc_db,
                    )
                else:
                    job_db = Job.objects.get(external_id=j_proj_id)
                
                # Lets create a phase...
                if not job_db.phases.all():
                    # Figure out service
                    serv = None
                    for x in Service.objects.all():
                        if x.name in job_db.title:
                            serv = x
                    if not serv:
                        # get a random service then!
                        serv = Service.objects.all()[random.randint(0, Service.objects.all().count()-1)]
                    
                    name = job_db.title + " - " + serv.name

                    self.stdout.write(
                        self.style.NOTICE('Creating phase: "'+name)
                    )
                    phase = Phase.objects.create(
                        job=job_db, phase_number=1, title=name, service=serv
                    )
                else:
                    # get the first phase....
                    phase = job_db.phases.all().first()
                
                with open(options['directory']+"projects/"+str(j_proj['id'])+"/assignments.json") as proj_file3:
                    j_proj_assignments = json.load(proj_file3)
                
                # Lets add the associations!
                for assignment in j_proj_assignments['data']:
                    ass = j_proj_assignments['data'][assignment][0]
                    if ass['user_id']:
                        if User.objects.filter(external_id=ass['user_id']).exists():
                            usr = User.objects.get(external_id=ass['user_id'])

                            if not TimeSlot.objects.filter(start=ass['starts_at'], end=ass['ends_at'],
                                                        user=usr, phase=phase).exists():
                                # add a slot
                                TimeSlot.objects.create(start=ass['starts_at'], end=ass['ends_at'],
                                                               deliveryRole=TimeSlotDeliveryRole.DELIVERY,
                                                               slotType=TimeSlotType.DELIVERY,
                                                                user=usr, phase=phase)


                self.stdout.write(
                    self.style.NOTICE('Processing project: "'+client+': '+name+'" ('+start_date+' - '+end_date+')')
                )
