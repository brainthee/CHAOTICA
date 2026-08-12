import datetime

# Equality-style operators where offering a value picklist makes sense.
_CHOICE_FRIENDLY_OPERATORS = {'exact', 'iexact', 'in'}


def normalise_field_type(name):
    """'Foreign Key' -> 'foreign_key' so it matches the widget/type lookups."""
    return (name or '').lower().replace(' ', '_')


def resolve_model_field(model, field_path):
    """Walk an ``a__b__c`` ORM path from ``model``; return the terminal Django
    field, or ``None`` if the path doesn't resolve."""
    field = None
    current = model
    for part in field_path.split('__'):
        try:
            field = current._meta.get_field(part)
        except Exception:
            return None
        related = getattr(field, 'related_model', None)
        if related is not None:
            current = related
    return field


def get_field_filter_choices(data_field, user=None, limit=1000):
    """Return ``[{'value','label'}, ...]`` for a filter field that has a bounded
    set of values (enum/choice fields like status, booleans, and related-name
    paths like ``unit__name``), else ``None`` to fall back to free text.

    Related-name value lists are scoped to what ``user`` may see (same permission
    filter the report results use) and capped at ``limit`` — beyond that we return
    ``None`` so huge columns stay as free text rather than an unusable dropdown.
    """
    from django.db import models as dj_models
    from ..models import DataField

    if getattr(data_field, 'source_type', None) == DataField.SOURCE_RESOLVER:
        return None  # resolver fields aren't ORM-filterable

    area = data_field.data_area
    try:
        model = area.content_type.model_class()
    except Exception:
        model = None
    if model is None:
        return None

    field = resolve_model_field(model, data_field.field_path)
    if field is None:
        return None

    # 1. Explicit model choices (status enums, etc.) — value is the stored value.
    if getattr(field, 'choices', None):
        return [{'value': str(v), 'label': str(label)} for v, label in field.choices]

    # 2. Booleans.
    if isinstance(field, dj_models.BooleanField):
        return [{'value': 'true', 'label': 'Yes'}, {'value': 'false', 'label': 'No'}]

    # 3. Related-name paths (unit__name, client__name, service__name, ...) — the
    #    filter matches the name, so enumerate the distinct names the user can see.
    if '__' in data_field.field_path:
        queryset = model.objects.all()
        if user is not None:
            try:
                from ..services.data_service import DataService
                queryset = DataService._apply_permission_filter(queryset, area, user)
            except Exception:
                pass
        path = data_field.field_path
        try:
            values = list(
                queryset.exclude(**{f'{path}__isnull': True})
                .order_by(path)
                .values_list(path, flat=True)
                .distinct()[: limit + 1]
            )
        except Exception:
            return None
        if not values or len(values) > limit:
            return None
        return [{'value': str(v), 'label': str(v)} for v in values if str(v) != '']

    return None


def get_filter_widget_and_choices(data_field, operator, user=None):
    """Resolve the value widget type and (optionally) its choices for a field +
    filter operator. Upgrades to a (searchable) select/multi-select when the field
    has a bounded value set and the operator is equality-style."""
    field_type = normalise_field_type(data_field.field_type.name)
    widget_type = get_filter_value_widget_type(field_type, operator)
    choices = None
    if operator in _CHOICE_FRIENDLY_OPERATORS:
        choices = get_field_filter_choices(data_field, user)
    if choices:
        widget_type = 'multi_select' if operator == 'in' else 'select'
    return widget_type, (choices or [])


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
            ('today+7d', 'In 7 days'),
            ('today+30d', 'In 30 days'),
            ('today-7d', '7 days ago'),
            ('today-30d', '30 days ago'),
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
        # Relative rolling offsets like "today+30d" / "today-7d".
        from .query_builder import resolve_relative_date_token
        relative = resolve_relative_date_token(value)
        if relative is not None:
            return relative
        return value