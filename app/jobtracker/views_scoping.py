"""Views for managing, building, testing and sharing scoping templates."""

import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy, reverse
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from django.views.generic import ListView, DeleteView

from chaotica_utils.mixins import SecurePermissionRequiredMixin as PermissionRequiredMixin
from chaotica_utils.views import ChaoticaBaseView
from chaotica_utils.decorators import permission_required_or_403

from .models.scoping import ScopingTemplate, ScopingMacro
from .forms_scoping import (
    ScopingTemplateForm,
    ScopingFieldFormSet,
    ScopingMacroForm,
    ScopingImportForm,
)
from .scoping_engine import evaluate

logger = logging.getLogger(__name__)

PACK_VERSION = 1
MANAGE_PERM = "jobtracker.manage_scoping"


# ---------------------------------------------------------------------------
# Serialisation (import / export "scoping packs")
# ---------------------------------------------------------------------------

def serialize_macro(macro):
    return {
        "name": macro.name,
        "slug": macro.slug,
        "description": macro.description,
        "expression": macro.expression,
    }


def serialize_field(field):
    return {
        "order": field.order,
        "label": field.label,
        "slug": field.slug,
        "field_type": field.field_type,
        "help_text": field.help_text,
        "required": field.required,
        "default": field.default,
        "options": field.options or [],
        "calc_role": field.calc_role,
        "rate": str(field.rate) if field.rate is not None else None,
        "weight": str(field.weight) if field.weight is not None else None,
    }


def serialize_template(template):
    return {
        "name": template.name,
        "slug": template.slug,
        "description": template.description or "",
        "is_active": template.is_active,
        "calc_mode": template.calc_mode,
        "sizing_combine": template.sizing_combine,
        "testing_expression": template.testing_expression,
        "reporting_expression": template.reporting_expression,
        "reporting_macro": template.reporting_macro.slug if template.reporting_macro else None,
        "fields": [serialize_field(f) for f in template.fields.all()],
    }


def build_pack(templates):
    """Build an export pack dict from an iterable of templates (+ their macros)."""
    macros = {}
    for tmpl in templates:
        if tmpl.reporting_macro:
            macros[tmpl.reporting_macro.slug] = tmpl.reporting_macro
    return {
        "chaotica_scoping_pack": PACK_VERSION,
        "macros": [serialize_macro(m) for m in macros.values()],
        "templates": [serialize_template(t) for t in templates],
    }


def import_pack(data, overwrite=False):
    """Create templates/macros from a pack dict. Returns a list of status strings."""
    from .models.scoping import ScopingField

    if not isinstance(data, dict) or "chaotica_scoping_pack" not in data:
        raise ValueError("Not a valid CHAOTICA scoping pack.")

    report = []

    # Macros first so templates can reference them.
    macro_by_slug = {}
    for m in data.get("macros", []):
        slug = m.get("slug") or slugify(m.get("name", ""))
        existing = ScopingMacro.objects.filter(slug=slug).first()
        if existing and not overwrite:
            macro_by_slug[slug] = existing
            report.append("Macro '{}' already exists — skipped".format(existing.name))
            continue
        if existing:
            existing.delete()
        macro = ScopingMacro.objects.create(
            name=m["name"],
            slug=slug,
            description=m.get("description", ""),
            expression=m.get("expression", ""),
        )
        macro_by_slug[slug] = macro
        report.append("Macro '{}' imported".format(macro.name))

    for t in data.get("templates", []):
        slug = t.get("slug") or slugify(t.get("name", ""))
        existing = ScopingTemplate.objects.filter(slug=slug).first()
        if existing and not overwrite:
            report.append("Template '{}' already exists — skipped".format(existing.name))
            continue
        if existing:
            existing.delete()

        reporting_macro = None
        if t.get("reporting_macro"):
            reporting_macro = macro_by_slug.get(t["reporting_macro"]) or \
                ScopingMacro.objects.filter(slug=t["reporting_macro"]).first()

        template = ScopingTemplate.objects.create(
            name=t["name"],
            slug=slug,
            description=t.get("description", ""),
            is_active=t.get("is_active", True),
            calc_mode=t.get("calc_mode", 0),
            sizing_combine=t.get("sizing_combine", 0),
            testing_expression=t.get("testing_expression", ""),
            reporting_expression=t.get("reporting_expression", "testing_days / 4"),
            reporting_macro=reporting_macro,
        )
        for f in t.get("fields", []):
            ScopingField.objects.create(
                template=template,
                order=f.get("order", 0),
                label=f["label"],
                slug=f.get("slug") or slugify(f["label"])[:100],
                field_type=f.get("field_type", 0),
                help_text=f.get("help_text", ""),
                required=f.get("required", False),
                default=f.get("default", ""),
                options=f.get("options", []),
                calc_role=f.get("calc_role", 0),
                rate=f.get("rate"),
                weight=f.get("weight"),
            )
        report.append(
            "Template '{}' imported ({} fields)".format(template.name, len(t.get("fields", [])))
        )
    return report


# ---------------------------------------------------------------------------
# Template CRUD + builder
# ---------------------------------------------------------------------------

class ScopingTemplateListView(PermissionRequiredMixin, ChaoticaBaseView, ListView):
    model = ScopingTemplate
    permission_required = MANAGE_PERM
    accept_global_perms = True
    return_403 = True
    template_name = "jobtracker/scoping/template_list.html"
    context_object_name = "templates"

    def get_queryset(self):
        return ScopingTemplate.objects.all().prefetch_related("fields", "services")


class ScopingTemplateDeleteView(PermissionRequiredMixin, ChaoticaBaseView, DeleteView):
    model = ScopingTemplate
    permission_required = MANAGE_PERM
    accept_global_perms = True
    return_403 = True
    template_name = "jobtracker/scoping/template_confirm_delete.html"
    success_url = reverse_lazy("scoping_template_list")


@login_required
@permission_required_or_403(MANAGE_PERM, accept_global_perms=True)
def scoping_template_edit(request, slug=None):
    """Create or edit a template: the builder page (template form + field formset)."""
    template = get_object_or_404(ScopingTemplate, slug=slug) if slug else None

    if request.method == "POST":
        form = ScopingTemplateForm(request.POST, instance=template)
        if form.is_valid():
            template = form.save()
            formset = ScopingFieldFormSet(request.POST, instance=template)
            if formset.is_valid():
                formset.save()
                messages.success(request, "Scoping template saved.")
                return redirect("scoping_template_edit", slug=template.slug)
        else:
            formset = ScopingFieldFormSet(request.POST, instance=template)
    else:
        form = ScopingTemplateForm(instance=template)
        formset = ScopingFieldFormSet(instance=template)

    return render(
        request,
        "jobtracker/scoping/template_edit.html",
        {"form": form, "formset": formset, "template": template},
    )


# ---------------------------------------------------------------------------
# Live test / calculate endpoint
# ---------------------------------------------------------------------------

@require_POST
@login_required
@permission_required_or_403(MANAGE_PERM, accept_global_perms=True)
def scoping_template_calc(request, slug):
    """Evaluate a template against posted answers; returns JSON for the test panel."""
    template = get_object_or_404(ScopingTemplate, slug=slug)
    try:
        answers = json.loads(request.body.decode("utf-8") or "{}").get("answers", {})
    except (ValueError, AttributeError):
        answers = {}
    return JsonResponse(evaluate(template, answers))


# ---------------------------------------------------------------------------
# Import / export
# ---------------------------------------------------------------------------

@login_required
@permission_required_or_403(MANAGE_PERM, accept_global_perms=True)
def scoping_template_export(request, slug=None):
    """Export one template, or all templates when no slug is given, as a JSON pack."""
    if slug:
        templates = [get_object_or_404(ScopingTemplate, slug=slug)]
        filename = "scoping-pack-{}.json".format(slug)
    else:
        templates = list(ScopingTemplate.objects.all().prefetch_related("fields"))
        filename = "scoping-pack-all.json"
    pack = build_pack(templates)
    response = HttpResponse(
        json.dumps(pack, indent=2), content_type="application/json"
    )
    response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
    return response


@login_required
@permission_required_or_403(MANAGE_PERM, accept_global_perms=True)
def scoping_import(request):
    if request.method == "POST":
        form = ScopingImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                data = json.loads(form.cleaned_data["file"].read().decode("utf-8"))
                report = import_pack(data, overwrite=form.cleaned_data["overwrite"])
            except (ValueError, KeyError) as exc:
                messages.error(request, "Import failed: {}".format(exc))
                return redirect("scoping_import")
            for line in report:
                messages.info(request, line)
            messages.success(request, "Scoping pack imported.")
            return redirect("scoping_template_list")
    else:
        form = ScopingImportForm()
    return render(request, "jobtracker/scoping/import.html", {"form": form})


# ---------------------------------------------------------------------------
# Macro CRUD (minimal)
# ---------------------------------------------------------------------------

class ScopingMacroListView(PermissionRequiredMixin, ChaoticaBaseView, ListView):
    model = ScopingMacro
    permission_required = MANAGE_PERM
    accept_global_perms = True
    return_403 = True
    template_name = "jobtracker/scoping/macro_list.html"
    context_object_name = "macros"


@login_required
@permission_required_or_403(MANAGE_PERM, accept_global_perms=True)
def scoping_macro_edit(request, slug=None):
    macro = get_object_or_404(ScopingMacro, slug=slug) if slug else None
    if request.method == "POST":
        form = ScopingMacroForm(request.POST, instance=macro)
        if form.is_valid():
            form.save()
            messages.success(request, "Macro saved.")
            return redirect("scoping_macro_list")
    else:
        form = ScopingMacroForm(instance=macro)
    return render(request, "jobtracker/scoping/macro_edit.html", {"form": form, "macro": macro})


class ScopingMacroDeleteView(PermissionRequiredMixin, ChaoticaBaseView, DeleteView):
    model = ScopingMacro
    permission_required = MANAGE_PERM
    accept_global_perms = True
    return_403 = True
    template_name = "jobtracker/scoping/macro_confirm_delete.html"
    success_url = reverse_lazy("scoping_macro_list")
