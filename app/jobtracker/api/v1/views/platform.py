"""Platform: instance metadata, the caller's profile and preferences, search."""

from constance import config
from django.conf import settings
from django.http import Http404
from django.templatetags.static import static
from django.urls import reverse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions
from rest_framework.response import Response

from chaotica_utils.models import User
from chaotica_utils.selectors.search import site_search, resolve_goto
from chaotica_utils.selectors.users import current_user_profile

from ..base import ApiView
from ..fields import RefSerializer, make_ref
from ..schedule import (
    SCHEDULE_QUERY_PARAMS,
    build_schedule_payload,
    parse_schedule_window,
)
from ..serializers import ScheduleSerializer
from ..serializers.platform import (
    MeSerializer,
    MetaSerializer,
    PreferencesSerializer,
    RealtimeTicketSerializer,
    SearchResultsSerializer,
)

# Constance switches a client may use to match the main UI's features.
FEATURE_FLAGS = {
    "entropy_meter": "ENTROPY_METER_ENABLED",
    "calendar_feed": "CALENDAR_FEED_ENABLED",
    "calendar_family_feed": "CALENDAR_FAMILY_FEED_ENABLED",
    "registration": "REGISTRATION_ENABLED",
    "invites": "INVITE_ENABLED",
    "rm_sync": "RM_SYNC_ENABLED",
    "snow": "SNOW_ENABLED",
    "christmas_lights": "CHRISTMAS_LIGHTS_ENABLED",
    "christmas_tree": "CHRISTMAS_TREE_ENABLED",
    "konami": "KONAMI_ENABLED",
    "easter_egg_games": "EASTEREGG_GAMES_ENABLED",
}

# Search groups the API returns, in display order. Billing codes are refs
# without an API url (the API has no billing resource), for the header search.
SEARCH_GROUPS = (
    ("jobs", "Jobs"),
    ("phases", "Phases"),
    ("projects", "Projects"),
    ("clients", "Clients"),
    ("billing_codes", "Billing Codes"),
    ("users", "People"),
    ("services", "Services"),
    ("skills", "Skills"),
    ("qualifications", "Qualifications"),
)


def search_result(obj, request):
    """A ref plus what a results list shows under it."""
    from chaotica_utils.models import User as UserModel

    from ....models import Job, Phase

    out = {
        **make_ref(obj, request),
        "subtitle": None,
        "status_display": None,
        "status_colour": None,
        "image_url": None,
    }
    if isinstance(obj, (Job, Phase)):
        client = obj.client if isinstance(obj, Job) else obj.job.client
        out["subtitle"] = str(client)
        out["status_display"] = obj.get_status_display()
        out["status_colour"] = obj.status_bs_colour
    elif isinstance(obj, UserModel):
        out["subtitle"] = obj.job_title or None
        out["image_url"] = request.build_absolute_uri(obj.get_avatar_url())
    return out


class MetaView(ApiView):
    """What a client needs before signing in. Public, and answers during
    maintenance (it reports it) — so no MaintenanceModePermission."""

    permission_classes = [permissions.AllowAny]

    def finalize_response(self, request, response, *args, **kwargs):
        # Public discovery: any site may read it (no credentials, so a
        # cross-origin read is always the anonymous view), letting a client
        # check an instance before its origin is registered.
        response = super().finalize_response(request, response, *args, **kwargs)
        response.setdefault("Access-Control-Allow-Origin", "*")
        return response

    @extend_schema(responses=MetaSerializer, summary="Instance metadata")
    def get(self, request):
        absolute = request.build_absolute_uri
        ws_scheme = "wss" if request.is_secure() else "ws"
        return Response(
            {
                "name": "CHAOTICA",
                # Don't advertise the build to anonymous callers.
                "version": (
                    settings.DJANGO_VERSION if request.user.is_authenticated else None
                ),
                "api_version": "1",
                "web_base_url": absolute("/"),
                "ws_url": f"{ws_scheme}://{request.get_host()}/ws/",
                "maintenance": bool(config.MAINTENANCE_MODE),
                "features": {
                    key: bool(getattr(config, name, False))
                    for key, name in FEATURE_FLAGS.items()
                },
                "auth": {
                    "session": True,
                    "local_login": bool(config.LOCAL_LOGIN_ENABLED),
                    "sso": bool(config.ADFS_ENABLED),
                    "login_url": absolute(reverse("login")),
                    "token_url": (
                        absolute(reverse("api_v1:token"))
                        if config.LOCAL_LOGIN_ENABLED
                        else None
                    ),
                    "oauth": (
                        {
                            "authorize_url": absolute(
                                reverse("oauth2_provider:authorize")
                            ),
                            "token_url": absolute(reverse("oauth2_provider:token")),
                            "revoke_url": absolute(
                                reverse("oauth2_provider:revoke-token")
                            ),
                            "scopes": list(settings.OAUTH2_PROVIDER["SCOPES"]),
                            "pkce": "S256",
                            # Per app: from Settings → Connected Apps.
                            "client_id": None,
                        }
                        if config.API_OAUTH2_ENABLED
                        else None
                    ),
                },
                "branding": {
                    "site_name": "CHAOTICA",
                    "logo_url": absolute(static("assets/img/icons/logo.png")),
                },
            }
        )


class MeView(ApiView):
    @extend_schema(responses=MeSerializer, summary="The signed-in user")
    def get(self, request):
        profile = current_user_profile(request.user, self.policy)
        return Response(MeSerializer(profile, context={"request": request}).data)


class MePreferencesView(ApiView):
    @extend_schema(responses=PreferencesSerializer, summary="My preferences")
    def get(self, request):
        return Response(PreferencesSerializer(request.user).data)


class MeScheduleView(ApiView):
    """``/users/{me}/schedule/`` without needing the id first."""

    @extend_schema(
        parameters=SCHEDULE_QUERY_PARAMS,
        responses=ScheduleSerializer,
        summary="My schedule window",
    )
    def get(self, request):
        start, end = parse_schedule_window(request)
        users = User.objects.filter(pk=request.user.pk)
        return Response(build_schedule_payload(users, start, end, request=request))


class SearchView(ApiView):
    @extend_schema(
        parameters=[
            OpenApiParameter(
                "q", str, required=True, description="At least 3 characters."
            ),
            OpenApiParameter("limit", int, description="Per group, 1–50 (default 10)."),
        ],
        responses=SearchResultsSerializer,
        summary="Search everything",
    )
    def get(self, request):
        q = request.query_params.get("q", "")
        try:
            limit = max(1, min(50, int(request.query_params.get("limit", 10))))
        except ValueError:
            limit = 10
        found = site_search(request.user, q, limit=limit, policy=self.policy)
        groups = [
            {
                "type": key,
                "label": label,
                "results": [search_result(o, request) for o in found[key]],
            }
            for key, label in SEARCH_GROUPS
            if found.get(key)
        ]
        return Response({"q": q, "groups": groups})


class SearchGotoView(ApiView):
    @extend_schema(
        parameters=[
            OpenApiParameter(
                "id",
                str,
                required=True,
                description='Job ID ("1234") or Phase ID ("1234-1").',
            )
        ],
        responses=RefSerializer,
        summary="Jump to a job or phase by its ID",
    )
    def get(self, request):
        obj = resolve_goto(request.user, request.query_params.get("id"), self.policy)
        if obj is None:
            raise Http404
        return Response(make_ref(obj, request))


class RealtimeTicketView(ApiView):
    """A single-use, 30-second ticket for opening a WebSocket as yourself
    (``wss://…/ws/me/?ticket=…`` or a ``ws/schedule/…`` socket) — for clients
    that can't send the session cookie, e.g. OAuth2 apps."""

    @extend_schema(
        request=None, responses=RealtimeTicketSerializer, summary="WebSocket ticket"
    )
    def post(self, request):
        from chaotica_utils.realtime import TICKET_TTL_SECONDS, issue_ticket

        ws_scheme = "wss" if request.is_secure() else "ws"
        return Response(
            {
                "ticket": issue_ticket(request.user),
                "expires_in": TICKET_TTL_SECONDS,
                "ws_url": f"{ws_scheme}://{request.get_host()}/ws/",
            }
        )
