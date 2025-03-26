from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Get an item from a dictionary using a variable key.
    Usage: {{ dictionary|get_item:key }}
    """
    if dictionary is None:
        return None
    
    # Try to get the item using the key directly
    try:
        return dictionary.get(key)
    except (KeyError, AttributeError, TypeError):
        # If that fails, try converting the key to string
        try:
            return dictionary.get(str(key))
        except (KeyError, AttributeError, TypeError):
            return None