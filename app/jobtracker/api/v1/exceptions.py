"""The /api/v1/ error envelope.

    {"error": {"code": "not_found", "message": "Not found.", "fields": {...}}}

``code`` is stable and machine-readable (DRF's error code, e.g. ``not_found``,
``permission_denied``, ``not_authenticated``, ``throttled``, ``maintenance``,
``invalid``); ``message`` is for humans; ``fields`` only on validation errors.
"""

from rest_framework import exceptions
from rest_framework.views import exception_handler


def _first_message(detail):
    if isinstance(detail, dict):
        for value in detail.values():
            return _first_message(value)
        return ""
    if isinstance(detail, list):
        return _first_message(detail[0]) if detail else ""
    return str(detail)


def _first_code(codes):
    if isinstance(codes, dict):
        for value in codes.values():
            return _first_code(value)
        return None
    if isinstance(codes, list):
        return _first_code(codes[0]) if codes else None
    return codes


def v1_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    error = {}
    if isinstance(exc, exceptions.ValidationError):
        error["code"] = "invalid"
        detail = exc.detail
        if isinstance(detail, dict):
            non_field = detail.get("non_field_errors")
            error["message"] = (
                _first_message(non_field) if non_field else "Invalid input."
            )
            error["fields"] = {
                k: [str(m) for m in (v if isinstance(v, list) else [v])]
                for k, v in detail.items()
                if k != "non_field_errors"
            }
        else:
            error["message"] = _first_message(detail)
    elif isinstance(exc, exceptions.APIException):
        error["code"] = _first_code(exc.get_codes()) or exc.default_code
        error["message"] = _first_message(exc.detail)
        if isinstance(exc, exceptions.Throttled) and exc.wait is not None:
            error["retry_after"] = int(exc.wait)
    else:  # Http404 / PermissionDenied from Django
        error["code"] = (
            "not_found" if response.status_code == 404 else "permission_denied"
        )
        error["message"] = _first_message(response.data)

    response.data = {"error": error}
    return response
