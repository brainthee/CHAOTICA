from chaotica_utils.impex.baseImporter import BaseImporter
from structlog import wrap_logger
import logging, json, re
from django.utils import timezone
from django.conf import settings
from datetime import time
from io import StringIO
from pprint import pprint
from chaotica_utils.models import User, Group, UserSkillRatings
from chaotica_utils.enums import UnitRoles
from jobtracker.enums import TimeSlotDeliveryRole, DefaultTimeSlotTypes
from jobtracker.models import TimeSlot, TimeSlotType, Service, Job, Phase, OrganisationalUnit, Client, Contact, Skill, SkillCategory, OrganisationalUnitMember, UserSkill

class ResourceManagerUserImporter(BaseImporter):

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

        log.info('Starting import')

        if not data:
            log.error('Data is null to ResourceManagerUserImporter')
            raise ValueError("Data is null to ResourceManagerUserImporter")
        
        for user_file in data:
            log.info('Processing '+str(user_file))
            decoded_file = user_file.read().decode('utf-8')
            user_data = json.loads(decoded_file)
            pprint(user_data)

            if not user_data['email']:
                log.warning("No email for this user: {display_name}. Skipping...".format(user_data['display_name']), user_data=user_data)

            db_user, _ = User.objects.get_or_create(
                email__iexact=user_data['email'],
                defaults = {
                    "email": user_data['email']
                })
            
            if db_user.first_name != user_data['first_name']:
                db_user.first_name = user_data['first_name']
            if db_user.last_name != user_data['last_name']:
                db_user.last_name = user_data['last_name']

            org_role = UnitRoles.CONSULTANT

            if user_data['role'] == "Consultant":
                grp = Group.objects.get(name=settings.GLOBAL_GROUP_PREFIX+"User")
                db_user.groups.add(grp)
            elif user_data['role'] == "Account Manager":
                grp = Group.objects.get(name=settings.GLOBAL_GROUP_PREFIX+"Sales Member")
                db_user.groups.add(grp)
                org_role = UnitRoles.SALES
            elif user_data['role'] == "Service Delivery Team":
                grp = Group.objects.get(name=settings.GLOBAL_GROUP_PREFIX+"Service Delivery")
                db_user.groups.add(grp)
                org_role = UnitRoles.SERVICE_DELIVERY


            for custom_field in user_data['data']:
                if custom_field['custom_field_name']=="Market Unit":
                    # Add to the right org unit...
                    org_name = custom_field['value']
                    if org_name:
                        if not OrganisationalUnitMember.objects.filter(member=db_user, unit__name=custom_field['value']).exists():
                            # Add them!
                            org_unit,_ = OrganisationalUnit.objects.get_or_create(name=custom_field['value'])
                            # See if there are any members...
                            if not org_unit.get_managers():
                                org_role = UnitRoles.MANAGER
                                org_unit.lead = db_user
                                org_unit.save()
                            OrganisationalUnitMember.objects.create(
                                member=db_user, unit=org_unit, role=org_role)

                # if custom_field['custom_field_name']=="Certifications":
                #     cert = custom_field['value']
                #     # get cert
                #     if cert:
                #         if Certification.objects.filter(name=cert).exists():
                #             db_cert = Certification.objects.get(name=cert)
                #             if not UserCertification.objects.filter(certification=db_cert, user=db_user).exists():
                #                 UserCertification.objects.create(certification=db_cert, user=db_user)

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

        return (log_stream.getvalue()+'.')[:-1]

    @property
    def importer_name(self):
        return "SmartSheet Exports"

    @property
    def importer_help(self):
        return "Export various sheets into a ZIP file."
