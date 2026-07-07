#!/usr/bin/env python3
"""Phases due for delivery (or Tech QA) within the next N days.

Iterates ``/api/v1/phases/`` and filters client-side to phases whose
``delivery_date`` or ``due_to_techqa`` falls inside the window. The API has no
server-side date filter, so this shows how to work with the engagement date
fields yourself.

    python upcoming_deliveries.py --days 60

``--days`` defaults to the ``CHAOTICA_UPCOMING_DAYS`` env var, or 30.
"""

import argparse
import datetime
import os

from chaotica_client import ChaoticaClient, ChaoticaClientError, die, print_table


COLUMNS = [
    ("job", "Job"),
    ("title", "Title"),
    ("service_name", "Service"),
    ("status_display", "Status"),
    ("delivery_date", "Delivery"),
    ("due_to_techqa", "Tech QA due"),
]


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def main():
    default_days = int(os.environ.get("CHAOTICA_UPCOMING_DAYS", "30"))
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--days",
        type=int,
        default=default_days,
        help="Window size in days (default {}).".format(default_days),
    )
    args = parser.parse_args()

    today = datetime.date.today()
    horizon = today + datetime.timedelta(days=args.days)

    client = ChaoticaClient.from_env()

    matches = []
    for phase in client.iterate("phases"):
        delivery = _parse_date(phase.get("delivery_date"))
        techqa = _parse_date(phase.get("due_to_techqa"))
        candidates = [d for d in (delivery, techqa) if d is not None]
        # Keep the phase if any relevant date lands within [today, horizon].
        if any(today <= d <= horizon for d in candidates):
            phase["_sort"] = min(candidates)
            matches.append(phase)

    matches.sort(key=lambda p: p["_sort"])

    print(
        "Phases with a delivery or Tech QA date between {} and {} "
        "({} day window):\n".format(today, horizon, args.days)
    )
    print_table(matches, COLUMNS)


if __name__ == "__main__":
    try:
        main()
    except ChaoticaClientError as exc:
        die(str(exc))
