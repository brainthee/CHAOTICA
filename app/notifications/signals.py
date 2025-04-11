from django.db.models.signals import post_save
from django.dispatch import receiver
from jobtracker.models import Job, Phase
from chaotica_utils.models import LeaveRequest
from notifications.enums import NotificationTypes
from .utils import auto_subscribe_users


@receiver(post_save, sender=LeaveRequest)
def leave_post_save_handler(sender, instance, created, **kwargs):
    """Signal handler for job creation and updates"""
    if created:
        auto_subscribe_users(NotificationTypes.LEAVE_SUBMITTED, instance)
        
    auto_subscribe_users(NotificationTypes.LEAVE_APPROVED, instance)
    auto_subscribe_users(NotificationTypes.LEAVE_REJECTED, instance)
    auto_subscribe_users(NotificationTypes.LEAVE_CANCELLED, instance)


@receiver(post_save, sender=Job)
def job_post_save_handler(sender, instance, created, **kwargs):
    """Signal handler for job creation and updates"""
    if created:
        auto_subscribe_users(NotificationTypes.JOB_CREATED, instance)
        
    auto_subscribe_users(NotificationTypes.JOB_STATUS_CHANGE, instance)


@receiver(post_save, sender=Phase)
def phase_post_save_handler(sender, instance, created, **kwargs):
    """Signal handler for phase creation and updates"""
    if created:
        # Auto-subscribe users to notifications for this phase
        auto_subscribe_users(NotificationTypes.PHASE_STATUS_CHANGE, instance)
    else:
        auto_subscribe_users(NotificationTypes.PHASE_STATUS_CHANGE, instance)
        auto_subscribe_users(NotificationTypes.PHASE_LATE_TO_TQA, instance)
        auto_subscribe_users(NotificationTypes.PHASE_LATE_TO_PQA, instance)
        auto_subscribe_users(NotificationTypes.PHASE_LATE_TO_DELIVERY, instance)