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


class ClientSerializer(serializers.HyperlinkedModelSerializer):
    name_link =  serializers.SerializerMethodField()
    status_display  =  serializers.SerializerMethodField()
    jobs_count = serializers.IntegerField(source="jobs.count", read_only=True)
    ams_display  =  serializers.SerializerMethodField()
    tams_display  =  serializers.SerializerMethodField()

    def get_name_link(self, client):
         return format_html("<a class='fw-bold fs-8' href='{}'>{}</a>", client.get_absolute_url(), client.name)

    def get_status_display(self, client):
        return format_html("<span class='badge badge-phoenix badge-phoenix-{}'>{}</span>", 
                           "success" if client.is_ready_for_jobs() else "warning",
                           "Ready" if client.is_ready_for_jobs() else "Not Ready")

    def get_ams_display(self, client):
        return loader.render_to_string(
            "partials/users/user_group.html", { "users": client.account_managers.all }
        )
    
    def get_tams_display(self, client):
        return loader.render_to_string(
            "partials/users/user_group.html", { "users": client.tech_account_managers.all }
        )

    class Meta:
        model = Client
        fields = ['name', 'name_link', 'ams_display', 'tams_display', 'jobs_count', 'status_display']
        datatables_always_serialize = ('name',)


class JobSerializer(serializers.HyperlinkedModelSerializer):
    client = ClientSerializer()
    unit = OrganisationalUnitSerializer()

    title_link =  serializers.SerializerMethodField()
    unit_link =  serializers.SerializerMethodField()
    client_link =  serializers.SerializerMethodField()
    phase_count = serializers.IntegerField(source="phases.count", read_only=True)
    status_display  =  serializers.SerializerMethodField()
    DT_RowId = serializers.SerializerMethodField()
    DT_RowAttr = serializers.SerializerMethodField()

    start_date = serializers.DateField(read_only=True)
    delivery_date = serializers.DateField(read_only=True)

    def get_DT_RowId(self, job):
        return 'row_%d' % job.pk

    def get_DT_RowAttr(self, job):
        return {'data-pk': job.pk}

    def get_title_link(self, job):
        return format_html("<a class='fw-bold fs-8' href='{}'>{}</a>", job.get_absolute_url(), job.title)

    def get_status_display(self, job):
        status_display = loader.render_to_string(
            "partials/job/status_badge.html", { "job": job }
        )
        return status_display

    def get_unit_link(self, job):
        return format_html("<a class='fw-bold fs-8' href='{}'>{}</a>", job.unit.get_absolute_url(), job.unit)

    def get_client_link(self, job):
        return format_html("<a class='fw-bold fs-8' href='{}'>{}</a>", job.client.get_absolute_url(), job.client)

    class Meta:
        model = Job
        fields = [
            'DT_RowId', 'DT_RowAttr', 
            'id', 
            'unit', 
            'unit_link', 
            'status', 
            'status_display',
            'external_id', 
            'title', 
            'title_link', 
            'client', 
            'client_link', 
            'start_date',
            'delivery_date',
            'phase_count'
        ]
        datatables_always_serialize = (
            'DT_RowId', 'DT_RowAttr', 'client', 'id')