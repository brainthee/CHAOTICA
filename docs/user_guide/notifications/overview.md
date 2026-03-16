# Notification System

CHAOTICA uses an event-driven notification system to keep users informed about job lifecycle events, scheduling changes, QA updates, and leave requests. Notifications are delivered through two channels: in-app and email.

## Delivery Channels

### In-App Notifications

The notification centre is accessible from the main navigation. It shows a badge count of unread notifications and provides:

- Chronological list of all notifications
- Read/unread status tracking
- Links to the relevant entity (job, phase, etc.)

### Email Notifications

Notifications flagged with `should_email = True` are sent as HTML emails using configurable templates. Each notification type can specify its own email template. Emails are sent via the `send_email()` method on the Notification model.

!!!note
    These are the only two delivery channels. CHAOTICA does not currently support SMS, push notifications, Slack, or other third-party integrations.

## Notification Types

Notifications are categorised by the `NotificationTypes` enum. Each type has a numeric ID, a display label, and a description.

### Job Events

| Type | Description |
|---|---|
| Job Created | A new job has been created |
| Job Status Change | A job's status has changed |
| Job Pending Scoping | A job is waiting to be scoped |
| Job Pending Scope Sign-off | A job scope is awaiting sign-off |
| Job Scoping Complete | Scoping has been completed |
| Job Complete | A job has been fully completed |

### Phase Events

| Type | Description |
|---|---|
| Phase Created | A new phase has been created |
| Phase Status Change | A phase's status has changed |
| Phase Late to TQA | A phase is overdue for technical QA |
| Phase Late to PQA | A phase is overdue for presentation QA |
| Phase Late to Delivery | A phase is overdue for delivery |
| Phase New Note | A note has been added to a phase |
| Phase TQA Updates | Updates to a phase's TQA review |
| Phase PQA Updates | Updates to a phase's PQA review |
| Phase Feedback | Feedback has been left on a phase |
| Phase Pending Scheduling | A phase is waiting to be scheduled |
| Phase Schedule Confirmed | A phase's schedule has been confirmed |
| Phase Ready for Pre-checks | A phase is ready for pre-delivery checks |
| Phase Client Not Ready | The client is not ready for the phase |
| Phase Ready | A phase is ready to begin |
| Phase In Progress | A phase has started |
| Phase Pending TQA | A phase is awaiting technical QA |
| Phase Pending PQA | A phase is awaiting presentation QA |
| Phase Pending Delivery | A phase is awaiting delivery to the client |
| Phase Completed | A phase has been completed |
| Phase Postponed | A phase has been postponed |
| Phase Pre-checks Overdue | Pre-delivery checks are overdue |

### Leave Events

| Type | Description |
|---|---|
| Leave Submitted | A leave request has been submitted |
| Leave Approved | A leave request has been approved |
| Leave Rejected | A leave request has been rejected |
| Leave Cancelled | A leave request has been cancelled |

### Client Events

| Type | Description |
|---|---|
| Client Onboarding Renewal | A client onboarding record needs renewal |

## Subscriptions

Users receive notifications based on **subscriptions**. A subscription links a user to a notification type, optionally scoped to a specific entity.

### Subscription Fields

| Field | Purpose |
|---|---|
| `notification_type` | Which event type to subscribe to |
| `entity_type` | Optional — scope to a specific model (e.g. "Job", "Phase") |
| `entity_id` | Optional — scope to a specific instance |
| `email_enabled` | Whether to send email for this subscription |
| `in_app_enabled` | Whether to show in-app notifications |

A subscription with no `entity_type`/`entity_id` is a global subscription for that notification type. A subscription scoped to e.g. `entity_type="Job", entity_id=42` only fires for events on that specific job.

## Subscription Rules

Subscription rules automate the creation and management of subscriptions. Instead of requiring users to manually subscribe, rules match users based on their roles and automatically create subscriptions.

### How Rules Work

Each rule targets a single notification type and contains one or more **criteria** that determine which users should be subscribed. When a rule is saved, it evaluates its criteria and creates or updates subscriptions for matching users.

Rules have a **priority** field (higher number = higher priority). When multiple rules target the same notification type, the highest-priority rule wins conflicts.

### Criteria Types

| Criteria Type | Matches Users By |
|---|---|
| **GlobalRoleCriteria** | User's global role (e.g. admin, manager) |
| **OrgUnitRoleCriteria** | User's role within a specific organisational unit |
| **JobRoleCriteria** | User's role on a job: Account Manager, Deputy Account Manager, Created By, Primary Point of Contact, Scoped By, or Scope Signed-off By |
| **PhaseRoleCriteria** | User's role on a phase: Project Lead, Report Author, TQA Reviewer, or PQA Reviewer |
| **DynamicRuleCriteria** | Custom criteria function looked up from the criteria registry by name, with optional JSON parameters |

A rule can have multiple criteria of different types. Each criterion independently returns a set of matching users, and all are combined.

### Rule vs Manual Subscriptions

Subscriptions track whether they were created by a rule (`created_by_rule = True`) or manually by the user. This distinction is visible in the admin interface and allows rule updates to only affect auto-created subscriptions.

## Notification Categories

Notification types can be grouped into **categories** for organisational purposes. Each category has a name and description. The `NotificationTypes` enum defines default category groupings for job events, phase events, and leave events.

## Opt-Outs

Users can explicitly opt out of specific notification types for specific entities using **NotificationOptOut** records. An opt-out is scoped to a `(user, notification_type, entity_type, entity_id)` combination.

## Administration

### Notification Admin

The Django admin interface provides management tools for notifications:

- **List view**: columns for user, timestamp, title, is_emailed, should_email, read
- **Filters**: by `is_emailed`, `should_email`, `read`, and `notification_type`
- **Search**: by title, message, or user name
- **Bulk actions**:
  - *Mark as emailed* — sets `is_emailed = True` without actually sending any email (useful for clearing backlogs)
  - *Send email now* — actually sends the email for selected notifications that have `should_email = True`

### Subscription Rule Admin

- **List view**: name, notification type, active status, priority, criteria count, subscription count, last updated
- **Inline editors**: each criteria type (Global, Org Unit, Job, Phase, Dynamic) has its own inline form
- **Criteria count**: hover shows breakdown by type (Global: N, Org: N, Job: N, Dynamic: N)
- **Subscription count**: shows how many auto-created subscriptions exist for this rule's notification type

### Subscription Admin

- **List view**: user, notification type, entity type/ID, email enabled, in-app enabled, creation method
- **Filters**: by notification type, entity type, email/in-app enabled, and creation method (rule vs manual)
- **Search**: by user email or name

## Related Topics

- [Managing Jobs](../Jobs/managing_jobs.md) — Job lifecycle events that trigger notifications
- [Quality Assurance](../workflows/quality_assurance.md) — QA workflow notifications
- [User Management](../team/user_management.md) — User profiles and preferences
