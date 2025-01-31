from django import template

register = template.Library()

@register.simple_tag
def get_org_working_days_range(org, start_date, end_date):
    return org.get_working_days_in_range(start_date, end_date)