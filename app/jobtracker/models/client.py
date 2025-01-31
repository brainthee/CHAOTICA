from django.db import models
from django.conf import settings
from chaotica_utils.utils import unique_slug_generator
from django.urls import reverse
from simple_history.models import HistoricalRecords
from django.contrib.contenttypes.fields import GenericRelation
from django.db.models import JSONField
from django.utils import timezone
from datetime import timedelta
from phone_field import PhoneField
from chaotica_utils.models import Note
from constance import config
from decimal import Decimal
from django_bleach.models import BleachField
from django.db.models.functions import Lower
from chaotica_utils.tasks import task_send_notifications
from chaotica_utils.utils import AppNotification
from chaotica_utils.views.common import log_system_activity
from chaotica_utils.enums import NotificationTypes


class Client(models.Model):
    name = models.CharField(
        max_length=255, unique=True, help_text="Legal name of the client"
    )
    slug = models.SlugField(null=False, default="", unique=True)
    short_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="To be used when referring to this client in documents such as proposals.",
    )
    external_id = models.CharField(
        verbose_name="External ID",
        db_index=True,
        max_length=255,
        blank=True,
        default="",
    )
    hours_in_day = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        default=Decimal(settings.DEFAULT_HOURS_IN_DAY),
        verbose_name="Hours in Day",
        help_text="The number of billable hours in a day",
    )
    specific_requirements = BleachField(
        blank=True,
        null=True,
        help_text="Any special notes, e.g. certain individuals, onboarding required etc",
    )
    specific_reporting_requirements = BleachField(
        blank=True, null=True, help_text="Any special reporting requirements"
    )
    history = HistoricalRecords()
    data = JSONField(verbose_name="Data", null=True, blank=True, default=dict)
    notes = GenericRelation(Note)

    account_managers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="clients_is_am",
        verbose_name="Account Managers",
        limit_choices_to=models.Q(is_active=True),
        blank=True,
    )
    tech_account_managers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="clients_is_tam",
        verbose_name="Technical Account Managers",
        limit_choices_to=models.Q(is_active=True),
        blank=True,
    )

    ### Onboarding settings
    onboarding_required = models.BooleanField(
        "Onboarding Required",
        default=False,
        help_text="Only onboarded users can be scheduled on jobs for this client.",
    )
    onboarding_reoccurring_renewal = models.BooleanField(
        "Reoccurring Renewal Required",
        default=False,
        help_text="Requirements must be refreshed repeatably.",
    )
    onboarding_requirements = models.TextField(
        "Reoccurring Requirements",
        null=True, blank=True,
        help_text="What requirements are there every renewal.",
    )
    onboarding_reqs_renewal = models.IntegerField(
        "Requirements Refresh Every",
        default=0,
        help_text="How many days requirements must be refreshed.",
    )
    onboarding_reqs_reminder_days = models.IntegerField(
        "Reminder Lead",
        default=0,
        help_text="How many days lead should a reminder be sent.",
    )

    class Meta:
        ordering = [Lower("name")]
        permissions = (("assign_account_managers_client", "Assign Account Managers"),)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
            self.save()
        return reverse("client_detail", kwargs={"slug": self.slug})

    def is_ready_for_jobs(self):
        if self.account_managers.all().count():
            return True
        else:
            # Not ready because no account managers
            return False

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug_generator(self, self.name)
        return super().save(*args, **kwargs)
    
    def get_jobs(self):
        return self.jobs.select_related('unit').all()

    def merge(self, client_to_merge):
        # Things to merge:
        # Jobs
        # Contacts
        # Billing Codes
        # FrameworkAgreements
        # Account Managers
        # Technical Account Managers

        ## Jobs
        from jobtracker.models.job import Job
        Job.objects.filter(client=client_to_merge).update(client=self)
        ## Contacts
        Contact.objects.filter(company=client_to_merge).update(company=self)
        ## BillingCode
        from jobtracker.models.financial import BillingCode
        BillingCode.objects.filter(client=client_to_merge).update(client=self)
        ## FrameworkAgreement
        FrameworkAgreement.objects.filter(client=client_to_merge).update(client=self)

        for am in client_to_merge.account_managers.all():
            self.account_managers.add(am)
            self.save()

        for tam in client_to_merge.tech_account_managers.all():
            self.tech_account_managers.add(tam)
            self.save()

        # If we have got this far... delete the target user!
        client_to_merge.delete()

        return True


class ClientOnboarding(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="onboarded_clients",
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="onboarded_users",
    )
    notes = GenericRelation(Note)

    onboarded = models.DateTimeField(
        "Date Onboarded", null=True, blank=True, help_text="This is the date they are considered onboarded"
    )
    reqs_completed = models.DateTimeField(
        "Requirements Completed", null=True, blank=True, help_text="This is the date reoccurring requirements were last completed"
    )
    offboarded = models.DateTimeField(
        "Date Offboarded", null=True, blank=True, help_text="This is the date they are considered offboarded"
    )

    def status(self):
        now = timezone.now()
        if self.offboarded and self.offboarded < now:
            # Not active if we're past an offboarded date
            return 'offboarded'
        elif self.onboarded and self.onboarded < now:
            # Ok, onboarded is in the past... lets check if we're stale...
            if self.client.onboarding_reoccurring_renewal:
                if self.reqs_completed:
                    renewal_date = self.reqs_completed + timedelta(days=self.client.onboarding_reqs_renewal)
                    if renewal_date < now:
                        # we're stale because we haven't renewed..
                        return 'stale'
                    else:
                        return 'active'
                else:
                    # Reqs required but no renewal date
                    return 'stale'
            else:
                return 'active'
        elif self.onboarded and self.onboarded > now:
            return 'pending'
        else:
            return 'unknown'
    
    @property
    def is_active(self):
        return self.status() == 'active'
    
    @property
    def is_stale(self):
        return self.status() == 'stale'
    
    @property
    def is_offboarded(self):
        return self.status() == 'offboarded'
    
    def days_till_renewal(self):
        now = timezone.now()
        if self.client.onboarding_reoccurring_renewal and self.reqs_completed:
            renewal_date = self.reqs_completed + timedelta(days=self.client.onboarding_reqs_renewal)
            return (renewal_date - now).days
        return 0
    
    def is_due(self):
        now = timezone.now()
        if self.client.onboarding_reoccurring_renewal:
            if self.reqs_completed:
                renewal_date = self.reqs_completed + timedelta(days=self.client.onboarding_reqs_renewal) - timedelta(days=self.client.onboarding_reqs_reminder_days)
                if renewal_date < now:
                    # we're stale because we haven't renewed..
                    return True
            else:
                # Reqs required but no renewal date
                return True
        else:
            return False
        
    def send_reminder(self):
        email_template = "emails/onboarding_reminder.html"
        if self.is_due:
            # check if we should or not...
            days_till_renewal = self.days_till_renewal()
            notice = AppNotification(
                NotificationTypes.CLIENT,
                "{client} Onboarding Requirements Due".format(client=self.client),
                "Onboarding requirements are due in {days_till_renewal} for {client}. Please check the requirements, complete them and mark it as renewed.".format(
                    days_till_renewal=days_till_renewal,
                    client=self.client,
                ),
                email_template,
                action_link=reverse('view_own_onboarding'),
            )
            task_send_notifications(notice, [self.user])
            log_system_activity(self, "Sent Onboarding Reminder")

    class Meta:
        ordering = [Lower("client"), "user"]


class FrameworkAgreement(models.Model):
    client = models.ForeignKey(
        Client, related_name="framework_agreements", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=200, blank=True)
    start_date = models.DateField("Start Date")
    end_date = models.DateField("End Date", null=True, blank=True)

    total_days = models.IntegerField("Total Days")
    allow_over_allocation = models.BooleanField("Allow Over Allocation", default=True)
    closed = models.BooleanField("Closed", default=False)

    class Meta:
        ordering = [Lower("name")]
        unique_together = ["client", "name"]

    def get_absolute_url(self):
        return reverse(
            "client_framework_detail",
            kwargs={"client_slug": self.client.slug, "pk": self.pk},
        )

    def __str__(self):
        return "{} ({}-{})".format(self.name, self.start_date, self.end_date)

    def days_remaining(self):
        days_allocated = self.days_allocated()
        return self.total_days - days_allocated

    def days_allocated(self):
        total = 0
        for job in self.associated_jobs.all():
            total = total + job.total_days_scheduled()
        return total

    def perc_allocated(self):
        if self.total_days:
            return round((self.days_allocated() / self.total_days) * 100, 2)
        else:
            return 0

    def is_over_allocated(self):
        days_allocated = self.days_allocated()
        return days_allocated > self.total_days


class Contact(models.Model):
    salutation = models.CharField(max_length=10, blank=True)
    first_name = models.CharField(max_length=200, blank=True)
    last_name = models.CharField(max_length=200, blank=True)
    jobtitle = models.CharField(max_length=200, blank=True)
    department = models.CharField(max_length=200, blank=True)
    phone = PhoneField(max_length=200, blank=True)
    mobile = PhoneField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    company = models.ForeignKey(
        Client, null=True, blank=True, related_name="contacts", on_delete=models.CASCADE
    )

    def __str__(self):
        res = "{} {} {}, {}, {}\n{}".format(
            self.salutation,
            self.first_name,
            self.last_name,
            self.jobtitle,
            self.company,
            self.email,
        )
        if self.phone:
            res += ", Phone: {}".format(self.phone)
        if self.mobile:
            res += ", Mobile: {}".format(self.mobile)
        return res

    def get_full_name(self):
        return "{} {}".format(self.first_name, self.last_name)


class Address(models.Model):
    street = models.CharField(max_length=250)
    city = models.CharField(max_length=250)
    county = models.CharField(max_length=250, blank=True)
    postcode = models.CharField(max_length=25)
    country = models.CharField(max_length=50)
    history = HistoricalRecords()
    data = JSONField(verbose_name="Data", null=True, blank=True, default=dict)

    def __unicode__(self):
        return "%s, %s, %s" % (self.street, self.city, self.country)

    class Meta:
        verbose_name_plural = "Addresses"

    def get_full_address(self):
        return "{street}\n{city}\n{county}{postcode}\n{country}".format(
            street=self.street,
            city=self.city,
            county=self.county + "\n" if self.county else "",
            postcode=self.postcode,
            country=self.country,
        )