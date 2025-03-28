from django.core.management.base import BaseCommand
from django.db import transaction

from reporting.models import (
    FieldType, FilterType, RelationshipType,
    FieldPresentation, ReportCategory, FilterCondition
)


class Command(BaseCommand):
    help = 'Setup core data for the Report Builder application (field types, filter types, etc.)'

    def handle(self, *args, **options):
        self.stdout.write('Setting up Report Builder core data...')
        
        # Use transaction to ensure all-or-nothing
        with transaction.atomic():
            self.setup_relationship_types()
            self.setup_field_types()
            self.setup_filter_types()
            self.setup_report_categories()
            
        self.stdout.write(self.style.SUCCESS('Report Builder core data setup complete!'))
    
    def setup_relationship_types(self):
        """Create relationship types"""
        self.stdout.write('Setting up relationship types...')
        
        relationship_types = [
            {
                'name': 'One-to-Many',
                'description': 'One record related to many records'
            },
            {
                'name': 'Many-to-One',
                'description': 'Many records related to one record'
            },
            {
                'name': 'Many-to-Many',
                'description': 'Many records related to many records'
            },
            {
                'name': 'One-to-One',
                'description': 'One record related to one record'
            },
        ]
        
        for rt_data in relationship_types:
            RelationshipType.objects.get_or_create(
                name=rt_data['name'],
                defaults={'description': rt_data['description']}
            )
    
    def setup_field_types(self):
        """Create field types"""
        self.stdout.write('Setting up field types...')
        
        field_types = [
            {
                'name': 'Text',
                'description': 'Text field',
                'django_field_type': 'CharField',
                'default_format': None,
                'can_filter': True,
                'can_sort': True
            },
            {
                'name': 'Long Text',
                'description': 'Long text field',
                'django_field_type': 'TextField',
                'default_format': None,
                'can_filter': True,
                'can_sort': True
            },
            {
                'name': 'Integer',
                'description': 'Integer field',
                'django_field_type': 'IntegerField',
                'default_format': None,
                'can_filter': True,
                'can_sort': True
            },
            {
                'name': 'Decimal',
                'description': 'Decimal field',
                'django_field_type': 'DecimalField',
                'default_format': '0.00',
                'can_filter': True,
                'can_sort': True
            },
            {
                'name': 'Boolean',
                'description': 'Boolean field',
                'django_field_type': 'BooleanField',
                'default_format': None,
                'can_filter': True,
                'can_sort': True
            },
            {
                'name': 'Date',
                'description': 'Date field',
                'django_field_type': 'DateField',
                'default_format': 'YYYY-MM-DD',
                'can_filter': True,
                'can_sort': True
            },
            {
                'name': 'DateTime',
                'description': 'Date and time field',
                'django_field_type': 'DateTimeField',
                'default_format': 'YYYY-MM-DD HH:MM:SS',
                'can_filter': True,
                'can_sort': True
            },
            {
                'name': 'Foreign Key',
                'description': 'Foreign key field',
                'django_field_type': 'ForeignKey',
                'default_format': None,
                'can_filter': True,
                'can_sort': True
            },
            {
                'name': 'Many to Many',
                'description': 'Many to many field',
                'django_field_type': 'ManyToManyField',
                'default_format': None,
                'can_filter': True,
                'can_sort': False
            },
            {
                'name': 'JSON',
                'description': 'JSON field',
                'django_field_type': 'JSONField',
                'default_format': None,
                'can_filter': False,
                'can_sort': False
            },
            {
                'name': 'Email',
                'description': 'Email field',
                'django_field_type': 'EmailField',
                'default_format': None,
                'can_filter': True,
                'can_sort': True
            },
            {
                'name': 'URL',
                'description': 'URL field',
                'django_field_type': 'URLField',
                'default_format': None,
                'can_filter': True,
                'can_sort': True
            },
            {
                'name': 'Image',
                'description': 'Image field',
                'django_field_type': 'ImageField',
                'default_format': None,
                'can_filter': False,
                'can_sort': False
            },
        ]
        
        for ft_data in field_types:
            field_type, created = FieldType.objects.get_or_create(
                name=ft_data['name'],
                defaults={
                    'description': ft_data['description'],
                    'django_field_type': ft_data['django_field_type'],
                    'default_format': ft_data['default_format'],
                    'can_filter': ft_data['can_filter'],
                    'can_sort': ft_data['can_sort']
                }
            )
            
            # Add field presentations for this field type
            if created:
                self.setup_field_presentations(field_type)
    
    def setup_field_presentations(self, field_type):
        """Create field presentations for a given field type"""
        presentations = []
        
        if field_type.name == 'Text':
            presentations = [
                {'name': 'Default', 'format_string': None},
                {'name': 'Uppercase', 'format_string': 'UPPERCASE'},
                {'name': 'Lowercase', 'format_string': 'lowercase'},
                {'name': 'Title Case', 'format_string': 'Title Case'},
            ]
        elif field_type.name == 'Integer':
            presentations = [
                {'name': 'Default', 'format_string': None},
                {'name': 'With Commas', 'format_string': '0,0'},
                {'name': 'Percentage', 'format_string': '0%'},
            ]
        elif field_type.name == 'Decimal':
            presentations = [
                {'name': 'Default', 'format_string': '0.00'},
                {'name': 'Currency (£)', 'format_string': '£0,0.00'},
                {'name': 'Currency ($)', 'format_string': '$0,0.00'},
                {'name': 'Percentage', 'format_string': '0.00%'},
                {'name': 'One Decimal Place', 'format_string': '0.0'},
                {'name': 'No Decimal Places', 'format_string': '0'},
            ]
        elif field_type.name == 'Boolean':
            presentations = [
                {'name': 'Yes/No', 'format_string': 'Yes/No'},
                {'name': 'True/False', 'format_string': 'True/False'},
                {'name': 'Y/N', 'format_string': 'Y/N'},
                {'name': '1/0', 'format_string': '1/0'},
            ]
        elif field_type.name == 'Date':
            presentations = [
                {'name': 'Default', 'format_string': 'YYYY-MM-DD'},
                {'name': 'Short Date', 'format_string': 'DD/MM/YYYY'},
                {'name': 'US Date', 'format_string': 'MM/DD/YYYY'},
                {'name': 'Long Date', 'format_string': 'D MMMM YYYY'},
            ]
        elif field_type.name == 'DateTime':
            presentations = [
                {'name': 'Default', 'format_string': 'YYYY-MM-DD HH:MM:SS'},
                {'name': 'Short Date/Time', 'format_string': 'DD/MM/YYYY HH:MM'},
                {'name': 'Date Only', 'format_string': 'YYYY-MM-DD'},
                {'name': 'Time Only', 'format_string': 'HH:MM:SS'},
            ]
        else:
            presentations = [
                {'name': 'Default', 'format_string': None},
            ]
        
        for pres in presentations:
            FieldPresentation.objects.get_or_create(
                name=pres['name'],
                field_type=field_type,
                defaults={
                    'format_string': pres['format_string'],
                    'is_available': True
                }
            )
    
    def setup_filter_types(self):
        """Create filter types and their filter conditions"""
        self.stdout.write('Setting up filter types...')
        
        # Get field types
        text_type = FieldType.objects.get(name='Text')
        long_text_type = FieldType.objects.get(name='Long Text')
        integer_type = FieldType.objects.get(name='Integer')
        decimal_type = FieldType.objects.get(name='Decimal')
        boolean_type = FieldType.objects.get(name='Boolean')
        date_type = FieldType.objects.get(name='Date')
        datetime_type = FieldType.objects.get(name='DateTime')
        foreign_key_type = FieldType.objects.get(name='Foreign Key')
        many_to_many_type = FieldType.objects.get(name='Many to Many')
        email_type = FieldType.objects.get(name='Email')
        url_type = FieldType.objects.get(name='URL')
        
        filter_types = [
            {
                'name': 'Equals',
                'description': 'Exactly matches the value',
                'operator': 'exact',
                'display_label': 'equals',
                'requires_value': True,
                'supports_multiple_values': False,
                'applicable_field_types': [
                    text_type, long_text_type, integer_type, decimal_type, boolean_type,
                    date_type, datetime_type, foreign_key_type, email_type, url_type
                ],
                'display_order': 1
            },
            {
                'name': 'Not Equals',
                'description': 'Does not match the value',
                'operator': 'exact',
                'display_label': 'does not equal',
                'requires_value': True,
                'supports_multiple_values': False,
                'applicable_field_types': [
                    text_type, long_text_type, integer_type, decimal_type, boolean_type,
                    date_type, datetime_type, foreign_key_type, email_type, url_type
                ],
                'display_order': 2
            },
            {
                'name': 'Contains',
                'description': 'Contains the value',
                'operator': 'contains',
                'display_label': 'contains',
                'requires_value': True,
                'supports_multiple_values': False,
                'applicable_field_types': [text_type, long_text_type, email_type, url_type],
                'display_order': 3
            },
            {
                'name': 'Does Not Contain',
                'description': 'Does not contain the value',
                'operator': 'contains',
                'display_label': 'does not contain',
                'requires_value': True,
                'supports_multiple_values': False,
                'applicable_field_types': [text_type, long_text_type, email_type, url_type],
                'display_order': 4
            },
            {
                'name': 'Starts With',
                'description': 'Starts with the value',
                'operator': 'startswith',
                'display_label': 'starts with',
                'requires_value': True,
                'supports_multiple_values': False,
                'applicable_field_types': [text_type, long_text_type, email_type, url_type],
                'display_order': 5
            },
            {
                'name': 'Ends With',
                'description': 'Ends with the value',
                'operator': 'endswith',
                'display_label': 'ends with',
                'requires_value': True,
                'supports_multiple_values': False,
                'applicable_field_types': [text_type, long_text_type, email_type, url_type],
                'display_order': 6
            },
            {
                'name': 'Greater Than',
                'description': 'Greater than the value',
                'operator': 'gt',
                'display_label': 'greater than',
                'requires_value': True,
                'supports_multiple_values': False,
                'applicable_field_types': [integer_type, decimal_type, date_type, datetime_type],
                'display_order': 7
            },
            {
                'name': 'Greater Than or Equal',
                'description': 'Greater than or equal to the value',
                'operator': 'gte',
                'display_label': 'greater than or equal to',
                'requires_value': True,
                'supports_multiple_values': False,
                'applicable_field_types': [integer_type, decimal_type, date_type, datetime_type],
                'display_order': 8
            },
            {
                'name': 'Less Than',
                'description': 'Less than the value',
                'operator': 'lt',
                'display_label': 'less than',
                'requires_value': True,
                'supports_multiple_values': False,
                'applicable_field_types': [integer_type, decimal_type, date_type, datetime_type],
                'display_order': 9
            },
            {
                'name': 'Less Than or Equal',
                'description': 'Less than or equal to the value',
                'operator': 'lte',
                'display_label': 'less than or equal to',
                'requires_value': True,
                'supports_multiple_values': False,
                'applicable_field_types': [integer_type, decimal_type, date_type, datetime_type],
                'display_order': 10
            },
            {
                'name': 'In List',
                'description': 'Matches any value in the list',
                'operator': 'in',
                'display_label': 'in list',
                'requires_value': True,
                'supports_multiple_values': True,
                'applicable_field_types': [
                    text_type, long_text_type, integer_type, decimal_type,
                    foreign_key_type, many_to_many_type, email_type, url_type
                ],
                'display_order': 11
            },
            {
                'name': 'Not In List',
                'description': 'Does not match any value in the list',
                'operator': 'in',
                'display_label': 'not in list',
                'requires_value': True,
                'supports_multiple_values': True,
                'applicable_field_types': [
                    text_type, long_text_type, integer_type, decimal_type,
                    foreign_key_type, many_to_many_type, email_type, url_type
                ],
                'display_order': 12
            },
            {
                'name': 'Between',
                'description': 'Between two values',
                'operator': 'range',
                'display_label': 'between',
                'requires_value': True,
                'supports_multiple_values': True,
                'applicable_field_types': [integer_type, decimal_type, date_type, datetime_type],
                'display_order': 13
            },
            {
                'name': 'Is Null',
                'description': 'Is null/empty',
                'operator': 'isnull',
                'display_label': 'is empty',
                'requires_value': False,
                'supports_multiple_values': False,
                'applicable_field_types': [
                    text_type, long_text_type, integer_type, decimal_type,
                    date_type, datetime_type, foreign_key_type, email_type, url_type
                ],
                'display_order': 14
            },
            {
                'name': 'Is Not Null',
                'description': 'Is not null/empty',
                'operator': 'isnull',
                'display_label': 'is not empty',
                'requires_value': False,
                'supports_multiple_values': False,
                'applicable_field_types': [
                    text_type, long_text_type, integer_type, decimal_type,
                    date_type, datetime_type, foreign_key_type, email_type, url_type
                ],
                'display_order': 15
            },
        ]
        
        for ft_data in filter_types:
            try:
                filter_type, created = FilterType.objects.get_or_create(
                    name=ft_data['name'],
                    defaults={
                        'description': ft_data['description'],
                        'operator': ft_data['operator'],
                        'display_label': ft_data['display_label'],
                        'requires_value': ft_data['requires_value'],
                        'supports_multiple_values': ft_data['supports_multiple_values'],
                        'display_order': ft_data['display_order'],
                    }
                )
                
                if created:
                    filter_type.applicable_field_types.set(ft_data['applicable_field_types'])
                    self.stdout.write(f"  Created filter type: {filter_type.name}")
                else:
                    self.stdout.write(f"  Filter type already exists: {filter_type.name}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error creating filter type {ft_data['name']}: {str(e)}"))
        
        # Now set up filter conditions separately
        self.setup_filter_conditions()

    def setup_filter_conditions(self):
        """Create filter conditions for all filter types"""
        self.stdout.write('Setting up filter conditions...')
        
        # Date field types
        try:
            date_type = FieldType.objects.get(name='Date')
            datetime_type = FieldType.objects.get(name='DateTime')
            boolean_type = FieldType.objects.get(name='Boolean')
            foreign_key_type = FieldType.objects.get(name='Foreign Key')
        except FieldType.DoesNotExist as e:
            self.stdout.write(self.style.ERROR(f"Error getting field types: {str(e)}"))
            return
        
        # Add date-based conditions
        date_filters = FilterType.objects.filter(
            name__in=['Equals', 'Greater Than', 'Greater Than or Equal', 'Less Than', 'Less Than or Equal']
        )
        
        if date_filters.exists():
            self.stdout.write("  Setting up date-based conditions")
            
            date_conditions = [
                {
                    'name': 'Today',
                    'field_type': date_type,
                    'value': 'today',
                    'is_dynamic': True,
                    'display_label': 'Today',
                    'display_order': 1,
                },
                {
                    'name': 'Yesterday',
                    'field_type': date_type,
                    'value': 'yesterday',
                    'is_dynamic': True,
                    'display_label': 'Yesterday',
                    'display_order': 2,
                },
                {
                    'name': 'Tomorrow',
                    'field_type': date_type,
                    'value': 'tomorrow',
                    'is_dynamic': True,
                    'display_label': 'Tomorrow',
                    'display_order': 3,
                },
                {
                    'name': 'First Day of Month',
                    'field_type': date_type,
                    'value': 'first_day_month',
                    'is_dynamic': True,
                    'display_label': 'First day of current month',
                    'display_order': 4,
                },
                {
                    'name': 'Last Day of Month',
                    'field_type': date_type,
                    'value': 'last_day_month',
                    'is_dynamic': True,
                    'display_label': 'Last day of current month',
                    'display_order': 5,
                },
            ]
            
            # Create date conditions for each filter type
            for filter_type in date_filters:
                for condition_data in date_conditions:
                    try:
                        condition, created = FilterCondition.objects.get_or_create(
                            name=condition_data['name'],
                            field_type=condition_data['field_type'],
                            filter_type=filter_type,
                            defaults={
                                'value': condition_data['value'],
                                'is_dynamic': condition_data['is_dynamic'],
                                'display_label': condition_data['display_label'],
                                'display_order': condition_data['display_order'],
                            }
                        )
                        if created:
                            self.stdout.write(f"    Created filter condition: {condition.name} for {filter_type.name}")
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"    Error creating condition {condition_data['name']} for {filter_type.name}: {str(e)}"))
                
                # Also create for DateTime field type
                for condition_data in date_conditions:
                    try:
                        datetime_condition = condition_data.copy()
                        datetime_condition['field_type'] = datetime_type
                        condition, created = FilterCondition.objects.get_or_create(
                            name=datetime_condition['name'],
                            field_type=datetime_condition['field_type'],
                            filter_type=filter_type,
                            defaults={
                                'value': datetime_condition['value'],
                                'is_dynamic': datetime_condition['is_dynamic'],
                                'display_label': datetime_condition['display_label'],
                                'display_order': datetime_condition['display_order'],
                            }
                        )
                        if created:
                            self.stdout.write(f"    Created filter condition: {condition.name} for {filter_type.name} (DateTime)")
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"    Error creating DateTime condition {datetime_condition['name']} for {filter_type.name}: {str(e)}"))
        
        # Add range conditions for Between filter
        between_filter = FilterType.objects.filter(name='Between').first()
        if between_filter:
            self.stdout.write("  Setting up date range conditions")
            
            range_conditions = [
                {
                    'name': 'This Week',
                    'field_type': date_type,
                    'value': 'this_week',
                    'is_dynamic': True,
                    'display_label': 'This week',
                    'display_order': 1,
                },
                {
                    'name': 'Last Week',
                    'field_type': date_type,
                    'value': 'last_week',
                    'is_dynamic': True,
                    'display_label': 'Last week',
                    'display_order': 2,
                },
                {
                    'name': 'This Month',
                    'field_type': date_type,
                    'value': 'this_month',
                    'is_dynamic': True,
                    'display_label': 'This month',
                    'display_order': 3,
                },
                {
                    'name': 'Last Month',
                    'field_type': date_type,
                    'value': 'last_month',
                    'is_dynamic': True,
                    'display_label': 'Last month',
                    'display_order': 4,
                },
                {
                    'name': 'This Quarter',
                    'field_type': date_type,
                    'value': 'this_quarter',
                    'is_dynamic': True,
                    'display_label': 'This quarter',
                    'display_order': 5,
                },
                {
                    'name': 'Last Quarter',
                    'field_type': date_type,
                    'value': 'last_quarter',
                    'is_dynamic': True,
                    'display_label': 'Last quarter',
                    'display_order': 6,
                },
                {
                    'name': 'This Year',
                    'field_type': date_type,
                    'value': 'this_year',
                    'is_dynamic': True,
                    'display_label': 'This year',
                    'display_order': 7,
                },
                {
                    'name': 'Last Year',
                    'field_type': date_type,
                    'value': 'last_year',
                    'is_dynamic': True,
                    'display_label': 'Last year',
                    'display_order': 8,
                },
            ]
            
            # Create range conditions
            for condition_data in range_conditions:
                try:
                    condition, created = FilterCondition.objects.get_or_create(
                        name=condition_data['name'],
                        field_type=condition_data['field_type'],
                        filter_type=between_filter,
                        defaults={
                            'value': condition_data['value'],
                            'is_dynamic': condition_data['is_dynamic'],
                            'display_label': condition_data['display_label'],
                            'display_order': condition_data['display_order'],
                        }
                    )
                    if created:
                        self.stdout.write(f"    Created filter condition: {condition.name} for Between")
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"    Error creating range condition {condition_data['name']}: {str(e)}"))
            
            # Also create for DateTime field type
            for condition_data in range_conditions:
                try:
                    datetime_condition = condition_data.copy()
                    datetime_condition['field_type'] = datetime_type
                    condition, created = FilterCondition.objects.get_or_create(
                        name=datetime_condition['name'],
                        field_type=datetime_condition['field_type'],
                        filter_type=between_filter,
                        defaults={
                            'value': datetime_condition['value'],
                            'is_dynamic': datetime_condition['is_dynamic'],
                            'display_label': datetime_condition['display_label'],
                            'display_order': datetime_condition['display_order'],
                        }
                    )
                    if created:
                        self.stdout.write(f"    Created filter condition: {condition.name} for Between (DateTime)")
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"    Error creating DateTime range condition {datetime_condition['name']}: {str(e)}"))
        
        # Add boolean conditions
        equals_filter = FilterType.objects.filter(name='Equals').first()
        if equals_filter:
            self.stdout.write("  Setting up boolean conditions")
            
            boolean_conditions = [
                {
                    'name': 'True',
                    'field_type': boolean_type,
                    'value': 'true',
                    'is_dynamic': False,
                    'display_label': 'Yes / True',
                    'display_order': 1,
                },
                {
                    'name': 'False',
                    'field_type': boolean_type,
                    'value': 'false',
                    'is_dynamic': False,
                    'display_label': 'No / False',
                    'display_order': 2,
                },
            ]
            
            for condition_data in boolean_conditions:
                try:
                    condition, created = FilterCondition.objects.get_or_create(
                        name=condition_data['name'],
                        field_type=condition_data['field_type'],
                        filter_type=equals_filter,
                        defaults={
                            'value': condition_data['value'],
                            'is_dynamic': condition_data['is_dynamic'],
                            'display_label': condition_data['display_label'],
                            'display_order': condition_data['display_order'],
                        }
                    )
                    if created:
                        self.stdout.write(f"    Created filter condition: {condition.name} for Boolean")
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"    Error creating boolean condition {condition_data['name']}: {str(e)}"))
        
        # Add user conditions
        for filter_name in ['Equals', 'Not Equals']:
            filter_type = FilterType.objects.filter(name=filter_name).first()
            if filter_type:
                self.stdout.write(f"  Setting up user conditions for {filter_name}")
                
                try:
                    condition, created = FilterCondition.objects.get_or_create(
                        name='Current User',
                        field_type=foreign_key_type,
                        filter_type=filter_type,
                        defaults={
                            'value': 'current_user',
                            'is_dynamic': True,
                            'display_label': 'Current user',
                            'display_order': 1,
                        }
                    )
                    if created:
                        self.stdout.write(f"    Created filter condition: Current User for {filter_name}")
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"    Error creating user condition for {filter_name}: {str(e)}"))

    def setup_report_categories(self):
        """Create initial report categories"""
        self.stdout.write('Setting up report categories...')
        
        categories = [
            {'name': 'General', 'description': 'General reports'},
            {'name': 'Users', 'description': 'User-related reports'},
            {'name': 'Jobs', 'description': 'Job-related reports'},
            {'name': 'Projects', 'description': 'Project-related reports'},
            {'name': 'Clients', 'description': 'Client-related reports'},
            {'name': 'Teams', 'description': 'Team-related reports'},
            {'name': 'Organisation', 'description': 'Organisation-related reports'},
            {'name': 'Skills', 'description': 'Skill-related reports'},
            {'name': 'Scheduling', 'description': 'Scheduling and time-related reports'},
        ]
        
        for cat_data in categories:
            ReportCategory.objects.get_or_create(
                name=cat_data['name'],
                defaults={'description': cat_data['description']}
            )