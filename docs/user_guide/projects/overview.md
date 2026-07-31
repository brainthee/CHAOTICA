# Projects Overview

Projects are lightweight engagements that link directly to scheduled time. They
are typically imported from an external Resource Manager (RM) and, unlike jobs,
have no phases — each project links straight to its `TimeSlot`s, and each slot
carries its own delivery role.

## Project detail page

The project detail page opens on descriptive information (point of contact,
unit, client, billing codes, status/state, dates, and the RM source link) and
provides four tabs:

- **Overview** — the free-text project overview.
- **Stats** — quantitative analytics (loaded on demand, see below).
- **Team** — each member's contribution to the project.
- **Schedule** — a read-only timeline of the project's booked time.

## Stats tab

The **Stats** tab is loaded lazily the first time it is opened, so the base
page stays fast. Every figure is aggregated from the project's own timeslots
and converted to days using the client's configured hours-in-day (or the
`DEFAULT_HOURS_IN_DAY` setting when no client is set):

- **Summary tiles** — total, used (in the past) and scheduled (upcoming) days,
  team size, and the confirmed-vs-tentative day split. A project's time counts
  as confirmed when the project is a deliverable in the Confirmed state, and as
  tentative when it is a deliverable in the Tentative state.
- **Team** — a per-member breakdown of used / scheduled / total days on the
  project, each member's delivery role(s), and their share of the total.
- **Delivery Type** — days split by delivery role (Delivery, Reporting, QA,
  etc.), shown as a table and a bar chart.
- **Monthly Burn-down** — days consumed per month with a running cumulative
  total.

The **Team** tab shows the same per-member contribution table.

!!! note
    Projects carry no revenue and no service link on their slots, so the stats
    are deliberately non-financial and have no per-service breakdown — that
    analysis lives on [framework agreements](../clients/framework_agreements.md)
    and [organisational units](../organisational_units/overview.md).
