#!/usr/bin/env python3
"""Who holds which skill, and at what rating.

Demonstrates joining two resources client-side: it pulls ``/api/v1/skills/`` (for
skill names/categories) and ``/api/v1/user-skills/`` (per-user competency), plus a
user-name map, then prints a grouped list of holders per skill.

    python skills_matrix.py

User-skill data is sensitive and permission-scoped: without the
``view_users_skill`` permission you only see your own and your reports' records.
"""

import argparse

from chaotica_client import (
    ChaoticaClient,
    ChaoticaClientError,
    die,
    resolve_user_names,
    user_label,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args()

    client = ChaoticaClient.from_env()

    # Reference data: id -> (name, category).
    skills = {}
    for skill in client.iterate("skills"):
        skills[skill["id"]] = (
            skill.get("name") or "skill #{}".format(skill["id"]),
            skill.get("category_name") or "Uncategorised",
        )

    names = resolve_user_names(client)

    # Group user-skills by skill id.
    holders = {}
    for us in client.iterate("user-skills"):
        holders.setdefault(us.get("skill"), []).append(us)

    if not holders:
        print("No user-skill records visible to your token.")
        return

    # Print grouped by category, then skill.
    def skill_sort_key(skill_id):
        name, category = skills.get(skill_id, ("skill #{}".format(skill_id), "~"))
        return (category, name)

    current_category = None
    for skill_id in sorted(holders, key=skill_sort_key):
        name, category = skills.get(
            skill_id, ("skill #{}".format(skill_id), "Unknown")
        )
        if category != current_category:
            current_category = category
            print("\n### {}".format(category))
        print("\n{}".format(name))
        for us in sorted(
            holders[skill_id],
            key=lambda r: (r.get("rating") or 0),
            reverse=True,
        ):
            print(
                "  - {:<28} {}".format(
                    user_label(names, us.get("user")),
                    us.get("rating_display") or "(no rating)",
                )
            )


if __name__ == "__main__":
    try:
        main()
    except ChaoticaClientError as exc:
        die(str(exc))
