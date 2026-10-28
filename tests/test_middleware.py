"""Unit tests for app/middleware.py (REQ-001/T4, ADR-REQ-001 security review).

Uses throwaway apps so these tests do not depend on app/main.py wiring. Some
tests drive the ASGI callable directly to control exactly how the body is
streamed (several chunks, no Content-Length, a lying Content-Length).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import register_error_handlers
from app.middleware import (
    MAX_BODY_SIZE,
    PAYLOAD_TOO_LARGE_CODE,
    BodySizeLimitMiddleware,
)

SECRET = "my-private-medical-note-xyz"


class Payload(BaseModel):
    note: str


def make_app(**middleware_kwargs: Any) -> tuple[FastAPI, list[str]]:
    """Throwaway app wired the way T8 should wire main.py."""
    calls: list[str] = []
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware, **middleware_kwargs)
    register_error_handlers(app)

    @app.post("/items")
    def create(payload: Payload) -> dict[str, int]:
        calls.append("create")
        return {"length": len(payload.note)}

    @app.get("/items")
    def list_items() -> dict[str, str]:
        calls.append("list")
        return {"status": "ok"}

    return app, calls


def json_body_of_size(size: int, note_char: str = "a") -> bytes:
    """A valid ``{"note": "..."}`` JSON body of exactly ``size`` bytes."""
    overhead = len(json.dumps({"note": ""}).encode())
    body = json.dumps({"note": note_char * (size - overhead)}).encode()
    assert len(body) == size
    return body


def assert_413(response: Any) -> None:
    assert response.status_code == 413
    assert response.json() == {
        "error": {
            "code": PAYLOAD_TOO_LARGE_CODE,
            "message": "Request body is too large",
            "fields": [],
        }
    }


# --------------------------------------------------------------------------- raw ASGI helpers


def run_asgi(
    app: ASGIApp,
    chunks: list[bytes],
    headers: list[tuple[bytes, bytes]] | None = None,
    method: str = "POST",
    path: str = "/raw",
) -> tuple[list[Message], int]:
    """Send ``chunks`` as separate ``http.request`` messages; return sent messages
    and how many times the app called ``receive``."""
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": headers or [],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    messages: list[Message] = [
        {"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1}
        for i, chunk in enumerate(chunks)
    ] or [{"type": "http.request", "body": b"", "more_body": False}]
    pending: Iterator[Message] = iter(messages)
    sent: list[Message] = []
    receive_calls = 0

    async def receive() -> Message:
        nonlocal receive_calls
        receive_calls += 1
        return next(pending, {"type": "http.disconnect"})

    async def send(message: Message) -> None:
        sent.append(message)

    async def main() -> None:
        await app(scope, receive, send)

    anyio.run(main)
    return sent, receive_calls


def status_of(sent: list[Message]) -> int:
    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert len(starts) == 1, sent
    return starts[0]["status"]


def body_of(sent: list[Message]) -> bytes:
    return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


def reading_app(record: list[int]) -> ASGIApp:
    """Reads the whole body chunk by chunk, then answers 200 with its length."""

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        total = 0
        while True:
            message = await receive()
            total += len(message.get("body", b""))
            if not message.get("more_body", False):
                break
        record.append(total)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": str(total).encode()})

    return app


def content_length(value: int | str) -> list[tuple[bytes, bytes]]:
    return [(b"content-length", str(value).encode())]


# --------------------------------------------------------------------------- limit constant


def test_limit_is_16_kib() -> None:
    assert MAX_BODY_SIZE == 16384


# --------------------------------------------------------------------------- Content-Length path (TestClient)


def test_body_of_exactly_limit_is_accepted() -> None:
    app, calls = make_app()
    body = json_body_of_size(MAX_BODY_SIZE)
    with TestClient(app) as client:
        response = client.post(
            "/items", content=body, headers={"Content-Type": "application/json"}
        )
    assert response.status_code == 200
    assert response.json() == {"length": MAX_BODY_SIZE - len(b'{"note": ""}')}
    assert calls == ["create"]


def test_body_one_byte_over_limit_is_rejected_before_parsing() -> None:
    app, calls = make_app()
    body = json_body_of_size(MAX_BODY_SIZE + 1)
    with TestClient(app) as client:
        response = client.post(
            "/items", content=body, headers={"Content-Type": "application/json"}
        )
    assert_413(response)
    assert calls == []


def test_large_invalid_json_gets_413_not_422() -> None:
    app, calls = make_app()
    with TestClient(app) as client:
        response = client.post(
            "/items",
            content=b"{" * (MAX_BODY_SIZE * 4),
            headers={"Content-Type": "application/json"},
        )
    assert_413(response)
    assert calls == []


def test_413_never_echoes_body_content() -> None:
    app, _ = make_app()
    body = json_body_of_size(MAX_BODY_SIZE + 100, note_char="x")
    body = body.replace(b"x" * len(SECRET), SECRET.encode(), 1)
    with TestClient(app) as client:
        response = client.post(
            "/items", content=body, headers={"Content-Type": "application/json"}
        )
    assert_413(response)
    assert SECRET not in response.text


def test_small_bodies_and_bodyless_requests_pass_through() -> None:
    app, calls = make_app()
    with TestClient(app) as client:
        created = client.post("/items", json={"note": "lunch"})
        listed = client.get("/items")
    assert created.status_code == 200
    assert created.json() == {"length": 5}
    assert listed.status_code == 200
    assert calls == ["create", "list"]


def test_custom_limit() -> None:
    app, calls = make_app(max_body_size=32)
    headers = {"Content-Type": "application/json"}
    with TestClient(app) as client:
        ok = client.post("/items", content=json_body_of_size(32), headers=headers)
        too_big = client.post("/items", content=json_body_of_size(33), headers=headers)
    assert ok.status_code == 200
    assert_413(too_big)
    assert calls == ["create"]


def test_negative_limit_is_rejected() -> None:
    with pytest.raises(ValueError):
        BodySizeLimitMiddleware(reading_app([]), max_body_size=-1)


def test_lifespan_passes_through() -> None:
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        events.append("startup")
        yield
        events.append("shutdown")

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(BodySizeLimitMiddleware)
    register_error_handlers(app)

    with TestClient(app):
        pass
    assert events == ["startup", "shutdown"]


# --------------------------------------------------------------------------- Content-Length path (raw ASGI)


def test_declared_length_over_limit_rejected_without_reading_body() -> None:
    record: list[int] = []
    app = BodySizeLimitMiddleware(reading_app(record))
    sent, receive_calls = run_asgi(
        app, [b"a" * 10], headers=content_length(MAX_BODY_SIZE + 1)
    )
    assert status_of(sent) == 413
    assert json.loads(body_of(sent))["error"]["code"] == PAYLOAD_TOO_LARGE_CODE
    assert receive_calls == 0
    assert record == []


def test_huge_declared_length_rejected() -> None:
    record: list[int] = []
    app = BodySizeLimitMiddleware(reading_app(record))
    sent, receive_calls = run_asgi(app, [b"a"], headers=content_length("9" * 5000))
    assert status_of(sent) == 413
    assert receive_calls == 0
    assert record == []


def test_declared_length_with_leading_zeros_within_limit_is_accepted() -> None:
    record: list[int] = []
    app = BodySizeLimitMiddleware(reading_app(record))
    sent, _ = run_asgi(app, [b"abc"], headers=content_length("0" * 40 + "3"))
    assert status_of(sent) == 200
    assert record == [3]


@pytest.mark.parametrize("value", [b"abc", b"-1", b"+5", b"1.5", b"", b"0x10", b"5, 5"])
def test_invalid_content_length_is_400(value: bytes) -> None:
    record: list[int] = []
    app = BodySizeLimitMiddleware(reading_app(record))
    sent, receive_calls = run_asgi(app, [b"hello"], headers=[(b"content-length", value)])
    assert status_of(sent) == 400
    payload = json.loads(body_of(sent))
    assert payload["error"]["code"] == "bad_request"
    assert payload["error"] == {
        "code": "bad_request",
        "message": "Invalid Content-Length header",
        "fields": [],
    }
    assert receive_calls == 0
    assert record == []


def test_conflicting_content_length_headers_are_400() -> None:
    record: list[int] = []
    app = BodySizeLimitMiddleware(reading_app(record))
    sent, _ = run_asgi(
        app,
        [b"hello"],
        headers=[(b"content-length", b"5"), (b"Content-Length", b"6")],
    )
    assert status_of(sent) == 400
    assert record == []


def test_repeated_identical_content_length_headers_are_accepted() -> None:
    record: list[int] = []
    app = BodySizeLimitMiddleware(reading_app(record))
    sent, _ = run_asgi(
        app,
        [b"hello"],
        headers=[(b"content-length", b"5"), (b"content-length", b"5")],
    )
    assert status_of(sent) == 200
    assert record == [5]


# --------------------------------------------------------------------------- streaming path (raw ASGI)


def test_chunked_body_without_content_length_at_limit_is_accepted() -> None:
    record: list[int] = []
    app = BodySizeLimitMiddleware(reading_app(record))
    chunks = [b"a" * 4096] * 4  # exactly 16384
    sent, _ = run_asgi(app, chunks)
    assert status_of(sent) == 200
    assert body_of(sent) == b"16384"
    assert record == [MAX_BODY_SIZE]


def test_chunked_body_without_content_length_over_limit_is_rejected() -> None:
    record: list[int] = []
    app = BodySizeLimitMiddleware(reading_app(record))
    chunks = [b"a" * 4096] * 4 + [b"b"]  # 16385
    sent, receive_calls = run_asgi(app, chunks)
    assert status_of(sent) == 413
    assert json.loads(body_of(sent))["error"]["code"] == PAYLOAD_TOO_LARGE_CODE
    assert record == []
    assert receive_calls == 5


def test_streaming_stops_reading_as_soon_as_limit_is_passed() -> None:
    record: list[int] = []
    app = BodySizeLimitMiddleware(reading_app(record))
    chunks = [b"a" * 10_000] * 100  # ~1 MB, stops at the second chunk
    sent, receive_calls = run_asgi(app, chunks)
    assert status_of(sent) == 413
    assert receive_calls == 2
    assert record == []


def test_body_longer_than_declared_content_length_is_rejected() -> None:
    record: list[int] = []
    app = BodySizeLimitMiddleware(reading_app(record))
    sent, _ = run_asgi(app, [b"a" * 10_000, b"a" * 10_000], headers=content_length(10))
    assert status_of(sent) == 413
    assert record == []


def test_fastapi_chunked_body_over_limit_gets_413_not_400() -> None:
    """FastAPI turns body-read errors into a 400; the middleware replaces it."""
    app, calls = make_app()
    body = json_body_of_size(MAX_BODY_SIZE + 1)
    sent, _ = run_asgi(
        app,
        [body[:8000], body[8000:]],
        headers=[(b"content-type", b"application/json"), (b"host", b"testserver")],
        path="/items",
    )
    assert status_of(sent) == 413
    assert json.loads(body_of(sent))["error"]["code"] == PAYLOAD_TOO_LARGE_CODE
    assert calls == []


def test_streamed_413_never_echoes_body_content() -> None:
    record: list[int] = []
    app = BodySizeLimitMiddleware(reading_app(record))
    sent, _ = run_asgi(app, [SECRET.encode() * 1000])
    assert status_of(sent) == 413
    assert SECRET.encode() not in body_of(sent)
    assert all(SECRET.encode() not in v for _, v in sent[0]["headers"])


def test_app_that_swallows_the_error_and_answers_is_replaced_by_413() -> None:
    async def swallowing_app(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            while (await receive()).get("more_body", False):
                pass
        except Exception:  # noqa: BLE001 - simulates FastAPI's body-read handling
            await send({"type": "http.response.start", "status": 400, "headers": []})
            await send({"type": "http.response.body", "body": b"bad"})
            return
        raise AssertionError("body should have been cut off")  # pragma: no cover

    sent, _ = run_asgi(BodySizeLimitMiddleware(swallowing_app), [b"a" * (MAX_BODY_SIZE + 1)])
    assert status_of(sent) == 413
    assert b"bad" not in body_of(sent)


def test_response_already_started_is_not_restarted() -> None:
    async def early_answer_app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 202, "headers": []})
        while (await receive()).get("more_body", False):
            pass  # pragma: no cover - receive raises first

    sent, _ = run_asgi(
        BodySizeLimitMiddleware(early_answer_app), [b"a" * MAX_BODY_SIZE, b"a"]
    )
    assert status_of(sent) == 202  # exactly one response start, never a second one


def test_unrelated_app_errors_still_propagate() -> None:
    class Boom(RuntimeError):
        pass

    async def failing_app(scope: Scope, receive: Receive, send: Send) -> None:
        await receive()
        raise Boom

    with pytest.raises(Boom):
        run_asgi(BodySizeLimitMiddleware(failing_app), [b"small"])


def test_non_http_scopes_pass_through_untouched() -> None:
    seen: list[str] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])
        message = await receive()
        seen.append(message["type"])

    async def receive() -> Message:
        return {"type": "websocket.receive", "bytes": b"x" * (MAX_BODY_SIZE * 2)}

    async def send(message: Message) -> None:  # pragma: no cover - not called
        raise AssertionError(message)

    async def main() -> None:
        await BodySizeLimitMiddleware(inner)({"type": "websocket", "headers": []}, receive, send)

    anyio.run(main)
    assert seen == ["websocket", "websocket.receive"]


# --------------------------------------------------------------------------- ordering with the catch-all


def test_wired_before_register_error_handlers_errors_stay_enveloped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """With the T8 ordering an unhandled error still gets the generic 500."""
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware)
    register_error_handlers(app)

    @app.post("/boom")
    def boom(payload: Payload) -> None:
        raise RuntimeError(payload.note)

    caplog.set_level(logging.DEBUG)
    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.post("/boom", json={"note": SECRET})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert SECRET not in caplog.text
