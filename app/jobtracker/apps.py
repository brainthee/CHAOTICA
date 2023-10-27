from django.apps import AppConfig
from django.db import connections
from .enums import DefaultTimeSlotTypes


def table_exists(table_name: str) -> bool:
    return table_name in connections["default"].introspection.table_names()


def populate_timeslot_types():
    from .models import TimeSlotType

    if table_exists("jobtracker_timeslottype"):
        for default_type in DefaultTimeSlotTypes.DEFAULTS:
            instance, created = TimeSlotType.objects.get_or_create(
                pk=default_type['pk'], defaults=default_type)
            if not created:
                for attr, value in default_type.items(): 
                    setattr(instance, attr, value)
                instance.save()
    

class JobtrackerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "jobtracker"

    def ready(self):
        populate_timeslot_types()