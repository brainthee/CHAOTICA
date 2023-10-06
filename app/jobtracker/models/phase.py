from django.db import models
from jobtracker.enums import TimeSlotDeliveryRole, PhaseStatuses
from django_fsm import FSMIntegerField, transition, can_proceed
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse
from simple_history.models import HistoricalRecords
from django.db.models import Q
from django.contrib.contenttypes.fields import GenericRelation
from model_utils.fields import MonitorField
from django.db.models import JSONField
from bs4 import BeautifulSoup
from django.contrib import messages
from pprint import pprint
from chaotica_utils.models import Note, User, UserCost
from chaotica_utils.enums import *
from chaotica_utils.tasks import *
from chaotica_utils.utils import *
from chaotica_utils.views import log_system_activity
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import Permission
from constance import config
from django_bleach.models import BleachField
from ..models.job import Job
from ..enums import BOOL_CHOICES, TechQARatings, PresQARatings, FeedbackType, JobStatuses


class PhaseManager(models.Manager):
    def phases_for_user(self, user):
        # Job's we're interested in:
        # - Scheduled on
        # - Lead/Author of
        # - Scoped while before scoping approved
        matches = self.filter(
            Q(timeslots__user=user) | # Filter by scheduled
            Q(report_author=user) | # Filter for report author
            Q(project_lead=user)  # filter for lead
            ).distinct()
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
    service = models.ForeignKey("Service", null=True, blank=True,
        related_name="phases", on_delete=models.PROTECT
    )
    description = BleachField(blank=True, null=True)

    # Requirements
    test_target = BleachField('Test Target URL/IPs/Scope', blank=True, null=True)
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
        from ..models.common import Feedback
        return Feedback.objects.filter(phase=self, feedbackType=FeedbackType.SCOPE)

    def feedback_techqa(self):
        from ..models.common import Feedback
        return Feedback.objects.filter(phase=self, feedbackType=FeedbackType.TECH)

    def feedback_presqa(self):
        from ..models.common import Feedback
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
    
    def fire_status_notification(self, targetStatus):
        if targetStatus == PhaseStatuses.DRAFT:
            pass        

        elif targetStatus == PhaseStatuses.PENDING_SCHED:
            pass

        elif targetStatus == PhaseStatuses.SCHEDULED_TENTATIVE:
            pass
        
        elif targetStatus == PhaseStatuses.SCHEDULED_CONFIRMED:        
            # Notify project team
            users_to_notify = self.team()
            notice = AppNotification(
                NotificationTypes.PHASE, 
                "Phase Update - Schedule Confirmed", "The schedule for this phase is confirmed.", 
                "emails/phase/SCHEDULED_CONFIRMED.html", phase=self)
            task_send_notifications.delay(notice, users_to_notify)
        
        elif targetStatus == PhaseStatuses.PRE_CHECKS:              
            # Notify project team
            users_to_notify = self.team()
            notice = AppNotification(
                NotificationTypes.PHASE, 
                "Phase Update - Ready for Pre-Checks", "Ready for Pre-checks", 
                "emails/phase/PRE_CHECKS.html", phase=self)
            task_send_notifications.delay(notice, users_to_notify)
        
        elif targetStatus == PhaseStatuses.CLIENT_NOT_READY:          
            # Notify project team
            users_to_notify = self.team()
            notice = AppNotification(
                NotificationTypes.PHASE, 
                "Phase Update - Client Not Ready", "Ready for Pre-checks", 
                "emails/phase/CLIENT_NOT_READY.html", phase=self)
            task_send_notifications.delay(notice, users_to_notify)
        
        elif targetStatus == PhaseStatuses.READY_TO_BEGIN:        
            # Notify project team
            users_to_notify = self.team()
            notice = AppNotification(
                NotificationTypes.PHASE, 
                "Phase Update - Ready To Begin!", "Checks have been carried out and the phase is ready to begin.", 
                "emails/phase/READY_TO_BEGIN.html", phase=self)
            task_send_notifications.delay(notice, users_to_notify)
        
        elif targetStatus == PhaseStatuses.IN_PROGRESS:        
            # Notify project team
            users_to_notify = self.team()
            notice = AppNotification(
                NotificationTypes.PHASE, 
                "Phase Update - In Progress", "The phase has started", 
                "emails/phase/IN_PROGRESS.html", phase=self)
            task_send_notifications.delay(notice, users_to_notify)
        
        elif targetStatus == PhaseStatuses.QA_TECH:        
            # Notify qa team
            if not self.techqa_by:
                users_to_notify = self.job.unit.get_active_members_with_perm("can_tqa_jobs")
            else:
                users_to_notify = User.objects.filter(pk=self.techqa_by.pk)
            notice = AppNotification(
                NotificationTypes.PHASE, 
                "Phase Update - Ready for Tech QA", "The phase is ready for Technical QA", 
                "emails/phase/QA_TECH.html", phase=self)
            task_send_notifications.delay(notice, users_to_notify)
        
        elif targetStatus == PhaseStatuses.QA_TECH_AUTHOR_UPDATES:        
            users_to_notify = User.objects.filter(pk=self.report_author.pk)
            notice = AppNotification(
                NotificationTypes.PHASE, 
                "Phase Update - Requires Author Updates", "The report for this phase requires author updates.", 
                "emails/phase/QA_TECH_AUTHOR_UPDATES.html", phase=self)
            task_send_notifications.delay(notice, users_to_notify)
        
        elif targetStatus == PhaseStatuses.QA_PRES:        
            # Notify qa team
            if not self.presqa_by:
                users_to_notify = self.job.unit.get_active_members_with_perm("can_pqa_jobs")
            else:
                users_to_notify = User.objects.filter(pk=self.presqa_by.pk)
            notice = AppNotification(
                NotificationTypes.PHASE, 
                "Phase Update - Ready for Pres QA", "The phase is ready for Presentation QA", 
                "emails/phase/QA_PRES.html", phase=self)
            task_send_notifications.delay(notice, users_to_notify)
        
        elif targetStatus == PhaseStatuses.QA_PRES_AUTHOR_UPDATES:        
            users_to_notify = User.objects.filter(pk=self.report_author.pk)
            notice = AppNotification(
                NotificationTypes.PHASE, 
                "Phase Update - Requires Author Updates", "The report for this phase requires author updates.", 
                "emails/phase/QA_PRES_AUTHOR_UPDATES.html", phase=self)
            task_send_notifications.delay(notice, users_to_notify)
        
        elif targetStatus == PhaseStatuses.COMPLETED:        
            # Notify project team
            users_to_notify = self.team()
            notice = AppNotification(
                NotificationTypes.PHASE, 
                "Phase Update - Complete", "The phase is ready for delivery", 
                "emails/phase/COMPLETED.html", phase=self)
            task_send_notifications.delay(notice, users_to_notify)
        
        elif targetStatus == PhaseStatuses.DELIVERED:
            pass
        
        elif targetStatus == PhaseStatuses.CANCELLED:
            pass
        
        elif targetStatus == PhaseStatuses.POSTPONED:            
            users_to_notify = None
            notice = AppNotification(
                NotificationTypes.PHASE, 
                "Phase Update - Postponed", "This phase has been postponed!", 
                "emails/phase/POSTPONED.html", phase=self)
            task_send_notifications.delay(notice, users_to_notify)
        
        elif targetStatus == PhaseStatuses.DELETED:
            pass
        
        elif targetStatus == PhaseStatuses.ARCHIVED:
            pass

    
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
        from ..models.timeslot import TimeSlot
        ids = []
        for slot in TimeSlot.objects.filter(phase=self):
            if slot.user.pk not in ids:
                ids.append(slot.user.pk)
        if self.project_lead and self.project_lead.pk not in ids:
                ids.append(self.project_lead.pk)
        if self.report_author and self.report_author.pk not in ids:
                ids.append(self.report_author.pk)
        if self.techqa_by and self.techqa_by.pk not in ids:
                ids.append(self.techqa_by.pk)
        if self.presqa_by and self.presqa_by.pk not in ids:
                ids.append(self.presqa_by.pk)
        if ids:
            return User.objects.filter(pk__in=ids)
        else:
            return User.objects.none()

    def team_scheduled(self):
        from ..models.timeslot import TimeSlot
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
        from ..models.timeslot import TimeSlot
        slots = TimeSlot.objects.filter(phase=self, deliveryRole=slotType)
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
            # We've scoped 0 but scheduled. Lets make a superficial scope of 1 to show perc inc
            totalScoped = 10
        return round(100 * float(scheduled)/float(totalScoped),2)
    
    def get_total_scheduled_perc(self):
        total_hours = self.get_total_scoped_hours()
        if total_hours > 0:
            # get total scheduled hours...
            totalScheduled = sum(self.get_all_total_scheduled_by_type().values())
            return round(100 * float(totalScheduled)/float(total_hours),2)
        else:
            return 0    

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
        self.fire_status_notification(PhaseStatuses.SCHEDULED_TENTATIVE)

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
        self.fire_status_notification(PhaseStatuses.SCHEDULED_CONFIRMED)

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
        self.fire_status_notification(PhaseStatuses.PRE_CHECKS)

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
        self.fire_status_notification(PhaseStatuses.CLIENT_NOT_READY)

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
        self.fire_status_notification(PhaseStatuses.READY_TO_BEGIN)

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
        self.fire_status_notification(PhaseStatuses.IN_PROGRESS)

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
        self.fire_status_notification(PhaseStatuses.QA_TECH)

    def can_proceed_to_tech_qa(self):
        return can_proceed(self.to_tech_qa)
        
    def can_to_tech_qa(self, notifyRequest=None):
        _canProceed = True
        # Do logic checks
        if self.feedback_scope_correct is None:
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "Please report if the scope was correct")
            _canProceed = False

        if self.feedback_scope_correct is False:
            # Check if there's any feedback since they've flagged it as wrong...
            if not self.feedback_scope():
                if notifyRequest:
                    messages.add_message(notifyRequest, messages.ERROR, "Scope was incorrect but no feedback provided")
                _canProceed = False

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
        self.fire_status_notification(PhaseStatuses.QA_TECH_AUTHOR_UPDATES)

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
        self.fire_status_notification(PhaseStatuses.QA_PRES)

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
        if not self.feedback_techqa():
            if notifyRequest:
                messages.add_message(notifyRequest, messages.ERROR, "No Tech QA feedback has been left")
            _canProceed = False
        
        # Make sure a rating has been left
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
        self.fire_status_notification(PhaseStatuses.QA_PRES_AUTHOR_UPDATES)

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
        self.fire_status_notification(PhaseStatuses.COMPLETED)

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
            if not self.feedback_presqa():
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
        self.fire_status_notification(PhaseStatuses.DELIVERED)

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
        self.fire_status_notification(PhaseStatuses.CANCELLED)

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
        self.fire_status_notification(PhaseStatuses.POSTPONED)

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
        self.fire_status_notification(PhaseStatuses.DELETED)

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
        self.fire_status_notification(PhaseStatuses.ARCHIVED)

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