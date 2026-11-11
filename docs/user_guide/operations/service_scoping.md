# Service Scoping

CHAOTICA can capture structured scoping information for a service and turn it
into an effort estimate (testing + reporting days, converted to phase hours).

Because every team scopes differently — and because CHAOTICA is open source —
**no scoping rules are built into the product**. You author your own questions
and formulas as data, and you can share them between instances as JSON
*scoping packs*. Nothing organisation-specific ever lives in the codebase.

## Concepts

- **Scoping template** — a reusable questionnaire plus a calculation. A service
  points at one template; many services can share the same template.
- **Field (question)** — one input on the template (number, checkbox, dropdown,
  text). Each field has a *calculation role* (see below).
- **Macro** — a reusable named formula (for example a reporting-days rule) so
  shared logic lives in one editable place.
- **Scoping pack** — a JSON export/import of templates and their macros.

Manage these under **Operations → Scoping Templates** (requires the
`Manage Scoping Templates` permission).

## Building a template

1. Go to **Operations → Scoping Templates → New template**.
2. Give it a name and add questions. For each question set:
    - **Type** — Number, Checkbox, Dropdown, Short/Long text.
    - **Slug** — the identifier used in formulas (e.g. `live_ips`).
    - **Calculation role**:
        - *Sizing metric* — `value ÷ rate = days` (set the per-day **rate**).
        - *Additive* — adds days (set **weight** = days; for a number field the
          days added are `value × weight`).
        - *Multiplier* — adds a percentage (set **weight** = fraction, e.g.
          `0.1` for +10%).
        - *Mode selector / Display only* — captured but combined via an
          expression (see below).
3. Choose how the calculation works:
    - **Declarative** — CHAOTICA combines your sizing/additive/multiplier fields
      as `(max-or-sum of sizing days + additive) × (1 + multipliers)`.
    - **Expression** — you write the testing-days formula yourself, referencing
      field slugs, e.g. `max(pages / 15, inputs / 200)`.
4. Set the **reporting** step: either pick a macro or write a reporting
   expression. It receives `testing_days`.

### Expression helpers

Formulas are evaluated in a **sandbox** (arithmetic only — no code execution).
Available helpers:

```
ceil, floor, round, round_half_up, max, min, abs,
bucket(value, thresholds, values)
```

`bucket()` does a tiered lookup: it returns the value for the first threshold
that `value` does not exceed — handy for banded pricing or sample sizes.

## Testing a template

The template editor has a **Test this template** panel. Fill in sample answers
and click **Calculate** to see testing/reporting days, the resulting phase
hours, and a human-readable "based on" breakdown. The panel always uses the
last **saved** version of the template.

Days are converted to hours using the `DEFAULT_HOURS_IN_DAY` setting (Settings
page; default 7.5).

## Scoping a phase

Once a service has a scoping template, every phase that uses that service gets a
**Scoping** tab on its detail page.

1. Open the phase and go to the **Scoping** tab. If the phase's service has no
   template attached you'll see an empty state linking to the service.
2. Answer the questions (they are pre-filled from the last saved answers).
3. **Calculate** shows a live preview of testing/reporting days and the
   resulting delivery/reporting hours, with a "based on" breakdown.
4. **Save answers** stores your answers on the phase without touching its hours.
5. **Apply to hours** additionally writes the calculated **delivery** and
   **reporting** hours onto the phase and records the justification.

Applying to hours is only available while the phase's hours are still editable
for its status (up to and including *In Progress*). In later statuses the button
is hidden and the saved answers are kept for reference only.

## Editing deliverables and report details

Deliverable links (deliverable / report data / technical data) **and** the
report metadata (number of reports, "left on client site", desired delivery
date, due-to-Tech-QA and due-to-Pres-QA dates) stay editable from **In Progress**
all the way through to **Delivered**. Use the **Edit** pencil on the phase's
*Deliverables* tab. Scheduling and service fields still lock once a phase starts;
only deliverables/report details remain open until the report is delivered.

## API

The scoping engine is available over the versioned API (`/api/v1/`) so external
tools can fetch a questionnaire and score a scope:

- `GET /api/v1/scoping-templates/` — list active templates.
- `GET /api/v1/scoping-templates/{id}/` — one template with its fields/options.
- `POST /api/v1/scoping/calculate/` — body `{"template": <id|slug>, "answers":
  {slug: value}}`; returns `{testing_days, reporting_days, delivery_hours,
  reporting_hours, justification, errors}`.

All three require authentication. See the API docs at `/api/v1/schema/swagger-ui/`.

## Import / export (scoping packs)

- **Export** a single template (or all templates) to a `.json` pack from the
  list page or the template editor.
- **Import** a pack from **Scoping Templates → Import**. Macros are created
  first, then templates. Tick *overwrite* to replace templates/macros with the
  same name; otherwise existing ones are skipped.

Keep your organisation's scoping rules in a private pack and import it into each
instance — they stay out of the source tree.
