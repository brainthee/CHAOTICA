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
   set per support profile or per job (see
   [Configuring the premium](#configuring-the-premium)).
2. Each support member has a **profile allocation %** — their coverage
   (`100` = full, `20` = 20%).
3. A member's **share** of the pool = `percent ÷ Σ percents`. For example, six
   members at `100%` plus two at `20%` give a total of `640`, so a full member's
   share is `100 ÷ 640 = 15.625%`.
4. **Budget (money)** = `pool × share`.
5. **Budget (hours)** = `budget ÷ loaded cost rate`; **days** = `hours ÷
   hours-in-day` (the client's working-day length, default 7.5).

Support rows without a live person (e.g. a deleted account) are left out of the
split, so they never dilute everyone else's share.

## Support profiles

A unit can run more than one support team. For example, UKI might have a
**Context** team and a **CCX** team, with different people and different figures.
Each one is a **support profile**, which has:

- a **name** (and optional description);
- its own **members**, each with a role and a profile allocation %. The same
  person can be in several profiles;
- an optional **premium %**. Leave it blank to use the unit's support premium
  default.

One profile per unit is the **default**. The first profile you create becomes the
default, and if you delete the default, another profile takes its place.

Each job uses **one** profile:

- When a **new job** is created, the unit's default profile is applied
  automatically, with one support-team row per member.
- On an existing job, use **Support → Change Support Profile** to pick a
  different profile, or to re-apply the current one after its members changed.
  The options are:
    - **Remove people who aren't in this profile**: ticked by default, which is
      what you want when switching teams. People who have already cashed out
      hours on the job are always kept, because their cash-outs are financial
      records.
    - **Also overwrite manually-edited rows**: see [Overrides](#overrides).
    - **Premium override (%)**: only shown to holders of *Can view loaded cost
      rates*.

Everything is managed in the main UI (the Django admin is not needed). Profiles
live on the **Finance tab** (see [The Finance tab](#the-finance-tab)), and a
job's profile is chosen on the job page.

## The Finance tab

On the organisational-unit detail page, users with the **Can view loaded cost
rates** permission see an extra **Finance** tab (hidden from everyone else). It
holds three cards:

- **Settings**: edit the unit's *support premium default %*, which is used by
  any profile that has no premium of its own.
- **Support Profiles**: add, edit or delete profiles (name, premium, default).
  Use each profile's menu to add members, and the member rows to edit or remove
  them.
- **Loaded Cost Rates** — set each member's date-effective LCR (see below). Rates
  are add-only: a new rate keeps the previous ones for historical budgets.

Because all of this is normal data behind a permission, changing the support
model is a day-to-day operation, not a code change.

### Overrides

You can change people and allocation % on an individual job. Any row you edit is
flagged as **overridden** and is left untouched when a profile is re-applied,
unless you tick *"Also overwrite manually-edited rows"*. Some rules:

- A person can appear only once on a job's support team.
- Once someone has cashed out hours on a row, that row can't be deleted, and its
  person can't be changed. To remove it, reverse the cash-outs first (see
  [Reversing a cash-out](#reversing-a-cash-out)).

## Configuring the premium

The premium % is resolved in this order (no code change needed to adjust it):

1. **Per-job override**: *Premium override (%)* in the job's **Change Support
   Profile** dialog (finance users only).
2. **Support profile**: the job's profile's *Support Premium (%)*, if one is set.
3. **Unit default**: `Support Premium Default (%)` on the organisational unit.
4. **Global default**: `SUPPORT_PREMIUM_DEFAULT` (8%), on the **Settings** page
   under **Finance → Support Team**.

Premiums and allocation % can't be negative.

Profile allocation %, membership, loaded cost rates and the working-day length
are likewise all editable data, not code.

## Loaded cost rates (LCR)

The money→hours conversion uses each person's **loaded cost rate**, a per-user,
date-effective cost. Budgets are always shown at **today's** rate. Each cash-out
also records the rate in force when it was made (see
[Cashing out budget](#cashing-out-budget)). Manage rates from the unit's
**Finance → Loaded Cost Rates** card.

**Visibility:** loaded cost rates are financially sensitive. They, and any £
figures derived from them, are only shown to holders of the **Can view loaded
cost rates** (`can_view_loaded_costs`) permission. That covers the unit
**Finance** tab, money columns on the **Billing Codes** page, and the per-person
budget and hours on the job's **Sales** tab. Hours alone, next to revenue and
share, would reveal a person's rate, so they are hidden too.

## The job Support widget

The **Support** panel on the job page is intentionally minimal. Its header shows
the job's **profile** and effective premium, and the table lists **Person**,
**Role** and **Share** (each member's % of the support pool). The row menu has:

- **Edit**: override a member's profile allocation % for this job. The row is
  then flagged *override* and protected when the profile is re-applied.
- **Cash out hours**: see below.
- **Cash-out history**: every cash-out on this row, with reversal for people
  who are allowed to reverse.
- **Delete**: remove the member from this job. This is blocked if they have
  cashed out hours.

The full picture — budget in money/hours, drawn and remaining — lives on each
member's **Billing Codes** page, so the job view stays uncluttered.

When adding or editing a support member, **type at least three letters** of
their name or email to search; only active accounts are offered, and a person
is required. The same search is used when adding people to a support profile
or an organisational unit.

Every change is logged in the job's **Activity** tab, for example *"Ada
Lovelace added at 20.5% as QA support role."*, *"… updated to 100% …"* (only
when something actually changed), *"… deleted from support role."*, *"… cashed
out 2.5h of support budget (2026-09-01 - 2026-09-07)."* and *"Reversed …'s
cash-out of 2.5h (…)."*.

## Cashing out budget

Each timesheet period, a support member "cashes out" hours against their budget.
There are three ways to do this:

- **Self-service**: on their own **Billing Codes** page, the *Support budget*
  table has a **Cash out** button per job. The period defaults to the period
  being viewed, and the hours default to everything remaining. Only the member
  themselves and their managers can do this; no scheduling rights on the job are
  needed.
- **Auto cash out this period**: this tops up every job with whatever remains
  for that member. Clicking it again does nothing, because nothing is left.
- **From the job**: **Cash out hours** on the job's Support widget. This needs
  scheduling rights on the job **and** either being the member, managing them,
  or holding **Can view loaded cost rates** on the job's unit. Scheduling rights
  alone don't let you cash out someone else's budget, and the menu item is
  hidden for people who can't use it.

### Limits

Cash-outs are checked on the server and are rejected when:

- the hours are more than the member has **remaining**;
- the hours are zero or negative;
- the period ends before it starts;
- the period **starts in the future** — cash-outs cover the current or a past
  period only;
- the member has no loaded cost rate (no rate, no hours);
- the job isn't **active or completed**. Completed jobs can still be cashed out
  (the work was done, so the budget was earned). Deleted, archived and lost jobs
  can't.

Simultaneous submissions (a double-click, or two tabs open) are handled safely:
they can't both spend the same remaining budget.

### How remaining is worked out

Budget is tracked in **money**:

- Each cash-out records its hours, the loaded cost rate at that moment, and its
  value (hours × rate).
- **Remaining** = budget money − the value of all cash-outs. It is shown in hours
  at today's rate, and it **carries forward** from one period to the next.

So if a person's rate changes, their **remaining hours** shift to match the new
rate. Hours already cashed out are never re-priced, and a rate rise can't push
anyone into a negative balance.

### Reversing a cash-out

A support budget lowered after hours were cashed out (e.g. revenue reduced)
shows a **negative** remaining balance; nothing is clawed back automatically.

Mistakes are fixed from **Cash-out history**, which is in the job's Support row
menu and behind the **History** button on the Billing Codes page.

- Members (and their managers) can see their history.
- Only people with **scheduling rights on the job** or **Can view loaded cost
  rates** on its unit can **reverse** a cash-out. Reversing deletes the cash-out,
  returns its value to the remaining budget, and logs it in the job's activity.

## The per-user Billing Codes page

Every user has a **Billing Codes** page (top-right user menu → *My Billing
Codes*, or a manager can open it from a person's profile). It shows, for a date
range:

- **billing-code usage from their schedule** — which codes their booked time maps
  to, per day and per code, with the phase/project shown against each; and
- their **support budget**: per-job budget hours, hours cashed out this period,
  and remaining, for active and completed jobs. Any problems are shown above the
  table, such as a missing loaded cost rate.

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
