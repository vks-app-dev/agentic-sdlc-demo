"""Q10 error envelope and exception handlers (REQ-001, ADR-REQ-001).

Every error response has one shape::

    {"error": {"code": "...", "message": "...", "fields": [{"field": "...", "message": "..."}]}}

Rules enforced here (ADR security review):

- ``fields`` is built from each validation error's ``loc``/``msg``/``type`` only.
  ``input`` and ``ctx`` are never read, so submitted values (e.g. ``note``) are
  never echoed.
- ``extra_forbidden`` errors are reported as ``field="body"`` / ``"unknown field"``
  because their ``loc`` holds a client-supplied key.
- ``field`` is capped at 64 characters.
- HTTP exception messages come from a fixed status phrase, never ``exc.detail``.
- Unhandled exceptions return a generic 500 envelope and log only the exception
  type name and the request path; never ``exc``, its message, a traceback or
  the request body.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

MAX_FIELD_LENGTH = 64
VALIDATION_ERROR_CODE = "validation_error"
VALIDATION_ERROR_MESSAGE = "Request validation failed"
INTERNAL_ERROR_CODE = "internal_error"
INTERNAL_ERROR_MESSAGE = "Internal server error"
UNKNOWN_FIELD_MESSAGE = "unknown field"
BODY_FIELD = "body"

# Leading ``loc`` segments that name where a parameter lives, not the field.
_LOC_SOURCES = frozenset({"body", "query", "path", "header", "cookie"})
# Error types whose ``loc`` tail is not a model field name.
_BODY_LEVEL_TYPES = frozenset({"json_invalid"})
_VALUE_ERROR_PREFIX = "Value error, "

_STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: VALIDATION_ERROR_CODE,
    429: "too_many_requests",
    500: INTERNAL_ERROR_CODE,
}


# --------------------------------------------------------------------------- models


class FieldError(BaseModel):
    field: str
    message: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    fields: list[FieldError] = []


class ApiError(BaseModel):
    """The Q10 error envelope."""

    error: ErrorDetail


class ApiException(Exception):
    """Raise from application code to return a Q10 envelope.

    Example: ``raise ApiException(422, "validation_error", "Request validation
    failed", [FieldError(field="from", message="must be on or before 'to'")])``.
    Never put submitted input into ``message`` or ``fields``.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        fields: Sequence[FieldError] = (),
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = list(fields)


# --------------------------------------------------------------------------- builders


def build_envelope(
    code: str, message: str, fields: Iterable[FieldError] = ()
) -> dict[str, Any]:
    """Return the Q10 envelope as a JSON-ready dict."""
    return ApiError(
        error=ErrorDetail(code=code, message=message, fields=list(fields))
    ).model_dump()


def error_response(
    status_code: int,
    code: str,
    message: str,
    fields: Iterable[FieldError] = (),
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Return a ``JSONResponse`` carrying the Q10 envelope."""
    return JSONResponse(
        status_code=status_code,
        content=build_envelope(code, message, fields),
        headers=dict(headers) if headers else None,
    )


def internal_error_response() -> JSONResponse:
    return error_response(500, INTERNAL_ERROR_CODE, INTERNAL_ERROR_MESSAGE)


def _cap(value: str) -> str:
    return value[:MAX_FIELD_LENGTH]


def field_from_loc(loc: Sequence[Any]) -> str:
    """Map a validation ``loc`` to a dotted field name without its source prefix.

    ``("body", "amount")`` -> ``"amount"``; ``("query", "from")`` -> ``"from"``;
    ``("body",)`` -> ``"body"``. Capped at ``MAX_FIELD_LENGTH`` characters.
    """
    parts = [str(part) for part in loc]
    source = BODY_FIELD
    if parts and parts[0] in _LOC_SOURCES:
        source = parts[0]
        parts = parts[1:]
    return _cap(".".join(parts) if parts else source)


def field_error_from(error: Mapping[str, Any]) -> FieldError:
    """Build one ``FieldError`` from a Pydantic/FastAPI error dict.

    Reads only ``type``, ``loc`` and ``msg``; ``input`` and ``ctx`` are ignored.
    """
    error_type = str(error.get("type", ""))
    loc = error.get("loc") or ()
    if error_type == "extra_forbidden":
        return FieldError(field=BODY_FIELD, message=UNKNOWN_FIELD_MESSAGE)
    if error_type in _BODY_LEVEL_TYPES:
        field = BODY_FIELD
    else:
        field = field_from_loc(loc)
    message = str(error.get("msg", "")) or "invalid value"
    message = message.removeprefix(_VALUE_ERROR_PREFIX)
    return FieldError(field=field, message=message)


def field_errors_from(errors: Iterable[Mapping[str, Any]]) -> list[FieldError]:
    """Build de-duplicated ``FieldError`` items, keeping first-seen order."""
    result: list[FieldError] = []
    seen: set[tuple[str, str]] = set()
    for error in errors:
        item = field_error_from(error)
        key = (item.field, item.message)
        if key not in seen:
            seen.add(key)
            result.append(item)
    if not result:
        result.append(FieldError(field=BODY_FIELD, message="invalid request"))
    return result


def code_for_status(status_code: int) -> str:
    if status_code in _STATUS_CODES:
        return _STATUS_CODES[status_code]
    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        return "http_error"
    words = "".join(c if c.isalnum() or c.isspace() else " " if c == "-" else "" for c in phrase)
    return "_".join(words.lower().split())


def message_for_status(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "HTTP error"


def _log_unhandled(exc: BaseException, path: str) -> None:
    # Only the type name and path: never exc, str(exc), a traceback or the body.
    logger.error("Unhandled %s on %s", type(exc).__name__, path)


# --------------------------------------------------------------------------- handlers


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return error_response(
        422,
        VALIDATION_ERROR_CODE,
        VALIDATION_ERROR_MESSAGE,
        field_errors_from(exc.errors()),
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    status_code = exc.status_code
    fields: list[FieldError] = []
    if status_code == 422:
        fields = [FieldError(field=BODY_FIELD, message="invalid request")]
    return error_response(
        status_code,
        code_for_status(status_code),
        message_for_status(status_code),
        fields,
        headers=getattr(exc, "headers", None),
    )


async def api_exception_handler(request: Request, exc: ApiException) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.fields)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _log_unhandled(exc, request.url.path)
    return internal_error_response()


class CatchAllMiddleware:
    """Turn unhandled exceptions into a generic 500 envelope without re-raising.

    Starlette's ``ServerErrorMiddleware`` re-raises after calling an
    ``Exception`` handler, so the server would then log the full traceback
    (whose message may contain submitted input). This middleware stops the
    exception before it gets there.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        # Catching every exception is the purpose of this catch-all (ADR security
        # review): it is logged (type + path) and answered with a generic 500.
        except Exception as exc:  # noqa: BLE001
            _log_unhandled(exc, str(scope.get("path", "")))
            if response_started:
                return
            await internal_error_response()(scope, receive, send)


def register_error_handlers(app: FastAPI) -> None:
    """Install the Q10 handlers on ``app``. Call before the app starts."""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(ApiException, api_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.add_middleware(CatchAllMiddleware)
