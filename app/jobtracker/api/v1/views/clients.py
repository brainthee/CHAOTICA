"""Clients."""

from guardian.shortcuts import get_objects_for_user



from ....models import (
    Client,
)
from ..base import BaseReadOnlyAPIViewSet
from ..serializers import (
    ClientSerializer,
)


# ---------------------------------------------------------------------------
# Foundation / coherence entities
# ---------------------------------------------------------------------------


class ClientViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = ClientSerializer

    def get_base_queryset(self):
        return Client.objects.prefetch_related(
            "account_managers", "tech_account_managers"
        )

    def scope_queryset(self, queryset, user):
        allowed = get_objects_for_user(user, "jobtracker.view_client", klass=Client)
        return queryset.filter(pk__in=allowed.values_list("pk", flat=True))
