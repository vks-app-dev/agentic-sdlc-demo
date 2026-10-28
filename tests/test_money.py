from decimal import (
    Decimal,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    getcontext,
)

import pytest

from app.money import (
    MAX_AMOUNT_LENGTH,
    MONEY_CONTEXT,
    AmountError,
    format_amount,
    parse_amount,
    sum_by_currency,
)

# --------------------------------------------------------------------------- context


def test_context_has_64_digit_precision_and_traps() -> None:
    assert MONEY_CONTEXT.prec == 64
    for signal in (InvalidOperation, Inexact, Overflow, DivisionByZero):
        assert MONEY_CONTEXT.traps[signal]


def test_module_does_not_change_global_context() -> None:
    assert getcontext() is not MONEY_CONTEXT
    assert getcontext().prec == 28


# --------------------------------------------------------------------------- parse_amount (AC-4)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12.50", "12.50"),
        ("12.5", "12.50"),
        ("7", "7.00"),
        ("0.01", "0.01"),
        ("0.1", "0.10"),
        ("100", "100.00"),
    ],
)
def test_parse_amount_accepts_and_normalises_to_two_decimals(raw: str, expected: str) -> None:
    amount = parse_amount(raw)

    assert isinstance(amount, Decimal)
    assert amount == Decimal(expected)
    assert format_amount(amount) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "0",
        "0.00",
        "0.0",
        "-1",
        "-0.01",
        "-12.50",
        "+1",
        "abc",
        "",
        "12.500",
        "0.001",
        "12.",
        ".5",
        "012",
        "1e1",
        "1E1",
        "NaN",
        "nan",
        "Infinity",
        "-Infinity",
        "sNaN",
        " 12.50 ",
        "12.50\n",
        "12,50",
        "1_000",
        "١٢",  # Arabic-Indic digits
        "１２",  # full-width digits
    ],
)
def test_parse_amount_rejects_invalid(raw: str) -> None:
    with pytest.raises(AmountError):
        parse_amount(raw)


@pytest.mark.parametrize("raw", [12.5, 12, None, Decimal("1.00"), b"12.50"])
def test_parse_amount_rejects_non_strings(raw: object) -> None:
    with pytest.raises(AmountError):
        parse_amount(raw)


def test_amount_error_is_value_error_and_does_not_echo_input() -> None:
    secret = "secret-value-123"
    with pytest.raises(ValueError) as excinfo:
        parse_amount(secret)
    assert secret not in str(excinfo.value)


def test_parse_amount_accepts_32_char_amount_without_error() -> None:
    raw = "9" * 32
    assert len(raw) == MAX_AMOUNT_LENGTH

    amount = parse_amount(raw)

    assert format_amount(amount) == raw + ".00"


def test_parse_amount_accepts_32_char_amount_with_decimals() -> None:
    raw = "9" * 29 + ".99"
    assert len(raw) == MAX_AMOUNT_LENGTH

    assert format_amount(parse_amount(raw)) == raw


@pytest.mark.parametrize("raw", ["9" * 33, "1" * 31 + ".00", "x" * 10_000])
def test_parse_amount_rejects_over_32_chars(raw: str) -> None:
    with pytest.raises(AmountError):
        parse_amount(raw)


def test_parse_amount_works_regardless_of_global_context() -> None:
    import decimal

    with decimal.localcontext() as ctx:
        ctx.prec = 5
        amount = parse_amount("9" * 32)
    assert format_amount(amount) == "9" * 32 + ".00"


# --------------------------------------------------------------------------- format_amount


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (Decimal("12.5"), "12.50"),
        (Decimal("1E+3"), "1000.00"),
        (Decimal("1E+40"), "1" + "0" * 40 + ".00"),
        (Decimal("0.30"), "0.30"),
    ],
)
def test_format_amount_never_uses_exponent(amount: Decimal, expected: str) -> None:
    formatted = format_amount(amount)

    assert formatted == expected
    assert "E" not in formatted and "e" not in formatted


def test_format_amount_rejects_more_than_two_decimals() -> None:
    with pytest.raises(Inexact):
        format_amount(Decimal("0.001"))


# --------------------------------------------------------------------------- sum_by_currency (AC-5, AC-18)


def test_sum_is_exact_for_point_one_plus_point_two() -> None:
    totals = sum_by_currency([("USD", parse_amount("0.10")), ("USD", parse_amount("0.20"))])

    assert totals == {"USD": "0.30"}


def test_sum_of_two_max_length_amounts_is_exact() -> None:
    big = "9" * 29 + ".99"

    totals = sum_by_currency([("USD", parse_amount(big)), ("USD", parse_amount(big))])

    assert totals == {"USD": "1" + "9" * 29 + ".98"}


def test_sum_of_many_max_length_amounts_is_exact() -> None:
    big = parse_amount("9" * 32)
    n = 10_000

    totals = sum_by_currency([("USD", big)] * n)

    # (10**32 - 1) * 10**4, written out to avoid default-context rounding.
    assert totals == {"USD": "9" * 32 + "0000.00"}


def test_sum_is_reported_per_currency_never_across() -> None:
    totals = sum_by_currency(
        [
            ("USD", parse_amount("10.00")),
            ("EUR", parse_amount("20.00")),
            ("USD", parse_amount("5.50")),
        ]
    )

    assert totals == {"USD": "15.50", "EUR": "20.00"}


def test_sum_accepts_stored_string_amounts() -> None:
    totals = sum_by_currency([("USD", "10.00"), ("USD", "5.50"), ("USD", "4.50")])

    assert totals == {"USD": "20.00"}


def test_sum_of_nothing_is_empty_map() -> None:
    assert sum_by_currency([]) == {}


def test_sum_works_regardless_of_global_context() -> None:
    import decimal

    big = "9" * 29 + ".99"
    with decimal.localcontext() as ctx:
        ctx.prec = 5
        totals = sum_by_currency([("USD", big), ("USD", big)])

    assert totals == {"USD": "1" + "9" * 29 + ".98"}
