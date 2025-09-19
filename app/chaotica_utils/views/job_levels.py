from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse
from django.template import loader
from django.urls import reverse
from django.core.paginator import Paginator
from guardian.decorators import permission_required_or_403
from ..models import JobLevel, UserJobLevel, User
from ..views import page_defaults
from ..forms.job_levels import JobLevelForm, AssignJobLevelForm, ImportJobLevelAssignmentsForm
from django.db import transaction
from django.utils import timezone
import csv
from datetime import datetime
import io


@require_http_methods(["GET"])
def job_level_list(request):
    """List all job levels"""
    from django.db.models import Count, Q

    job_levels = JobLevel.objects.annotate(
        current_user_count=Count('user_assignments', filter=Q(user_assignments__is_current=True))
    ).order_by('order')

    context = {
        'job_levels': job_levels,
        'can_manage': request.user.is_superuser or request.user.is_staff,
    }

    template = loader.get_template("job_levels/list.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@staff_member_required
@require_http_methods(["GET", "POST"])
def job_level_create(request):
    """Create a new job level"""
    if request.method == "POST":
        form = JobLevelForm(request.POST)
        if form.is_valid():
            job_level = form.save()
            messages.success(request, f"Job level '{job_level.short_label}' created successfully")
            return redirect('job_level_list')
    else:
        form = JobLevelForm()

    context = {
        'form': form,
    }

    template = loader.get_template("job_levels/create.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@staff_member_required
@require_http_methods(["GET", "POST"])
def job_level_edit(request, pk):
    """Edit an existing job level"""
    job_level = get_object_or_404(JobLevel, pk=pk)

    if request.method == "POST":
        form = JobLevelForm(request.POST, instance=job_level)
        if form.is_valid():
            job_level = form.save()
            messages.success(request, f"Job level '{job_level.short_label}' updated successfully")
            return redirect('job_level_list')
    else:
        form = JobLevelForm(instance=job_level)

    # Get current assignment count
    current_assignment_count = UserJobLevel.objects.filter(
        job_level=job_level,
        is_current=True
    ).count()

    context = {
        'form': form,
        'job_level': job_level,
        'current_assignment_count': current_assignment_count,
    }

    template = loader.get_template("job_levels/edit.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@staff_member_required
@require_http_methods(["POST"])
def job_level_delete(request, pk):
    """Delete a job level (soft delete by setting inactive)"""
    job_level = get_object_or_404(JobLevel, pk=pk)

    # Check if any users are currently assigned to this level
    active_assignments = UserJobLevel.objects.filter(
        job_level=job_level,
        is_current=True
    ).count()

    if active_assignments > 0:
        messages.error(request, f"Cannot delete job level '{job_level.short_label}' - {active_assignments} users are currently assigned to it")
        return redirect('job_level_list')

    try:
        # Soft delete by setting inactive
        job_level.is_active = False
        job_level.save()
        messages.success(request, f"Job level '{job_level.short_label}' has been deactivated")
    except Exception as e:
        messages.error(request, f"Error deactivating job level: {str(e)}")

    return redirect('job_level_list')


@staff_member_required
@require_http_methods(["GET"])
def user_job_level_history(request):
    """View job level assignment history"""
    search_email = request.GET.get('search_email', '').strip()
    level_filter = request.GET.get('level_filter', '')

    assignments = UserJobLevel.objects.select_related(
        'user', 'job_level', 
    ).order_by('-assigned_date', '-created_at')

    if search_email:
        assignments = assignments.filter(
            user__email__icontains=search_email
        )

    if level_filter:
        assignments = assignments.filter(job_level__pk=level_filter)

    # Pagination
    paginator = Paginator(assignments, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    job_levels = JobLevel.objects.filter(is_active=True).order_by('order')

    context = {
        'page_obj': page_obj,
        'job_levels': job_levels,
        'search_email': search_email,
        'level_filter': level_filter,
    }

    template = loader.get_template("job_levels/history.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@staff_member_required
@require_http_methods(["GET", "POST"])
def assign_job_level(request):
    """Assign job level to a user"""
    if request.method == "POST":
        form = AssignJobLevelForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                assignment = form.save()
                messages.success(request,
                    f"Assigned {assignment.job_level.short_label} to {assignment.user}")
            return redirect('user_job_level_history')
    else:
        form = AssignJobLevelForm()

    context = {
        'form': form,
    }

    template = loader.get_template("job_levels/assign.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@staff_member_required
@require_http_methods(["GET", "POST"])
def import_job_level_assignments(request):
    """Import job level assignments from CSV file"""

    if request.method == "POST":
        form = ImportJobLevelAssignmentsForm(request.POST, request.FILES)

        if form.is_valid():
            csv_file = form.cleaned_data['csv_file']
            update_existing = form.cleaned_data['update_existing']

            # Process the CSV file
            try:
                # Decode CSV file
                text_file = io.TextIOWrapper(csv_file.file, encoding='utf-8')
                csv_reader = csv.DictReader(text_file)

                # Validate headers
                required_headers = {'email', 'job_level_short_label', 'assigned_date'}
                if csv_reader.fieldnames:
                    headers = set(csv_reader.fieldnames)
                    missing_headers = required_headers - headers
                    if missing_headers:
                        messages.error(request,
                            f"CSV file is missing required columns: {', '.join(missing_headers)}")
                        return redirect('import_job_level_assignments')

                # Process rows
                success_count = 0
                error_count = 0
                errors = []

                with transaction.atomic():
                    for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 to account for header
                        try:
                            email = row.get('email', '').strip()
                            job_level_short = row.get('job_level_short_label', '').strip()
                            assigned_date_str = row.get('assigned_date', '').strip()

                            # Validate row data
                            if not email or not job_level_short or not assigned_date_str:
                                errors.append(f"Row {row_num}: Missing required data")
                                error_count += 1
                                continue

                            # Get user
                            try:
                                user = User.objects.get(email=email)
                            except User.DoesNotExist:
                                errors.append(f"Row {row_num}: User with email '{email}' not found")
                                error_count += 1
                                continue

                            # Get job level
                            try:
                                job_level = JobLevel.objects.get(short_label=job_level_short, is_active=True)
                            except JobLevel.DoesNotExist:
                                errors.append(f"Row {row_num}: Job level '{job_level_short}' not found or inactive")
                                error_count += 1
                                continue

                            # Parse date
                            try:
                                assigned_date = datetime.strptime(assigned_date_str, '%Y-%m-%d').date()

                                # Validate date is not in future
                                if assigned_date > timezone.now().date():
                                    errors.append(f"Row {row_num}: Assignment date cannot be in the future")
                                    error_count += 1
                                    continue
                            except ValueError:
                                errors.append(f"Row {row_num}: Invalid date format '{assigned_date_str}' (use YYYY-MM-DD)")
                                error_count += 1
                                continue

                            # Check if user already has a current job level
                            current_level = UserJobLevel.get_current_level(user)

                            if current_level and not update_existing:
                                errors.append(f"Row {row_num}: User {email} already has a job level assigned (skipped)")
                                continue

                            # Create or update job level assignment
                            if not current_level or current_level.job_level != job_level:
                                UserJobLevel.assign_level(
                                    user=user,
                                    job_level=job_level,
                                    assigned_date=assigned_date,
                                    notes=f"Imported via CSV by {request.user.email}"
                                )
                                success_count += 1
                            else:
                                # User already has this level, no change needed
                                pass

                        except Exception as e:
                            errors.append(f"Row {row_num}: Unexpected error - {str(e)}")
                            error_count += 1

                # Report results
                if success_count > 0:
                    messages.success(request, f"Successfully imported {success_count} job level assignment(s)")

                if error_count > 0:
                    # Show first 5 errors
                    error_message = f"Failed to import {error_count} row(s)."
                    if errors:
                        error_details = errors[:5]
                        if len(errors) > 5:
                            error_details.append(f"... and {len(errors) - 5} more errors")
                        error_message += " Errors: " + "; ".join(error_details)
                    messages.error(request, error_message)

                if success_count > 0:
                    return redirect('user_job_level_history')

            except Exception as e:
                messages.error(request, f"Error processing CSV file: {str(e)}")
                return redirect('import_job_level_assignments')
    else:
        form = ImportJobLevelAssignmentsForm()

    context = {
        'form': form,
    }

    template = loader.get_template("job_levels/import.html")
    context = {**context, **page_defaults(request)}
    return HttpResponse(template.render(context, request))


@staff_member_required
@require_http_methods(["GET"])
def download_job_level_template(request):
    """Download a CSV template for job level imports"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="job_level_assignments_template.csv"'

    writer = csv.writer(response)
    writer.writerow(['email', 'job_level_short_label', 'assigned_date'])

    # Add example rows
    writer.writerow(['user@example.com', 'JL1', '2024-01-01'])
    writer.writerow(['another@example.com', 'JL2', '2024-01-15'])

    return response