# Billing Codes

Billing codes (also called charge codes) identify how work is billed. Most codes
belong to a **client**; some are **internal** (client-less) and represent
work-breakdown-structure (WBS) / non-chargeable activity.

Billing codes are a first-class part of the delivery lifecycle: they can be
assigned to **jobs, phases and projects**, each assignment optionally carrying a
**date range** for *when* that code applies.

## Administering codes

Codes are managed per client from the client detail page under the **Billing
Codes** tab (create / edit / delete), and all codes — including client-less
(internal) ones — from **Operations → Billing Codes**. Whether a code is
internal is a flag on the code itself (`is_internal`); there's no separate
internal-codes page.

### Billing Codes list

**Operations → Billing Codes** lists every code you can reach with its client,
type badges (Internal / Chargeable / Not chargeable / Recoverable), region,
how many jobs, phases and projects it's assigned to, and whether it's open.
Filter by **type** or **client** above the table; closed codes are hidden until
you switch on **Show closed**. **Analytics** opens Billing Analytics and
**New code** (needs `add_billingcode`) creates one.

### Billing code page

Each code's page has a header with the client, region, type badges and
open/closed status, plus tiles for active assignments (today) and job, phase
and project assignments. **Edit** and **Delete** need
`change_billingcode` / `delete_billingcode`. Tabs:

- **Analytics** — scheduled hours, person-days and people booked against the
  code over a range (30d / 3m / 6m / 12m presets or a custom range, default
  last 12 months; future dates allowed), hours per month, and breakdowns per
  person and per phase/project. It uses exactly the same attribution rules as
  Billing Analytics (assignment dates, phase overrides, duplicate-code policy)
  and only counts people you can see.
- **Assignments** — every job / phase / project the code is assigned to, with
  its date range, who added it, and whether it applies today.
- **Activity** — changes to the code and its assignments.

| Field | Description |
|---|---|
| `code` | The billing code string (unique) |
| `client` | Owning client, or blank for internal (client-less) codes |
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

The code picker is a **searchable, type-ahead** field: start typing to search
the codes available for the target's client (plus internal/WBS codes) — they are
loaded on demand rather than all rendered up front.

### Creating a new code without leaving the modal

If the code you need doesn't exist yet, expand **"Can't find the code? Create a
new one"** at the bottom of the assign modal. Fill in the code (client defaults
to the target's client, or clear it for an internal/WBS code), set the
chargeable / recoverable / internal flags and region, and click **Create code**.
The new code is created and selected into the current row immediately, so you can
carry on assigning without a page reload. This shortcut is only shown to users
with permission to add billing codes.

### Phase override / inheritance

A phase **inherits** its job's codes by default. If you assign codes directly to
a phase, those **override** the job's codes for that phase (they replace, not
add). The phase header shows whether codes are *Inherited from job* or
*Overridden*.

## Missing billing codes

A phase **needs a code** when neither the phase nor its job has any billing-code
assignment — time booked to it can't be coded. CHAOTICA flags this (it never
blocks):

- **Moving a phase to Schedule Confirmed** — the confirm dialog shows a note,
  and the bulk "move phases" dialog marks each such phase with a **No billing
  code** badge plus a summary line.
- **Banners** on the phase page and on the job page (listing the affected
  phases), for live phases only: not cancelled / postponed / deleted / archived,
  and the job isn't lost, deleted or archived.
- **Dashboard alarm** — *Phases with No Billing Code* lists phases from Schedule
  Tentative through Completed on active jobs in your scheduling scope (or that
  you're on). It also counts towards the dashboard entropy score.

Assign a code to the job (all its phases inherit it) or to the phase to clear
the warning.

## Code Allocations (per user)

From a user's profile, **Code Allocations** shows which code(s) that person
should book against, day by day, with the business hours scheduled each day, and
a per-code summary (days, hours, chargeable vs internal). This is a view over
the schedule — **not** a timesheet. A day can map to several codes (all
applicable codes are shown). Visible to the user and to anyone who can manage
them (their manager / unit lead).

## Team and unit billing tabs

The **Team** page (team owners and admins) and the **Organisational Unit** page
(`can_view_all_leave_requests` on the unit, i.e. Service Delivery and Manager by
default) each have a **Billing** tab. It covers the active
members for one timesheet period (◀ / ▶ step periods; *Jump to current period*
returns), and shows:

- totals tiles — capacity, coded, uncoded, unavailable, internal and support
  hours;
- a **per-member** table with the same columns. A name links to that person's
  own Billing Codes page when you can manage them;
- a **per-code** roll-up — code, client, chargeable, hours and person-days.

The figures are **hours only** (no money) and come from the same calculation as
each member's own Billing Codes page — multi-code days, leave wins and support
cash-outs included — so the team totals add up to the individual pages.

## Analytics & operations

- **Operations → Billing Analytics** — hours per code across your reachable
  teams over a date range (presets or custom; default this month to four weeks
  ahead), the 15 busiest codes as a chart, and roll-ups by client and per code
  (chargeable vs internal).
- Billing codes are also available as a data area in the custom report builder
  (joined to Client and Job).

## Data model note

Assignments are stored as `BillingCodeAssignment` rows (one per code + target +
date range). The legacy `Job.charge_codes` / `Project.charge_codes`
many-to-many relations were migrated into undated assignments and are retained
as read-only compatibility accessors.
