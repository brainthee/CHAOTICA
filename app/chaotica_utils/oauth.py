"""Ending OAuth2 access: revoking a person's app tokens."""

from django.db import transaction


def revoke_user_tokens(user, application=None):
    """Revoke ``user``'s OAuth2 access (for one ``application``, or all):
    refresh and access tokens, and any authorization code not yet redeemed.
    Returns the number of tokens removed. Also drops their live sockets opened
    with app tickets (see ``chaotica_utils.realtime``)."""
    from oauth2_provider.models import AccessToken, Grant, RefreshToken

    refresh = RefreshToken.objects.filter(user=user, revoked__isnull=True)
    access = AccessToken.objects.filter(user=user)
    grants = Grant.objects.filter(user=user)
    if application is not None:
        refresh = refresh.filter(application=application)
        access = access.filter(application=application)
        grants = grants.filter(application=application)
    count = access.count() + refresh.filter(access_token__isnull=True).count()
    with transaction.atomic():
        for token in refresh:
            token.revoke()  # also deletes its access token
        access.delete()
        grants.delete()
    if count:
        from .realtime import disconnect_user

        transaction.on_commit(lambda: disconnect_user(user.pk, ticket_only=True))
    return count


def application_holders(application):
    """Pks of the people holding live tokens for ``application``."""
    from oauth2_provider.models import AccessToken, RefreshToken

    users = set(
        AccessToken.objects.filter(application=application).values_list(
            "user_id", flat=True
        )
    )
    users |= set(
        RefreshToken.objects.filter(
            application=application, revoked__isnull=True
        ).values_list("user_id", flat=True)
    )
    users.discard(None)
    return users
