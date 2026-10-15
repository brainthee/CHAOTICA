# Team Overview

Teams group users together for coordination, debriefs, and reporting. A team's
membership is independent of organisational units — a team draws its analytics
from its members' scheduled work rather than from job ownership.

## Team detail page

The team detail page has these tabs:

- **Team** — the membership list, including former members (shown as
  "Left").
- **Stats** — quantitative analytics (loaded on demand, see below).
- **Debrief** — a weekly delivery debrief (team owners and admins only).
- **Billing** — members' billing-code hours for a timesheet period (team owners
  and admins only). See
  [Team and unit billing tabs](../clients/billing_codes.md#team-and-unit-billing-tabs).

## Stats tab

The **Stats** tab is loaded lazily the first time it is opened, so the base
page stays fast. Because a team has no direct job-ownership relationship, every
figure is derived from the scheduled `TimeSlot`s of the team's active members
(phases/jobs a phase is counted once even when several members are booked on
it).

### Date range and membership

The header has quick ranges (**30d**, **3m**, **6m**, **12m**) and a custom
range picker; the default is the last three months. Changing the range
reloads the tab in place.

Membership is date-aware. Anyone whose membership overlaps the range is
included — even if they have since left the team — but only for the days they
were a member: their membership is clipped to the range, and only time booked
inside that window counts. People who joined after the range ended are left
out. In the member table, anyone who joined or left part-way through is marked
with the date.

It shows:

- **Summary tiles** — members in the range, jobs worked on, phases delivered,
  and the team's confirmed utilisation over the range.
- **Upcoming availability** — confirmed / tentative / internal / available
  time across the coming one, two, four and eight weeks. This is
  forward-looking and always uses the *current* members, regardless of the
  date range. Each bar is 100% of the effective working days (leave and public
  holidays removed), and each day is counted in exactly one segment
  (confirmed, then tentative, then internal, then available).
- **Delivery throughput** — phases delivered per month in the range.
- **Service breakdown** — phases worked on in the range by service, as a radar
  chart. The eight busiest services are shown individually and the rest are
  grouped as "Other (N services)".
- **Job pipeline** — jobs worked on in the range, grouped by current status.
- **Member utilisation** — a per-member table of confirmed utilisation and
  available days over the range, for the days each person was a member.

The **Detail** panel (bottom right) shows the raw JSON behind the current
Stats view.

Utilisation always uses the [central utilisation
formula](../scheduling/overview.md) — confirmed client-delivery days over
effective working days.
