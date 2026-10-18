"""``{% workflow_transitions job as transitions %}`` — the transitions the
viewer can take on a job or phase now, from :mod:`jobtracker.workflow` (the
same list the API returns), each with its ``url``."""

from django import template
from django.urls import reverse

from ..models import Job
from ..policy import PolicyContext
from ..workflow import available_transitions

register = template.Library()


@register.simple_tag(takes_context=True)
def workflow_transitions(context, obj):
    request = context.get("request")
    if request is None or not request.user.is_authenticated:
        return []
    policy = getattr(request, "_chaotica_policy", None) or PolicyContext(request.user)
    out = []
    for t in available_transitions(policy, obj):
        if not t["allowed"]:
            continue
        if isinstance(obj, Job):
            url = reverse("job_update_workflow", args=[obj.slug, t["target"]])
        else:
            url = reverse(
                "phase_update_workflow", args=[obj.job.slug, obj.slug, t["target"]]
            )
        out.append({**t, "url": url})
    return out
