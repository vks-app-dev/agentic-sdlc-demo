"""REQ-001 acceptance tests: record and list expenses.

Written from specs/REQ-001.md (acceptance criteria plus answered open questions)
and the API contract in docs/adr/ADR-REQ-001.md. Every test exercises the public
HTTP API only. Test names carry the AC id so QA can trace them.

Contract summary (ADR):
- POST /expenses -> 201 Expense {id, amount, currency, category, date, note, created_at}
- GET /expenses?from&to&category -> 200 {"items": [...], "total": {currency: "x.xx"}}
- Every 4xx: {"error": {"code", "message", "fields": [{"field", "message"}]}}
"""

from __future__ import annotations

import importlib
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

VALID: dict[str, Any] = {
    "amount": "12.50",
    "currency": "USD",
    "category": "food",
    "date": "2026-10-01",
    "note": "lunch",
}


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    """TestClient bound to a fresh, per-test SQLite store (Q20)."""
    db_path = tmp_path / "expenses.db"
    monkeypatch.setenv("EXPENSE_DB_PATH", str(db_path))

    # Imported lazily so that a missing module fails each test individually
    # instead of aborting collection for the whole suite (ADR module names).
    get_store = importlib.import_module("app.expenses.deps").get_store
    store_cls = importlib.import_module("app.expenses.store").SqliteExpenseStore
    app = importlib.import_module("app.main").app

    store = store_cls(str(db_path))
    app.dependency_overrides[get_store] = lambda: store
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_store, None)


# --------------------------------------------------------------------------- helpers


def payload(**overrides: Any) -> dict[str, Any]:
    body = dict(VALID)
    body.update(overrides)
    return body


def create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/expenses", json=payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def list_expenses(client: TestClient, params: Any = None) -> dict[str, Any]:
    response = client.get("/expenses", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def assert_validation_error(response, field: str | None = None) -> dict[str, Any]:
    assert response.status_code == 422, response.text
    body = response.json()
    assert set(body) == {"error"}, body
    error = body["error"]
    assert error["code"] == "validation_error"
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["fields"], list) and error["fields"]
    for item in error["fields"]:
        assert set(item) == {"field", "message"}
    if field is not None:
        assert field in {item["field"] for item in error["fields"]}, error["fields"]
    return error


def assert_store_empty(client: TestClient) -> None:
    assert list_expenses(client) == {"items": [], "total": {}}


def dates_of(listing: dict[str, Any]) -> list[str]:
    return [item["date"] for item in listing["items"]]


@pytest.fixture
def four_dated(client: TestClient) -> TestClient:
    """AC-11 / AC-12 data set."""
    for day, amount in [
        ("2026-09-30", "1.00"),
        ("2026-10-01", "2.00"),
        ("2026-10-15", "3.00"),
        ("2026-10-31", "4.00"),
    ]:
        create(client, date=day, amount=amount, note=None)
    return client


# --------------------------------------------------------------------------- AC-1


def test_ac01_create_expense_returns_201_with_stored_values(client: TestClient) -> None:
    response = client.post("/expenses", json=VALID)

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"id", "amount", "currency", "category", "date", "note", "created_at"}
    assert uuid.UUID(body["id"]).version == 4
    assert body["amount"] == "12.50"
    assert body["currency"] == "USD"
    assert body["category"] == "food"
    assert body["date"] == "2026-10-01"
    assert body["note"] == "lunch"
    assert isinstance(body["created_at"], str) and body["created_at"]


def test_ac01_created_expense_appears_in_subsequent_list(client: TestClient) -> None:
    created = create(client)

    listing = list_expenses(client)

    assert listing["items"] == [created]
    assert listing["total"] == {"USD": "12.50"}


# --------------------------------------------------------------------------- AC-2


def test_ac02_create_without_note_stores_null_note(client: TestClient) -> None:
    body = payload()
    del body["note"]

    response = client.post("/expenses", json=body)

    assert response.status_code == 201, response.text
    assert response.json()["note"] is None
    assert list_expenses(client)["items"][0]["note"] is None


@pytest.mark.parametrize("note", [None, "", "   "])
def test_ac02_null_or_empty_note_is_stored_as_null(client: TestClient, note) -> None:
    # Q11: note is trimmed; an empty note is stored and returned as null.
    assert create(client, note=note)["note"] is None


def test_ac02_note_is_trimmed(client: TestClient) -> None:
    assert create(client, note="  lunch  ")["note"] == "lunch"


# --------------------------------------------------------------------------- AC-3


@pytest.mark.parametrize("missing", ["amount", "currency", "category", "date"])
def test_ac03_missing_required_field_is_rejected_and_named(
    client: TestClient, missing: str
) -> None:
    body = payload()
    del body[missing]

    response = client.post("/expenses", json=body)

    assert_validation_error(response, field=missing)
    assert_store_empty(client)


@pytest.mark.parametrize("field", ["amount", "currency", "category", "date"])
def test_ac03_q14_explicit_null_for_required_field_is_rejected(
    client: TestClient, field: str
) -> None:
    response = client.post("/expenses", json=payload(**{field: None}))

    assert_validation_error(response, field=field)
    assert_store_empty(client)


@pytest.mark.parametrize(
    ("field", "value"),
    [("category", 123), ("currency", 840), ("date", 20261001), ("note", 5), ("category", ["food"])],
)
def test_ac03_q14_wrong_json_type_is_rejected(client: TestClient, field: str, value) -> None:
    response = client.post("/expenses", json=payload(**{field: value}))

    assert_validation_error(response)
    assert_store_empty(client)


def test_ac03_q14_unknown_extra_field_is_rejected(client: TestClient) -> None:
    response = client.post("/expenses", json=payload(merchant="cafe"))

    assert_validation_error(response)
    assert_store_empty(client)


@pytest.mark.parametrize(
    "raw_body",
    [b"", b"{", b"not json", b"[]", b'"string"', b"42", b"null"],
    ids=["empty", "truncated", "garbage", "array", "string", "number", "null"],
)
def test_ac03_q14_empty_malformed_or_non_object_body_is_rejected(
    client: TestClient, raw_body: bytes
) -> None:
    response = client.post(
        "/expenses", content=raw_body, headers={"Content-Type": "application/json"}
    )

    assert_validation_error(response)
    assert_store_empty(client)


def test_ac03_q10_error_body_never_echoes_submitted_input(client: TestClient) -> None:
    secret_note = "my-private-medical-note-xyz"
    body = payload(note=secret_note, amount="-1")

    response = client.post("/expenses", json=body)

    assert_validation_error(response, field="amount")
    assert secret_note not in response.text
    assert '"input"' not in response.text


# --------------------------------------------------------------------------- AC-4


@pytest.mark.parametrize(
    "amount",
    [
        "0",
        "0.00",
        "-1",
        "-0.01",
        "-12.50",
        "abc",
        "",
        "12.500",
        "0.001",
        "1e1",
        "NaN",
        "Infinity",
        " 12.50 ",
        "12,50",
    ],
)
def test_ac04_invalid_amount_is_rejected(client: TestClient, amount: str) -> None:
    response = client.post("/expenses", json=payload(amount=amount))

    assert_validation_error(response, field="amount")
    assert_store_empty(client)


@pytest.mark.parametrize("amount", [12.5, 12, 0.1])
def test_ac04_q9_json_number_amount_is_rejected(client: TestClient, amount) -> None:
    # Q9 (a): amount is a JSON string only.
    response = client.post("/expenses", json=payload(amount=amount))

    assert_validation_error(response, field="amount")
    assert_store_empty(client)


@pytest.mark.parametrize(("submitted", "returned"), [("12.5", "12.50"), ("7", "7.00"), ("0.01", "0.01")])
def test_ac04_valid_amount_up_to_two_decimals_is_returned_with_two_decimals(
    client: TestClient, submitted: str, returned: str
) -> None:
    assert create(client, amount=submitted)["amount"] == returned


# --------------------------------------------------------------------------- AC-5


def test_ac05_amounts_and_total_are_exact(client: TestClient) -> None:
    create(client, amount="0.10", date="2026-10-02")
    create(client, amount="0.20", date="2026-10-01")

    listing = list_expenses(client)

    assert sorted(item["amount"] for item in listing["items"]) == ["0.10", "0.20"]
    assert listing["total"] == {"USD": "0.30"}


def test_ac05_large_amounts_total_exactly_and_never_500(client: TestClient) -> None:
    # Security review (H): Decimal precision must cover the 32-char amount cap.
    big = "9" * 29 + ".99"
    create(client, amount=big)
    create(client, amount=big)

    listing = list_expenses(client)

    assert listing["total"] == {"USD": "1" + "9" * 29 + ".98"}


# --------------------------------------------------------------------------- AC-6


@pytest.mark.parametrize("currency", ["usd", "Usd", "US", "DOLLARS", "", "U5D", " USD", "USD "])
def test_ac06_invalid_currency_is_rejected(client: TestClient, currency: str) -> None:
    response = client.post("/expenses", json=payload(currency=currency))

    assert_validation_error(response, field="currency")
    assert_store_empty(client)


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
def test_ac07_invalid_date_is_rejected(client: TestClient, date: str) -> None:
    response = client.post("/expenses", json=payload(date=date))

    assert_validation_error(response, field="date")
    assert_store_empty(client)


def test_ac07_q3_future_date_is_accepted(client: TestClient) -> None:
    assert create(client, date="2099-12-31")["date"] == "2099-12-31"


def test_ac07_leap_day_is_accepted(client: TestClient) -> None:
    assert create(client, date="2028-02-29")["date"] == "2028-02-29"


# --------------------------------------------------------------------------- AC-8


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("category", ""),
        ("category", "   "),
        ("category", "x" * 51),
        ("category", "  " + "x" * 51 + "  "),
        ("note", "n" * 501),
    ],
    ids=["empty-category", "blank-category", "long-category", "long-padded-category", "long-note"],
)
def test_ac08_invalid_category_or_note_is_rejected(
    client: TestClient, field: str, value: str
) -> None:
    response = client.post("/expenses", json=payload(**{field: value}))

    assert_validation_error(response, field=field)
    assert_store_empty(client)


def test_ac08_category_and_note_at_max_length_are_accepted(client: TestClient) -> None:
    body = create(client, category="c" * 50, note="n" * 500)

    assert body["category"] == "c" * 50
    assert body["note"] == "n" * 500


def test_ac08_q11_category_is_trimmed_and_case_kept(client: TestClient) -> None:
    # Trim happens before the 1-50 length check.
    assert create(client, category="  Food  ")["category"] == "Food"
    assert create(client, category="  " + "c" * 50 + "  ")["category"] == "c" * 50


# --------------------------------------------------------------------------- AC-9


def test_ac09_list_all_with_total(client: TestClient) -> None:
    ids = {
        create(client, amount="10.00", date="2026-10-01")["id"],
        create(client, amount="5.50", date="2026-10-02")["id"],
        create(client, amount="4.50", date="2026-10-03")["id"],
    }

    response = client.get("/expenses")

    assert response.status_code == 200
    listing = response.json()
    assert set(listing) == {"items", "total"}
    assert {item["id"] for item in listing["items"]} == ids
    assert listing["total"] == {"USD": "20.00"}


def test_ac09_q6_list_is_ordered_by_date_descending(client: TestClient) -> None:
    for day in ["2026-10-02", "2026-10-31", "2026-09-30", "2026-10-15"]:
        create(client, date=day)

    assert dates_of(list_expenses(client)) == [
        "2026-10-31",
        "2026-10-15",
        "2026-10-02",
        "2026-09-30",
    ]


def test_ac09_q12_same_date_ties_break_by_newest_first(client: TestClient) -> None:
    first = create(client, date="2026-10-01", note="first")
    second = create(client, date="2026-10-01", note="second")

    assert [item["id"] for item in list_expenses(client)["items"]] == [second["id"], first["id"]]


# --------------------------------------------------------------------------- AC-10


def test_ac10_empty_store_lists_empty_with_empty_total(client: TestClient) -> None:
    response = client.get("/expenses")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": {}}


# --------------------------------------------------------------------------- AC-11


def test_ac11_filter_by_inclusive_date_range(four_dated: TestClient) -> None:
    listing = list_expenses(four_dated, {"from": "2026-10-01", "to": "2026-10-15"})

    assert dates_of(listing) == ["2026-10-15", "2026-10-01"]
    assert listing["total"] == {"USD": "5.00"}


def test_ac11_q15_from_equal_to_is_a_single_day(four_dated: TestClient) -> None:
    listing = list_expenses(four_dated, {"from": "2026-10-15", "to": "2026-10-15"})

    assert dates_of(listing) == ["2026-10-15"]
    assert listing["total"] == {"USD": "3.00"}


# --------------------------------------------------------------------------- AC-12


def test_ac12_open_ended_from_only(four_dated: TestClient) -> None:
    listing = list_expenses(four_dated, {"from": "2026-10-15"})

    assert dates_of(listing) == ["2026-10-31", "2026-10-15"]
    assert listing["total"] == {"USD": "7.00"}


def test_ac12_open_ended_to_only(four_dated: TestClient) -> None:
    listing = list_expenses(four_dated, {"to": "2026-10-01"})

    assert dates_of(listing) == ["2026-10-01", "2026-09-30"]
    assert listing["total"] == {"USD": "3.00"}


# --------------------------------------------------------------------------- AC-13


def test_ac13_filter_by_category(client: TestClient) -> None:
    food_ids = {
        create(client, category="food", amount="10.00", date="2026-10-01")["id"],
        create(client, category="food", amount="2.25", date="2026-10-03")["id"],
    }
    create(client, category="travel", amount="100.00", date="2026-10-02")

    listing = list_expenses(client, {"category": "food"})

    assert {item["id"] for item in listing["items"]} == food_ids
    assert listing["total"] == {"USD": "12.25"}


def test_ac13_q15_empty_filter_values_count_as_not_supplied(client: TestClient) -> None:
    create(client, category="food", date="2026-10-01")
    create(client, category="travel", date="2026-10-02")

    listing = list_expenses(client, {"from": "", "to": "", "category": ""})

    assert len(listing["items"]) == 2


def test_ac13_q15_whitespace_category_filter_counts_as_not_supplied(client: TestClient) -> None:
    create(client, category="food", date="2026-10-01")
    create(client, category="travel", date="2026-10-02")

    assert len(list_expenses(client, {"category": "   "})["items"]) == 2


def test_ac13_sql_injection_string_in_category_matches_nothing(client: TestClient) -> None:
    create(client, category="food")

    assert list_expenses(client, {"category": "' OR 1=1 --"}) == {"items": [], "total": {}}


# --------------------------------------------------------------------------- AC-14


def test_ac14_combined_filters(client: TestClient) -> None:
    match_a = create(client, category="food", date="2026-10-05", amount="3.00")
    match_b = create(client, category="Food", date="2026-10-10", amount="4.00")
    create(client, category="food", date="2026-09-30", amount="50.00")  # before range
    create(client, category="food", date="2026-10-11", amount="60.00")  # after range
    create(client, category="travel", date="2026-10-07", amount="70.00")  # wrong category

    listing = list_expenses(
        client, {"from": "2026-10-01", "to": "2026-10-10", "category": "food"}
    )

    assert [item["id"] for item in listing["items"]] == [match_b["id"], match_a["id"]]
    assert listing["total"] == {"USD": "7.00"}


# --------------------------------------------------------------------------- AC-15


@pytest.mark.parametrize(
    "params",
    [
        {"category": "rent"},
        {"from": "2027-01-01"},
        {"to": "2020-01-01"},
        {"from": "2026-10-01", "to": "2026-10-31", "category": "travel"},
    ],
)
def test_ac15_no_matches_returns_empty_list_and_empty_total(
    client: TestClient, params: dict[str, str]
) -> None:
    create(client, category="food", date="2026-10-01")

    response = client.get("/expenses", params=params)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": {}}


# --------------------------------------------------------------------------- AC-16


@pytest.mark.parametrize("param", ["from", "to"])
@pytest.mark.parametrize(
    "value", ["2026-02-30", "10/01/2026", "2026-10-01T00:00:00", "yesterday", "1696118400"]
)
def test_ac16_invalid_filter_date_is_rejected(client: TestClient, param: str, value: str) -> None:
    create(client)

    response = client.get("/expenses", params={param: value})

    error = assert_validation_error(response, field=param)
    assert "items" not in response.json()
    assert error["code"] == "validation_error"


def test_ac16_from_later_than_to_is_rejected(client: TestClient) -> None:
    create(client)

    response = client.get("/expenses", params={"from": "2026-10-15", "to": "2026-10-01"})

    assert_validation_error(response, field="from")
    assert "items" not in response.json()


def test_ac16_q15_repeated_category_is_rejected(client: TestClient) -> None:
    create(client)

    response = client.get("/expenses", params=[("category", "food"), ("category", "travel")])

    assert_validation_error(response, field="category")
    assert "items" not in response.json()


# --------------------------------------------------------------------------- AC-17


@pytest.mark.parametrize("query", ["food", "FOOD", "Food", " food "])
def test_ac17_category_filter_is_case_insensitive(client: TestClient, query: str) -> None:
    stored = create(client, category="Food")

    listing = list_expenses(client, {"category": query})

    assert [item["id"] for item in listing["items"]] == [stored["id"]]
    assert listing["items"][0]["category"] == "Food"


# --------------------------------------------------------------------------- AC-18


def test_ac18_totals_are_reported_per_currency(client: TestClient) -> None:
    create(client, amount="10.00", currency="USD", date="2026-10-01")
    create(client, amount="20.00", currency="EUR", date="2026-10-02")

    listing = list_expenses(client)

    assert len(listing["items"]) == 2
    assert listing["total"] == {"USD": "10.00", "EUR": "20.00"}


def test_ac18_filtered_totals_only_include_present_currencies(client: TestClient) -> None:
    create(client, amount="10.00", currency="USD", category="food")
    create(client, amount="20.00", currency="EUR", category="travel")

    assert list_expenses(client, {"category": "travel"})["total"] == {"EUR": "20.00"}


# --------------------------------------------------------------------------- AC-19


def test_ac19_duplicate_create_gets_new_id_and_both_are_counted(client: TestClient) -> None:
    first = client.post("/expenses", json=VALID)
    second = client.post("/expenses", json=VALID)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    listing = list_expenses(client)
    assert {item["id"] for item in listing["items"]} == {first.json()["id"], second.json()["id"]}
    assert listing["total"] == {"USD": "25.00"}


# --------------------------------------------------------------------------- AC-20


def test_ac20_health_is_unchanged(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ac20_app_title_is_unchanged(client: TestClient) -> None:
    assert client.app.title == "Expense API"


def test_ac20_q10_unknown_path_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/no-such-path")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
