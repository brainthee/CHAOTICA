from django.db import models
from django.urls import reverse
from ..enums import TimeSlotDeliveryRole, PhaseStatuses, AvailabilityType, DefaultTimeSlotTypes
from ..models.phase import Phase
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from chaotica_utils.models import Note, UserCost
from chaotica_utils.utils import ext_reverse
from django.core.exceptions import ValidationError
from business_duration import businessDuration
from decimal import Decimal
from simple_history.models import HistoricalRecords


class TimeSlotType(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name='Name')
    built_in = models.BooleanField(verbose_name="Type is a default type", default=False)
    is_delivery = models.BooleanField(verbose_name="Is a delivery type", default=False)
    is_working = models.BooleanField(verbose_name="Is Working", default=False)
    is_assignable = models.BooleanField(verbose_name="Is Assignable", default=True)
    availability = models.IntegerField(verbose_name="Availability", help_text="If resource is available or not",
        choices=AvailabilityType.CHOICES, default=AvailabilityType.AVAILABLE)
    
    def __str__(self):
        return "{} - ({})".format(self.name, self.get_availability_display())

    class Meta:
        verbose_name_plural = "Timeslot Types"
        ordering = ['name']
    
    @classmethod
    def get_builtin_object(cls, object_pk=DefaultTimeSlotTypes.UNASSIGNED):
        return TimeSlotType.objects.get(pk=object_pk)
    
    @classmethod
    def get_default_slot_type(cls):
        return DefaultTimeSlotTypes.UNASSIGNED


class TimeSlot(models.Model):
    start = models.DateTimeField()
    end = models.DateTimeField()
    notes = GenericRelation(Note)
    history = HistoricalRecords()
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
        limit_choices_to=(models.Q(is_active=True)),
        related_name="timeslots", on_delete=models.CASCADE,
    )

    slot_type = models.ForeignKey(TimeSlotType, related_name="timeslots", on_delete=models.CASCADE,
        default=TimeSlotType.get_default_slot_type,
    )

    phase = models.ForeignKey(Phase, related_name="timeslots",
        null=True, blank=True,on_delete=models.CASCADE
    )

    deliveryRole = models.IntegerField(verbose_name="Delivery Type", help_text="Type of role in job",
        choices=TimeSlotDeliveryRole.CHOICES, default=TimeSlotDeliveryRole.NA)
    is_onsite = models.BooleanField(verbose_name="Is onsite", 
        help_text="Is this slot onsite", default=False)
    
    @property
    def slug(self):
        if self.phase:
            return self.phase.job.slug
        return None

    def __str__(self):
        # There is no rhyme or reason for this...
        if self.phase:
            tentative = "Tentative" if not self.is_confirmed() else ""
            onsite = ", Onsite" if self.is_onsite else ""
            extra = "({}{})".format(tentative, onsite) if tentative or onsite else ""
            return '{}: {} {}'.format(str(self.phase.get_id()), self.slot_type.name, extra)
        else:
            return '{}: {} ({})'.format(self.user.get_full_name(), self.slot_type.name, self.start)        
    
    def is_delivery(self):
        return self.slot_type == TimeSlotType.get_builtin_object(DefaultTimeSlotTypes.DELIVERY)
    
    def get_schedule_title(self):
        if self.is_delivery():
            return str(self)
        else:
            return self.slot_type.name
    

    def get_schedule_slot_colour(self):
        if not self.phase:
            # If no phase attached... always confirmed ;)
            return "#378006"
        else:
            if self.is_confirmed():
                return "#FFC7CE" if self.is_onsite else "#bdb3ff"
            else:
                return "#E6B9B8" if self.is_onsite else "#95B3D7"
    
    
    def get_schedule_json(self, url=None):
        if not url:
            url = self.get_target_url()
                        
        data = {
            "id": self.pk,
            "title": self.get_schedule_title(),
            "resourceId": self.user.pk,
            "start": self.start,
            "end": self.end,
            "slot_type_ID": self.slot_type.pk,
            "slot_type_name": self.slot_type.name,
            "url": url,
            "userId": self.user.pk,
            "color": self.get_schedule_slot_colour(),
        }
        if self.phase:
            data['deliveryRole'] = self.deliveryRole
            data['phaseId'] = self.phase.pk
            data['editURL'] = reverse('change_job_schedule_slot', kwargs={"slug":self.phase.job.slug, "pk":self.pk})
        return data
    

    def get_business_hours(self):
        unit='hour'
        org = self.user.unit_memberships.first()
        if org:
            hours = businessDuration(self.start, self.end, unit=unit,
                                     starttime=org.unit.businessHours_startTime,
                                     endtime=org.unit.businessHours_endTime)
        else:
            hours = businessDuration(self.start, self.end, unit=unit)
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
    

    def get_target_url(self):
        if self.is_delivery() and self.phase:
            return self.phase.get_absolute_url()
        # Eventually return more useful URLs... but for now, return home.
        return ext_reverse(reverse('home'))
    
        
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
        if self.phase and self.phase.status == PhaseStatuses.PENDING_SCHED:
            # lets move to scheduled tentative!
            if self.phase.can_to_sched_tentative():
                self.phase.to_sched_tentative()
                self.phase.save()