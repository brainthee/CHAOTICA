from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.utils import timezone
from django.contrib import messages
from django.db.models import Q
from datetime import timedelta
import random
import json

from jobtracker.models import Phase, Job, OrganisationalUnit
from jobtracker.enums import PhaseStatuses
from chaotica_utils.models import User
from .models import QAReview, QAReviewConfiguration
from guardian.shortcuts import get_objects_for_user


def get_eligible_phases_for_unit(unit, weeks_back=4):
    """
    Get eligible phases for QA review selection for a given unit.
    This method ensures consistent logic between spin_wheel and get_eligible_users.
    """
    cutoff_date = timezone.now() - timedelta(weeks=weeks_back)

    # Get eligible phases with consistent criteria
    eligible_phases = Phase.objects.filter(
        job__unit=unit,
        status__in=[PhaseStatuses.COMPLETED, PhaseStatuses.DELIVERED],  # Completed phases
        linkDeliverable__isnull=False,
        status_changed_date__gte=cutoff_date  # Use status change date instead of desired delivery
    ).exclude(linkDeliverable='').select_related('report_author', 'job')

    return eligible_phases


def get_eligible_users_data_for_unit(unit, weeks_back=4):
    """
    Get structured user data with their eligible phases for QA review.
    Ensures only active users are included.
    """
    eligible_phases = get_eligible_phases_for_unit(unit, weeks_back)

    user_data = {}
    for phase in eligible_phases:
        author = phase.report_author
        if author and author.is_active:  # Only include active users
            if author.id not in user_data:
                user_data[author.id] = {
                    'id': author.id,
                    'name': author.get_full_name() or author.username,
                    'email': author.email,
                    'phases': []
                }
            user_data[author.id]['phases'].append({
                'id': phase.id,
                'phase_id': phase.phase_id,
                'title': phase.title,
                'job_title': phase.job.title,
                'delivery_date': phase.job.desired_delivery_date.isoformat() if phase.job.desired_delivery_date else None
            })

    return list(user_data.values())


@login_required
def qa_wheel_selection(request):
    # Get units where user has can_conduct_review permission
    user_units = get_objects_for_user(request.user, 'jobtracker.can_conduct_review', klass=OrganisationalUnit)

    # If no specific units, check if user is staff/superuser
    if not user_units and not request.user.is_staff:
        messages.error(request, "You don't have permission to conduct reviews for any units.")
        return redirect('home')

    # If user is staff but no specific units, get all units (but still check permission in views)
    if not user_units and request.user.is_staff:
        user_units = OrganisationalUnit.objects.all()

    selected_unit = None
    config = None
    weeks_back = 4  # default

    # Check for unit parameter from URL
    unit_param = request.GET.get('unit')
    if unit_param:
        try:
            unit_id = int(unit_param)
            potential_unit = OrganisationalUnit.objects.get(id=unit_id)
            if potential_unit in user_units or request.user.is_staff:
                selected_unit = potential_unit
                config, created = QAReviewConfiguration.objects.get_or_create(
                    unit=selected_unit,
                    defaults={'weeks_back': weeks_back}
                )
                if not created:
                    weeks_back = config.weeks_back
        except (ValueError, OrganisationalUnit.DoesNotExist):
            pass

    if request.method == 'POST':
        unit_id = request.POST.get('unit_id')
        weeks_back = int(request.POST.get('weeks_back', 4))

        if unit_id:
            selected_unit = get_object_or_404(OrganisationalUnit, id=unit_id)
            if selected_unit not in user_units and not request.user.is_staff:
                messages.error(request, "You don't have permission to conduct reviews for this unit.")
                return redirect('qa_reviews:wheel_selection')

            config, created = QAReviewConfiguration.objects.get_or_create(
                unit=selected_unit,
                defaults={'weeks_back': weeks_back}
            )
            if not created:
                config.weeks_back = weeks_back
                config.save()

    context = {
        'units': user_units,
        'selected_unit': selected_unit,
        'config': config,
        'weeks_back': weeks_back,
    }

    return render(request, 'qa_reviews/wheel_selection.html', context)


@login_required
@require_http_methods(["POST"])
def get_eligible_users(request):
    unit_id = request.POST.get('unit_id')
    weeks_back = int(request.POST.get('weeks_back', 4))

    if not unit_id:
        return JsonResponse({'error': 'Unit ID is required'}, status=400)

    unit = get_object_or_404(OrganisationalUnit, id=unit_id)
    user_units = get_objects_for_user(request.user, 'jobtracker.can_conduct_review', klass=OrganisationalUnit)

    # Allow staff/superuser access
    if not request.user.is_staff and unit not in user_units:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    # Use shared method to get eligible users data
    users = get_eligible_users_data_for_unit(unit, weeks_back)

    return JsonResponse({
        'users': users,
        'count': len(users)
    })


@login_required
@require_http_methods(["POST"])
def spin_wheel(request):
    unit_id = request.POST.get('unit_id')
    weeks_back = int(request.POST.get('weeks_back', 4))

    if not unit_id:
        return JsonResponse({'error': 'Unit ID is required'}, status=400)

    unit = get_object_or_404(OrganisationalUnit, id=unit_id)
    user_units = get_objects_for_user(request.user, 'jobtracker.can_conduct_review', klass=OrganisationalUnit)

    # Allow staff/superuser access
    if not request.user.is_staff and unit not in user_units:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    # Get eligible phases using shared method
    eligible_phases = get_eligible_phases_for_unit(unit, weeks_back)

    # Get unique active authors
    authors = list(set([phase.report_author for phase in eligible_phases if phase.report_author and phase.report_author.is_active]))

    if not authors:
        return JsonResponse({'error': 'No eligible users found'}, status=404)

    selected_user = random.choice(authors)

    # Get this user's phases
    user_phases = eligible_phases.filter(report_author=selected_user).select_related('job')

    phases_data = [{
        'id': phase.id,
        'phase_id': phase.phase_id,
        'title': phase.title,
        'job_title': phase.job.title,
        'job_id': phase.job.id,
        'delivery_date': phase.job.desired_delivery_date.isoformat() if phase.job.desired_delivery_date else None
    } for phase in user_phases]

    return JsonResponse({
        'selected_user': {
            'id': selected_user.id,
            'name': selected_user.get_full_name() or selected_user.username,
            'email': selected_user.email
        },
        'phases': phases_data
    })


@login_required
def begin_review(request, phase_id):
    phase = get_object_or_404(Phase, id=phase_id)

    # Check permissions
    user_units = get_objects_for_user(request.user, 'jobtracker.can_conduct_review', klass=OrganisationalUnit)
    if not request.user.is_staff and phase.job.unit not in user_units:
        messages.error(request, "You don't have permission to review this phase.")
        return redirect('qa_reviews:wheel_selection')

    # Create or get existing review
    review, created = QAReview.objects.get_or_create(
        phase=phase,
        reviewer=request.user,
        status__in=['started', 'in_progress'],
        defaults={
            'reviewed_user': phase.report_author,
            'status': 'started'
        }
    )

    if not created:
        review.status = 'in_progress'
        review.save()

    return redirect('qa_reviews:review_detail', review_id=review.id)


@login_required
def review_detail(request, review_id):
    review = get_object_or_404(QAReview, id=review_id)

    # Check permissions
    if review.reviewer != request.user:
        messages.error(request, "You don't have permission to view this review.")
        return redirect('qa_reviews:wheel_selection')

    if request.method == 'POST':
        # Update review with form data
        review.notes = request.POST.get('notes', '')

        if request.POST.get('action') == 'complete':
            # Check if user can complete this review
            if not review.can_be_completed_by(request.user):
                messages.error(request, "You don't have permission to complete this review. Only the original reviewer can complete it.")
                return redirect('qa_reviews:review_detail', review_id=review.id)

            review.complete_review()
            messages.success(request, "Review completed successfully!")
            return redirect('qa_reviews:wheel_selection')
        else:
            review.status = 'in_progress'
            review.save()
            messages.success(request, "Review saved successfully!")

    context = {
        'review': review,
        'phase': review.phase,
        'job': review.phase.job,
    }

    return render(request, 'qa_reviews/review_detail.html', context)


@login_required
def review_history(request):
    # Get reviews conducted by the user
    conducted_reviews = QAReview.objects.filter(
        reviewer=request.user
    ).select_related('phase', 'reviewed_user', 'phase__job')

    # Get reviews of the user's work (if they want to see it)
    received_reviews = QAReview.objects.filter(
        reviewed_user=request.user,
        status='completed'
    ).select_related('phase', 'reviewer', 'phase__job')

    context = {
        'conducted_reviews': conducted_reviews,
        'received_reviews': received_reviews,
    }

    return render(request, 'qa_reviews/review_history.html', context)


@login_required
@require_http_methods(["POST"])
def abort_review(request, review_id):
    review = get_object_or_404(QAReview, id=review_id)

    # Check if user can abort this review
    if not review.can_be_aborted_by(request.user):
        messages.error(request, "You don't have permission to abort this review.")
        return redirect('qa_reviews:review_detail', review_id=review.id)

    # Check if review is in abortable state
    if review.status not in ['started', 'in_progress']:
        messages.error(request, "This review cannot be aborted.")
        return redirect('qa_reviews:review_detail', review_id=review.id)

    # Abort the review
    review.abort_review()
    messages.success(request, "Review has been aborted successfully.")

    # Redirect to unit detail page if possible, otherwise to wheel selection
    if review.phase and review.phase.job and review.phase.job.unit:
        return redirect('organisationalunit_detail', slug=review.phase.job.unit.slug)
    else:
        return redirect('qa_reviews:wheel_selection')
