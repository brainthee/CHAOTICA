# Sidebar Widgets

The **job** and **phase** schedule pages show a sidebar of panels alongside the timeline. They answer the questions a scheduler actually asks — *what's left to book, for whom, and by when?* — and refresh automatically after you make a change.

## Schedule Tools

Quick actions for the whole job/phase:

- **Add User** — pull an extra person onto the timeline (their full, faded schedule appears) so you can find free days before booking them.
- **Clear** — remove booked slots. You can clear **all**, **by user**, or **by role**; a confirmation shows the count before anything is deleted.
- **Move Slots** — move all of one person's slots on this job/phase to **another** person (e.g. re‑assigning work). Onboarding is re‑checked on the destination.

## Utilisation

The core planning panel: a per‑phase, per‑delivery‑role table of **Scoped**, **Scheduled** and **Remaining**, with a scheduled‑% badge.

- **Remaining** is the number that matters — how much is still to book. It's green when a role is complete, red when **over‑scheduled**, and shows "x left" otherwise.
- Each phase has a **total** row and a **confirmed vs tentative** note; the job view adds a **grand total** across all phases.
- Phase headers show the **delivery date** and days‑to‑delivery, and an **"Attention"** flag when a required role (Delivery/QA) is scoped but unscheduled, or a milestone is late.
- A **days / hours** toggle switches units; your choice is remembered across pages.

## Team Allocation

A per‑person breakdown of booked time by role, with totals.

- People **assigned** to the job/phase (Lead, Author, Tech QA, Pres QA, account managers) but with **no hours booked yet** are listed too, flagged **"Not scheduled"** — so nobody who should be on the plan is invisible.
- Role tags and a per‑role **tentative** hint are shown; the same days/hours toggle applies.

!!! tip "Team tab & XLSX export"
    For a fuller, client‑shareable view — dates, per‑capacity days (Delivery / Reporting / QA / …), roles and totals, with an **Export XLSX** button — use the **Team** tab on the job or phase detail page. On a job each member is broken down into per‑phase rows that show the role they hold on each phase.

## Phase Status (job schedule)

An at‑a‑glance strip of the job's phases: each phase's workflow **status**, its **scheduled %**, the **delivery date + countdown**, and a **needs‑attention** flag (the whole row highlights) when a required role is unscheduled or a milestone is late. Phase names link straight to the phase.

## Related Topics

- [Scheduling Concepts](concepts.md) — scoped vs scheduled/remaining, confirmed vs tentative, delivery roles
- [Scheduling Overview](overview.md) — the timeline itself
- [Booking & Validation](validation.md) — what happens when you book
