#!/usr/bin/env python3
"""Qualification records lapsing within the next N days.

A compliance use case: iterates ``/api/v1/qualification-records/`` and filters on
the server-computed ``days_to_lapse`` field, sorted soonest-first.

    python qual_expiry.py --days 90

``--days`` defaults to the ``CHAOTICA_QUAL_DAYS`` env var, or 90. Records are
permission-scoped: without ``view_users_qualifications`` you only see your own and
your reports'.
"""

import argparse
import os

from chaotica_client import (
    ChaoticaClient,
    ChaoticaClientError,
    die,
    print_table,
    resolve_user_names,
    user_label,
)


COLUMNS = [
    ("qualification_name", "Qualification"),
    ("holder", "Holder"),
    ("lapse_date", "Lapses"),
    ("days_to_lapse", "Days left"),
    ("expiry_urgency", "Urgency"),
]


def main():
    default_days = int(os.environ.get("CHAOTICA_QUAL_DAYS", "90"))
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--days",
        type=int,
        default=default_days,
        help="Threshold in days (default {}).".format(default_days),
    )
    args = parser.parse_args()

    client = ChaoticaClient.from_env()
    names = resolve_user_names(client)

    matches = []
    for record in client.iterate("qualification-records"):
        days = record.get("days_to_lapse")
        if days is None or days > args.days:
            continue
        record["holder"] = user_label(names, record.get("user"))
        matches.append(record)

    matches.sort(key=lambda r: r.get("days_to_lapse"))

    print(
        "Qualification records lapsing within {} days "
        "(negative = already lapsed):\n".format(args.days)
    )
    print_table(matches, COLUMNS)


if __name__ == "__main__":
    try:
        main()
    except ChaoticaClientError as exc:
        die(str(exc))
