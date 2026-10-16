"""Phase detail data shared by the phase page and /api/v1/phases/."""

from ..enums import JobStatuses, PhaseStatuses


def concurrent_phases(phase):
    """Other live phases on the same job whose scheduled window overlaps."""
    from ..models import Phase

    if not (
        phase._start_date
        and phase._delivery_date
        and phase.status in PhaseStatuses.ACTIVE_STATUSES
    ):
        return Phase.objects.none()
    return (
        Phase.objects.filter(
            job=phase.job,
            _start_date__lte=phase._delivery_date,
            _delivery_date__gte=phase._start_date,
        )
        .exclude(pk=phase.pk)
        .exclude(
            status__in=[
                PhaseStatuses.CANCELLED,
                PhaseStatuses.POSTPONED,
                PhaseStatuses.DELETED,
                PhaseStatuses.ARCHIVED,
            ]
        )
    )


def phase_missing_billing_code(phase):
    """A live phase on an open job with no effective billing code."""
    return (
        phase.status not in PhaseStatuses.INACTIVE_STATUSES
        and phase.job.status not in JobStatuses.CLOSED_STATUSES
        and not phase.has_billing_code()
    )
