"""App hardening tests (REQ-001/T8, ADR-REQ-001 security review).

Covers: TrustedHost (DNS rebinding) with a Q10 400 envelope, no CORS,
``debug=False``, the 16 KiB body limit mounted on the real app, ``text/plain``
POSTs rejected with 422, a forced 500 that returns a generic envelope and logs
only the exception type and path, the ``note`` text never appearing in
response bodies or logs, middleware order, and AC-20 (title and ``/health``
unchanged).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

from app.errors import CatchAllMiddleware
from app.expenses.deps import get_store
from app.expenses.schemas import Expense, ExpenseCreate
from app.expenses.store import SqliteExpenseStore
from app.main import ALLOWED_HOSTS, HostEnvelopeMiddleware, app
from app.middleware import MAX_BODY_SIZE, BodySizeLimitMiddleware

SECRET_NOTE = "t8-private-note-do-not-leak-4f1c"

VALID: dict[str, Any] = {
    "amount": "12.50",
    "currency": "USD",
    "category": "food",
    "date": "2026-10-01",
    "note": SECRET_NOTE,
}


def assert_envelope(body: dict[str, Any], code: str) -> dict[str, Any]:
    assert set(body) == {"error"}
    error = body["error"]
    assert set(error) == {"code", "message", "fields"}
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["fields"], list)
    return error


def assert_no_secret(text: str) -> None:
    assert SECRET_NOTE not in text


# --------------------------------------------------------------------------- app config


def test_debug_is_off() -> None:
    assert app.debug is False


def test_no_cors_middleware() -> None:
    assert all(m.cls is not CORSMiddleware for m in app.user_middleware)


def test_middleware_order_catch_all_outermost() -> None:
    # user_middleware[0] is the outermost layer.
    assert [m.cls for m in app.user_middleware] == [
        CatchAllMiddleware,
        HostEnvelopeMiddleware,
        BodySizeLimitMiddleware,
    ]


def test_allowed_hosts_are_loopback_and_testserver_only() -> None:
    assert ALLOWED_HOSTS == ("localhost", "127.0.0.1", "testserver")


def test_no_cors_headers_for_cross_origin_request(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "https://evil.example"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_is_not_granted(client: TestClient) -> None:
    response = client.options(
        "/expenses",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 405
    assert "access-control-allow-origin" not in response.headers
    assert_envelope(response.json(), "method_not_allowed")


# --------------------------------------------------------------------------- AC-20


def test_ac20_health_unchanged(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ac20_title_unchanged(client: TestClient) -> None:
    assert app.title == "Expense API"
    assert client.get("/openapi.json").json()["info"]["title"] == "Expense API"


# --------------------------------------------------------------------------- trusted host


@pytest.mark.parametrize(
    "host",
    ["localhost", "localhost:8000", "127.0.0.1", "127.0.0.1:8000", "testserver", "LOCALHOST"],
)
def test_allowed_host_is_accepted(client: TestClient, host: str) -> None:
    response = client.get("/health", headers={"Host": host})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        "evil.example:8000",
        "localhost.evil.example",
        "127.0.0.1.nip.io",
        "www.localhost",
        "0.0.0.0",
        "192.168.1.10:8000",
        "",
    ],
)
def test_foreign_host_is_rejected_with_envelope(client: TestClient, host: str) -> None:
    response = client.get("/health", headers={"Host": host})
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    error = assert_envelope(response.json(), "bad_request")
    assert error["message"] == "Invalid host header"
    assert error["fields"] == []
    assert "evil" not in response.text


def test_foreign_host_cannot_list_or_create(
    client: TestClient, store: SqliteExpenseStore
) -> None:
    headers = {"Host": "evil.example"}
    get_response = client.get("/expenses", headers=headers)
    post_response = client.post("/expenses", json=VALID, headers=headers)
    assert get_response.status_code == 400
    assert post_response.status_code == 400
    assert_envelope(get_response.json(), "bad_request")
    assert_envelope(post_response.json(), "bad_request")
    assert_no_secret(post_response.text)
    assert store.list() == []


def test_foreign_host_is_checked_before_body_size(client: TestClient) -> None:
    content = b"x" * (MAX_BODY_SIZE + 1)
    response = client.post(
        "/expenses",
        content=content,
        headers={"Host": "evil.example", "Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert_envelope(response.json(), "bad_request")


def test_allowed_host_post_still_creates(client: TestClient, store: SqliteExpenseStore) -> None:
    response = client.post("/expenses", json=VALID, headers={"Host": "127.0.0.1:8000"})
    assert response.status_code == 201
    assert len(store.list()) == 1


# --------------------------------------------------------------------------- body size


def _body_of_size(size: int) -> bytes:
    payload = dict(VALID)
    base = len(json.dumps({**payload, "note": ""}).encode())
    payload["note"] = SECRET_NOTE + "a" * (size - base - len(SECRET_NOTE))
    body = json.dumps(payload).encode()
    assert len(body) == size
    return body


def test_body_over_16_kib_is_413_envelope(
    client: TestClient, store: SqliteExpenseStore, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    response = client.post(
        "/expenses",
        content=_body_of_size(MAX_BODY_SIZE + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    error = assert_envelope(response.json(), "payload_too_large")
    assert error["fields"] == []
    assert_no_secret(response.text)
    assert_no_secret(caplog.text)
    assert store.list() == []


def test_chunked_body_over_16_kib_is_413_envelope(
    client: TestClient, store: SqliteExpenseStore
) -> None:
    body = _body_of_size(MAX_BODY_SIZE * 2)

    def chunks():
        for start in range(0, len(body), 4096):
            yield body[start : start + 4096]

    response = client.post(
        "/expenses", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert_envelope(response.json(), "payload_too_large")
    assert_no_secret(response.text)
    assert store.list() == []


def test_body_at_limit_is_not_413(client: TestClient) -> None:
    # Exactly 16 KiB passes the size limit; the oversized note then fails
    # validation with 422 (not echoed).
    response = client.post(
        "/expenses",
        content=_body_of_size(MAX_BODY_SIZE),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert_envelope(response.json(), "validation_error")
    assert_no_secret(response.text)


# --------------------------------------------------------------------------- content type


@pytest.mark.parametrize(
    "content_type",
    ["text/plain", "text/plain;charset=UTF-8", "application/x-www-form-urlencoded"],
)
def test_simple_cross_site_post_is_422(
    client: TestClient,
    store: SqliteExpenseStore,
    caplog: pytest.LogCaptureFixture,
    content_type: str,
) -> None:
    caplog.set_level(logging.DEBUG)
    response = client.post(
        "/expenses",
        content=json.dumps(VALID).encode(),
        headers={"Content-Type": content_type, "Origin": "https://evil.example"},
    )
    assert response.status_code == 422
    assert_envelope(response.json(), "validation_error")
    assert "access-control-allow-origin" not in response.headers
    assert_no_secret(response.text)
    assert_no_secret(caplog.text)
    assert store.list() == []


# --------------------------------------------------------------------------- forced 500


class ExplodingStore:
    """A store whose methods raise with the submitted note in the message."""

    def add(self, payload: ExpenseCreate) -> Expense:
        raise RuntimeError(f"database exploded while saving note={payload.note!r}")

    def list(self, *args: Any, **kwargs: Any) -> list[Expense]:
        raise RuntimeError(f"database exploded {SECRET_NOTE}")


@pytest.fixture
def exploding_client(client: TestClient) -> TestClient:
    # ``client`` installs (and later removes) the get_store override; replace it.
    app.dependency_overrides[get_store] = ExplodingStore
    return client


def test_forced_500_returns_generic_envelope(
    exploding_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    response = exploding_client.post("/expenses", json=VALID)

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Internal server error", "fields": []}
    }
    assert_no_secret(response.text)
    assert "RuntimeError" not in response.text
    assert "exploded" not in response.text


def test_forced_500_logs_only_type_and_path(
    exploding_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    exploding_client.post("/expenses", json=VALID)

    assert_no_secret(caplog.text)
    assert "exploded" not in caplog.text
    assert "Traceback" not in caplog.text

    error_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(error_records) == 1
    record = error_records[0]
    assert record.name == "app.errors"
    assert record.getMessage() == "Unhandled RuntimeError on /expenses"
    assert record.exc_info is None
    assert record.exc_text is None
    assert record.stack_info is None


def test_forced_500_is_not_reraised_to_server(client: TestClient) -> None:
    # raise_server_exceptions=True (default) would re-raise anything that
    # escaped the CatchAll middleware.
    app.dependency_overrides[get_store] = ExplodingStore
    with TestClient(app, raise_server_exceptions=True) as strict_client:
        response = strict_client.post("/expenses", json=VALID)
    assert response.status_code == 500


# --------------------------------------------------------------------------- note never leaked


def test_note_absent_from_422_body_and_logs(
    client: TestClient, store: SqliteExpenseStore, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    bad_bodies = [
        {**VALID, "amount": "-1"},
        {**VALID, "note": SECRET_NOTE * 30},
        {**VALID, "note": SECRET_NOTE + "\x00"},
        {**VALID, SECRET_NOTE: SECRET_NOTE},
        {**VALID, "date": SECRET_NOTE},
    ]
    for body in bad_bodies:
        response = client.post("/expenses", json=body)
        assert response.status_code == 422
        assert_envelope(response.json(), "validation_error")
        assert_no_secret(response.text)

    malformed = client.post(
        "/expenses",
        content=b'{"note": "' + SECRET_NOTE.encode() + b'",',
        headers={"Content-Type": "application/json"},
    )
    assert malformed.status_code == 422
    assert_no_secret(malformed.text)

    assert_no_secret(caplog.text)
    assert store.list() == []


def test_note_absent_from_logs_on_success(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    response = client.post("/expenses", json=VALID)
    assert response.status_code == 201
    assert_no_secret(caplog.text)
