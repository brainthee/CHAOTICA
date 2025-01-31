from django import template

register = template.Library()

@register.simple_tag
def get_available_days_in_range(user, start_date, end_date):
    return user.get_available_days_in_range(start_date, end_date)

@register.simple_tag
def get_user_working_days_range(user, org, start_date, end_date):
    return user.get_working_days_in_range(org, start_date, end_date)