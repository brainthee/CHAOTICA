from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from reporting.models import (
    DataArea, DataField, FieldType, DataSource, RelationshipType
)

from chaotica_utils.models import User
from jobtracker.models import (
    Job, Phase, Project, Client, Team, OrganisationalUnit, 
    TimeSlot, Skill, Service
)


class Command(BaseCommand):
    help = 'Setup model-specific data areas for the Report Builder application'

    def handle(self, *args, **options):
        self.stdout.write('Setting up Report Builder model data areas...')
        
        # Use transaction to ensure all-or-nothing
        with transaction.atomic():
            # Setup data areas for main models
            self.setup_user_data_area()
            self.setup_job_data_area()
            self.setup_phase_data_area()
            self.setup_project_data_area()
            self.setup_client_data_area()
            
            # Setup data area relationships
            self.setup_data_sources()
            
        self.stdout.write(self.style.SUCCESS('Report Builder model data setup complete!'))

    def setup_user_data_area(self):
        """Set up User data area and fields"""
        self.stdout.write('Setting up User data area...')
        
        # Get model content type
        content_type = ContentType.objects.get_for_model(User)
        
        # Create data area
        data_area, created = DataArea.objects.get_or_create(
            name='Users',
            defaults={
                'description': 'User accounts and related information',
                'content_type': content_type,
                'model_name': 'User',
                'default_sort_field': 'last_name',
                'icon_class': 'fa-users',
                'population_options': {
                    'active': {'label': 'Active Users Only'},
                    'inactive': {'label': 'Inactive Users Only'},
                    'staff': {'label': 'Staff Users Only'},
                    'superuser': {'label': 'Superusers Only'},
                }
            }
        )
        
        # Only create fields if this is a new data area
        if not created:
            self.stdout.write(f"  Data area 'Users' already exists, skipping field creation")
            return
        
        # Get field types
        text_type = FieldType.objects.get(name='Text')
        boolean_type = FieldType.objects.get(name='Boolean')
        date_type = FieldType.objects.get(name='Date')
        datetime_type = FieldType.objects.get(name='DateTime')
        email_type = FieldType.objects.get(name='Email')
        foreign_key_type = FieldType.objects.get(name='Foreign Key')
        integer_type = FieldType.objects.get(name='Integer')
        
        # Define fields
        fields = [
            {
                'name': 'id',
                'display_name': 'ID',
                'field_path': 'id',
                'field_type': integer_type,
                'group': 'Basic',
                'is_sensitive': False,
            },
            {
                'name': 'email',
                'display_name': 'Email Address',
                'field_path': 'email',
                'field_type': email_type,
                'group': 'Basic',
                'is_sensitive': False,
            },
            {
                'name': 'first_name',
                'display_name': 'First Name',
                'field_path': 'first_name',
                'field_type': text_type,
                'group': 'Basic',
                'is_sensitive': False,
            },
            {
                'name': 'last_name',
                'display_name': 'Last Name',
                'field_path': 'last_name',
                'field_type': text_type,
                'group': 'Basic',
                'is_sensitive': False,
            },
            {
                'name': 'is_active',
                'display_name': 'Active',
                'field_path': 'is_active',
                'field_type': boolean_type,
                'group': 'Status',
                'is_sensitive': False,
            },
            {
                'name': 'is_staff',
                'display_name': 'Staff',
                'field_path': 'is_staff',
                'field_type': boolean_type,
                'group': 'Status',
                'is_sensitive': False,
            },
            {
                'name': 'date_joined',
                'display_name': 'Date Joined',
                'field_path': 'date_joined',
                'field_type': datetime_type,
                'group': 'Dates',
                'is_sensitive': False,
            },
            {
                'name': 'last_login',
                'display_name': 'Last Login',
                'field_path': 'last_login',
                'field_type': datetime_type,
                'group': 'Dates',
                'is_sensitive': False,
            },
            {
                'name': 'manager',
                'display_name': 'Manager',
                'field_path': 'manager__last_name',
                'field_type': foreign_key_type,
                'group': 'Work',
                'is_sensitive': False,
            },
            {
                'name': 'location',
                'display_name': 'Location',
                'field_path': 'location',
                'field_type': text_type,
                'group': 'Work',
                'is_sensitive': False,
            },
            {
                'name': 'country',
                'display_name': 'Country',
                'field_path': 'country',
                'field_type': text_type,
                'group': 'Work',
                'is_sensitive': False,
            },
            {
                'name': 'job_title',
                'display_name': 'Job Title',
                'field_path': 'job_title',
                'field_type': text_type,
                'group': 'Work',
                'is_sensitive': False,
            },
            {
                'name': 'contracted_leave',
                'display_name': 'Contracted Annual Leave',
                'field_path': 'contracted_leave',
                'field_type': integer_type,
                'group': 'Leave',
                'is_sensitive': False,
            },
            {
                'name': 'phone_number',
                'display_name': 'Phone Number',
                'field_path': 'phone_number',
                'field_type': text_type,
                'group': 'Contact',
                'is_sensitive': True,
                'requires_permission': 'chaotica_utils.manage_user',
            },
        ]
        
        # Create fields
        for field_data in fields:
            DataField.objects.get_or_create(
                data_area=data_area,
                name=field_data['name'],
                defaults={
                    'display_name': field_data['display_name'],
                    'field_path': field_data['field_path'],
                    'field_type': field_data['field_type'],
                    'group': field_data['group'],
                    'is_sensitive': field_data['is_sensitive'],
                    'requires_permission': field_data.get('requires_permission'),
                }
            )
            
        self.stdout.write(f"  Created {len(fields)} fields for 'Users' data area")

    def setup_job_data_area(self):
        """Set up Job data area and fields"""
        self.stdout.write('Setting up Job data area...')
        
        # Get model content type
        content_type = ContentType.objects.get_for_model(Job)
        
        # Create data area
        data_area, created = DataArea.objects.get_or_create(
            name='Jobs',
            defaults={
                'description': 'Jobs and related information',
                'content_type': content_type,
                'model_name': 'Job',
                'default_sort_field': 'id',
                'icon_class': 'fa-briefcase',
                'population_options': {
                    'pending': {'label': 'Pending Jobs'},
                    'in_progress': {'label': 'In Progress Jobs'},
                    'completed': {'label': 'Completed Jobs'},
                    'cancelled': {'label': 'Cancelled Jobs'},
                }
            }
        )
        
        # Only create fields if this is a new data area
        if not created:
            self.stdout.write(f"  Data area 'Jobs' already exists, skipping field creation")
            return
        
        # Get field types
        text_type = FieldType.objects.get(name='Text')
        long_text_type = FieldType.objects.get(name='Long Text')
        boolean_type = FieldType.objects.get(name='Boolean')
        date_type = FieldType.objects.get(name='Date')
        datetime_type = FieldType.objects.get(name='DateTime')
        foreign_key_type = FieldType.objects.get(name='Foreign Key')
        integer_type = FieldType.objects.get(name='Integer')
        
        # Define fields
        fields = [
            {
                'name': 'id',
                'display_name': 'Job ID',
                'field_path': 'id',
                'field_type': integer_type,
                'group': 'Basic',
                'is_sensitive': False,
            },
            {
                'name': 'title',
                'display_name': 'Job Title',
                'field_path': 'title',
                'field_type': text_type,
                'group': 'Basic',
                'is_sensitive': False,
            },
            {
                'name': 'description',
                'display_name': 'Description',
                'field_path': 'description',
                'field_type': long_text_type,
                'group': 'Basic',
                'is_sensitive': False,
            },
            {
                'name': 'client',
                'display_name': 'Client',
                'field_path': 'client__name',
                'field_type': foreign_key_type,
                'group': 'Client',
                'is_sensitive': False,
            },
            {
                'name': 'unit',
                'display_name': 'Organisational Unit',
                'field_path': 'unit__name',
                'field_type': foreign_key_type,
                'group': 'Organisation',
                'is_sensitive': False,
            },
            {
                'name': 'status',
                'display_name': 'Status',
                'field_path': 'status',
                'field_type': integer_type,
                'group': 'Status',
                'is_sensitive': False,
            },
            {
                'name': 'account_manager',
                'display_name': 'Account Manager',
                'field_path': 'account_manager__last_name',
                'field_type': foreign_key_type,
                'group': 'Management',
                'is_sensitive': False,
            },
            {
                'name': 'dep_account_manager',
                'display_name': 'Deputy Account Manager',
                'field_path': 'dep_account_manager__last_name',
                'field_type': foreign_key_type,
                'group': 'Management',
                'is_sensitive': False,
            },
            {
                'name': 'created_by',
                'display_name': 'Created By',
                'field_path': 'created_by__last_name',
                'field_type': foreign_key_type,
                'group': 'Management',
                'is_sensitive': False,
            },
            {
                'name': 'created_at',
                'display_name': 'Created At',
                'field_path': 'created_at',
                'field_type': datetime_type,
                'group': 'Dates',
                'is_sensitive': False,
            },
            {
                'name': 'external_id',
                'display_name': 'External ID',
                'field_path': 'external_id',
                'field_type': text_type,
                'group': 'External',
                'is_sensitive': False,
            },
            {
                'name': 'is_restricted',
                'display_name': 'Is Restricted',
                'field_path': 'is_restricted',
                'field_type': boolean_type,
                'group': 'Status',
                'is_sensitive': False,
            },
            {
                'name': 'start_date',
                'display_name': 'Start Date',
                'field_path': '_start_date',
                'field_type': date_type,
                'group': 'Dates',
                'is_sensitive': False,
            },
            {
                'name': 'delivery_date',
                'display_name': 'Delivery Date',
                'field_path': '_delivery_date',
                'field_type': date_type,
                'group': 'Dates',
                'is_sensitive': False,
            },
        ]
        
        # Create fields
        for field_data in fields:
            DataField.objects.get_or_create(
                data_area=data_area,
                name=field_data['name'],
                defaults={
                    'display_name': field_data['display_name'],
                    'field_path': field_data['field_path'],
                    'field_type': field_data['field_type'],
                    'group': field_data['group'],
                    'is_sensitive': field_data['is_sensitive'],
                    'requires_permission': field_data.get('requires_permission'),
                }
            )
            
        self.stdout.write(f"  Created {len(fields)} fields for 'Jobs' data area")

    def setup_phase_data_area(self):
        """Set up Phase data area and fields"""
        self.stdout.write('Setting up Phase data area...')
        
        # Get model content type
        content_type = ContentType.objects.get_for_model(Phase)
        
        # Create data area
        data_area, created = DataArea.objects.get_or_create(
            name='Phases',
            defaults={
                'description': 'Job phases and related information',
                'content_type': content_type,
                'model_name': 'Phase',
                'default_sort_field': 'id',
                'icon_class': 'fa-list-check',
                'population_options': {
                    'pending': {'label': 'Pending Phases'},
                    'in_progress': {'label': 'In Progress Phases'},
                    'completed': {'label': 'Completed Phases'},
                    'cancelled': {'label': 'Cancelled Phases'},
                }
            }
        )
        
        # Only create fields if this is a new data area
        if not created:
            self.stdout.write(f"  Data area 'Phases' already exists, skipping field creation")
            return
        
        # Get field types
        text_type = FieldType.objects.get(name='Text')
        long_text_type = FieldType.objects.get(name='Long Text')
        boolean_type = FieldType.objects.get(name='Boolean')
        date_type = FieldType.objects.get(name='Date')
        datetime_type = FieldType.objects.get(name='DateTime')
        foreign_key_type = FieldType.objects.get(name='Foreign Key')
        integer_type = FieldType.objects.get(name='Integer')
        
        # Define fields
        fields = [
            {
                'name': 'id',
                'display_name': 'Phase ID',
                'field_path': 'id',
                'field_type': integer_type,
                'group': 'Basic',
                'is_sensitive': False,
            },
            {
                'name': 'name',
                'display_name': 'Phase Name',
                'field_path': 'name',
                'field_type': text_type,
                'group': 'Basic',
                'is_sensitive': False,
            },
            {
                'name': 'description',
                'display_name': 'Description',
                'field_path': 'description',
                'field_type': long_text_type,
                'group': 'Basic',
                'is_sensitive': False,
            },
            {
                'name': 'job',
                'display_name': 'Job',
                'field_path': 'job__title',
                'field_type': foreign_key_type,
                'group': 'Job',
                'is_sensitive': False,
            },
            {
                'name': 'job_client',
                'display_name': 'Client',
                'field_path': 'job__client__name',
                'field_type': foreign_key_type,
                'group': 'Job',
                'is_sensitive': False,
            },
            {
                'name': 'status',
                'display_name': 'Status',
                'field_path': 'status',
                'field_type': integer_type,
                'group': 'Status',
                'is_sensitive': False,
            },
            {
                'name': 'project_lead',
                'display_name': 'Project Lead',
                'field_path': 'project_lead__last_name',
                'field_type': foreign_key_type,
                'group': 'Resources',
                'is_sensitive': False,
            },
            {
                'name': 'report_author',
                'display_name': 'Report Author',
                'field_path': 'report_author__last_name',
                'field_type': foreign_key_type,
                'group': 'Resources',
                'is_sensitive': False,
            },
            {
                'name': 'start_date',
                'display_name': 'Start Date',
                'field_path': '_start_date',
                'field_type': date_type,
                'group': 'Dates',
                'is_sensitive': False,
            },
            {
                'name': 'delivery_date',
                'display_name': 'Delivery Date',
                'field_path': '_delivery_date',
                'field_type': date_type,
                'group': 'Dates',
                'is_sensitive': False,
            },
            {
                'name': 'is_imported',
                'display_name': 'Is Imported',
                'field_path': 'is_imported',
                'field_type': boolean_type,
                'group': 'Status',
                'is_sensitive': False,
            },
            {
                'name': 'location',
                'display_name': 'Location',
                'field_path': 'location',
                'field_type': text_type,
                'group': 'Location',
                'is_sensitive': False,
            },
            {
                'name': 'was_submitted_late_delivery',
                'display_name': 'Late Delivery',
                'field_path': 'was_submitted_late_delivery',
                'field_type': boolean_type,
                'group': 'Delivery',
                'is_sensitive': False,
            },
        ]
        
        # Create fields
        for field_data in fields:
            DataField.objects.get_or_create(
                data_area=data_area,
                name=field_data['name'],
                defaults={
                    'display_name': field_data['display_name'],
                    'field_path': field_data['field_path'],
                    'field_type': field_data['field_type'],
                    'group': field_data['group'],
                    'is_sensitive': field_data['is_sensitive'],
                    'requires_permission': field_data.get('requires_permission'),
                }
            )
            
        self.stdout.write(f"  Created {len(fields)} fields for 'Phases' data area")

    def setup_project_data_area(self):
        """Set up Project data area and fields"""
        self.stdout.write('Setting up Project data area...')
        
        # Get model content type
        content_type = ContentType.objects.get_for_model(Project)
        
        # Create data area
        data_area, created = DataArea.objects.get_or_create(
            name='Projects',
            defaults={
                'description': 'Projects and related information',
                'content_type': content_type,
                'model_name': 'Project',
                'default_sort_field': 'title',
                'icon_class': 'fa-project-diagram',
                'population_options': {
                    'pending': {'label': 'Pending Projects'},
                    'in_progress': {'label': 'In Progress Projects'},
                    'completed': {'label': 'Completed Projects'},
                }
            }
        )
        
        # Only create fields if this is a new data area
        if not created:
            self.stdout.write(f"  Data area 'Projects' already exists, skipping field creation")
            return
        
        # Get field types
        text_type = FieldType.objects.get(name='Text')
        long_text_type = FieldType.objects.get(name='Long Text')
        boolean_type = FieldType.objects.get(name='Boolean')
        date_type = FieldType.objects.get(name='Date')
        datetime_type = FieldType.objects.get(name='DateTime')
        foreign_key_type = FieldType.objects.get(name='Foreign Key')
        integer_type = FieldType.objects.get(name='Integer')
        
        # Define fields
        fields = [
            {
                'name': 'id',
                'display_name': 'Project ID',
                'field_path': 'id',
                'field_type': integer_type,
                'group': 'Basic',
                'is_sensitive': False,
            },
            {
                'name': 'title',
                'display_name': 'Project Title',
                'field_path': 'title',
                'field_type': text_type,
                'group': 'Basic',
                'is_sensitive': False,
            },
            {
                'name': 'status',
                'display_name': 'Status',
                'field_path': 'status',
                'field_type': integer_type,
                'group': 'Status',
                'is_sensitive': False,
            },
            {
                'name': 'created_by',
                'display_name': 'Created By',
                'field_path': 'created_by__last_name',
                'field_type': foreign_key_type,
                'group': 'Management',
                'is_sensitive': False,
            },
            {
                'name': 'created_at',
                'display_name': 'Created At',
                'field_path': 'created_at',
                'field_type': datetime_type,
                'group': 'Dates',
                'is_sensitive': False,
            },
            {
                'name': 'primary_poc',
                'display_name': 'Primary POC',
                'field_path': 'primary_poc__last_name',
                'field_type': foreign_key_type,
                'group': 'Management',
                'is_sensitive': False,
            },
            {
                'name': 'external_id',
                'display_name': 'External ID',
                'field_path': 'external_id',
                'field_type': text_type,
                'group': 'External',
                'is_sensitive': False,
            },
        ]
        
        # Create fields
        for field_data in fields:
            DataField.objects.get_or_create(
                data_area=data_area,
                name=field_data['name'],
                defaults={
                    'display_name': field_data['display_name'],
                    'field_path': field_data['field_path'],
                    'field_type': field_data['field_type'],
                    'group': field_data['group'],
                    'is_sensitive': field_data['is_sensitive'],
                    'requires_permission': field_data.get('requires_permission'),
                }
            )
            
        self.stdout.write(f"  Created {len(fields)} fields for 'Projects' data area")

    def setup_client_data_area(self):
        """Set up Client data area and fields"""
        self.stdout.write('Setting up Client data area...')
        
        # Get model content type
        content_type = ContentType.objects.get_for_model(Client)
        
        # Create data area
        data_area, created = DataArea.objects.get_or_create(
            name='Clients',
            defaults={
                'description': 'Clients and related information',
                'content_type': content_type,
                'model_name': 'Client',
                'default_sort_field': 'name',
                'icon_class': 'fa-building',
                'population_options': {}
            }
        )
        
        # Only create fields if this is a new data area
        if not created:
            self.stdout.write(f"  Data area 'Clients' already exists, skipping field creation")
            return
        
        # Get field types
        text_type = FieldType.objects.get(name='Text')
        long_text_type = FieldType.objects.get(name='Long Text')
        boolean_type = FieldType.objects.get(name='Boolean')
        email_type = FieldType.objects.get(name='Email')
        foreign_key_type = FieldType.objects.get(name='Foreign Key')
        
        # Define fields
        fields = [
            {
                'name': 'id',
                'display_name': 'Client ID',
                'field_path': 'id',
                'field_type': foreign_key_type,
                'group': 'Basic',
                'is_sensitive': False,
            },
            {
                'name': 'name',
                'display_name': 'Client Name',
                'field_path': 'name',
                'field_type': text_type,
                'group': 'Basic',
                'is_sensitive': False,
            },
            {
                'name': 'short_name',
                'display_name': 'Short Name',
                'field_path': 'short_name',
                'field_type': text_type,
                'group': 'Basic',
                'is_sensitive': False,
            },
            {
                'name': 'onboarding_required',
                'display_name': 'Onboarding Required',
                'field_path': 'onboarding_required',
                'field_type': boolean_type,
                'group': 'Onboarding',
                'is_sensitive': False,
            },
            {
                'name': 'onboarding_requirements',
                'display_name': 'Onboarding Requirements',
                'field_path': 'onboarding_requirements',
                'field_type': long_text_type,
                'group': 'Onboarding',
                'is_sensitive': False,
            },
        ]
        
        # Create fields
        for field_data in fields:
            DataField.objects.get_or_create(
                data_area=data_area,
                name=field_data['name'],
                defaults={
                    'display_name': field_data['display_name'],
                    'field_path': field_data['field_path'],
                    'field_type': field_data['field_type'],
                    'group': field_data['group'],
                    'is_sensitive': field_data['is_sensitive'],
                    'requires_permission': field_data.get('requires_permission'),
                }
            )
            
        self.stdout.write(f"  Created {len(fields)} fields for 'Clients' data area")

    def setup_data_sources(self):
        """Set up relationships between data areas"""
        self.stdout.write('Setting up data source relationships...')
        
        # Get relationship types
        one_to_many = RelationshipType.objects.get(name='One-to-Many')
        many_to_one = RelationshipType.objects.get(name='Many-to-One')
        
        # Get data areas
        try:
            users_area = DataArea.objects.get(name='Users')
            jobs_area = DataArea.objects.get(name='Jobs')
            phases_area = DataArea.objects.get(name='Phases')
            projects_area = DataArea.objects.get(name='Projects')
            clients_area = DataArea.objects.get(name='Clients')
            
            # Define relationships
            relationships = [
                {
                    'from_area': jobs_area,
                    'to_area': phases_area,
                    'relationship_type': one_to_many,
                    'join_field': 'job',
                    'display_name': 'Job Phases',
                },
                {
                    'from_area': jobs_area,
                    'to_area': clients_area,
                    'relationship_type': many_to_one,
                    'join_field': 'client',
                    'display_name': 'Job Client',
                },
                {
                    'from_area': phases_area,
                    'to_area': jobs_area,
                    'relationship_type': many_to_one,
                    'join_field': 'job',
                    'display_name': 'Phase Job',
                },
                {
                    'from_area': phases_area,
                    'to_area': users_area,
                    'relationship_type': many_to_one,
                    'join_field': 'project_lead',
                    'display_name': 'Phase Project Lead',
                },
                {
                    'from_area': projects_area,
                    'to_area': users_area,
                    'relationship_type': many_to_one,
                    'join_field': 'primary_poc',
                    'display_name': 'Project POC',
                },
            ]
            
            # Create relationships
            for rel_data in relationships:
                DataSource.objects.get_or_create(
                    from_area=rel_data['from_area'],
                    to_area=rel_data['to_area'],
                    join_field=rel_data['join_field'],
                    defaults={
                        'relationship_type': rel_data['relationship_type'],
                        'display_name': rel_data['display_name'],
                    }
                )
                
            self.stdout.write(f"  Created {len(relationships)} data source relationships")
            
        except DataArea.DoesNotExist as e:
            self.stdout.write(self.style.WARNING(f"Skipping data source setup: {e}"))