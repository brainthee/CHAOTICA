"""A user's in-app notifications (the header widget and /api/v1/notifications/)."""

from .models import Notification

def notifications_for(user, unread_only=False):
    qs = Notification.objects.filter(user=user).order_by("-timestamp", "-pk")
    return qs.filter(read=False) if unread_only else qs


def unread_count(user):
    return Notification.objects.filter(user=user, read=False).count()


def set_read(user, ids, read=True):
    """Mark the user's own notifications ``ids`` read (or unread). Returns the
    number changed; ids belonging to anyone else are ignored."""
    updated = Notification.objects.filter(user=user, pk__in=ids).update(read=read)
    if updated:
        _push(user)
    return updated


def mark_all_read(user):
    updated = Notification.objects.filter(user=user, read=False).update(read=True)
    if updated:
        _push(user)
    return updated


def _push(user):
    """Refresh the user's badge in their other open tabs (ws/me/)."""
    from django.db import transaction

    from chaotica_utils.realtime import push_unread_changed

    transaction.on_commit(lambda: push_unread_changed([user.pk]))


def serialize_notification(n):
    """The dict shape both the widget and the API return."""
    return {
        "id": n.id,
        "type": n.notification_type,
        "type_display": n.get_notification_type_display(),
        "timestamp": n.timestamp.isoformat(),
        "timestamp_human": n.get_human_timestamp(),
        "title": n.title,
        "message": n.message,
        "link": n.link,
        "read": n.read,
        "entity_type": n.entity_type,
        "entity_id": n.entity_id,
        "metadata": n.metadata,
    }


def parse_positive_int(value, default):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default
