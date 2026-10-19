# API / UI coexistence

The main UI and `/api/v1/` share selectors (`jobtracker/selectors/`), the
permission facade (`jobtracker/policy.py`) and the workflow table
(`jobtracker/workflow.py`). The API never shows more than the UI. Where the
UI is currently *looser* than the API, the API stays strict and the gap is
listed here, so each one can be closed in the UI or accepted deliberately.

## Where the UI is looser than the API

| Area | UI today | API |
|---|---|---|
| Site search, people | Lists every active user to every signed-in user | Same people, as identity-only refs. `/users/` requires `view_user`, which no default role holds |
| Job Sales tab | Staff cost and profit shown to anyone who can view the job | Only with `can_view_loaded_costs` |
| Support-team money | Hidden by the template only | Removed on the server |
| User profile page | Open to any global role; the Schedule History tab is ungated | Skills and qualifications only for self, manager, or `view_users_skill` / `view_users_qualifications`; schedule history not exposed |
| Skill page user table, skill matrix | Every holder's rating shown to anyone with `view_skill` | Follows the `/user-skills/` rule |
| Service coverage | Names people by competency to `view_service` holders | Counts only; names require `view_users_skill` |
| Client page | Contacts and frameworks shown to anyone who can view the client | Require `view_contact` / `view_frameworkagreement` |

## Same as the UI (accepted for now)

These are as open in the API as in the UI. They are listed because they're
worth a decision.

- **Job contacts:** a job's primary and additional contacts (with phone and
  email) are shown to anyone who can view the job. The people delivering the
  job need them. The client page is stricter (see above).
- **Framework usage:** a framework's usage lists every job and person on the
  framework, including jobs the viewer can't open.
- **Schedule history text:** a history entry is shown when it touches anyone
  whose schedule you can see. Its summary or override reason may name other
  people.
- **Restricted jobs:** marked (`is_restricted`) but not hidden.

## Pages still using page endpoints

- **Scheduler writes:** create, move, delete, revert and undo, plus the
  `ws/schedule/` socket. All scheduler *reads* use `/api/v1/`.
- **Dashboard tab partials:** server-rendered HTML, built from the same
  selectors as `/api/v1/me/dashboard/`.

## Known follow-ups (not blocking)

- **Phase detail:** about 40 queries, 19 of them the same membership lookup
  repeated by the workflow readiness checks. It should be memoised per
  request.
- **`/me/dashboard/`:** about 80 queries and 0.5–0.7s on production-sized
  data. The queue counts would benefit from short per-user caching.
- **Payload sizes:**
  - `/schedule/` is about 700 KB per 28 days unfiltered.
  - `/skills/matrix/` is about 1.3 MB; it could send only non-default cells.
  - JSON responses are not gzip-compressed by the app. Enable it at the
    proxy (`gzip_types application/json`).
- **Global schedule history:** filtered in Python over the latest 1,000–2,000
  actions. Storing affected users in an indexed column would let SQL do it.
- **Realtime across instances:** live socket pushes, single-use tickets and
  throttle counters need a Redis shared by every app instance. A
  per-container Redis only reaches sockets on the same instance; the
  notification badge falls back to polling every 5 minutes.
