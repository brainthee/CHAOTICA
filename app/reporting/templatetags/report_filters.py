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

@register.filter
def get(dictionary, key):
    """Get a value from a dictionary by key"""
    if dictionary is None:
        return None
    try:
        return dictionary.get(str(key))
    except (AttributeError, KeyError, TypeError):
        return None

@register.filter
def default(value, arg):
    """Return a default value if the original is empty or None"""
    if value is None or value == "":
        return arg
    return value