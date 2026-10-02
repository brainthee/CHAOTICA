"""Error handlers (400/403/404/500) that are safe under ASGI.

Under ASGI, Django renders error responses via ``response_for_exception`` with
``sync_to_async(..., thread_sensitive=False)`` — i.e. in a long-lived worker
thread pool that never sees the per-request ``close_old_connections`` signals.
Any DB connection opened while rendering an error page (the base template's
menu does permission/group queries) therefore lingers in that pool thread until
MySQL's idle timeout kills it, and the next error page rendered on the same
thread fails with ``OperationalError: (2006, 'Server has gone away')``.

These wrappers apply Django's normal connection hygiene around the stock
handlers: drop stale connections before rendering and release them after.
"""
from functools import wraps

from django.db import connections
from django.views import defaults


def _release_db_connections():
    # Mirrors django.db.close_old_connections, but never touches a connection
    # inside an atomic block (e.g. TestCase, or a request that errored mid-
    # transaction) — closing there would break the surrounding transaction.
    for conn in connections.all(initialized_only=True):
        if not conn.in_atomic_block:
            conn.close_if_unusable_or_obsolete()


def _with_fresh_db(handler):
    @wraps(handler)
    def wrapper(request, *args, **kwargs):
        _release_db_connections()
        try:
            return handler(request, *args, **kwargs)
        finally:
            _release_db_connections()

    return wrapper


bad_request = _with_fresh_db(defaults.bad_request)
permission_denied = _with_fresh_db(defaults.permission_denied)
page_not_found = _with_fresh_db(defaults.page_not_found)
server_error = _with_fresh_db(defaults.server_error)
