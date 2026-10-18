"""Connected Apps: registering OAuth2 clients (Settings) and a person's own
app access (profile)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template import loader
from django.urls import reverse
from guardian.decorators import permission_required_or_403
from oauth2_provider.models import get_access_token_model, get_application_model

from ..audit import record_audit
from ..forms.connected_apps import ConnectedAppForm
from ..models import AuditCategory, AuditVerb
from ..oauth import revoke_user_tokens

Application = get_application_model()
AccessToken = get_access_token_model()

SETTINGS_ANCHOR = "#connected-apps"
PROFILE_ANCHOR = "#connected-apps"


def connected_apps():
    """Registered apps for the Settings card, with active-token counts."""
    from django.db.models import Count, Q
    from django.utils import timezone

    return Application.objects.annotate(
        active_tokens=Count("accesstoken", filter=Q(accesstoken__expires__gt=timezone.now()))
    ).order_by("name")


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
        app.delete()  # cascades its tokens and grants
        messages.info(request, f"Connected app '{name}' removed; its sign-ins ended.")
        _done(data, reverse("app_settings") + SETTINGS_ANCHOR)
    return _modal(request, "modals/connected_app_delete.html", {"app": app}, data)


def own_connected_apps(user):
    """Apps the user has signed in to, with when their access lasts until."""
    from django.utils import timezone

    rows = (
        AccessToken.objects.filter(user=user, expires__gt=timezone.now())
        .values("application_id", "application__name")
        .annotate(last_expires=Max("expires"))
        .order_by("application__name")
    )
    return list(rows)


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
