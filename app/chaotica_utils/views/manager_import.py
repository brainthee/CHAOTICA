"""Bulk-set people's managers from a CSV, with a dry-run preview.

Upload -> every row is checked and shown as a change, no change, or the reason
it can't be applied. Confirm re-checks the same rows against current data and
applies the changes in one transaction. Changes go through ``User.save()`` so
pending leave follows the new manager (notifications signal), and each one is
audited.
"""

import csv
import io

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template import loader
from django.views.decorators.http import require_http_methods, require_safe

from ..decorators import permission_required_or_403
from ..models import User
from .common import page_defaults

MANAGER_CSV_HEADERS = ["email", "manager_email", "acting_manager_email"]
# A cell with one of these clears the field; a blank cell leaves it as is.
CLEAR_VALUES = {"-", "none"}
SESSION_KEY = "manager_import_rows"
# Placeholder accounts that are never real people.
NOT_PEOPLE = {"deleted@chaotica.app", "anonymoususer"}
MAX_ROWS = 5000


class ImportManagersForm(forms.Form):
    csv_file = forms.FileField(
        label="CSV File",
        help_text="Columns: email, manager_email, acting_manager_email",
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".csv"}),
    )

    def clean_csv_file(self):
        csv_file = self.cleaned_data.get("csv_file")
        if not csv_file.name.lower().endswith(".csv"):
            raise forms.ValidationError("File must be a CSV file")
        if csv_file.size > 5 * 1024 * 1024:
            raise forms.ValidationError("File size must be less than 5MB")
        return csv_file


def _read_rows(csv_file):
    """``(rows, error)``: the CSV's rows as dicts of the three columns."""
    try:
        reader = csv.DictReader(io.TextIOWrapper(csv_file.file, encoding="utf-8-sig"))
        fieldnames = reader.fieldnames
        raw = list(reader)
    except UnicodeDecodeError:
        return None, (
            "The file could not be read as text. Re-save it as 'CSV UTF-8' "
            "(not another encoding) and try again."
        )
    except csv.Error as e:
        return None, f"The file isn't a valid CSV: {e}"
    headers = [(f or "").strip().lower() for f in (fieldnames or [])]
    if "email" not in headers:
        return None, (
            "CSV file must include an 'email' column. Columns found: "
            + (", ".join(h for h in headers if h) or "none")
        )
    if not raw:
        return None, "The file has a header row but no data rows."
    if len(raw) > MAX_ROWS:
        return None, f"The file has more than {MAX_ROWS} rows; split it up."
    rows = []
    for r in raw:
        clean = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        rows.append({h: clean.get(h, "") for h in MANAGER_CSV_HEADERS})
    return rows, None


def _creates_loop(person, new_manager, manager_of):
    """Would ``person`` -> ``new_manager`` close a loop in the manager chain
    (with this file's other changes applied)?"""
    seen = set()
    current = new_manager.pk if new_manager else None
    while current is not None and current not in seen:
        if current == person.pk:
            return True
        seen.add(current)
        current = manager_of.get(current)
    return False


def plan_manager_changes(rows):
    """Check every row; returns one dict per row with ``status`` of
    ``change`` / ``same`` / ``error`` (and ``reason`` for errors)."""
    emails = set()
    for r in rows:
        for h in MANAGER_CSV_HEADERS:
            if r[h] and r[h].lower() not in CLEAR_VALUES:
                emails.add(r[h].lower())
    users = {}
    for u in User.objects.filter(email__in=list(emails)).select_related(
        "manager", "acting_manager"
    ):
        users[u.email.lower()] = u
    # Case-insensitive fallback for anything the exact match missed (the
    # prod columns compare case-sensitively).
    for email in emails - set(users):
        u = User.objects.filter(email__iexact=email).first()
        if u is not None:
            users[email] = u

    manager_of = dict(
        User.objects.exclude(manager__isnull=True).values_list("pk", "manager_id")
    )

    def resolve(value, label):
        """``(user_or_None, change, error)`` for one manager cell."""
        if not value:
            return None, False, None
        if value.lower() in CLEAR_VALUES:
            return None, True, None
        found = users.get(value.lower())
        if found is None or value.lower() in NOT_PEOPLE:
            return None, False, f"Unknown {label} {value}"
        if not found.is_active:
            return None, False, f"{label.capitalize()} {value} is deactivated"
        return found, True, None

    plan, seen_people = [], set()
    for num, r in enumerate(rows, start=2):
        entry = {"row": num, "email": r["email"], "status": "error"}
        plan.append(entry)
        if not r["email"]:
            entry["reason"] = "No email"
            continue
        person = users.get(r["email"].lower())
        if person is None or r["email"].lower() in NOT_PEOPLE:
            entry["reason"] = "Unknown person"
            continue
        entry["person"] = person
        if person.pk in seen_people:
            entry["reason"] = "Duplicate row for this person"
            continue
        seen_people.add(person.pk)

        manager, set_manager, err = resolve(r["manager_email"], "manager")
        if not err:
            acting, set_acting, err = resolve(r["acting_manager_email"], "acting manager")
        if err:
            entry["reason"] = err
            continue
        new_manager = manager if set_manager else person.manager
        new_acting = acting if set_acting else person.acting_manager
        if person in (new_manager, new_acting):
            entry["reason"] = "Can't be their own manager"
            continue
        if new_manager and _creates_loop(person, new_manager, manager_of):
            entry["reason"] = "Would create a management loop"
            continue

        entry.update(
            old_manager=person.manager,
            new_manager=new_manager,
            old_acting=person.acting_manager,
            new_acting=new_acting,
        )
        if new_manager == person.manager and new_acting == person.acting_manager:
            entry["status"] = "same"
        else:
            entry["status"] = "change"
            manager_of[person.pk] = new_manager.pk if new_manager else None
    return plan


def apply_manager_changes(plan):
    """Apply the plan's ``change`` rows in one transaction; returns count."""
    from ..audit import record_audit
    from ..models.audit import AuditCategory, AuditVerb

    changed = 0
    with transaction.atomic():
        for entry in plan:
            if entry["status"] != "change":
                continue
            person = entry["person"]
            person.manager = entry["new_manager"]
            person.acting_manager = entry["new_acting"]
            person.save()
            record_audit(
                person,
                AuditVerb.UPDATE,
                message="Manager set to {}; acting manager {} (manager import)".format(
                    entry["new_manager"] or "none", entry["new_acting"] or "none"
                ),
                category=AuditCategory.SECURITY,
                changes={
                    "manager": [
                        str(entry["old_manager"] or ""),
                        str(entry["new_manager"] or ""),
                    ],
                    "acting_manager": [
                        str(entry["old_acting"] or ""),
                        str(entry["new_acting"] or ""),
                    ],
                },
            )
            changed += 1
    return changed


def _render(request, context):
    context = {**context, **page_defaults(request)}
    template = loader.get_template("chaotica_utils/import_managers.html")
    return HttpResponse(template.render(context, request))


def _summary(plan):
    return {
        status: sum(1 for e in plan if e["status"] == status)
        for status in ("change", "same", "error")
    }


@login_required
@permission_required_or_403("chaotica_utils.manage_user")
@require_http_methods(["GET", "POST"])
def user_import_managers(request):
    if request.method == "POST" and request.POST.get("action") == "apply":
        rows = request.session.get(SESSION_KEY)
        if not rows:
            messages.error(request, "Nothing to apply - upload the file again.")
            return redirect("user_import_managers")
        # Re-check against current data rather than trusting the preview.
        plan = plan_manager_changes(rows)
        changed = apply_manager_changes(plan)
        del request.session[SESSION_KEY]
        skipped = _summary(plan)["error"]
        messages.success(
            request,
            "Updated managers for {} {}.".format(
                changed, "person" if changed == 1 else "people"
            )
            + (" {} row(s) skipped.".format(skipped) if skipped else ""),
        )
        return _render(
            request,
            {"form": ImportManagersForm(), "plan": plan, "applied": True,
             "summary": _summary(plan)},
        )

    if request.method == "POST":
        form = ImportManagersForm(request.POST, request.FILES)
        if form.is_valid():
            rows, error = _read_rows(form.cleaned_data["csv_file"])
            if error:
                messages.error(request, error)
                return redirect("user_import_managers")
            plan = plan_manager_changes(rows)
            request.session[SESSION_KEY] = rows
            return _render(
                request,
                {"form": ImportManagersForm(), "plan": plan, "preview": True,
                 "summary": _summary(plan)},
            )
    else:
        request.session.pop(SESSION_KEY, None)
        form = ImportManagersForm()
    return _render(request, {"form": form})


@login_required
@permission_required_or_403("chaotica_utils.manage_user")
@require_safe
def user_import_managers_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="managers_template.csv"'
    writer = csv.writer(response)
    writer.writerow(MANAGER_CSV_HEADERS)
    writer.writerow(["person@example.com", "their.manager@example.com", ""])
    return response
