"""Connected Apps: OAuth2 clients (e.g. LCARS) registered on the Settings page."""

from urllib.parse import urlsplit

from crispy_forms.helper import FormHelper
from django import forms
from django.conf import settings
from oauth2_provider.models import get_application_model

Application = get_application_model()


def _allowed_schemes():
    return settings.OAUTH2_PROVIDER["ALLOWED_REDIRECT_URI_SCHEMES"]


class ConnectedAppForm(forms.ModelForm):
    """Public clients using the authorization-code flow with PKCE only — no
    client secret, no password or client-credentials grants."""

    redirect_uris = forms.CharField(
        label="Redirect URIs",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="One per line. Exact match; https (http allowed in development).",
    )
    allowed_origins = forms.CharField(
        label="Allowed origins",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="One per line, e.g. https://lcars.example.com — browsers on these "
        "origins may call the API and token endpoints.",
    )
    skip_authorization = forms.BooleanField(
        label="Trusted (skip the consent screen)",
        required=False,
        help_text="Only for first-party apps you run.",
    )

    class Meta:
        model = Application
        fields = ["name", "redirect_uris", "allowed_origins", "skip_authorization"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        # Fixed for every Connected App; set before model validation runs.
        self.instance.client_type = Application.CLIENT_PUBLIC
        self.instance.authorization_grant_type = Application.GRANT_AUTHORIZATION_CODE
        self.instance.client_secret = ""
        self.instance.algorithm = ""

    @staticmethod
    def _lines(value):
        return [v.strip() for v in (value or "").split() if v.strip()]

    def clean_redirect_uris(self):
        uris = self._lines(self.cleaned_data["redirect_uris"])
        if not uris:
            raise forms.ValidationError("Add at least one redirect URI.")
        for uri in uris:
            parts = urlsplit(uri)
            if parts.scheme not in _allowed_schemes() or not parts.netloc:
                raise forms.ValidationError(f"{uri}: use an absolute https URL.")
            if parts.fragment:
                raise forms.ValidationError(f"{uri}: must not contain a #fragment.")
        return " ".join(uris)

    def clean_allowed_origins(self):
        origins = self._lines(self.cleaned_data.get("allowed_origins"))
        for origin in origins:
            parts = urlsplit(origin)
            if (
                parts.scheme not in _allowed_schemes()
                or not parts.netloc
                or parts.path not in ("", "/")
                or parts.query
                or parts.fragment
            ):
                raise forms.ValidationError(
                    f"{origin}: an origin is scheme://host[:port], nothing more."
                )
        return " ".join(o.rstrip("/") for o in origins)

