# API / UI coexistence — debt register (working list)

Where the main UI and `/api/v1/` differ, or where page logic still lives in a
template view instead of a shared selector. `/api/v1/` never widens access
beyond the UI; where the UI is *looser* than the API's stance, the API stays
strict and the gap is listed here. To be cleaned up as pages move onto the API.

## UI looser than the API
- Global site search lists every active user to every signed-in user. API
  search returns them as identity-only refs, the same as the UI. The API's
  `/users/` list stays gated on `view_user`, which no default role holds.
- Job Sales tab shows staff cost and profit to anyone who can view the job
  (`views/job.py` `view_job_sales`). The API sends these figures only with
  `can_view_loaded_costs` (A3).
- Support-team money is hidden in the template only; the API strips it on
  the server (A3).
- The user profile page is open to any user with a global role, and its
  Schedule History tab is ungated. The API does not expose schedule history
  (A6).
- Service performance metrics cover every phase, not only those the viewer
  can see (`Service.get_performance_metrics`). The API scopes them (A7).
- `user_skill_table.html` lists every user's rating for a skill. API
  `/skills/{id}/users/` uses UserSkill scoping (A7).
- The skill matrix base set isn't limited by unit (A7).

## Logic still in template views
- Workflow buttons: four status-button templates, two workflow views and the
  bulk modal each map statuses to transitions by hand, with hard-coded ids
  (some mismatched). `jobtracker/workflow.py` is the shared description that
  the templates should render from (A9).

## Fixed in passing
- `/api/v1/jobs/` and `/projects/` returned the business number as `id` while
  `/{id}/` looked up the primary key. `id` is now the pk; the number is
  `job_id` / `project_id`.
- `/api/v1/timeslots/` showed slots of people who had left the viewer's unit;
  it now uses scheduler visibility (`viewable_schedule_user_pks`).
