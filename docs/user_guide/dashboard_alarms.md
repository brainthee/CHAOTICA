# Dashboard Alarms

The dashboard's **Alarms** tab lists phases and jobs that need attention. What
you see depends on your role: unit managers see every alarm in their units,
TQA / PQA reviewers see QA alarms unit-wide, schedulers see scheduling alarms
unit-wide, and everyone sees alarms for work they're on (booked, lead, report
author, or on the job's account/scoping team).

There are two groups. The red count on the tab is **overdue** only; stale items
have their own grey count.

!!! info "Tabs load on demand and keep themselves fresh"
    The dashboard opens on **Alarms** when you have overdue work (otherwise on
    **Schedule**), and only that tab is loaded up front. Every other tab — My Jobs,
    My Phases, In Flight, Scheduled This Week, Upcoming Reports, Scoping, Signoff,
    TQA, PQA, Pending Delivery, My Team, Team Leave — loads the first time you open
    it. Badge counts are shown straight away.

    The tab you're looking at **refreshes itself every 3 minutes** (the Schedule tab
    re-fetches its calendar), and its badge updates; an *Updated hh:mm* note shows
    when. Refreshing pauses while the browser tab is hidden and catches up as soon as
    you come back after a longer absence. Table search, page and scroll position are
    kept across refreshes.

## Overdue

Live work that's late or missing something:

| Alarm | Means |
|---|---|
| Delivery overdue | The phase's wanted/scheduled delivery date has passed. |
| Tech QA / Pres QA overdue | The phase is past its TQA / PQA due date and still before / in that QA stage. |
| No Tech QA / Pres QA | In (or waiting for) QA with no reviewer assigned. |
| Unscheduled | Marked as scheduled (or later) but with no bookings. |
| No billing code | Booked work with no billing code to charge it to. |
| Job overdue | The job's delivery date has passed. |

## Stale

Work that has stopped moving. These are left out of the overdue lists so those
only show genuinely late work, and nobody gets daily late reminders for them —
someone needs to pick them back up or close them off.

| Alarm | Means | Usually |
|---|---|---|
| **Stalled phases** | Schedule Tentative to In Progress, with no status change for `STALE_PHASE_DAYS` and nothing booked since. | Move it on (e.g. to QA), postpone or cancel it. |
| **Jobs with no live phases** | Scope signed off or later, every phase finished, but the job can't complete — usually all phases were cancelled. | Close the job (Lost before it's In Progress, otherwise Delete) or add the missing work. |
| **Never booked** | Pending Scheduling with the wanted delivery date more than `STALE_PHASE_DAYS` ago and nothing ever booked. | Re-date, postpone or cancel it. |
| **Long postponed** | Postponed for more than `STALE_POSTPONED_DAYS` (a postponed phase stops its job completing). | Bring it back to Pending Scheduling or cancel it. |
| **Dormant jobs** | Draft, scoping or sign-off with no status change for `STALE_JOB_DAYS`. | Move it on or close it as Lost. |

QA and awaiting-delivery phases never count as stalled: waiting on a reviewer
with nothing booked is normal there, so they stay in the overdue alarms and
keep their reminders.

The thresholds are on **Settings → Stale Alarms** (see
[CHAOTICA settings](../administration/chaotica_settings.md)).

## Related behaviour

- Starting a phase moves its job to **In Progress** from either Pending Start
  or Scoping Complete, so jobs can't get stuck short of auto-completing.
- A job only completes (automatically or by hand) if at least one phase was
  **delivered**. A job whose phases were all cancelled delivered nothing; it
  shows under *Jobs with no live phases* instead.
