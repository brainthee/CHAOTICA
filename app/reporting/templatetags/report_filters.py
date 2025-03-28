from django import template

register = template.Library()

@register.filter(name='startswith')
def startswith(value, arg):
    """Check if a string starts with a given prefix."""
    return value.startswith(arg)

@register.filter(name='getattribute')
def getattribute(obj, attr):
    """Get attribute dynamically from an object"""
    if hasattr(obj, attr):
        return getattr(obj, attr)
    try:
        return obj.get(attr)
    except (TypeError, KeyError, AttributeError):
        return None

@register.filter
def add(value, arg):
    """Concatenate two strings"""
    return str(value) + str(arg)