# Billing Codes

Billing codes (also called charge codes) identify how work is billed. Most codes
belong to a **client**; some are **internal** (client-less) and represent
work-breakdown-structure (WBS) / non-chargeable activity.

Billing codes are a first-class part of the delivery lifecycle: they can be
assigned to **jobs, phases and projects**, each assignment optionally carrying a
**date range** for *when* that code applies.

## Administering codes

Codes are managed per client from the client detail page under the **Billing
Codes** tab (create / edit / delete). Client-less (internal) codes are managed
from **Operations → Internal Codes (WBS)** and **Operations → Billing Codes**.

| Field | Description |
|---|---|
| `code` | The billing code string (unique) |
| `client` | Owning client, or blank for internal / WBS codes |
| `is_chargeable` | Work booked to this code is chargeable to the client |
| `is_recoverable` | Costs are recoverable |
| `is_internal` | Internal (non-client) code |
| `is_closed` | Closed to new use |
| `region` | Country/region the code applies to |

### Visibility (scoping)

You only see codes you can reach: client-less/internal codes, plus codes whose
client has a job in an organisational unit you can view. This applies to the
Billing Codes list, the assignment pickers and the autocomplete.

## Assigning codes to jobs, phases and projects

Use **Assign Billing Codes** from the job, phase or project action menu. Each
assignment is a row with a code and an optional start/end date:

- **No dates** — the code applies for the whole target span.
- **A date range** — the code applies only within it. Several dated codes can
  coexist (e.g. a code replaced mid-engagement, the old one kept for historical
  dates). Overlapping dates are allowed and surfaced, not blocked.

A code can only be assigned **once without a date range** per target.

### Phase override / inheritance

A phase **inherits** its job's codes by default. If you assign codes directly to
a phase, those **override** the job's codes for that phase (they replace, not
add). The phase header shows whether codes are *Inherited from job* or
*Overridden*.

## Code Allocations (per user)

From a user's profile, **Code Allocations** shows which code(s) that person
should book against, day by day, with the business hours scheduled each day, and
a per-code summary (days, hours, chargeable vs internal). This is a view over
the schedule — **not** a timesheet. A day can map to several codes (all
applicable codes are shown). Visible to the user and to anyone who can manage
them (their manager / unit lead).

## Analytics & operations

- **Operations → Billing Analytics** — hours per code across your reachable
  teams over a date window, rolled up by client and chargeable vs internal.
- **Operations → Internal Codes (WBS)** — the client-less subset, with its own
  analytics view.
- Billing codes are also available as a data area in the custom report builder
  (joined to Client and Job).

## Data model note

Assignments are stored as `BillingCodeAssignment` rows (one per code + target +
date range). The legacy `Job.charge_codes` / `Project.charge_codes`
many-to-many relations were migrated into undated assignments and are retained
as read-only compatibility accessors.
