from django.template import Template
from django.template.loader import render_to_string
from crispy_forms.layout import TemplateNameMixin
from crispy_forms.utils import TEMPLATE_PACK, flatatt

class WizardButton(TemplateNameMixin):

    template = "%s/layout/button.html"
    field_classes = "multisteps-form__progress-btn"

    def __init__(self, content, css_id=None, css_class=None, template=None, **kwargs):
        self.content = content
        self.template = template or self.template

        kwargs.setdefault("type", "button")

        # We turn css_id and css_class into id and class
        if css_id:
            kwargs["id"] = css_id

        kwargs["class"] = self.field_classes
        if css_class:
            kwargs["class"] += f" {css_class}"

        self.flat_attrs = flatatt(kwargs)

    def render(self, form, context, template_pack=TEMPLATE_PACK, **kwargs):
        self.content = Template(str(self.content)).render(context)
        template = self.get_template_name(template_pack)
        context.update({"button": self})

        return render_to_string(template, context.flatten())