from django.conf import settings
from .models import User
from jobtracker.models import OrganisationalUnit, Client, Service

def defaults(_):
    return {}