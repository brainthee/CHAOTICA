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
- `user_skill_table.html` lists every user's rating for a skill. API
  `/skills/{id}/users/` uses UserSkill scoping (A7).
- The skill matrix shows every role holder's ratings to anyone with
  `view_skill`; the API's matrix rows follow the `/user-skills/` rule (A7).
- Service coverage lists people by competency to `view_service` holders; the
  API returns counts, plus names only with `view_users_skill` (A7).
- The client page lists contacts and frameworks to anyone who can view the
  client. The API includes them only with `view_contact` /
  `view_frameworkagreement` (A6).
- The profile page shows skills and qualifications to anyone with a global
  role. The API's `/users/{id}/profile/` includes them only for yourself, your
  manager or holders of `view_users_skill` / `view_users_qualifications` (A6).
- The contact detail route (`client_contact_detail`) has no template and
  errors; contacts are only reachable through their edit modal. API contact
  refs link to the client page instead (A6).

## Logic still in template views
- Workflow buttons: four status-button templates, two workflow views and the
  bulk modal each map statuses to transitions by hand, with hard-coded ids
  (some mismatched). `jobtracker/workflow.py` is the shared description that
  the templates should render from (A9).

## Scheduler (A5)
- Utilisation: `/schedule/` uses `calculate_bulk_utilization` (via
  `collect_schedule_members`). The scheduler rows (`/schedule/resources/`)
  and the page's members feed use `get_bulk_stats`. Both feed the same
  `calculate_utilisation` engine for the window; `get_bulk_stats` also adds
  upcoming-availability ranges, which the window doesn't need.
- Holidays: everywhere it is now the user's country's holidays plus global
  ones. The page's holiday bands used to drop global holidays.

## Fixed in passing
- `/api/v1/jobs/` and `/projects/` returned the business number as `id` while
  `/{id}/` looked up the primary key. `id` is now the pk; the number is
  `job_id` / `project_id`.
- `/api/v1/timeslots/` showed slots of people who had left the viewer's unit;
  it now uses scheduler visibility (`viewable_schedule_user_pks`).
- Job/phase schedule feeds: `include_user` added anyone by id (exposing
  their other commitments); it is now limited to people the viewer may see.
- Global schedule history listed every change; it now lists only changes
  touching people the viewer may see.
- Contact and framework pages (view, edit, delete) resolved any pk under any
  client slug; they are now bound to the client in the URL.
- The service page's Performance tab covered every phase (and listed their
  clients); it now covers the phases the viewer can see, like its Jobs tab.
- Skill page Edit/Delete buttons checked `perms.chaotica.*` and never showed.
