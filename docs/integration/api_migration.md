# API Migration: legacy `/api/` → `/api/v1/`

CHAOTICA has two API surfaces. This page explains the difference and how to move
consumers that currently depend on the legacy URLs.

## Why there are two

| | Legacy `/api/` | New `/api/v1/` |
|---|---|---|
| Purpose | DataTables feeds for the **web UI** | Clean data API for **integrations** |
| Payload | Rendered HTML links, `DT_RowId`/`DT_RowAttr` row metadata | Plain JSON: IDs + `*_name`/`*_display` labels |
| Pagination | DataTables draw/paging params | Standard `{count, next, previous, results}` |
| Versioned | No | Yes (`/api/v1/`) |
| Stability | Frozen; may change with UI needs | Stable contract; documented via OpenAPI |

The legacy endpoints are **not being removed** — the UI still relies on them — but
they are unsuitable for programmatic use and are not documented for integration.
New and migrating consumers should use `/api/v1/`.

## URL mapping

| Legacy endpoint | New endpoint | Notes |
|---|---|---|
| `GET /api/users/` | `GET /api/v1/users/` | v1 returns identity only (no PII) |
| `GET /api/jobs/` | `GET /api/v1/jobs/` | v1 has no HTML/`DT_*`; adds `phase_count`, `is_restricted` |
| `GET /api/client/` | `GET /api/v1/clients/` | note plural `clients` |
| `GET /api/orgunit/` | `GET /api/v1/org-units/` | |
| `GET /api/notes/` | *(not exposed in v1)* | superuser-only in legacy |

## New in v1 (no legacy equivalent)

`phases`, `projects`, `timeslots`, `timeslot-types`, `leave-requests`, `skills`,
`skill-categories`, `user-skills`, `qualifications`, `qualification-records`,
`services`.

Plus the supporting endpoints:

- `POST /api/v1/auth/token/` — obtain an auth token
- `GET /api/v1/schema/`, `/schema/swagger-ui/`, `/schema/redoc/` — OpenAPI docs

## What changes for a consumer

1. **Base path**: prefix requests with `/api/v1/` and update the client/singular
   paths (`client` → `clients`, `orgunit` → `org-units`).
2. **Auth**: obtain a token from `/api/v1/auth/token/` and send
   `Authorization: Token <key>` (session auth also works in-browser). If you relied
   on the legacy token declaration, note it was previously non-functional — the
   token backend is now installed and migrated.
3. **Response shape**: read data from `results` and paginate via `next`/`previous`.
   Stop parsing HTML out of fields — v1 gives you IDs and plain labels.
4. **Fields**: consult the OpenAPI schema (`/api/v1/schema/swagger-ui/`) for the
   exact field list per resource; it is the source of truth.

## Access scoping is unchanged

`/api/v1/` enforces the **same permissions** as the web UI (see
[REST API (v1)](../development/api_v1.md#permissions-data-scoping)). Migrating to v1
does not grant any consumer broader visibility than they had in the application.
