from django import template

register = template.Library()

@register.filter(name='startswith')
def startswith(value, arg):
    """Check if a string starts with a given prefix."""
    return value.startswith(arg)