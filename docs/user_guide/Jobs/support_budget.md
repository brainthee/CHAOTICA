# Support-Team Budget

Delivery jobs are run by consultants, but a **back-office support team** (account
management, sales, PM, QA) also takes a share of each job. CHAOTICA works out how
much budget each support member gets — in money, hours and days — from the job's
revenue, and lets each member draw that budget down against the relevant billing
/ WBS code over time.

This is a **read-only computed view** (like the billing-code allocation): it does
not create schedule bookings. It answers *"of this job's revenue, how much time
should each support person book, and how much have they used?"*

## The model

For a job of value **V** (`Sales Revenue` on the job):

1. **Support pool** = `V × premium%`. The premium defaults to **8%** but can be
   overridden (see [Configuring the premium](#configuring-the-premium)).
2. Each support member has a **profile allocation %** — their coverage
   (`100` = full, `20` = 20%).
3. A member's **share** of the pool = `percent ÷ Σ percents`. For example, six
   members at `100%` plus two at `20%` give a total of `640`, so a full member's
   share is `100 ÷ 640 = 15.625%`.
4. **Budget (money)** = `pool × share`.
5. **Budget (hours)** = `budget ÷ loaded cost rate`; **days** = `hours ÷
   hours-in-day` (the client's working-day length, default 7.5).

## Organisational-unit template

Most jobs in a unit use the same support team, so each **organisational unit**
can hold a **support-team template**: a list of members, each with a role and a
profile allocation %, plus the unit's default premium %.

Everything is managed from the **Finance tab** on the organisational-unit detail
page (see [The Finance tab](#the-finance-tab)) — the Django admin is not needed.

- When a **new job** is created in that unit, the template is applied
  automatically, creating a support-team row per member.
- On an existing job, use **Support → Apply Support Template** to (re)apply it.

## The Finance tab

On the organisational-unit detail page, users with the **Can view loaded cost
rates** permission see an extra **Finance** tab (hidden from everyone else). It
holds three cards:

- **Settings** — edit the unit's *support premium default %*.
- **Support Template** — add / edit / remove template members and their profile
  allocation %.
- **Loaded Cost Rates** — set each member's date-effective LCR (see below). Rates
  are add-only: a new rate keeps the previous ones for historical budgets.

Because all of this is normal data behind a permission, changing the support
model is a day-to-day operation, not a code change.

### Overrides

You can change people, allocation % and hours on an individual job. Any row you edit
is flagged as **overridden** and is left untouched when the template is
re-applied — unless you tick *"Also overwrite manually-edited rows"*. Members
removed from the template are never auto-deleted from a job (their history and
draw-downs are preserved).

## Configuring the premium

The premium % is resolved in this order (no code change needed to adjust it):

1. **Per-job override** — `Support Premium Override (%)` on the job.
2. **Unit default** — `Support Premium Default (%)` on the organisational unit.
3. **Global default** — `SUPPORT_PREMIUM_DEFAULT` (8%), on the **Settings** page
   under **Finance → Support Team**.

Profile allocation %, membership, loaded cost rates and the working-day length
are likewise all editable data, not code.

## Loaded cost rates (LCR)

The money→hours conversion uses each person's **loaded cost rate** — a per-user,
date-effective cost. The rate in force on the relevant date is used, so
historical changes are respected. Manage rates from the unit's **Finance →
Loaded Cost Rates** card.

**Visibility:** loaded cost rates are financially sensitive and are only shown on
the unit **Finance** tab and a member's own **Billing Codes** page to holders of
the **Can view loaded cost rates** (`can_view_loaded_costs`) permission.

## The job Support widget

The **Support** panel on the job page is intentionally minimal — **Person**,
**Role** and **Share** (each member's % of the support pool). Use the row menu to:

- **Edit** — override a member's profile allocation % for this job (the row is
  then flagged *override* and protected from a template re-apply).
- **Draw Down Hours** — see below.
- **Delete** — remove the member from this job.

The full picture — budget in money/hours, drawn and remaining — lives on each
member's **Billing Codes** page, so the job view stays uncluttered.

## Drawing down budget

Each timesheet period a support member "cashes out" hours against their budget.
Two places do this:

- **Self-service** — on their own **Billing Codes** page, the *Support budget*
  table has a **Cash out** button per job. The period defaults to the current
  timesheet period. This is gated to the member themselves and their managers
  (no scheduling rights on the job required).
- **From the job** — **Draw Down Hours** on the job's Support widget (for people
  with scheduling rights on that job).

**Remaining** = budget hours − everything drawn, and it **carries forward** across
periods; over-drawing is allowed and shown in red.

## The per-user Billing Codes page

Every user has a **Billing Codes** page (top-right user menu → *My Billing
Codes*, or a manager can open it from a person's profile). It shows, for a date
range:

- **billing-code usage from their schedule** — which codes their booked time maps
  to, per day and per code, with the phase/project shown against each; and
- their **support budget** — per-job budget hours, drawn this period and
  remaining.

Headline **stats** for the period sit at the top: *Capacity* (working days ×
hours-per-day), *Coded*, *Uncoded* (scheduled work missing a code), *Unavailable*
(leave / sick / bank holiday) and *Internal* (training / internal time) hours — so
the numbers read against a real week.

It's visible to the user themselves and to anyone who can manage them; money/LCR
figures on it are gated by `can_view_loaded_costs`.

### Multiple codes on a day & leave

When a day maps to **more than one billing code**, how the hours are attributed is
controlled site-wide by **Settings → Finance → Billing Codes**
(`BILLING_DUPLICATE_CODE_POLICY`):

- **Split evenly** (default) — the day's hours are divided across the codes (2
  codes ⇒ 50/50), so day totals match real hours.
- **Stack** — each code gets the full day's hours (totals can exceed the day).
- **Prefer newest / oldest** — the whole day goes to a single code by assignment
  date.

**Leave wins:** if a job's schedule overran into a day you were on leave, that
day's *coded* hours are reduced by the overlapping leave — you didn't actually
deliver — and the day shows the leave instead. Leave/sick time is reported under
*Unavailable*, separate from *Uncoded* (missing-code) work.

### Timesheet periods

The page opens on the **current timesheet period** and has ◀ / ▶ buttons to step
between periods (plus a *Custom range* picker for anything else). The period
boundaries are set on the **Settings** page under **Scheduling → Work Settings**
(`TIMESHEET_PERIOD_START_DAYS`) — a comma-separated list of the days of the month
a period starts on. For example `1,15` gives two periods per month (1st–14th and
15th–end); `1` gives whole-month periods. Changing it applies immediately, no
deploy.
