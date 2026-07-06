# Scheduling Assistant

The **Scheduling Assistant** suggests *who* to book for a phase (or a job's indicative services), ranked using the data CHAOTICA already holds — skills, availability, client onboarding, qualifications and delivery history. It replaces manually cross-referencing service competency pages against the schedule.

## Where to find it

- **Phase schedule** — the **Scheduling Assistant** card in the sidebar. Click **Suggest people**.
- **Job schedule** — the **Suggest team** button, which ranks people per *indicative service* (a discovery view; book from within a specific phase).

## How suggestions are ranked

Each candidate gets a transparent **score out of 100**, built from weighted signals. Click **Why?** on any card to see exactly how the score was made up.

| Signal | What it measures |
|---|---|
| **Skill** | The candidate's competency tier for the phase's **service** — *Specialist*, *Can Do Alone*, or *With Support*. Only people who hold **all** of the service's required skills are suggested. |
| **Availability window** | The earliest run of consecutive **working days** long enough for the phase (derived from its scoped delivery hours), respecting weekends, public holidays and existing bookings. This is the strongest signal. |
| **Availability %** | How free the person is across the search window overall. |
| **Onboarding** | Whether the person is onboarded to the job's **client** (active / stale / not onboarded). |
| **Qualifications** | Whether the person holds the service's **required / desired qualifications** (see below). Missing required qualifications are flagged. |
| **History** | How many times the person has delivered **this service** before. |
| **Seniority** | The person's current job level. |

Candidates are sorted best-first, with the earliest availability breaking ties. **People already on the phase** — anyone with a booking on it, or assigned as its Lead / Author / QA — are highlighted and **pinned to the top regardless of score**, so continuing an existing team is the obvious path. Their **assigned role** is shown as a badge (e.g. *Lead*, *Author*), and they appear even if they'd otherwise fall outside the current skill or unit filters.

### What's already scheduled

The top of the panel shows the phase's **delivery utilisation** — how much is **Scoped**, how much is already **Scheduled**, and how many days **Remain**. The assistant works with what's *left*: **Days to plan** defaults to the remaining days, so you can pick up an existing plan and **continue** it rather than re-planning the whole phase. If the phase is already over-scheduled it's flagged in red.

### Splitting a phase across several people

A large phase is rarely delivered by one person for its whole duration — a 20-day web app is more likely split across three or four testers. Use the **Days to plan** and **Split across N people** controls:

- **Days to plan** defaults to the remaining delivery days (override it if you want).
- **Split across N people** divides that into per-person segments (e.g. 20 days ÷ 4 = ~5 days each).

The assistant then ranks people on their availability for a **per-person segment** rather than the whole phase, so far more people qualify. You can book each person into their slice individually, or use the team planner below.

### Drafting a whole split team

Rather than booking one person at a time, you can assemble the whole team in one pass:

1. Tick **Add to plan** on the people you want, then click **Plan split** (top of the panel).
2. The **planner** splits the scoped **man-days** evenly across the people (the day allocations always **sum to the scoped effort** — it never over-books). Choose the **coverage model**:
   - **Sequential** — people work back-to-back (elapsed time ≈ the man-days), Lead first, Author last.
   - **Parallel** — people work concurrently to compress elapsed time (e.g. 12 man-days over ~4 elapsed days with three people); the Lead is naturally present throughout.
3. By default the first person is **Lead** and the last is **Author** (one person can be **Lead & Author** — the default on a solo job). Change anyone's **role, start date or days** in the table, then **Recalculate dates** to re-lay-out, or edit days directly. Drafting also sets the phase's Project Lead / Report Author to match.
4. **Draft team** books the plan as **tentative** slots. They appear as dashed drafts on the timeline and in the sidebar for review; adjust or remove any of them, then **Confirm schedule** when you're happy.

!!! note "Scheduling checks can't be bypassed here"
    Drafting runs the **same logic checks as the normal scheduler** — over-scoping, overlaps with existing work, and client onboarding — and these **cannot be bypassed**. Any booking that would breach a check is **not created**; it's listed in the planner with the reason so you can fix it (change the person, dates or split) and draft the rest. This keeps the assistant from ever quietly over-scheduling a phase.

### Turning signals on and off

Not every signal matters on every booking. Use the **Signals** checkboxes at the top of the panel to toggle **Onboarding, History, Qualifications** and **Seniority** on or off, then click **Update** to re-rank. **Skill** and **Availability window** are always on.

The pool of people considered is always limited to those you have permission to schedule, defaulting to the job's organisational unit.

## Acting on a suggestion

Each candidate card offers:

- **Book…** — opens the normal booking dialog, pre-filled with that person and their earliest free window. All the usual [booking validations](validation.md) (onboarding, overlaps, scope) still run. The booking is created as a **draft** (see below).
- **Lead** / **Author** — one-click assigns the person as the phase's Project Lead or Report Author.

## Draft (proposed) schedules

Bookings you create from the assistant are **tentative** until you commit them — CHAOTICA's existing tentative mechanism *is* the draft mode:

- Proposed bookings appear on the timeline as **dashed "ghost" blocks**, clearly distinct from confirmed work, and are listed under **Proposed team (draft)** in the assistant sidebar card.
- Reassign or remove a proposal exactly like any slot — **drag** it on the timeline, or **double-click** to edit/delete. Nothing is committed yet.
- When you're happy, click **Confirm schedule** to move the phase to *Scheduled (Confirmed)*. The ghost styling clears and the bookings become confirmed work.

This lets you build up and rework a proposed team freely before committing.

## Setting a service's skills & qualifications

Suggestions are only as good as a service's definition. On the **Service** edit page set the:

- **Required / Desired skills** — required skills gate who can be suggested and drive the competency tier.
- **Required / Desired qualifications** — required qualifications are matched against people's **awarded** qualification records; anyone missing a required one is flagged on their card.

## Related Topics

- [Booking & Validation](validation.md) — what happens when you book
- [Scheduling Concepts](concepts.md) — confirmed vs tentative, scoped vs scheduled
- [Sidebar Widgets](widgets.md) — the other schedule panels
- [Qualifications](../qualifications/overview.md)
