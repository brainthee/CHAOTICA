from django import template
from django.conf import settings
from ..enums import GlobalRoles

register = template.Library()


@register.simple_tag
def has_role(user, required_role):
    if required_role and user.is_authenticated:
        if required_role == "*":
            return user.groups.filter().exists()
        else:
            selected_role = None
            for role, role_label in GlobalRoles.CHOICES:
                if required_role == role_label:
                    selected_role = role
            
            if not selected_role:
                return False
            
            return user.groups.filter(
                name=settings.GLOBAL_GROUP_PREFIX
                + GlobalRoles.CHOICES[selected_role][1]
            ).exists()
    else:
        return False