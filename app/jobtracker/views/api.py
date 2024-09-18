from chaotica_utils.models import User
from django.db.models import Q
from guardian.shortcuts import get_objects_for_user
from ..models import Job, OrganisationalUnit, Client
from ..enums import JobStatuses
from rest_framework import permissions, viewsets, filters
from ..serializers import *
# from django_filters.rest_framework import DjangoFilterBackend
from rest_framework_datatables.django_filters.backends import DatatablesFilterBackend

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
    
class NoteViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """
    serializer_class = NoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'head']

    def get_queryset(self):
        if self.request.user.is_superuser:
            queryset = Note.objects.all()
        else:
            queryset = Note.objects.none()
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
    # filterset_fields = ['name',]
    # filter_backends = [DatatablesFilterBackend]

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
    # filterset_fields = ['status', 'client', 'unit']
    # filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    # filter_backends = [DatatablesFilterBackend]
    # search_fields = ['title', 'client__name', 'unit__name']


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