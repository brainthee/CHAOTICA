from django.conf import settings
from constance import config
from django.template import loader
from django.utils import timezone
from django.http import (
    HttpResponse,
)
from guardian.decorators import permission_required_or_403
from .models import RMSyncRecord
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import (
    require_safe,
)
from chaotica_utils.views import page_defaults


@permission_required_or_403("chaotica_utils.manage_site_settings")
@require_safe
def rm_settings(request):
    context = {
        "sync_records": RMSyncRecord.objects.all(),
    }
    template = loader.get_template("rm_sync_settings.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))