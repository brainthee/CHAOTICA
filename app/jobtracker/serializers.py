from chaotica_utils.models import Group, User
from .models import Job, OrganisationalUnit, Client
from rest_framework import serializers
from django.utils.html import format_html
from django.template import loader


class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']


class OrganisationalUnitSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = OrganisationalUnit
        fields = ['name']


class ClientSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Client
        fields = ['name']

class JobSerializer(serializers.HyperlinkedModelSerializer):
    title_link =  serializers.SerializerMethodField()
    unit_link =  serializers.SerializerMethodField()
    client_link =  serializers.SerializerMethodField()
    phases = serializers.IntegerField(source="phases.count", read_only=True)
    status_display  =  serializers.SerializerMethodField()


    def get_title_link(self, job):
         return format_html("<a class='fw-bold fs-0' href='{}'>{}</a>", job.get_absolute_url(), job.title)

    def get_status_display(self, job):
        context = dict()
        context = { "job": job }
        status_display = loader.render_to_string(
            "partials/job/status_badge.html", context
        )
        return status_display

    def get_unit_link(self, job):
         return format_html("<a class='fw-bold fs-0' href='{}'>{}</a>", job.unit.get_absolute_url(), job.unit)

    def get_client_link(self, job):
         return format_html("<a class='fw-bold fs-0' href='{}'>{}</a>", job.client.get_absolute_url(), job.client)

    class Meta:
        model = Job
        fields = [
            'id', 
            'slug', 
            'unit', 
            'unit_link', 
            'status', 
            'status_display',
            'status_changed_date', 
            'external_id', 
            'title', 
            'title_link', 
            'desired_start_date', 
            'desired_delivery_date', 
            'client', 
            'client_link', 
            'start_date',
            'delivery_date',
            'phases'
        ]