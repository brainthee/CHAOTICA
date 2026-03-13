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

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete all existing data areas, fields, and sources then recreate from scratch. '
                 'WARNING: This will also break any existing reports that reference deleted fields.',
        )

    def handle(self, *args, **options):
        self.stdout.write('Setting up Report Builder model data areas...')

        if options['reset']:
            self.stdout.write(self.style.WARNING(
                'RESET mode: Deleting all existing data areas, fields, and sources...'
            ))
            with transaction.atomic():
                ds_count, _ = DataSource.objects.all().delete()
                df_count, _ = DataField.objects.all().delete()
                da_count, _ = DataArea.objects.all().delete()
                self.stdout.write(
                    f'  Deleted {da_count} data areas, {df_count} fields, {ds_count} sources'
                )

        # Cache field types for reuse
        self.field_types = {}
        for ft in FieldType.objects.all():
            self.field_types[ft.name] = ft

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

    def _get_or_create_data_area(self, name, defaults):
        """Get or create a data area, updating defaults if it already exists."""
        data_area, created = DataArea.objects.update_or_create(
            name=name,
            defaults=defaults
        )
        action = "Created" if created else "Updated"
        self.stdout.write(f"  {action} data area '{name}'")
        return data_area

    def _sync_fields(self, data_area, fields):
        """Create or update fields for a data area.
        Uses field_path as the unique lookup key (matches unique_together constraint).
        Disables stale fields that are no longer in the definition.
        """
        count_created = 0
        count_updated = 0
        defined_paths = set()

        for field_data in fields:
            defined_paths.add(field_data['field_path'])
            _, created = DataField.objects.update_or_create(
                data_area=data_area,
                field_path=field_data['field_path'],
                defaults={
                    'name': field_data['name'],
                    'display_name': field_data['display_name'],
                    'field_type': field_data['field_type'],
                    'group': field_data['group'],
                    'is_sensitive': field_data.get('is_sensitive', False),
                    'requires_permission': field_data.get('requires_permission'),
                    'is_available': True,
                }
            )
            if created:
                count_created += 1
            else:
                count_updated += 1

        # Disable stale fields that are no longer defined
        stale = data_area.fields.filter(is_available=True).exclude(field_path__in=defined_paths)
        count_disabled = stale.update(is_available=False)

        msg = f"  Fields for '{data_area.name}': {count_created} created, {count_updated} updated"
        if count_disabled:
            msg += f", {count_disabled} stale disabled"
        self.stdout.write(msg)

    def setup_user_data_area(self):
        """Set up User data area and fields"""
        self.stdout.write('Setting up User data area...')

        content_type = ContentType.objects.get_for_model(User)

        data_area = self._get_or_create_data_area('Users', {
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
        })

        text_type = self.field_types['Text']
        boolean_type = self.field_types['Boolean']
        datetime_type = self.field_types['DateTime']
        email_type = self.field_types['Email']
        foreign_key_type = self.field_types['Foreign Key']
        integer_type = self.field_types['Integer']

        fields = [
            {'name': 'id', 'display_name': 'ID', 'field_path': 'id', 'field_type': integer_type, 'group': 'Basic'},
            {'name': 'email', 'display_name': 'Email Address', 'field_path': 'email', 'field_type': email_type, 'group': 'Basic'},
            {'name': 'first_name', 'display_name': 'First Name', 'field_path': 'first_name', 'field_type': text_type, 'group': 'Basic'},
            {'name': 'last_name', 'display_name': 'Last Name', 'field_path': 'last_name', 'field_type': text_type, 'group': 'Basic'},
            {'name': 'is_active', 'display_name': 'Active', 'field_path': 'is_active', 'field_type': boolean_type, 'group': 'Status'},
            {'name': 'is_staff', 'display_name': 'Staff', 'field_path': 'is_staff', 'field_type': boolean_type, 'group': 'Status'},
            {'name': 'date_joined', 'display_name': 'Date Joined', 'field_path': 'date_joined', 'field_type': datetime_type, 'group': 'Dates'},
            {'name': 'last_login', 'display_name': 'Last Login', 'field_path': 'last_login', 'field_type': datetime_type, 'group': 'Dates'},
            {'name': 'manager', 'display_name': 'Manager', 'field_path': 'manager__last_name', 'field_type': foreign_key_type, 'group': 'Work'},
            {'name': 'location', 'display_name': 'Location', 'field_path': 'location', 'field_type': text_type, 'group': 'Work'},
            {'name': 'country', 'display_name': 'Country', 'field_path': 'country', 'field_type': text_type, 'group': 'Work'},
            {'name': 'job_title', 'display_name': 'Job Title', 'field_path': 'job_title', 'field_type': text_type, 'group': 'Work'},
            {'name': 'contracted_leave', 'display_name': 'Contracted Annual Leave', 'field_path': 'contracted_leave', 'field_type': integer_type, 'group': 'Leave'},
            {'name': 'phone_number', 'display_name': 'Phone Number', 'field_path': 'phone_number', 'field_type': text_type, 'group': 'Contact', 'is_sensitive': True, 'requires_permission': 'chaotica_utils.manage_user'},
        ]

        self._sync_fields(data_area, fields)

    def setup_job_data_area(self):
        """Set up Job data area and fields"""
        self.stdout.write('Setting up Job data area...')

        content_type = ContentType.objects.get_for_model(Job)

        data_area = self._get_or_create_data_area('Jobs', {
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
        })

        text_type = self.field_types['Text']
        long_text_type = self.field_types['Long Text']
        boolean_type = self.field_types['Boolean']
        date_type = self.field_types['Date']
        datetime_type = self.field_types['DateTime']
        foreign_key_type = self.field_types['Foreign Key']
        integer_type = self.field_types['Integer']
        decimal_type = self.field_types['Decimal']

        fields = [
            # Basic
            {'name': 'id', 'display_name': 'Job ID', 'field_path': 'id', 'field_type': integer_type, 'group': 'Basic'},
            {'name': 'title', 'display_name': 'Job Title', 'field_path': 'title', 'field_type': text_type, 'group': 'Basic'},
            {'name': 'description', 'display_name': 'Description', 'field_path': 'description', 'field_type': long_text_type, 'group': 'Basic'},
            {'name': 'overview', 'display_name': 'Overview', 'field_path': 'overview', 'field_type': long_text_type, 'group': 'Basic'},
            # Client
            {'name': 'client', 'display_name': 'Client', 'field_path': 'client__name', 'field_type': foreign_key_type, 'group': 'Client'},
            {'name': 'client_short_name', 'display_name': 'Client Short Name', 'field_path': 'client__short_name', 'field_type': foreign_key_type, 'group': 'Client'},
            # Organisation
            {'name': 'unit', 'display_name': 'Organisational Unit', 'field_path': 'unit__name', 'field_type': foreign_key_type, 'group': 'Organisation'},
            # Status
            {'name': 'status', 'display_name': 'Status', 'field_path': 'status', 'field_type': integer_type, 'group': 'Status'},
            {'name': 'is_restricted', 'display_name': 'Is Restricted', 'field_path': 'is_restricted', 'field_type': boolean_type, 'group': 'Status'},
            {'name': 'restricted_detail', 'display_name': 'Restricted Detail', 'field_path': 'restricted_detail', 'field_type': integer_type, 'group': 'Status'},
            # Financial
            {'name': 'revenue', 'display_name': 'Revenue', 'field_path': 'revenue', 'field_type': decimal_type, 'group': 'Financial'},
            # Management
            {'name': 'account_manager', 'display_name': 'Account Manager', 'field_path': 'account_manager__last_name', 'field_type': foreign_key_type, 'group': 'Management'},
            {'name': 'dep_account_manager', 'display_name': 'Deputy Account Manager', 'field_path': 'dep_account_manager__last_name', 'field_type': foreign_key_type, 'group': 'Management'},
            {'name': 'created_by', 'display_name': 'Created By', 'field_path': 'created_by__last_name', 'field_type': foreign_key_type, 'group': 'Management'},
            {'name': 'scoped_signed_off_by', 'display_name': 'Scoped Signed Off By', 'field_path': 'scoped_signed_off_by__last_name', 'field_type': foreign_key_type, 'group': 'Management'},
            {'name': 'primary_client_poc', 'display_name': 'Primary Client POC', 'field_path': 'primary_client_poc__full_name', 'field_type': foreign_key_type, 'group': 'Management'},
            # Dates
            {'name': 'created_at', 'display_name': 'Created At', 'field_path': 'created_at', 'field_type': datetime_type, 'group': 'Dates'},
            {'name': 'start_date', 'display_name': 'Start Date', 'field_path': '_start_date', 'field_type': date_type, 'group': 'Dates'},
            {'name': 'delivery_date', 'display_name': 'Delivery Date', 'field_path': '_delivery_date', 'field_type': date_type, 'group': 'Dates'},
            {'name': 'desired_start_date', 'display_name': 'Desired Start Date', 'field_path': 'desired_start_date', 'field_type': date_type, 'group': 'Dates'},
            {'name': 'desired_delivery_date', 'display_name': 'Desired Delivery Date', 'field_path': 'desired_delivery_date', 'field_type': date_type, 'group': 'Dates'},
            {'name': 'scoping_requested_on', 'display_name': 'Scoping Requested On', 'field_path': 'scoping_requested_on', 'field_type': datetime_type, 'group': 'Dates'},
            {'name': 'scoping_completed_date', 'display_name': 'Scoping Completed Date', 'field_path': 'scoping_completed_date', 'field_type': datetime_type, 'group': 'Dates'},
            {'name': 'status_changed_date', 'display_name': 'Status Changed Date', 'field_path': 'status_changed_date', 'field_type': datetime_type, 'group': 'Dates'},
            # Flags
            {'name': 'bespoke_project', 'display_name': 'Bespoke Project', 'field_path': 'bespoke_project', 'field_type': boolean_type, 'group': 'Flags'},
            {'name': 'report_to_third_party', 'display_name': 'Report to Third Party', 'field_path': 'report_to_third_party', 'field_type': boolean_type, 'group': 'Flags'},
            {'name': 'is_time_limited', 'display_name': 'Time Limited', 'field_path': 'is_time_limited', 'field_type': boolean_type, 'group': 'Flags'},
            {'name': 'retest_included', 'display_name': 'Retest Included', 'field_path': 'retest_included', 'field_type': boolean_type, 'group': 'Flags'},
            {'name': 'technically_complex_test', 'display_name': 'Technically Complex', 'field_path': 'technically_complex_test', 'field_type': boolean_type, 'group': 'Flags'},
            {'name': 'high_risk', 'display_name': 'High Risk', 'field_path': 'high_risk', 'field_type': boolean_type, 'group': 'Flags'},
            {'name': 'is_imported', 'display_name': 'Is Imported', 'field_path': 'is_imported', 'field_type': boolean_type, 'group': 'Flags'},
            {'name': 'additional_kit_required', 'display_name': 'Additional Kit Required', 'field_path': 'additional_kit_required', 'field_type': boolean_type, 'group': 'Flags'},
            {'name': 'kit_sourced_by_client', 'display_name': 'Kit Sourced by Client', 'field_path': 'kit_sourced_by_client', 'field_type': boolean_type, 'group': 'Flags'},
            # Framework
            {'name': 'associated_framework', 'display_name': 'Framework Agreement', 'field_path': 'associated_framework__name', 'field_type': foreign_key_type, 'group': 'Client'},
            # External
            {'name': 'external_id', 'display_name': 'External ID', 'field_path': 'external_id', 'field_type': text_type, 'group': 'External'},
        ]

        self._sync_fields(data_area, fields)

    def setup_phase_data_area(self):
        """Set up Phase data area and fields"""
        self.stdout.write('Setting up Phase data area...')

        content_type = ContentType.objects.get_for_model(Phase)

        data_area = self._get_or_create_data_area('Phases', {
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
        })

        text_type = self.field_types['Text']
        long_text_type = self.field_types['Long Text']
        boolean_type = self.field_types['Boolean']
        date_type = self.field_types['Date']
        datetime_type = self.field_types['DateTime']
        foreign_key_type = self.field_types['Foreign Key']
        integer_type = self.field_types['Integer']
        decimal_type = self.field_types['Decimal']

        fields = [
            # Basic
            {'name': 'id', 'display_name': 'Phase DB ID', 'field_path': 'id', 'field_type': integer_type, 'group': 'Basic'},
            {'name': 'phase_id', 'display_name': 'Phase ID', 'field_path': 'phase_id', 'field_type': text_type, 'group': 'Basic'},
            {'name': 'phase_number', 'display_name': 'Phase Number', 'field_path': 'phase_number', 'field_type': integer_type, 'group': 'Basic'},
            {'name': 'title', 'display_name': 'Title', 'field_path': 'title', 'field_type': text_type, 'group': 'Basic'},
            {'name': 'description', 'display_name': 'Description', 'field_path': 'description', 'field_type': long_text_type, 'group': 'Basic'},
            # Status
            {'name': 'status', 'display_name': 'Status', 'field_path': 'status', 'field_type': integer_type, 'group': 'Status'},
            {'name': 'is_imported', 'display_name': 'Is Imported', 'field_path': 'is_imported', 'field_type': boolean_type, 'group': 'Status'},
            # Job
            {'name': 'job', 'display_name': 'Job', 'field_path': 'job__title', 'field_type': foreign_key_type, 'group': 'Job'},
            {'name': 'job_id', 'display_name': 'Job ID', 'field_path': 'job__id', 'field_type': integer_type, 'group': 'Job'},
            {'name': 'job_client', 'display_name': 'Client', 'field_path': 'job__client__name', 'field_type': foreign_key_type, 'group': 'Job'},
            {'name': 'job_status', 'display_name': 'Job Status', 'field_path': 'job__status', 'field_type': integer_type, 'group': 'Job'},
            {'name': 'job_account_manager', 'display_name': 'Job Account Manager', 'field_path': 'job__account_manager__last_name', 'field_type': foreign_key_type, 'group': 'Job'},
            {'name': 'job_revenue', 'display_name': 'Job Revenue', 'field_path': 'job__revenue', 'field_type': decimal_type, 'group': 'Job'},
            {'name': 'job_unit', 'display_name': 'Job Org Unit', 'field_path': 'job__unit__name', 'field_type': foreign_key_type, 'group': 'Job'},
            {'name': 'job_framework', 'display_name': 'Job Framework Agreement', 'field_path': 'job__associated_framework__name', 'field_type': foreign_key_type, 'group': 'Job'},
            # Service
            {'name': 'service', 'display_name': 'Service', 'field_path': 'service__name', 'field_type': foreign_key_type, 'group': 'Service'},
            # Resources
            {'name': 'project_lead', 'display_name': 'Project Lead', 'field_path': 'project_lead__last_name', 'field_type': foreign_key_type, 'group': 'Resources'},
            {'name': 'report_author', 'display_name': 'Report Author', 'field_path': 'report_author__last_name', 'field_type': foreign_key_type, 'group': 'Resources'},
            {'name': 'techqa_by', 'display_name': 'Tech QA By', 'field_path': 'techqa_by__last_name', 'field_type': foreign_key_type, 'group': 'Resources'},
            {'name': 'presqa_by', 'display_name': 'Pres QA By', 'field_path': 'presqa_by__last_name', 'field_type': foreign_key_type, 'group': 'Resources'},
            {'name': 'last_modified_by', 'display_name': 'Last Modified By', 'field_path': 'last_modified_by__last_name', 'field_type': foreign_key_type, 'group': 'Resources'},
            # Scoped Hours
            {'name': 'delivery_hours', 'display_name': 'Delivery Hours', 'field_path': 'delivery_hours', 'field_type': decimal_type, 'group': 'Scoped Hours'},
            {'name': 'reporting_hours', 'display_name': 'Reporting Hours', 'field_path': 'reporting_hours', 'field_type': decimal_type, 'group': 'Scoped Hours'},
            {'name': 'mgmt_hours', 'display_name': 'Management Hours', 'field_path': 'mgmt_hours', 'field_type': decimal_type, 'group': 'Scoped Hours'},
            {'name': 'qa_hours', 'display_name': 'QA Hours', 'field_path': 'qa_hours', 'field_type': decimal_type, 'group': 'Scoped Hours'},
            {'name': 'oversight_hours', 'display_name': 'Oversight Hours', 'field_path': 'oversight_hours', 'field_type': decimal_type, 'group': 'Scoped Hours'},
            {'name': 'debrief_hours', 'display_name': 'Debrief Hours', 'field_path': 'debrief_hours', 'field_type': decimal_type, 'group': 'Scoped Hours'},
            {'name': 'contingency_hours', 'display_name': 'Contingency Hours', 'field_path': 'contingency_hours', 'field_type': decimal_type, 'group': 'Scoped Hours'},
            {'name': 'other_hours', 'display_name': 'Other Hours', 'field_path': 'other_hours', 'field_type': decimal_type, 'group': 'Scoped Hours'},
            # Phase Detail
            {'name': 'test_target', 'display_name': 'Test Target/Scope', 'field_path': 'test_target', 'field_type': long_text_type, 'group': 'Phase Detail'},
            {'name': 'comm_reqs', 'display_name': 'Communication Requirements', 'field_path': 'comm_reqs', 'field_type': long_text_type, 'group': 'Phase Detail'},
            {'name': 'restrictions', 'display_name': 'Restrictions/Special Requirements', 'field_path': 'restrictions', 'field_type': long_text_type, 'group': 'Phase Detail'},
            {'name': 'scheduling_requirements', 'display_name': 'Scheduling Requirements', 'field_path': 'scheduling_requirements', 'field_type': long_text_type, 'group': 'Phase Detail'},
            {'name': 'prerequisites', 'display_name': 'Pre-requisites', 'field_path': 'prerequisites', 'field_type': long_text_type, 'group': 'Phase Detail'},
            # Deliverable Links
            {'name': 'linkDeliverable', 'display_name': 'Link to Deliverable', 'field_path': 'linkDeliverable', 'field_type': text_type, 'group': 'Deliverables'},
            {'name': 'linkTechData', 'display_name': 'Link to Technical Data', 'field_path': 'linkTechData', 'field_type': text_type, 'group': 'Deliverables'},
            {'name': 'linkReportData', 'display_name': 'Link to Report Data', 'field_path': 'linkReportData', 'field_type': text_type, 'group': 'Deliverables'},
            # Dates
            {'name': 'start_date', 'display_name': 'Start Date', 'field_path': '_start_date', 'field_type': date_type, 'group': 'Dates'},
            {'name': 'delivery_date', 'display_name': 'Delivery Date', 'field_path': '_delivery_date', 'field_type': date_type, 'group': 'Dates'},
            {'name': 'desired_start_date', 'display_name': 'Desired Start Date', 'field_path': 'desired_start_date', 'field_type': date_type, 'group': 'Dates'},
            {'name': 'desired_delivery_date', 'display_name': 'Desired Delivery Date', 'field_path': 'desired_delivery_date', 'field_type': date_type, 'group': 'Dates'},
            {'name': 'actual_start_date', 'display_name': 'Actual Start Date', 'field_path': 'actual_start_date', 'field_type': datetime_type, 'group': 'Dates'},
            {'name': 'actual_delivery_date', 'display_name': 'Actual Delivery Date', 'field_path': 'actual_delivery_date', 'field_type': datetime_type, 'group': 'Dates'},
            {'name': 'actual_completed_date', 'display_name': 'Actual Completed Date', 'field_path': 'actual_completed_date', 'field_type': datetime_type, 'group': 'Dates'},
            {'name': 'pre_checks_done_date', 'display_name': 'Pre-checks Done Date', 'field_path': 'pre_checks_done_date', 'field_type': datetime_type, 'group': 'Dates'},
            {'name': 'created_date', 'display_name': 'Created Date', 'field_path': 'created_date', 'field_type': datetime_type, 'group': 'Dates'},
            {'name': 'last_modified', 'display_name': 'Last Modified', 'field_path': 'last_modified', 'field_type': datetime_type, 'group': 'Dates'},
            {'name': 'status_changed_date', 'display_name': 'Status Changed Date', 'field_path': 'status_changed_date', 'field_type': datetime_type, 'group': 'Dates'},
            {'name': 'cancellation_date', 'display_name': 'Cancellation Date', 'field_path': 'cancellation_date', 'field_type': datetime_type, 'group': 'Dates'},
            # QA Dates
            {'name': 'due_to_techqa', 'display_name': 'Due to Tech QA (computed)', 'field_path': '_due_to_techqa', 'field_type': date_type, 'group': 'QA Dates'},
            {'name': 'due_to_techqa_set', 'display_name': 'Due to Tech QA (set)', 'field_path': 'due_to_techqa_set', 'field_type': date_type, 'group': 'QA Dates'},
            {'name': 'actual_sent_to_tqa_date', 'display_name': 'Actual Sent to TQA', 'field_path': 'actual_sent_to_tqa_date', 'field_type': datetime_type, 'group': 'QA Dates'},
            {'name': 'due_to_presqa', 'display_name': 'Due to Pres QA (computed)', 'field_path': '_due_to_presqa', 'field_type': date_type, 'group': 'QA Dates'},
            {'name': 'due_to_presqa_set', 'display_name': 'Due to Pres QA (set)', 'field_path': 'due_to_presqa_set', 'field_type': date_type, 'group': 'QA Dates'},
            {'name': 'actual_sent_to_pqa_date', 'display_name': 'Actual Sent to PQA', 'field_path': 'actual_sent_to_pqa_date', 'field_type': datetime_type, 'group': 'QA Dates'},
            # Quality
            {'name': 'feedback_scope_correct', 'display_name': 'Feedback Scope Correct', 'field_path': 'feedback_scope_correct', 'field_type': boolean_type, 'group': 'Quality'},
            {'name': 'required_tqa_updates', 'display_name': 'Required TQA Updates', 'field_path': 'required_tqa_updates', 'field_type': boolean_type, 'group': 'Quality'},
            {'name': 'required_pqa_updates', 'display_name': 'Required PQA Updates', 'field_path': 'required_pqa_updates', 'field_type': boolean_type, 'group': 'Quality'},
            {'name': 'was_submitted_late_tqa', 'display_name': 'Late TQA Submission', 'field_path': 'was_submitted_late_tqa', 'field_type': boolean_type, 'group': 'Quality'},
            {'name': 'was_submitted_late_pqa', 'display_name': 'Late PQA Submission', 'field_path': 'was_submitted_late_pqa', 'field_type': boolean_type, 'group': 'Quality'},
            {'name': 'was_submitted_late_delivery', 'display_name': 'Late Delivery', 'field_path': 'was_submitted_late_delivery', 'field_type': boolean_type, 'group': 'Quality'},
            {'name': 'techqa_report_rating', 'display_name': 'Tech QA Report Rating', 'field_path': 'techqa_report_rating', 'field_type': integer_type, 'group': 'Quality'},
            {'name': 'presqa_report_rating', 'display_name': 'Pres QA Report Rating', 'field_path': 'presqa_report_rating', 'field_type': integer_type, 'group': 'Quality'},
            {'name': 'number_of_reports', 'display_name': 'Number of Reports', 'field_path': 'number_of_reports', 'field_type': integer_type, 'group': 'Quality'},
            # Logistics
            {'name': 'is_testing_onsite', 'display_name': 'Testing Onsite', 'field_path': 'is_testing_onsite', 'field_type': boolean_type, 'group': 'Logistics'},
            {'name': 'is_reporting_onsite', 'display_name': 'Reporting Onsite', 'field_path': 'is_reporting_onsite', 'field_type': boolean_type, 'group': 'Logistics'},
            {'name': 'report_to_be_left_on_client_site', 'display_name': 'Report Left on Client Site', 'field_path': 'report_to_be_left_on_client_site', 'field_type': boolean_type, 'group': 'Logistics'},
            {'name': 'location', 'display_name': 'Location', 'field_path': 'location', 'field_type': text_type, 'group': 'Logistics'},
        ]

        self._sync_fields(data_area, fields)

    def setup_project_data_area(self):
        """Set up Project data area and fields"""
        self.stdout.write('Setting up Project data area...')

        content_type = ContentType.objects.get_for_model(Project)

        data_area = self._get_or_create_data_area('Projects', {
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
        })

        text_type = self.field_types['Text']
        datetime_type = self.field_types['DateTime']
        foreign_key_type = self.field_types['Foreign Key']
        integer_type = self.field_types['Integer']

        fields = [
            {'name': 'id', 'display_name': 'Project ID', 'field_path': 'id', 'field_type': integer_type, 'group': 'Basic'},
            {'name': 'title', 'display_name': 'Project Title', 'field_path': 'title', 'field_type': text_type, 'group': 'Basic'},
            {'name': 'status', 'display_name': 'Status', 'field_path': 'status', 'field_type': integer_type, 'group': 'Status'},
            {'name': 'created_by', 'display_name': 'Created By', 'field_path': 'created_by__last_name', 'field_type': foreign_key_type, 'group': 'Management'},
            {'name': 'created_at', 'display_name': 'Created At', 'field_path': 'created_at', 'field_type': datetime_type, 'group': 'Dates'},
            {'name': 'primary_poc', 'display_name': 'Primary POC', 'field_path': 'primary_poc__last_name', 'field_type': foreign_key_type, 'group': 'Management'},
            {'name': 'external_id', 'display_name': 'External ID', 'field_path': 'external_id', 'field_type': text_type, 'group': 'External'},
        ]

        self._sync_fields(data_area, fields)

    def setup_client_data_area(self):
        """Set up Client data area and fields"""
        self.stdout.write('Setting up Client data area...')

        content_type = ContentType.objects.get_for_model(Client)

        data_area = self._get_or_create_data_area('Clients', {
            'description': 'Clients and related information',
            'content_type': content_type,
            'model_name': 'Client',
            'default_sort_field': 'name',
            'icon_class': 'fa-building',
            'population_options': {}
        })

        text_type = self.field_types['Text']
        long_text_type = self.field_types['Long Text']
        boolean_type = self.field_types['Boolean']
        integer_type = self.field_types['Integer']
        decimal_type = self.field_types['Decimal']
        foreign_key_type = self.field_types['Foreign Key']

        fields = [
            # Basic
            {'name': 'id', 'display_name': 'Client ID', 'field_path': 'id', 'field_type': integer_type, 'group': 'Basic'},
            {'name': 'name', 'display_name': 'Client Name', 'field_path': 'name', 'field_type': text_type, 'group': 'Basic'},
            {'name': 'short_name', 'display_name': 'Short Name', 'field_path': 'short_name', 'field_type': text_type, 'group': 'Basic'},
            {'name': 'external_id', 'display_name': 'External ID', 'field_path': 'external_id', 'field_type': text_type, 'group': 'Basic'},
            # Operations
            {'name': 'hours_in_day', 'display_name': 'Hours in Day', 'field_path': 'hours_in_day', 'field_type': decimal_type, 'group': 'Operations'},
            # Onboarding
            {'name': 'onboarding_required', 'display_name': 'Onboarding Required', 'field_path': 'onboarding_required', 'field_type': boolean_type, 'group': 'Onboarding'},
            {'name': 'onboarding_requirements', 'display_name': 'Onboarding Requirements', 'field_path': 'onboarding_requirements', 'field_type': long_text_type, 'group': 'Onboarding'},
            {'name': 'onboarding_reoccurring_renewal', 'display_name': 'Reoccurring Renewal', 'field_path': 'onboarding_reoccurring_renewal', 'field_type': boolean_type, 'group': 'Onboarding'},
            {'name': 'onboarding_reqs_renewal', 'display_name': 'Renewal Period (days)', 'field_path': 'onboarding_reqs_renewal', 'field_type': integer_type, 'group': 'Onboarding'},
            {'name': 'onboarding_reqs_reminder_days', 'display_name': 'Reminder Days', 'field_path': 'onboarding_reqs_reminder_days', 'field_type': integer_type, 'group': 'Onboarding'},
            # Requirements
            {'name': 'specific_requirements', 'display_name': 'Specific Requirements', 'field_path': 'specific_requirements', 'field_type': long_text_type, 'group': 'Requirements'},
            {'name': 'specific_reporting_requirements', 'display_name': 'Specific Reporting Requirements', 'field_path': 'specific_reporting_requirements', 'field_type': long_text_type, 'group': 'Requirements'},
        ]

        self._sync_fields(data_area, fields)

    def setup_data_sources(self):
        """Set up relationships between data areas"""
        self.stdout.write('Setting up data source relationships...')

        one_to_many = RelationshipType.objects.get(name='One-to-Many')
        many_to_one = RelationshipType.objects.get(name='Many-to-One')

        try:
            users_area = DataArea.objects.get(name='Users')
            jobs_area = DataArea.objects.get(name='Jobs')
            phases_area = DataArea.objects.get(name='Phases')
            projects_area = DataArea.objects.get(name='Projects')
            clients_area = DataArea.objects.get(name='Clients')

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
