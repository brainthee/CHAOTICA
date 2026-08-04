# Team Overview

Teams group users together for coordination, debriefs, and reporting. A team's
membership is independent of organisational units — a team draws its analytics
from its members' scheduled work rather than from job ownership.

## Team detail page

The team detail page has three tabs:

- **Team** — the current membership list.
- **Stats** — quantitative analytics (loaded on demand, see below).
- **Debrief** — a weekly delivery debrief (team owners and admins only).

## Stats tab

The **Stats** tab is loaded lazily the first time it is opened, so the base
page stays fast. Because a team has no direct job-ownership relationship, every
figure is derived from the scheduled `TimeSlot`s of the team's active members
(phases/jobs a phase is counted once even when several members are booked on
it).

It shows:

- **Summary tiles** — active members, active jobs the team has time booked on,
  phases delivered in the selected range, and the rolling four-week
  utilisation.
- **Future Utilisation** — confirmed / tentative / non-delivery / available
  time as percentages across the coming one, two, four and eight weeks.
- **Delivery Throughput** — phases delivered per month over the last six
  months.
- **Service Breakdown** — the mix of services the team's members have worked
  on, drawn as a radar chart.
- **Job Pipeline** — the jobs the team has scheduled time on, grouped by
  status.
- **Member Utilisation** — a per-member table of confirmed utilisation and
  available days over the selected range.

Utilisation always uses the [central utilisation
formula](../scheduling/overview.md) — confirmed client-delivery days over
effective working days.
