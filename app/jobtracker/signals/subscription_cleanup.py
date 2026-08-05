"""Clean up notification subscriptions/opt-outs when a Job or Phase is deleted.

Subscriptions and opt-outs reference their target by ``(entity_type, entity_id)``
strings, not a ForeignKey, so nothing cascades them away when the target row is
removed. The soft-delete transitions (``Job.to_delete`` / ``Phase.to_deleted``)
call ``remove_subscriptions_for_entity`` directly; these ``post_delete`` receivers
cover the hard-delete paths (admin, ``on_delete=CASCADE`` from a client/unit, or
any DeleteView) so no path leaves dangling rows behind.
"""

from django.db.models.signals import post_delete
from django.dispatch import receiver

from jobtracker.models.job import Job
from jobtracker.models.phase import Phase


@receiver(post_delete, sender=Job)
@receiver(post_delete, sender=Phase)
def cleanup_entity_subscriptions(sender, instance, **kwargs):
    # Lazy import to avoid a jobtracker → notifications import cycle at load.
    from notifications.utils import remove_subscriptions_for_entity

    remove_subscriptions_for_entity(instance)
