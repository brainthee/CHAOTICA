import datetime

def get_filter_type_choices(field_type):
    """
    Get available filter types for a field type

    :param field_type: The field type string
    :return: List of (value, display_text) tuples
    """
    common_filters = [
        ('exact', 'Equals'),
        ('iexact', 'Equals (case insensitive)'),
        ('isnull', 'Is null'),
    ]
    
    text_filters = [
        ('contains', 'Contains'),
        ('icontains', 'Contains (case insensitive)'),
        ('startswith', 'Starts with'),
        ('istartswith', 'Starts with (case insensitive)'),
        ('endswith', 'Ends with'),
        ('iendswith', 'Ends with (case insensitive)'),
        ('regex', 'Matches regex'),
        ('iregex', 'Matches regex (case insensitive)'),
        ('in', 'In list'),
    ]
    
    number_filters = [
        ('gt', 'Greater than'),
        ('gte', 'Greater than or equal to'),
        ('lt', 'Less than'),
        ('lte', 'Less than or equal to'),
        ('range', 'Between'),
        ('in', 'In list'),
    ]
    
    date_filters = [
        ('gt', 'After'),
        ('gte', 'On or after'),
        ('lt', 'Before'),
        ('lte', 'On or before'),
        ('range', 'Between'),
        ('year', 'Year equals'),
        ('month', 'Month equals'),
        ('day', 'Day equals'),
        ('week_day', 'Weekday equals'),
    ]
    
    boolean_filters = [
        ('exact', 'Is'),
    ]
    
    # Return the appropriate filter types based on field type
    if field_type in ('text', 'char', 'string'):
        return common_filters + text_filters
    elif field_type in ('integer', 'decimal', 'float', 'number'):
        return common_filters + number_filters
    elif field_type in ('date', 'datetime'):
        return common_filters + date_filters
    elif field_type == 'boolean':
        return boolean_filters
    elif field_type in ('foreign_key', 'many_to_many'):
        return common_filters + [('in', 'In list')]
    else:
        # Default to common filters only
        return common_filters

def get_dynamic_filter_values(field_type):
    """
    Get dynamic filter values for a field type

    :param field_type: The field type string
    :return: List of (value, display_text) tuples
    """
    if field_type in ('date', 'datetime'):
        return [
            ('today', 'Today'),
            ('yesterday', 'Yesterday'),
            ('tomorrow', 'Tomorrow'),
            ('this_week', 'This week'),
            ('last_week', 'Last week'),
            ('this_month', 'This month'),
            ('last_month', 'Last month'),
            ('this_quarter', 'This quarter'),
            ('last_quarter', 'Last quarter'),
            ('this_year', 'This year'),
            ('last_year', 'Last year'),
        ]
    elif field_type in ('foreign_key', 'many_to_many') and field_type.endswith('__user'):
        return [
            ('current_user', 'Current user'),
        ]
    else:
        return []

def get_filter_value_widget_type(field_type, filter_type):
    """
    Get the appropriate form widget type for a filter value

    :param field_type: The field type string
    :param filter_type: The filter type string
    :return: Widget type string
    """
    if filter_type == 'isnull':
        return 'boolean'
    
    if field_type in ('text', 'char', 'string'):
        if filter_type == 'in':
            return 'text_list'
        else:
            return 'text'
    elif field_type in ('integer', 'decimal', 'float', 'number'):
        if filter_type == 'range':
            return 'number_range'
        elif filter_type == 'in':
            return 'number_list'
        else:
            return 'number'
    elif field_type in ('date', 'datetime'):
        if filter_type == 'range':
            return 'date_range'
        elif filter_type in ('year', 'month', 'day', 'week_day'):
            return 'number'
        else:
            return 'date'
    elif field_type == 'boolean':
        return 'boolean'
    elif field_type in ('foreign_key', 'many_to_many'):
        if filter_type == 'in':
            return 'multi_select'
        else:
            return 'select'
    else:
        return 'text'

def format_filter_display(field_name, filter_type, filter_value):
    """
    Format a filter condition for display

    :param field_name: Field display name
    :param filter_type: Filter type string
    :param filter_value: Filter value
    :return: Formatted string
    """
    # Map filter types to display text
    filter_type_map = {
        'exact': 'equals',
        'iexact': 'equals (case insensitive)',
        'contains': 'contains',
        'icontains': 'contains (case insensitive)',
        'startswith': 'starts with',
        'istartswith': 'starts with (case insensitive)',
        'endswith': 'ends with',
        'iendswith': 'ends with (case insensitive)',
        'gt': 'is greater than',
        'gte': 'is greater than or equal to',
        'lt': 'is less than',
        'lte': 'is less than or equal to',
        'in': 'is in',
        'range': 'is between',
        'isnull': 'is null' if filter_value else 'is not null',
        'regex': 'matches regex',
        'iregex': 'matches regex (case insensitive)',
        'year': 'year equals',
        'month': 'month equals',
        'day': 'day equals',
        'week_day': 'weekday equals',
    }
    
    # Format based on filter type
    filter_display = filter_type_map.get(filter_type, filter_type)
    
    # Format the value based on type
    if filter_type == 'isnull':
        return f"{field_name} {filter_display}"
    elif filter_type == 'in':
        if isinstance(filter_value, (list, tuple)):
            value_display = ', '.join(str(v) for v in filter_value)
        else:
            value_display = str(filter_value)
        return f"{field_name} {filter_display} ({value_display})"
    elif filter_type == 'range':
        if isinstance(filter_value, (list, tuple)) and len(filter_value) == 2:
            return f"{field_name} {filter_display} {filter_value[0]} and {filter_value[1]}"
        else:
            return f"{field_name} {filter_display} {filter_value}"
    else:
        return f"{field_name} {filter_display} {filter_value}"

def evaluate_dynamic_filter_value(value, field_type):
    """
    Evaluate a dynamic filter value

    :param value: Dynamic value string
    :param field_type: Field type string
    :return: Actual value
    """
    today = datetime.date.today()
    
    if value == 'today':
        return today
    elif value == 'yesterday':
        return today - datetime.timedelta(days=1)
    elif value == 'tomorrow':
        return today + datetime.timedelta(days=1)
    elif value == 'this_week':
        # Get the start of the week (Monday)
        start_of_week = today - datetime.timedelta(days=today.weekday())
        return (start_of_week, start_of_week + datetime.timedelta(days=6))
    elif value == 'last_week':
        # Get the start of last week
        start_of_last_week = today - datetime.timedelta(days=today.weekday() + 7)
        return (start_of_last_week, start_of_last_week + datetime.timedelta(days=6))
    elif value == 'this_month':
        start_of_month = datetime.date(today.year, today.month, 1)
        if today.month == 12:
            end_of_month = datetime.date(today.year + 1, 1, 1) - datetime.timedelta(days=1)
        else:
            end_of_month = datetime.date(today.year, today.month + 1, 1) - datetime.timedelta(days=1)
        return (start_of_month, end_of_month)
    elif value == 'last_month':
        if today.month == 1:
            start_of_last_month = datetime.date(today.year - 1, 12, 1)
            end_of_last_month = datetime.date(today.year, 1, 1) - datetime.timedelta(days=1)
        else:
            start_of_last_month = datetime.date(today.year, today.month - 1, 1)
            end_of_last_month = datetime.date(today.year, today.month, 1) - datetime.timedelta(days=1)
        return (start_of_last_month, end_of_last_month)
    elif value == 'this_year':
        return (datetime.date(today.year, 1, 1), datetime.date(today.year, 12, 31))
    elif value == 'last_year':
        return (datetime.date(today.year - 1, 1, 1), datetime.date(today.year - 1, 12, 31))
    else:
        return value