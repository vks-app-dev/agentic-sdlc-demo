"""Money handling for expenses.

All monetary arithmetic goes through ``MONEY_CONTEXT``, a dedicated
``decimal.Context`` with 64 digits of precision that traps every signal that
would otherwise lose information or produce a non-finite value. The default
context (``prec=28``) is below what the 32-character amount cap allows, which
would make ``quantize`` raise or sums round silently (ADR-REQ-001, security
review H finding).

Amounts are never represented as binary floats. On the wire they are strings
with exactly two decimal places, produced by ``format(d, "f")`` so that
exponent notation can never appear.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import (
    Context,
    Decimal,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
)

MAX_AMOUNT_LENGTH = 32
"""Maximum length, in characters, of a submitted amount string."""

MONEY_CONTEXT = Context(
    prec=64,
    traps=[InvalidOperation, Inexact, Overflow, DivisionByZero],
)
"""Decimal context used for all money parsing, quantising and summing."""

CENT = Decimal("0.01")

# ASCII digits only (no ``\d``), anchored via ``fullmatch``, no nested
# quantifiers, so there is no Unicode-digit bypass and no ReDoS risk.
_AMOUNT_RE = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]{1,2})?", re.ASCII)


class AmountError(ValueError):
    """Raised when an amount is invalid.

    Messages are fixed strings and never include the submitted value.
    """


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(CENT, context=MONEY_CONTEXT)


def parse_amount(value: object) -> Decimal:
    """Parse a submitted amount string into a ``Decimal`` with 2 decimals.

    The length cap is checked before the regex and before any Decimal work.
    Accepts a positive number with 0-2 decimal places written in plain ASCII
    digits; rejects zero, negatives, exponents, NaN/Infinity, whitespace and
    anything else.
    """
    if not isinstance(value, str):
        raise AmountError("amount must be a string")
    if len(value) > MAX_AMOUNT_LENGTH:
        raise AmountError(f"amount must be at most {MAX_AMOUNT_LENGTH} characters")
    if _AMOUNT_RE.fullmatch(value) is None:
        raise AmountError("amount must be a positive number with at most 2 decimal places")
    amount = _quantize(MONEY_CONTEXT.create_decimal(value))
    if amount <= 0:
        raise AmountError("amount must be greater than 0")
    return amount


def format_amount(amount: Decimal) -> str:
    """Render an amount as a plain string with exactly 2 decimal places."""
    return format(_quantize(amount), "f")


def sum_by_currency(entries: Iterable[tuple[str, Decimal | str]]) -> dict[str, str]:
    """Total amounts per currency, never summing across currencies.

    ``entries`` are ``(currency, amount)`` pairs; amounts may be ``Decimal``
    or canonical decimal strings (as stored). Returns a map of currency to
    the formatted 2-decimal total, in order of first appearance; ``{}`` when
    there are no entries.
    """
    totals: dict[str, Decimal] = {}
    for currency, raw in entries:
        amount = raw if isinstance(raw, Decimal) else MONEY_CONTEXT.create_decimal(raw)
        current = totals.get(currency, Decimal(0))
        totals[currency] = MONEY_CONTEXT.add(current, amount)
    return {currency: format_amount(total) for currency, total in totals.items()}
