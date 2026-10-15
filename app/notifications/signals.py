from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from jobtracker.models import Job, Phase, ClientOnboarding, Client
from jobtracker.enums import JobStatuses, PhaseStatuses
from chaotica_utils.models import LeaveRequest, User
from notifications.enums import NotificationTypes
from .utils import auto_subscribe_users


@receiver(pre_save, sender=User)
def note_leave_routing_change(sender, instance, **kwargs):
    """Flag a change to who approves this person's leave (or, if they manage
    anyone, whether they still can) so post_save can move the subscriptions."""
    instance._leave_routing_changed = False
    instance._active_changed = False
    if not instance.pk:
        return
    old = (
        User.objects.filter(pk=instance.pk)
        .values("manager_id", "acting_manager_id", "is_active")
        .first()
    )
    if old is None:
        return
    instance._leave_routing_changed = (
        old["manager_id"] != instance.manager_id
        or old["acting_manager_id"] != instance.acting_manager_id
    )
    instance._active_changed = old["is_active"] != instance.is_active


@receiver(post_save, sender=User)
def update_subscriptions_on_manager_change(sender, instance, created, **kwargs):
    from django.db.models import Q
    from notifications.utils import resync_leave_subscriptions

    if getattr(instance, "_leave_routing_changed", False):
        resync_leave_subscriptions(instance)
    if getattr(instance, "_active_changed", False):
        # A manager was (de)activated: their reports' requests re-route.
        for report in User.objects.filter(
            Q(manager=instance) | Q(acting_manager=instance)
        ):
            resync_leave_subscriptions(report)


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
    # A deleted job had its subscriptions removed by to_delete(); the save()
    # that follows must not add them back.
    if instance.status == JobStatuses.DELETED:
        return
    for eventType, eventCat in NotificationTypes.CATEGORIES.items():
        if eventCat == "Job":
            if created and eventType == NotificationTypes.JOB_CREATED:
                auto_subscribe_users(NotificationTypes.JOB_CREATED, instance)
            else:
                auto_subscribe_users(eventType, instance)

@receiver(post_save, sender=Phase)
def phase_post_save_handler(sender, instance, created, **kwargs):
    # As above: don't re-subscribe users to a deleted phase.
    if instance.status == PhaseStatuses.DELETED:
        return
    for eventType, eventCat in NotificationTypes.CATEGORIES.items():
        if eventCat == "Phase":
            if created and eventType == NotificationTypes.PHASE_CREATED:
                auto_subscribe_users(NotificationTypes.PHASE_CREATED, instance)
            else:
                auto_subscribe_users(eventType, instance)
