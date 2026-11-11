"""Dynamic, data-driven scoping for Services.

A :class:`ScopingTemplate` is an admin-authored questionnaire (a set of
:class:`ScopingField` rows) plus a calculation that turns the captured answers
into *testing* and *reporting* effort. Templates are reusable: a Service points
at one, and many Services may share the same template.

Nothing in this module encodes any particular organisation's scoping rules.
Every field, rate, weight and formula is data, authored at runtime and
exportable/importable as a JSON "scoping pack". The only executable logic is a
sandboxed arithmetic evaluator (see ``jobtracker.utils.scoping``).
"""

from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils.text import slugify
from django.db.models.functions import Lower
from django.db.models import JSONField
from simple_history.models import HistoricalRecords
from django_bleach.models import BleachField


class ScopingFieldType(models.IntegerChoices):
    NUMBER = 0, "Number"
    BOOLEAN = 1, "Checkbox (yes/no)"
    SELECT = 2, "Dropdown (single choice)"
    TEXT = 3, "Short text"
    TEXTAREA = 4, "Long text"


class ScopingCalcRole(models.IntegerChoices):
    NONE = 0, "Display only (not used in calculation)"
    SIZING = 1, "Sizing metric (value ÷ rate = days)"
    ADDITIVE = 2, "Additive modifier (adds days)"
    MULTIPLIER = 3, "Multiplier (adds a percentage)"
    MODE = 4, "Mode selector (chosen option sets the rate)"


class SizingCombine(models.IntegerChoices):
    MAX = 0, "Largest sizing metric wins (max)"
    SUM = 1, "Add sizing metrics together (sum)"


class CalcMode(models.IntegerChoices):
    DECLARATIVE = 0, "Declarative (build from field rates/weights)"
    EXPRESSION = 1, "Expression (write a formula)"


class ScopingMacro(models.Model):
    """A reusable, named arithmetic expression.

    Lets shared post-processing (e.g. a reporting-days formula) live in one
    editable place rather than being copy-pasted across templates. Macros are
    referenced from a template's reporting step and may be called from
    expressions via their slug.
    """

    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.CharField(max_length=500, blank=True, default="")
    expression = models.TextField(
        help_text="Arithmetic expression. Available variables depend on the "
        "caller; the reporting step receives 'testing_days'.",
    )
    history = HistoricalRecords()

    class Meta:
        ordering = [Lower("name")]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class ScopingTemplate(models.Model):
    """A reusable scoping questionnaire + calculation for a kind of service."""

    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = BleachField(blank=True, null=True, help_text="What this template is for")
    is_active = models.BooleanField(
        default=True, help_text="Inactive templates cannot be attached to services"
    )

    # --- calculation configuration -------------------------------------
    calc_mode = models.IntegerField(
        choices=CalcMode.choices, default=CalcMode.DECLARATIVE
    )
    sizing_combine = models.IntegerField(
        choices=SizingCombine.choices,
        default=SizingCombine.MAX,
        help_text="How to combine multiple sizing metrics in declarative mode",
    )
    testing_expression = models.TextField(
        blank=True,
        default="",
        help_text="Expression mode only: formula for testing days. References "
        "field slugs, e.g. max(pages / 15, inputs / 200).",
    )
    reporting_macro = models.ForeignKey(
        ScopingMacro,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="templates",
        help_text="Reusable formula that derives reporting days from "
        "'testing_days'. If unset, reporting_expression is used.",
    )
    reporting_expression = models.TextField(
        blank=True,
        default="testing_days / 4",
        help_text="Fallback reporting-days formula when no macro is set. "
        "Receives 'testing_days'.",
    )

    data = JSONField(verbose_name="Data", null=True, blank=True, default=dict)
    history = HistoricalRecords()

    class Meta:
        ordering = [Lower("name")]
        permissions = (("manage_scoping", "Manage Scoping Templates"),)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("scoping_template_detail", kwargs={"slug": self.slug})


class ScopingField(models.Model):
    """One question within a :class:`ScopingTemplate`."""

    template = models.ForeignKey(
        ScopingTemplate, on_delete=models.CASCADE, related_name="fields"
    )
    label = models.CharField(max_length=255)
    slug = models.SlugField(
        max_length=100,
        help_text="Short identifier used in formulas (e.g. 'live_ips')",
    )
    help_text = models.CharField(max_length=500, blank=True, default="")
    order = models.PositiveIntegerField(default=0)
    field_type = models.IntegerField(
        choices=ScopingFieldType.choices, default=ScopingFieldType.NUMBER
    )
    required = models.BooleanField(default=False)
    default = models.CharField(max_length=255, blank=True, default="")

    # Options for SELECT fields: list of {"value","label","weight"} dicts.
    # 'weight' meaning depends on calc_role (rate for MODE, days/fraction
    # otherwise); it is optional and defaults to 0.
    options = JSONField(blank=True, null=True, default=list)

    # --- calculation role ----------------------------------------------
    calc_role = models.IntegerField(
        choices=ScopingCalcRole.choices, default=ScopingCalcRole.NONE
    )
    rate = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="SIZING: units covered per day (value ÷ rate = days)",
    )
    weight = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="ADDITIVE: days to add. MULTIPLIER: fraction, e.g. 0.1 = +10%.",
    )

    data = JSONField(blank=True, null=True, default=dict)

    class Meta:
        ordering = ["order", "id"]
        unique_together = ("template", "slug")

    def __str__(self):
        return "{} / {}".format(self.template.name, self.label)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.label)[:100]
        super().save(*args, **kwargs)
