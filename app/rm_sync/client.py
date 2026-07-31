"""Centralised HTTP client for the Smartsheet Resource Management (RM) API.

Historically every sync method in ``models.py`` built its own headers and made raw
``requests`` calls with no timeout, no retry/backoff, no rate-limit handling and a lot of
duplicated status-code branching. ``RMClient`` centralises all of that:

* consistent auth headers + base URL from constance,
* a timeout on every request,
* bounded retry/backoff for transient failures (5xx) and rate limiting (429, honouring
  ``Retry-After`` / ``X-RateLimit-Reset``),
* a ``paginate`` generator that follows ``paging.next`` (RM does not return a total count),
* per-run memoised lookups for leave-type ids and projects (resolving an assignment's
  ``assignable_id`` otherwise re-fetches the same project for every user), and
* a hard **read-only** guard: when ``RM_SYNC_READ_ONLY`` is set, every write verb
  (POST/PUT/DELETE) is refused. This is the belt-and-braces guarantee that a non-prod
  instance pointed at a prod RM token can never mutate prod.
"""

import logging
import time

import requests
from constance import config

logger = logging.getLogger("rm_sync")

# Verbs that mutate RM state. Refused while RM_SYNC_READ_ONLY is on.
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

DEFAULT_TIMEOUT = 30  # seconds
MAX_RETRIES = 4
BACKOFF_BASE = 1.5  # seconds; exponential
MAX_BACKOFF = 60  # cap a single sleep


class RMReadOnlyError(Exception):
    """Raised when a write is attempted while the read-only guard is active."""


class RMClient:
    """Thin wrapper around ``requests`` for the RM API.

    One instance is intended to live for the duration of a single sync run so its
    ``_leave_type_ids`` / ``_project_cache`` memoisation is scoped to that run.
    """

    def __init__(self, token=None, site=None, timeout=DEFAULT_TIMEOUT):
        self.token = token if token is not None else config.RM_SYNC_API_TOKEN
        self.site = (site if site is not None else config.RM_SYNC_API_SITE).rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        # Per-run caches
        self._leave_types = None
        self._project_cache = {}

    # ------------------------------------------------------------------ helpers
    @property
    def read_only(self):
        return bool(config.RM_SYNC_READ_ONLY)

    def _headers(self):
        return {
            "Content-Type": "application/json; charset=utf-8",
            "auth": self.token,
        }

    def _url(self, path):
        if path.startswith("http"):
            return path
        return "{}/{}".format(self.site, path.lstrip("/"))

    def _sleep_for_rate_limit(self, response, attempt):
        """Return how long to sleep before a retry.

        Honour ``Retry-After`` (seconds) or ``X-RateLimit-Reset`` (epoch) when present,
        otherwise fall back to exponential backoff.
        """
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), MAX_BACKOFF)
            except ValueError:
                pass
        reset = response.headers.get("X-RateLimit-Reset")
        if reset:
            try:
                delta = float(reset) - time.time()
                if delta > 0:
                    return min(delta, MAX_BACKOFF)
            except ValueError:
                pass
        return min(BACKOFF_BASE * (2**attempt), MAX_BACKOFF)

    # ------------------------------------------------------------------ core request
    def request(self, method, path, *, params=None, json=None):
        """Make a single request with retry/backoff.

        Returns the ``requests.Response`` (callers inspect ``status_code``). Raises
        ``RMReadOnlyError`` for write verbs while the read-only guard is active, and
        ``requests.RequestException`` if all retries are exhausted on a transport error.
        """
        method = method.upper()
        if method in WRITE_METHODS and self.read_only:
            logger.warning("RM_SYNC_READ_ONLY is on — refusing %s %s", method, path)
            raise RMReadOnlyError(
                "Refusing {} {} while RM_SYNC_READ_ONLY is enabled".format(method, path)
            )

        url = self._url(path)
        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.request(
                    method,
                    url,
                    headers=self._headers(),
                    params=params,
                    json=json,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_exc = exc
                sleep = min(BACKOFF_BASE * (2**attempt), MAX_BACKOFF)
                logger.warning(
                    "RM request %s %s failed (%s); retry %d/%d in %.1fs",
                    method,
                    url,
                    exc,
                    attempt + 1,
                    MAX_RETRIES,
                    sleep,
                )
                time.sleep(sleep)
                continue

            # Rate limited or transient server error → back off and retry
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt < MAX_RETRIES - 1:
                    sleep = self._sleep_for_rate_limit(response, attempt)
                    logger.warning(
                        "RM %s %s returned %d; retry %d/%d in %.1fs",
                        method,
                        url,
                        response.status_code,
                        attempt + 1,
                        MAX_RETRIES,
                        sleep,
                    )
                    time.sleep(sleep)
                    continue
            return response

        # Exhausted retries on transport errors
        raise (
            last_exc
            if last_exc
            else requests.RequestException(
                "RM request {} {} failed after {} retries".format(
                    method, url, MAX_RETRIES
                )
            )
        )

    # ------------------------------------------------------------------ verbs
    def get(self, path, params=None):
        return self.request("GET", path, params=params)

    def post(self, path, json=None, params=None):
        return self.request("POST", path, params=params, json=json)

    def put(self, path, json=None, params=None):
        return self.request("PUT", path, params=params, json=json)

    def delete(self, path, params=None):
        return self.request("DELETE", path, params=params)

    # ------------------------------------------------------------------ pagination
    def paginate(self, path, params=None):
        """Yield each item across all pages, following ``paging.next``.

        RM returns ``{"data": [...], "paging": {"next": <url|null>, ...}}`` and does not
        populate a total ``count``, so we follow ``next`` until it is null or a page comes
        back empty.
        """
        params = dict(params or {})
        params.setdefault("per_page", 200)
        next_path = path
        next_params = params
        while next_path:
            response = self.get(next_path, params=next_params)
            if response.status_code != 200:
                logger.warning(
                    "RM paginate %s returned %d; stopping",
                    next_path,
                    response.status_code,
                )
                return
            body = response.json()
            data = body.get("data", [])
            if not data:
                return
            for item in data:
                yield item
            paging = body.get("paging") or {}
            next_path = paging.get("next")
            # ``next`` is a fully-qualified path incl. query string; don't re-apply params
            next_params = None

    # ------------------------------------------------------------------ cached lookups
    def leave_types(self):
        """List of ``{id, name}`` leave types (memoised for this client's lifetime)."""
        if self._leave_types is None:
            self._leave_types = list(
                self.paginate("/api/v1/leave_types", {"per_page": 100})
            )
        return self._leave_types

    def leave_type_ids(self):
        """Set of RM leave-type ids (derived from the memoised list)."""
        return {lt["id"] for lt in self.leave_types()}

    def get_project(self, project_id):
        """Fetch a project by id, memoised. Returns the dict or ``None`` on 404/error."""
        if project_id in self._project_cache:
            return self._project_cache[project_id]
        response = self.get("/api/v1/projects/{}".format(project_id))
        project = response.json() if response.status_code == 200 else None
        self._project_cache[project_id] = project
        return project
