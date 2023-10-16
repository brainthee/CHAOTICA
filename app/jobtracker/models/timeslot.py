from django.db import models
from django.urls import reverse
from ..enums import TimeSlotDeliveryRole, TimeSlotType, PhaseStatuses
from ..models.phase import Phase
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from chaotica_utils.models import Note, UserCost
from chaotica_utils.utils import ext_reverse
from django.core.exceptions import ValidationError
from business_duration import businessDuration
from decimal import Decimal


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

    deliveryRole = models.IntegerField(verbose_name="Delivery Type", help_text="Type of role in job",
        choices=TimeSlotDeliveryRole.CHOICES, default=TimeSlotDeliveryRole.NA)
    is_onsite = models.BooleanField(verbose_name="Is onsite", 
        help_text="Is this slot onsite", default=False)
    
    slotType = models.IntegerField(verbose_name="Slot Type", help_text="Type of time",
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
    
    def get_schedule_phase_json(self):
        data = {
            "id": self.pk,
            "title": str(self.get_deliveryRole_display()),
            "resourceId": self.user.pk,
            "start": self.start,
            "end": self.end,
            "deliveryRole": self.deliveryRole,
            "slotType": self.slotType,
            "userId": self.user.pk,
            "phaseId": self.phase.pk,
            "color": self.slot_colour(),
        }
        if self.phase:
            data['url'] = reverse('change_job_schedule_slot', kwargs={"slug":self.phase.job.slug, "pk":self.pk})
        return data
    
    def get_business_hours(self):
        unit='hour'
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
        if self.slotType == TimeSlotType.DELIVERY and self.phase:
            return self.phase.get_absolute_url()
        # Eventually return more useful URLs... but for now, return home.
        # elif self.slotType == TimeSlotType.GENERIC:
        #     return ext_reverse(reverse('home'))
        # elif self.slotType == TimeSlotType.INTERNAL:
        #     return ext_reverse(reverse('home'))
        # elif self.slotType == TimeSlotType.LEAVE:
        #     return ext_reverse(reverse('home'))
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