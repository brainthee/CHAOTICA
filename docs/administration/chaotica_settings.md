# Application Settings

CHAOTICA's application settings are managed through the **Settings** page, accessible to users with the `manage_site_settings` permission. Changes take effect immediately — no restart is required.

Settings are stored in the database using [django-constance](https://django-constance.readthedocs.io/) and can also be modified via the Django admin interface under **Constance > Config**.

---

## Work Settings

These control core working-time calculations used across scheduling, scoping, and leave.

| Setting | Default | Description |
|---------|---------|-------------|
| **DEFAULT_HOURS_IN_DAY** | `7.5` | Standard working hours per day. Used to convert between days and hours when displaying scoped/scheduled time. Clients can override this at the client level — this value is the fallback. |
| **DEFAULT_WORKING_DAYS** | `[1, 2, 3, 4, 5]` | JSON array of working days (Sunday = 0, Monday = 1, ..., Saturday = 6). Defaults to Monday–Friday. Used for leave calculations and team utilisation stats when an organisation hasn't defined custom business hours. |

---

## Leave

| Setting | Default | Description |
|---------|---------|-------------|
| **LEAVE_DAYS_NOTICE** | `14` | Minimum number of days' notice required for annual leave requests. Requests submitted with less notice are flagged as `requested_late`. |
| **LEAVE_HISTORY_MONTHS** | `3` | How many months of past leave to show on the manage leave page. |
| **LEAVE_ENFORCE_LIMIT** | `False` | When enabled, the leave request form will reject requests that would exceed the user's remaining leave balance. When disabled, over-balance requests are allowed (but may still be flagged). |

---

## Phase Deadlines

These settings control the automatic calculation of key phase dates based on the last scheduled delivery/reporting timeslot.

| Setting | Default | Description |
|---------|---------|-------------|
| **DAYS_TO_TQA** | `0` | Business days after the last delivery slot that a phase is due for Technical QA. |
| **DAYS_TO_PQA** | `5` | Business days after the last delivery slot that a phase is due for Pre-sales QA. |
| **DAYS_TO_DELIVERY** | `7` | Business days after the last delivery slot that a phase is due for final delivery. |

!!! note
    These dates are recalculated automatically when timeslots are added or removed. They appear on the phase detail page under the Dates tab.

---

## Late Notification Intervals

Controls the throttling of repeat notifications when a phase is overdue for a workflow step. These prevent notification spam while keeping stakeholders informed.

| Setting | Default | Description |
|---------|---------|-------------|
| **PRECHECK_LATE_HOURS** | `24` | Hours between repeat "prechecks overdue" notifications. |
| **TQA_LATE_HOURS** | `24` | Hours between repeat "late to TQA" notifications. |
| **PQA_LATE_HOURS** | `24` | Hours between repeat "late to PQA" notifications. |
| **DELIVERY_LATE_HOURS** | `24` | Hours between repeat "late to delivery" notifications. |

!!! example
    With the default of 24 hours, if a phase is overdue for TQA, the first notification fires immediately. The next will not fire until 24 hours later, even if the background task runs more frequently.

---

## Job/Phase IDs

| Setting | Default | Description |
|---------|---------|-------------|
| **JOB_ID_START** | `2500` | Starting number for auto-generated job IDs. Only applies when the first job is created — subsequent jobs increment from the highest existing ID. |
| **PROJECT_ID_START** | `9000` | Starting number for auto-generated project IDs. Same behaviour as JOB_ID_START. |

---

## Schedule Thresholds

Controls the colour coding of the scheduled-vs-scoped progress indicators shown on the job page phase table and the schedule page phase status panel.

| Setting | Default | Colour | Description |
|---------|---------|--------|-------------|
| **SCHEDULE_THRESHOLD_SUCCESS** | `90` | Green | Minimum percentage of scoped time that must be scheduled to show as "fully scheduled". |
| **SCHEDULE_THRESHOLD_INFO** | `50` | Blue | Minimum percentage to show as "partially scheduled". |
| *Over 100%* | — | Red | Hard-coded. Shown when scheduled time exceeds scoped time. |
| *Above 0% but below info threshold* | — | Yellow | Hard-coded. Indicates minimal scheduling. |
| *0%* | — | Grey | Hard-coded. Nothing scheduled. |

!!! note
    The percentage is calculated as `(total scheduled hours / total scoped hours) × 100`. Hovering over the indicator shows a tooltip with the full breakdown in days and hours.

---

## Calendar Feeds

Site-wide toggles for the iCal schedule feeds users can subscribe to. See [Calendar Feeds](../user_guide/scheduling/calendar_feeds.md).

| Setting | Default | Description |
|---------|---------|-------------|
| **CALENDAR_FEED_ENABLED** | `True` | Enables the personal schedule (iCal) feed users can subscribe to from their profile. When off, feed URLs return nothing. |
| **CALENDAR_FAMILY_FEED_ENABLED** | `True` | Enables the family-friendly feed showing only onsite/remote + confirmed/tentative status (no job detail). |

---

## Reminders

| Setting | Default | Description |
|---------|---------|-------------|
| **SKILLS_REVIEW_DAYS** | `31` | Days since last skills update before the user sees a prompt to review their skills. Shown as an info banner on page load. |
| **PROFILE_REVIEW_DAYS** | `182` | Days since last profile update before the user sees a prompt to review their profile. |

---

## Authentication

| Setting | Default | Description |
|---------|---------|-------------|
| **ADFS_ENABLED** | `False` | Enables Azure AD / ADFS single sign-on. When enabled, a "Sign in with Microsoft" button appears on the login page. Requires a valid ADFS configuration in Django settings. |
| **ADFS_AUTO_LOGIN** | `False` | When enabled (and ADFS_ENABLED is also true), unauthenticated users are automatically redirected to ADFS login instead of seeing the login form. |
| **LOCAL_LOGIN_ENABLED** | `True` | Allows username/password authentication. When disabled, the email/password form is hidden and POST requests to the login endpoint are blocked. |
| **EMAIL_ENABLED** | `False` | Master toggle for all outbound email. When disabled, the notification system skips email dispatch entirely. Notifications are still created in-app. |

---

## Registration & Invites

| Setting | Default | Description |
|---------|---------|-------------|
| **REGISTRATION_ENABLED** | `True` | Allows new users to self-register. When disabled, the "Create an account" link is hidden from the login page. |
| **INVITE_ENABLED** | `True` | Allows existing users to send invitations. When disabled, invitation requests return a 403 error. |
| **USER_INVITE_EXPIRY** | `7` | Days until an invitation link expires. After this period, the invite token becomes invalid. |
| **ALLOWED_SIGNUP_EMAIL_DOMAINS** | `""` | Comma-separated list of email domains permitted to be added or self-register (e.g. `accenture.com, example.org`). Blank allows any domain. Enforced on self-registration, invites, and [pre-loading/CSV import](../user_guide/organisational_units/preloading_members.md). |

---

## Site Notice

| Setting | Default | Description |
|---------|---------|-------------|
| **MAINTENANCE_MODE** | `False` | Redirects all non-superusers to a maintenance page. Superusers can still access the full site. Can also be toggled via the management command `python manage.py maintenance_mode on|off`. |
| **SITE_NOTICE_ENABLED** | `False` | Shows a sitewide alert banner at the top of every page. |
| **SITE_NOTICE_MSG** | *(empty)* | The message text displayed in the banner. |
| **SITE_NOTICE_COLOUR** | `primary` | Bootstrap alert colour class. Options: `primary`, `secondary`, `info`, `success`, `danger`, `warning`. |

---

## Theme

Seasonal and fun settings. None of these affect functionality.

| Setting | Default | Description |
|---------|---------|-------------|
| **SNOW_ENABLED** | `False` | Adds an animated snow effect with a toggle in the top navigation bar. |
| **CHRISTMAS_LIGHTS_ENABLED** | `False` | Displays decorative Christmas lights across the top of the page. |
| **CHRISTMAS_TREE_ENABLED** | `False` | Replaces the standard page loading spinner with an animated Christmas tree. |
| **KONAMI_ENABLED** | `True` | Enables the Konami code easter egg (↑ ↑ ↓ ↓ ← → ← → B A). |
| **EASTEREGG_GAMES_ENABLED** | `False` | Enables the hidden stress-relief games (DOM Destroyer, Schedule Blaster, Rage Quit) reachable from the Konami menu. |
| **FAKE_HONEYPOT_ENABLED** | `True` | Serves a fake "web shell" at commonly-scanned URLs (e.g. `/shell.php`, `/c99.php`). It looks like a leftover compromised shell but is completely inert — it never runs anything, returns canned output for common commands, and rickrolls on the second command. Purely for fun (and to gently troll scanners). |
| **ENTROPY_METER_ENABLED** | `False` | Shows a deliberately subtle "entropy meter" glyph in the footer. It reflects your own overdue/at-risk work as an operational "chaos level" (scoped exactly like your dashboard alarms), pulses when high, and opens a full breakdown — factors plus a recent late-delivery trend — when clicked. |

---

## Schedule Colours

Hex colour values used in the calendar/schedule views for different timeslot types. All accept standard hex colour codes (e.g. `#FF5722`).

| Setting | Default | Used For |
|---------|---------|----------|
| **SCHEDULE_COLOR_AVAILABLE** | `#8BC34A` | Available/free time |
| **SCHEDULE_COLOR_UNAVAILABLE** | `#F44336` | Unavailable/blocked time |
| **SCHEDULE_COLOR_INTERNAL** | `#FFC107` | Internal/overhead timeslots |
| **SCHEDULE_COLOR_PROJECT** | `#9C27B0` | Project-level timeslots |
| **SCHEDULE_COLOR_PHASE** | `#A3E1FF` | Unconfirmed phase timeslots |
| **SCHEDULE_COLOR_PHASE_CONFIRMED** | `#239DFF` | Confirmed phase timeslots |
| **SCHEDULE_COLOR_PHASE_AWAY** | `#FFBCA9` | Unconfirmed phase (working away) |
| **SCHEDULE_COLOR_PHASE_CONFIRMED_AWAY** | `#FF5722` | Confirmed phase (working away) |
| **SCHEDULE_COLOR_COMMENT** | `#cbd0dd` | Comment/note entries |

---

## Notification Recipients

Additional email addresses (comma-separated) to receive workflow notifications for each pool. These are sent alongside the normal role-based notifications.

| Setting | Default | Description |
|---------|---------|-------------|
| **NOTIFICATION_POOL_SCOPING_EMAIL_RCPTS** | *(empty)* | Extra recipients when a job enters the scoping pool. |
| **NOTIFICATION_POOL_SCHEDULING_EMAIL_RCPTS** | *(empty)* | Extra recipients when a job/phase enters the scheduling pool. |
| **NOTIFICATION_POOL_TQA_EMAIL_RCPTS** | *(empty)* | Extra recipients for TQA pool notifications. |
| **NOTIFICATION_POOL_PQA_EMAIL_RCPTS** | *(empty)* | Extra recipients for PQA pool notifications. |

!!! note
    These are useful for sending notifications to shared mailboxes or distribution lists that aren't tied to individual user accounts.

---

## Resource Manager Integration

Settings for synchronising data with [Smartsheet Resource Management](https://www.smartsheet.com/resource-management) (formerly 10,000ft).

The integration is **two-way**, controlled per user by a **direction** on each user's sync
record:

- **PUSH** — CHAOTICA is the source of truth. The user's CHAOTICA schedule is mirrored into
  RM (this is the original behaviour).
- **PULL** — RM is the source of truth. The user's RM schedule is imported into CHAOTICA:
  RM projects become internal CHAOTICA Projects (linked back to RM), assignments become
  timeslots, and RM leave becomes authorised leave requests.
- **OFF** — no sync.

The **Authoritative** flag is orthogonal to direction and controls pruning: for PUSH it
deletes RM assignments CHAOTICA doesn't know about; for PULL it deletes imported CHAOTICA
slots that no longer exist in RM. With it off, the sync only adds/updates and never deletes.

### PULL date window

Inbound PULL fetches a date-bounded slice of each user's RM schedule. By default it pulls
**from today forward one year** — no history. The window is configurable:

- **`RM_SYNC_PULL_LOOKBACK_DAYS`** (default `0`) — days of *past* schedule to import. Set to
  `365` to pull the last year of history. `0` means today onwards only.
- **`RM_SYNC_PULL_LOOKAHEAD_DAYS`** (default `365`) — days of *future* schedule to import,
  counting from today.

!!! warning "Look-back and authoritative pruning"
    For **authoritative** PULL records, imported slots not present in the fetched window are
    deleted. Increasing the look-back widens the range that reconciliation considers, and a
    large look-back imports proportionally more historical timeslots (which also feed
    utilisation). Raise it deliberately.

### Reflecting other teams (RM-only users) via Market Units

Users are grouped by RM's **Market Unit** custom field (`UKI`, `Iberia`, `Prague`,
`Nordics`, …). A **Unit Map** (admin: *RM unit maps*) ties each market unit to an
OrganisationalUnit **and** a sync direction — e.g. `UKI → UK OU, PUSH` (CHAOTICA stays
authoritative) and `Iberia/Prague/… → EU OUs, PULL` (reflect RM's schedule).

Typical workflow:

1. `python manage.py run_rm_users` — adopts existing CHAOTICA users by email and creates any
   missing RM users (active, password-less). It sets each record's RM ID + market unit, and
   **auto-creates a Unit Map row (with no OU, disabled) for every market unit it sees**. Add
   `--dry-run` to preview, `--market-unit Prague` to scope.
2. In admin, fill in each Unit Map's **OU + direction** and tick **enabled**.
3. `python manage.py apply_rm_unit_maps` — assigns those OUs and directions to the imported
   users. (OU assignment is non-invasive: users who already belong to a unit are left alone.)

Safety rules that prevent clobbering existing config:

- **Existing direction is never changed.** A record already on PUSH/PULL is left untouched
  (so UKI users stay PUSH) unless you pass `--force-direction`.
- **`--create-missing` only creates absent users**; adopting an existing user is additive
  (fills a blank RM ID / market unit) and never repoints them.
- A different existing RM ID is only overwritten with `--overwrite-rm-id`.

`python manage.py match_rm_users` is the adopt-only variant (same rules; `--create-missing`
optional). Use **Preview Inbound** on the settings page (or `run_rm_pull --dry-run`) to see
what an inbound schedule sync would change without writing.

### Clients

`python manage.py run_rm_clients` pre-imports RM clients (`/api/v1/clients`) into CHAOTICA
`Client`s (keyed on external ID). When inbound sync mirrors an RM project into an internal
`Project`, it links the project's optional **client** by name (creating the Client if needed).

| Setting | Default | Description |
|---------|---------|-------------|
| **RM_SYNC_ENABLED** | `False` | Master toggle for all RM synchronisation. When disabled, sync tasks and API views are blocked. |
| **RM_SYNC_READ_ONLY** | `False` | Hard-blocks **all writes** (POST/PUT/DELETE) to the RM API while still allowing reads. Set this on non-production instances that point at a production RM token so they can pull/preview without ever modifying RM. |
| **RM_SYNC_PULL_ENABLED** | `False` | Enables inbound (RM → CHAOTICA) sync for users whose direction is PULL, and the periodic RM user import. |
| **RM_SYNC_PULL_LOOKBACK_DAYS** | `0` | Days of *past* RM schedule to import on PULL. `0` = today onwards only; e.g. `365` pulls the last year of history. |
| **RM_SYNC_PULL_LOOKAHEAD_DAYS** | `365` | Days of *future* RM schedule to import on PULL, from today. |
| **RM_SYNC_API_SITE** | `https://api.rm.smartsheet.com` | Base URL for the RM API. |
| **RM_SYNC_API_TOKEN** | *(empty)* | Developer API token for authenticating with the RM API. |
| **RM_SYNC_STALE_TIMEOUT** | `60` | Minutes before a running sync task is considered stale/stuck. |
| **RM_SYNC_DOMAIN_REWRITE** | `False` | Rewrite legacy email domains (`accenture.com`/`contextis.com` → `cyberdefense.global`) when matching/creating RM users. A migration artefact; off by default. |
| **RM_WARNING_MSG** | `This project is managed via CHAOTICA.` | Warning text appended to project descriptions in RM to indicate that changes may be overwritten. Also used to detect CHAOTICA-origin projects during inbound sync (loop prevention). |

---

## Support Links

URLs displayed in the help menu in the top navigation bar.

| Setting | Default | Description |
|---------|---------|-------------|
| **SUPPORT_DOC_URL** | `https://docs.chaotica.app/en/latest/` | Link to documentation. |
| **SUPPORT_MAILBOX** | `https://github.com/brainthee/CHAOTICA/issues` | Link to request support. |
| **SUPPORT_ISSUES** | `https://github.com/brainthee/CHAOTICA/issues` | Link to report issues/bugs. |
