"""Connected Apps: registering OAuth2 clients (Settings) and a person's own
app access (profile)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template import loader
from django.urls import reverse
from guardian.decorators import permission_required_or_403
from oauth2_provider.models import (
    get_access_token_model,
    get_application_model,
    get_refresh_token_model,
)

from ..audit import record_audit
from ..forms.connected_apps import ConnectedAppForm
from ..models import AuditCategory, AuditVerb
from ..oauth import application_holders, revoke_user_tokens
from ..realtime import disconnect_user

Application = get_application_model()
AccessToken = get_access_token_model()
RefreshToken = get_refresh_token_model()

SETTINGS_ANCHOR = "#connected-apps"
PROFILE_ANCHOR = "#connected-apps"


def _live_sign_ins(**filters):
    """``(application_id, user_id, until)`` for every sign-in that can still
    reach the API: a live access token, or an unrevoked refresh token the app
    can still redeem (which outlives the access token by weeks)."""
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    now = timezone.now()
    lifetime = timedelta(seconds=settings.OAUTH2_PROVIDER["REFRESH_TOKEN_EXPIRE_SECONDS"])
    rows = [
        (a, u, exp)
        for a, u, exp in AccessToken.objects.filter(
            expires__gt=now, **filters
        ).values_list("application_id", "user_id", "expires")
    ]
    rows += [
        (a, u, created + lifetime)
        for a, u, created in RefreshToken.objects.filter(
            revoked__isnull=True, created__gt=now - lifetime, **filters
        ).values_list("application_id", "user_id", "created")
    ]
    return rows


def connected_apps():
    """Registered apps for the Settings card, with how many people are signed
    in to each."""
    people = {}
    for app_id, user_id, _until in _live_sign_ins():
        people.setdefault(app_id, set()).add(user_id)
    apps = list(Application.objects.order_by("name"))
    for app in apps:
        app.active_tokens = len(people.get(app.pk, ()))
    return apps


def _modal(request, template, context, data=None):
    data = data or {"form_is_valid": False}
    data["html_form"] = loader.render_to_string(template, context, request=request)
    return JsonResponse(data)


def _done(data, anchor_url):
    data["form_is_valid"] = True
    data["next"] = anchor_url
    return data


@permission_required_or_403("chaotica_utils.manage_site_settings")
def connected_app_form(request, pk=None):
    app = get_object_or_404(Application, pk=pk) if pk else None
    data = {"form_is_valid": False}
    form = ConnectedAppForm(request.POST or None, instance=app)
    if request.method == "POST" and form.is_valid():
        if app is None:
            form.instance.user = request.user
        app = form.save()
        messages.success(request, f"Connected app '{app.name}' saved.")
        _done(data, reverse("app_settings") + SETTINGS_ANCHOR)
    return _modal(request, "modals/connected_app_form.html", {"form": form, "app": app}, data)


@permission_required_or_403("chaotica_utils.manage_site_settings")
def connected_app_delete(request, pk):
    app = get_object_or_404(Application, pk=pk)
    data = {"form_is_valid": False}
    if request.method == "POST" and request.POST.get("user_action") == "approve_action":
        name = app.name
        holders = application_holders(app)
        app.delete()  # cascades its tokens and grants
        for user_pk in holders:
            disconnect_user(user_pk, ticket_only=True)
        messages.info(request, f"Connected app '{name}' removed; its sign-ins ended.")
        _done(data, reverse("app_settings") + SETTINGS_ANCHOR)
    return _modal(request, "modals/connected_app_delete.html", {"app": app}, data)


def own_connected_apps(user):
    """Apps the user has signed in to, with when their access lasts until."""
    until = {}
    for app_id, _user_id, expires in _live_sign_ins(user=user):
        until[app_id] = max(expires, until.get(app_id, expires))
    names = dict(
        Application.objects.filter(pk__in=until).values_list("pk", "name")
    )
    return sorted(
        (
            {
                "application_id": app_id,
                "application__name": names.get(app_id, ""),
                "last_expires": expires,
            }
            for app_id, expires in until.items()
        ),
        key=lambda row: row["application__name"],
    )


@login_required
def revoke_own_connected_app(request, pk):
    app = get_object_or_404(Application, pk=pk)
    data = {"form_is_valid": False}
    if request.method == "POST" and request.POST.get("user_action") == "approve_action":
        count = revoke_user_tokens(request.user, app)
        record_audit(
            request.user,
            AuditVerb.TOKEN_REVOKED,
            message=f"Disconnected app {app.name} ({count} token(s) revoked)",
            category=AuditCategory.AUTH,
            request=request,
        )
        messages.info(request, f"{app.name} disconnected.")
        _done(data, reverse("update_own_profile") + PROFILE_ANCHOR)
    return _modal(request, "modals/connected_app_revoke.html", {"app": app}, data)
