from django import forms
from django.utils.translation import gettext_lazy as _
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Div, Field, HTML, ButtonHolder

class ReportDesignerBaseForm(forms.Form):
    """Base form for report wizard steps"""
    def __init__(self, *args, **kwargs):
        self.report_data = kwargs.pop('report_data', {})
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = True
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-8'