# Scheduling Overview

The scheduler is the central tool for allocating team members to jobs, phases, projects, and internal activities. It provides a calendar-based interface where schedulers can create, edit, and manage time slots across the organisation.

## Scheduler Interface

The scheduler uses a [FullCalendar](https://fullcalendar.io/)-based resource timeline view. Each row represents a team member, and time slots appear as coloured bars spanning their assigned dates.

- **Resource rows** show team members from the selected organisational unit(s)
- **Filtering** controls which units, members, and slot types are visible — see [Filtering](filtering.md) for details
- **Navigation** lets you scroll through weeks and months with standard calendar controls

## Time Slot Types

Every time slot in CHAOTICA has a type that determines its behaviour and which validation checks apply.

### Delivery (Phase) Slots

Delivery slots are the primary scheduling mechanism. They tie a team member to a specific **phase** within a **job** and assign a **delivery role** (testing, reporting, review, or management).

- Subject to all [validation and logic checks](validation.md)
- Hours are counted toward framework agreement budgets
- Trigger notifications to relevant stakeholders

### Project Slots

Project slots assign a team member to an **internal project** rather than a client job.

- Checked for overlaps with other working-time slots
- Unavailable-time overlaps (leave, etc.) are a hard block
- Working-time overlaps produce a bypassable warning

### Internal Slots

Internal slots cover non-delivery time such as leave, training, sick days, and unassigned time.

- No framework or onboarding checks
- Marked as non-working time, so they block delivery and project slots from overlapping

### Comment Slots

Comment slots are text annotations placed on the schedule. They have no validation and do not count toward any budgets or utilisation calculations.

## Creating Time Slots

To create a time slot:

1. Click on the calendar at the desired date range for a team member
2. Select the slot type from the creation menu (Phase, Project, Internal, or Comment)
3. Fill in the modal form — fields vary by type:
   - **Phase slots**: select job, phase, delivery role, start/end dates
   - **Project slots**: select project, start/end dates
   - **Internal slots**: select slot type (leave, training, etc.), start/end dates
   - **Comment slots**: enter comment text, start/end dates
4. On submit, validation checks run (for delivery and project slots)
5. If checks pass, the slot is saved and appears on the calendar

The creation endpoint receives `start`, `end`, and `resource_id` parameters from the calendar click event.

## Editing Time Slots

Existing slots can be modified in two ways:

- **Drag and resize** on the calendar — triggers a date-change endpoint that runs the same validation checks
- **Edit modal** — click a slot to open its edit form, modify fields, and save

For delivery slots, framework checks (closed, over-allocation, over-budget) apply on both create and edit operations via the `_check_framework_slot()` helper. See [Validation](validation.md) for full details.

## Clearing a Range

Schedulers can clear all slots and comments for a specific team member within a date range. This opens a confirmation modal showing all affected slots before deletion.

## Validation and Logic Checks

When creating or editing delivery slots, CHAOTICA runs a series of validation checks to prevent scheduling conflicts and framework budget issues. Checks range from hard blocks (framework closed) to bypassable warnings (overlapping working time).

For the complete list of checks and how they work, see [Scheduling Validation](validation.md).

## Permissions

Scheduling operations require the `can_schedule_job` permission, which is granted at the **organisational unit** level. The `unit_permission_required_or_403` decorator enforces this on all create, edit, delete, and date-change endpoints.

Users without this permission can still view the scheduler but cannot modify any slots.

| Action | Required Permission |
|---|---|
| View scheduler | `login_required` (any authenticated user) |
| Create / edit / delete slots | `can_schedule_job` (on the relevant org unit) |
| Clear slot range | `can_schedule_job` (on the relevant org unit) |

## Related Topics

- [Scheduling Validation](validation.md) — Full list of logic checks and bypass rules
- [Filtering](filtering.md) — Controlling which resources and slots are visible
- [Managing Phases](../Jobs/phases/managing_phases.md) — Phase setup before scheduling
- [Framework Agreements](../clients/framework_agreements.md) — Budget tracking that drives scheduling checks
