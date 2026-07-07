#!/usr/bin/env python3
"""Obtain a CHAOTICA API token from a username (email) and password.

This is the one script that does *not* need a token -- it creates one. It POSTs
your credentials to ``/api/v1/auth/token/`` and prints the token plus a ready to
copy ``export`` line.

Reads ``CHAOTICA_API_URL``, ``CHAOTICA_API_USER`` and ``CHAOTICA_API_PASSWORD``
from the environment (or ``.env``). You can also pass credentials on the command
line, which overrides the env values.

Alternatively, on the server itself:
    cd app && python manage.py drf_create_token <your-email>
"""

import argparse
import getpass
import os

from chaotica_client import (
    ChaoticaClient,
    ChaoticaClientError,
    die,
    load_dotenv,
    normalise_base_url,
    _env_bool,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--user", help="Login email (defaults to CHAOTICA_API_USER)."
    )
    parser.add_argument(
        "--password",
        help="Password (defaults to CHAOTICA_API_PASSWORD; prompts if unset).",
    )
    args = parser.parse_args()

    load_dotenv()

    base_url = os.environ.get("CHAOTICA_API_URL")
    if not base_url:
        die(
            "CHAOTICA_API_URL is not set.\n"
            "Set it to your instance API, e.g. http://localhost:8000/api/v1"
        )

    user = args.user or os.environ.get("CHAOTICA_API_USER")
    if not user:
        die(
            "No username. Set CHAOTICA_API_USER or pass --user <email>."
        )

    password = args.password or os.environ.get("CHAOTICA_API_PASSWORD")
    if not password:
        password = getpass.getpass("Password for {}: ".format(user))
    if not password:
        die("No password provided.")

    # We don't have a token yet, so build a bare client and POST directly.
    client = ChaoticaClient(
        base_url=base_url,
        token=None,
        verify_ssl=_env_bool("CHAOTICA_VERIFY_SSL", default=True),
    )
    url = normalise_base_url(base_url) + "/auth/token/"

    try:
        response = client.session.post(
            url, data={"username": user, "password": password}
        )
    except Exception as exc:  # noqa: BLE001 - surface any connection issue
        die("Could not reach the API: {}".format(exc))

    if response.status_code == 400:
        die(
            "Login failed (HTTP 400): the email/password was not accepted.\n"
            "Check the credentials and that the account is active."
        )
    if not response.ok:
        die(
            "Token request failed (HTTP {}):\n{}".format(
                response.status_code, response.text[:300]
            )
        )

    try:
        token = response.json()["token"]
    except (ValueError, KeyError):
        die("Unexpected response (no token field):\n" + response.text[:300])

    print("Token: {}".format(token))
    print()
    print("# Add this to your environment (or .env):")
    print("export CHAOTICA_API_TOKEN={}".format(token))


if __name__ == "__main__":
    try:
        main()
    except ChaoticaClientError as exc:
        die(str(exc))
