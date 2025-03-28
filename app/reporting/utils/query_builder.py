from django.db.models import Q
import json
import operator
from functools import reduce
import datetime

def build_query_from_report(queryset, report, filter_values=None):
    """
    Build a Django queryset based on a report definition

    :param queryset: Base queryset to start with
    :param report: Report model instance
    :param filter_values: Dict of runtime filter values for prompts
    :return: Modified queryset with filters applied
    """
    filter_values = filter_values or {}
    
    # Apply report filters
    filters = report.get_filters()
    if filters:
        filter_q = build_filter_conditions(filters, filter_values)
        if filter_q:
            queryset = queryset.filter(filter_q)
    
    return queryset

def build_filter_conditions(filters, runtime_values=None):
    """
    Build Django Q objects from filter conditions

    :param filters: List of ReportFilter instances
    :param runtime_values: Dict of runtime values for prompted filters
    :return: Combined Q object
    """
    runtime_values = runtime_values or {}
    
    # Group filters by parent (for AND/OR grouping)
    filter_groups = {}
    standalone_filters = []
    
    for filter_obj in filters:
        if filter_obj.parent_filter_id is not None:
            if filter_obj.parent_filter_id not in filter_groups:
                filter_groups[filter_obj.parent_filter_id] = []
            filter_groups[filter_obj.parent_filter_id].append(filter_obj)
        else:
            standalone_filters.append(filter_obj)
    
    # Build Q objects for standalone filters (these will be AND'ed together)
    q_objects = []
    
    for filter_obj in standalone_filters:
        q = build_single_filter(filter_obj, runtime_values)
        if q is not None:
            q_objects.append(q)
        
        # If this filter has children, process them
        if filter_obj.id in filter_groups:
            child_filters = filter_groups[filter_obj.id]
            child_operator = operator.and_ if filter_obj.operator == 'and' else operator.or_
            
            child_q_objects = [build_single_filter(cf, runtime_values) for cf in child_filters]
            child_q_objects = [q for q in child_q_objects if q is not None]
            
            if child_q_objects:
                combined_child_q = reduce(child_operator, child_q_objects)
                q_objects.append(combined_child_q)
    
    # Combine all Q objects with AND
    if q_objects:
        return reduce(operator.and_, q_objects)
    
    return None

def build_single_filter(filter_obj, runtime_values=None):
    """
    Build a single Q object from a filter definition

    :param filter_obj: ReportFilter instance
    :param runtime_values: Dict of runtime values for prompted filters
    :return: Q object or None
    """
    runtime_values = runtime_values or {}
    
    # Get the field and filter type
    field = filter_obj.data_field
    field_path = field.field_path
    filter_type = filter_obj.filter_type
    
    # Get the filter value (either from the filter object or runtime values)
    if filter_obj.prompt_at_runtime:
        # Use the value from runtime_values if available
        filter_value = runtime_values.get(str(filter_obj.id))
        
        # If the value wasn't provided at runtime, don't apply this filter
        if filter_value is None:
            return None
    else:
        filter_value = filter_obj.value
    
    # Convert the value to the appropriate type based on the field type
    filter_value = convert_value_to_proper_type(filter_value, field.field_type.django_field_type)
    
    # Handle special filter operators
    if filter_type.operator == 'exact':
        if filter_type.name == 'Not Equals':
            return ~Q(**{field_path: filter_value})
        return Q(**{field_path: filter_value})
    elif filter_type.operator == 'iexact':
        if filter_type.name == 'Not Equals':
            return ~Q(**{f'{field_path}__iexact': filter_value})
        return Q(**{f'{field_path}__iexact': filter_value})
    elif filter_type.operator == 'contains':
        if filter_type.name == 'Does Not Contain':
            return ~Q(**{f'{field_path}__contains': filter_value})
        return Q(**{f'{field_path}__contains': filter_value})
    elif filter_type.operator == 'icontains':
        if filter_type.name == 'Does Not Contain':
            return ~Q(**{f'{field_path}__icontains': filter_value})
        return Q(**{f'{field_path}__icontains': filter_value})
    elif filter_type.operator == 'startswith':
        return Q(**{f'{field_path}__startswith': filter_value})
    elif filter_type.operator == 'istartswith':
        return Q(**{f'{field_path}__istartswith': filter_value})
    elif filter_type.operator == 'endswith':
        return Q(**{f'{field_path}__endswith': filter_value})
    elif filter_type.operator == 'iendswith':
        return Q(**{f'{field_path}__iendswith': filter_value})
    elif filter_type.operator == 'gt':
        return Q(**{f'{field_path}__gt': filter_value})
    elif filter_type.operator == 'gte':
        return Q(**{f'{field_path}__gte': filter_value})
    elif filter_type.operator == 'lt':
        return Q(**{f'{field_path}__lt': filter_value})
    elif filter_type.operator == 'lte':
        return Q(**{f'{field_path}__lte': filter_value})
    elif filter_type.operator == 'in':
        # Handle list values
        if isinstance(filter_value, str) and ',' in filter_value:
            filter_value = [v.strip() for v in filter_value.split(',')]
        elif not isinstance(filter_value, (list, tuple)):
            filter_value = [filter_value]
            
        if filter_type.name == 'Not In List':
            return ~Q(**{f'{field_path}__in': filter_value})
        return Q(**{f'{field_path}__in': filter_value})
    elif filter_type.operator == 'range':
        # Handle range values
        if isinstance(filter_value, str):
            if ',' in filter_value:
                start, end = filter_value.split(',', 1)
                return Q(**{f'{field_path}__range': (start.strip(), end.strip())})
            else:
                # Single value, can't do range
                return None
        elif isinstance(filter_value, (list, tuple)) and len(filter_value) == 2:
            return Q(**{f'{field_path}__range': filter_value})
        return None
    elif filter_type.operator == 'isnull':
        # Convert string 'true'/'false' to boolean
        if isinstance(filter_value, str):
            filter_value = filter_value.lower() == 'true'
        
        if filter_type.name == 'Is Not Null':
            return Q(**{f'{field_path}__isnull': False})
        return Q(**{f'{field_path}__isnull': True})
    elif filter_type.operator == 'regex':
        return Q(**{f'{field_path}__regex': filter_value})
    elif filter_type.operator == 'iregex':
        return Q(**{f'{field_path}__iregex': filter_value})
    elif filter_type.operator == 'day':
        return Q(**{f'{field_path}__day': filter_value})
    elif filter_type.operator == 'month':
        return Q(**{f'{field_path}__month': filter_value})
    elif filter_type.operator == 'year':
        return Q(**{f'{field_path}__year': filter_value})
    elif filter_type.operator == 'week_day':
        return Q(**{f'{field_path}__week_day': filter_value})
    
    # If we reach here, the operator isn't supported
    return None

def convert_value_to_proper_type(value, field_type):
    """
    Convert a value to the appropriate Python type based on Django field type

    :param value: The value to convert
    :param field_type: Django field type string
    :return: Converted value
    """
    if value is None:
        return None
    
    if field_type in ('IntegerField', 'AutoField', 'BigIntegerField', 'SmallIntegerField', 'PositiveIntegerField'):
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0
    
    elif field_type in ('FloatField', 'DecimalField'):
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    
    elif field_type == 'BooleanField':
        if isinstance(value, str):
            return value.lower() in ('true', 'yes', '1', 't', 'y')
        return bool(value)
    
    elif field_type in ('DateField', 'DateTimeField'):
        if isinstance(value, (datetime.date, datetime.datetime)):
            return value
            
        # Handle special dynamic values
        if value == 'today':
            return datetime.date.today()
        elif value == 'yesterday':
            return datetime.date.today() - datetime.timedelta(days=1)
        elif value == 'tomorrow':
            return datetime.date.today() + datetime.timedelta(days=1)
        elif value == 'this_month_start':
            today = datetime.date.today()
            return datetime.date(today.year, today.month, 1)
        elif value == 'this_month_end':
            today = datetime.date.today()
            if today.month == 12:
                next_month = datetime.date(today.year + 1, 1, 1)
            else:
                next_month = datetime.date(today.year, today.month + 1, 1)
            return next_month - datetime.timedelta(days=1)
        
        # Try to parse the date string
        try:
            # Try common formats
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d']:
                try:
                    return datetime.datetime.strptime(value, fmt).date()
                except ValueError:
                    continue
            
            # If none of the formats worked, try the datetime parser
            from dateutil import parser
            return parser.parse(value)
        except:
            # Return current date as fallback
            return datetime.date.today()
    
    # Default to returning the original value
    return value