"""Ending OAuth2 access: revoking a person's app tokens."""

from django.db import transaction


def revoke_user_tokens(user, application=None):
    """Revoke ``user``'s OAuth2 tokens (for one ``application``, or all).
    Returns the number of access tokens removed. Also drops their live
    sockets opened with those apps (see ``chaotica_utils.realtime``)."""
    from oauth2_provider.models import AccessToken, RefreshToken

    refresh = RefreshToken.objects.filter(user=user, revoked__isnull=True)
    access = AccessToken.objects.filter(user=user)
    if application is not None:
        refresh = refresh.filter(application=application)
        access = access.filter(application=application)
    count = access.count()
    with transaction.atomic():
        for token in refresh:
            token.revoke()  # also deletes its access token
        access.delete()
    if count:
        from .realtime import disconnect_user

        transaction.on_commit(lambda: disconnect_user(user.pk, ticket_only=True))
    return count
