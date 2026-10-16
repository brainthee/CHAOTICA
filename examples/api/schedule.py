#!/usr/bin/env python3
"""Show scheduled timeslots in a date window, grouped by user.

Iterates ``/api/v1/timeslots/`` and filters client-side to slots overlapping the
window (default: the next 4 weeks). Timeslots are permission-scoped to users
whose schedule you may view, plus your own.

    python schedule.py
    python schedule.py --days 14 --user 42

There is no ``/api/v1/users/me/`` endpoint, so "my schedule" is expressed as a
single-user filter (``--user`` / ``CHAOTICA_USER_ID``).
"""

import argparse
import datetime
import os

from chaotica_client import (
    ChaoticaClient,
    ChaoticaClientError,
    die,
    print_table,
    ref_id,
    ref_label,
)


COLUMNS = [
    ("start", "Start"),
    ("end", "End"),
    ("deliveryRole_display", "Role"),
    ("engagement", "Phase / Project"),
    ("is_onsite", "Onsite"),
]


def _parse_dt_date(value):
    """Return the date part of an ISO datetime/date string, or None."""
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except (ValueError, TypeError, AttributeError):
        return _parse_date(value)


def _parse_date(value):
    try:
        return datetime.date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def _engagement(slot):
    for key in ("phase", "project", "slot_type"):
        if slot.get(key):
            return ref_label(slot[key])
    return ""


def main():
    default_days = int(os.environ.get("CHAOTICA_SCHEDULE_DAYS", "28"))
    default_user = os.environ.get("CHAOTICA_USER_ID")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--days",
        type=int,
        default=default_days,
        help="Window size in days (default {}).".format(default_days),
    )
    parser.add_argument(
        "--user",
        type=int,
        default=int(default_user) if default_user else None,
        help="Only show this user id (default CHAOTICA_USER_ID, if set).",
    )
    args = parser.parse_args()

    today = datetime.date.today()
    horizon = today + datetime.timedelta(days=args.days)

    client = ChaoticaClient.from_env()
    names = {}

    # Group matching slots by user id.
    by_user = {}
    for slot in client.iterate("timeslots"):
        if args.user is not None and ref_id(slot.get("user")) != args.user:
            continue
        start = _parse_dt_date(slot.get("start"))
        end = _parse_dt_date(slot.get("end")) or start
        if start is None:
            continue
        # Keep slots that overlap [today, horizon].
        if end < today or start > horizon:
            continue
        names[ref_id(slot.get("user"))] = ref_label(slot.get("user"))
        by_user.setdefault(ref_id(slot.get("user")), []).append(slot)

    if not by_user:
        print(
            "No timeslots between {} and {} for the selected scope.".format(
                today, horizon
            )
        )
        return

    print(
        "Schedule from {} to {} ({} day window):".format(today, horizon, args.days)
    )
    for user_id in sorted(by_user, key=lambda uid: names[uid]):
        slots = sorted(by_user[user_id], key=lambda s: s.get("start") or "")
        for slot in slots:
            slot["engagement"] = _engagement(slot)
        print("\n== {} ==".format(names[user_id]))
        print_table(slots, COLUMNS)


if __name__ == "__main__":
    try:
        main()
    except ChaoticaClientError as exc:
        die(str(exc))
