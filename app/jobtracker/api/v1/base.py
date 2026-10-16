import datetime

from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from .pagination import StandardResultsPagination
from .permissions import MaintenanceModePermission


class ApiV1Mixin:
    """Behaviour shared by every /api/v1/ view (viewsets and plain views).

    - maintenance mode answers 503 (after authentication, so superusers pass);
    - anon/user throttles;
    - output is always UTC: the session middleware activates the user's
      timezone, token callers get none, and clients should not have to care
      which — they localise with the ``/me/`` timezone.
    """

    permission_classes = [MaintenanceModePermission, permissions.IsAuthenticated]
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    def initial(self, request, *args, **kwargs):
        timezone.activate(datetime.timezone.utc)
        super().initial(request, *args, **kwargs)


class BaseReadOnlyAPIViewSet(ApiV1Mixin, viewsets.ModelViewSet):
    """Shared base for every ``/api/v1/`` endpoint.

    Read-only *today* — ``http_method_names`` is restricted to safe verbs — but it
    subclasses ``ModelViewSet`` (not ``ReadOnlyModelViewSet``) on purpose: enabling
    writes later is a localised change (widen ``http_method_names``, point at a
    write-capable serializer, add an object-level permission class) rather than a
    rewrite.

    It also *locally* overrides the global datatables renderer / pagination / filter
    defaults (see ``settings.REST_FRAMEWORK``) so v1 emits clean paginated JSON
    without affecting the legacy ``/api/`` DataTables UI endpoints.

    Subclasses provide access scoping by overriding :meth:`get_base_queryset`
    (prefetch / select_related) and :meth:`scope_queryset` (guardian / ownership
    filtering). The scoping must reproduce — never widen — the checks the existing
    Django views apply; see ``jobtracker/mixins.py`` and the model managers.
    """

    # Flip to include "post"/"put"/"patch"/"delete" when writes are added.
    http_method_names = ["get", "head", "options"]

    # Override the datatables globals from settings.REST_FRAMEWORK, per-view.
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]
    pagination_class = StandardResultsPagination

    # Deliberately empty: opt into DjangoFilterBackend / SearchFilter per view,
    # never inherit DatatablesFilterBackend.
    filter_backends = []

    # Every v1 resource is looked up by integer primary key.
    lookup_value_regex = r"[0-9]+"

    def get_queryset(self):
        return self.scope_queryset(self.get_base_queryset(), self.request.user)

    def get_base_queryset(self):
        """Unscoped queryset with any prefetch/select_related applied.

        Defaults to the viewset's declared ``queryset``. Subclasses override to add
        ``select_related``/``prefetch_related`` for the fields their serializer reads.
        """
        return super().get_queryset()

    def scope_queryset(self, queryset, user):
        """Apply guardian / ownership scoping.

        The base implementation is intentionally a no-op so that a subclass which
        forgets to scope will surface in review rather than silently leaking data;
        every concrete viewset overrides this.
        """
        return queryset
