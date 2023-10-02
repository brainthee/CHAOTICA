from django.conf import settings
from .models import User
from jobtracker.models import *
import pprint

def defaults(request):
    new_install = User.objects.all().count() <= 1
    setup_unit = OrganisationalUnit.objects.all().count() == 0
    setup_client = Client.objects.all().count() == 0
    setup_service = Service.objects.all().count() == 0

    return {
        'new_install': new_install,
        'setup_unit': setup_unit,
        'setup_client': setup_client,
        'setup_service': setup_service,
    }