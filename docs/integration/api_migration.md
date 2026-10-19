# API Migration: legacy `/api/` → `/api/v1/`

`/api/v1/` is CHAOTICA's API for integrations, standalone UIs and the main web
UI alike. See [REST API (v1)](../development/api_v1.md).

## What is left of the legacy `/api/`

The legacy endpoints were DataTables feeds for the web UI. They returned
rendered HTML and `DT_*` row metadata, and were never a stable contract.

The UI has since moved to v1:

- the job list (`/api/jobs/`) and client list (`/api/client/`) feeds have been
  **removed**;
- so have the old search, notification and scheduler read feeds.

What remains is frozen and undocumented for integration use:

| Legacy endpoint | Use instead |
|---|---|
| `GET /api/users/` | `GET /api/v1/users/` (identity only; contact details need `view_user`) |
| `GET /api/orgunit/` | `GET /api/v1/org-units/` |
| `GET /api/notes/` | `GET /api/v1/jobs/{id}/notes/`, `/api/v1/phases/{id}/notes/` |
| `GET /api/auditevents/` | `GET /api/v1/jobs/{id}/activity/`, `/api/v1/phases/{id}/activity/` |
| ~~`GET /api/jobs/`~~ (removed) | `GET /api/v1/jobs/` |
| ~~`GET /api/client/`~~ (removed) | `GET /api/v1/clients/` |

## Moving a consumer

1. **Paths.** Prefix with `/api/v1/` and use the plural names: `client` →
   `clients`, `orgunit` → `org-units`.
2. **Auth.** Choose by client type:
   - Scripts use an API token (`Authorization: Token <key>`).
   - Browser apps on another origin use OAuth2 + PKCE through a
     [Connected App](../administration/connected_apps.md).
   - Session cookies work only on the CHAOTICA origin itself.
3. **Shape.**
   - Read `results` and follow `next` / `previous` to page.
   - Relations are Ref objects (`id`, `display`, `url`, `web_url`), not HTML
     fragments.
   - `id` is always the primary key; jobs carry their business number as
     `job_id`.
4. **Times** are UTC.
5. **Fields.** The OpenAPI schema (`/api/v1/schema/swagger-ui/`) is the source
   of truth.

## Access is never wider

`/api/v1/` applies the same permissions as the web UI, and in a few places
stricter ones (see [API / UI coexistence](../development/api_coexistence.md)).
Moving to v1 never gives a consumer more visibility than they have in the
application.
