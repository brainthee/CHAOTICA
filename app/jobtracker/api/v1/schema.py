"""drf-spectacular preprocessing hooks for the versioned API.

``DEFAULT_SCHEMA_CLASS`` is global, so without filtering spectacular would also
introspect the legacy ``/api/`` datatables viewsets (and any other DRF views).
This hook keeps the generated schema limited to the ``/api/v1/`` surface.
"""


def exclude_non_v1_endpoints(endpoints):
    """Return only endpoints whose path is under ``/api/v1/``."""
    return [
        (path, path_regex, method, callback)
        for (path, path_regex, method, callback) in endpoints
        if path.startswith("/api/v1/")
    ]
