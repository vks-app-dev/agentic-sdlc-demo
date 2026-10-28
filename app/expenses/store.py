"""SQLite persistence for expenses (ADR-REQ-001, Option A).

``SqliteExpenseStore`` owns the schema and every SQL statement. Design rules:

- The database file is created with mode ``0600`` before SQLite first opens
  it, so personal financial data is never world-readable (security review).
  SQLite gives the ``-wal``/``-shm`` files the same mode as the database.
- WAL journal mode and a 5 second busy timeout let parallel writers wait
  instead of failing with ``database is locked``.
- A short-lived connection is opened per call, so no connection is ever
  shared between FastAPI's threadpool workers.
- All values are bound with ``?`` placeholders. The WHERE clause is assembled
  only from the fixed fragments below, never from user strings, and the
  ORDER BY is fixed.
- Schema versions are tracked with ``PRAGMA user_version``.
"""

from __future__ import annotations

import datetime as dt
import os
import sqlite3
import uuid
from contextlib import closing
from typing import Protocol

from app.expenses.schemas import Expense, ExpenseCreate

SCHEMA_VERSION = 1
BUSY_TIMEOUT_SECONDS = 5.0
DB_FILE_MODE = 0o600

# UTC, fixed width, so lexical order equals chronological order.
CREATED_AT_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

_SCHEMA_V1 = (
    """
    CREATE TABLE IF NOT EXISTS expenses (
      id           TEXT PRIMARY KEY,
      amount       TEXT NOT NULL,
      currency     TEXT NOT NULL,
      category     TEXT NOT NULL,
      category_key TEXT NOT NULL,
      date         TEXT NOT NULL,
      note         TEXT,
      created_at   TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_expenses_date ON expenses(date)",
    "CREATE INDEX IF NOT EXISTS ix_expenses_category_key ON expenses(category_key)",
)

_INSERT_SQL = (
    "INSERT INTO expenses "
    "(id, amount, currency, category, category_key, date, note, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)

_SELECT_SQL = "SELECT id, amount, currency, category, date, note, created_at FROM expenses"
_WHERE_DATE_FROM = "date >= ?"
_WHERE_DATE_TO = "date <= ?"
_WHERE_CATEGORY = "category_key = ?"
_ORDER_SQL = " ORDER BY date DESC, created_at DESC, rowid DESC"


def category_key(category: str) -> str:
    """Key used for case-insensitive category matching (Unicode-aware)."""
    return category.strip().casefold()


class ExpenseStore(Protocol):
    """Storage interface used by the expenses router."""

    def add(self, payload: ExpenseCreate) -> Expense:
        """Store a validated expense and return it with ``id``/``created_at``."""
        ...

    def list(
        self,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
        category: str | None = None,
    ) -> list[Expense]:
        """Return matching expenses, newest date first. Bounds are inclusive."""
        ...


class SqliteExpenseStore:
    """``ExpenseStore`` backed by a SQLite file at ``db_path``."""

    def __init__(self, db_path: str) -> None:
        self._db_path = os.fspath(db_path)
        self._create_file()
        self._init_schema()

    @property
    def db_path(self) -> str:
        return self._db_path

    def _create_file(self) -> None:
        # Pre-create with 0600 so SQLite never creates it with the umask
        # default (typically 0644). An existing file keeps its mode.
        fd = os.open(self._db_path, os.O_CREAT | os.O_RDWR, DB_FILE_MODE)
        os.close(fd)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=BUSY_TIMEOUT_SECONDS)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.isolation_level = None  # explicit transaction control below
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            try:
                (version,) = conn.execute("PRAGMA user_version").fetchone()
                if version < 1:
                    for statement in _SCHEMA_V1:
                        conn.execute(statement)
                    # PRAGMA does not accept bound parameters; the value is
                    # an int constant, never user input.
                    conn.execute(f"PRAGMA user_version = {int(SCHEMA_VERSION)}")
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    def add(self, payload: ExpenseCreate) -> Expense:
        expense_id = str(uuid.uuid4())
        created_at = dt.datetime.now(dt.UTC)  # timezone-aware, serialises with "Z"
        row = (
            expense_id,
            payload.amount,
            payload.currency,
            payload.category,
            category_key(payload.category),
            payload.date.isoformat(),
            payload.note,
            created_at.strftime(CREATED_AT_FORMAT),
        )
        with closing(self._connect()) as conn, conn:
            conn.execute(_INSERT_SQL, row)
        return Expense(
            id=expense_id,
            amount=payload.amount,
            currency=payload.currency,
            category=payload.category,
            date=payload.date,
            note=payload.note,
            created_at=created_at,
        )

    def list(
        self,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
        category: str | None = None,
    ) -> list[Expense]:
        clauses: list[str] = []
        params: list[str] = []
        if date_from is not None:
            clauses.append(_WHERE_DATE_FROM)
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append(_WHERE_DATE_TO)
            params.append(date_to.isoformat())
        if category is not None:
            clauses.append(_WHERE_CATEGORY)
            params.append(category_key(category))

        sql = _SELECT_SQL
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += _ORDER_SQL

        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
        return [Expense(**dict(row)) for row in rows]
