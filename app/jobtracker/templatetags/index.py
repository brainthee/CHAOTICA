from django import template
from chaotica_utils.enums import UnitRoles
import datetime

register = template.Library()

@register.filter
def index(indexable, i):
    return indexable[i]

@register.simple_tag
def get_slot_type_usage_perc(obj, slot_type):
    return obj.get_slot_type_usage_perc(slot_type)

@register.simple_tag
def get_total_scheduled_by_type(obj, slot_type):
    return obj.get_total_scheduled_by_type(slot_type)

@register.simple_tag
def get_total_scoped_by_type(obj, slot_type):
    return obj.get_total_scoped_by_type(slot_type)

@register.simple_tag
def get_unit_role_display(role):
    return UnitRoles.CHOICES[role][1]

@register.simple_tag
def get_range_from_zero(number):
    rng = range(0, number, 1)
    return rng

@register.simple_tag
def get_range_from_one(number):
    rng = range(1, number+1, 1)
    return rng

@register.simple_tag
def py_date_to_js_date(date):
    if date:
        if isinstance(date, datetime.datetime):
            return str(date.strftime('%Y-%m-%d'))
        elif isinstance(date, datetime.date):
            return str(date.strftime('%Y-%m-%d'))
        else:
            # Try and convert it to a datetime...
            return str(datetime.datetime.strptime(date, "%Y-%m-%d").strftime('%Y-%m-%d'))
    else:
        return ""