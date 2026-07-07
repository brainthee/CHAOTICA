# CHAOTICA `/api/v1/` example scripts

Small, runnable Python examples that authenticate against a CHAOTICA instance and
pull the main data through the versioned read-only REST API at `/api/v1/`. They
are configuration-driven via environment variables, so they work against any
instance without editing code.

These are **consumer/demo scripts**. They live outside the Django app, are not
imported by anything, and only ever issue `GET` requests.

## Prerequisites

- Python 3.7+
- Install the one dependency (ideally in a virtualenv):

  ```bash
  pip install -r requirements.txt
  ```

## Configure

Every script reads its configuration from environment variables. Set them in your
shell, or copy the template and edit it:

```bash
cp .env.example .env
# then edit .env
```

`.env` is loaded from the current directory first, then from this scripts
directory. Real environment variables always win over the file.

| Variable | Used by | Notes |
|---|---|---|
| `CHAOTICA_API_URL` | all | Base API URL, e.g. `http://localhost:8000/api/v1`. A bare host has `/api/v1` appended; a trailing slash is fine. |
| `CHAOTICA_API_TOKEN` | all except `get_token.py` | Sent as `Authorization: Token <token>`. |
| `CHAOTICA_API_USER` | `get_token.py` | Login email. |
| `CHAOTICA_API_PASSWORD` | `get_token.py` | Password (prompts if unset). |
| `CHAOTICA_VERIFY_SSL` | all | Default `true`; set `false` for self-signed dev certs. |
| `CHAOTICA_PAGE_SIZE` | all | Optional; passed as `?page_size=`. Set to `1` to watch pagination work. |

## Get a token

Two ways:

1. **From this directory**, with `CHAOTICA_API_USER` / `CHAOTICA_API_PASSWORD` set
   (or passed as flags):

   ```bash
   python get_token.py
   # prints the token and a ready-to-copy `export CHAOTICA_API_TOKEN=...` line
   ```

2. **On the server** (ships with `rest_framework.authtoken`):

   ```bash
   cd app && python manage.py drf_create_token <your-email>
   ```

Put the resulting token in `CHAOTICA_API_TOKEN`.

## The scripts

Run each from this directory once your environment is configured.

| Script | What it does | Example |
|---|---|---|
| `get_token.py` | Exchange username/password for an API token. | `python get_token.py` |
| `list_jobs.py` | List all visible jobs (id, title, client, status, phase count, delivery date), following pagination. | `python list_jobs.py` |
| `upcoming_deliveries.py` | Phases due for delivery or Tech QA in the next N days. | `python upcoming_deliveries.py --days 60` |
| `schedule.py` | Timeslots in a date window, grouped by user (optional single-user filter). | `python schedule.py --days 14 --user 42` |
| `skills_matrix.py` | Who holds each skill and at what rating (joins skills + user-skills). | `python skills_matrix.py` |
| `qual_expiry.py` | Qualification records lapsing within N days. | `python qual_expiry.py --days 90` |

`chaotica_client.py` is the shared helper module (env config, `.env` loading, an
authenticated session, pagination via `iterate()`, and plain-text table output).
It is imported by the others, not run directly.

## Results are permission-scoped

The API reproduces the same access rules as the web UI and never widens them, so
**results are scoped to your token's user**. An unprivileged token legitimately
sees little (or nothing) — empty output is not necessarily a bug. Scripts that
show `user` fields resolve names best-effort from `/users/` and fall back to
`user #<id>` for anyone your token can't see.

## Notes

- All scripts are read-only (`GET` only).
- `schedule.py` expresses "my schedule" as a single-user filter because the API
  has no `/api/v1/users/me/` endpoint yet.
- Full, always-current field lists are in the OpenAPI docs at
  `/api/v1/schema/swagger-ui/` and the project docs:
  [`docs/development/api_v1.md`](../../docs/development/api_v1.md).
