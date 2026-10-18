"""Per-user live channel: WebSocket tickets and pushes to ``ws/me/``.

Browsers on this site authenticate sockets with the session cookie. Other
clients (OAuth2 bearer tokens, which a browser can't attach to a WebSocket)
exchange their token for a **ticket**: single use, 30 seconds, bound to the
user (``POST /api/v1/realtime/ticket/``, then ``…/ws/…/?ticket=…``).
"""

import hashlib
import logging
import secrets

from django.core.cache import cache

logger = logging.getLogger(__name__)

TICKET_TTL_SECONDS = 30


def user_group(user_id):
    return f"user_{user_id}"


def _ticket_key(raw):
    return "ws_ticket:" + hashlib.sha256(raw.encode()).hexdigest()


def issue_ticket(user):
    raw = secrets.token_urlsafe(32)
    cache.set(_ticket_key(raw), user.pk, TICKET_TTL_SECONDS)
    return raw


def redeem_ticket(raw):
    """The user id a ticket was issued for, once; ``None`` if unknown,
    expired or already used."""
    if not raw or len(raw) > 128:
        return None
    key = _ticket_key(raw)
    user_id = cache.get(key)
    # Only the caller whose delete removed the key may use it (single use,
    # even if two connections race with the same ticket).
    if user_id is None or not cache.delete(key):
        return None
    return user_id


def _group_send(group, message):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is not None:
            async_to_sync(layer.group_send)(group, message)
    except Exception:  # realtime is best-effort; never break the caller
        logger.warning("Realtime push to %s failed", group, exc_info=True)


def push_unread_changed(user_ids):
    """Tell each user's ``ws/me/`` sockets their unread count changed."""
    for uid in set(user_ids):
        _group_send(user_group(uid), {"type": "unread.changed"})


def disconnect_user(user_id, ticket_only=False):
    """Close the user's live sockets — all of them (deactivation), or only
    those opened with an app's ticket (``ticket_only``, on app revoke)."""
    _group_send(
        user_group(user_id), {"type": "force.disconnect", "ticket_only": ticket_only}
    )
