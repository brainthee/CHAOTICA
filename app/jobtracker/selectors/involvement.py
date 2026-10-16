"""Who counts as "involved" in a job or phase.

Shared by the dashboard queues and the API's ``involving=me`` filters so they
always agree.
"""

from django.db.models import Q


def phase_involvement_q(user):
    return (
        Q(timeslots__user=user)
        | Q(report_author=user)
        | Q(project_lead=user)
        | Q(techqa_by=user)
        | Q(presqa_by=user)
    )


def job_involvement_q(user):
    return (
        Q(phases__timeslots__user=user)
        | Q(phases__report_author=user)
        | Q(phases__project_lead=user)
        | Q(phases__techqa_by=user)
        | Q(phases__presqa_by=user)
        | Q(scoped_by=user)
        | Q(account_manager=user)
        | Q(dep_account_manager=user)
    )
