"""Clients, contacts and framework agreements."""

from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action

from ....models import Client, Contact, FrameworkAgreement, Job
from ..base import BaseReadOnlyAPIViewSet
from ..serializers import (
    ClientDetailSerializer,
    ClientSerializer,
    ContactSerializer,
    FrameworkDetailSerializer,
    FrameworkSerializer,
    JobSerializer,
)


class ClientViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = ClientSerializer
    policy_scope = "client.view"
    ordering_fields = ("name",)
    search_fields = ("name",)

    def get_serializer_class(self):
        return ClientDetailSerializer if self.action == "retrieve" else ClientSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "policy": self.policy}

    def get_base_queryset(self):
        qs = Client.objects.prefetch_related(
            "account_managers", "tech_account_managers"
        )
        if self.action == "retrieve":
            qs = qs.prefetch_related("contacts", "framework_agreements__client")
        return qs

    def _sub_list(self, queryset, serializer_class):
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(
            serializer_class(
                page, many=True, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(responses=JobSerializer(many=True), summary="A client's jobs")
    @action(detail=True, methods=["get"], filter_backends=[])
    def jobs(self, request, pk=None):
        client = self.get_object()
        jobs = self.policy.scope(
            "job.view",
            Job.objects.filter(client=client).select_related(
                "unit", "client", "account_manager"
            ),
        ).order_by("-pk")
        return self._sub_list(jobs, JobSerializer)

    @extend_schema(
        responses=ContactSerializer(many=True), summary="A client's contacts"
    )
    @action(detail=True, methods=["get"], filter_backends=[])
    def contacts(self, request, pk=None):
        client = self.get_object()
        contacts = self.policy.scope(
            "contact.view", client.contacts.select_related("company")
        ).order_by("last_name", "first_name")
        return self._sub_list(contacts, ContactSerializer)

    @extend_schema(
        responses=FrameworkSerializer(many=True), summary="A client's frameworks"
    )
    @action(detail=True, methods=["get"], filter_backends=[])
    def frameworks(self, request, pk=None):
        client = self.get_object()
        frameworks = self.policy.scope(
            "framework.view", client.framework_agreements.select_related("client")
        ).order_by("-start_date")
        return self._sub_list(frameworks, FrameworkSerializer)


class ContactViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = ContactSerializer
    policy_scope = "contact.view"
    ordering_fields = ("last_name", "first_name")
    search_fields = ("first_name", "last_name", "email")

    def get_base_queryset(self):
        return Contact.objects.select_related("company")


class FrameworkViewSet(BaseReadOnlyAPIViewSet):
    serializer_class = FrameworkSerializer
    policy_scope = "framework.view"
    ordering_fields = ("name", "start_date", "end_date")
    search_fields = ("name",)

    def get_serializer_class(self):
        return (
            FrameworkDetailSerializer
            if self.action == "retrieve"
            else FrameworkSerializer
        )

    def get_base_queryset(self):
        return FrameworkAgreement.objects.select_related("client")
