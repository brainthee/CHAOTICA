from django import template

register = template.Library()


@register.simple_tag
def can_auth(leave, user):
    return leave.can_user_auth(user)
