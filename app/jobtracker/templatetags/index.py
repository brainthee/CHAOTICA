from django import template
from chaotica_utils.enums import *
from pprint import pprint
import datetime

register = template.Library()

@register.filter
def index(indexable, i):
    return indexable[i]

@register.simple_tag
def get_slotType_usage_perc(obj, slotType):
    return obj.get_slotType_usage_perc(slotType)

@register.simple_tag
def get_total_scheduled_by_type(obj, slotType):
    return obj.get_total_scheduled_by_type(slotType)

@register.simple_tag
def get_total_scoped_by_type(obj, slotType):
    return obj.get_total_scoped_by_type(slotType)

@register.simple_tag
def get_unit_role_display(role):
    return UnitRoles.CHOICES[role][1]

@register.simple_tag
def getRange(number):
    return range(number)

@register.simple_tag
def PyDateToJSDate(date):
    if type(date) == datetime.datetime:
        return str(date.strftime('%Y-%m-%d'))
    else:
        return ""