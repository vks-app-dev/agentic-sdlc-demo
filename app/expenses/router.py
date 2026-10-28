"""HTTP routes for expenses (ADR-REQ-001, "API contracts").

``POST /expenses`` validates the JSON body into ``ExpenseCreate`` (FastAPI
turns failures into a ``RequestValidationError``, which ``app.errors`` renders
as a 422 Q10 envelope with nothing stored), then stores it and returns the
stored ``Expense`` with 201.

``GET /expenses`` lists stored expenses with optional ``from``/``to``
(inclusive) and ``category`` filters, plus a per-currency total. Request-level
rules (ADR "Sequence of calls", spec Q15):

1. A repeated ``category`` is a 422.
2. Empty ``from``/``to``/``category`` values, and a whitespace-only
   ``category``, count as not supplied.
3. ``from``/``to`` use the same strict ``YYYY-MM-DD`` rule as the body.
4. ``from`` later than ``to`` is a 422 reported on field ``from``.

Error messages are fixed strings; submitted values are never echoed.

Routes are plain ``def`` so FastAPI runs the blocking SQLite calls in its
threadpool.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.errors import (
    VALIDATION_ERROR_CODE,
    VALIDATION_ERROR_MESSAGE,
    ApiException,
    FieldError,
)
from app.expenses.deps import get_store
from app.expenses.schemas import (
    MSG_DATE,
    DateError,
    Expense,
    ExpenseCreate,
    ExpenseList,
    parse_iso_date,
)
from app.expenses.store import ExpenseStore
from app.money import sum_by_currency

router = APIRouter(prefix="/expenses", tags=["expenses"])

StoreDep = Annotated[ExpenseStore, Depends(get_store)]

MSG_CATEGORY_REPEATED = "must be supplied at most once"
MSG_FROM_AFTER_TO = "must be on or before 'to'"


def _validation_error(field: str, message: str) -> ApiException:
    return ApiException(
        422,
        VALIDATION_ERROR_CODE,
        VALIDATION_ERROR_MESSAGE,
        [FieldError(field=field, message=message)],
    )


def _parse_date_param(field: str, value: str | None) -> dt.date | None:
    """Parse an optional ``from``/``to`` value; empty counts as absent."""
    if value is None or value == "":
        return None
    try:
        return parse_iso_date(value)
    except DateError:
        raise _validation_error(field, MSG_DATE) from None


def _category_filter(value: str | None) -> str | None:
    """Empty or whitespace-only ``category`` counts as absent."""
    if value is None or not value.strip():
        return None
    return value


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Expense)
def create_expense(payload: ExpenseCreate, store: StoreDep) -> Expense:
    """Record one expense. Duplicates are allowed and get a new ``id``."""
    return store.add(payload)


@router.get("", response_model=ExpenseList)
def list_expenses(
    request: Request,
    store: StoreDep,
    from_: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
) -> ExpenseList:
    """List expenses, newest date first, with per-currency totals."""
    if len(request.query_params.getlist("category")) > 1:
        raise _validation_error("category", MSG_CATEGORY_REPEATED)

    date_from = _parse_date_param("from", from_)
    date_to = _parse_date_param("to", to)
    if date_from is not None and date_to is not None and date_from > date_to:
        raise _validation_error("from", MSG_FROM_AFTER_TO)

    items = store.list(date_from, date_to, _category_filter(category))
    total = sum_by_currency((item.currency, item.amount) for item in items)
    return ExpenseList(items=items, total=total)
