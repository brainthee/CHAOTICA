"""Forms for the dynamic Service scoping management UI.

Kept in a separate module from the (very large) ``forms.py`` to reduce merge
churn and keep the scoping feature self-contained.
"""

from django import forms
from django.forms import inlineformset_factory
from crispy_forms.helper import FormHelper

from .models.scoping import (
    ScopingTemplate,
    ScopingField,
    ScopingMacro,
)


class ScopingTemplateForm(forms.ModelForm):
    class Meta:
        model = ScopingTemplate
        fields = [
            "name",
            "description",
            "is_active",
            "calc_mode",
            "sizing_combine",
            "testing_expression",
            "reporting_macro",
            "reporting_expression",
        ]
        widgets = {
            "testing_expression": forms.Textarea(attrs={"rows": 2, "class": "font-monospace"}),
            "reporting_expression": forms.Textarea(attrs={"rows": 2, "class": "font-monospace"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.fields["reporting_macro"].queryset = ScopingMacro.objects.all()


class ScopingFieldForm(forms.ModelForm):
    class Meta:
        model = ScopingField
        fields = [
            "order",
            "label",
            "slug",
            "field_type",
            "help_text",
            "required",
            "default",
            "options",
            "calc_role",
            "rate",
            "weight",
        ]
        widgets = {
            "options": forms.Textarea(
                attrs={
                    "rows": 2,
                    "class": "font-monospace",
                    "placeholder": '[{"value": "ipt", "label": "Internal Pen", "weight": 12}]',
                }
            ),
            "help_text": forms.TextInput(),
        }

    def clean_slug(self):
        # Allow blank; the model's save() will derive it from the label.
        return self.cleaned_data.get("slug", "").strip()

    def clean_options(self):
        """Validate that options is a list of {value,label[,weight]} dicts."""
        options = self.cleaned_data.get("options")
        if options in (None, "", []):
            return []
        if not isinstance(options, list):
            raise forms.ValidationError("Options must be a JSON list.")
        for opt in options:
            if not isinstance(opt, dict) or "value" not in opt or "label" not in opt:
                raise forms.ValidationError(
                    "Each option needs at least 'value' and 'label' keys."
                )
        return options


ScopingFieldFormSet = inlineformset_factory(
    ScopingTemplate,
    ScopingField,
    form=ScopingFieldForm,
    extra=1,
    can_delete=True,
)


class ScopingMacroForm(forms.ModelForm):
    class Meta:
        model = ScopingMacro
        fields = ["name", "description", "expression"]
        widgets = {
            "expression": forms.Textarea(attrs={"rows": 2, "class": "font-monospace"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False


class ScopingImportForm(forms.Form):
    file = forms.FileField(
        label="Scoping pack (JSON)",
        help_text="A .json file previously exported from CHAOTICA.",
    )
    overwrite = forms.BooleanField(
        required=False,
        initial=False,
        label="Overwrite templates/macros with the same name",
    )
