"""Request body size limit (REQ-001/T4, ADR-REQ-001 security review, OWASP A04).

Starlette reads the whole request body and FastAPI parses the JSON before any
Pydantic length check runs, so an unbounded body costs memory and CPU.
``BodySizeLimitMiddleware`` rejects any body larger than ``MAX_BODY_SIZE``
(16 KiB; the largest valid expense body is about 2.5 KB) *before* it reaches
JSON parsing:

1. ``Content-Length`` check. A declared length above the limit gets a 413
   without calling the app or reading the body. A malformed ``Content-Length``
   (not ASCII digits, or several headers that disagree) gets a 400.
2. Byte counting while streaming. ``receive`` is wrapped and every
   ``http.request`` chunk is counted, so chunked bodies (no
   ``Content-Length``) and bodies longer than their declared length are cut
   off as soon as the running total passes the limit. Nothing is buffered.

When the streamed total passes the limit the wrapped ``receive`` raises
``BodyTooLargeError``. Whatever the app does with that exception (FastAPI turns
body-read errors into a 400, for example), any response it tries to send is
dropped and a 413 is sent instead, provided the app had not already started
its response. Bodies of exactly ``MAX_BODY_SIZE`` bytes are accepted.

Responses use the Q10 envelope from ``app.errors`` with fixed messages; body
content is never echoed or logged.

Mounting (T8, ``app/main.py``)
------------------------------
Starlette's ``add_middleware`` inserts at the front of the stack, so the
middleware added *last* is the *outermost*. ``register_error_handlers`` adds
``CatchAllMiddleware``, which must wrap every other middleware so an unhandled
exception anywhere is turned into a generic 500 without a traceback being
logged. Add this middleware (and ``TrustedHostMiddleware``) *before* calling
``register_error_handlers``::

    app = FastAPI(...)
    app.add_middleware(BodySizeLimitMiddleware)          # innermost of the three
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[...])
    register_error_handlers(app)                         # adds CatchAllMiddleware last
    app.include_router(...)

Resulting order: ServerErrorMiddleware -> CatchAllMiddleware ->
TrustedHostMiddleware -> BodySizeLimitMiddleware -> ExceptionMiddleware ->
router. Requests for disallowed hosts are rejected before any body is read.
"""

from __future__ import annotations

from collections.abc import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import code_for_status, error_response

MAX_BODY_SIZE = 16 * 1024  # 16 KiB

PAYLOAD_TOO_LARGE_STATUS = 413
PAYLOAD_TOO_LARGE_CODE = "payload_too_large"
PAYLOAD_TOO_LARGE_MESSAGE = "Request body is too large"
INVALID_CONTENT_LENGTH_STATUS = 400
INVALID_CONTENT_LENGTH_MESSAGE = "Invalid Content-Length header"

_CONTENT_LENGTH = b"content-length"


class BodyTooLargeError(Exception):
    """Raised by the wrapped ``receive`` once the body passes the limit."""


class _InvalidContentLength(Exception):
    pass


def _declared_length(headers: Iterable[tuple[bytes, bytes]], limit: int) -> int | None:
    """Return the declared ``Content-Length``, or ``None`` if there is none.

    Raises ``_InvalidContentLength`` for anything but ASCII digits or for
    several headers that disagree. Values with more digits than the limit are
    returned as ``limit + 1`` so huge numbers are never converted.
    """
    values = {value.strip() for name, value in headers if name.lower() == _CONTENT_LENGTH}
    if not values:
        return None
    if len(values) > 1:
        raise _InvalidContentLength
    (value,) = values
    if not value or not value.isdigit():
        raise _InvalidContentLength
    if len(value.lstrip(b"0")) > len(str(limit)):
        return limit + 1
    return int(value)


async def payload_too_large(scope: Scope, receive: Receive, send: Send) -> None:
    response = error_response(
        PAYLOAD_TOO_LARGE_STATUS,
        PAYLOAD_TOO_LARGE_CODE,
        PAYLOAD_TOO_LARGE_MESSAGE,
        headers={"Connection": "close"},
    )
    await response(scope, receive, send)


async def _invalid_content_length(scope: Scope, receive: Receive, send: Send) -> None:
    response = error_response(
        INVALID_CONTENT_LENGTH_STATUS,
        code_for_status(INVALID_CONTENT_LENGTH_STATUS),
        INVALID_CONTENT_LENGTH_MESSAGE,
        headers={"Connection": "close"},
    )
    await response(scope, receive, send)


class BodySizeLimitMiddleware:
    """Pure ASGI middleware that rejects HTTP request bodies over ``max_body_size``."""

    def __init__(self, app: ASGIApp, max_body_size: int = MAX_BODY_SIZE) -> None:
        if max_body_size < 0:
            raise ValueError("max_body_size must not be negative")
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self.max_body_size
        try:
            declared = _declared_length(scope.get("headers") or (), limit)
        except _InvalidContentLength:
            await _invalid_content_length(scope, receive, send)
            return
        if declared is not None and declared > limit:
            await payload_too_large(scope, receive, send)
            return

        received = 0
        exceeded = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            if exceeded:
                raise BodyTooLargeError
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise BodyTooLargeError
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if exceeded and not response_started:
                # The app is answering a body it could not read in full
                # (e.g. FastAPI's 400); the 413 below replaces it.
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not exceeded:
                raise
            # The exception came from (or was caused by) the body limit; it is
            # answered with a 413 below and must not reach the error logger.

        if exceeded and not response_started:
            await payload_too_large(scope, receive, send)
