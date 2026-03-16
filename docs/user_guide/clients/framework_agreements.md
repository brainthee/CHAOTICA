# Framework Agreements

Framework agreements are pre-negotiated contractual arrangements that track day budgets across multiple jobs for a client. They provide budget visibility, allocation controls, and analytics to help manage ongoing client engagements.

## Creating a Framework Agreement

Framework agreements are created from the client detail page under the Framework Agreements tab.

| Field | Description |
|---|---|
| `name` | Descriptive name for the agreement (unique per client) |
| `client` | The client this agreement belongs to |
| `start_date` | When the agreement becomes active |
| `end_date` | When the agreement expires (optional) |
| `total_days` | The total day budget for the agreement |
| `allow_over_allocation` | Whether scheduling beyond the budget is permitted (default: yes) |
| `closed` | Whether the agreement is closed to new scheduling (default: no) |

## Associating Jobs

Jobs have an optional `associated_framework` field. When a job is linked to a framework agreement, all delivery time slots scheduled against that job's phases count toward the framework's day budget.

To associate a job with a framework, set the framework field when creating or editing the job.

## Budget Tracking

Framework agreements track budget consumption by converting time slot hours into days using the client's `hours_in_day` setting:

```
days = slot_business_hours / client.hours_in_day
```

The framework provides these budget metrics:

| Metric | Meaning |
|---|---|
| **Days Used** | Days from time slots that have already ended |
| **Days Scheduled** | Days from time slots that haven't started yet |
| **Days Allocated** | Total of used + scheduled |
| **Days Available** | Remaining budget (`total_days - days_allocated`) |
| **% Allocated** | Percentage of total budget allocated |
| **Over-Allocated** | Boolean — whether `days_allocated` exceeds `total_days` |

## Allocation Controls

Framework agreements have three levels of control over scheduling:

### Open (Default)

`allow_over_allocation = True`, `closed = False`

Scheduling is allowed freely. If a slot would push the total above the budget, a **bypassable warning** is shown but the scheduler can confirm and proceed.

### Budget-Locked

`allow_over_allocation = False`, `closed = False`

Scheduling is allowed up to the budget. If a slot would push the total above `total_days`, it is a **hard block** — the slot cannot be saved.

### Closed

`closed = True`

No new scheduling is allowed at all. Any attempt to create or modify a delivery slot against this framework produces a **hard block**.

!!!warning
    Closing a framework does not delete existing time slots. It only prevents new ones from being created or existing ones from being extended.

See [Scheduling Validation](../scheduling/validation.md) for the full logic check sequence.

## Breakdown Dashboard

The framework agreement detail page provides a comprehensive breakdown of how the budget is being consumed.

### Header

The top of the page shows:

- Framework name with status badges (Closed, Over Allocation Allowed, Over Allocated)
- Summary table: start date, end date, total days, used, scheduled, available
- Stats cards: job count, phase count, average days per job, average days per phase

### Per-Job Breakdown

A table listing every job associated with the framework, with nested phase rows showing:

- Job/phase name and status
- Days used, days scheduled, and total days
- Visual indicators for phases that are consuming the most budget

### Team Breakdown

A table showing how days are distributed across individual team members who have been scheduled against the framework.

### Delivery Role Breakdown

A table showing days split by delivery role:

- Testing
- Reporting
- Review
- Management

### Service Breakdown

A table and **donut pie chart** showing days consumed by each service type (e.g. penetration testing, code review, etc.).

### Monthly Burn-Down

A combined chart showing:

- **Bar chart** — monthly day usage
- **Line chart** — cumulative days used over time
- **Dashed line** — total budget for reference

This visualisation helps identify burn rate trends and forecast when the budget will be exhausted.

## Related Topics

- [Adding Clients](adding_clients.md) — Client setup and framework agreement creation
- [Managing Jobs](../Jobs/managing_jobs.md) — Associating jobs with framework agreements
- [Scheduling Validation](../scheduling/validation.md) — How framework checks work during scheduling
