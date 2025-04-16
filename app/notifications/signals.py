from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from jobtracker.models import Job, Phase, ClientOnboarding, Client
from chaotica_utils.models import LeaveRequest, User
from notifications.enums import NotificationTypes
from .utils import auto_subscribe_users


@receiver(pre_save, sender=User)
def update_subscriptions_on_manager_change(sender, instance, **kwargs):
    if not instance.pk:
        return
    
    try:
        old_instance = User.objects.get(pk=instance.pk)
        
        # Determine effective managers (accounting for acting managers)
        old_effective_manager = old_instance.acting_manager or old_instance.manager
        new_effective_manager = instance.acting_manager or instance.manager
        
        # Only proceed if the effective manager has changed
        if old_effective_manager != new_effective_manager:
            from notifications.utils import reassign_manager_subscriptions
            reassign_manager_subscriptions(instance, old_effective_manager, new_effective_manager)
            
    except User.DoesNotExist:
        pass


@receiver(post_save, sender=ClientOnboarding)
def leave_post_save_handler(sender, instance, created, **kwargs):
    auto_subscribe_users(NotificationTypes.CLIENT_ONBOARDING_RENEWAL, instance)


@receiver(post_save, sender=LeaveRequest)
def leave_post_save_handler(sender, instance, created, **kwargs):
    for eventType, eventCat in NotificationTypes.CATEGORIES.items():
        if eventCat == "Leave":
            if created and eventType == NotificationTypes.LEAVE_SUBMITTED:
                auto_subscribe_users(NotificationTypes.LEAVE_SUBMITTED, instance)
            else:
                auto_subscribe_users(eventType, instance)
                
@receiver(post_save, sender=Job)
def job_post_save_handler(sender, instance, created, **kwargs):    
    for eventType, eventCat in NotificationTypes.CATEGORIES.items():
        if eventCat == "Job":
            if created and eventType == NotificationTypes.JOB_CREATED:
                auto_subscribe_users(NotificationTypes.JOB_CREATED, instance)
            else:
                auto_subscribe_users(eventType, instance)

@receiver(post_save, sender=Phase)
def phase_post_save_handler(sender, instance, created, **kwargs):
    for eventType, eventCat in NotificationTypes.CATEGORIES.items():
        if eventCat == "Phase":
            if created and eventType == NotificationTypes.PHASE_CREATED:
                auto_subscribe_users(NotificationTypes.PHASE_CREATED, instance)
            else:
                auto_subscribe_users(eventType, instance)
