from django.db import models
from .enums import *
from django_fsm import FSMIntegerField, transition, can_proceed
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse
from simple_history.models import HistoricalRecords
from django.db.models import Q, Sum, Count
from django.contrib.contenttypes.fields import GenericRelation
from guardian.shortcuts import get_objects_for_user, assign_perm, remove_perm, get_perms, get_user_perms
from tinymce.models import HTMLField
from lxml.html.clean import clean_html
from phonenumber_field.modelfields import PhoneNumberField
from model_utils.fields import MonitorField
from django.db.models import JSONField
from bs4 import BeautifulSoup
from phone_field import PhoneField
from django.contrib import messages
from pprint import pprint
import uuid, os, random
from chaotica_utils.models import Note, User, UserCost
from chaotica_utils.enums import *
from chaotica_utils.tasks import *
from chaotica_utils.utils import *
from chaotica_utils.views import log_system_activity
from datetime import time, timedelta
from django.core.exceptions import ValidationError
from business_duration import businessDuration
from decimal import Decimal
from django.contrib.auth.models import Permission
from django.templatetags.static import static
from constance import config
from django_bleach.models import BleachField
from location_field.models.plain import PlainLocationField


class Link(models.Model):
    url = models.URLField(max_length=2000, default="", null=True, blank=True, verbose_name="URL")
    title = models.CharField(max_length=255, help_text="Title of the link when other.")
    linkType = models.IntegerField(verbose_name="Link Type", help_text="Type of link",
                                     choices=LinkType.CHOICES, default=LinkType.LN_OTHER)

    def __str__(self):
        return self.url


class BillingCode(models.Model):
    code = models.CharField(verbose_name="Code", max_length=255, unique=True)
    is_chargeable = models.BooleanField(default=False)
    is_recoverable = models.BooleanField(default=False)
    is_closed = models.BooleanField(default=False)

    def __str__(self):
        return self.code

    class Meta:
        ordering = ['code']

    def get_absolute_url(self):
        kwargs = {
            'code': self.code
        }
        return "#"
        # return reverse('billingcode_detail', kwargs=kwargs)


class SkillCategory(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(null=False, default='', unique=True)

    def __str__(self):
        return '%s' % (self.name)

    class Meta:
        verbose_name_plural = "Skill Categories"
        ordering = ['name']
        permissions = (
            ## Defaults
            # ('view_skillcategory', 'View Skill Category'),
            # ('add_skillcategory', 'Add Skill Category'),
            # ('change_skillcategory', 'Change Skill Category'),
            # ('delete_skillcategory', 'Delete Skill Category'),
        )
    

    def syncPermissions(self):
        pass

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)

    def get_absolute_url(self):
        if not self.slug:
            self.slug = slugify(self.name)
            self.save()
        return reverse("skillcategory_detail", kwargs={"slug": self.slug})


class Skill(models.Model):
    name = models.CharField(max_length=200)
    category = models.ForeignKey(SkillCategory, related_name="skills", on_delete=models.CASCADE)
    slug = models.SlugField(null=False, default='', unique=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.category.name+"-"+self.name)
        return super().save(*args, **kwargs)

    def __unicode__(self):
        return u'%s - %s' % (self.name, self.category)

    def __str__(self):
        return '%s - %s' % (self.category, self.name)

    class Meta:
        ordering = ['category', 'name']
        unique_together = (('category', 'name'), )
        permissions = (
            ## Defaults
            # ('view_skill', 'View Skill'),
            # ('add_skill', 'Add Skill'),
            # ('change_skill', 'Change Skill'),
            # ('delete_skill'', 'Delete Skill'),
            ## Extra
            ('view_users_skill', 'View Users with Skill'),
        )    

    def syncPermissions(self):
        pass

    def get_users_can_do_alone(self):
        return UserSkill.objects.filter(skill=self, rating=UserSkillRatings.CAN_DO_ALONE)

    def get_users_can_do_with_support(self):
        return UserSkill.objects.filter(skill=self, rating=UserSkillRatings.CAN_DO_WITH_SUPPORT)

    def get_users_specialist(self):
        return UserSkill.objects.filter(skill=self, rating=UserSkillRatings.SPECIALIST)

    def get_absolute_url(self):
        if not self.slug:
            self.slug = slugify(self.name)
            self.save()
        return reverse("skill_detail", kwargs={"slug": self.slug})


class UserSkill(models.Model):
    skill = models.ForeignKey(Skill, related_name='users', on_delete=models.PROTECT)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        limit_choices_to=(
            models.Q(is_active=True)
        ),
        on_delete=models.CASCADE,
        related_name="skills",
    )
    rating = models.IntegerField(choices=UserSkillRatings.CHOICES, default=UserSkillRatings.NO_EXPERIENCE)
    interested_in_improving_skill = models.BooleanField(default=False)
    last_updated_on = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return u'%s %s - %s: %s' % (self.user.first_name, self.user.last_name,
                                    self.skill)

    class Meta:
        ordering = ['-rating', 'user', ]
        unique_together = (('user', 'skill',),)


class Service(models.Model):
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(null=False, default='', unique=True)
    owners = models.ManyToManyField(settings.AUTH_USER_MODEL,
        blank=True, limit_choices_to={'is_active': True})
    history = HistoricalRecords()
    skillsRequired = models.ManyToManyField(Skill,
        blank=True, related_name="services_skill_required")
    skillsDesired = models.ManyToManyField(Skill,
        blank=True, related_name="services_skill_desired")
    data = JSONField(verbose_name="Data", null=True, blank=True, default=dict)

    class Meta:
        ordering = ['name']
        permissions = (
            ## Defaults
            # ('view_service', 'View Service'),
            # ('add_service', 'Add Service'),
            # ('change_service', 'Change Service'),
            # ('delete_service', 'Delete Service'),
            ## Extras
            ('assign_to_phase', 'Assign To Phase'),
        )
    

    def syncPermissions(self):
        pass

    def __str__(self):
        return self.name
        
    def get_absolute_url(self):
        if not self.slug:
            self.slug = slugify(self.name)
            self.save()
        return reverse('service_detail', kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)


class Certification(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(null=False, default='', unique=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)

    def __str__(self):
        return '%s' % (self.name)

    class Meta:
        ordering = ['name']
        unique_together = (('name'), )
        permissions = (
            ## Defaults
            # ('view_certification', 'View Service'),
            # ('add_certification', 'Add Service'),
            # ('change_certification', 'Change Service'),
            # ('delete_certification', 'Delete Service'),
            ## Extras
            ('view_users_certification', 'View Users with Certification'),
        )

    # def get_absolute_url(self):
    #     if not self.slug:
    #         self.slug = slugify(self.name)
    #         self.save()
    #     return reverse("skill_detail", kwargs={"slug": self.slug})


class UserCertification(models.Model):
    certification = models.ForeignKey(Certification, related_name='users', on_delete=models.PROTECT)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        limit_choices_to=(
            models.Q(is_active=True)
        ),
        on_delete=models.CASCADE,
        related_name="certifications",
    )
    last_updated_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return u'%s %s - %s' % (self.user.first_name, self.user.last_name,
                                    self.certification)

    class Meta:
        ordering = ['certification', 'user', ]
        unique_together = (('user', 'certification',),)


class Client(models.Model):
    name = models.CharField(max_length=255, unique=True, help_text="Legal name of the client")
    slug = models.SlugField(null=False, default='', unique=True)
    short_name = models.CharField(
        max_length=100,
        null=True, blank=True,
        help_text='To be used when referring to this client in documents such as proposals.'
    )
    external_id = models.CharField(verbose_name="External ID", db_index=True, max_length=255, null=True, blank=True, default="")
    hours_in_day = models.DecimalField(max_digits=3, decimal_places=1, default=Decimal(settings.DEFAULT_HOURS_IN_DAY),
        verbose_name="Hours in Day", help_text="The number of billable hours in a day")
    specific_requirements = BleachField(blank=True, null=True, help_text="Any special notes, e.g. certain individuals, onboarding required etc")
    history = HistoricalRecords()
    data = JSONField(verbose_name="Data", null=True, blank=True, default=dict)
    notes = GenericRelation(Note)

    account_managers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='clients_is_am', verbose_name="Account Managers",
        limit_choices_to=models.Q(is_active=True), blank=True)
    tech_account_managers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='clients_is_tam', verbose_name="Technical Account Managers",
        limit_choices_to=models.Q(is_active=True), blank=True)

    class Meta:
        ordering = ['name']
        permissions = (
            ## Defaults
            # ('view_client', 'View Client'),
            # ('add_client', 'Add Client'),
            # ('change_client', 'Change Client'),
            # ('delete_client', 'Delete Client'),
            ## Extra
            ('assign_account_managers_client', 'Assign Account Managers'),
        )
    

    def syncPermissions(self):
        pass

    def __str__(self):
        return self.name
        
    def get_absolute_url(self):
        if not self.slug:
            self.slug = slugify(self.name)
            self.save()
        return reverse('client_detail', kwargs={"slug": self.slug})
    
    def is_ready_for_jobs(self):
        if self.account_managers.all().count():
            return True
        else:
            # Not ready because no account managers
            return False

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)


class Contact(models.Model):
    salutation = models.CharField(max_length=10, blank=True)
    first_name = models.CharField(max_length=200, blank=True)
    last_name = models.CharField(max_length=200, blank=True)
    jobtitle = models.CharField(max_length=200, blank=True)
    department = models.CharField(max_length=200, blank=True)
    phone = PhoneField(max_length=200, blank=True)
    mobile = PhoneField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    company = models.ForeignKey(Client, null=True, blank=True,
                    related_name="contacts", on_delete=models.CASCADE)

    def __str__(self):
        res = '{} {} {}, {}, {}\n{}'.format(
            self.salutation, self.first_name, self.last_name, self.jobtitle, self.company, self.email,
        )
        if self.phone:
            res += u', Phone: {}'.format(self.phone)
        if self.mobile:
            res += u', Mobile: {}'.format(self.mobile)
        return res

    def get_full_name(self):
        return '{} {}'.format(self.first_name, self.last_name)


class Address(models.Model):
    street = models.CharField(max_length=250)
    city = models.CharField(max_length=250)
    county = models.CharField(max_length=250, null=True, blank=True)
    postcode = models.CharField(max_length=25)
    country = models.CharField(max_length=50)
    history = HistoricalRecords()
    data = JSONField(verbose_name="Data", null=True, blank=True, default=dict)

    def __unicode__(self):
        return u'%s, %s, %s' % (self.street, self.city, self.country)

    class Meta:
        verbose_name_plural = 'Addresses'

    def get_full_address(self):
        return u"{street}\n{city}\n{county}{postcode}\n{country}".format(
            street=self.street,
            city=self.city,
            county=self.county + '\n' if self.county else '',
            postcode=self.postcode,
            country=self.country,
        )


def _default_business_days():
    return [1,2,3,4,5]

def get_media_image_file_path(instance, filename):
    ext = filename.split('.')[-1]
    filename = "%s.%s" % (uuid.uuid4(), ext)
    return os.path.join('media/images', filename)


class OrganisationalUnit(models.Model):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(null=False, default='', unique=True)
    description = BleachField(default="", null=True)
    image = models.ImageField(default='default.jpg',  
                                     upload_to=get_media_image_file_path)
    targetProfit = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal(37),
        verbose_name="Target Profit", help_text="The % target profit for this unit")
    businessHours_startTime = models.TimeField('Start Time', default='09:00:00')
    businessHours_endTime = models.TimeField('End Time', default='17:30:00')
    businessHours_days = JSONField(verbose_name="Days", null=True, blank=True, default=_default_business_days, help_text="An int array with the numbers equaling the day of the week. Sunday == 0, Monday == 2 etc")
    approval_required = models.BooleanField('Approval Required', default=True, help_text="Approval by a Manager is required to join the unit")
    special_requirements = BleachField(blank=True, null=True)
    history = HistoricalRecords()
    lead = models.ForeignKey(settings.AUTH_USER_MODEL,
                            related_name='units_lead',
                            default=1,
                            on_delete=models.CASCADE)

    class Meta:
        ordering = ['name']
        permissions = (
            ## Defaults
            # ('view_organisationalunit', 'View Organisational Unit'),
            # ('add_organisationalunit', 'Add Organisational Unit'),
            # ('change_organisationalunit', 'Change Organisational Unit'),
            # ('delete_organisationalunit', 'Delete Organisational Unit'),
            ## Extras
            ('assign_members_organisationalunit', 'Assign Members'),
            ('can_view_unit_jobs', 'Can view jobs'),
            ('can_add_job', 'Can add jobs'),

            ('can_tqa_jobs', 'Can TQA jobs'),
            ('can_pqa_jobs', 'Can PQA jobs'),

            ('can_scope_jobs', 'Can scope jobs'),
            ('can_signoff_scopes', 'Can signoff scopes'),
            ('can_signoff_own_scopes', 'Can signoff own scopes'),

            ('view_users_schedule', 'View Members Schedule'),
            ('can_schedule_phases', 'Can schedule phases'),
        )
    
    def syncPermissions(self):
        for user in self.get_allMembers():
            # Ensure the permissions are set right!
            existing_perms = list(get_user_perms(user, self).values_list('codename', flat=True))
            pprint(existing_perms)

            expected_perms = []
            # get a combined list of perms from their roles...
            for ms in OrganisationalUnitMember.objects.filter(unit=self, member=user, left_date__isnull=True):
                for rolePerm in UnitRoles.PERMISSIONS[ms.role][1]:
                    if "." in rolePerm:
                        cleanPerm = rolePerm.split('.')[1]
                    else:
                        cleanPerm = rolePerm
                    if cleanPerm not in expected_perms:
                        expected_perms.append(cleanPerm)

            pprint(expected_perms)

            if expected_perms:
                # First lets add missing perms...
                for new_perm in expected_perms:
                    if new_perm not in existing_perms:
                        assign_perm(new_perm, user, self)
                
                # Now lets remove old perms
                for old_perm in existing_perms:
                    if old_perm not in expected_perms:
                        remove_perm(old_perm, user, self)
            else:
                if existing_perms:
                    # We should not have any permissions! Clear them all
                    for perm in existing_perms:
                        remove_perm(perm, user, self)
    

    def __str__(self):
        return self.name    
          
    def get_managers(self):
        ids = []
        for mgr in OrganisationalUnitMember.objects.filter(unit=self, role=UnitRoles.MANAGER):
            if mgr.member.pk not in ids:
                ids.append(mgr.member.pk)
        if ids:
            return User.objects.filter(pk__in=ids)
        else:
            return User.objects.none()
          
    def get_activeMembers(self):
        ids = []
        for mgr in OrganisationalUnitMember.objects.filter(unit=self, left_date__isnull=True):
            if mgr.member.pk not in ids:
                ids.append(mgr.member.pk)
        if ids:
            return User.objects.filter(pk__in=ids)
        else:
            return User.objects.none()
          
    def get_allMembers(self):
        ids = []
        for mgr in OrganisationalUnitMember.objects.filter(unit=self):
            if mgr.member.pk not in ids:
                ids.append(mgr.member.pk)
        if ids:
            return User.objects.filter(pk__in=ids)
        else:
            return User.objects.none()
        
    def get_absolute_url(self):
        if not self.slug:
            self.slug = slugify(self.name)
            self.save()
        return reverse('organisationalunit_detail', kwargs={"slug": self.slug})
    
    def get_avatar_url(self):
        if self.image:
            return self.image.url
        else:
            rand = random.randint(1,5)
            return static('assets/img/team-{}.jpg'.format(rand))

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
        # Resync permissions...
        self.syncPermissions()


class OrganisationalUnitMember(models.Model):
    unit = models.ForeignKey(OrganisationalUnit, on_delete=models.CASCADE, related_name='members')
    member = models.ForeignKey(settings.AUTH_USER_MODEL,
                               related_name='unit_memberships',
                               on_delete=models.CASCADE)
    inviter = models.ForeignKey(settings.AUTH_USER_MODEL,
                                on_delete=models.CASCADE,
                                related_name="unitmember_invites",
                                null=True,
                                blank=True)
    role = models.IntegerField(verbose_name="Role",
                        choices=UnitRoles.CHOICES, default=UnitRoles.CONSULTANT)
    add_date = models.DateTimeField(verbose_name="Date Added", help_text="Date the user was added to the unit", auto_now_add=True)
    mod_date = models.DateTimeField(verbose_name="Date Modified", help_text="Last date the membership was modified", auto_now=True)
    left_date = models.DateTimeField(verbose_name="Date Left", help_text="Date the user left the group", null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ['member', '-role']
        get_latest_by = 'mod_date'
        
    @property
    def role_bs_colour(self):
        return UnitRoles.BS_COLOURS[self.role][1]
    
    def getActiveRoles(self):
        return OrganisationalUnitMember.objects.filter(
            unit=self.unit, member=self.member,
            left_date__isnull=True,
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Lets resync the permissions!
        self.unit.syncPermissions()

class WorkflowTasks(models.Model):
    WF_JOB = 1
    WF_PHASE = 2
    CHOICES = (
        (WF_JOB, "Job"),
        (WF_PHASE, "Phase"),
    )
    appliedModel = models.IntegerField(verbose_name="Applicable Model",
                            choices=CHOICES, default=WF_JOB)
    status = models.IntegerField(verbose_name="Status", default=0)
    task = models.CharField('Task', max_length=255)


class JobManager(models.Manager):    
    def jobs_for_user(self, user):
        # Job's we're interested in:
        # - Scheduled on
        # - Lead/Author of
        # - Scoped while before scoping approved

        scheduled = self.filter(phases__timeslots__user=user)
        matches = scheduled
        return matches
    

class Job(models.Model):
    objects = JobManager()
    unit = models.ForeignKey(OrganisationalUnit, related_name='jobs', on_delete=models.CASCADE)
    # slug = models.SlugField(null=False, default='', unique=True)
    slug = models.UUIDField(default=uuid.uuid4, unique=True)
    status = FSMIntegerField(verbose_name="Job Status",
                            help_text="Current state of the job", protected=True,
                            choices=JobStatuses.CHOICES, default=JobStatuses.DRAFT)
    status_changed_date = MonitorField(monitor='status')
    external_id = models.CharField(verbose_name="External ID", db_index=True, max_length=255, null=True, blank=True, default="")
    id = models.AutoField(primary_key=True, verbose_name='Job ID')
    title = models.CharField('Job Title', max_length=250)
    history = HistoricalRecords()
    data = JSONField(verbose_name="Data", null=True, blank=True, default=dict)
    notes = GenericRelation(Note)
    start_date_set = models.DateField('Start Date', null=True, blank=True, help_text="If left blank, this will be automatically determined from scheduled slots")
    delivery_date_set = models.DateField('Delivery date', null=True, blank=True, db_index=True, help_text="If left blank, this will be automatically determined from scheduled slots")
    
    
    # Client fields
    client = models.ForeignKey(Client, related_name='jobs', on_delete=models.CASCADE)
    primary_client_poc = models.ForeignKey(Contact, verbose_name='Primary Point of Contact', 
        related_name='jobs_poc_for', blank=True, null=True, on_delete=models.CASCADE)
    additional_contacts = models.ManyToManyField(
        Contact,
        related_name='jobs_contact_for', blank=True)
    
    # Sales fields
    charge_codes = models.ManyToManyField(BillingCode,
        verbose_name="Charge Code", related_name='jobs', blank=True)
    revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True,
        verbose_name="Sales Revenue", help_text="Cost of the job to the client")
    
    
    def staff_cost(self):
        totalCost = 0
        # Ok, for each person... lets take their cost per hour and figure out staffing!
        for slot in TimeSlot.objects.filter(phase__job=self):
            # lets add up the hours!
            totalCost = totalCost + slot.cost()
        return totalCost
    
    @property
    def job_starts(self):
        pass

    @property
    def job_ends(self):
        pass

    @property
    def profit_perc(self):
        if self.revenue:
            return round((self.profit / self.revenue) * 100, 2)
        else:
            return 0

    @property
    def profit(self):
        staffCost = self.staff_cost()
        if self.revenue is not None:
            return self.revenue - staffCost
        else:
            return 0 - staffCost
    
    @property
    def average_day_rate(self):
        # Calculate profit and return as a Decimal
        # Profit is calculated as basically revenue - costs
        days = self.get_total_scoped_days()
        if days > 0:
            return round(self.revenue / days, 2)
        else:
            return Decimal(0)
    
    def has_staff_with_missing_costs(self):
        scheduled_users = self.team_scheduled()
        if scheduled_users:
            for user in scheduled_users:
                if user.current_cost() is None:
                    return True
        return False


    # People Fields
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Created By", related_name='jobs_created', on_delete=models.CASCADE)
    account_manager = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Account Manager", related_name='jobs_am_for', on_delete=models.CASCADE)
    dep_account_manager = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Deputy Account Manager", null=True, blank=True, related_name='jobs_dam_for', on_delete=models.CASCADE)

    # Related jobs
    previous_jobs = models.ManyToManyField(
        "Job",
        related_name='associated_jobs', blank=True)
    links = models.ManyToManyField(
        Link,
        related_name='jobs', blank=True)

    # # Required Groups
    # associated_teams = models.ManyToManyField(
    #     Team,
    #     related_name='jobs',
    #     blank=True)
    # enforce_team_membership = models.BooleanField(default=False, 
    #     help_text="Setting to true allows only users who are a member of the associated teams to be selected")

    ## General Scoping Fields
    scoped_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='engagements_that_scoped',
        limit_choices_to=models.Q(is_active=True), blank=True)

    scoped_signed_off_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='engagements_that_signed_off_scope',
        limit_choices_to=models.Q(is_active=True), null=True, blank=True,
        on_delete=models.PROTECT)
    
    # General engagement info
    additional_kit_required = models.BooleanField('Additional kit required', default=False)
    additional_kit_info = BleachField(null=True, blank=True)
    kit_sourced_by_client = models.BooleanField(default=False)

    # Restrictions
    is_restricted = models.BooleanField('Is the engagement Protectively Marked', default=False)
    restricted_detail = models.IntegerField('GSC level', choices=RestrictedClassifications.CHOICES, 
                                            null=True, blank=True)
    
    # General scope info    
    bespoke_project = models.BooleanField('Bespoke Project', default=False)
    report_to_third_party = models.BooleanField('Report to 3rd party', default=False)
    is_time_limited = models.BooleanField('Time Limited', default=False)
    retest_included = models.BooleanField(default=False)
    technically_complex_test = models.BooleanField('Does the job involve complex tech', default=False)
    high_risk = models.BooleanField('High Risk', default=False)
    reasons_for_high_risk = BleachField(null=True, blank=True)

    # Main info
    overview = BleachField(blank=True, null=True)

    # Dates
    scoping_requested_on = models.DateTimeField('Scoping requested on', null=True, blank=True)
    scoping_completed_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Job'
        ordering = ['id']
        permissions = (
            ## Defaults
            # ('view_job', 'View Job'),
            # ('add_job', 'Add Job'),
            # ('change_job', 'Change Job'),
            # ('delete_job', 'Delete Job'),
            ## Extras
            ('add_note', 'Can Add Note'),
            ('scope_job', 'Can Scope Job'),
            ('view_schedule', 'Can View Schedule'),
            ('change_schedule', 'Can Change Schedule'),
            ('assign_poc', 'Can assign Point of Contact'),
        )
    

    def syncPermissions(self):
        pass

    def __str__(self):
        return u'{client}/{id}'.format(client=self.client, id=self.id)
    

    def start_date(self):
        if self.start_date_set:
            return self.start_date_set
        else:
            # Calculate start from first delivery slot
            if TimeSlot.objects.filter(phase__job=self, deliveryRole=TimeSlotDeliveryRole.DELIVERY).exists():
                return TimeSlot.objects.filter(phase__job=self, deliveryRole=TimeSlotDeliveryRole.DELIVERY).order_by('-start').first().start.date()
            else:
                # No slots - return None
                return None
            
            
    def delivery_date(self):
        if self.delivery_date_set:
            return self.delivery_date_set
        else:
            # Calculate start from first delivery slot
            if TimeSlot.objects.filter(phase__job=self, deliveryRole=TimeSlotDeliveryRole.REPORTING).exists():
                return TimeSlot.objects.filter(phase__job=self, deliveryRole=TimeSlotDeliveryRole.REPORTING).order_by('end').first().end.date() + timedelta(weeks=1)
            else:
                # No slots - return None
                return None
    
    @property
    def status_bs_colour(self):
        return JobStatuses.BS_COLOURS[self.status][1]
    
    @property
    def inScoping(self):
        pprint(self.status)
        return (self.status == JobStatuses.SCOPING or self.status == JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED)
    
    def isOverdue(self):
        today = timezone.now().date()
        if self.delivery_date() is not None:
            return (self.delivery_date() <= today)
        else:
            return False
    

    def get_user_notes(self):
        return self.notes.filter(is_system_note=False)
    
    
    def get_total_scoped_hours(self):
        phases = self.phases.all()
        totalScoped = Decimal(0.0)
        for phase in phases:
            totalScoped = totalScoped + phase.get_total_scoped_hours()
        return totalScoped
    
    
    def get_total_scoped_days(self):
        totalScopedHrs = self.get_total_scoped_hours()
        # Lets get the hours, 
        return round(totalScopedHrs / self.client.hours_in_day, 2)
        

    def team_scheduled(self):
        user_ids = TimeSlot.objects.filter(phase__job=self).values_list('user', flat=True).distinct()
        if user_ids:
            return User.objects.filter(pk__in=user_ids)
        else:
            return None
    
    def get_activeTimeSlotDeliveryRoles(self):
        mySlots = TimeSlot.objects.filter(phase__job=self).values_list('deliveryRole', flat=True).distinct()
        return mySlots
    
    def get_all_total_scheduled_by_type(self):
        data = dict()
        for state in TimeSlotDeliveryRole.CHOICES:
            data[state[0]] = self.get_total_scheduled_by_type(state[0])
        return data
    
    def get_total_scheduled_by_type(self, slotType):
        slots = TimeSlot.objects.filter(phase__job=self, slotType=slotType)
        total = 0.0
        for slot in slots:
            diff = slot.get_business_hours()
            total = total + diff
        return total
    
    def get_all_total_scoped_by_type(self):
        data = dict()
        for state in TimeSlotDeliveryRole.CHOICES:
            data[state[0]] = {
                "type": state[1],
                "hrs": self.get_total_scoped_by_type(state[0])
            }
        return data
    
    def get_total_scoped_by_type(self, slotType):
        phases = self.phases.all()
        totalScoped = Decimal(0.0)
        for phase in phases:
            # Ugly.... but yolo
            if slotType == TimeSlotDeliveryRole.DELIVERY:
                totalScoped = totalScoped + phase.delivery_hours
            elif slotType == TimeSlotDeliveryRole.REPORTING:
                totalScoped = totalScoped + phase.reporting_hours
            elif slotType == TimeSlotDeliveryRole.MANAGEMENT:
                totalScoped = totalScoped + phase.mgmt_hours
            elif slotType == TimeSlotDeliveryRole.QA:
                totalScoped = totalScoped + phase.qa_hours
            elif slotType == TimeSlotDeliveryRole.OVERSIGHT:
                totalScoped = totalScoped + phase.oversight_hours
            elif slotType == TimeSlotDeliveryRole.DEBRIEF:
                totalScoped = totalScoped + phase.debrief_hours
            elif slotType == TimeSlotDeliveryRole.CONTINGENCY:
                totalScoped = totalScoped + phase.contingency_hours
            elif slotType == TimeSlotDeliveryRole.OTHER:
                totalScoped = totalScoped + phase.other_hours
        return totalScoped
        
    
    def get_slotType_usage_perc(self, slotType):
        # First, get the total for the slotType
        totalScoped = self.get_total_scoped_by_type(slotType)        
        # Now lets get the scheduled amount
        scheduled = self.get_total_scheduled_by_type(slotType)
        if scheduled == 0.0:
            return 0
        if totalScoped == 0.0 and scheduled > 0.0:
            # Over scheduled and scope is zero
            return 100
        return 100 * float(scheduled)/float(totalScoped)


    def get_system_notes(self):
        return self.notes.filter(is_system_note=True)

    def get_absolute_url(self):
        return reverse('job_detail', kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):        

        # Commented this out for the moment. If implementing this - populate the allowed_fields_per_status
        # beware - will need to ensure you allow for auto-changing fields
        
        # if self.pk is not None:
        #     # Get which fields have changed
        #     orig = Job.objects.get(pk=self.pk)
        #     field_names = [field.name for field in Job._meta.fields]
        #     changed_fields = {}
        #     for field_name in field_names:
        #         if getattr(orig, field_name) != getattr(self, field_name):
        #             changed_fields[field_name] = field_name

        #     # Now lets check if we're trying to change any fields which aren't allowed at this state.
        #     allowed_fields_per_status = {
        #         JobStatuses.DRAFT : [
        #             'title'
        #         ],
        #         JobStatuses.PENDING_SCOPE : [
        #             'title'
        #         ],
        #         JobStatuses.SCOPING : [
        #             'title'
        #         ],
        #     }
        #     for f in changed_fields:
        #         if f not in allowed_fields_per_status[self.status]:
        #             raise ValidationError("Current status does not allow that field to be changed")

        return super().save(*args, **kwargs)
    
    #### FSM Methods

    # PENDING_SCOPE
    @transition(field=status, source=JobStatuses.DRAFT,
        target=JobStatuses.PENDING_SCOPE)
    def to_pending_scope(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.PENDING_SCOPE][1])
        self.scoping_requested_on = timezone.now()

        # Notify scoping team
        perm = Permission.objects.get(codename="can_scope_jobs")
        users_to_notify = self.unit.get_activeMembers().filter(Q(user_permissions=perm))
        notice = AppNotification(
            NotificationTypes.JOB, 
            "Job Pending Scope", "A job has just been marked as ready to scope.", 
            "emails/job/PENDING_SCOPE.html", job=self)
        task_send_notifications.delay(notice, users_to_notify)


    def can_proceed_to_pending_scope(self):
        return can_proceed(self.to_pending_scope)
        
    def can_to_pending_scope(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks
        ## Check if we have an account manager
        if not self.account_manager:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "No Account Manager assigned.")
            _canProceed = False

        ## Check if we have a primary PoC
        if not self.primary_client_poc:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "No Client Point of Contact assigned.")
            _canProceed = False


        # Do general check
        can_proceed_result = can_proceed(self.to_pending_scope)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # SCOPING
    @transition(field=status, source=[JobStatuses.PENDING_SCOPE,JobStatuses.SCOPING_COMPLETE],
        target=JobStatuses.SCOPING)
    def to_scoping(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.SCOPING][1])

    def can_proceed_to_scoping(self):
        return can_proceed(self.to_scoping)
        
    def can_to_scoping(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks
        # If no person is defined as scoped by, warn we'll set ourselves
        if self.status == JobStatuses.SCOPING_COMPLETE:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.INFO, 
                                     "The scope will need to be signed off again.")

        if not self.scoped_by.all():
            if notifyRequest.user.has_perm('scope_job'):
                if notifyRequest:
                    messages.add_message(notifyRequest, messages.INFO, "No one assigned to scope. You will automatically be assigned to scope this job.")
            else:
                if notifyRequest:
                    messages.add_message(notifyRequest, messages.ERROR, "No one assigned to scope. You do not have permission to scope this job.")
                _canProceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_scoping)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # SCOPING_ADDITIONAL_INFO_REQUIRED
    @transition(field=status, source=JobStatuses.SCOPING,
        target=JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED)
    def to_additional_scope_req(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED][1])

    def can_proceed_to_additional_scope_req(self):
        return can_proceed(self.to_additional_scope_req)
        
    def can_to_additional_scope_req(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_additional_scope_req)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # PENDING_SCOPING_SIGNOFF
    @transition(field=status, 
        source=[JobStatuses.SCOPING, JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED],
        target=JobStatuses.PENDING_SCOPING_SIGNOFF)
    def to_scope_pending_signoff(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.PENDING_SCOPING_SIGNOFF][1])
        
        # Notify scoping team
        perm = Permission.objects.get(codename="can_signoff_scopes")
        users_to_notify = self.unit.get_activeMembers().filter(Q(user_permissions=perm))
        notice = AppNotification(
            NotificationTypes.JOB, 
            "Job Scope Pending Signoff", "A job's scope is ready for signoff.", 
            "emails/job/PENDING_SCOPING_SIGNOFF.html", job=self)
        task_send_notifications.delay(notice, users_to_notify)

    def can_proceed_to_scope_pending_signoff(self):
        return can_proceed(self.to_scope_pending_signoff)
        
    def can_to_scope_pending_signoff(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks

        ## Check fields are populated
        if not self.overview:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Job overview missing.")
            _canProceed = False

        if ((self.high_risk or self.technically_complex_test) and not self.reasons_for_high_risk):
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Flagged as complex or high risk but no detail entered.")
            _canProceed = False

        if not self.phases.all():
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "No phases defined")
            _canProceed = False

        for phase in self.phases.all():
            if phase.get_total_scoped_hours() == Decimal(0.0):
                if notifyRequest:
                    messages.add_message(notifyRequest, messages.ERROR, "Phase with no hours: "+str(phase))
                _canProceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_scope_pending_signoff)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # SCOPING_COMPLETE
    @transition(field=status, 
        source=JobStatuses.PENDING_SCOPING_SIGNOFF,
        target=JobStatuses.SCOPING_COMPLETE)
    def to_scope_complete(self, user=None):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.SCOPING_COMPLETE][1])
        self.scoping_completed_date = timezone.now()
        if user:
            self.scoped_signed_off_by = user

        # update all phases to pending scheduling
        for phase in self.phases.all():
            if phase.can_to_pending_sched():
                phase.to_pending_sched()
                phase.save()        
        
        # Notify scheduling team
        perm = Permission.objects.get(codename="can_schedule_phases")
        users_to_notify = self.unit.get_activeMembers().filter(Q(user_permissions=perm))
        notice = AppNotification(
            NotificationTypes.JOB, 
            "Job Ready to Schedule", "A job's scope has been signed off and is ready for scheduling.", 
            "emails/job/SCOPING_COMPLETE.html", job=self)
        task_send_notifications.delay(notice, users_to_notify)

    def can_proceed_to_scope_complete(self):
        return can_proceed(self.to_scope_complete)
        
    def can_to_scope_complete(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks
        #         
        ## TODO: Setup a `can_signoff_own_scopes` permission
        if notifyRequest:
            # We have a request, check if we've scoped it...
            if notifyRequest.user.has_perm('can_signoff_scopes', self.unit):
                if notifyRequest.user in self.scoped_by.all():
                    # Yup, we've scoped it - check for permission...
                    if not notifyRequest.user.has_perm('can_signoff_own_scopes', self.unit):
                        messages.add_message(notifyRequest, messages.ERROR, 
                                            "You do not have permission to sign off your own scope.")
                        _canProceed = False
                    else:
                        # We can sign off our own scopes - warn!
                        messages.add_message(notifyRequest, messages.INFO, 
                                            "Be aware - you are about to sign off your own scope!")
                else:
                    messages.add_message(notifyRequest, messages.INFO, 
                                        "This will assign you as approver to this scope")

            else:
                # We don't have permission to signoff scopes!
                messages.add_message(notifyRequest, messages.ERROR, 
                                    "You do not have permission to sign off scopes.")
                _canProceed = False

        ## Check fields are populated
        if not self.overview:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Job overview missing.")
            _canProceed = False

        if ((self.high_risk or self.technically_complex_test) and not self.reasons_for_high_risk):
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Flagged as complex or high risk but no detail entered.")
            _canProceed = False

        if not self.phases.all():
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "No phases defined")
            _canProceed = False

        for phase in self.phases.all():
            if phase.get_total_scoped_hours() == Decimal(0.0):
                if notifyRequest:
                    messages.add_message(notifyRequest, messages.ERROR, "Phase with no hours: "+str(phase))
                _canProceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_scope_complete)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # PENDING_START
    @transition(field=status, source=JobStatuses.SCOPING_COMPLETE,
        target=JobStatuses.PENDING_START)
    def to_pending_start(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.PENDING_START][1])

    def can_proceed_to_pending_start(self):
        return can_proceed(self.to_pending_start)
        
    def can_to_pending_start(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_pending_start)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # IN_PROGRESS
    @transition(field=status, 
        source=[JobStatuses.SCOPING_COMPLETE,JobStatuses.PENDING_START],
        target=JobStatuses.IN_PROGRESS)
    def to_in_progress(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.IN_PROGRESS][1])

    def can_proceed_to_in_progress(self):
        return can_proceed(self.to_in_progress)
        
    def can_to_in_progress(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_in_progress)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # COMPLETED
    @transition(field=status, source=JobStatuses.IN_PROGRESS,
        target=JobStatuses.COMPLETED)
    def to_complete(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.COMPLETED][1])

    def can_proceed_to_complete(self):
        return can_proceed(self.to_complete)
        
    def can_to_complete(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_complete)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # LOST
    @transition(field=status, 
        source=[JobStatuses.DRAFT,JobStatuses.PENDING_SCOPE,JobStatuses.SCOPING,
            JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED,JobStatuses.SCOPING_COMPLETE,
            JobStatuses.PENDING_START],
        target=JobStatuses.LOST)
    def to_lost(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.LOST][1])

    def can_proceed_to_lost(self):
        return can_proceed(self.to_lost)
        
    def can_to_lost(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_lost)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # DELETED
    @transition(field=status, source="+",
        target=JobStatuses.DELETED)
    def to_delete(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.DELETED][1])

    def can_proceed_to_delete(self):
        return can_proceed(self.to_delete)
        
    def can_to_delete(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_delete)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # ARCHIVED
    @transition(field=status, source=[JobStatuses.COMPLETED,JobStatuses.LOST],
        target=JobStatuses.ARCHIVED)
    def to_archive(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.ARCHIVED][1])

    def can_proceed_to_archive(self):
        return can_proceed(self.to_archive)
        
    def can_to_archive(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_archive)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed



class PhaseManager(models.Manager):
    def phases_for_user(self, user):
        # Job's we're interested in:
        # - Scheduled on
        # - Lead/Author of
        # - Scoped while before scoping approved

        scheduled = self.filter(timeslots__user=user).distinct()
        matches = scheduled
        return matches

class Phase(models.Model):
    objects = PhaseManager()
    job = models.ForeignKey(
        Job,
        related_name="phases",
        on_delete=models.CASCADE
    )

    # auto fields
    slug = models.SlugField(null=False, default='', unique=True)
    phase_id = models.CharField(max_length=100, unique=True, verbose_name='Phase ID')

    # misc fields
    history = HistoricalRecords()
    data = JSONField(verbose_name="Data", null=True, blank=True, default=dict)
    notes = GenericRelation(Note)
    status = FSMIntegerField(choices=PhaseStatuses.CHOICES, db_index=True, default=PhaseStatuses.DRAFT, protected=True)

    # Phase info
    phase_number = models.IntegerField(db_index=True)
    title = models.CharField(max_length=200)

    # General test info
    service = models.ForeignKey(Service, null=True, blank=True,
        related_name="phases", on_delete=models.PROTECT
    )
    description = BleachField(blank=True, null=True)

    # Requirements
    test_target = BleachField('Test Target URL/IPs/Scope', blank=True, null=True)
    account_credentials = BleachField('Test Account Credentials', blank=True, null=True)
    comm_reqs = BleachField('Communication Requirements', blank=True, null=True)
    
    restrictions = BleachField('Time restrictions / Special requirements', blank=True, null=True)
    scheduling_requirements = BleachField('Special requirements for scheduling', blank=True, null=True)
    prerequisites = BleachField('Pre-requisites', null=True, blank=True)

    # Key Users
    report_author = models.ForeignKey(settings.AUTH_USER_MODEL,
        related_name='phase_where_report_author', null=True, blank=True,
        limit_choices_to=models.Q(is_staff=True), on_delete=models.PROTECT,
    )
    project_lead = models.ForeignKey(settings.AUTH_USER_MODEL,
        related_name='phase_where_project_lead', null=True, blank=True,
        limit_choices_to=models.Q(is_staff=True), on_delete=models.PROTECT,
    )
    techqa_by = models.ForeignKey(settings.AUTH_USER_MODEL,
        related_name='techqaed_phases', verbose_name='Tech QA by',
        limit_choices_to=models.Q(is_staff=True), null=True, blank=True, on_delete=models.PROTECT,
    )
    presqa_by = models.ForeignKey(settings.AUTH_USER_MODEL,
        related_name='presqaed_phases', verbose_name='Pres QA by',
        limit_choices_to=models.Q(is_staff=True), null=True, blank=True, on_delete=models.PROTECT,
    )

    # Logistics
    is_testing_onsite = models.BooleanField('Testing Onsite', default=False)
    is_reporting_onsite = models.BooleanField('Reporting Onsite', default=False)
    location = BleachField('Onsite Location', blank=True, null=True)
    number_of_reports = models.IntegerField(
        default=1,
        help_text='If set to 0, this phase will not go through Technical or Presentation QA',
    )
    report_to_be_left_on_client_site = models.BooleanField(default=False)

    # links
    linkDeliverable = models.URLField(max_length=2000, default="", null=True, blank=True, verbose_name="Link to Deliverable")
    linkTechData = models.URLField(max_length=2000, default="", null=True, blank=True, verbose_name="Link to Technical Data")
    linkReportData = models.URLField(max_length=2000, default="", null=True, blank=True, verbose_name="Link to Report Data")

    # dates
    start_date_set = models.DateField('Start Date', null=True, blank=True, help_text="If left blank, this will be automatically determined from scheduled slots")
    delivery_date_set = models.DateField('Delivery date', null=True, blank=True, db_index=True, help_text="If left blank, this will be automatically determined from scheduled slots")
    
    due_to_techqa_set = models.DateField('Due to Tech QA', null=True, blank=True, help_text="If left blank, this will be automatically determined from the end of last day of reporting")
    due_to_presqa_set = models.DateField('Due to Pres QA', null=True, blank=True, help_text="If left blank, this will be automatically determined from the end of last day of reporting plus QA days")

    def earliest_date(self):
        if self.start_date:
            return self.start_date
        elif self.job.start_date():
            return self.job.start_date()
        else:
            # return today
            return timezone.now().today()
        
    def earliest_scheduled_date(self):
        # Calculate start from first delivery slot
        if self.timeslots.filter(deliveryRole=TimeSlotDeliveryRole.DELIVERY).exists():
            return self.timeslots.filter(deliveryRole=TimeSlotDeliveryRole.DELIVERY).order_by('-start').first().start.date()
        else:
            # return today
            return timezone.now().today()        

    @property
    def start_date(self):
        if self.start_date_set:
            return self.start_date_set
        else:
            # Calculate start from first delivery slot
            if self.timeslots.filter(deliveryRole=TimeSlotDeliveryRole.DELIVERY).exists():
                return self.timeslots.filter(deliveryRole=TimeSlotDeliveryRole.DELIVERY).order_by('-start').first().start.date()
            else:
                # No slots - return None
                return None
            
    @property
    def due_to_techqa(self):
        if self.due_to_techqa_set:
            return self.due_to_techqa_set
        else:
            # Calculate start from last delivery slot
            if self.timeslots.filter(Q(deliveryRole=TimeSlotDeliveryRole.REPORTING)|Q(deliveryRole=TimeSlotDeliveryRole.DELIVERY)).exists():
                return self.timeslots.filter(Q(deliveryRole=TimeSlotDeliveryRole.REPORTING)|Q(deliveryRole=TimeSlotDeliveryRole.DELIVERY)).order_by('end').first().end.date()
            else:
                # No slots - return None
                return None
            
    @property
    def due_to_presqa(self):
        if self.due_to_presqa_set:
            return self.due_to_presqa_set
        else:
            # Calculate start from last delivery slot
            if self.timeslots.filter(Q(deliveryRole=TimeSlotDeliveryRole.REPORTING)|Q(deliveryRole=TimeSlotDeliveryRole.DELIVERY)).exists():
                return self.timeslots.filter(Q(deliveryRole=TimeSlotDeliveryRole.REPORTING)|Q(deliveryRole=TimeSlotDeliveryRole.DELIVERY)).order_by('end').first().end.date() + timedelta(days=5)
            else:
                # No slots - return None
                return None
            
    @property
    def delivery_date(self):
        if self.delivery_date_set:
            return self.delivery_date_set
        else:
            # Calculate start from first delivery slot
            if self.timeslots.filter(Q(deliveryRole=TimeSlotDeliveryRole.REPORTING)|Q(deliveryRole=TimeSlotDeliveryRole.DELIVERY)).exists():
                return self.timeslots.filter(Q(deliveryRole=TimeSlotDeliveryRole.REPORTING)|Q(deliveryRole=TimeSlotDeliveryRole.DELIVERY)).order_by('end').first().end.date() + timedelta(weeks=1)
            else:
                # No slots - return None
                return None
    
    @property
    def is_delivery_late(self):
        if self.status < PhaseStatuses.DELIVERED:
            if self.number_of_reports > 0:
                if self.due_to_techqa:
                    if self.due_to_techqa < timezone.now().date():
                        return True
        return False
    
    @property
    def is_tqa_late(self):
        if self.status < PhaseStatuses.QA_TECH:
            if self.number_of_reports > 0:
                if self.due_to_techqa:
                    if self.due_to_techqa < timezone.now().date():
                        return True
        return False
    
    @property
    def is_pqa_late(self):
        if self.status < PhaseStatuses.QA_PRES:
            if self.number_of_reports > 0:
                if self.due_to_presqa:
                    if self.due_to_presqa < timezone.now().date():
                        return True
        return False

    # Status change dates
    cancellation_date = models.DateTimeField(null=True, blank=True)
    pre_consultancy_checks_date = models.DateTimeField(null=True, blank=True)
    status_changed_date = MonitorField(monitor='status')

    # rating and feedback
    feedback_scope_correct = models.BooleanField('Was scope correct?', choices=BOOL_CHOICES,
                                                     default=None, null=True, blank=False)
    techqa_report_rating = models.IntegerField('Report rating by person doing tech QA', choices=TechQARatings.CHOICES,
                                               null=True, blank=True)
    presqa_report_rating = models.IntegerField('PresQA report rating', choices=PresQARatings.CHOICES, null=True,
                                               blank=True)

    # # Feedback
    # feedback_scope = models.ManyToManyField(Feedback, blank=True, null=True, 
    #     related_name="scope_phases", on_delete=models.PROTECT, verbose_name='Scope Feedback')
    # feedback_techqa = models.ManyToManyField(Feedback, blank=True, null=True, 
    #     related_name="techqa_phases", on_delete=models.PROTECT, verbose_name='Tech QA Feedback')
    # feedback_presqa = models.ManyToManyField(Feedback, blank=True, null=True, 
    #     related_name="presqa_phases", on_delete=models.PROTECT, verbose_name='Pres QA Feedback')

    def feedback_scope(self):
        return Feedback.objects.filter(phase=self, feedbackType=FeedbackType.SCOPE)

    def feedback_techqa(self):
        return Feedback.objects.filter(phase=self, feedbackType=FeedbackType.TECH)

    def feedback_presqa(self):
        return Feedback.objects.filter(phase=self, feedbackType=FeedbackType.PRES)

    # Scoped Time
    delivery_hours = models.DecimalField('Delivery Hours', max_digits=4, default=0, decimal_places=2, )    
    reporting_hours = models.DecimalField('Reporting Hours', max_digits=4, default=0, decimal_places=2, )   
    mgmt_hours = models.DecimalField('Management Hours', max_digits=4, default=0, decimal_places=2, )   
    qa_hours = models.DecimalField('QA Hours', max_digits=4, default=0, decimal_places=2, )   
    oversight_hours = models.DecimalField('Oversight Hours', max_digits=4, default=0, decimal_places=2, )   
    debrief_hours = models.DecimalField('Debrief Hours', max_digits=4, default=0, decimal_places=2, )   
    contingency_hours = models.DecimalField('Contingency Hours', max_digits=4, default=0, decimal_places=2, )   
    other_hours = models.DecimalField('Other Hours', max_digits=4, default=0, decimal_places=2, )   

    # change control
    last_modified = models.DateTimeField(auto_now=True)
    last_modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, 
        blank=True, null=True, on_delete=models.SET_NULL)
    created_date = models.DateTimeField(auto_now_add=True)

    def get_id(self):
        return u'{job_id}-{phase_number}'.format(
            job_id=self.job.id,
            phase_number=self.phase_number
        )

    class Meta:
        ordering = ('-job__id', 'phase_number')
        unique_together = ('job', 'phase_number')
        verbose_name = 'Phase'
        permissions = (
            ## Defaults
            # ('view_phase', 'View Phase'),
            # ('add_phase', 'Add Phase'),
            # ('change_phase', 'Change Phase'),
            # ('delete_phase', 'Delete Phase'),
            ## Extras
            # ('assign_members_job', 'Assign Members'),
        )
    

    def syncPermissions(self):
        pass

    def __str__(self):
        return u'{id}: {title}'.format(
            id=self.get_id(),
            title=self.title
        )
    
    def summary(self):
        if self.description:
            soup = BeautifulSoup(self.description, 'lxml')
            text = soup.find_all('p')[0].get_text()
            if len(text) > 100:
                text = text.partition('.')[0] + '.'
            return text
        else:
            return ""

    # Gets scheduled users and assigned users (e.g. lead/author/qa etc)        
    def team(self):
        ids = []
        for slot in TimeSlot.objects.filter(phase=self):
            if slot.user.pk not in ids:
                ids.append(slot.user.pk)
        if self.project_lead:
            if self.project_lead.pk not in ids:
                ids.append(self.project_lead.pk)
        if self.report_author:
            if self.report_author.pk not in ids:
                ids.append(self.report_author.pk)
        if self.techqa_by:
            if self.techqa_by.pk not in ids:
                ids.append(self.techqa_by.pk)
        if self.presqa_by:
            if self.presqa_by.pk not in ids:
                ids.append(self.presqa_by.pk)
        if ids:
            return User.objects.filter(pk__in=ids)
        else:
            return User.objects.none()

    def team_scheduled(self):
        scheduledUsersIDs = []
        for slot in TimeSlot.objects.filter(phase=self):
            if slot.user.pk not in scheduledUsersIDs:
                scheduledUsersIDs.append(slot.user.pk)
        if scheduledUsersIDs:
            return User.objects.filter(pk__in=scheduledUsersIDs)
        else:
            return None
    
    def get_all_total_scheduled_by_type(self):
        data = dict()
        for state in TimeSlotDeliveryRole.CHOICES:
            data[state[0]] = self.get_total_scheduled_by_type(state[0])
        return data
    
    def get_total_scheduled_by_type(self, slotType):
        slots = TimeSlot.objects.filter(phase=self, slotType=slotType)
        total = 0.0
        for slot in slots:
            diff = slot.get_business_hours()
            total = total + diff
        return total
    
    
    def get_total_scoped_by_type(self, slotType):
        totalScoped = Decimal(0.0)
        # Ugly.... but yolo
        if slotType == TimeSlotDeliveryRole.DELIVERY:
            totalScoped = totalScoped + self.delivery_hours
        elif slotType == TimeSlotDeliveryRole.REPORTING:
            totalScoped = totalScoped + self.reporting_hours
        elif slotType == TimeSlotDeliveryRole.MANAGEMENT:
            totalScoped = totalScoped + self.mgmt_hours
        elif slotType == TimeSlotDeliveryRole.QA:
            totalScoped = totalScoped + self.qa_hours
        elif slotType == TimeSlotDeliveryRole.OVERSIGHT:
            totalScoped = totalScoped + self.oversight_hours
        elif slotType == TimeSlotDeliveryRole.DEBRIEF:
            totalScoped = totalScoped + self.debrief_hours
        elif slotType == TimeSlotDeliveryRole.CONTINGENCY:
            totalScoped = totalScoped + self.contingency_hours
        elif slotType == TimeSlotDeliveryRole.OTHER:
            totalScoped = totalScoped + self.other_hours
        return totalScoped
    
    def get_total_scoped_hours(self):
        totalScoped = Decimal(0.0)
        for state in TimeSlotDeliveryRole.CHOICES:
            totalScoped = totalScoped + self.get_total_scoped_by_type(state[0])
        return totalScoped
    
    def get_all_total_scoped_by_type(self):
        data = dict()
        for state in TimeSlotDeliveryRole.CHOICES:
            data[state[0]] = {
                "type": state[1],
                "hrs": self.get_total_scoped_by_type(state[0])
            }
        return data            
    
    def get_slotType_usage_perc(self, slotType):
        # First, get the total for the slotType
        totalScoped = self.get_total_scoped_by_type(slotType)        
        # Now lets get the scheduled amount
        scheduled = self.get_total_scheduled_by_type(slotType)
        if scheduled == 0.0:
            return 0
        if totalScoped == 0.0 and scheduled > 0.0:
            # Over scheduled and scope is zero
            return 100
        return 100 * float(scheduled)/float(totalScoped)
    

    def get_user_notes(self):
        return self.notes.filter(is_system_note=False)

    def get_system_notes(self):
        return self.notes.filter(is_system_note=True)

    def save(self, *args, **kwargs):
        if not self.phase_id:
            self.phase_id = self.get_id()
        if not self.slug:
            self.slug = slugify(str(self.phase_id)+self.title)
        super(Phase, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("phase_detail", kwargs={"slug": self.slug, "jobSlug": self.job.slug})
    
    @property
    def status_bs_colour(self):
        return PhaseStatuses.BS_COLOURS[self.status][1]
    
    # PENDING_SCHED
    @transition(field=status, source=[PhaseStatuses.DRAFT, 
                                      PhaseStatuses.SCHEDULED_TENTATIVE,
                                      PhaseStatuses.SCHEDULED_CONFIRMED,
                                      PhaseStatuses.POSTPONED],
        target=PhaseStatuses.PENDING_SCHED)
    def to_pending_sched(self):
        log_system_activity(self, "Moved to "+PhaseStatuses.CHOICES[PhaseStatuses.PENDING_SCHED][1])

    def can_proceed_to_pending_sched(self):
        return can_proceed(self.to_pending_sched)
        
    def can_to_pending_sched(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_pending_sched)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # SCHEDULED_TENTATIVE
    @transition(field=status, source=[PhaseStatuses.PENDING_SCHED,PhaseStatuses.SCHEDULED_CONFIRMED],
        target=PhaseStatuses.SCHEDULED_TENTATIVE)
    def to_sched_tentative(self):
        log_system_activity(self, "Moved to "+PhaseStatuses.CHOICES[PhaseStatuses.SCHEDULED_TENTATIVE][1])

    def can_proceed_to_sched_tentative(self):
        return can_proceed(self.to_sched_tentative)
        
    def can_to_sched_tentative(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks
        # Check we've got slots! Can't move forward if no slots
        if not self.timeslots.all():
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "No scheduled timeslots.")
            _canProceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_sched_tentative)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # SCHEDULED_CONFIRMED
    @transition(field=status, source=[PhaseStatuses.PENDING_SCHED, PhaseStatuses.SCHEDULED_TENTATIVE],
        target=PhaseStatuses.SCHEDULED_CONFIRMED)
    def to_sched_confirmed(self):
        log_system_activity(self, "Moved to "+PhaseStatuses.CHOICES[PhaseStatuses.SCHEDULED_CONFIRMED][1])
        # Ok, lets update our parent job to pending_start!
        if self.job.can_proceed_to_pending_start():
            self.job.to_pending_start()
            self.job.save()
        
        # Notify project team
        users_to_notify = self.team()
        notice = AppNotification(
            NotificationTypes.PHASE, 
            "Phase Update - Schedule Confirmed", "The schedule for this phase is confirmed.", 
            "emails/phase/SCHEDULED_CONFIRMED.html", phase=self)
        task_send_notifications.delay(notice, users_to_notify)

    def can_proceed_to_sched_confirmed(self):
        return can_proceed(self.to_sched_confirmed)
        
    def can_to_sched_confirmed(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks
        # Check we've got slots! Can't confirm if no slots...
        if not self.timeslots.all():
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "No scheduled timeslots.")
            _canProceed = False

        if not self.project_lead:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "No project lead.")
            _canProceed = False

        if not self.report_author and self.number_of_reports > 0:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "More than one report required and no author defined.")
            _canProceed = False

        if self.number_of_reports == 0:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.INFO, "Beware - no reports required!")

        if self.job.status < JobStatuses.SCOPING_COMPLETE:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Parent job not set to "+ JobStatuses.CHOICES[JobStatuses.SCOPING_COMPLETE][1])
            _canProceed = False


        # Do general check
        can_proceed_result = can_proceed(self.to_sched_confirmed)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # PRE_CHECKS
    @transition(field=status, source=[PhaseStatuses.SCHEDULED_CONFIRMED,],
        target=PhaseStatuses.PRE_CHECKS)
    def to_pre_checks(self):
        log_system_activity(self, "Moved to "+PhaseStatuses.CHOICES[PhaseStatuses.PRE_CHECKS][1])
        
        # Notify project team
        users_to_notify = self.team()
        notice = AppNotification(
            NotificationTypes.PHASE, 
            "Phase Update - Ready for Pre-Checks", "Ready for Pre-checks", 
            "emails/phase/PRE_CHECKS.html", phase=self)
        task_send_notifications.delay(notice, users_to_notify)

    def can_proceed_to_pre_checks(self):
        return can_proceed(self.to_pre_checks)
        
    def can_to_pre_checks(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_pre_checks)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # CLIENT_NOT_READY
    @transition(field=status, source=[PhaseStatuses.PRE_CHECKS,],
        target=PhaseStatuses.CLIENT_NOT_READY)
    def to_not_ready(self):
        log_system_activity(self, "Moved to "+PhaseStatuses.CHOICES[PhaseStatuses.CLIENT_NOT_READY][1])
        
        # Notify project team
        users_to_notify = self.team()
        notice = AppNotification(
            NotificationTypes.PHASE, 
            "Phase Update - Client Not Ready", "Ready for Pre-checks", 
            "emails/phase/CLIENT_NOT_READY.html", phase=self)
        task_send_notifications.delay(notice, users_to_notify)

    def can_proceed_to_not_ready(self):
        return can_proceed(self.to_not_ready)
        
    def can_to_not_ready(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_not_ready)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # READY_TO_BEGIN
    @transition(field=status, source=[PhaseStatuses.PRE_CHECKS,PhaseStatuses.CLIENT_NOT_READY],
        target=PhaseStatuses.READY_TO_BEGIN)
    def to_ready(self):
        log_system_activity(self, "Moved to "+PhaseStatuses.CHOICES[PhaseStatuses.READY_TO_BEGIN][1])
        self.pre_consultancy_checks_date = timezone.now()
        
        # Notify project team
        users_to_notify = self.team()
        notice = AppNotification(
            NotificationTypes.PHASE, 
            "Phase Update - Ready To Begin!", "Checks have been carried out and the phase is ready to begin.", 
            "emails/phase/READY_TO_BEGIN.html", phase=self)
        task_send_notifications.delay(notice, users_to_notify)

    def can_proceed_to_ready(self):
        return can_proceed(self.to_ready)
        
    def can_to_ready(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_ready)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # IN_PROGRESS
    @transition(field=status, source=[PhaseStatuses.READY_TO_BEGIN,],
        target=PhaseStatuses.IN_PROGRESS)
    def to_in_progress(self):
        log_system_activity(self, "Moved to "+PhaseStatuses.CHOICES[PhaseStatuses.IN_PROGRESS][1])
        # lets make sure our parent job is in progress now!
        if self.job.status == JobStatuses.PENDING_START:
            if self.job.can_to_in_progress():
                self.job.to_in_progress()
                self.job.save()
        
        # Notify project team
        users_to_notify = self.team()
        notice = AppNotification(
            NotificationTypes.PHASE, 
            "Phase Update - In Progress", "The phase has started", 
            "emails/phase/IN_PROGRESS.html", phase=self)
        task_send_notifications.delay(notice, users_to_notify)

    def can_proceed_to_in_progress(self):
        return can_proceed(self.to_in_progress)
        
    def can_to_in_progress(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_in_progress)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # QA_TECH
    @transition(field=status, source=[PhaseStatuses.IN_PROGRESS,
        PhaseStatuses.QA_TECH_AUTHOR_UPDATES,],
        target=PhaseStatuses.QA_TECH)
    def to_tech_qa(self):
        log_system_activity(self, "Moved to "+PhaseStatuses.CHOICES[PhaseStatuses.QA_TECH][1])
        
        # Notify qa team
        if not self.techqa_by:
            perm = Permission.objects.get(codename="can_tqa_jobs")
            users_to_notify = self.unit.get_activeMembers().filter(Q(user_permissions=perm))
        else:
            users_to_notify = User.objects.filter(pk=self.techqa_by.pk)
        notice = AppNotification(
            NotificationTypes.PHASE, 
            "Phase Update - Ready for Tech QA", "The phase is ready for Technical QA", 
            "emails/phase/QA_TECH.html", phase=self)
        task_send_notifications.delay(notice, users_to_notify)

    def can_proceed_to_tech_qa(self):
        return can_proceed(self.to_tech_qa)
        
    def can_to_tech_qa(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks
        if self.number_of_reports > 0:
            if not self.linkDeliverable:
                if notifyRequest:
                    messages.add_message(notifyRequest, messages.ERROR, "Missing deliverable link")
                _canProceed = False

            if not self.linkTechData:
                if notifyRequest:
                    messages.add_message(notifyRequest, messages.ERROR, "Missing technical data link")
                _canProceed = False

            if not self.linkReportData:
                if notifyRequest:
                    messages.add_message(notifyRequest, messages.ERROR, "Missing report data link")
                _canProceed = False
        else:
            if not self.linkDeliverable:
                if notifyRequest:
                    messages.add_message(notifyRequest, messages.INFO, "Missing deliverable link. Is this intentional?")
                _canProceed = False

            if not self.linkTechData:
                if notifyRequest:
                    messages.add_message(notifyRequest, messages.INFO, "Missing technical data link. Is this intentional?")
                _canProceed = False

            if not self.linkReportData:
                if notifyRequest:
                    messages.add_message(notifyRequest, messages.INFO, "Missing report data link. Is this intentional?")
                _canProceed = False


        # Do general check
        can_proceed_result = can_proceed(self.to_tech_qa)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # QA_TECH_AUTHOR_UPDATES
    @transition(field=status, source=[PhaseStatuses.QA_TECH,],
        target=PhaseStatuses.QA_TECH_AUTHOR_UPDATES)
    def to_tech_qa_updates(self):
        log_system_activity(self, "Moved to "+PhaseStatuses.CHOICES[PhaseStatuses.QA_TECH_AUTHOR_UPDATES][1])
        
        users_to_notify = User.objects.filter(pk=self.report_author.pk)
        notice = AppNotification(
            NotificationTypes.PHASE, 
            "Phase Update - Requires Author Updates", "The report for this phase requires author updates.", 
            "emails/phase/QA_TECH_AUTHOR_UPDATES.html", phase=self)
        task_send_notifications.delay(notice, users_to_notify)

    def can_proceed_to_tech_qa_updates(self):
        return can_proceed(self.to_tech_qa_updates)
        
    def can_to_tech_qa_updates(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks
        if not self.techqa_by:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "No one assigned to Tech QA.")
            _canProceed = False  
        else:
            # Check if we're the person...
            if notifyRequest:
                if notifyRequest.user != self.techqa_by:
                    # We're not the person doing the TQA!
                    messages.add_message(notifyRequest, messages.ERROR, "Not assigned to Tech QA.")
                    _canProceed = False      

        # Do general check
        can_proceed_result = can_proceed(self.to_tech_qa_updates)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # QA_PRES
    @transition(field=status, source=[PhaseStatuses.QA_TECH,
        PhaseStatuses.QA_PRES_AUTHOR_UPDATES],
        target=PhaseStatuses.QA_PRES)
    def to_pres_qa(self):
        log_system_activity(self, "Moved to "+PhaseStatuses.CHOICES[PhaseStatuses.QA_PRES][1])
        
        # Notify qa team
        if not self.presqa_by:
            perm = Permission.objects.get(codename="can_pqa_jobs")
            users_to_notify = self.unit.get_activeMembers().filter(Q(user_permissions=perm))
        else:
            users_to_notify = User.objects.filter(pk=self.presqa_by.pk)
        notice = AppNotification(
            NotificationTypes.PHASE, 
            "Phase Update - Ready for Pres QA", "The phase is ready for Presentation QA", 
            "emails/phase/QA_PRES.html", phase=self)
        task_send_notifications.delay(notice, users_to_notify)

    def can_proceed_to_pres_qa(self):
        return can_proceed(self.to_pres_qa)
        
    def can_to_pres_qa(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks
        if not self.techqa_by:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "No one assigned to Tech QA.")
            _canProceed = False
        else:
            # Check if we're the person...
            if notifyRequest:
                if notifyRequest.user != self.techqa_by:
                    # We're not the person doing the TQA!
                    messages.add_message(notifyRequest, messages.ERROR, "Not assigned to Tech QA.")
                    _canProceed = False

        
        # Lets check feedback/ratings have been left!
        if not self.feedback_techqa:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "No Tech QA feedback has been left")
            _canProceed = False
        if self.techqa_report_rating == None:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "No Tech QA rating has been left")
            _canProceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_pres_qa)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # QA_PRES_AUTHOR_UPDATES
    @transition(field=status, source=[PhaseStatuses.QA_PRES,],
        target=PhaseStatuses.QA_PRES_AUTHOR_UPDATES)
    def to_pres_qa_updates(self):
        log_system_activity(self, "Moved to "+PhaseStatuses.CHOICES[PhaseStatuses.QA_PRES_AUTHOR_UPDATES][1])
        
        users_to_notify = User.objects.filter(pk=self.report_author.pk)
        notice = AppNotification(
            NotificationTypes.PHASE, 
            "Phase Update - Requires Author Updates", "The report for this phase requires author updates.", 
            "emails/phase/QA_PRES_AUTHOR_UPDATES.html", phase=self)
        task_send_notifications.delay(notice, users_to_notify)

    def can_proceed_to_pres_qa_updates(self):
        return can_proceed(self.to_pres_qa_updates)
        
    def can_to_pres_qa_updates(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks
        if not self.presqa_by:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "No one assigned to Pres QA.")
            _canProceed = False
        else:
            # Check if we're the person...
            if notifyRequest:
                if notifyRequest.user != self.presqa_by:
                    # We're not the person doing the TQA!
                    messages.add_message(notifyRequest, messages.ERROR, "Not assigned to Pres QA.")
                    _canProceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_pres_qa_updates)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # COMPLETED
    @transition(field=status, source=[PhaseStatuses.QA_PRES,
        PhaseStatuses.IN_PROGRESS],
        target=PhaseStatuses.COMPLETED)
    def to_completed(self):
        log_system_activity(self, "Moved to "+PhaseStatuses.CHOICES[PhaseStatuses.DELIVERED][1])
        
        # Notify project team
        users_to_notify = self.team()
        notice = AppNotification(
            NotificationTypes.PHASE, 
            "Phase Update - Complete", "The phase is ready for delivery", 
            "emails/phase/COMPLETED.html", phase=self)
        task_send_notifications.delay(notice, users_to_notify)

    def can_proceed_to_completed(self):
        return can_proceed(self.to_completed)
        
    def can_to_completed(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks
        if self.number_of_reports > 0:
            if self.status <= PhaseStatuses.QA_TECH:
                if notifyRequest:
                    messages.add_message(notifyRequest, messages.ERROR, "More than one report expected - must go through QA")
                _canProceed = False

            if not self.presqa_by:
                if notifyRequest:
                    messages.add_message(notifyRequest, messages.ERROR, "No one assigned to Pres QA.")
                _canProceed = False

        
            # Lets check feedback/ratings have been left!
            if not self.feedback_presqa:
                if notifyRequest:
                    messages.add_message(notifyRequest, messages.ERROR, "No Pres QA feedback has been left")
                _canProceed = False
            if self.presqa_report_rating == None:
                if notifyRequest:
                    messages.add_message(notifyRequest, messages.ERROR, "No Pres QA rating has been left")
                _canProceed = False

        else:
            # No reports - display a warning
            if notifyRequest:
                messages.add_message(notifyRequest, messages.INFO, 
                                    "Are you sure there is no report? This bypasses QA!")

        # Do general check
        can_proceed_result = can_proceed(self.to_completed)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # DELIVERED
    @transition(field=status, source=PhaseStatuses.COMPLETED,
        target=PhaseStatuses.DELIVERED)
    def to_delivered(self):
        log_system_activity(self, "Moved to "+PhaseStatuses.CHOICES[PhaseStatuses.DELIVERED][1])
        # Ok, check if all phases have completed...
        jobDone = True
        for phase in self.job.phases.all():
            if phase.pk != self.pk: # we know we're delivered...
                if phase.status < PhaseStatuses.DELIVERED:
                    jobDone = False
                    
        if jobDone:
            if self.job.can_to_complete():
                self.job.to_complete()
                self.job.save()

    def can_proceed_to_delivered(self):
        if self.number_of_reports == 0:
            return can_proceed(self.to_delivered)
        else:
            if self.status == PhaseStatuses.COMPLETED:
                return can_proceed(self.to_delivered)
            else:
                return False
        
    def can_to_delivered(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks
        if notifyRequest:
            messages.add_message(notifyRequest, messages.INFO, 
                                "Are you sure all deliverables have been submitted to the client?")

        # Do general check
        can_proceed_result = can_proceed(self.to_delivered)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed
    
    # CANCELLED
    @transition(field=status, source="+",
        target=PhaseStatuses.CANCELLED)
    def to_cancelled(self):
        log_system_activity(self, "Moved to "+PhaseStatuses.CHOICES[PhaseStatuses.CANCELLED][1])

    def can_proceed_to_cancelled(self):
        return can_proceed(self.to_cancelled)
        
    def can_to_cancelled(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_cancelled)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # POSTPONED
    @transition(field=status, source="+",
        target=PhaseStatuses.POSTPONED)
    def to_postponed(self):
        log_system_activity(self, "Moved to "+PhaseStatuses.CHOICES[PhaseStatuses.POSTPONED][1])
        
        users_to_notify = None
        notice = AppNotification(
            NotificationTypes.PHASE, 
            "Phase Update - Postponed", "This phase has been postponed!", 
            "emails/phase/POSTPONED.html", phase=self)
        task_send_notifications.delay(notice, users_to_notify)

    def can_proceed_to_postponed(self):
        return can_proceed(self.to_postponed)
        
    def can_to_postponed(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_postponed)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # DELETED
    @transition(field=status, source="+",
        target=PhaseStatuses.DELETED)
    def to_deleted(self):
        log_system_activity(self, "Moved to "+PhaseStatuses.CHOICES[PhaseStatuses.DELETED][1])

    def can_proceed_to_deleted(self):
        return can_proceed(self.to_deleted)
        
    def can_to_deleted(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_deleted)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed

    # ARCHIVED
    @transition(field=status, source=[
        PhaseStatuses.DELIVERED, PhaseStatuses.DELETED, PhaseStatuses.CANCELLED
    ],
        target=PhaseStatuses.ARCHIVED)
    def to_archived(self):
        log_system_activity(self, "Moved to "+PhaseStatuses.CHOICES[PhaseStatuses.ARCHIVED][1])

    def can_proceed_to_archived(self):
        return can_proceed(self.to_archived)
        
    def can_to_archived(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_archived)
        if not can_proceed_result:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Invalid state or permissions.")
            _canProceed = False
        return _canProceed


class TimeSlot(models.Model):
    start = models.DateTimeField()
    end = models.DateTimeField()
    notes = GenericRelation(Note)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
        limit_choices_to=(models.Q(is_active=True)),
        related_name="timeslots", on_delete=models.CASCADE,
    )

    phase = models.ForeignKey(Phase, related_name="timeslots",
        null=True, blank=True,on_delete=models.CASCADE
    )

    deliveryRole = models.IntegerField(verbose_name="Type", help_text="Type of role in job",
        choices=TimeSlotDeliveryRole.CHOICES, default=TimeSlotDeliveryRole.NA)
    is_onsite = models.BooleanField(verbose_name="Is onsite", 
        help_text="Is this slot onsite", default=False)
    
    slotType = models.IntegerField(verbose_name="Type", help_text="Type of time",
        choices=TimeSlotType.CHOICES, default=TimeSlotType.GENERIC)
    
    @property
    def slug(self):
        if self.phase:
            return self.phase.job.slug
        return None
    
    def get_web_schedule_format(self, url=None):
        if not url:
            url = self.get_target_url()
            
        return {
            "title": str(self),
            "resourceId": self.user.pk,
            "start": self.start,
            "end": self.end,
            "url": url,
            "color": self.slot_colour(),
        }

    
    def get_business_hours(self):
        startbday = time(9,0,0)
        endbday = time(16,30,0) # 5:30pm - 1hr for lunch! :) 
        unit='hour'
        hours = businessDuration(self.start, self.end, startbday, endbday, unit=unit)
        return hours
    
    def cost(self):
        # Only support a single cost field at the moment... :(
        if UserCost.objects.filter(user=self.user).exists():
            cost = UserCost.objects.filter(user=self.user).filter(effective_from__lte=self.start).last()
            # Now we have a cost, figure out hours and the cost of this slot...
            if cost:
                hours = Decimal(self.get_business_hours())
                return round(Decimal(cost.cost_per_hour * hours), 2)
        return 0 # No cost assigned!


    def is_confirmed(self):
        if not self.phase:
            # If no phase attached... always confirmed ;)
            return True
        else:
            # Phase attached - only proceed if scheduling confirmed on phase
            return self.phase.status >= PhaseStatuses.SCHEDULED_CONFIRMED
    
    def slot_colour(self):
        if not self.phase:
            # If no phase attached... always confirmed ;)
            return "#378006"
        else:
            if self.is_confirmed():
                return "#FFC7CE" if self.is_onsite else "#bdb3ff"
            else:
                return "#E6B9B8" if self.is_onsite else "#95B3D7"


    def __str__(self):
        if self.phase:
            confirmed = "Confirmed" if self.is_confirmed() else "Tentative"
            onsite = ", Onsite" if self.is_onsite else ""
            if self.deliveryRole > TimeSlotDeliveryRole.NA:
                return '{}: {} ({}{})'.format(str(self.phase), self.get_slotType_display(), confirmed, onsite)
            else:
                return '{} ({}{})'.format(str(self.phase), confirmed, onsite)
        else:
            return '{}: {}'.format(self.user.get_full_name(), self.start)
    
    def get_target_url(self):
        if self.phase:
            return self.phase.get_absolute_url()
        else:
            return None
        
    def delete(self):
        phase = self.phase
        super(TimeSlot, self).delete()
        # Ok we're deleted... lets check if we should move the phase status back to pending
        if not TimeSlot.objects.filter(phase=phase).exists():
            # No more slots... move back to pending scheduling
            if phase.status == PhaseStatuses.SCHEDULED_CONFIRMED or phase.status == PhaseStatuses.SCHEDULED_TENTATIVE:
                if phase.can_to_pending_sched():
                    phase.to_pending_sched()
                    phase.save()

    def save(self, *args, **kwargs):
        if self.start > self.end:
            raise ValidationError("End time must come after the start")
        super(TimeSlot, self).save(*args, **kwargs)
        # Lets see if we need to update our parent phase
        if self.phase.status == PhaseStatuses.PENDING_SCHED:
            # lets move to scheduled tentative!
            if self.phase.can_to_sched_tentative():
                self.phase.to_sched_tentative()
                self.phase.save()


class Feedback(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='written_feedback',
        on_delete=models.PROTECT)
    
    phase = models.ForeignKey(
        Phase,
        related_name='feedback',
        on_delete=models.PROTECT)
    
    feedbackType = models.IntegerField(verbose_name="Type", help_text="Type of feedback",
        choices=FeedbackType.CHOICES, default=FeedbackType.OTHER)
        
    body = BleachField()
    created_on = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ['-created_on']
        permissions = (
            ## Defaults
            # ('view_feedback', 'View Feedback'),
            # ('add_feedback', 'Add Feedback'),
            # ('change_feedback', 'Change Feedback'),
            # ('delete_feedback', 'Delete Feedback'),
        )

    def syncPermissions(self):
        pass

    def __str__(self):
        return 'Feedback {} by {}'.format(self.body, self.author.get_full_name())