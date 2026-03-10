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

| Setting | Default | Description |
|---------|---------|-------------|
| **RM_SYNC_ENABLED** | `False` | Master toggle for all RM synchronisation. When disabled, sync tasks and API views are blocked. |
| **RM_SYNC_API_SITE** | `https://api.rm.smartsheet.com` | Base URL for the RM API. |
| **RM_SYNC_API_TOKEN** | *(empty)* | Developer API token for authenticating with the RM API. |
| **RM_SYNC_STALE_TIMEOUT** | `60` | Minutes before a running sync task is considered stale/stuck. |
| **RM_WARNING_MSG** | `This project is managed via CHAOTICA.` | Warning text appended to project descriptions in RM to indicate that changes may be overwritten. |

---

## Support Links

URLs displayed in the help menu in the top navigation bar.

| Setting | Default | Description |
|---------|---------|-------------|
| **SUPPORT_DOC_URL** | `https://docs.chaotica.app/en/latest/` | Link to documentation. |
| **SUPPORT_MAILBOX** | `https://github.com/brainthee/CHAOTICA/issues` | Link to request support. |
| **SUPPORT_ISSUES** | `https://github.com/brainthee/CHAOTICA/issues` | Link to report issues/bugs. |
