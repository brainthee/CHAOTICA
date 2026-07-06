# Change History, Undo & Live Updates

Every change you make on the scheduler — booking, editing, moving, clearing, the bulk
Tools, and reverts themselves — is recorded as a single **schedule action**. That log
powers two things: a **change history** you can revert from, and **live updates** so
other people looking at the same schedule see your changes appear as they happen.

## Change history & reverting

The toolbar has a **History** button (on every scheduler surface — global, job and
phase). It opens a panel listing recent changes for the scope you're viewing, newest
first, each showing:

- **what changed** (a short summary, e.g. *Created 1 slot*, *Moved 3 slots*, *Cleared 5 slots*),
- **who** made it and **when** (relative time),
- a **Revert** button, where allowed.

Reverting applies the exact inverse of a change:

| Original change | Revert does |
|---|---|
| Created a slot | Deletes it |
| Deleted / cleared slots | Recreates them |
| Edited / moved a slot | Restores its previous dates, person, role, onsite flag, etc. |

Reverts are routed through the normal save path, so phase status and dates recalculate
and the activity log updates just as they would for a manual change.

!!! note "A revert is itself undoable (redo)"
    Each revert is recorded as its own action, so you can revert the revert to redo the
    original change.

### Who can revert what

- You can revert **your own** changes, provided you **still** hold scheduling
  permission (`can_schedule_job`) on the affected job/phase — reverting recreates
  or removes the same slots, so it needs the same permission as a live edit. If
  you've since been removed from that unit or job, your old changes become
  read-only.
- Reverting **someone else's** change requires the site‑level permission
  **_Can revert any schedule change_** (`jobtracker.revert_any_scheduleaction`), which
  administrators hold by default. Without it, other people's changes show as read‑only
  history with no Revert button.

!!! note "History is scoped to what you can see"
    The History panel and the live/polled updates only ever show changes for
    schedules you're allowed to view (`view_job_schedule`). Opening a job or phase
    scope you don't have access to returns nothing, and global live updates are
    filtered to the people whose schedules you can see.

### Undo with Ctrl/⌘ + Z

Press **Ctrl+Z** (or **⌘+Z** on Mac) while on a scheduler page to revert **your own
most‑recent change** in the current scope. Press it again to walk further back through
your edits. (It's ignored while typing in a field or with a modal open, and disabled on
the read‑only schedule tabs.)

## Live updates

When you change the schedule, anyone else with that schedule open sees the change
**applied in place** — a booking appears, moves or disappears on their timeline within a
second or so, without them reloading or panning. A change on a job or phase schedule also
updates the **global** scheduler for anyone watching it.

This runs over a WebSocket. If the socket can't be established (for example the site
isn't deployed with the WebSocket server, or a proxy blocks the upgrade), the scheduler
**automatically falls back to polling** for changes every few seconds — the live
behaviour still works, just with a small delay, and no configuration is needed.

## Related Topics

- [Scheduling Overview](overview.md)
- [Booking & Validation](validation.md)
- [Permissions](../../administration/permissions.md)
