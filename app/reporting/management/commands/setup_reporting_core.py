from django.core.management.base import BaseCommand
from django.db import transaction

from reporting.models import (
    FieldType, FilterType, RelationshipType,
    FieldPresentation, ReportCategory
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
        """Create filter types"""
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