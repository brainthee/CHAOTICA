"""Clients."""

from ....models import (
    Client,
)
from ..base import BaseReadOnlyAPIViewSet
from ..serializers import (
    ClientSerializer,
)


class ClientViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = ClientSerializer
    policy_scope = "client.view"
    ordering_fields = ("name",)
    search_fields = ("name",)

    def get_base_queryset(self):
        return Client.objects.prefetch_related(
            "account_managers", "tech_account_managers"
        )
