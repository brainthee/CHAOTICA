"""Platform: instance metadata, the caller's profile, search."""

from rest_framework import serializers

from ..fields import RefField, RefSerializer, WebUrlField


class MetaOAuthSerializer(serializers.Serializer):
    authorize_url = serializers.CharField()
    token_url = serializers.CharField()
    revoke_url = serializers.CharField()
    scopes = serializers.ListField(child=serializers.CharField())
    pkce = serializers.CharField()
    client_id = serializers.CharField(allow_null=True)


class MetaAuthSerializer(serializers.Serializer):
    session = serializers.BooleanField()
    local_login = serializers.BooleanField()
    sso = serializers.BooleanField()
    login_url = serializers.CharField()
    token_url = serializers.CharField(allow_null=True)
    oauth = MetaOAuthSerializer(allow_null=True)


class MetaBrandingSerializer(serializers.Serializer):
    site_name = serializers.CharField()
    logo_url = serializers.CharField(allow_null=True)


class MetaSerializer(serializers.Serializer):
    """Schema for ``/meta/`` (assembled in the view)."""

    name = serializers.CharField()
    version = serializers.CharField(allow_null=True)  # null when anonymous
    api_version = serializers.CharField()
    web_base_url = serializers.CharField()
    ws_url = serializers.CharField()
    maintenance = serializers.BooleanField()
    features = serializers.DictField(child=serializers.BooleanField())
    auth = MetaAuthSerializer()
    branding = MetaBrandingSerializer()


class MembershipSerializer(serializers.Serializer):
    unit = RefField()
    roles = serializers.SerializerMethodField()

    def get_roles(self, membership) -> list[str]:
        return [r.name for r in membership.roles.all()]


class MeSerializer(serializers.Serializer):
    """The caller (from ``chaotica_utils.selectors.users.current_user_profile``)."""

    id = serializers.IntegerField(source="user.pk")
    display = serializers.CharField(source="user.__str__")
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")
    email = serializers.EmailField(source="user.email")
    avatar_url = serializers.SerializerMethodField()
    job_title = serializers.CharField(source="user.job_title", allow_null=True)
    job_level = serializers.CharField(source="job_level.short_label", default=None)
    job_level_label = serializers.CharField(source="job_level.long_label", default=None)
    tz = serializers.SerializerMethodField()
    theme = serializers.CharField(source="user.site_theme")
    city = RefField(source="user.city")
    country = serializers.CharField(source="user.country", allow_null=True)
    units = MembershipSerializer(source="memberships", many=True)
    manager = RefField(source="user.manager")
    acting_manager = RefField(source="user.acting_manager")
    global_roles = serializers.ListField(child=serializers.CharField())
    capabilities = serializers.DictField(child=serializers.BooleanField())
    web_url = WebUrlField(source="user")

    def get_avatar_url(self, profile) -> str:
        url = profile["user"].get_avatar_url()
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url

    def get_tz(self, profile) -> str:
        return profile["user"].pref_timezone or "UTC"


class PreferencesSerializer(serializers.Serializer):
    theme = serializers.CharField(source="site_theme")
    tz = serializers.SerializerMethodField()
    show_help = serializers.BooleanField()
    scheduler_default_filter = serializers.CharField()

    def get_tz(self, user) -> str:
        return user.pref_timezone or "UTC"


class RealtimeTicketSerializer(serializers.Serializer):
    ticket = serializers.CharField()
    expires_in = serializers.IntegerField(help_text="Seconds.")
    ws_url = serializers.CharField()


class SearchGroupSerializer(serializers.Serializer):
    type = serializers.CharField()
    label = serializers.CharField()
    results = RefSerializer(many=True)


class SearchResultsSerializer(serializers.Serializer):
    q = serializers.CharField()
    groups = SearchGroupSerializer(many=True)
