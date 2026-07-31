# REST API (v1)

CHAOTICA exposes a versioned, **read-mostly** REST API under `/api/v1/` for
programmatic access to the main engagement-lifecycle data. It is built on Django
REST Framework and documented by an auto-generated OpenAPI schema.

!!! note "Read-mostly"
    Endpoints support `GET`/`HEAD`/`OPTIONS`. The only write surface today is the
    [account-status action](#writes-account-status) on users; broader
    create/update support is a deliberate future step, and the endpoints are
    designed so it can be added without breaking existing consumers.

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
| Users | `/api/v1/users/` | identity, `job_title`, current `job_level`/`job_level_label`; no PII |
| Organisational units | `/api/v1/org-units/` | |
| Clients | `/api/v1/clients/` | |
| Jobs | `/api/v1/jobs/` | active jobs; includes `phase_count`, `is_restricted` flag |
| Phases | `/api/v1/phases/` | |
| Projects | `/api/v1/projects/` | |
| Timeslots | `/api/v1/timeslots/` | scheduling assignments |
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
