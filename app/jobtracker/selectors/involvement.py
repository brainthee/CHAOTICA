"""Who counts as "involved" in a job or phase.

Shared by the dashboard queues, job scoping and the API's ``involving=me``
filters so they always agree.

Relations are tested with ``Exists`` subqueries, not joins: joining phases ×
timeslots × scoped_by fans every big job out into thousands of rows that then
need DISTINCT (a 35s query on production-sized data).
"""

from django.db.models import Exists, OuterRef, Q


def phase_involvement_q(user):
    from ..models import TimeSlot

    return (
        Q(Exists(TimeSlot.objects.filter(phase=OuterRef("pk"), user=user)))
        | Q(report_author=user)
        | Q(project_lead=user)
        | Q(techqa_by=user)
        | Q(presqa_by=user)
    )


def job_involvement_q(user):
    from ..models import Job, Phase, TimeSlot

    return (
        Q(Exists(TimeSlot.objects.filter(phase__job=OuterRef("pk"), user=user)))
        | Q(
            Exists(
                Phase.objects.filter(job=OuterRef("pk")).filter(
                    Q(report_author=user)
                    | Q(project_lead=user)
                    | Q(techqa_by=user)
                    | Q(presqa_by=user)
                )
            )
        )
        | Q(
            Exists(
                Job.scoped_by.through.objects.filter(
                    job_id=OuterRef("pk"), user_id=user.pk
                )
            )
        )
        | Q(account_manager=user)
        | Q(dep_account_manager=user)
    )
