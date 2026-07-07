#!/usr/bin/env python3
"""List jobs visible to your token, following pagination.

Demonstrates the core pattern: build a client from the environment and iterate a
list resource across all pages. Prints one row per job.

    python list_jobs.py

Results are permission-scoped -- you only see jobs in units where you hold the
relevant permission (or that you are on the team of).
"""

import argparse

from chaotica_client import ChaoticaClient, ChaoticaClientError, die, print_table


COLUMNS = [
    ("id", "ID"),
    ("title", "Title"),
    ("client_name", "Client"),
    ("status_display", "Status"),
    ("phase_count", "Phases"),
    ("desired_delivery_date", "Desired delivery"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args()

    client = ChaoticaClient.from_env()
    rows = list(client.iterate("jobs"))
    rows.sort(key=lambda r: r.get("id") or 0)
    print_table(rows, COLUMNS)


if __name__ == "__main__":
    try:
        main()
    except ChaoticaClientError as exc:
        die(str(exc))
