from django import template
from chaotica_utils.enums import *
from pprint import pprint
register = template.Library()

@register.filter
def index(indexable, i):
    return indexable[i]

@register.simple_tag
def get_slotType_usage_perc(job, slotType):
    return job.get_slotType_usage_perc(slotType)

@register.simple_tag
def get_total_scheduled_by_type(job, slotType):
    return job.get_total_scheduled_by_type(slotType)

@register.simple_tag
def get_total_scoped_by_type(job, slotType):
    return job.get_total_scoped_by_type(slotType)

@register.simple_tag
def get_unit_role_display(role):
    return UnitRoles.CHOICES[role][1]

@register.simple_tag
def getRange(number):
    return range(number)

@register.simple_tag
def PyDateToJSDate(date):
    return str(date.strftime('%Y-%m-%d'))