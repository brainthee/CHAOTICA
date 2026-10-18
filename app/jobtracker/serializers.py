from chaotica_utils.models import Group, User, Note
from .models import Job, OrganisationalUnit, Client
from rest_framework import serializers
from django.utils.html import format_html
from django.template import loader


class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']


class NoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Note
        fields = ['create_date', 'content', 'author', 'is_system_note', 'content_type']


class OrganisationalUnitSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = OrganisationalUnit
        fields = ['name']

