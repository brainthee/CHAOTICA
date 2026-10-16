import datetime

from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, viewsets
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from ...policy import PolicyContext
from .exceptions import v1_exception_handler
from .filters import AliasOrderingFilter, QSearchFilter
from .pagination import StandardResultsPagination
from .permissions import MaintenanceModePermission, OAuth2ScopeIfBearer


def get_policy(request):
    """The request's :class:`PolicyContext`, built once and shared by every
    selector the request touches."""
    django_request = getattr(request, "_request", request)
    policy = getattr(django_request, "_chaotica_policy", None)
    if policy is None or policy.user != request.user:
        policy = PolicyContext(request.user)
        django_request._chaotica_policy = policy
    return policy


class ApiV1Mixin:
    """Behaviour shared by every /api/v1/ view (viewsets and plain views).

    - maintenance mode answers 503 (after authentication, so superusers pass);
    - OAuth2 bearer tokens need the ``read`` / ``write`` scope (A8);
    - anon/user throttles;
    - errors use the v1 envelope (``exceptions.py``);
    - output is always UTC: the session middleware activates the user's
      timezone, token callers get none, and clients should not have to care
      which — they localise with the ``/me/`` timezone.
    """

    permission_classes = [
        MaintenanceModePermission,
        permissions.IsAuthenticated,
        OAuth2ScopeIfBearer,
    ]
    throttle_classes = [AnonRateThrottle, UserRateThrottle]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]

    def initial(self, request, *args, **kwargs):
        timezone.activate(datetime.timezone.utc)
        super().initial(request, *args, **kwargs)

    def get_exception_handler(self):
        return v1_exception_handler

    @property
    def policy(self):
        return get_policy(self.request)


class ApiView(ApiV1Mixin, APIView):
    """Base for composite (non-model) endpoints, e.g. ``/me/dashboard/``."""


class BaseReadOnlyAPIViewSet(ApiV1Mixin, viewsets.ModelViewSet):
    """Shared base for every ``/api/v1/`` model endpoint.

    Read-only *today* — ``http_method_names`` is restricted to safe verbs — but it
    subclasses ``ModelViewSet`` (not ``ReadOnlyModelViewSet``) on purpose: enabling
    writes later is a localised change (widen ``http_method_names``, point at a
    write-capable serializer, add an object-level permission class) rather than a
    rewrite.

    It also *locally* overrides the global datatables renderer / pagination / filter
    defaults (see ``settings.REST_FRAMEWORK``) so v1 emits clean paginated JSON
    without affecting the legacy ``/api/`` DataTables UI endpoints.

    Access scoping: set ``policy_scope`` to a :mod:`jobtracker.policy` scope
    action (e.g. ``"job.view"``); ``None`` means reference data visible to every
    authenticated user, and must be a deliberate choice. Override
    :meth:`get_base_queryset` for select/prefetch.

    Filtering: declare ``filterset_class`` / ``ordering_fields`` /
    ``search_fields`` per view. Ordering is an allowlist — nothing is orderable
    unless listed.
    """

    # Flip to include "post"/"put"/"patch"/"delete" when writes are added.
    http_method_names = ["get", "head", "options"]

    pagination_class = StandardResultsPagination
    filter_backends = [DjangoFilterBackend, AliasOrderingFilter, QSearchFilter]
    ordering_fields = ()
    ordering = ("pk",)  # stable pagination; ?ordering= overrides

    # Every v1 resource is looked up by integer primary key.
    lookup_value_regex = r"[0-9]+"

    policy_scope = NotImplemented

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation
            return self.get_base_queryset().none()
        return self.scope_queryset(self.get_base_queryset(), self.request.user)

    def get_base_queryset(self):
        """Unscoped queryset with any prefetch/select_related applied.

        Defaults to the viewset's declared ``queryset``. Subclasses override to add
        ``select_related``/``prefetch_related`` for the fields their serializer reads.
        """
        return super().get_queryset()

    def scope_queryset(self, queryset, user):
        if self.policy_scope is NotImplemented:
            raise NotImplementedError(
                f"{type(self).__name__} must set policy_scope (or None for "
                "reference data)."
            )
        if self.policy_scope is None:
            return queryset
        return self.policy.scope(self.policy_scope, queryset)
