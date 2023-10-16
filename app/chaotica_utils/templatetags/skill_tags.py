from django import template
register = template.Library()

@register.simple_tag
def get_user_skill(user, skill):
    from jobtracker.models import UserSkill
    if UserSkill.objects.filter(user=user, skill=skill).exists():
        return UserSkill.objects.get(user=user, skill=skill)
    else:
        return None