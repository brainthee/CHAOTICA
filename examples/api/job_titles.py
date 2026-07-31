#!/usr/bin/env python3
"""List every visible user's job title and current job level.

Pulls ``/api/v1/users/`` and prints each user's free-text ``job_title`` plus
their current job level (short label + long description). The level comes from
the ``UserJobLevel`` history on the server -- the record flagged
``is_current=True`` -- exposed on the user serializer as ``job_level`` /
``job_level_label``.

    python job_titles.py                 # everyone your token can see
    python job_titles.py --active-only   # skip deactivated accounts
    python job_titles.py --by-level      # group the output by job level

Results are permission-scoped: you only see users your token's account is
allowed to view (the ``view_user`` guardian permission).
"""

import argparse

from chaotica_client import (
    ChaoticaClient,
    ChaoticaClientError,
    die,
    print_table,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Only include users whose account is active.",
    )
    parser.add_argument(
        "--by-level",
        action="store_true",
        help="Group the listing by job level instead of one flat table.",
    )
    args = parser.parse_args()

    client = ChaoticaClient.from_env()

    users = []
    for user in client.iterate("users"):
        if args.active_only and not user.get("is_active"):
            continue
        full = "{} {}".format(
            user.get("first_name") or "", user.get("last_name") or ""
        ).strip()
        users.append(
            {
                "name": full or user.get("email") or "user #{}".format(user["id"]),
                "email": user.get("email") or "",
                "job_title": user.get("job_title") or "",
                "level": user.get("job_level") or "",
                "level_label": user.get("job_level_label") or "",
                "active": "yes" if user.get("is_active") else "no",
            }
        )

    if not users:
        print("No users visible to your token.")
        return

    if args.by_level:
        # Group by the short level label; unset levels sort last under "(none)".
        groups = {}
        for u in users:
            groups.setdefault(u["level"] or "(none)", []).append(u)
        for level in sorted(groups, key=lambda lvl: (lvl == "(none)", lvl)):
            members = groups[level]
            label = members[0]["level_label"]
            heading = level if not label else "{} - {}".format(level, label)
            print("\n### {}  ({} user(s))".format(heading, len(members)))
            for u in sorted(members, key=lambda r: r["name"].lower()):
                print(
                    "  - {:<28} {}".format(
                        u["name"], u["job_title"] or "(no job title)"
                    )
                )
        print("\n{} user(s).".format(len(users)))
        return

    print_table(
        sorted(users, key=lambda r: r["name"].lower()),
        columns=[
            ("name", "Name"),
            ("email", "Email"),
            ("job_title", "Job Title"),
            ("level", "Level"),
            ("level_label", "Level Description"),
            ("active", "Active"),
        ],
    )


if __name__ == "__main__":
    try:
        main()
    except ChaoticaClientError as exc:
        die(str(exc))
