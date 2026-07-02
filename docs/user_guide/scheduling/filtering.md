# Filtering

The **global scheduler** (`/scheduler/`) can show a lot of people, so it has a filter panel to narrow the resource list and control ordering. Open it from the **filter** toggle; the panel slides in from the side.

!!! note "Global scheduler only"
    Filters apply to the global scheduler. The **job** and **phase** schedules are already scoped to that job/phase's team and ignore these filters — use the **Add User** tool there instead (see the end of this page).

## Applying filters

Set the fields you want and **apply** — the timeline re‑fetches in place (no full page reload) and the URL updates so the view is shareable/bookmarkable. **Reset to default** clears everything.

## Available filters

| Filter | What it does |
|---|---|
| **Ordering** | Sort rows by Name, Last name, Availability, Utilisation, Seniority, or Distance. |
| **Reverse** | Flip the sort direction. |
| **Compressed view** | Tighter row/label layout for fitting more people on screen. |
| **Filter by city / distance** | With *Ordering = Distance*, orders people by straight‑line distance from the chosen city (needs user locations set). |
| **Skills — Specialist / Independent / Requires support** | Show only people with the chosen skills at that competency. |
| **Teams** | Restrict to members of the selected team(s). |
| **Services** | Restrict to people associated with the selected service(s). |
| **Organisational units** | Restrict to the selected unit(s). |
| **Org‑unit roles** | Restrict to people holding the selected unit role(s). |
| **Job levels** | Restrict to the selected job level(s). |
| **Date range (from / to)** | The window to load. |
| **Users** | Show specific named people. |
| **Jobs** | Restrict to people working the selected job(s). |
| **Phases** | Restrict to people working the selected phase(s). |
| **Onboarded to** | Restrict to people onboarded to the selected client(s). |
| **Show inactive users** | Include deactivated accounts. |

Most multi‑selects are type‑ahead (Select2) autocompletes.

!!! tip "Finding the Red Team / a particular group"
    Set up a **Team** for the group and filter by it (Teams field). Team membership then becomes a one‑click filter on the scheduler.

## Adding one more person (Add User)

On a **job or phase** schedule, use the **Add User** tool (in the sidebar Schedule Tools) to pull an extra person onto the view even if they have nothing booked yet. Their full (faded) schedule appears so you can find free days before booking them. Under the hood this adds an `include_user` to the members request; it doesn't change who's on the job until you actually book them.

## Related Topics

- [Scheduling Overview](overview.md) — the timeline interface
- [Sidebar Widgets](widgets.md) — the Add User / Clear / Move tools
- [Organisational Units](../organisational_units/overview.md) — units and roles used in filters
