from django import forms
from .models import RMSyncRecord, RMUnitMap
from crispy_forms.helper import FormHelper

# Note: django-select2 import might be needed if widgets are added later


class RMSyncRecordForm(forms.ModelForm):
    rm_id = forms.CharField(required=False)

    class Meta:
        model = RMSyncRecord
        fields = (
            "user",
            "rm_id",
            "direction",
            "sync_authoritative",
        )


class RMUnitMapForm(forms.ModelForm):
    """Inline edit of a market-unit → OU + direction mapping on the settings page."""

    class Meta:
        model = RMUnitMap
        fields = ("unit", "direction", "enabled")
