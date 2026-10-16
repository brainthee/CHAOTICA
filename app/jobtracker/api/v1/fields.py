"""References: how every foreign key is rendered in /api/v1/.

    {"id": 12, "type": "client", "display": "Daystrom",
     "url": "/api/v1/clients/12/", "web_url": "https://…/client/daystrom/"}

``url`` is the API resource (null when the type has no endpoint), ``web_url``
the main-UI page (absolute when a request is in context, else a path; null
when there is none).
"""

from django.urls import NoReverseMatch, reverse
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


def _slug_url(obj):
    # Client/Service/Skill/OrgUnit get_absolute_url() *save* to fill an empty
    # slug — never write from a read.
    return obj.get_absolute_url() if getattr(obj, "slug", None) else None


def _user_display(user):
    return str(user)


def _phase_display(phase):
    return f"{phase.phase_id} {phase.title}".strip()


class RefType:
    def __init__(self, type, basename=None, display=str, web_url=None):
        self.type = type
        self.basename = basename
        self.display = display
        self.web_url = web_url


def _registry():
    from cities_light.models import City
    from chaotica_utils.models import User
    from chaotica_utils.models.leave import LeaveRequest
    from ...models import (
        AwardingBody,
        Client,
        Contact,
        FrameworkAgreement,
        Job,
        OrganisationalUnit,
        Phase,
        Project,
        Qualification,
        QualificationTag,
        Service,
        Skill,
        SkillCategory,
        TimeSlot,
        TimeSlotType,
    )

    return {
        User: RefType("user", "user", _user_display, lambda o: o.get_absolute_url()),
        OrganisationalUnit: RefType("org_unit", "org-unit", str, _slug_url),
        Client: RefType("client", "client", str, _slug_url),
        Contact: RefType(
            "contact",
            None,
            lambda c: f"{c.first_name} {c.last_name}".strip(),
            lambda c: (
                reverse(
                    "client_contact_detail",
                    kwargs={"client_slug": c.company.slug, "pk": c.pk},
                )
                if c.company.slug
                else None
            ),
        ),
        FrameworkAgreement: RefType(
            "framework",
            None,
            lambda f: f.name,
            lambda f: f.get_absolute_url() if f.client.slug else None,
        ),
        Job: RefType("job", "job", str, lambda o: o.get_absolute_url()),
        Phase: RefType(
            "phase", "phase", _phase_display, lambda o: o.get_absolute_url()
        ),
        Project: RefType("project", "project", str, lambda o: o.get_absolute_url()),
        Service: RefType("service", "service", str, _slug_url),
        Skill: RefType("skill", "skill", lambda s: s.name, _slug_url),
        SkillCategory: RefType(
            "skill_category", "skill-category", str, lambda o: o.get_absolute_url()
        ),
        Qualification: RefType(
            "qualification", "qualification", str, lambda o: o.get_absolute_url()
        ),
        TimeSlotType: RefType("timeslot_type", "timeslot-type", lambda t: t.name),
        LeaveRequest: RefType("leave_request", "leave-request", lambda l: str(l.pk)),
        AwardingBody: RefType("awarding_body", None, lambda b: b.name),
        QualificationTag: RefType("qualification_tag", None, lambda t: t.name),
        TimeSlot: RefType("timeslot", "timeslot", lambda t: str(t.pk)),
        City: RefType("city", None, lambda c: c.name),
    }


_REGISTRY = None


def ref_type_for(obj):
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _registry()
    for klass in type(obj).__mro__:
        if klass in _REGISTRY:
            return _REGISTRY[klass]
    raise KeyError(f"No RefType registered for {type(obj).__name__}")


def _absolute(request, path):
    if not path:
        return None
    return request.build_absolute_uri(path) if request is not None else path


def make_ref(obj, request=None):
    """Render ``obj`` as a ref dict (``None`` passes through)."""
    if obj is None:
        return None
    rt = ref_type_for(obj)
    url = None
    if rt.basename:
        try:
            url = reverse(f"api_v1:{rt.basename}-detail", kwargs={"pk": obj.pk})
        except NoReverseMatch:
            url = None
    web = None
    if rt.web_url is not None:
        try:
            web = rt.web_url(obj)
        except NoReverseMatch:
            web = None
    return {
        "id": obj.pk,
        "type": rt.type,
        "display": rt.display(obj),
        "url": url,
        "web_url": _absolute(request, web),
    }


class RefSerializer(serializers.Serializer):
    """A reference to another object: its id, type and label, plus links to
    its API resource (``url``) and main-UI page (``web_url``)."""

    id = serializers.IntegerField()
    type = serializers.CharField()
    display = serializers.CharField()
    url = serializers.CharField(allow_null=True)
    web_url = serializers.CharField(allow_null=True)


@extend_schema_field(RefSerializer(allow_null=True))
class RefField(serializers.Field):
    """A foreign key rendered as a ref. Read-only."""

    def __init__(self, **kwargs):
        kwargs["read_only"] = True
        super().__init__(**kwargs)

    def to_representation(self, value):
        return make_ref(value, self.context.get("request"))


@extend_schema_field(RefSerializer(many=True))
class RefListField(serializers.Field):
    """A to-many relation (manager or iterable) rendered as a list of refs."""

    def __init__(self, **kwargs):
        kwargs["read_only"] = True
        super().__init__(**kwargs)

    def to_representation(self, value):
        request = self.context.get("request")
        items = value.all() if hasattr(value, "all") else value
        return [make_ref(o, request) for o in items]


@extend_schema_field(serializers.CharField(allow_null=True))
class WebUrlField(serializers.Field):
    """The object's own main-UI page, absolute. Read-only; ``source='*'``."""

    def __init__(self, **kwargs):
        kwargs["read_only"] = True
        kwargs.setdefault("source", "*")
        super().__init__(**kwargs)

    def to_representation(self, obj):
        rt = ref_type_for(obj)
        if rt.web_url is None:
            return None
        try:
            path = rt.web_url(obj)
        except NoReverseMatch:
            return None
        return _absolute(self.context.get("request"), path)
