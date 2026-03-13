from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.apps import apps
from django.contrib.contenttypes.models import ContentType

from ..models import DataArea, DataField, DataSource, Report, ReportField, ReportFilter, ReportSort


def is_superuser(user):
    return user.is_superuser


@login_required
@user_passes_test(is_superuser)
def admin_dashboard(request):
    """Admin dashboard for the reporting system"""
    data_areas = DataArea.objects.all().prefetch_related('fields')
    data_sources = DataSource.objects.select_related(
        'from_area', 'to_area', 'relationship_type'
    ).all()

    context = {
        'data_areas': data_areas,
        'data_sources': data_sources,
    }
    return render(request, 'reporting/admin/dashboard.html', context)


@login_required
@user_passes_test(is_superuser)
def validate_fields(request):
    """Validate all DataField definitions against their actual Django models"""
    results = []
    data_areas = DataArea.objects.all().prefetch_related('fields__field_type')

    for data_area in data_areas:
        area_result = {
            'data_area': data_area,
            'valid': [],
            'invalid': [],
            'warnings': [],
        }

        # Resolve the model class
        model_class = None
        try:
            ct = data_area.content_type
            model_class = ct.model_class()
            if model_class is None:
                area_result['invalid'].append({
                    'field': None,
                    'error': f"Content type '{ct.app_label}.{ct.model}' does not resolve to a model class.",
                })
                results.append(area_result)
                continue
        except Exception as e:
            area_result['invalid'].append({
                'field': None,
                'error': f"Cannot resolve content type: {e}",
            })
            results.append(area_result)
            continue

        for field in data_area.fields.filter(is_available=True):
            validation = _validate_field_path(model_class, field)
            if validation['status'] == 'valid':
                area_result['valid'].append(validation)
            elif validation['status'] == 'warning':
                area_result['warnings'].append(validation)
            else:
                area_result['invalid'].append(validation)

        results.append(area_result)

    total_valid = sum(len(r['valid']) for r in results)
    total_invalid = sum(len(r['invalid']) for r in results)
    total_warnings = sum(len(r['warnings']) for r in results)

    context = {
        'results': results,
        'total_valid': total_valid,
        'total_invalid': total_invalid,
        'total_warnings': total_warnings,
    }
    return render(request, 'reporting/admin/validate_fields.html', context)


@login_required
@user_passes_test(is_superuser)
def delete_invalid_fields(request):
    """Delete DataField records whose field_path doesn't resolve on the model"""
    if request.method != 'POST':
        return redirect('reporting:admin_validate_fields')

    deleted_count = 0
    data_areas = DataArea.objects.all().prefetch_related('fields')

    for data_area in data_areas:
        model_class = None
        try:
            model_class = data_area.content_type.model_class()
            if model_class is None:
                continue
        except Exception:
            continue

        for field in data_area.fields.filter(is_available=True):
            validation = _validate_field_path(model_class, field)
            if validation['status'] == 'invalid':
                field.is_available = False
                field.save(update_fields=['is_available'])
                deleted_count += 1

    messages.success(request, f"Disabled {deleted_count} invalid field(s).")
    return redirect('reporting:admin_validate_fields')


def _validate_field_path(model_class, data_field):
    """
    Validate a single DataField's field_path against the Django model.
    Walks the full path (e.g. 'job__client__name') resolving each segment.
    """
    field_path = data_field.field_path
    result = {
        'field': data_field,
        'field_path': field_path,
        'status': 'valid',
        'error': None,
        'resolved_type': None,
    }

    parts = field_path.split('__')
    current_model = model_class

    for i, part in enumerate(parts):
        # Handle fields starting with _ (could be properties or private fields)
        if part.startswith('_'):
            # Check if it's an actual model field
            try:
                django_field = current_model._meta.get_field(part)
                result['resolved_type'] = type(django_field).__name__
                if hasattr(django_field, 'related_model') and django_field.related_model:
                    current_model = django_field.related_model
                continue
            except Exception:
                pass

            # Check if it's a property on the model
            if hasattr(current_model, part):
                result['status'] = 'warning'
                result['error'] = (
                    f"'{part}' resolved as a Python attribute/property on "
                    f"{current_model.__name__}, not a DB field. "
                    f"Queries using .values()/filter() on this path will fail."
                )
                result['resolved_type'] = 'property/attribute'
                return result

            result['status'] = 'invalid'
            result['error'] = (
                f"Cannot resolve '{part}' on {current_model.__name__}. "
                f"Available fields: {_get_field_names(current_model)}"
            )
            return result

        try:
            django_field = current_model._meta.get_field(part)
            result['resolved_type'] = type(django_field).__name__

            # If this is a relation and there are more parts, follow it
            if hasattr(django_field, 'related_model') and django_field.related_model:
                current_model = django_field.related_model
        except Exception:
            # Check if it's a valid lookup (e.g. a property accessed via __)
            # but not a real DB field
            if hasattr(current_model, part):
                result['status'] = 'warning'
                result['error'] = (
                    f"'{part}' is a Python attribute on {current_model.__name__}, "
                    f"not a database field. ORM queries may fail."
                )
                result['resolved_type'] = 'attribute'
                return result

            result['status'] = 'invalid'
            result['error'] = (
                f"Cannot resolve '{part}' on {current_model.__name__}. "
                f"Available fields: {_get_field_names(current_model)}"
            )
            return result

    return result


def _get_field_names(model_class):
    """Get a sorted, comma-separated list of field names for a model."""
    names = sorted(f.name for f in model_class._meta.get_fields())
    # Truncate if too long for display
    if len(names) > 20:
        return ', '.join(names[:20]) + f' ... (+{len(names) - 20} more)'
    return ', '.join(names)


@login_required
@user_passes_test(is_superuser)
def validate_reports(request):
    """Check all saved reports for references to invalid or disabled fields."""
    reports = Report.objects.select_related('data_area', 'owner').prefetch_related(
        'fields__data_field__field_type',
        'filters__data_field__field_type',
        'filters__filter_type',
        'sorts__data_field__field_type',
    ).all()

    # Build a cache of model classes per data area and field validation results
    model_cache = {}  # data_area_id -> model_class or None
    field_valid_cache = {}  # data_field_id -> (status, error)

    report_results = []

    for report in reports:
        issues = []

        # Check the data area itself
        da = report.data_area
        if da.id not in model_cache:
            try:
                model_cache[da.id] = da.content_type.model_class()
            except Exception:
                model_cache[da.id] = None

        model_class = model_cache[da.id]
        if model_class is None:
            issues.append({
                'severity': 'error',
                'component': 'Data Area',
                'detail': f"Data area '{da.name}' cannot resolve to a model class.",
            })
            report_results.append({
                'report': report,
                'issues': issues,
                'status': 'error',
            })
            continue

        # Check fields
        for rf in report.fields.all():
            issue = _check_report_data_field(rf.data_field, model_class, field_valid_cache, 'Column')
            if issue:
                issue['detail'] = f"Column '{rf.get_display_name()}' (pos {rf.position}): {issue['detail']}"
                issues.append(issue)

        # Check filters
        for rf in report.filters.all():
            issue = _check_report_data_field(rf.data_field, model_class, field_valid_cache, 'Filter')
            if issue:
                label = f"{rf.data_field.display_name} {rf.filter_type.display_label}"
                issue['detail'] = f"Filter '{label}': {issue['detail']}"
                issues.append(issue)

        # Check sorts
        for rs in report.sorts.all():
            issue = _check_report_data_field(rs.data_field, model_class, field_valid_cache, 'Sort')
            if issue:
                issue['detail'] = f"Sort '{rs.data_field.display_name}' ({rs.direction}): {issue['detail']}"
                issues.append(issue)

        if issues:
            has_errors = any(i['severity'] == 'error' for i in issues)
            status = 'error' if has_errors else 'warning'
        else:
            status = 'ok'

        report_results.append({
            'report': report,
            'issues': issues,
            'status': status,
        })

    total_ok = sum(1 for r in report_results if r['status'] == 'ok')
    total_warning = sum(1 for r in report_results if r['status'] == 'warning')
    total_error = sum(1 for r in report_results if r['status'] == 'error')

    context = {
        'report_results': report_results,
        'total_ok': total_ok,
        'total_warning': total_warning,
        'total_error': total_error,
    }
    return render(request, 'reporting/admin/validate_reports.html', context)


def _check_report_data_field(data_field, model_class, cache, component_label):
    """
    Check whether a DataField used by a report is valid.
    Returns an issue dict or None if valid.
    """
    df_id = data_field.id

    if df_id not in cache:
        if not data_field.is_available:
            cache[df_id] = ('disabled', f"references disabled field '{data_field.display_name}' ({data_field.field_path})")
        else:
            validation = _validate_field_path(model_class, data_field)
            if validation['status'] == 'invalid':
                cache[df_id] = ('invalid', f"field path '{data_field.field_path}' does not resolve — {validation['error']}")
            elif validation['status'] == 'warning':
                cache[df_id] = ('warning', f"field path '{data_field.field_path}' resolves to a property, not a DB field")
            else:
                cache[df_id] = ('valid', None)

    status, error = cache[df_id]

    if status == 'valid':
        return None

    severity = 'error' if status in ('invalid', 'disabled') else 'warning'
    return {
        'severity': severity,
        'component': component_label,
        'detail': error,
    }
