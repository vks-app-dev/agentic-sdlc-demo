"""Pydantic models for the expenses API (ADR-REQ-001, "Validation rules").

Every field validator runs in "before" mode and requires a real ``str`` (or
``None`` for ``note``), so Pydantic's lax coercion never turns a JSON number,
bool or list into a value. Error messages are fixed strings and never include
the submitted value (spec Q10), and errors carry no ``ctx``.

Normalisation (spec Q11):

- ``amount``: canonical 2-decimal string (``"12.5"`` becomes ``"12.50"``).
- ``currency``: none; must already be 3 uppercase ASCII letters.
- ``category``: trimmed, case kept, then 1-50 characters.
- ``note``: trimmed, at most 500 characters; empty becomes ``None``.
- ``date``: strict ``YYYY-MM-DD`` (ASCII digits) and a real calendar date.

``category`` and ``note`` reject C0/C1 control characters anywhere in the
submitted value (security review, stored content injection).
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict
from pydantic_core import PydanticCustomError

from app.money import AmountError, format_amount, parse_amount

CATEGORY_MAX_LENGTH = 50
NOTE_MAX_LENGTH = 500

# ``[0-9]`` rather than ``\d`` so non-ASCII digits cannot slip through.
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_CURRENCY_RE = re.compile(r"[A-Z]{3}")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")

MSG_NOT_STRING = "must be a string"
MSG_DATE = "must be a valid calendar date in YYYY-MM-DD format"
MSG_CURRENCY = "must be a 3-letter uppercase currency code"
MSG_CATEGORY_LENGTH = f"must be 1-{CATEGORY_MAX_LENGTH} characters after trimming"
MSG_NOTE_LENGTH = f"must be at most {NOTE_MAX_LENGTH} characters after trimming"
MSG_CONTROL = "must not contain control characters"


class DateError(ValueError):
    """Raised by :func:`parse_iso_date`. The message never includes the input."""


def parse_iso_date(value: object) -> dt.date:
    """Parse a strict ``YYYY-MM-DD`` calendar date.

    Rejects non-strings, non-ASCII digits, datetimes, time zones, timestamps
    and impossible dates such as ``2026-02-30``. Shared by the request body
    model and the list endpoint's ``from``/``to`` query parameters.
    """
    if not isinstance(value, str) or _DATE_RE.fullmatch(value) is None:
        raise DateError(MSG_DATE)
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise DateError(MSG_DATE) from None


def _error(error_type: str, message: str) -> PydanticCustomError:
    return PydanticCustomError(error_type, message)


def _require_str(value: object) -> str:
    if not isinstance(value, str):
        raise _error("string_type", MSG_NOT_STRING)
    return value


def _reject_control_chars(value: str) -> None:
    if _CONTROL_RE.search(value) is not None:
        raise _error("control_characters", MSG_CONTROL)


def _validate_amount(value: object) -> str:
    try:
        return format_amount(parse_amount(_require_str(value)))
    except AmountError as exc:
        # AmountError messages are fixed strings without the submitted value.
        raise _error("amount_invalid", str(exc)) from None


def _validate_currency(value: object) -> str:
    text = _require_str(value)
    if _CURRENCY_RE.fullmatch(text) is None:
        raise _error("currency_invalid", MSG_CURRENCY)
    return text


def _validate_category(value: object) -> str:
    text = _require_str(value)
    _reject_control_chars(text)
    text = text.strip()
    if not 1 <= len(text) <= CATEGORY_MAX_LENGTH:
        raise _error("category_length", MSG_CATEGORY_LENGTH)
    return text


def _validate_date(value: object) -> dt.date:
    try:
        return parse_iso_date(_require_str(value))
    except DateError:
        raise _error("date_invalid", MSG_DATE) from None


def _validate_note(value: object) -> str | None:
    if value is None:
        return None
    text = _require_str(value)
    _reject_control_chars(text)
    text = text.strip()
    if len(text) > NOTE_MAX_LENGTH:
        raise _error("note_length", MSG_NOTE_LENGTH)
    return text or None


Amount = Annotated[str, BeforeValidator(_validate_amount)]
Currency = Annotated[str, BeforeValidator(_validate_currency)]
Category = Annotated[str, BeforeValidator(_validate_category)]
IsoDate = Annotated[dt.date, BeforeValidator(_validate_date)]
Note = Annotated[str | None, BeforeValidator(_validate_note)]


class ExpenseCreate(BaseModel):
    """Request body for ``POST /expenses``."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    amount: Amount
    currency: Currency
    category: Category
    date: IsoDate
    note: Note = None


class Expense(BaseModel):
    """A stored expense as returned by the API.

    ``amount`` is a 2-decimal string, never a float. ``date`` serialises as
    ``YYYY-MM-DD`` and ``created_at`` as an ISO 8601 UTC timestamp.
    """

    id: str
    amount: str
    currency: str
    category: str
    date: dt.date
    note: str | None = None
    created_at: dt.datetime


class ExpenseList(BaseModel):
    """Response body for ``GET /expenses``.

    ``total`` maps each currency present in ``items`` to its 2-decimal total
    string; it is ``{}`` when there are no items (spec Q8a).
    """

    items: list[Expense]
    total: dict[str, str]
