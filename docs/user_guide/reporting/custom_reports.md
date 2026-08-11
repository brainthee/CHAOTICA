# Custom Reports

The report builder lets you define a report against a data area (Users, Jobs,
Phases, Projects, Clients), choose columns, filter and sort, and either view it
on screen, export it, or have it **emailed automatically on a schedule**.

!!! note "Who can create reports"
    Every authenticated user can create and own reports — the base **User**
    global role grants `reporting.add_report` and `reporting.view_report`. New
    reports are owned by whoever creates them; owners can always view, edit and
    delete their own reports (and by default they're private). What a report can
    *see* is still scoped to the running user's permissions (below), and
    cross-org reporting still needs **Can run all reports**.

## Building a report

1. Go to **Reporting → New report** and pick a **data area** (e.g. *Phases*).
2. **Select fields** — the columns for your report. Fields are grouped
   (Basic, Job, Dates, Scheduled, …).
3. **Filters** — restrict which records appear (see date windows below).
4. **Sort** — order the results.
5. **Presentation** — choose the default output format (HTML, Excel, PDF, CSV, …).

### Computed columns

Some values aren't stored directly on a record but are calculated from related
data. These are available as ordinary fields you can pick in the wizard. On the
**Phases** data area these include:

| Column | What it shows |
| --- | --- |
| Start Date (effective) | The phase's start date (desired date if set, else the scheduled date) |
| Days Testing | Scheduled delivery days (from timeslots with the *Delivery* role) |
| Days Reporting | Scheduled reporting days (timeslots with the *Reporting* role) |
| Days Management / Days QA / Days Oversight | Scheduled days for those delivery roles |
| Assigned To | Comma-separated list of engineers scheduled on the phase |
| Project Manager | The job's account manager (falls back to the phase project lead) |
| Status (label) | The human-readable phase status |

The **Jobs** data area has equivalent computed columns: *Status (label)*,
*Charge Codes*, *Indicative Services* and *Scoped By* (the latter three are
comma-separated lists).

These behave like any other column — you can reorder them, rename them with a
custom label, and include them in exports.

### QA ratings and feedback (Phases)

The Tech QA and Pres QA report ratings are stored internally as `0`–`4`, but the
app displays them as **1–5 stars** (a stored `2` shows as ★★★). To report on
them the way you read them, use the star columns rather than the raw values:

| Column | What it shows |
| --- | --- |
| Tech QA Stars (1-5) / Pres QA Stars (1-5) | The rating as a 1–5 star count. Filter *equals 3* to get all 3★ reports. |
| Tech QA Rating (label) / Pres QA Rating (label) | The full rating text (e.g. "Average report…") |
| Tech QA Report Rating (raw) / Pres QA (raw) | The stored `0`–`4` value (one less than the star count) |

The free-text QA feedback left against a phase is also available:

| Column | What it shows |
| --- | --- |
| Scope / Tech QA / Pres QA Feedback Count | Number of feedback comments of that type |
| Scope / Tech QA / Pres QA Feedback Text | The comment bodies, as plain text, joined together |

> **Example — "all 3★ reports":** on the *Phases* area, add the *Tech QA Stars
> (1-5)* column and a filter *Tech QA Stars (1-5) equals 3*.

### Rolling date windows

Date filters accept fixed dates and dynamic tokens. As well as `today`,
`this_month_start`, etc., you can use **relative rolling offsets**:

- `today+30d` — 30 days from today
- `today-7d` — 7 days ago

For example, "phases starting in the next month" is two filters on the start
date: *on or after* `today` and *on or before* `today+30d`. Changing `30` to
another number changes the window — it's just data, no code change needed.

## Running a report

When you press **Run Report**, most reports run **inline** and the results appear
on screen straight away. Larger reports (and any **Download As** export) fall back
to **background execution**: a progress page appears showing *Queued… →
Running…*, updates itself, and loads the results (or starts the download) as soon
as they're ready. You can leave the page open while it works.

Background execution means large reports never time out: a big report used to tie
up the request until an upstream proxy (load balancer / nginx) cut it off with an
error. Now the heavy work happens out of band and the browser polls for the result.

Two things worth knowing:

- **Fast path vs. queue.** On-screen reports are attempted inline for a few
  seconds first, so quick reports are instant. Only reports that overrun that
  budget (and all downloads) drop to the background job, which is picked up about
  once a minute — so a queued report can sit at *Queued…* for up to ~60 seconds
  before it starts. This is normal.
- **Results expire.** A finished run's on-screen data and any exported file are
  kept for a couple of hours, then cleaned up automatically. Re-run the report to
  regenerate them.

Results are stored durably (on-screen rows in the database, export files in shared
object storage), so they load correctly no matter which server instance handles
your request. The background job (`reporting.tasks.ProcessReportRuns`, run by the
same `runcrons` scheduler that sends scheduled report emails) also re-queues any
run left stuck *Running…* by a crashed worker.

## The Tentative Projects report

A ready-made report lists phases whose schedule is still **tentative**
(scheduled but not yet confirmed) within a rolling window. It reproduces the
weekly "tentative chaser" that Demand Management used to assemble by hand:
Client, CHAOTICA ID, Project Name, Project Manager, Project Type, Assigned To,
Start Date, Days Testing, Days Reporting.

To (re)create it in an environment:

```bash
cd app
python manage.py setup_reporting_models      # ensure the fields exist
python manage.py setup_tentative_report       # create/refresh the report
# optional: --owner someone@example.com  --window-days 30
```

It's an ordinary report — you can duplicate or tweak it in the wizard.

## What data a report shows

Reports are scoped to what the **running user** is allowed to see, using the same
organisational-unit permissions as the rest of the app:

- A normal user only sees jobs/phases (and job-owned data) in the units they hold
  **Can view jobs** on. Data from other units is excluded — running a report is
  not a way to see across units you otherwise can't.
- Protectively Marked / **restricted** jobs are always excluded for everyone
  except superusers.
- Sensitive columns that require a permission are blanked out for users who lack
  it (on every execution path, including aggregated/grouped reports).
- To intentionally run **cross-org** reports (e.g. a company-wide chaser), grant
  the account the **Can run all reports** (`reporting.can_run_all_reports`)
  permission. That still excludes restricted jobs.

!!! note "Data areas without a unit link"
    Data areas that aren't tied to an org unit (e.g. some reference lists) return
    no rows for ordinary users — they require **Can run all reports** or a
    superuser. Grant the dedicated reporting account that permission if it needs
    them.

## Scheduling & emailing a report

Open a report and click **Schedule** to add one or more scheduled emails.

**Cadence** — daily, or weekly on a chosen day, at a chosen time. A background
job checks every 15 minutes; each schedule sends at most once per day.

**Run as** — the report runs with this user's permissions. Choose a dedicated
reporting account with the right unit visibility (add **Can run all reports** for
a company-wide report). **Superusers can't be selected** — that would side-step
the unit scoping and restricted-job exclusion described above. The report's data
is scoped to this user, so restricted work never leaks into a broad email.

**Recipients** — you can send:

- an **aggregated** email (the full table) to a list of addresses and/or an
  auth group, and/or
- **personalised slices**: choose a *Split by field* (e.g. *Account Manager
  Email*) and each manager receives an email containing only their own rows.

Both can be enabled at once — a group summary plus per-manager slices. The split
field does not need to be a visible column; it's fetched behind the scenes.

!!! warning "Split-slice recipients must be known users"
    Because the split value comes from the data, personalised slices are only
    delivered to addresses that belong to an **active user in the system**. An
    address that isn't a known user is skipped (and logged), so report rows can't
    be emailed to an arbitrary address that happens to appear in the data.

**Content** — set the subject and optional intro/outro HTML shown above and
below the table. You can also attach the results as CSV or Excel.

!!! note "Email must be enabled"
    Scheduled emails only send when the `EMAIL_ENABLED` setting is on. In
    development the console email backend prints emails instead of sending them.

## Editable email templates

All system emails (leave, invites, job/phase notifications, scheduled reports,
…) render from **database-stored templates** that superusers can edit under
**Admin → Email Templates**, so wording can change without a deploy.

- Each template is keyed by a slug matching its original file path
  (e.g. `emails/leave_requested.html`).
- Editors change the **subject**, **content**, and **button label** only; the
  shared responsive shell (`email_base.html`) is applied automatically.
- Use **Preview** to see a rendered example with sample data.
- If a template is set inactive (or missing), the system falls back to the
  built-in filesystem template, so emails never break.
- Defaults are loaded automatically on migration; re-seed with
  `python manage.py seed_email_templates` (add `--force` to overwrite edited
  templates).

!!! warning "Template editing is superuser-only"
    Email bodies are Django templates. Editing them is a template-injection
    surface, so it is restricted to superusers, and tags like `{% load %}` /
    `{% include %}` are rejected on save.

## Related Topics

- [Reporting Overview](overview.md)
- [Scheduling Overview](../scheduling/overview.md)
