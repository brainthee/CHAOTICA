from django.db import models
from ..enums import *
from django_fsm import FSMIntegerField, transition, can_proceed
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
from simple_history.models import HistoricalRecords
from django.db.models import Q
from django.contrib.contenttypes.fields import GenericRelation
from model_utils.fields import MonitorField
from django.db.models import JSONField
from django.contrib import messages
from pprint import pprint
import uuid
from chaotica_utils.models import Note, User
from chaotica_utils.enums import *
from chaotica_utils.tasks import *
from chaotica_utils.utils import *
from chaotica_utils.views import log_system_activity
from datetime import timedelta
from decimal import Decimal
from django_bleach.models import BleachField


class JobManager(models.Manager):    
    def jobs_for_user(self, user):
        # Job's we're interested in:
        # - Scheduled on
        # - Lead/Author of
        # - Scoped while before scoping approved

        matches = self.filter(
            Q(phases__timeslots__user=user) | # Filter by scheduled
            Q(phases__report_author=user) | # Filter for report author
            Q(phases__project_lead=user) | # filter for lead
            Q(scoped_by__in=[user]) | # filter for scoped
            Q(account_manager=user) | # filter for account_manager
            Q(dep_account_manager=user)  # filter for dep_account_manager
            ).exclude(Q(status=JobStatuses.DELETED)|Q(status=JobStatuses.ARCHIVED)).distinct()
        return matches
    

class Job(models.Model):
    objects = JobManager()
    unit = models.ForeignKey("OrganisationalUnit", related_name='jobs', on_delete=models.CASCADE)
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
    desired_start_date = models.DateField('Start Date', null=True, blank=True, help_text="If left blank, this will be automatically determined from scheduled slots")
    desired_delivery_date = models.DateField('Delivery date', null=True, blank=True, db_index=True, help_text="If left blank, this will be automatically determined from scheduled slots")
    
    
    # Client fields
    client = models.ForeignKey("Client", related_name='jobs', on_delete=models.CASCADE)
    primary_client_poc = models.ForeignKey("Contact", verbose_name='Primary Point of Contact', 
        related_name='jobs_poc_for', blank=True, null=True, on_delete=models.CASCADE)
    additional_contacts = models.ManyToManyField(
        "Contact",
        related_name='jobs_contact_for', blank=True)
    
    # Sales fields
    charge_codes = models.ManyToManyField("BillingCode",
        verbose_name="Charge Code", related_name='jobs', blank=True)
    revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True,
        verbose_name="Sales Revenue", help_text="Cost of the job to the client")
    
    
    def staff_cost(self):
        totalCost = 0
        # Ok, for each person... lets take their cost per hour and figure out staffing!
        from ..models import TimeSlot
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
        "Link",
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
        # we don't do anything yet ;)
        pass

    def __str__(self):
        return u'{client}/{id}'.format(client=self.client, id=self.id)
    
    def fire_status_notification(self, targetStatus):
        if targetStatus == JobStatuses.DRAFT:
            pass        

        elif targetStatus == JobStatuses.PENDING_SCOPE:
            # Notify scoping team
            users_to_notify = self.unit.get_active_members_with_perm("can_scope_jobs")
            notice = AppNotification(
                NotificationTypes.JOB, 
                "Job Pending Scope", "A job has just been marked as ready to scope.", 
                "emails/job/PENDING_SCOPE.html", job=self)
            task_send_notifications.delay(notice, users_to_notify)

        elif targetStatus == JobStatuses.SCOPING:
            pass
        
        elif targetStatus == JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED:
            pass
        
        elif targetStatus == JobStatuses.PENDING_SCOPING_SIGNOFF:        
            # Notify scoping team
            users_to_notify = self.unit.get_active_members_with_perm("can_signoff_scopes")
            notice = AppNotification(
                NotificationTypes.JOB, 
                "Job Scope Pending Signoff", "A job's scope is ready for signoff.", 
                "emails/job/PENDING_SCOPING_SIGNOFF.html", job=self)
            task_send_notifications.delay(notice, users_to_notify)
        
        elif targetStatus == JobStatuses.SCOPING_COMPLETE:        
            # Notify scheduling team
            users_to_notify = self.unit.get_active_members_with_perm("can_schedule_phases")
            notice = AppNotification(
                NotificationTypes.JOB, 
                "Job Ready to Schedule", "A job's scope has been signed off and is ready for scheduling.", 
                "emails/job/SCOPING_COMPLETE.html", job=self)
            task_send_notifications.delay(notice, users_to_notify)
        
        elif targetStatus == JobStatuses.PENDING_START:
            pass
        
        elif targetStatus == JobStatuses.IN_PROGRESS:
            pass
        
        elif targetStatus == JobStatuses.COMPLETED:
            pass
        
        elif targetStatus == JobStatuses.LOST:
            pass
        
        elif targetStatus == JobStatuses.DELETED:
            pass
        
        elif targetStatus == JobStatuses.ARCHIVED:
            pass
    

    def start_date(self):
        from ..models import TimeSlot
        if self.desired_start_date:
            return self.desired_start_date
        else:
            # Calculate start from first delivery slot
            if TimeSlot.objects.filter(phase__job=self, deliveryRole=TimeSlotDeliveryRole.DELIVERY).exists():
                return TimeSlot.objects.filter(phase__job=self, deliveryRole=TimeSlotDeliveryRole.DELIVERY).order_by('-start').first().start.date()
            else:
                # No slots - return None
                return None
            
            
    def delivery_date(self):
        from ..models import TimeSlot
        if self.desired_delivery_date:
            return self.desired_delivery_date
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
        from ..models import TimeSlot
        user_ids = TimeSlot.objects.filter(phase__job=self).values_list('user', flat=True).distinct()
        if user_ids:
            return User.objects.filter(pk__in=user_ids)
        else:
            return None
    
    def get_activeTimeSlotDeliveryRoles(self):
        from ..models import TimeSlot
        mySlots = TimeSlot.objects.filter(phase__job=self).values_list('deliveryRole', flat=True).distinct()
        return mySlots
    
    def get_all_total_scheduled_by_type(self):
        data = dict()
        for state in TimeSlotDeliveryRole.CHOICES:
            data[state[0]] = self.get_total_scheduled_by_type(state[0])
        return data
    
    def get_total_scheduled_by_type(self, slotType):
        from ..models import TimeSlot
        slots = TimeSlot.objects.filter(phase__job=self, deliveryRole=slotType)
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
        return round(100 * float(scheduled)/float(totalScoped),2)


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
        self.fire_status_notification(JobStatuses.PENDING_SCOPE)

    def can_proceed_to_pending_scope(self):
        return can_proceed(self.to_pending_scope)
        
    def can_to_pending_scope(self, notify_request=None):
        _can_proceed = True
        # Do logic checks
        ## Check if we have an account manager
        if not self.account_manager:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "No Account Manager assigned.")
            _can_proceed = False

        ## Check if we have a primary PoC
        if not self.primary_client_poc:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "No Client Point of Contact assigned.")
            _can_proceed = False


        # Do general check
        can_proceed_result = can_proceed(self.to_pending_scope)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "Invalid state or permissions.")
            _can_proceed = False
        return _can_proceed

    # SCOPING
    @transition(field=status, source=[JobStatuses.PENDING_SCOPE,JobStatuses.SCOPING_COMPLETE],
        target=JobStatuses.SCOPING)
    def to_scoping(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.SCOPING][1])
        self.fire_status_notification(JobStatuses.SCOPING)

    def can_proceed_to_scoping(self):
        return can_proceed(self.to_scoping)
        
    def can_to_scoping(self, notify_request=None):
        _can_proceed = True
        # Do logic checks
        # If no person is defined as scoped by, warn we'll set ourselves
        if self.status == JobStatuses.SCOPING_COMPLETE:
            if notify_request:
                messages.add_message(notify_request, messages.INFO, 
                                     "The scope will need to be signed off again.")

        if not self.scoped_by.all():
            if notify_request.user.has_perm('scope_job'):
                if notify_request:
                    messages.add_message(notify_request, messages.INFO, "No one assigned to scope. You will automatically be assigned to scope this job.")
            else:
                if notify_request:
                    messages.add_message(notify_request, messages.ERROR, "No one assigned to scope. You do not have permission to scope this job.")
                _can_proceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_scoping)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "Invalid state or permissions.")
            _can_proceed = False
        return _can_proceed

    # SCOPING_ADDITIONAL_INFO_REQUIRED
    @transition(field=status, source=JobStatuses.SCOPING,
        target=JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED)
    def to_additional_scope_req(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED][1])
        self.fire_status_notification(JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED)

    def can_proceed_to_additional_scope_req(self):
        return can_proceed(self.to_additional_scope_req)
        
    def can_to_additional_scope_req(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_additional_scope_req)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "Invalid state or permissions.")
            _can_proceed = False
        return _can_proceed

    # PENDING_SCOPING_SIGNOFF
    @transition(field=status, 
        source=[JobStatuses.SCOPING, JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED],
        target=JobStatuses.PENDING_SCOPING_SIGNOFF)
    def to_scope_pending_signoff(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.PENDING_SCOPING_SIGNOFF][1])
        self.fire_status_notification(JobStatuses.PENDING_SCOPING_SIGNOFF)

    def can_proceed_to_scope_pending_signoff(self):
        return can_proceed(self.to_scope_pending_signoff)
        
    def can_to_scope_pending_signoff(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        ## Check fields are populated
        if not self.overview:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "Job overview missing.")
            _can_proceed = False

        if ((self.high_risk or self.technically_complex_test) and not self.reasons_for_high_risk):
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "Flagged as complex or high risk but no detail entered.")
            _can_proceed = False

        if not self.phases.all():
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "No phases defined")
            _can_proceed = False

        for phase in self.phases.all():
            if phase.get_total_scoped_hours() == Decimal(0.0):
                if notify_request:
                    messages.add_message(notify_request, messages.ERROR, "Phase with no hours: "+str(phase))
                _can_proceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_scope_pending_signoff)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "Invalid state or permissions.")
            _can_proceed = False
        return _can_proceed

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

        self.fire_status_notification(JobStatuses.SCOPING_COMPLETE)

    def can_proceed_to_scope_complete(self):
        return can_proceed(self.to_scope_complete)
        
    def can_to_scope_complete(self, notify_request=None):
        _can_proceed = True
        # Do logic checks
        #         
        ## TODO: Setup a `can_signoff_own_scopes` permission
        if notify_request:
            # We have a request, check if we've scoped it...
            if notify_request.user.has_perm('can_signoff_scopes', self.unit):
                if notify_request.user in self.scoped_by.all():
                    # Yup, we've scoped it - check for permission...
                    if not notify_request.user.has_perm('can_signoff_own_scopes', self.unit):
                        messages.add_message(notify_request, messages.ERROR, 
                                            "You do not have permission to sign off your own scope.")
                        _can_proceed = False
                    else:
                        # We can sign off our own scopes - warn!
                        messages.add_message(notify_request, messages.INFO, 
                                            "Be aware - you are about to sign off your own scope!")
                else:
                    messages.add_message(notify_request, messages.INFO, 
                                        "This will assign you as approver to this scope")

            else:
                # We don't have permission to signoff scopes!
                messages.add_message(notify_request, messages.ERROR, 
                                    "You do not have permission to sign off scopes.")
                _can_proceed = False

        ## Check fields are populated
        if not self.overview:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "Job overview missing.")
            _can_proceed = False

        if ((self.high_risk or self.technically_complex_test) and not self.reasons_for_high_risk):
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "Flagged as complex or high risk but no detail entered.")
            _can_proceed = False

        if not self.phases.all():
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "No phases defined")
            _can_proceed = False

        for phase in self.phases.all():
            if phase.get_total_scoped_hours() == Decimal(0.0):
                if notify_request:
                    messages.add_message(notify_request, messages.ERROR, "Phase with no hours: "+str(phase))
                _can_proceed = False

        # Do general check
        can_proceed_result = can_proceed(self.to_scope_complete)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "Invalid state or permissions.")
            _can_proceed = False
        return _can_proceed

    # PENDING_START
    @transition(field=status, source=JobStatuses.SCOPING_COMPLETE,
        target=JobStatuses.PENDING_START)
    def to_pending_start(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.PENDING_START][1])
        self.fire_status_notification(JobStatuses.PENDING_START)

    def can_proceed_to_pending_start(self):
        return can_proceed(self.to_pending_start)
        
    def can_to_pending_start(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_pending_start)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "Invalid state or permissions.")
            _can_proceed = False
        return _can_proceed

    # IN_PROGRESS
    @transition(field=status, 
        source=[JobStatuses.SCOPING_COMPLETE,JobStatuses.PENDING_START],
        target=JobStatuses.IN_PROGRESS)
    def to_in_progress(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.IN_PROGRESS][1])
        self.fire_status_notification(JobStatuses.IN_PROGRESS)

    def can_proceed_to_in_progress(self):
        return can_proceed(self.to_in_progress)
        
    def can_to_in_progress(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_in_progress)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "Invalid state or permissions.")
            _can_proceed = False
        return _can_proceed

    # COMPLETED
    @transition(field=status, source=JobStatuses.IN_PROGRESS,
        target=JobStatuses.COMPLETED)
    def to_complete(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.COMPLETED][1])
        self.fire_status_notification(JobStatuses.COMPLETED)

    def can_proceed_to_complete(self):
        return can_proceed(self.to_complete)
        
    def can_to_complete(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_complete)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "Invalid state or permissions.")
            _can_proceed = False
        return _can_proceed

    # LOST
    @transition(field=status, 
        source=[JobStatuses.DRAFT,JobStatuses.PENDING_SCOPE,JobStatuses.SCOPING,
            JobStatuses.SCOPING_ADDITIONAL_INFO_REQUIRED,JobStatuses.SCOPING_COMPLETE,
            JobStatuses.PENDING_START],
        target=JobStatuses.LOST)
    def to_lost(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.LOST][1])
        self.fire_status_notification(JobStatuses.LOST)

    def can_proceed_to_lost(self):
        return can_proceed(self.to_lost)
        
    def can_to_lost(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_lost)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "Invalid state or permissions.")
            _can_proceed = False
        return _can_proceed

    # DELETED
    @transition(field=status, source="+",
        target=JobStatuses.DELETED)
    def to_delete(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.DELETED][1])
        self.fire_status_notification(JobStatuses.DELETED)
        # Lets make all phases to cancelled.
        for phase in self.phases.all():
            if phase.can_to_deleted():
                phase.to_deleted()

    def can_proceed_to_delete(self):
        return can_proceed(self.to_delete)
        
    def can_to_delete(self, notify_request=None):
        _can_proceed = True
        # Do logic checks
        for phase in self.phases.all():
            if not phase.can_to_deleted():
                if notify_request:
                    messages.add_message(notify_request, messages.ERROR, "One or more child phases can not be deleted.")
                _can_proceed = False


        # Do general check
        can_proceed_result = can_proceed(self.to_delete)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "Invalid state or permissions.")
            _can_proceed = False
        return _can_proceed

    # ARCHIVED
    @transition(field=status, source=[JobStatuses.COMPLETED,JobStatuses.LOST],
        target=JobStatuses.ARCHIVED)
    def to_archive(self):
        log_system_activity(self, "Moved to "+JobStatuses.CHOICES[JobStatuses.ARCHIVED][1])
        self.fire_status_notification(JobStatuses.ARCHIVED)

    def can_proceed_to_archive(self):
        return can_proceed(self.to_archive)
        
    def can_to_archive(self, notify_request=None):
        _can_proceed = True
        # Do logic checks

        # Do general check
        can_proceed_result = can_proceed(self.to_archive)
        if not can_proceed_result:
            if notify_request:
                messages.add_message(notify_request, messages.ERROR, "Invalid state or permissions.")
            _can_proceed = False
        return _can_proceed