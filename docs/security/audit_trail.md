# Audit Trail & Activity History

CHAOTICA records a central, append-only **audit trail** of significant actions —
who did what, to which object, and when. It complements two existing mechanisms
rather than replacing them:

| Mechanism | Purpose |
| --- | --- |
| **AuditEvent** (this feature) | Cross-cutting "who did what" feed: auth, finance, security, config, workflow and general activity. Powers the activity tabs and the site-wide feed. |
| **django-simple-history** | Full field-level before/after snapshots on selected models (Job, Phase, Client, TimeSlot, …). |
| **ScheduleAction** | The scheduler's reversible commit log (undo / revert). |

## What is recorded

Each `AuditEvent` captures an **actor** (the user, or *SYSTEM* for background
work), a **verb** (created, updated, status changed, login, permission change,
…), a **category**, the **target object**, a compact **diff** of what changed,
and the **source** (web, API, background task, Resource Manager sync, …).

Coverage includes:

- **Authentication** — sign-in, sign-out, and failed sign-in attempts (only the
  attempted identifier is stored — **never** the password), plus API-token and
  health-key issue/revoke.
- **Security** — object-permission reconciliation on org units, unit role/lead
  changes, and global-role (group) membership changes.
- **Finance** — billing-code changes, per-user cost/rate changes, and job
  charge-code assignments.
- **Configuration** — services, skills, teams, org units, qualifications,
  email templates, report definitions/schedules and notification rules.
- **Workflow** — leave request approve / decline / cancel, and the existing
  job/phase lifecycle transitions.
- **Sync** — a summary event per Resource Manager sync run, plus a record when a
  user is auto-created from Resource Manager.

## Where to see it

### Object-level activity

Job, Phase, Project, Client, Organisational Unit, Service, Skill, Team, Billing
Code and Report detail pages each carry an **Activity** tab (or card) showing
that object's history, newest first.

Visibility follows the object's own permissions — if you can view the object you
can see its activity. **Sensitive rows** (authentication, security and finance
categories) are shown **only to global administrators**, even on an object you
can otherwise view.

### Site-wide activity log

Global administrators can open the **Activity Log** (`/activity/`) for a
cross-object feed of every category, with the actor, target, category and
message for each event.

## Notes

- **User comments** (the free-text "Notes" you add to a job or phase) are a
  separate feature and are unaffected — only *system* activity moved to the
  audit trail.
- The trail is **append-only**: events are never edited or deleted through the
  UI. A retention/archival policy can be applied out-of-band if required.

## For developers

Write an event from anywhere with the writer service:

```python
from chaotica_utils.audit import record_audit
from chaotica_utils.models import AuditVerb, AuditCategory

record_audit(
    some_object,
    AuditVerb.UPDATE,
    message="Rate updated",
    category=AuditCategory.FINANCE,
    changes={"cost_per_hour": [old, new]},
)
```

- The **actor** defaults to the current request user (resolved from a
  thread-local); pass `actor=None` to force a SYSTEM event, or an explicit user
  to override. Background tasks / management commands / sync jobs correctly
  resolve to SYSTEM / background sources.
- Writes **never raise** into the caller — an audit failure is logged, not
  propagated.
- To add a plain model to automatic create/update/delete auditing, add one line
  to `_AUDITED_MODELS` in `chaotica_utils/signals.py`; for a relation, add to
  `_AUDITED_M2M`.
- `audit_events_for(obj, viewer)` returns the permission-scoped queryset used by
  the UI (hides sensitive categories from non-admins).
