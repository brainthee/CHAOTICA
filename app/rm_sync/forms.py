from django import forms
from .models import RMSyncRecord
from crispy_forms.helper import FormHelper
from dal import autocomplete


class RMSyncRecordForm(forms.ModelForm):
    rm_id = forms.CharField(required=False)

    class Meta:
        model = RMSyncRecord
        fields = ("user",
                  "rm_id",
                  "sync_enabled",
                  "sync_authoritative",
                  )