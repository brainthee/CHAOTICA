from django.db import models
from ..enums import *
from ..models.skill import Skill
from ..models.phase import Phase
from django.conf import settings
from django.utils.text import slugify
from django.urls import reverse
from simple_history.models import HistoricalRecords
from django.contrib.contenttypes.fields import GenericRelation
from django.db.models import JSONField
from phone_field import PhoneField
from pprint import pprint
from chaotica_utils.models import Note
from chaotica_utils.enums import *
from chaotica_utils.tasks import *
from chaotica_utils.utils import *
from chaotica_utils.views import log_system_activity
from decimal import Decimal
from django_bleach.models import BleachField


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