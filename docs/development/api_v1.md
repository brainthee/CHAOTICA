# REST API (v1)

CHAOTICA exposes a versioned, **read-mostly** REST API under `/api/v1/` for
programmatic access to the main engagement-lifecycle data. It is built on Django
REST Framework and documented by an auto-generated OpenAPI schema.

!!! note "Read-mostly"
    Endpoints support `GET`/`HEAD`/`OPTIONS`. Writes are limited to a few
    narrowly-scoped per-user actions — [account status](#writes-account-status)
    and [profile / career level / loaded cost rate](#writes-user-profile-career-level-loaded-cost-rate).
    Each reproduces the exact permission gate of its UI equivalent. Broader
    create/update support is a deliberate future step.

!!! warning "Not the legacy `/api/` endpoints"
    The older `/api/` endpoints (`/api/jobs/`, `/api/client/`, …) are **DataTables
    feeds for the web UI**, not a clean data API — they return rendered HTML and
    table-row metadata. They remain in place but are frozen and undocumented for
    integration use. See [API migration](../integration/api_migration.md).

## Base information

| | |
|---|---|
| **Base URL** | `https://your-instance/api/v1/` |
| **Format** | JSON |
| **Auth** | Token or session (see below) |
| **Pagination** | Page-number: `{count, next, previous, results}` |

## Authentication

All endpoints require an authenticated user (`IsAuthenticated`).

### Token authentication (programmatic clients)

Get a token in any of three ways:

- **In the UI**: **Profile → API Token → Generate Token**, where you can also
  view, regenerate and revoke it.
- **By credentials**: POST to `/api/v1/auth/token/` (below).
- **On the server**: `cd app && python manage.py drf_create_token <email>`.

A token authenticates as its owner and **inherits exactly that user's
permissions** — every request is scoped to what the owner could see or do in the
web UI, and a token can never do more.

Obtain a token by POSTing credentials, then send it on every request:

```bash
# 1. Obtain a token
curl -X POST https://your-instance/api/v1/auth/token/ \
     -d "username=you@example.com&password=your-password"
# -> {"token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"}

# 2. Use it
curl -H "Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b" \
     https://your-instance/api/v1/jobs/
```

`username` is the user's email address (the account's login identifier).

!!! info "Token lifecycle"
    Tokens are long-lived and do not expire. Treat them like passwords: store in
    environment variables, never commit them, and re-issue if compromised. Expiring
    / rotatable tokens are a candidate future enhancement.

### Session authentication (browsable API)

When logged into the web UI you can browse the API interactively in the same
session — useful during development.

## Pagination

Responses are paginated with a standard page-number scheme:

```json
{
    "count": 150,
    "next": "https://your-instance/api/v1/jobs/?page=2",
    "previous": null,
    "results": [ ... ]
}
```

Control paging with `?page=<n>` and `?page_size=<n>` (default 50, max 200).

## Permissions & data scoping

The API **reproduces the same access rules as the web UI** — it never widens them:

- Jobs, phases and projects are scoped to the organisational units where you hold
  the relevant permission (e.g. `can_view_jobs`), plus any you are on the team of.
- Timeslots are limited to users whose schedule you may view
  (`view_users_schedule`), plus your own.
- The schedule endpoints (`/schedule/`, `/users/{id}/schedule/`) use the same
  `view_users_schedule` visibility, plus your own schedule — identical to the
  scheduler in the UI.
- Leave requests follow the same visibility as the *Manage Leave* screen (your own,
  your reports', and units where you can view all leave).
- Skills, qualifications, clients, services and org units are scoped by their
  respective `view_*` permissions (administrators/global-role holders see all).
- A user's own skills/qualification records are visible to them, their manager, and
  holders of the relevant view permission.

Sensitive fields are deliberately never serialized — notably qualification
`certificate_file` and user PII such as phone numbers.

## Resources

| Resource | Endpoint | Notes |
|---|---|---|
| Users | `/api/v1/users/` | identity, `job_title`, current `job_level`/`job_level_label`, `city`/`city_name`/`country`; no PII |
| Organisational units | `/api/v1/org-units/` | |
| Clients | `/api/v1/clients/` | |
| Jobs | `/api/v1/jobs/` | active jobs; includes `phase_count`, `is_restricted` flag |
| Phases | `/api/v1/phases/` | |
| Projects | `/api/v1/projects/` | |
| Timeslots | `/api/v1/timeslots/` | scheduling assignments (paginated, per-slot) |
| Schedule (global) | `/api/v1/schedule/` | composite window: timeslots + leave + holidays + per-user availability (see below) |
| Schedule (per-user) | `/api/v1/users/{id}/schedule/` | the same composite for one user |
| Timeslot types | `/api/v1/timeslot-types/` | reference data |
| Leave requests | `/api/v1/leave-requests/` | |
| Skills | `/api/v1/skills/` | |
| Skill categories | `/api/v1/skill-categories/` | reference data |
| User skills | `/api/v1/user-skills/` | per-user competency |
| Qualifications | `/api/v1/qualifications/` | |
| Qualification records | `/api/v1/qualification-records/` | per-user; no certificate file |
| Services | `/api/v1/services/` | |

Each resource supports list (`GET /api/v1/<resource>/`) and detail
(`GET /api/v1/<resource>/{id}/`, integer primary key).

## Schedule (composite window)

For building a calendar/timeline view there is a dedicated read-only schedule
feed. It returns everything the scheduler needs for a date window in one call —
work timeslots, leave, public holidays and per-user availability/utilisation —
rather than making you stitch the individual resources together.

- `GET /api/v1/schedule/` — every user you may see (`view_users_schedule`, plus
  yourself). Optionally narrow with `?unit=<id>` or `?user=<id>`.
- `GET /api/v1/users/{id}/schedule/` — a single user (yourself, or anyone whose
  schedule you may view). Ideal for a personal admin/availability tool.

Both accept a date window and are **not paginated** — bound the result with the
window instead:

| Param | Default | Notes |
|---|---|---|
| `start` | today | ISO date (`YYYY-MM-DD`) |
| `end` | `start` + 28 days | ISO date; the span must be **366 days or fewer** |

An invalid date, an inverted range, or an over-cap span returns `400`.

```bash
curl -H "Authorization: Token <your-token>" \
     "https://your-instance/api/v1/users/42/schedule/?start=2026-09-01&end=2026-09-30"
```

```json
{
  "start": "2026-09-01",
  "end": "2026-09-30",
  "users": [
    {"user": 42, "availability": 40.0, "utilisation": 55.0,
     "business_hours": {"startTime": "09:00", "endTime": "17:30", "daysOfWeek": [1,2,3,4,5]}}
  ],
  "timeslots": [ {"id": 1001, "user": 42, "start": "…", "end": "…", "slot_type": 3, "phase": 87, ...} ],
  "leave":     [ {"id": 12, "user": 42, "start_date": "…", "end_date": "…", "type_of_leave": 1, ...} ],
  "holidays":  [ {"id": 3, "date": "2026-09-07", "country": "US", "reason": "Labor Day"} ]
}
```

`timeslots` and `leave` use the same fields as the `/timeslots/` and
`/leave-requests/` resources. `holidays` apply per country — match one to a user
via the user's country. The schedule feed is built from the **same shared core**
as the in-app vis-timeline scheduler, so the two never drift.

## Writes: account status

The one write action in v1 activates or deactivates a user account — the API
twin of the *Manage → Activate/Deactivate* control in the UI:

```bash
curl -X POST https://your-instance/api/v1/users/42/set-status/ \
     -H "Authorization: Token <your-token>" \
     -H "Content-Type: application/json" \
     -d '{"is_active": false}'
```

```json
{"changed": true, "user": {"id": 42, "email": "jane@example.com", "is_active": false, ...}}
```

- Requires the `chaotica_utils.manage_user` permission (403 otherwise).
- Deactivation also closes the user's open team and org-unit memberships, exactly
  as the management screen does.
- **Idempotent**: `changed` is `false` if the account was already in the
  requested state.
- You cannot deactivate your own account.

A worked example that reconciles status against Azure AD / Entra ID lives in
`examples/api/sync_aad_status.py`.

## Writes: user profile, career level & loaded cost rate

Three further per-user write actions let an HR/directory sync push people data
into CHAOTICA. Each reproduces the exact permission gate of its UI equivalent —
they never widen access — so an integration token can only do what its owner can
do in the app.

| Action | Endpoint | Permission gate |
|---|---|---|
| Update profile | `POST /api/v1/users/{id}/update-profile/` | Self, the user's (acting) manager, or `chaotica_utils.manage_user` |
| Set career level | `POST /api/v1/users/{id}/set-job-level/` | The user's (acting) manager, a superuser/staff, or self when they have no manager |
| Set loaded cost rate | `POST /api/v1/users/{id}/set-cost/` | `jobtracker.can_view_loaded_costs` — held globally, or on **every** org-unit the user belongs to |

**Update profile** — partial update of org-chart facts only (`first_name`,
`last_name`, `job_title`, `city` by id, `country` as a 2-letter code). Account
status, cost rates, permissions and email are *not* writable here.

```bash
curl -X POST https://your-instance/api/v1/users/42/update-profile/ \
     -H "Authorization: Token <your-token>" -H "Content-Type: application/json" \
     -d '{"job_title": "Senior Consultant", "city": 1826, "country": "GB"}'
```

**Set career level** — sets the current level by its short label, or clears it.
Effective-dated and idempotent: a new assignment is created only when the level
actually changes (dated `effective_from`, default today), and the previous
assignment is closed off (`is_current=false`). Re-posting the same level is a
no-op (`changed: false`).

```bash
curl ... -d '{"job_level": "JL5", "effective_from": "2026-01-01"}'   # set/promote
curl ... -d '{"clear": true}'                                        # clear
```
```json
{"changed": true, "user": {"id": 42, "job_level": "JL5", ...}}
```

**Set loaded cost rate (LCR)** — a date-effective rate. Effective-dated and
idempotent: if the rate already in force on `effective_from` (default today)
equals the posted value, nothing is written (`changed: false`); otherwise a new
row is added at that date and the previous rate is superseded from then on
(the old rate stays valid up to the new date — that's the "close-off"). So a
weekly import only ever adds a row when the number actually moves. This is the
finance boundary: gated on `can_view_loaded_costs`, **not** on
manager/`manage_user`, so profile-editing rights never leak into cost-rate
access, and a person can never set their own LCR.

```bash
curl -X POST https://your-instance/api/v1/users/42/set-cost/ \
     -H "Authorization: Token <your-token>" -H "Content-Type: application/json" \
     -d '{"cost_per_hour": "43.46", "effective_from": "2026-01-01"}'
```
```json
{"changed": true, "created": true, "user_id": 42, "effective_from": "2026-01-01", "cost_per_hour": "43.46"}
```

Because both actions diff against current state, the intended workflow is simply
to **replay the full import each run**: unchanged people are no-ops, and only
genuine changes create a new dated record. You can still `GET /api/v1/users/{id}/`
to inspect `city`/`country`/`job_level` first if you want to log diffs yourself.

## Interactive documentation & schema

The full, always-current field list for every endpoint is published as OpenAPI:

- **Swagger UI**: `/api/v1/schema/swagger-ui/`
- **ReDoc**: `/api/v1/schema/redoc/`
- **Raw schema**: `/api/v1/schema/`

Generate the schema file from the CLI with:

```bash
cd app && python manage.py spectacular --file schema.yml
```

## Example

```bash
curl -H "Authorization: Token <your-token>" \
     "https://your-instance/api/v1/phases/?page_size=10"
```

```json
{
    "count": 42,
    "next": "https://your-instance/api/v1/phases/?page=2&page_size=10",
    "previous": null,
    "results": [
        {
            "id": 450,
            "phase_id": "2501-1",
            "title": "Web Application Assessment",
            "status": 5,
            "status_display": "In Progress",
            "job": 2501,
            "service": 12,
            "service_name": "Web Application Testing",
            "start_date": "2026-04-01",
            "delivery_date": "2026-04-15",
            "delivery_hours": "40.00"
        }
    ]
}
```

## Related topics

- [API migration (legacy `/api/` → `/api/v1/`)](../integration/api_migration.md)
- [Access control](../security/access_control.md)
