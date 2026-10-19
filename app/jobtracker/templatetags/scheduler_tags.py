"""``{% scheduler_v1_config "job" job %}`` — the ``v1`` block of a page's
``SCHEDULER_CONFIG``: the /api/v1/ feeds the vis-timeline scheduler reads."""

import json

from constance import config
from django import template
from django.urls import reverse
from django.utils.safestring import mark_safe

register = template.Library()

_SCOPED = {"job": "api_v1:job-schedule", "phase": "api_v1:phase-schedule",
           "project": "api_v1:project-schedule"}


@register.simple_tag
def scheduler_v1_config(scope, obj=None):
    if scope in _SCOPED:
        schedule = reverse(_SCOPED[scope], args=[obj.pk])
        scope_param = f"{scope}={obj.pk}"
    else:
        schedule = reverse("api_v1:schedule-list")
        scope_param = ""
    block = {
        "schedule": schedule,
        "resources": reverse("api_v1:schedule-resources"),
        "bounds": reverse("api_v1:schedule-bounds"),
        "actions": reverse("api_v1:schedule-actions"),
        "deltas": reverse("api_v1:schedule-deltas"),
        "scope": scope_param,
        "shadeAvailable": bool(config.SCHEDULE_SHADE_AVAILABLE),
        "availableColour": str(config.SCHEDULE_COLOR_AVAILABLE),
    }
    # JSON is valid JS; escape "</" so it can't close the <script>.
    return mark_safe(json.dumps(block).replace("</", "<\\/"))
