"""Unit tests for app/errors.py (REQ-001/T2, AC-3, Q10, Q14, ADR security review).

Uses a throwaway FastAPI app so these tests do not depend on app/main.py wiring.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, field_validator

from app.errors import (
    MAX_FIELD_LENGTH,
    ApiException,
    FieldError,
    build_envelope,
    code_for_status,
    field_error_from,
    field_from_loc,
    register_error_handlers,
)

SECRET = "my-private-medical-note-xyz"


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    amount: str
    note: str | None = None

    @field_validator("amount")
    @classmethod
    def _check_amount(cls, value: str) -> str:
        if value.startswith("-"):
            raise ValueError("must be greater than 0")
        return value


class SecretError(RuntimeError):
    pass


def make_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/items")
    def create_item(item: Item) -> dict[str, Any]:
        return item.model_dump()

    @app.get("/search")
    def search(from_: str = Query(alias="from")) -> dict[str, str]:
        return {"from": from_}

    @app.get("/boom")
    def boom() -> None:
        raise SecretError(f"failed with {SECRET}")

    @app.get("/teapot")
    def teapot() -> None:
        raise HTTPException(status_code=409, detail=f"conflict on {SECRET}")

    @app.get("/range")
    def range_check() -> None:
        raise ApiException(
            422,
            "validation_error",
            "Request validation failed",
            [FieldError(field="from", message="must be on or before 'to'")],
        )

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(make_app(), raise_server_exceptions=False)


def assert_envelope(response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert set(error) == {"code", "message", "fields"}
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    for item in error["fields"]:
        assert set(item) == {"field", "message"}
    return error


def fields_of(error: dict[str, Any]) -> list[str]:
    return [item["field"] for item in error["fields"]]


# --------------------------------------------------------------------------- 422


def test_missing_field_is_named_without_body_prefix(client: TestClient) -> None:
    error = assert_envelope(client.post("/items", json={}), 422, "validation_error")
    assert error["fields"] == [{"field": "amount", "message": "Field required"}]


def test_value_error_message_has_no_prefix(client: TestClient) -> None:
    error = assert_envelope(
        client.post("/items", json={"amount": "-1"}), 422, "validation_error"
    )
    assert error["fields"] == [{"field": "amount", "message": "must be greater than 0"}]


def test_wrong_type_is_rejected(client: TestClient) -> None:
    error = assert_envelope(client.post("/items", json={"amount": 5}), 422, "validation_error")
    assert fields_of(error) == ["amount"]


def test_query_param_error_strips_query_prefix(client: TestClient) -> None:
    error = assert_envelope(client.get("/search"), 422, "validation_error")
    assert fields_of(error) == ["from"]


@pytest.mark.parametrize(
    "raw_body",
    [b"", b"{", b"not json", b"[]", b'"string"', b"42", b"null"],
    ids=["empty", "truncated", "garbage", "array", "string", "number", "null"],
)
def test_bad_bodies_report_field_body(client: TestClient, raw_body: bytes) -> None:
    response = client.post(
        "/items", content=raw_body, headers={"Content-Type": "application/json"}
    )
    error = assert_envelope(response, 422, "validation_error")
    assert fields_of(error) == ["body"]


def test_unknown_field_is_reported_as_body_without_echoing_key(client: TestClient) -> None:
    secret_key = "x" * 200 + SECRET
    response = client.post(
        "/items", json={"amount": "1", secret_key: "v", "other": "w"}
    )
    error = assert_envelope(response, 422, "validation_error")
    assert error["fields"] == [{"field": "body", "message": "unknown field"}]
    assert SECRET not in response.text


def test_error_body_and_logs_never_echo_input(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    response = client.post("/items", json={"amount": "-1", "note": SECRET})

    assert_envelope(response, 422, "validation_error")
    assert SECRET not in response.text
    assert '"input"' not in response.text
    assert '"ctx"' not in response.text
    assert SECRET not in caplog.text


def test_api_exception_returns_envelope(client: TestClient) -> None:
    error = assert_envelope(client.get("/range"), 422, "validation_error")
    assert error["fields"] == [{"field": "from", "message": "must be on or before 'to'"}]


# --------------------------------------------------------------------------- other 4xx


def test_unknown_path_is_not_found_envelope(client: TestClient) -> None:
    error = assert_envelope(client.get("/no-such-path"), 404, "not_found")
    assert error["fields"] == []


def test_wrong_method_is_method_not_allowed_envelope(client: TestClient) -> None:
    response = client.delete("/items")
    error = assert_envelope(response, 405, "method_not_allowed")
    assert error["fields"] == []
    assert "POST" in response.headers.get("allow", "")


def test_http_exception_detail_is_not_echoed(client: TestClient) -> None:
    response = client.get("/teapot")
    assert_envelope(response, 409, "conflict")
    assert SECRET not in response.text


# --------------------------------------------------------------------------- 500


def test_unhandled_exception_returns_generic_500_and_logs_only_type_and_path(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    response = client.get("/boom")

    error = assert_envelope(response, 500, "internal_error")
    assert error["fields"] == []
    assert SECRET not in response.text
    assert SECRET not in caplog.text
    assert "Traceback" not in caplog.text
    records = [r for r in caplog.records if r.name == "app.errors"]
    assert len(records) == 1
    assert records[0].exc_info is None
    assert "SecretError" in records[0].getMessage()
    assert "/boom" in records[0].getMessage()


def test_unhandled_exception_is_not_reraised() -> None:
    # The catch-all middleware stops the exception, so the server never logs a
    # traceback containing the exception message.
    with TestClient(make_app(), raise_server_exceptions=True) as client:
        response = client.get("/boom")
    assert response.status_code == 500


# --------------------------------------------------------------------------- helpers


def test_field_is_capped_at_64_characters() -> None:
    assert len(field_from_loc(("body", "a" * 500))) == MAX_FIELD_LENGTH


@pytest.mark.parametrize(
    ("loc", "expected"),
    [
        (("body", "amount"), "amount"),
        (("query", "from"), "from"),
        (("body",), "body"),
        (("query",), "query"),
        (("body", "items", 0, "amount"), "items.0.amount"),
        ((), "body"),
    ],
)
def test_field_from_loc(loc: tuple[Any, ...], expected: str) -> None:
    assert field_from_loc(loc) == expected


def test_field_error_ignores_input_and_ctx() -> None:
    item = field_error_from(
        {
            "type": "string_too_long",
            "loc": ("body", "note"),
            "msg": "String should have at most 500 characters",
            "input": SECRET,
            "ctx": {"secret": SECRET},
        }
    )
    assert item == FieldError(field="note", message="String should have at most 500 characters")


def test_json_invalid_maps_to_body() -> None:
    item = field_error_from({"type": "json_invalid", "loc": ("body", 1), "msg": "JSON decode error"})
    assert item.field == "body"


def test_build_envelope_shape() -> None:
    assert build_envelope("not_found", "Not Found") == {
        "error": {"code": "not_found", "message": "Not Found", "fields": []}
    }


@pytest.mark.parametrize(
    ("status", "code"),
    [(404, "not_found"), (405, "method_not_allowed"), (413, "payload_too_large"),
     (422, "validation_error"), (418, "im_a_teapot"), (599, "http_error")],
)
def test_code_for_status(status: int, code: str) -> None:
    assert code_for_status(status) == code
