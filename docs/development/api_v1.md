# REST API (v1)

CHAOTICA's API lives under `/api/v1/`. It is the single API for every client:
integrations, standalone UIs (such as LCARS), and the main web UI itself, whose
scheduler, job/client lists, search and notifications all read from it.

It is **read-mostly**. You can read the dashboard, jobs and phases (plus
everything they link to), the scheduler, and skills, services and
qualifications. Writes are limited to:

- notifications (mark as read);
- a few per-user HR actions ([below](#writes-user-administration)).

The API is built from the **same selectors and policy code as the web pages**.
It therefore never shows a user more than the UI would. Where the UI is
currently looser, the API stays strict (see
[API / UI coexistence](api_coexistence.md)).

!!! info "The contract is the schema"
    The OpenAPI schema is the source of truth for every endpoint, parameter and
    field. It is committed at `docs/api/openapi-v1.yaml`, CI fails if it drifts
    from the code, and it is served live at:

    - `/api/v1/schema/swagger-ui/`
    - `/api/v1/schema/redoc/`
    - `/api/v1/schema/`

    This page covers what the schema can't: auth, conventions and behaviour.

## Authentication

Every endpoint except `/meta/` requires a signed-in, **active** user. Every
request is scoped to that user's own permissions, whichever method is used.

| Method | For | How |
|---|---|---|
| **OAuth2 + PKCE** | browser apps on another origin (e.g. LCARS), anything acting *for* a person | `Authorization: Bearer <access token>` |
| **API token** | scripts and server-to-server integrations | `Authorization: Token <key>` |
| **Session** | the main web UI and the browsable API | the CHAOTICA session cookie (same origin only) |

A bearer token takes precedence when a request carries more than one.

### OAuth2 (authorization code + PKCE)

This is off by default. To turn it on, enable `API_OAUTH2_ENABLED` (**Settings
→ Access → Authentication**) and register the client as a
[Connected App](../administration/connected_apps.md). While it is off, `/o/`
returns 404 and bearer tokens are ignored.

- **Flow:** authorization code with PKCE, `S256` only. Public clients, so there
  is no client secret. Implicit, password and client-credentials grants are
  refused.
- **Endpoints:**

  | Purpose | Endpoint |
  |---|---|
  | Authorize | `/o/authorize/` |
  | Token and refresh | `/o/token/` |
  | Revoke | `/o/revoke_token/` |

  `/meta/` advertises these under `auth.oauth` whenever OAuth is enabled.
- **Sign-in:** `/o/authorize/` sends the user through the normal CHAOTICA
  login (SSO or local), then to a consent page. Trusted apps skip consent.
  Authorization is refused while impersonating another user.
- **Scopes:** `read` (the default) and `write`. A bearer token without `read`
  gets 403.
- **Lifetimes:**
  - Access tokens last 1 hour.
  - Refresh tokens last 30 days and rotate on every use. Reusing an old refresh
    token revokes the whole token family.
- **Revocation:** tokens are revoked when the user does so from **Profile →
  Connected apps**, when an admin deletes the app, or when the account is
  deactivated. Tokens of inactive users are rejected (401).
- **CORS:** `/api/v1/` and `/o/token|revoke_token/` accept cross-origin calls
  only from a Connected App's *allowed origins*, plus the `CORS_ALLOWED_ORIGINS`
  env var. Credentials (cookies) are never allowed cross-origin.

### API tokens

API tokens are long-lived and inherit exactly their owner's permissions. Treat
them like passwords. You can get one in three ways:

- **Profile → API Token**, where you can generate, view, regenerate or revoke it.
- `POST /api/v1/auth/token/` with `username` (email) and `password`. This is
  available only while local login is enabled, and is throttled to 10/min.
- On the server: `python manage.py drf_create_token <email>`.

```bash
curl -H "Authorization: Token <key>" https://your-instance/api/v1/me/
```

### Realtime (WebSockets)

| Socket | Sends |
|---|---|
| `ws/me/` | `{"type": "unread", "count": N}` on connect and whenever your unread notifications change |
| `ws/schedule/global/`, `ws/schedule/job/{id}/`, `ws/schedule/phase/{id}/` | scheduler deltas: `{"type": "delta", ...}` |

**How a socket authenticates:**

- **Session-cookie sockets** must come from the CHAOTICA origin itself.
- **Other clients** call `POST /api/v1/realtime/ticket/`, which returns
  `{ticket, expires_in, ws_url}`, then connect to `…/ws/me/?ticket=<ticket>`.
  A ticket is single-use and expires after 30 seconds.

Sockets are closed with code `4401` when the user's tokens are revoked or their
account is deactivated.

### Maintenance and setup

- In maintenance mode, every endpoint returns `503` with the error code
  `maintenance`. Superusers are the exception.
- Before first-run setup is complete, every endpoint returns `503`.
- `/meta/` reports `maintenance` so clients can show a banner.

## Conventions

- **References.** Every relation is an object:
  `{"id", "type", "display", "url", "web_url"}`.
  - `url` is the API resource, or null if the type has none.
  - `web_url` is the page in the main UI.
- **Ids.** `id` is always the primary key used in `/{id}/` URLs. Jobs and
  projects also carry the number people quote, as `job_id` / `project_id`.
- **Workflow and capabilities.**
  - Job and phase detail responses include a `workflow` block: grouped `steps`,
    plus the transitions available to *you*, with labels identical to the UI's
    buttons.
  - They also include a `capabilities` block of booleans for what you may do.
    Show or hide actions from these, rather than re-deriving permissions on the
    client.
- **Lists:**
  - Paginated as `{count, next, previous, results}`.
  - `?page=` and `?page_size=` (default 50, max 200).
  - `?q=` searches.
  - `?ordering=` takes a per-resource allowlist, shown in the schema.
  - Resource filters are listed in the schema.
  - `me` is accepted wherever a user id is, e.g. `?lead=me`.
  - Dashboard queues are list filters, e.g. `/jobs/?queue=scoping` and
    `/phases/?queue=tqa`.
- **Times.** Always UTC (ISO 8601). Localise using `tz` from `/me/`.
- **Errors.** All errors use one envelope:

  ```json
  {"error": {"code": "not_found", "message": "Not found."}}
  ```

  | Code | When |
  |---|---|
  | `not_authenticated` | 401 |
  | `permission_denied` | 403 |
  | `not_found` | 404 |
  | `invalid` | validation error; includes `fields` |
  | `throttled` | rate limit hit; includes `retry_after` |
  | `maintenance` | 503 |
- **Throttling.** 60/min anonymous and 600/min per user by default.
  - Adjust with the `API_THROTTLE_ANON` / `API_THROTTLE_USER` env vars.
  - Set `API_NUM_PROXIES` to the number of reverse proxies in front of the app
    so client IPs are read correctly.

## Access and sensitive data

The API applies the UI's own rules, and is stricter wherever the UI is loose:

- **Jobs, phases and projects:** visible if you hold a view permission on the
  unit, are involved with the job, created it, or hold the per-job permission.
  Deleted jobs are never visible. Restricted jobs carry `is_restricted`; as in
  the UI, they are not hidden.
- **Schedules** (timeslots, `/schedule/`, history, deltas): follow the
  scheduler's visibility (`view_users_schedule` in your units, plus yourself).
- **Leave:** follows *Manage Leave* (yourself, your reports, and units where you
  can view all leave). Schedule windows also include other people's
  *approved* leave, as the scheduler draws it, but without notes or approver.
- **Money:**
  - Loaded costs, staff cost and profit appear only with
    `can_view_loaded_costs`.
  - Support-team money is removed on the server.
  - Billing codes appear only as badges.
- **People:**
  - User refs carry identity only.
  - The `contact` block on `/users/{id}/` (email, phone) requires `view_user`.
  - Skill and qualification data requires being that user, their manager, or
    holding the relevant view permission.
- **Never serialised:** certificate files.

## Resources

The full list, with parameters and fields, is in the schema. In outline:

| Area | Endpoints |
|---|---|
| Platform | `meta/`, `me/`, `me/preferences/`, `search/?q=`, `search/goto/?id=`, `realtime/ticket/` |
| Dashboard | `me/dashboard/` (queues and stats), `me/alarms/`, `entropy/`, `notifications/` (+ `unread-count/`, `mark-read/`, `mark-all-read/`) |
| Jobs | `jobs/`, `jobs/{id}/` + `phases/`, `team/`, `sales/`, `support-team/`, `schedule/`, `notes/`, `activity/` |
| Phases | `phases/`, `phases/{id}/` + `team/`, `feedback/`, `schedule/`, `notes/`, `activity/` |
| Projects | `projects/`, `projects/{id}/` + `schedule/` |
| Scheduler | `schedule/` (+ `resources/`, `actions/`, `deltas/`, `bounds/`), `me/schedule/`, `users/{id}/schedule/`, `timeslots/`, `timeslot-comments/`, `timeslot-types/`, `leave-requests/` |
| Clients | `clients/`, `clients/{id}/` + `jobs/`, `contacts/`, `frameworks/`; `contacts/`, `frameworks/` |
| People | `users/`, `users/{id}/` + `profile/`, `stats/`; `org-units/`, `org-units/{id}/` + `members/` |
| Catalogue | `skills/` (+ `matrix/`, `{id}/users/`), `skill-categories/`, `user-skills/`, `services/{id}/` + `coverage/`, `metrics/`, `phases/`; `qualifications/` (+ `{id}/records/`), `qualification-records/`, `awarding-bodies/` |

### Schedule windows

`/schedule/`, `me/schedule/`, `users/{id}/schedule/` and the
job/phase/project `schedule/` endpoints all return one composite object for a
date window, not a paginated list. Each contains:

- users and timeslots, where each slot has a `display` block with the colours
  and title the scheduler draws;
- leave, holidays (the user's country plus global ones), comments and
  availability;
- a `refs` lookup for phases and projects.

| Param | Default | Notes |
|---|---|---|
| `start` | today | `YYYY-MM-DD` |
| `end` | `start` + 28 days | the span must be 366 days or fewer |

Invalid, inverted or over-long windows return `400`.

The global schedule also takes the scheduler's own filters (unit, user, skills,
and so on; see the schema). `schedule/resources/` returns the scheduler's rows
in display order. `schedule/deltas/?since=` returns changes since a timestamp,
for polling clients.

## Writes: user administration

These per-user actions let an HR or directory sync push people data into
CHAOTICA. Each reproduces the permission gate of its UI equivalent. All of them
compare against the current state, so replaying a full import each run is
safe: unchanged people are no-ops (`"changed": false`).

| Action | Endpoint | Body | Permission |
|---|---|---|---|
| Activate / deactivate | `POST users/{id}/set-status/` | `{"is_active": false}` | `chaotica_utils.manage_user`; not yourself |
| Update profile | `POST users/{id}/update-profile/` | any of `first_name`, `last_name`, `job_title`, `city` (id), `country` (2-letter) | self, (acting) manager, or `manage_user` |
| Career level | `POST users/{id}/set-job-level/` | `{"job_level": "JL5", "effective_from": "2026-01-01"}` or `{"clear": true}` | (acting) manager, superuser/staff, or self if unmanaged |
| Loaded cost rate | `POST users/{id}/set-cost/` | `{"cost_per_hour": "43.46", "effective_from": "2026-01-01"}` | `jobtracker.can_view_loaded_costs`, held globally or on every unit the user belongs to |

What each action also does:

- **Activate / deactivate:**
  - Deactivation closes the user's team and unit memberships.
  - It also revokes their OAuth tokens and disconnects their sockets.
- **Career level and loaded cost rate:**
  - These are effective-dated. A change adds a new record from
    `effective_from` (default today) and supersedes the old one.
  - The cost rate is gated on finance permission, not on management rights. As
    a result, nobody can set their own rate.

Worked examples live in `examples/api/`:

- `sync_aad_status.py` reconciles account status with Entra ID.
- `job_titles.py` pushes job titles.

## Developing the API

Code layout under `app/jobtracker/api/v1/`:

| Path | Holds |
|---|---|
| `base.py` | `ApiView` and `BaseReadOnlyAPIViewSet`, which set auth, permissions, throttles, UTC, the error envelope and `self.policy` |
| `serializers/`, `views/` | one module per area |
| `fields.py` | the Ref fields |
| `filters.py` | the FilterSets |

Shared logic:

- **Selectors.** Query logic lives in `jobtracker/selectors/`,
  `chaotica_utils/selectors/` and `notifications/selectors.py`. Template views
  and API views both call these, so an endpoint and its page cannot drift.
- **Policy.** `jobtracker/policy.py` holds `PolicyContext`: `can(action, obj)`,
  `scope(resource, qs)` and `capabilities(obj)`, memoised per request. Use it
  rather than calling guardian directly.
- **Workflow.** `jobtracker/workflow.py` is the single transition table for
  both the status buttons and the API's `workflow` block.

Tests live in `jobtracker/tests/api_v1/`. `helpers.py` provides a user matrix
and `assert_same_ids` for parity checks against the page's queryset. Give new
endpoints a permission matrix test, a parity test and an `assertNumQueries`
budget.

After changing any endpoint, regenerate the schema:

```bash
cd app && python manage.py spectacular --file ../docs/api/openapi-v1.yaml --validate
```

## Related topics

- [Connected Apps (admin guide)](../administration/connected_apps.md)
- [API / UI coexistence](api_coexistence.md)
- [API migration (legacy `/api/` → `/api/v1/`)](../integration/api_migration.md)
- [Access control](../security/access_control.md)
