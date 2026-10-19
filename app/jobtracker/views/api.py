from chaotica_utils.models import User
from django.db.models import Q, Prefetch, Max, Min, Count
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
    http_method_names = ["get", "head"]

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
    http_method_names = ["get", "head"]

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
    http_method_names = ["get", "head"]

    def get_queryset(self):
        queryset = get_objects_for_user(
            self.request.user,
            "jobtracker.view_organisationalunit",
            klass=OrganisationalUnit,
        )
        return queryset

