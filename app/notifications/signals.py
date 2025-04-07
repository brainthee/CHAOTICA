from django.db.models.signals import post_save
from django.dispatch import receiver
from jobtracker.models import Job, Phase
from notifications.enums import NotificationTypes
from .utils import auto_subscribe_users


# @receiver(post_save, sender=Job)
# def job_post_save_handler(sender, instance, created, **kwargs):
#     """Signal handler for job creation and updates"""
#     if created:
#         # Auto-subscribe users to notifications for this job
#         auto_subscribe_users(NotificationTypes.JOB_STATUS_CHANGE, instance)
#         auto_subscribe_users(NotificationTypes.JOB_CREATED, instance)
#     else:
#         # For updates, we may want to check if certain fields changed
#         # that would warrant re-triggering subscriptions
#         if instance.tracker.has_changed('status'):
#             auto_subscribe_users(NotificationTypes.JOB_STATUS_CHANGE, instance)


# @receiver(post_save, sender=Phase)
# def phase_post_save_handler(sender, instance, created, **kwargs):
#     """Signal handler for phase creation and updates"""
#     if created:
#         # Auto-subscribe users to notifications for this phase
#         auto_subscribe_users(NotificationTypes.PHASE_STATUS_CHANGE, instance)
#     else:
#         # For updates, check if relevant fields changed
#         if instance.tracker.has_changed('status'):
#             auto_subscribe_users(NotificationTypes.PHASE_STATUS_CHANGE, instance)
        
#         # Handle other phase-specific notification types
#         if instance.tracker.has_changed('_due_to_techqa'):
#             auto_subscribe_users(NotificationTypes.PHASE_LATE_TO_TQA, instance)
        
#         if instance.tracker.has_changed('_due_to_presqa'):
#             auto_subscribe_users(NotificationTypes.PHASE_LATE_TO_PQA, instance)
        
#         if instance.tracker.has_changed('_delivery_date'):
#             auto_subscribe_users(NotificationTypes.PHASE_LATE_TO_DELIVERY, instance)