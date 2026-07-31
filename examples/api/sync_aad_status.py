#!/usr/bin/env python3
"""Reconcile CHAOTICA account status against Azure AD / Entra ID.

For every user CHAOTICA knows about, this asks Azure AD (via the ``az`` CLI)
whether the account still exists and is enabled, then -- optionally -- brings
the CHAOTICA ``is_active`` flag into line by calling the write endpoint
``POST /api/v1/users/{id}/set-status/``.

The desired state for each user is derived from AAD:

    * present in AAD and ``accountEnabled`` == true   -> should be ACTIVE
    * present but disabled, or absent from AAD         -> should be INACTIVE

Safety first -- this is destructive, so it is **dry-run by default**:

    python sync_aad_status.py                 # report mismatches, change nothing
    python sync_aad_status.py --apply         # apply DEACTIVATIONS only
    python sync_aad_status.py --apply --reactivate   # also re-enable accounts
    python sync_aad_status.py --user jane@example.com # a single user
    python sync_aad_status.py --workers 16           # more concurrent AAD lookups

The AAD lookups (one ``az`` call per user) are the slow part and are run
concurrently -- tune with ``--workers`` (default 8; drop to 1 if you hit Graph
throttling).

Prerequisites:
    * The Azure CLI (``az``) installed and logged in (``az login``) with rights
      to read users (Directory Readers / User.Read.All).
    * A CHAOTICA token whose account holds ``manage_user`` (needed to write) and
      ``view_user`` (to enumerate the users to check). See get_token.py.

Only users your token can *see* are considered, and only an account with
``manage_user`` can actually change status -- the API enforces both.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from chaotica_client import (
    ChaoticaClient,
    ChaoticaClientError,
    die,
    print_table,
)


# -- Account exclusions -----------------------------------------------------

# Internal/system accounts that must never be touched regardless of AAD.
SYSTEM_EMAILS = {"deleted@chaotica.app"}

# A pragmatic "looks like a real email" check. It deliberately rejects
# placeholders that aren't addressable in AAD -- e.g. "AnonymousUser" (no @) and
# malformed values with parentheses/spaces like "damien.(us)@accenture.com".
_EMAIL_RE = re.compile(r"^[^@\s()]+@[^@\s()]+\.[^@\s()]+$")


def skip_reason(email):
    """Return why ``email`` should be skipped, or ``None`` to check it."""
    if not email:
        return "no email on record"
    if email.lower() in SYSTEM_EMAILS:
        return "system account"
    if not _EMAIL_RE.match(email):
        return "not a checkable email address"
    return None


# -- Azure AD lookup --------------------------------------------------------

# Sentinel status values returned by aad_account_state().
AAD_ENABLED = "enabled"
AAD_DISABLED = "disabled"
AAD_NOT_FOUND = "not_found"
AAD_UNKNOWN = "unknown"  # exists, but accountEnabled couldn't be read
AAD_ERROR = "error"

# We query Microsoft Graph directly via `az rest`. NOTE: `az ad user show`
# returns accountEnabled as *null* (a long-standing CLI quirk), which would make
# every user look disabled -- so we hit Graph with an explicit $select instead.
_GRAPH_USER_URL = (
    "https://graph.microsoft.com/v1.0/users/{}?$select=accountEnabled"
)


def ensure_az_available():
    """Exit early with guidance if the az CLI isn't on PATH."""
    if shutil.which("az") is None:
        die(
            "The Azure CLI ('az') was not found on your PATH.\n"
            "Install it (https://aka.ms/azure-cli) and run 'az login' first."
        )


def aad_account_state(email):
    """Return ``(state, detail)`` for ``email`` in Azure AD.

    ``state`` is one of AAD_ENABLED / AAD_DISABLED / AAD_NOT_FOUND /
    AAD_UNKNOWN / AAD_ERROR. We only ever *deactivate* on a confident
    AAD_DISABLED or AAD_NOT_FOUND; AAD_UNKNOWN (user exists but the enabled flag
    couldn't be read) and AAD_ERROR (auth/throttle/network) are never acted on,
    so we can't accidentally disable someone we simply failed to read.
    """
    url = _GRAPH_USER_URL.format(urllib.parse.quote(email, safe="@"))
    result = subprocess.run(
        ["az", "rest", "--url", url, "-o", "json"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        try:
            data = json.loads(result.stdout.strip() or "{}")
        except ValueError:
            return AAD_ERROR, "unparseable az output: " + result.stdout[:120]
        enabled = data.get("accountEnabled")
        if enabled is True:
            return AAD_ENABLED, ""
        if enabled is False:
            return AAD_DISABLED, ""
        # Present in the directory but the flag is null -> don't guess.
        return AAD_UNKNOWN, "accountEnabled not readable"

    stderr = (result.stderr or "").strip()
    lowered = stderr.lower()
    # A 404 / ResourceNotFound means the user is genuinely gone; anything else
    # (auth expired, throttling, bad request, network) must NOT read as "left".
    if (
        "resourcenotfound" in lowered
        or "does not exist" in lowered
        or "(404)" in lowered
        or " 404 " in lowered
    ):
        return AAD_NOT_FOUND, ""
    return AAD_ERROR, stderr[:200] or "az exited {}".format(result.returncode)


# -- Main -------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually change status (default is a dry run that changes nothing).",
    )
    parser.add_argument(
        "--reactivate",
        action="store_true",
        help="With --apply, also re-enable accounts that are active in AAD but "
        "inactive in CHAOTICA. Off by default so intentional deactivations "
        "aren't undone.",
    )
    parser.add_argument(
        "--user",
        help="Limit the check to a single user by email.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="How many AAD lookups to run concurrently (default 8). Each is an "
        "independent 'az' call, so this is the main speed lever. Use 1 to "
        "serialise (e.g. if you hit Graph throttling).",
    )
    args = parser.parse_args()

    ensure_az_available()
    client = ChaoticaClient.from_env()

    # Enumerate the users to check (permission-scoped by the token).
    if args.user:
        matches = list(client.iterate("users", email=args.user))
        # The email filter is a server convenience; fall back to exact match.
        users = [u for u in matches if (u.get("email") or "").lower()
                 == args.user.lower()] or matches
        if not users:
            die("No visible user with email {}.".format(args.user))
    else:
        users = list(client.iterate("users"))

    deactivations, reactivations, skipped, in_sync = [], [], [], 0

    # Split off system/unaddressable accounts (never touched) and look the rest
    # up in AAD concurrently -- the lookups are independent network calls, so a
    # small pool turns an N-round-trip serial scan into roughly N/workers.
    checkable = []
    for user in users:
        reason = skip_reason(user.get("email"))
        if reason:
            skipped.append((user.get("email") or user.get("id"), reason))
        else:
            checkable.append(user)

    workers = max(1, min(args.workers, len(checkable) or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        states = list(
            pool.map(lambda u: aad_account_state(u["email"]), checkable)
        )

    for user, (state, detail) in zip(checkable, states):
        email = user["email"]
        current_active = bool(user.get("is_active"))

        # Only ENABLED / DISABLED / NOT_FOUND are confident enough to act on.
        if state in (AAD_ERROR, AAD_UNKNOWN):
            note = "AAD lookup error: " if state == AAD_ERROR else "unknown: "
            skipped.append((email, note + detail))
            continue

        desired_active = state == AAD_ENABLED
        row = {
            "email": email,
            "chaotica": "active" if current_active else "inactive",
            "aad": {
                AAD_ENABLED: "enabled",
                AAD_DISABLED: "disabled",
                AAD_NOT_FOUND: "not found",
            }[state],
            "id": user.get("id"),
        }

        if desired_active == current_active:
            in_sync += 1
        elif current_active and not desired_active:
            row["action"] = "deactivate"
            deactivations.append(row)
        else:  # inactive in CHAOTICA, enabled in AAD
            row["action"] = "reactivate"
            reactivations.append(row)

    _report(deactivations, reactivations, skipped, in_sync)

    changes = deactivations + (reactivations if args.reactivate else [])
    if not args.apply:
        if changes:
            print(
                "\nDry run -- nothing changed. Re-run with --apply"
                + (" --reactivate" if reactivations and not args.reactivate else "")
                + " to apply."
            )
        return

    if not changes:
        print("\nNothing to apply.")
        return

    _apply(client, changes)


def _report(deactivations, reactivations, skipped, in_sync):
    print("In sync: {} user(s).".format(in_sync))

    if deactivations:
        print("\nTo DEACTIVATE (gone/disabled in AAD):")
        print_table(
            deactivations,
            columns=[("email", "Email"), ("chaotica", "CHAOTICA"), ("aad", "AAD")],
        )
    if reactivations:
        print("\nActive in AAD but INACTIVE in CHAOTICA (use --reactivate):")
        print_table(
            reactivations,
            columns=[("email", "Email"), ("chaotica", "CHAOTICA"), ("aad", "AAD")],
        )
    if skipped:
        print("\nSkipped (not evaluated):")
        for who, why in skipped:
            print("  - {}: {}".format(who, why))


def _apply(client, changes):
    print("\nApplying {} change(s)...".format(len(changes)))
    ok, failed = 0, 0
    for row in changes:
        desired_active = row["action"] == "reactivate"
        try:
            resp = client.post(
                "users/{}/set-status".format(row["id"]),
                json={"is_active": desired_active},
            )
        except ChaoticaClientError as exc:
            failed += 1
            print("  ! {} ({}): {}".format(row["email"], row["action"], exc),
                  file=sys.stderr)
            continue
        ok += 1
        state = "active" if resp.get("user", {}).get("is_active") else "inactive"
        note = "" if resp.get("changed") else " (already in state)"
        print("  - {} -> {}{}".format(row["email"], state, note))
    print("\nDone: {} applied, {} failed.".format(ok, failed))


if __name__ == "__main__":
    try:
        main()
    except ChaoticaClientError as exc:
        die(str(exc))
