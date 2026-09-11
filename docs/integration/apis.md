# External APIs

CHAOTICA exposes a versioned, read-mostly REST API under `/api/v1/` for building
your own tools and integrations against your engagement, people and schedule
data. It reproduces the same permission rules as the web UI — a token can only
see and do what its owner can.

Full reference (authentication, pagination, every resource and field, and the
interactive Swagger/ReDoc explorer) lives in the developer docs:
[REST API (v1)](../development/api_v1.md).

## Getting a token

Generate a personal API token from your **profile** (the *API Tokens* card), then
send it on every request:

```
Authorization: Token <your-token>
```

A token acts entirely as you, and inherits your object-level permissions.

## Schedule API

The schedule is available programmatically, so a personal admin/availability tool
can read it directly instead of scraping the calendar. One call returns a whole
date window — work timeslots, leave, public holidays and per-user
availability/utilisation:

```bash
# Your own schedule for September
curl -H "Authorization: Token <your-token>" \
     "https://your-instance/api/v1/users/42/schedule/?start=2026-09-01&end=2026-09-30"

# Everyone whose schedule you may see
curl -H "Authorization: Token <your-token>" \
     "https://your-instance/api/v1/schedule/?start=2026-09-01&end=2026-09-30"
```

Visibility matches the in-app scheduler: your own schedule plus anyone in an org
unit where you hold *view users' schedule*. See
[REST API (v1) → Schedule](../development/api_v1.md#schedule-composite-window)
for the response shape and query parameters.

If you only need a calendar subscription (Outlook/Google/Apple) rather than raw
data, use the read-only iCal [Calendar Feeds](../user_guide/scheduling/calendar_feeds.md)
instead.

## Related topics

- [REST API (v1)](../development/api_v1.md) — full reference
- [API Migration (v1)](api_migration.md)
- [Calendar Feeds](../user_guide/scheduling/calendar_feeds.md)
