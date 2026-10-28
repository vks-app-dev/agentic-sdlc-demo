"""API tests for POST /expenses and app wiring (REQ-001/T6).

Covers AC-1, AC-2, AC-3, AC-4, AC-6, AC-7, AC-8, AC-19 and AC-20. "Nothing
stored" is checked directly against the per-test store, because the list
endpoint belongs to T7.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.expenses.store import SqliteExpenseStore
from app.main import app

VALID: dict[str, Any] = {
    "amount": "12.50",
    "currency": "USD",
    "category": "food",
    "date": "2026-10-01",
    "note": "lunch",
}

EXPENSE_KEYS = {"id", "amount", "currency", "category", "date", "note", "created_at"}
SECRET_NOTE = "my-private-medical-note-xyz"


def payload(**overrides: Any) -> dict[str, Any]:
    body = dict(VALID)
    body.update(overrides)
    return body


def post(client: TestClient, body: Any) -> Any:
    return client.post("/expenses", json=body)


def create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = post(client, payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def assert_422(response: Any, field: str | None = None) -> dict[str, Any]:
    assert response.status_code == 422, response.text
    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert set(error) == {"code", "message", "fields"}
    assert error["code"] == "validation_error"
    assert error["message"] == "Request validation failed"
    assert error["fields"], error
    for item in error["fields"]:
        assert set(item) == {"field", "message"}
        assert item["message"]
    if field is not None:
        assert field in {item["field"] for item in error["fields"]}, error["fields"]
    assert '"input"' not in response.text
    assert '"ctx"' not in response.text
    return error


def assert_nothing_stored(store: SqliteExpenseStore) -> None:
    assert store.list() == []


# --------------------------------------------------------------------------- AC-1


def test_create_returns_201_with_stored_values(
    client: TestClient, store: SqliteExpenseStore
) -> None:
    response = post(client, VALID)

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == EXPENSE_KEYS
    assert uuid.UUID(body["id"]).version == 4
    assert body["amount"] == "12.50"
    assert body["currency"] == "USD"
    assert body["category"] == "food"
    assert body["date"] == "2026-10-01"
    assert body["note"] == "lunch"


def test_create_created_at_is_utc_iso_timestamp(client: TestClient) -> None:
    before = dt.datetime.now(dt.UTC)
    created_at = create(client)["created_at"]
    after = dt.datetime.now(dt.UTC)

    assert created_at.endswith("Z")
    parsed = dt.datetime.fromisoformat(created_at)
    assert parsed.tzinfo is not None
    assert before <= parsed <= after


def test_create_persists_to_store(client: TestClient, store: SqliteExpenseStore) -> None:
    body = create(client)

    stored = store.list()

    assert len(stored) == 1
    assert stored[0].model_dump(mode="json") == body


def test_amount_is_json_string_in_response(client: TestClient) -> None:
    assert isinstance(create(client, amount="7")["amount"], str)


def test_create_route_is_registered_at_expenses() -> None:
    operation = app.openapi()["paths"]["/expenses"]["post"]
    assert "201" in operation["responses"]


# --------------------------------------------------------------------------- AC-2


def test_create_without_note_returns_null(client: TestClient, store: SqliteExpenseStore) -> None:
    body = payload()
    del body["note"]

    response = post(client, body)

    assert response.status_code == 201, response.text
    assert response.json()["note"] is None
    assert store.list()[0].note is None


@pytest.mark.parametrize("note", [None, "", "   "])
def test_null_or_blank_note_becomes_null(client: TestClient, note: Any) -> None:
    assert create(client, note=note)["note"] is None


def test_note_is_trimmed(client: TestClient) -> None:
    assert create(client, note="  lunch  ")["note"] == "lunch"


# --------------------------------------------------------------------------- AC-3


@pytest.mark.parametrize("missing", ["amount", "currency", "category", "date"])
def test_missing_required_field_is_named(
    client: TestClient, store: SqliteExpenseStore, missing: str
) -> None:
    body = payload()
    del body[missing]

    error = assert_422(post(client, body), field=missing)

    assert error["fields"] == [{"field": missing, "message": "Field required"}]
    assert_nothing_stored(store)


def test_all_required_fields_missing_are_all_reported(
    client: TestClient, store: SqliteExpenseStore
) -> None:
    error = assert_422(post(client, {}))

    assert {item["field"] for item in error["fields"]} == {
        "amount",
        "currency",
        "category",
        "date",
    }
    assert_nothing_stored(store)


@pytest.mark.parametrize("field", ["amount", "currency", "category", "date"])
def test_null_required_field_is_rejected(
    client: TestClient, store: SqliteExpenseStore, field: str
) -> None:
    assert_422(post(client, payload(**{field: None})), field=field)
    assert_nothing_stored(store)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", True),
        ("amount", ["12.50"]),
        ("currency", 840),
        ("category", 123),
        ("category", ["food"]),
        ("category", {"name": "food"}),
        ("date", 20261001),
        ("note", 5),
        ("note", False),
    ],
)
def test_wrong_json_type_is_rejected_and_named(
    client: TestClient, store: SqliteExpenseStore, field: str, value: Any
) -> None:
    assert_422(post(client, payload(**{field: value})), field=field)
    assert_nothing_stored(store)


def test_unknown_extra_field_is_rejected_without_echoing_key(
    client: TestClient, store: SqliteExpenseStore
) -> None:
    response = post(client, payload(merchant="cafe-secret-key"))

    error = assert_422(response, field="body")

    assert {"field": "body", "message": "unknown field"} in error["fields"]
    assert "merchant" not in response.text
    assert "cafe-secret-key" not in response.text
    assert_nothing_stored(store)


@pytest.mark.parametrize(
    "raw_body",
    [b"", b"{", b"not json", b"[]", b'"string"', b"42", b"null", b"true", b'[{"a": 1}]'],
    ids=["empty", "truncated", "garbage", "array", "string", "number", "null", "bool", "list"],
)
def test_empty_malformed_or_non_object_body_is_rejected(
    client: TestClient, store: SqliteExpenseStore, raw_body: bytes
) -> None:
    response = client.post(
        "/expenses", content=raw_body, headers={"Content-Type": "application/json"}
    )

    assert_422(response, field="body")
    assert_nothing_stored(store)


def test_malformed_json_does_not_echo_body(client: TestClient) -> None:
    raw = ('{"note": "' + SECRET_NOTE + '", ').encode()

    response = client.post(
        "/expenses", content=raw, headers={"Content-Type": "application/json"}
    )

    assert_422(response, field="body")
    assert SECRET_NOTE not in response.text


def test_non_json_content_type_is_rejected(
    client: TestClient, store: SqliteExpenseStore
) -> None:
    response = client.post(
        "/expenses",
        content=b'{"amount": "12.50"}',
        headers={"Content-Type": "text/plain"},
    )

    assert_422(response)
    assert_nothing_stored(store)


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": "-1"},
        {"currency": "usd"},
        {"date": "2026-02-30"},
        {"category": ""},
        {"merchant": "x"},
        {"amount": 12.5},
    ],
)
def test_note_is_never_echoed_in_422(client: TestClient, overrides: dict[str, Any]) -> None:
    response = post(client, payload(note=SECRET_NOTE, **overrides))

    assert_422(response)
    assert SECRET_NOTE not in response.text


def test_invalid_note_is_not_echoed(client: TestClient) -> None:
    long_note = SECRET_NOTE * 30  # > 500 characters

    response = post(client, payload(note=long_note))

    assert_422(response, field="note")
    assert SECRET_NOTE not in response.text


def test_wrong_method_uses_envelope(client: TestClient) -> None:
    response = client.delete("/expenses")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


# --------------------------------------------------------------------------- AC-4


@pytest.mark.parametrize(
    "amount",
    [
        "0",
        "0.00",
        "-1",
        "-0.01",
        "abc",
        "",
        "12.500",
        "0.001",
        "1e1",
        "NaN",
        "Infinity",
        " 12.50 ",
        "12,50",
        "9" * 33,
    ],
)
def test_invalid_amount_is_rejected(
    client: TestClient, store: SqliteExpenseStore, amount: str
) -> None:
    assert_422(post(client, payload(amount=amount)), field="amount")
    assert_nothing_stored(store)


@pytest.mark.parametrize("amount", [12.5, 12, 0.1])
def test_json_number_amount_is_rejected(
    client: TestClient, store: SqliteExpenseStore, amount: Any
) -> None:
    assert_422(post(client, payload(amount=amount)), field="amount")
    assert_nothing_stored(store)


@pytest.mark.parametrize(
    ("submitted", "returned"),
    [("12.5", "12.50"), ("7", "7.00"), ("0.01", "0.01"), ("9" * 32, "9" * 32 + ".00")],
)
def test_valid_amount_is_returned_with_two_decimals(
    client: TestClient, submitted: str, returned: str
) -> None:
    assert create(client, amount=submitted)["amount"] == returned


# --------------------------------------------------------------------------- AC-6


@pytest.mark.parametrize("currency", ["usd", "Usd", "US", "DOLLARS", "", "U5D", " USD", "USD "])
def test_invalid_currency_is_rejected(
    client: TestClient, store: SqliteExpenseStore, currency: str
) -> None:
    assert_422(post(client, payload(currency=currency)), field="currency")
    assert_nothing_stored(store)


def test_other_currency_is_accepted(client: TestClient) -> None:
    assert create(client, currency="EUR")["currency"] == "EUR"


# --------------------------------------------------------------------------- AC-7


@pytest.mark.parametrize(
    "date",
    [
        "2026-02-30",
        "2026-13-01",
        "10/01/2026",
        "2026-1-1",
        "2026/10/01",
        "",
        "2026-10-01T00:00:00",
        "2026-10-01T10:00:00Z",
        "2026-10-01+02:00",
        "1696118400",
        "２０２６-１０-０１",
    ],
)
def test_invalid_date_is_rejected(client: TestClient, store: SqliteExpenseStore, date: str) -> None:
    assert_422(post(client, payload(date=date)), field="date")
    assert_nothing_stored(store)


@pytest.mark.parametrize("date", ["2099-12-31", "2028-02-29"])
def test_future_and_leap_dates_are_accepted(client: TestClient, date: str) -> None:
    assert create(client, date=date)["date"] == date


# --------------------------------------------------------------------------- AC-8


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("category", ""),
        ("category", "   "),
        ("category", "x" * 51),
        ("category", "  " + "x" * 51 + "  "),
        ("category", "fo\x00od"),
        ("note", "n" * 501),
        ("note", "lu\x07nch"),
    ],
    ids=[
        "empty-category",
        "blank-category",
        "long-category",
        "long-padded-category",
        "control-category",
        "long-note",
        "control-note",
    ],
)
def test_invalid_category_or_note_is_rejected(
    client: TestClient, store: SqliteExpenseStore, field: str, value: str
) -> None:
    assert_422(post(client, payload(**{field: value})), field=field)
    assert_nothing_stored(store)


def test_category_and_note_at_max_length_are_accepted(client: TestClient) -> None:
    body = create(client, category="c" * 50, note="n" * 500)

    assert body["category"] == "c" * 50
    assert body["note"] == "n" * 500


def test_category_is_trimmed_and_case_kept(client: TestClient) -> None:
    assert create(client, category="  Food  ")["category"] == "Food"
    assert create(client, category="  " + "c" * 50 + "  ")["category"] == "c" * 50


# --------------------------------------------------------------------------- AC-19


def test_duplicate_create_gets_new_id_and_both_are_stored(
    client: TestClient, store: SqliteExpenseStore
) -> None:
    first = post(client, VALID)
    second = post(client, VALID)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert {e.id for e in store.list()} == {first.json()["id"], second.json()["id"]}


# --------------------------------------------------------------------------- AC-20


def test_health_is_unchanged(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_title_is_unchanged(client: TestClient) -> None:
    assert client.app.title == "Expense API"
    assert client.get("/openapi.json").json()["info"]["title"] == "Expense API"


def test_unknown_path_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/no-such-path")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not Found", "fields": []}
    }


def test_client_fixture_isolates_database(client: TestClient, store, tmp_path) -> None:
    create(client)

    assert store.db_path == str(tmp_path / "expenses.db")
    assert len(store.list()) == 1
