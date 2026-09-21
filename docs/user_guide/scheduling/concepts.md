# Scheduling Concepts

A reference for the terms and rules behind the scheduler.

## Time slots

A **time slot** is one booking of a person's time between a start and end. Every slot has a **type** which decides how it behaves:

- **Working** types occupy the person and count toward utilisation — Delivery, Project, and internal working time (Training, Self‑learning, Conference, Catch‑up, Interview, Service Development, Unassigned).
- **Non‑working** types mean the person is unavailable — **Leave**, **Sick**, **Bank Holiday**. These block delivery work and are **read‑only in the scheduler** (managed via leave requests).

A slot is one of:

- **Delivery** — client work tied to a **phase** (and a delivery role).
- **Project** — internal‑project work.
- **Internal** — any non‑delivery, non‑project time (including leave).

**Comments** are a separate thing: text notes placed on a person's row, with no effect on hours or utilisation.

Administrators can create additional slot types (setting *is working*, *is assignable*, and *availability*).

## Delivery roles

Delivery slots carry a **delivery role** describing the kind of work: **Delivery, Reporting, Management, QA, Oversight, Debrief, Contingency, Shadow, Other**. Each role has its **own** scoped and scheduled budget on a phase, so you can track (say) QA hours separately from delivery hours. **Delivery** and **QA** are treated as *required* allocations — if they're scoped but nothing is booked, the phase is flagged as needing attention.

## Scoped vs scheduled vs remaining

- **Scoped** — the hours *planned* for a phase (per delivery role), set when the phase is scoped.
- **Scheduled** — the hours actually *booked* as slots.
- **Remaining** — `scoped − scheduled`. Positive means there's still work to book; **negative means over‑scheduled**.

Hours are shown as **days** using the client's **hours‑per‑day** (see below); the widgets offer a days/hours toggle.

## Hours per day, business hours, working days & holidays

- **Hours per day** is a **client** setting used to convert hours ↔ days for budgets and utilisation.
- **Business hours** and **working days** come from the **organisational unit** (e.g. 09:00–17:30, Mon–Fri) and can differ per team. Bookings are snapped to a person's working hours, and a booking's *billable* hours exclude lunch and non‑working time.
- **Holidays** (per country) are excluded from billable hours and are skipped when a booking is spread **around** existing commitments.

## Confirmed vs tentative

A phase's delivery bookings are **tentative** until the phase status reaches **Scheduled – Confirmed**, after which they're **confirmed**. The scheduler colours them differently, and the Utilisation widget splits scheduled hours into confirmed vs tentative so you can see how firm a plan is.

## Availability shading

Days on which a person is **available** (free to be booked) are shaded (green by default) behind their row in the scheduler, so you can see at a glance who has capacity on any given day. A day counts as available when it's a **working day** for that person (their unit's business days), it's **not a public holiday** for their country, and they have **no booking at all** that day — anything already scheduled (delivery/internal work, leave, sick, etc.), a weekend, or a holiday is left unshaded.

Both the colour and whether the shading is shown at all are controlled on the **Settings → Appearance** page (*Schedule Colours*): the **"Shade available days"** switch turns it on/off, and **"Colour used to shade available days"** sets the colour.

## Onboarding

If a **client requires onboarding**, a person must have an onboarding record for that client before they can be booked on its delivery work (a hard block otherwise). If their onboarding is **stale** (past its renewal), booking is still allowed but warns. See the client's onboarding configuration.

## Framework budget

A client's **framework agreement** sets a total number of days that can be scheduled across its jobs. Bookings check against it: a **closed** framework blocks all scheduling; exceeding the budget either blocks (if over‑allocation isn't allowed) or warns. See [Framework Agreements](../clients/framework_agreements.md).

## One source of truth (for developers)

What appears on the schedule — the time slots, leave, holidays and per-user
availability for a date window, and *who* you're allowed to see — is assembled by
a single shared core in the backend. Both the in-app vis-timeline scheduler and
the read-only [schedule REST API](../../integration/apis.md) render from that same
core, so the calendar and the API can never disagree. Changes to what counts as
availability or which slots are shown land in one place.

## Related Topics

- [Booking & Validation](validation.md) — how these rules fire when you book
- [Sidebar Widgets](widgets.md) — where scoped/scheduled/remaining and confirmed/tentative are shown
- [Calendar Feeds](calendar_feeds.md) — iCal subscriptions and the schedule REST API
- [Framework Agreements](../clients/framework_agreements.md)
- [Managing Leave](../operations/managing_leave.md)
