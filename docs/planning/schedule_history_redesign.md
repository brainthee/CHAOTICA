# Schedule History tab — redesign plan

**Status:** Plan for review (branch `feature/schedule-history-redesign`)
**Purpose:** Rebuild the "Schedule History" tab on a user's profile on top of the
`ScheduleAction` version-control log, replacing the stale django-simple-history
timeline, so the profile, scheduler, and job/phase panels all read one source of truth.
**Scope:** The `schedule_history` tab in `chaotica_utils/templates/chaotica_utils/user_detail.html`
and its partial `partials/users/user_schedule_history.html`, plus a `user`-scoped
addition to the schedule-actions selector/API.

---

## 1. Why change

The tab today (`partials/users/user_schedule_history.html`) renders a date-grouped
`timeline-basic` from `TimeSlot.history` (django-simple-history), populated by
`chaotica_utils/views/user_management.py:142`:

```python
context["schedule_history"] = TimeSlot.history.filter(
    user=self.get_object()
).prefetch_related("history_user")
```

Problems:

1. **Wrong history system.** The app records every scheduler mutation as a
   `ScheduleAction` (one logical, reversible, human-summarised change with
   `summary`, `forced`, `override_reason`, revert support). The profile tab ignores
   all of that and shows raw per-row simple-history records with only the slot's
   `__str__`. It is a stale parallel implementation of a feature that already
   exists in a richer form on the scheduler and job/phase pages.
2. **Unbounded.** The queryset has no date filter (the view computes `start_date`/
   `end_date` for the Stats tab but never applies them here) and no pagination —
   a long-tenured user loads their entire slot-change history into one DOM blob.
3. **Dead affordances.** The actor link is `href="#!"`; there's no link to the
   job/phase a change touched; no revert; no filtering.
4. **Self-described as untrustworthy.** It opens with a banner: *"This page is
   somewhat experimental and should only be used as a rough guide for now."*

## 2. What we reuse

Already built and shipping on the scheduler — we reuse, not reinvent:

| Piece | Location | Reuse |
|---|---|---|
| `ScheduleAction` model | `jobtracker/models/schedule_action.py` | source of truth; `can_revert()`, `_affected_user_ids()` |
| `schedule_history()` selector | `jobtracker/selectors/schedule.py:341` | add a `user_id` scope (see §4) |
| `ScheduleActionSerializer` | `jobtracker/api/v1/serializers/schedule.py:248` | JSON shape (summary, forced, override_reason, items, can_revert…) |
| `schedule-actions` endpoint | `jobtracker/api/v1/views/schedule.py:318` | add `user` param |
| `renderHistory()` card UI | `templates/js/scheduler_vis_init.js:1505` | lift the card markup into a small standalone script |
| revert endpoint | `schedule_action_revert` (`urls.py:116`) | reuse as-is |

## 3. Target design

**Functionality**
1. Tab reads `ScheduleAction`s **touching this user** (as a scheduled resource),
   newest first, via a new `user` scope on the actions endpoint.
2. Per-item **revert** button, gated on the existing `can_revert` rule; reverted
   items dimmed with a "reverted" badge (identical to the scheduler panel).
3. Show **override reasons** and the ⚠ forced flag — the richest signal, invisible today.
4. **Date-range + action-type filters**: wire the range the view already computes;
   add type chips (Created / Updated / Moved / Cleared / Reverted). Lazy-load / paginate.
5. Actor becomes a real profile link; each item links back to its job/phase.
6. Remove the experimental banner.

**Design / looks** (house style: fs-9, no bespoke old-theme markup)
- Replace the heavy `timeline-basic` with the scheduler's compact history-card row
  (icon + bold summary + `actor · relative-time`, forced rows flagged amber),
  under light day dividers.
- A small KPI strip at the top: counts by action type over the selected range, so
  the tab doubles as a "how volatile is this person's schedule" read. (Use the
  `dataviz` palette conventions.)
- Relative times ("2h ago") with exact timestamp on hover.

## 4. Implementation steps

1. **Selector** — add `user_id=None` to `schedule_history()` (`selectors/schedule.py`).
   When set and no job/phase, scan recent actions and keep those whose
   `_affected_user_ids()` contains `user_id` **and** that the viewer may see.
   *Perf note:* `ScheduleAction` has no user FK — matching is a Python scan over
   JSON payloads (same pattern as the existing global path). For the profile tab's
   bounded range this is fine; if it bites, denormalise affected-user PKs into an
   indexed column in a follow-up (out of scope here).
2. **API** — add a `user` query param to `schedule.actions` (`views/schedule.py:318`),
   authorised with the same rule the profile view already uses
   (`_get_schedule_viewable_user`, i.e. `context["can_view_schedule"]`).
3. **View** — delete the simple-history queryset in `user_management.py:142`;
   pass the target user pk + the computed date range to the template as config for
   the JS fetch (no server-rendered list).
4. **Partial + JS** — rewrite `user_schedule_history.html` to host the card list
   container, filter chips, and KPI strip; add a small script that calls the
   actions endpoint and reuses the `renderHistory()` card markup + revert handler.
5. **Gating** — only render the tab when `can_view_schedule` is true (today it's
   always shown; the simple-history data leaked regardless of schedule-view rights).
6. **Docs** — update any user-guide reference to the tab; drop "experimental".
7. **Tests** — selector user-scope (authorised vs not; reverted dimming;
   affected-user matching), API param, and the tab gating.

## 5. Risks / decisions

- **Authorisation tightening (step 5)** is a behaviour change: the tab currently
  shows history to anyone who can see the profile. Moving it behind
  `can_view_schedule` is correct but worth flagging to reviewers.
- **No user FK on `ScheduleAction`** — accepted as a Python-scan match for now;
  denormalisation deferred.
- **Simple-history retirement** — we stop *reading* `TimeSlot.history` here; the
  records still exist. No migration needed. Decide separately whether simple-history
  on `TimeSlot` is still earning its keep elsewhere.

## 6. Out of scope

- Denormalising affected users onto `ScheduleAction`.
- Removing django-simple-history from `TimeSlot`.
- Any change to the scheduler/job/phase history panels (they already use this).
