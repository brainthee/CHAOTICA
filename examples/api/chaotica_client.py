"""Shared helpers for the CHAOTICA `/api/v1/` example scripts.

This module is the one piece of reused code every example imports. It has no
dependencies beyond `requests` and provides:

* ``load_dotenv()``      -- a minimal `.env` loader (no python-dotenv).
* ``ChaoticaClient``     -- an authenticated session with GET + pagination.
* ``print_table()``      -- aligned plain-text tables (no tabulate).
* ``resolve_user_names`` -- best-effort ``{id: "First Last"}`` map.

Configuration is read entirely from environment variables so the scripts run
against any instance without editing code. See ``.env.example`` for the full
list.
"""

import os
import sys

try:
    import requests
except ImportError:  # pragma: no cover - guidance for a fresh checkout
    sys.exit(
        "The 'requests' package is required.\n"
        "Install it with:  pip install -r requirements.txt"
    )


# ---------------------------------------------------------------------------
# .env loading
# ---------------------------------------------------------------------------


def load_dotenv():
    """Populate ``os.environ`` from a ``.env`` file, without overriding.

    Looks in the current working directory first, then next to the scripts
    (this module's directory). Real environment variables always win --
    ``os.environ.setdefault`` never clobbers a value that is already set. Lines
    that are blank or start with ``#`` are ignored; everything else is split on
    the first ``=``.
    """
    seen = set()
    for directory in (os.getcwd(), os.path.dirname(os.path.abspath(__file__))):
        path = os.path.join(directory, ".env")
        if path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        with open(path, "r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)


def _env_bool(name, default=True):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in ("0", "false", "no", "off", "")


def normalise_base_url(url):
    """Return a base URL that ends in ``/api/v1`` (no trailing slash).

    A trailing slash is tolerated and a bare host has ``/api/v1`` appended, so
    all of these resolve to the same place::

        https://host            -> https://host/api/v1
        https://host/           -> https://host/api/v1
        https://host/api/v1     -> https://host/api/v1
        https://host/api/v1/    -> https://host/api/v1
    """
    url = url.strip().rstrip("/")
    if not url.endswith("/api/v1"):
        url = url + "/api/v1"
    return url


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------


class ChaoticaClientError(Exception):
    """Raised for configuration or HTTP problems, with a friendly message."""


class ChaoticaClient:
    """Thin authenticated wrapper over the read-only ``/api/v1/`` API."""

    def __init__(self, base_url, token, verify_ssl=True, page_size=None):
        self.base_url = normalise_base_url(base_url)
        self.page_size = page_size
        self.session = requests.Session()
        self.session.verify = verify_ssl
        if token:
            self.session.headers["Authorization"] = "Token " + token
        self.session.headers["Accept"] = "application/json"

    @classmethod
    def from_env(cls, require_token=True):
        """Build a client from the environment (loading ``.env`` first)."""
        load_dotenv()

        base_url = os.environ.get("CHAOTICA_API_URL")
        if not base_url:
            raise ChaoticaClientError(
                "CHAOTICA_API_URL is not set.\n"
                "Set it to your instance API, e.g. "
                "http://localhost:8000/api/v1\n"
                "(copy .env.example to .env, or export the variable)."
            )

        token = os.environ.get("CHAOTICA_API_TOKEN")
        if require_token and not token:
            raise ChaoticaClientError(
                "CHAOTICA_API_TOKEN is not set.\n"
                "Obtain one with:  python get_token.py\n"
                "or on the server:  cd app && python manage.py "
                "drf_create_token <your-email>"
            )

        page_size = os.environ.get("CHAOTICA_PAGE_SIZE")
        if page_size:
            try:
                page_size = int(page_size)
            except ValueError:
                raise ChaoticaClientError(
                    "CHAOTICA_PAGE_SIZE must be an integer, got: "
                    + repr(page_size)
                )
        else:
            page_size = None

        return cls(
            base_url=base_url,
            token=token,
            verify_ssl=_env_bool("CHAOTICA_VERIFY_SSL", default=True),
            page_size=page_size,
        )

    # -- request plumbing ---------------------------------------------------

    def _url(self, resource):
        return self.base_url + "/" + resource.strip("/") + "/"

    def _request(self, url, params=None):
        try:
            response = self.session.get(url, params=params)
        except requests.exceptions.SSLError as exc:
            raise ChaoticaClientError(
                "TLS certificate verification failed: {}\n"
                "For a self-signed dev instance set CHAOTICA_VERIFY_SSL=false."
                .format(exc)
            )
        except requests.exceptions.RequestException as exc:
            raise ChaoticaClientError("Could not reach the API: {}".format(exc))

        if response.status_code in (401, 403):
            raise ChaoticaClientError(
                "Authentication/permission error ({}) for {}\n"
                "- Check CHAOTICA_API_TOKEN is set and valid "
                "(re-issue with get_token.py).\n"
                "- Results are permission-scoped: your token's user may simply "
                "not be allowed to see this resource.".format(
                    response.status_code, url
                )
            )
        if not response.ok:
            snippet = response.text[:300].replace("\n", " ")
            raise ChaoticaClientError(
                "API returned HTTP {} for {}\n{}".format(
                    response.status_code, url, snippet
                )
            )

        try:
            return response.json()
        except ValueError:
            raise ChaoticaClientError(
                "Expected JSON but got a non-JSON response from {}.\n"
                "Is CHAOTICA_API_URL pointing at the /api/v1 base?".format(url)
            )

    def get(self, resource, **params):
        """GET a single resource (or one page) and return parsed JSON."""
        if self.page_size and "page_size" not in params:
            params["page_size"] = self.page_size
        return self._request(self._url(resource), params=params or None)

    def iterate(self, resource, **params):
        """Yield every result row for a list resource, following ``next``.

        This is the key pattern consumers must adopt: the API paginates, so you
        keep following the ``next`` link until it is null. ``CHAOTICA_PAGE_SIZE``
        (if set) controls the page size.
        """
        if self.page_size and "page_size" not in params:
            params["page_size"] = self.page_size

        url = self._url(resource)
        first = True
        while url:
            # params only apply to the first request; `next` already encodes them.
            payload = self._request(url, params=params if first else None)
            first = False
            if isinstance(payload, dict) and "results" in payload:
                for row in payload["results"]:
                    yield row
                url = payload.get("next")
            else:
                # Defensive: a non-paginated list response.
                if isinstance(payload, list):
                    for row in payload:
                        yield row
                url = None


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def print_table(rows, columns):
    """Print ``rows`` (list of dicts) as an aligned plain-text table.

    ``columns`` is a list of ``(key, heading)`` pairs. Missing values render as
    an empty string.
    """
    keys = [key for key, _ in columns]
    headings = [heading for _, heading in columns]

    cells = []
    for row in rows:
        cells.append(["" if row.get(k) is None else str(row.get(k)) for k in keys])

    widths = [len(h) for h in headings]
    for cell_row in cells:
        for i, value in enumerate(cell_row):
            widths[i] = max(widths[i], len(value))

    def fmt(values):
        return "  ".join(v.ljust(widths[i]) for i, v in enumerate(values))

    print(fmt(headings))
    print(fmt(["-" * w for w in widths]))
    for cell_row in cells:
        print(fmt(cell_row))

    print("\n{} row(s).".format(len(rows)))


def resolve_user_names(client):
    """Return a best-effort ``{user_id: "First Last"}`` map from ``/users/``.

    Users are permission-scoped, so this only covers users your token can see;
    callers should fall back to ``user #<id>`` for anyone missing. Never raises
    on a permission error -- an empty map is a valid (if unhelpful) result.
    """
    names = {}
    try:
        for user in client.iterate("users"):
            full = "{} {}".format(
                user.get("first_name") or "", user.get("last_name") or ""
            ).strip()
            names[user["id"]] = full or user.get("email") or "user #{}".format(
                user["id"]
            )
    except ChaoticaClientError:
        # Best-effort only: fall back to raw ids at the call site.
        pass
    return names


def user_label(names, user_id):
    """Look up ``user_id`` in ``names`` with a ``user #<id>`` fallback."""
    if user_id is None:
        return "(unassigned)"
    return names.get(user_id, "user #{}".format(user_id))


def die(message):
    """Print ``message`` to stderr and exit non-zero."""
    print(message, file=sys.stderr)
    sys.exit(1)
