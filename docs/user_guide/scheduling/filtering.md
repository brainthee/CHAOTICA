# Filtering

The **global scheduler** (`/scheduler/`) can show a lot of people, so it has a filter panel to narrow the resource list and control ordering. Open it from the **filter** toggle; the panel slides in from the side.

!!! note "Global scheduler only"
    Filters apply to the global scheduler. The **job** and **phase** schedules are already scoped to that job/phase's team and ignore these filters — use the **Add User** tool there instead (see the end of this page).

## Applying filters

Set the fields you want and **apply** — the timeline re‑fetches in place (no full page reload) and the URL updates so the view is shareable/bookmarkable. **Clear filters** removes everything and shows the full resource list.

## Saving a default view

If you always open the scheduler to the same view (for example your own team or organisational unit), you can save it so it loads automatically.

1. Set the filters you want.
2. In the filter panel, under **Default view**, click **Set as my default**.

Next time you open `/scheduler/` with no filters in the URL, it loads your saved default automatically. When a default is applied you'll see a subtle **Default view** badge next to the filter toggle and a note in the panel. Changing the filters and applying drops the badge (you're now on a custom view) without touching the saved default.

- **Clear filters** shows everything *this visit* but keeps your saved default for next time.
- **Clear my default** (in the panel) removes the saved default entirely, so future visits open unfiltered.

!!! note "Personal and non‑privileged"
    Your default is stored against your own account only — it doesn't affect anyone else. It's purely a display shortcut: it can only narrow what you're already allowed to see and never grants access to extra people, jobs, or phases.

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
