from chaotica_utils.models import User
from django.db.models import Q
from guardian.shortcuts import get_objects_for_user
from ..models import Job, OrganisationalUnit, Client
from ..enums import JobStatuses
from rest_framework import permissions, viewsets
from django_filters.rest_framework import DjangoFilterBackend
from ..serializers import *


class UserViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'head']

    def get_queryset(self):
        queryset = get_objects_for_user(
            self.request.user, "chaotica_utils.view_user", klass=User
        )
        return queryset


class OrganisationalUnitViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """
    serializer_class = OrganisationalUnitSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'head']

    def get_queryset(self):
        queryset = get_objects_for_user(
            self.request.user, "jobtracker.view_organisationalunit", klass=OrganisationalUnit
        )
        return queryset


class ClientViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'head']
    filter_backends = [DjangoFilterBackend]
    search_fields = ['name']

    def get_queryset(self):
        queryset = get_objects_for_user(
            self.request.user, "jobtracker.view_client", klass=Client
        )
        return queryset


class JobViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows groups to be viewed or edited.
    """
    serializer_class = JobSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'head']
    filter_backends = [DjangoFilterBackend]
    search_fields = ['title', 'client__name']
    filterset_fields = ['status']


    def get_queryset(self):
        units = get_objects_for_user(
            self.request.user, "jobtracker.can_view_jobs", klass=OrganisationalUnit
        )
        queryset = (
            Job.objects.filter(Q(unit__in=units))
            .exclude(status=JobStatuses.DELETED)
            .exclude(status=JobStatuses.ARCHIVED)
        )
        return queryset