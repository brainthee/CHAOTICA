# Custom Reports

The report builder lets you define a report against a data area (Users, Jobs,
Phases, Projects, Clients), choose columns, filter and sort, and either view it
on screen, export it, or have it **emailed automatically on a schedule**.

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
| Assigned To | Comma-separated list of engineers scheduled on the phase |
| Project Manager | The job's account manager (falls back to the phase project lead) |
| Status (label) | The human-readable phase status |

These behave like any other column — you can reorder them, rename them with a
custom label, and include them in exports.

### Rolling date windows

Date filters accept fixed dates and dynamic tokens. As well as `today`,
`this_month_start`, etc., you can use **relative rolling offsets**:

- `today+30d` — 30 days from today
- `today-7d` — 7 days ago

For example, "phases starting in the next month" is two filters on the start
date: *on or after* `today` and *on or before* `today+30d`. Changing `30` to
another number changes the window — it's just data, no code change needed.

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

## Scheduling & emailing a report

Open a report and click **Schedule** to add one or more scheduled emails.

**Cadence** — daily, or weekly on a chosen day, at a chosen time. A background
job checks every 15 minutes; each schedule sends at most once per day.

**Run as** — the report runs with this user's permissions. Use a dedicated
reporting account, **not** a superuser: non-superusers never see Protectively
Marked / restricted jobs, so restricted work won't leak into a broad email.

**Recipients** — you can send:

- an **aggregated** email (the full table) to a list of addresses and/or an
  auth group, and/or
- **personalised slices**: choose a *Split by field* (e.g. *Account Manager
  Email*) and each manager receives an email containing only their own rows.

Both can be enabled at once — a group summary plus per-manager slices. The split
field does not need to be a visible column; it's fetched behind the scenes.

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
