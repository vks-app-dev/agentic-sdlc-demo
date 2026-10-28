import datetime as dt
from typing import Any

import pytest
from pydantic import ValidationError

from app.expenses.schemas import (
    CATEGORY_MAX_LENGTH,
    NOTE_MAX_LENGTH,
    DateError,
    Expense,
    ExpenseCreate,
    ExpenseList,
    parse_iso_date,
)

VALID: dict[str, Any] = {
    "amount": "12.50",
    "currency": "USD",
    "category": "food",
    "date": "2026-10-01",
    "note": "lunch",
}


def body(**overrides: Any) -> dict[str, Any]:
    data = dict(VALID)
    data.update(overrides)
    return data


def errors_for(data: Any) -> list[dict[str, Any]]:
    with pytest.raises(ValidationError) as info:
        ExpenseCreate.model_validate(data)
    return info.value.errors()


def error_fields(data: Any) -> set[str]:
    return {".".join(str(part) for part in err["loc"]) for err in errors_for(data)}


# --------------------------------------------------------------------------- valid input


def test_valid_body_is_parsed() -> None:
    model = ExpenseCreate.model_validate(VALID)

    assert model.amount == "12.50"
    assert model.currency == "USD"
    assert model.category == "food"
    assert model.date == dt.date(2026, 10, 1)
    assert model.note == "lunch"


def test_valid_body_from_json_is_parsed() -> None:
    model = ExpenseCreate.model_validate_json(
        '{"amount": "7", "currency": "EUR", "category": "travel", "date": "2028-02-29"}'
    )

    assert model.amount == "7.00"
    assert model.date == dt.date(2028, 2, 29)
    assert model.note is None


# --------------------------------------------------------------------------- AC-2 note


def test_ac02_note_absent_is_none() -> None:
    data = body()
    del data["note"]

    assert ExpenseCreate.model_validate(data).note is None


@pytest.mark.parametrize("note", [None, "", "   ", " 　 "])
def test_ac02_null_or_blank_note_is_none(note: Any) -> None:
    assert ExpenseCreate.model_validate(body(note=note)).note is None


def test_ac02_note_is_trimmed() -> None:
    assert ExpenseCreate.model_validate(body(note="  lunch  ")).note == "lunch"


def test_ac08_note_max_length_measured_after_trim() -> None:
    note = "  " + "n" * NOTE_MAX_LENGTH + "  "

    assert ExpenseCreate.model_validate(body(note=note)).note == "n" * NOTE_MAX_LENGTH


def test_ac08_note_too_long_is_rejected() -> None:
    assert error_fields(body(note="n" * (NOTE_MAX_LENGTH + 1))) == {"note"}


# --------------------------------------------------------------------------- AC-3 required / types


@pytest.mark.parametrize("missing", ["amount", "currency", "category", "date"])
def test_ac03_missing_required_field_is_named(missing: str) -> None:
    data = body()
    del data[missing]

    errors = errors_for(data)

    assert [(err["loc"], err["type"]) for err in errors] == [((missing,), "missing")]


@pytest.mark.parametrize("field", ["amount", "currency", "category", "date"])
def test_ac03_null_required_field_is_rejected(field: str) -> None:
    assert error_fields(body(**{field: None})) == {field}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("category", 123),
        ("currency", 840),
        ("date", 20261001),
        ("note", 5),
        ("category", ["food"]),
        ("note", True),
        ("currency", {"code": "USD"}),
    ],
)
def test_ac03_wrong_type_is_rejected(field: str, value: Any) -> None:
    assert error_fields(body(**{field: value})) == {field}


def test_ac03_extra_field_is_rejected() -> None:
    errors = errors_for(body(merchant="cafe"))

    assert [err["type"] for err in errors] == ["extra_forbidden"]


@pytest.mark.parametrize("data", [[], "string", 42, None])
def test_ac03_non_object_body_is_rejected(data: Any) -> None:
    assert errors_for(data)


# --------------------------------------------------------------------------- AC-4 amount


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
        "+1",
        "01",
        "１２",
        "9" * 33,
    ],
)
def test_ac04_invalid_amount_is_rejected(amount: str) -> None:
    assert error_fields(body(amount=amount)) == {"amount"}


@pytest.mark.parametrize("amount", [12.5, 12, 0.1, True])
def test_ac04_json_number_amount_is_rejected(amount: Any) -> None:
    assert error_fields(body(amount=amount)) == {"amount"}


def test_ac04_json_number_amount_is_rejected_from_raw_json() -> None:
    raw = '{"amount": 12.5, "currency": "USD", "category": "food", "date": "2026-10-01"}'

    with pytest.raises(ValidationError) as info:
        ExpenseCreate.model_validate_json(raw)

    assert {err["loc"] for err in info.value.errors()} == {("amount",)}


@pytest.mark.parametrize(
    ("submitted", "normalised"),
    [
        ("12.5", "12.50"),
        ("7", "7.00"),
        ("0.01", "0.01"),
        ("12.50", "12.50"),
        ("9" * 32, "9" * 32 + ".00"),
        ("9" * 29 + ".99", "9" * 29 + ".99"),
    ],
)
def test_ac04_valid_amount_is_normalised_to_two_decimals(submitted: str, normalised: str) -> None:
    amount = ExpenseCreate.model_validate(body(amount=submitted)).amount

    assert isinstance(amount, str)
    assert amount == normalised


# --------------------------------------------------------------------------- AC-6 currency


@pytest.mark.parametrize(
    "currency", ["usd", "Usd", "US", "DOLLARS", "", "U5D", " USD", "USD ", "ÜSD", "USD\n"]
)
def test_ac06_invalid_currency_is_rejected(currency: str) -> None:
    assert error_fields(body(currency=currency)) == {"currency"}


@pytest.mark.parametrize("currency", ["USD", "EUR", "JPY", "XAU"])
def test_ac06_valid_currency_is_kept(currency: str) -> None:
    assert ExpenseCreate.model_validate(body(currency=currency)).currency == currency


# --------------------------------------------------------------------------- AC-7 date


@pytest.mark.parametrize(
    "date",
    [
        "2026-02-30",
        "2026-13-01",
        "2026-00-10",
        "2027-02-29",
        "10/01/2026",
        "2026-1-1",
        "2026/10/01",
        "",
        "2026-10-01T00:00:00",
        "2026-10-01T10:00:00Z",
        "2026-10-01+02:00",
        " 2026-10-01",
        "1696118400",
        "20261001",
        "２０２６-１０-０１",
        "٢٠٢٦-١٠-٠١",
    ],
)
def test_ac07_invalid_date_is_rejected(date: str) -> None:
    assert error_fields(body(date=date)) == {"date"}


def test_ac07_date_object_is_rejected() -> None:
    # Only JSON strings are accepted; no lax coercion of other types.
    assert error_fields(body(date=dt.date(2026, 10, 1))) == {"date"}


@pytest.mark.parametrize(
    ("date", "expected"),
    [
        ("2099-12-31", dt.date(2099, 12, 31)),
        ("2028-02-29", dt.date(2028, 2, 29)),
        ("2026-10-01", dt.date(2026, 10, 1)),
    ],
)
def test_ac07_future_and_leap_dates_are_accepted(date: str, expected: dt.date) -> None:
    assert ExpenseCreate.model_validate(body(date=date)).date == expected


# --------------------------------------------------------------------------- parse_iso_date


def test_parse_iso_date_parses_valid_date() -> None:
    assert parse_iso_date("2026-10-15") == dt.date(2026, 10, 15)


@pytest.mark.parametrize(
    "value",
    ["2026-02-30", "10/01/2026", "2026-10-01T00:00:00", "yesterday", "1696118400", "", None, 20261001],
)
def test_parse_iso_date_rejects_invalid_input(value: Any) -> None:
    with pytest.raises(DateError):
        parse_iso_date(value)


def test_date_error_is_value_error_without_input() -> None:
    with pytest.raises(ValueError) as info:
        parse_iso_date("secret-2026-02-30")

    assert "secret" not in str(info.value)


# --------------------------------------------------------------------------- AC-8 category


@pytest.mark.parametrize(
    "category",
    ["", "   ", "　", "x" * (CATEGORY_MAX_LENGTH + 1), "  " + "x" * (CATEGORY_MAX_LENGTH + 1) + "  "],
)
def test_ac08_invalid_category_is_rejected(category: str) -> None:
    assert error_fields(body(category=category)) == {"category"}


@pytest.mark.parametrize(
    ("submitted", "stored"),
    [
        ("  Food  ", "Food"),
        ("Food", "Food"),
        ("c" * CATEGORY_MAX_LENGTH, "c" * CATEGORY_MAX_LENGTH),
        ("  " + "c" * CATEGORY_MAX_LENGTH + "  ", "c" * CATEGORY_MAX_LENGTH),
        ("Café", "Café"),
        ("x", "x"),
    ],
)
def test_ac08_category_is_trimmed_and_case_kept(submitted: str, stored: str) -> None:
    assert ExpenseCreate.model_validate(body(category=submitted)).category == stored


def test_ac08_category_length_counts_code_points() -> None:
    category = "é" * CATEGORY_MAX_LENGTH  # 100 bytes in UTF-8, 50 code points

    assert ExpenseCreate.model_validate(body(category=category)).category == category


# --------------------------------------------------------------------------- control characters


@pytest.mark.parametrize("field", ["category", "note"])
@pytest.mark.parametrize(
    "char", ["\x00", "\x01", "\t", "\n", "\r", "\x1b", "\x1f", "\x7f", "\x80", "\x85", "\x9f"]
)
def test_control_characters_are_rejected(field: str, char: str) -> None:
    assert error_fields(body(**{field: f"fo{char}od"})) == {field}


@pytest.mark.parametrize("field", ["category", "note"])
def test_edge_control_characters_are_rejected_before_trimming(field: str) -> None:
    assert error_fields(body(**{field: "food\n"})) == {field}


# --------------------------------------------------------------------------- error messages


def test_error_messages_never_echo_input_and_have_no_ctx() -> None:
    secret = "my-private-note-xyz"
    data = {
        "amount": secret,
        "currency": secret,
        "category": secret * 10,
        "date": secret,
        "note": secret * 100,
        secret: "x",
    }

    with pytest.raises(ValidationError) as info:
        ExpenseCreate.model_validate(data)

    errors = info.value.errors(include_input=False, include_url=False)
    assert {err["loc"][0] for err in errors} == {
        "amount",
        "currency",
        "category",
        "date",
        "note",
        secret,  # extra_forbidden: loc is the key; T2 maps it to "body"
    }
    for err in errors:
        assert secret not in err["msg"]
        assert "ctx" not in err


def test_error_messages_are_fixed_strings() -> None:
    first = {err["loc"]: err["msg"] for err in errors_for(body(amount="abc", date="bad"))}
    second = {err["loc"]: err["msg"] for err in errors_for(body(amount="xyz", date="worse"))}

    assert first == second


# --------------------------------------------------------------------------- response models


def test_expense_serialises_amount_as_string_and_date_iso() -> None:
    expense = Expense(
        id="6f1c2d3e-0000-4000-8000-000000000000",
        amount="12.50",
        currency="USD",
        category="Food",
        date=dt.date(2026, 10, 1),
        note=None,
        created_at=dt.datetime(2026, 10, 23, 9, 15, 2, 123456, tzinfo=dt.UTC),
    )

    data = expense.model_dump(mode="json")

    assert data == {
        "id": "6f1c2d3e-0000-4000-8000-000000000000",
        "amount": "12.50",
        "currency": "USD",
        "category": "Food",
        "date": "2026-10-01",
        "note": None,
        "created_at": "2026-10-23T09:15:02.123456Z",
    }


def test_expense_accepts_stored_text_values() -> None:
    expense = Expense.model_validate(
        {
            "id": "abc",
            "amount": "0.10",
            "currency": "EUR",
            "category": "food",
            "date": "2026-10-01",
            "note": "x",
            "created_at": "2026-10-23T09:15:02.123456Z",
        }
    )

    assert expense.date == dt.date(2026, 10, 1)
    assert expense.created_at.tzinfo is not None
    assert expense.model_dump(mode="json")["amount"] == "0.10"


def test_expense_list_total_is_a_currency_map_of_strings() -> None:
    assert ExpenseList(items=[], total={}).model_dump(mode="json") == {"items": [], "total": {}}
    listing = ExpenseList(items=[], total={"USD": "20.00", "EUR": "20.00"})

    assert listing.model_dump(mode="json")["total"] == {"USD": "20.00", "EUR": "20.00"}


def test_response_amount_and_total_schema_types_are_string() -> None:
    expense_schema = Expense.model_json_schema()
    list_schema = ExpenseList.model_json_schema()

    assert expense_schema["properties"]["amount"]["type"] == "string"
    assert list_schema["properties"]["total"]["additionalProperties"]["type"] == "string"
