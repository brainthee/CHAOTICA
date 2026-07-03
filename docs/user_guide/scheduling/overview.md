# Scheduling Overview

The scheduler is the central tool for allocating team members to jobs, phases, projects, and internal activities. It presents a **timeline** where each row is a team member and their bookings appear as blocks across the dates they're working.

CHAOTICA's scheduler is built on [vis-timeline](https://visjs.github.io/vis-timeline/) — a single, continuously-scrolling, zoomable timeline (there is no longer a paged month/week calendar). Work is booked **by the day**, so bookings render as whole‑day blocks even though the underlying times follow each person's working hours.

## Where the scheduler appears

| Surface | URL | What it shows | Who can open it |
|---|---|---|---|
| **Global scheduler** | `/scheduler/` | Everyone (filterable) across the org | Any signed‑in user |
| **Job schedule** | `Job → Schedule` | The job's team, all its phases | Users with `view_job_schedule` on the job |
| **Phase schedule** | `Phase → Schedule` | The phase's team only | Users with `view_job_schedule` on the job |
| **Read‑only tab** | `Job`/`Phase` detail → *Schedule* tab | An embedded, read‑only timeline | Users with `view_job_schedule` |

Viewing a schedule and **editing** it are separate rights:

| Action | Required permission |
|---|---|
| View the global scheduler | Any authenticated user |
| View a job/phase schedule | `jobtracker.view_job_schedule` (on the job) |
| Create / edit / delete / move slots | `jobtracker.can_schedule_job` (on the relevant **organisational unit**) |

Users without `can_schedule_job` can look but not change anything — the create/edit actions simply aren't offered, and the backend refuses them.

!!! note "Job/phase views show the *full* schedule"
    On a job or phase schedule, each person's **other** commitments (other jobs, leave, internal time) are still shown — just **faded** — so an empty gap can be trusted as genuinely free. Only the current job/phase's work is shown in full colour.

## Reading the timeline

**Resource rows** — each row header shows the person's name, job level, a **utilisation %** badge (red ≥ 90%, green ≥ 70%, amber ≥ 40%), and, on job/phase schedules, small **role tags** (Account Manager, Lead, Author, Tech QA, Pres QA, …) so you can see who's doing what.

**Blocks** are colour‑coded (a legend sits in the toolbar):

- **Confirmed** vs **Tentative** delivery work (a phase is *confirmed* once its status reaches *Scheduled – Confirmed*; before that its bookings show tentative).
- **Project** and **Internal** time have their own colours; **onsite** delivery is shaded differently to remote.
- **Weekends and holidays** are lightly shaded; the current day is highlighted.
- **Faded** blocks are out‑of‑scope context on a job/phase view (see the note above) and can't be edited from there.

## Getting around

- **Scroll** moves the resource list up/down; **Ctrl/⌘ + scroll** (or pinch) zooms in/out smoothly. The time axis re‑scales itself day → week → month → year.
- **Zoom** buttons and quick‑zoom presets (2w / 2m / 6m / 1y) are in the toolbar.
- **Today** re‑centres on the current week; **Fit** zooms to the *actual data* (the earliest→latest booking in scope), so repeatedly pressing Fit is stable rather than creeping outward.
- **Pan / Select** mode toggle: *Pan* (default) drags the timeline; *Select* lets you drag a box across rows and dates to act on several people at once (see below).

## Booking work

**Right‑click** a resource row (on empty space) to open the booking menu:

- **Assign phase** — book delivery work against a job's phase (the main booking action).
- **Assign project** — book time on an internal project.
- **Assign internal** — book internal/non‑delivery time (training, self‑learning, etc.).
- **Add comment** — drop a text note on someone's row.
- **Clear range** — remove that person's slots across the dragged range.

Pick the dates by right‑clicking a single day, or in **Select** mode drag across the days you want first.

### Booking for several people at once

Switch to **Select** mode and drag a box across **multiple rows and a date range**. The booking menu then applies to everyone selected:

- **Assign phase/project/internal / Add comment** create a slot for each person (one modal, one confirmation). Anyone who's blocked (e.g. not onboarded) is skipped and reported; bypassable warnings can be forced for all at once.
- **Clear range** clears the range for every selected person.

### Slot types

| Type | Purpose | Notes |
|---|---|---|
| **Delivery (phase)** | Client work against a phase + a **delivery role** (Delivery, Reporting, Management, QA, Oversight, Debrief, Contingency, Shadow, Other) | Full validation (framework, onboarding, scope, overlaps). Counts toward the framework budget. |
| **Project** | Internal‑project time | Overlap checks only. |
| **Internal** | Training, self‑learning, conferences, leave, sick, etc. | No framework/onboarding checks. |
| **Comment** | A text annotation | No validation; doesn't count toward utilisation. |

See [Booking & Validation](validation.md) for exactly which checks run and how the overlap chooser works.

## Editing and moving

- **Double‑click** a block to open its edit modal.
- **Drag** a block to move its dates and/or drop it on a different person's row — both happen in one action; the destination person's working hours are applied automatically.
- **Resize** a block to lengthen/shorten it.

!!! warning "Leave and time off are read‑only here"
    Annual leave, sick and bank‑holiday slots **cannot be moved or edited from the scheduler** — the block isn't draggable and the backend refuses the change. Manage those through the leave request (see [Managing Leave](../operations/managing_leave.md)).

## Clearing a range

The right‑click **Clear range** (and the sidebar **Clear** tool on job/phase pages) shows a confirmation listing exactly what will be removed before anything is deleted. On job/phase pages you can also clear by **all / a specific user / a specific role**.

## Exporting the schedule

The **Schedule** tab on a job or phase has an **Export XLSX** button that downloads a themed, client‑ready Excel workbook — handy for sharing a plan with a client or working offline.

- **Overview** sheet — a cover page with the title, key stats (client, job/phase, service, status, dates, lead, author, scoped days, reports, onsite) and a **colour key**.
- **Schedule** sheet — a grid of **Resources** (rows) against a **continuous run of dates** (columns, no missing days). Each booked cell names the phase (with its ID, e.g. *5557‑4: Azure Cloud Config (Delivery)*) and the **delivery type**, shaded in the **same colours as the on‑screen scheduler** (confirmed vs tentative, onsite vs remote). Days a resource is committed elsewhere are marked **Unavailable** (or **Leave** for time off) so a blank cell can be trusted as genuinely free — clients won't mistake other commitments for spare capacity. Other clients' work is never named.
- **Summary** sheet — one row per phase with its ID, the full hours breakdown (Delivery, Reporting, Mgmt, QA, Oversight, Debrief, Contingency, Other) and the assigned Lead, Author, Tech QA and Pres QA.

A **client‑level** export is also available (`Client → Schedule → Export`): pick a **date range** and, optionally, a single **framework agreement** to scope which jobs are included. The Overview records the client, chosen range and framework.

## Related Topics

- [Scheduling Concepts](concepts.md) — slots, delivery roles, scoped vs scheduled, confirmed/tentative, hours‑per‑day
- [Booking & Validation](validation.md) — logic checks and the around/over/destructive overlap chooser
- [Filtering](filtering.md) — controlling which resources and slots are shown
- [Sidebar Widgets](widgets.md) — utilisation, team allocation and phase‑status panels on job/phase pages
- [Calendar Feeds](calendar_feeds.md) — subscribing to your schedule in Outlook/Google/etc.
- [Framework Agreements](../clients/framework_agreements.md) — the budget that drives scheduling checks
