"""FastAPI application (REQ-001, ADR-REQ-001).

Hardening from the ADR security review (T8):

- ``debug=False``, so no tracebacks are ever rendered into responses.
- No ``CORSMiddleware``: browsers on other origins get no CORS grant.
- ``TrustedHostMiddleware`` limits the ``Host`` header to loopback names, which
  stops DNS-rebinding pages from reading the API as same-origin. Its rejection
  is answered with a 400 in the Q10 envelope (``HostEnvelopeMiddleware``)
  because Q10 requires one error shape for every 4xx.
- ``BodySizeLimitMiddleware`` rejects bodies over 16 KiB before JSON parsing.

The API has no authentication: serve it on 127.0.0.1 only (see README.md).
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import code_for_status, error_response, register_error_handlers
from app.expenses import router as expenses_router
from app.middleware import BodySizeLimitMiddleware

ALLOWED_HOSTS: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")

INVALID_HOST_STATUS = 400
INVALID_HOST_MESSAGE = "Invalid host header"

# Per-request scope key set once Starlette's host check has passed.
_HOST_ACCEPTED = "app.trusted_host_accepted"


class HostEnvelopeMiddleware:
    """Starlette's ``TrustedHostMiddleware`` with a Q10 envelope on rejection.

    The host check itself is delegated to ``TrustedHostMiddleware`` (with
    ``www_redirect=False``, so it either passes the request on or rejects it).
    The request counts as accepted only if the check called the wrapped app;
    otherwise its plain-text 400 is dropped and a 400 envelope is sent instead.
    Responses from the wrapped app are never touched.
    """

    def __init__(self, app: ASGIApp, allowed_hosts: Sequence[str]) -> None:
        self.app = app
        self.checker = TrustedHostMiddleware(
            self._accepted, allowed_hosts=list(allowed_hosts), www_redirect=False
        )

    async def _accepted(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope[_HOST_ACCEPTED] = True
        await self.app(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.checker(scope, receive, send)
            return

        async def rejecting_send(message: Message) -> None:
            if scope.get(_HOST_ACCEPTED):
                await send(message)
            # Otherwise this is the plain-text rejection; it is replaced below.

        await self.checker(scope, receive, rejecting_send)
        if not scope.get(_HOST_ACCEPTED):
            response = error_response(
                INVALID_HOST_STATUS,
                code_for_status(INVALID_HOST_STATUS),
                INVALID_HOST_MESSAGE,
            )
            await response(scope, receive, send)


app = FastAPI(title="Expense API", debug=False)

app.include_router(expenses_router)

# Middleware order: add_middleware inserts at the front of the stack, so the
# last one added is outermost. CatchAllMiddleware (added by
# register_error_handlers) must stay outermost, so the resulting order is
# CatchAll -> HostEnvelope (TrustedHost) -> BodySizeLimit -> router: foreign
# hosts are rejected before any body is read.
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(HostEnvelopeMiddleware, allowed_hosts=ALLOWED_HOSTS)
register_error_handlers(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
