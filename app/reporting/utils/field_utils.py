from django.db import models
from django.db.models.fields.related import ForeignKey, ManyToManyField
from django.contrib.contenttypes.fields import GenericForeignKey

def get_model_fields(model_class, exclude_fields=None, include_relations=True):
    """
    Get all fields from a Django model class

    :param model_class: Django model class
    :param exclude_fields: List of field names to exclude
    :param include_relations: Whether to include relation fields
    :return: List of field info dictionaries
    """
    exclude_fields = exclude_fields or []
    fields = []
    
    for field in model_class._meta.get_fields():
        # Skip many-to-many relationships if not including relations
        if not include_relations and isinstance(field, ManyToManyField):
            continue
            
        # Skip fields that are in the exclude list
        if field.name in exclude_fields:
            continue
            
        # Skip generic foreign keys
        if isinstance(field, GenericForeignKey):
            continue
            
        # Create field info
        field_info = {
            'name': field.name,
            'verbose_name': getattr(field, 'verbose_name', field.name),
            'field_type': field.__class__.__name__,
            'is_relation': field.is_relation,
            'related_model': field.related_model.__name__ if field.is_relation and field.related_model else None,
        }
        
        fields.append(field_info)
    
    return fields

def get_field_type_for_django_field(field):
    """
    Get the appropriate field type for a Django field

    :param field: Django model field
    :return: String representing the field type
    """
    if isinstance(field, models.CharField) or isinstance(field, models.TextField):
        return 'text'
    elif isinstance(field, models.IntegerField) or isinstance(field, models.BigIntegerField):
        return 'integer'
    elif isinstance(field, models.FloatField) or isinstance(field, models.DecimalField):
        return 'decimal'
    elif isinstance(field, models.BooleanField):
        return 'boolean'
    elif isinstance(field, models.DateField):
        return 'date'
    elif isinstance(field, models.DateTimeField):
        return 'datetime'
    elif isinstance(field, models.TimeField):
        return 'time'
    elif isinstance(field, models.ForeignKey) or isinstance(field, models.OneToOneField):
        return 'foreign_key'
    elif isinstance(field, models.ManyToManyField):
        return 'many_to_many'
    elif isinstance(field, models.JSONField):
        return 'json'
    else:
        return 'text'  # Default to text for unknown field types

def get_related_fields(model_class, max_depth=2, current_depth=0, path='', visited=None):
    """
    Recursively get all fields from a model and its related models

    :param model_class: Django model class
    :param max_depth: Maximum depth to traverse relationships
    :param current_depth: Current depth of traversal
    :param path: Current field path (dot-separated)
    :param visited: Set of visited models to prevent circular references
    :return: List of field info dictionaries
    """
    if visited is None:
        visited = set()
        
    # Don't revisit models or exceed max depth
    if model_class in visited or current_depth > max_depth:
        return []
    
    visited.add(model_class)
    fields = []
    
    for field in model_class._meta.get_fields():
        # Skip many-to-many relationships at deep levels to prevent complexity
        if current_depth > 0 and isinstance(field, ManyToManyField):
            continue
            
        # Skip generic foreign keys
        if isinstance(field, GenericForeignKey):
            continue
        
        # Build the full field path
        field_path = f"{path}{field.name}" if path else field.name
        
        # Get field info
        field_info = {
            'name': field.name,
            'verbose_name': getattr(field, 'verbose_name', field.name),
            'field_type': get_field_type_for_django_field(field),
            'path': field_path,
            'is_relation': field.is_relation,
        }
        
        fields.append(field_info)
        
        # Recursively get fields from related models
        if field.is_relation and field.related_model and not field.many_to_many:
            related_fields = get_related_fields(
                field.related_model,
                max_depth=max_depth,
                current_depth=current_depth + 1,
                path=f"{field_path}__",
                visited=visited.copy()
            )
            fields.extend(related_fields)
    
    return fields

def get_model_field_choices(model_class, include_relations=True):
    """
    Get field choices for a model, suitable for form select fields

    :param model_class: Django model class
    :param include_relations: Whether to include relation fields
    :return: List of (field_path, verbose_name) tuples
    """
    fields = get_model_fields(model_class, include_relations=include_relations)
    choices = [(field['name'], field['verbose_name']) for field in fields]
    return choices

def format_field_value(value, field_type, format_string=None):
    """
    Format a field value based on its type and format string

    :param value: The value to format
    :param field_type: Field type string
    :param format_string: Optional format string
    :return: Formatted value
    """
    if value is None:
        return ''
    
    if field_type == 'date' and hasattr(value, 'strftime'):
        if format_string:
            return value.strftime(format_string)
        return value.strftime('%Y-%m-%d')
    
    if field_type == 'datetime' and hasattr(value, 'strftime'):
        if format_string:
            return value.strftime(format_string)
        return value.strftime('%Y-%m-%d %H:%M:%S')
    
    if field_type == 'decimal' or field_type == 'float':
        if format_string:
            return format_string.format(value)
        return f"{value:.2f}"
    
    if field_type == 'boolean':
        return 'Yes' if value else 'No'
    
    # Default to string representation
    return str(value)

def get_field_groups(fields):
    """
    Group fields by their group property

    :param fields: List of field objects
    :return: Dictionary of grouped fields
    """
    groups = {}
    
    for field in fields:
        group_name = field.group or 'General'
        if group_name not in groups:
            groups[group_name] = []
        groups[group_name].append(field)
    
    return groups