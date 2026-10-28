"""API tests for GET /expenses (REQ-001/T7).

Covers AC-5, AC-9 to AC-18: listing, per-currency totals, date and category
filters, open-ended ranges, ``from == to``, no matches, invalid filters,
case-insensitive category matching and exact Decimal totals.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

VALID: dict[str, Any] = {
    "amount": "12.50",
    "currency": "USD",
    "category": "food",
    "date": "2026-10-01",
}


def create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    body = dict(VALID)
    body.update(overrides)
    response = client.post("/expenses", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def get_list(client: TestClient, params: Any = None) -> dict[str, Any]:
    response = client.get("/expenses", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def dates_of(listing: dict[str, Any]) -> list[str]:
    return [item["date"] for item in listing["items"]]


def assert_422(response: Any, field: str) -> dict[str, Any]:
    assert response.status_code == 422, response.text
    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert set(error) == {"code", "message", "fields"}
    assert error["code"] == "validation_error"
    assert error["message"] == "Request validation failed"
    assert error["fields"]
    for item in error["fields"]:
        assert set(item) == {"field", "message"}
        assert item["message"]
    assert field in {item["field"] for item in error["fields"]}, error["fields"]
    return error


@pytest.fixture
def four_dated(client: TestClient) -> TestClient:
    for day, amount in [
        ("2026-09-30", "1.00"),
        ("2026-10-01", "2.00"),
        ("2026-10-15", "3.00"),
        ("2026-10-31", "4.00"),
    ]:
        create(client, date=day, amount=amount)
    return client


# --------------------------------------------------------------------------- AC-5


def test_point_one_plus_point_two_is_exactly_point_three(client: TestClient) -> None:
    create(client, amount="0.10")
    create(client, amount="0.20")

    listing = get_list(client)

    assert sorted(item["amount"] for item in listing["items"]) == ["0.10", "0.20"]
    assert listing["total"] == {"USD": "0.30"}


def test_amounts_are_strings_never_floats(client: TestClient) -> None:
    create(client, amount="12.5")

    listing = get_list(client)

    assert listing["items"][0]["amount"] == "12.50"
    assert isinstance(listing["total"]["USD"], str)


def test_large_amount_totals_are_exact(client: TestClient) -> None:
    big = "9" * 29 + ".99"
    create(client, amount=big)
    create(client, amount=big)

    assert get_list(client)["total"] == {"USD": "1" + "9" * 29 + ".98"}


# --------------------------------------------------------------------------- AC-9


def test_list_all_with_total(client: TestClient) -> None:
    ids = {
        create(client, amount="10.00", date="2026-10-01")["id"],
        create(client, amount="5.50", date="2026-10-02")["id"],
        create(client, amount="4.50", date="2026-10-03")["id"],
    }

    listing = get_list(client)

    assert set(listing) == {"items", "total"}
    assert {item["id"] for item in listing["items"]} == ids
    assert listing["total"] == {"USD": "20.00"}


def test_items_have_expense_shape(client: TestClient) -> None:
    created = create(client, note="lunch")

    (item,) = get_list(client)["items"]

    assert item == created


def test_list_is_ordered_by_date_descending_then_newest(client: TestClient) -> None:
    first = create(client, date="2026-10-01")
    create(client, date="2026-10-31")
    second = create(client, date="2026-10-01")

    listing = get_list(client)

    assert dates_of(listing) == ["2026-10-31", "2026-10-01", "2026-10-01"]
    assert [item["id"] for item in listing["items"][1:]] == [second["id"], first["id"]]


# --------------------------------------------------------------------------- AC-10


def test_empty_store_returns_empty_items_and_empty_total(client: TestClient) -> None:
    response = client.get("/expenses")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": {}}


# --------------------------------------------------------------------------- AC-11


def test_filter_by_inclusive_date_range(four_dated: TestClient) -> None:
    listing = get_list(four_dated, {"from": "2026-10-01", "to": "2026-10-15"})

    assert dates_of(listing) == ["2026-10-15", "2026-10-01"]
    assert listing["total"] == {"USD": "5.00"}


def test_from_equal_to_is_a_single_day(four_dated: TestClient) -> None:
    listing = get_list(four_dated, {"from": "2026-10-15", "to": "2026-10-15"})

    assert dates_of(listing) == ["2026-10-15"]
    assert listing["total"] == {"USD": "3.00"}


# --------------------------------------------------------------------------- AC-12


def test_open_ended_from_only(four_dated: TestClient) -> None:
    listing = get_list(four_dated, {"from": "2026-10-15"})

    assert dates_of(listing) == ["2026-10-31", "2026-10-15"]
    assert listing["total"] == {"USD": "7.00"}


def test_open_ended_to_only(four_dated: TestClient) -> None:
    listing = get_list(four_dated, {"to": "2026-10-01"})

    assert dates_of(listing) == ["2026-10-01", "2026-09-30"]
    assert listing["total"] == {"USD": "3.00"}


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"from": "", "to": "2026-10-01"}, ["2026-10-01", "2026-09-30"]),
        ({"from": "2026-10-15", "to": ""}, ["2026-10-31", "2026-10-15"]),
    ],
)
def test_empty_bound_counts_as_open(
    four_dated: TestClient, params: dict[str, str], expected: list[str]
) -> None:
    assert dates_of(get_list(four_dated, params)) == expected


# --------------------------------------------------------------------------- AC-13


def test_filter_by_category(client: TestClient) -> None:
    food = {
        create(client, category="food", amount="10.00")["id"],
        create(client, category="food", amount="2.25")["id"],
    }
    create(client, category="travel", amount="100.00")

    listing = get_list(client, {"category": "food"})

    assert {item["id"] for item in listing["items"]} == food
    assert listing["total"] == {"USD": "12.25"}


@pytest.mark.parametrize(
    "params",
    [
        {"category": ""},
        {"category": "   "},
        {"category": "\t"},
        {"from": "", "to": "", "category": ""},
    ],
    ids=["empty-category", "spaces-category", "tab-category", "all-empty"],
)
def test_empty_or_blank_filters_count_as_not_supplied(
    client: TestClient, params: dict[str, str]
) -> None:
    create(client, category="food", date="2026-10-01")
    create(client, category="travel", date="2026-10-02")

    listing = get_list(client, params)

    assert len(listing["items"]) == 2
    assert listing["total"] == {"USD": "25.00"}


def test_sql_like_strings_match_nothing(client: TestClient) -> None:
    create(client, category="food")

    for query in ["' OR 1=1 --", "%", "_ood", "f%"]:
        assert get_list(client, {"category": query}) == {"items": [], "total": {}}


# --------------------------------------------------------------------------- AC-14


def test_combined_filters(client: TestClient) -> None:
    a = create(client, category="food", date="2026-10-05", amount="3.00")
    b = create(client, category="Food", date="2026-10-10", amount="4.00")
    create(client, category="food", date="2026-09-30", amount="50.00")
    create(client, category="food", date="2026-10-11", amount="60.00")
    create(client, category="travel", date="2026-10-07", amount="70.00")

    listing = get_list(client, {"from": "2026-10-01", "to": "2026-10-10", "category": "food"})

    assert [item["id"] for item in listing["items"]] == [b["id"], a["id"]]
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
def test_no_matches_returns_empty_items_and_empty_total(
    client: TestClient, params: dict[str, str]
) -> None:
    create(client, category="food", date="2026-10-01")

    assert get_list(client, params) == {"items": [], "total": {}}


# --------------------------------------------------------------------------- AC-16


@pytest.mark.parametrize("param", ["from", "to"])
@pytest.mark.parametrize(
    "value",
    [
        "2026-02-30",
        "2026-13-01",
        "10/01/2026",
        "2026-1-1",
        "2026-10-01T00:00:00",
        "2026-10-01T10:00:00Z",
        "2026-10-01+02:00",
        "1696118400",
        "yesterday",
        " ",
        " 2026-10-01",
        "２０２６-１０-０１",
    ],
)
def test_invalid_filter_date_is_rejected(client: TestClient, param: str, value: str) -> None:
    create(client)

    response = client.get("/expenses", params={param: value})

    error = assert_422(response, param)
    assert "items" not in response.json()
    assert error["fields"] == [
        {"field": param, "message": "must be a valid calendar date in YYYY-MM-DD format"}
    ]


def test_invalid_filter_date_is_not_echoed(client: TestClient) -> None:
    secret = "not-a-date-secret-xyz"

    response = client.get("/expenses", params={"from": secret})

    assert_422(response, "from")
    assert secret not in response.text


def test_from_later_than_to_is_rejected_on_from(client: TestClient) -> None:
    create(client)

    response = client.get("/expenses", params={"from": "2026-10-15", "to": "2026-10-01"})

    error = assert_422(response, "from")
    assert error["fields"] == [{"field": "from", "message": "must be on or before 'to'"}]
    assert "items" not in response.json()


def test_repeated_category_is_rejected(client: TestClient) -> None:
    create(client)

    response = client.get("/expenses", params=[("category", "food"), ("category", "travel")])

    error = assert_422(response, "category")
    assert error["fields"] == [{"field": "category", "message": "must be supplied at most once"}]
    assert "items" not in response.json()


def test_repeated_identical_category_is_rejected(client: TestClient) -> None:
    response = client.get("/expenses", params=[("category", "food"), ("category", "food")])

    assert_422(response, "category")


def test_repeated_empty_category_is_rejected(client: TestClient) -> None:
    response = client.get("/expenses", params=[("category", ""), ("category", "")])

    assert_422(response, "category")


# --------------------------------------------------------------------------- AC-17


@pytest.mark.parametrize("query", ["food", "FOOD", "Food", "fOoD", " food ", "\tfood\n"])
def test_category_filter_is_case_insensitive_and_trimmed(
    client: TestClient, query: str
) -> None:
    stored = create(client, category="Food")
    create(client, category="travel")

    listing = get_list(client, {"category": query})

    assert [item["id"] for item in listing["items"]] == [stored["id"]]
    assert listing["items"][0]["category"] == "Food"


def test_category_filter_uses_unicode_casefold(client: TestClient) -> None:
    stored = create(client, category="Straße")

    listing = get_list(client, {"category": "STRASSE"})

    assert [item["id"] for item in listing["items"]] == [stored["id"]]


# --------------------------------------------------------------------------- AC-18


def test_totals_are_reported_per_currency(client: TestClient) -> None:
    create(client, amount="10.00", currency="USD", date="2026-10-01")
    create(client, amount="20.00", currency="EUR", date="2026-10-02")

    listing = get_list(client)

    assert len(listing["items"]) == 2
    assert listing["total"] == {"USD": "10.00", "EUR": "20.00"}


def test_totals_sum_within_each_currency_only(client: TestClient) -> None:
    create(client, amount="1.10", currency="USD")
    create(client, amount="2.20", currency="EUR")
    create(client, amount="3.30", currency="USD")
    create(client, amount="4.40", currency="GBP")

    assert get_list(client)["total"] == {"USD": "4.40", "EUR": "2.20", "GBP": "4.40"}


def test_filtered_totals_only_include_present_currencies(client: TestClient) -> None:
    create(client, amount="10.00", currency="USD", category="food")
    create(client, amount="20.00", currency="EUR", category="travel")

    assert get_list(client, {"category": "travel"})["total"] == {"EUR": "20.00"}


# --------------------------------------------------------------------------- wiring


def test_list_route_is_documented_with_query_params(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/expenses"]["get"]
    names = {param["name"] for param in operation["parameters"]}
    assert names == {"from", "to", "category"}
