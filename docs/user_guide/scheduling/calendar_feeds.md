# Calendar Feeds

You can subscribe to your CHAOTICA schedule from Outlook, Google Calendar, Apple Calendar, or any app that reads **iCal (`.ics`)** feeds, so your bookings show up alongside the rest of your calendar. Feeds are **read‑only** and update on their own schedule (governed by your calendar app's refresh interval).

There are two feeds:

- **Personal schedule feed** — your own bookings with detail (e.g. *"Phase: Delivery (Confirmed, Onsite)"*). Covers roughly the last 3 months and the next year.
- **Family feed** — a privacy‑friendly version for sharing with family: it shows only whether you're **Onsite/Remote** and **Confirmed/Tentative**, with **no** job, client or phase detail.

## Subscribing

1. Go to your **profile**.
2. **Enable** the feed you want. Each feed has a unique, unguessable URL tied to a private key.
3. Copy the feed URL and **add it as a subscribed/internet calendar** in your calendar app.

If you ever need to revoke access (e.g. you shared the link too widely), use **Reset** — this generates a new key and immediately invalidates the old URL. **Disable** turns the feed off entirely (the URL then returns nothing).

!!! note
    Each feed access is logged against your account (time, IP, user‑agent). If a feed is disabled or the key is wrong, the URL returns *not found*.

## Availability (administrators)

Feeds are gated by site‑wide settings, so an administrator can turn them on or off for everyone:

| Setting | Controls |
|---|---|
| `CALENDAR_FEED_ENABLED` | The personal schedule feed |
| `CALENDAR_FAMILY_FEED_ENABLED` | The family feed |

If a feed type is disabled site‑wide, its URLs stop returning data regardless of individual settings. See [Application Settings](../../administration/chaotica_settings.md).

## Related Topics

- [Scheduling Overview](overview.md)
- [Application Settings](../../administration/chaotica_settings.md) — the feed toggles and schedule colours
