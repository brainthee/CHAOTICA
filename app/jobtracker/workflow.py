"""Job and phase workflow, described once for every client.

The FSM transitions live on the models (django-fsm). This module adds what a
UI needs to present them: labels, button style, grouping of statuses into
progress steps, and which transitions a given user can take now.

``available_transitions`` is keyed by transition **name** — several share a
target status (e.g. ``to_reopen`` and ``to_scoping`` both lead to Scoping).
"""

from dataclasses import dataclass

from .enums import JobStatuses, PhaseStatuses


@dataclass(frozen=True)
class Transition:
    name: str
    label: str
    style: str = "info"  # bootstrap colour: info | success | warning | danger
    menu: bool = False  # in the status menu rather than a main button
    needs_reason: bool = False
    icon: str = ""  # Font Awesome class, e.g. "fa-solid fa-rotate-left"
    # Status-specific labels, e.g. "Return to Scoping" from Scoping Complete.
    labels: tuple = ()

    def label_for(self, status):
        return dict(self.labels).get(status, self.label)


@dataclass(frozen=True)
class Step:
    label: str
    statuses: tuple


J, P = JobStatuses, PhaseStatuses

# The transitions people take by hand, as the job/phase pages offer them.
# Others (e.g. a job going In Progress / Complete) follow from its phases.
JOB_TRANSITIONS = {
    t.name: t
    for t in (
        Transition("to_pending_scope", "Move to Pending Scoping Queue"),
        Transition(
            "to_scoping",
            "Begin Scoping",
            labels=((J.SCOPING_COMPLETE, "Return to Scoping"),),
        ),
        Transition("to_additional_scope_req", "Additional Scoping Required"),
        Transition("to_scope_pending_signoff", "Move to Signoff Queue"),
        Transition("to_scope_complete", "Signoff Scope"),
        Transition(
            "to_reopen",
            "Reopen Job",
            "warning",
            needs_reason=True,
            icon="fa-solid fa-rotate-left",
        ),
        Transition("to_lost", "Close as Lost", "warning", menu=True),
        Transition("to_delete", "Delete Job", "danger", menu=True),
    )
}

PHASE_TRANSITIONS = {
    t.name: t
    for t in (
        Transition("to_pending_sched", "Mark Pending Scheduling", "success"),
        Transition("to_sched_confirmed", "Confirm Schedule", "success"),
        Transition("to_not_ready", "Client Not Ready", "warning"),
        Transition("to_ready", "Ready To Begin"),
        Transition("to_pending_tech_qa", "Submit to Tech QA Queue"),
        Transition("to_tech_qa", "Begin Tech QA"),
        Transition("to_tech_qa_updates", "Return for Author Updates"),
        Transition("to_pending_pres_qa", "Submit to Pres QA Queue"),
        Transition("to_pres_qa", "Begin Pres QA"),
        Transition("to_pres_qa_updates", "Return for Author Updates"),
        Transition("to_completed", "Set as Completed", "success"),
        Transition("to_delivered", "Set as Delivered", "success"),
        Transition(
            "to_reopen",
            "Reopen Phase",
            "warning",
            needs_reason=True,
            icon="fa-solid fa-rotate-left",
        ),
        Transition("to_postponed", "Postpone Phase", "info", menu=True),
        Transition("to_cancelled", "Close as Cancelled", "warning", menu=True),
        Transition("to_deleted", "Delete Phase", "danger", menu=True),
    )
}
# FSM transitions not offered by hand.
INTERNAL_TRANSITIONS = {
    "to_reopen_for_phase",  # driven by Phase.to_reopen
    "to_pending_start",
    "to_in_progress",
    "to_complete",
    "to_archive",
    "to_sched_tentative",
    "to_pre_checks",
    "to_archived",
}

JOB_STEPS = (
    Step("Draft", (J.DRAFT,)),
    Step("Scoping", (J.PENDING_SCOPE, J.SCOPING, J.SCOPING_ADDITIONAL_INFO_REQUIRED)),
    Step("Scope Signoff", (J.PENDING_SCOPING_SIGNOFF,)),
    Step("Scoped", (J.SCOPING_COMPLETE, J.PENDING_START)),
    Step("In Progress", (J.IN_PROGRESS,)),
    Step("Complete", (J.COMPLETED, J.ARCHIVED)),
)

PHASE_STEPS = (
    Step("Draft", (P.DRAFT,)),
    Step(
        "Scheduling",
        (P.PENDING_SCHED, P.SCHEDULED_TENTATIVE, P.SCHEDULED_CONFIRMED),
    ),
    Step("Pre-checks", (P.PRE_CHECKS, P.CLIENT_NOT_READY, P.READY_TO_BEGIN)),
    Step("In Progress", (P.IN_PROGRESS,)),
    Step("Tech QA", (P.PENDING_TQA, P.QA_TECH, P.QA_TECH_AUTHOR_UPDATES)),
    Step("Pres QA", (P.PENDING_PQA, P.QA_PRES, P.QA_PRES_AUTHOR_UPDATES)),
    Step("Completed", (P.COMPLETED,)),
    Step("Delivered", (P.DELIVERED, P.ARCHIVED)),
)


def _kind(obj):
    from .models import Job, Phase

    if isinstance(obj, Job):
        return JOB_TRANSITIONS, JOB_STEPS, "job.update"
    if isinstance(obj, Phase):
        return PHASE_TRANSITIONS, PHASE_STEPS, "phase.update"
    raise TypeError(f"No workflow for {type(obj).__name__}")


def steps(obj):
    """Progress steps with ``done`` / ``current`` / ``todo``. Off-path
    statuses (lost, cancelled, postponed, deleted) have no current step."""
    _, step_defs, _ = _kind(obj)
    current = next(
        (i for i, s in enumerate(step_defs) if obj.status in s.statuses), None
    )
    out = []
    for i, step in enumerate(step_defs):
        if current is None:
            state = "todo"
        elif i < current:
            state = "done"
        elif i == current:
            state = "current"
        else:
            state = "todo"
        out.append({"status": step.statuses[0], "label": step.label, "state": state})
    return out


def _ready(obj, name):
    """``can_to_*`` preconditions (required people/fields set). They read the
    current user where a check is about the user (e.g. assigned QA'er)."""
    check = getattr(obj, "can_" + name, None)
    return True if check is None else bool(check())


def can_reach(obj, target):
    """Whether the FSM lets ``obj`` move to status ``target`` now by a forward
    transition (reopening is its own action)."""
    return any(
        t.target == target and t.name not in ("to_reopen", "to_reopen_for_phase")
        for t in obj.get_available_status_transitions()
    )


def available_transitions(policy, obj):
    """Transitions the FSM allows from the current status, with
    ``ready`` (preconditions met) and ``allowed`` (caller may act)."""
    table, _, action = _kind(obj)
    allowed = policy.can(action, obj)
    out = []
    for fsm_t in obj.get_available_status_transitions():
        t = table.get(fsm_t.name)
        if t is None:
            continue
        out.append(
            {
                "name": t.name,
                "target": fsm_t.target,
                "label": t.label_for(obj.status),
                "style": t.style,
                "icon": t.icon,
                "menu": t.menu,
                "needs_reason": t.needs_reason,
                "ready": _ready(obj, t.name),
                "allowed": allowed,
            }
        )
    return out


def workflow_block(policy, obj):
    return {
        "status": obj.status,
        "status_display": obj.get_status_display(),
        "steps": steps(obj),
        "transitions": available_transitions(policy, obj),
    }
