from django import template

register = template.Library()


@register.simple_tag
def get_user_skill(user, skill):
    if user.skills.filter(skill=skill).exists():
        return user.skills.get(skill=skill)
    else:
        return None


@register.filter
def lookup(dictionary, key):
    """Template filter to lookup dictionary values by key"""
    return dictionary.get(key)
