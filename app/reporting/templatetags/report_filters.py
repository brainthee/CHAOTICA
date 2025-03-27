# reporting/templatetags/report_filters.py
from django import template

register = template.Library()

@register.filter
def replace(value, arg):
    """Replace all instances of the first argument with the second in the value"""
    if len(arg.split(',')) != 2:
        return value
    
    old, new = arg.split(',')
    return value.replace(old, new)


@register.filter
def underscores_to_spaces(value):
    """Convert underscores to spaces in a string"""
    if value is None:
        return ""
    return value.replace('_', ' ')