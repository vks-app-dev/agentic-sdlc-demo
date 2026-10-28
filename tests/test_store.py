"""Tests for app/expenses/store.py and app/expenses/deps.py (REQ-001/T5)."""

from __future__ import annotations

import datetime as dt
import os
import sqlite3
import stat
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from app.expenses import deps
from app.expenses.schemas import Expense, ExpenseCreate
from app.expenses.store import SCHEMA_VERSION, ExpenseStore, SqliteExpenseStore

REPO_ROOT = Path(__file__).resolve().parent.parent

VALID: dict[str, Any] = {
    "amount": "12.50",
    "currency": "USD",
    "category": "food",
    "date": "2026-10-01",
    "note": "lunch",
}


def make(**overrides: Any) -> ExpenseCreate:
    data = dict(VALID)
    data.update(overrides)
    return ExpenseCreate.model_validate(data)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "expenses.db"


@pytest.fixture
def store(db_path: Path) -> SqliteExpenseStore:
    return SqliteExpenseStore(str(db_path))


@pytest.fixture
def dated(store: SqliteExpenseStore) -> SqliteExpenseStore:
    """The four expenses from AC-11/AC-12."""
    for day in ("2026-09-30", "2026-10-01", "2026-10-15", "2026-10-31"):
        store.add(make(date=day))
    return store


def dates(items: list[Expense]) -> list[str]:
    return [item.date.isoformat() for item in items]


# --------------------------------------------------------------------------- file and schema


def test_store_satisfies_protocol(store: SqliteExpenseStore) -> None:
    typed: ExpenseStore = store
    assert typed.list() == []


def test_db_file_created_with_mode_0600(db_path: Path) -> None:
    old_umask = os.umask(0o000)  # most permissive umask: mode must still be 0600
    try:
        SqliteExpenseStore(str(db_path))
    finally:
        os.umask(old_umask)
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600


def test_wal_and_shm_files_are_not_world_readable(db_path: Path) -> None:
    old_umask = os.umask(0o000)
    try:
        store = SqliteExpenseStore(str(db_path))
        store.add(make())
        # Hold a connection open so the -wal/-shm files exist while checked.
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("SELECT count(*) FROM expenses").fetchone()
            for suffix in ("-wal", "-shm"):
                side = Path(str(db_path) + suffix)
                if side.exists():
                    assert stat.S_IMODE(side.stat().st_mode) == 0o600
        finally:
            conn.close()
    finally:
        os.umask(old_umask)


def test_schema_version_wal_and_indexes(store: SqliteExpenseStore, db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        columns = [row[1] for row in conn.execute("PRAGMA table_info(expenses)")]
        assert columns == [
            "id",
            "amount",
            "currency",
            "category",
            "category_key",
            "date",
            "note",
            "created_at",
        ]
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(expenses)")}
        assert {"ix_expenses_date", "ix_expenses_category_key"} <= indexes
    finally:
        conn.close()


def test_reopening_existing_db_keeps_data(db_path: Path) -> None:
    first = SqliteExpenseStore(str(db_path)).add(make())
    reopened = SqliteExpenseStore(str(db_path))
    assert reopened.list() == [first]


def test_amount_stored_as_text(store: SqliteExpenseStore, db_path: Path) -> None:
    store.add(make(amount="0.10"))
    conn = sqlite3.connect(str(db_path))
    try:
        value, kind = conn.execute("SELECT amount, typeof(amount) FROM expenses").fetchone()
    finally:
        conn.close()
    assert (value, kind) == ("0.10", "text")


# --------------------------------------------------------------------------- add (AC-1, AC-19)


def test_add_returns_expense_with_uuid_and_values(store: SqliteExpenseStore) -> None:
    expense = store.add(make())
    assert uuid.UUID(expense.id).version == 4
    assert expense.amount == "12.50"
    assert expense.currency == "USD"
    assert expense.category == "food"
    assert expense.date == dt.date(2026, 10, 1)
    assert expense.note == "lunch"


def test_created_at_is_timezone_aware_utc(store: SqliteExpenseStore) -> None:
    before = dt.datetime.now(dt.UTC)
    expense = store.add(make())
    after = dt.datetime.now(dt.UTC)
    assert expense.created_at.utcoffset() == dt.timedelta(0)
    assert before - dt.timedelta(milliseconds=1) <= expense.created_at <= after
    assert expense.model_dump(mode="json")["created_at"].endswith("Z")
    listed = store.list()[0]
    assert listed.created_at == expense.created_at
    assert listed.model_dump(mode="json")["created_at"].endswith("Z")


def test_added_expense_appears_in_list(store: SqliteExpenseStore) -> None:
    expense = store.add(make())
    assert store.list() == [expense]


def test_add_without_note_stores_null(store: SqliteExpenseStore) -> None:
    data = dict(VALID)
    del data["note"]
    expense = store.add(ExpenseCreate.model_validate(data))
    assert expense.note is None
    assert store.list()[0].note is None


def test_duplicates_get_distinct_ids(store: SqliteExpenseStore) -> None:
    first = store.add(make())
    second = store.add(make())
    assert first.id != second.id
    assert {item.id for item in store.list()} == {first.id, second.id}


def test_category_case_kept(store: SqliteExpenseStore) -> None:
    store.add(make(category="  Food  "))
    assert store.list()[0].category == "Food"


def test_parallel_adds(store: SqliteExpenseStore) -> None:
    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(lambda _: store.add(make()), range(50)))
    ids = {expense.id for expense in results}
    assert len(ids) == 50
    listed = store.list()
    assert len(listed) == 50
    assert {item.id for item in listed} == ids


def test_parallel_adds_from_separate_store_instances(db_path: Path) -> None:
    stores = [SqliteExpenseStore(str(db_path)) for _ in range(5)]
    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda i: stores[i % 5].add(make()), range(50)))
    assert len({expense.id for expense in results}) == 50
    assert len(stores[0].list()) == 50


# --------------------------------------------------------------------------- list ordering


def test_list_orders_by_date_desc_then_created_desc(store: SqliteExpenseStore) -> None:
    a = store.add(make(date="2026-10-01"))
    b = store.add(make(date="2026-10-15"))
    c = store.add(make(date="2026-10-01"))
    d = store.add(make(date="2026-09-30"))
    assert [item.id for item in store.list()] == [b.id, c.id, a.id, d.id]


def test_identical_created_at_falls_back_to_insertion_order(
    store: SqliteExpenseStore, db_path: Path
) -> None:
    first = store.add(make())
    second = store.add(make())
    conn = sqlite3.connect(str(db_path))
    try:
        with conn:
            conn.execute("UPDATE expenses SET created_at = '2026-10-01T00:00:00.000000Z'")
    finally:
        conn.close()
    assert [item.id for item in store.list()] == [second.id, first.id]


# --------------------------------------------------------------------------- filters (AC-11..13, AC-17)


def test_empty_store_lists_nothing(store: SqliteExpenseStore) -> None:
    assert store.list() == []


def test_date_range_bounds_inclusive(dated: SqliteExpenseStore) -> None:
    items = dated.list(date_from=dt.date(2026, 10, 1), date_to=dt.date(2026, 10, 15))
    assert dates(items) == ["2026-10-15", "2026-10-01"]


def test_open_ended_from(dated: SqliteExpenseStore) -> None:
    items = dated.list(date_from=dt.date(2026, 10, 15))
    assert dates(items) == ["2026-10-31", "2026-10-15"]


def test_open_ended_to(dated: SqliteExpenseStore) -> None:
    items = dated.list(date_to=dt.date(2026, 10, 1))
    assert dates(items) == ["2026-10-01", "2026-09-30"]


def test_single_day_range(dated: SqliteExpenseStore) -> None:
    day = dt.date(2026, 10, 15)
    assert dates(dated.list(date_from=day, date_to=day)) == ["2026-10-15"]


def test_filter_by_category(store: SqliteExpenseStore) -> None:
    store.add(make(category="food", amount="1.00"))
    store.add(make(category="travel", amount="2.00"))
    store.add(make(category="food", amount="3.00"))
    items = store.list(category="food")
    assert sorted(item.amount for item in items) == ["1.00", "3.00"]
    assert all(item.category == "food" for item in items)


@pytest.mark.parametrize("query", ["food", "FOOD", "fOoD", "  food  "])
def test_category_filter_case_insensitive(store: SqliteExpenseStore, query: str) -> None:
    stored = store.add(make(category="Food"))
    assert store.list(category=query) == [stored]


def test_category_filter_unicode_casefold(store: SqliteExpenseStore) -> None:
    stored = store.add(make(category="Straße"))
    assert store.list(category="STRASSE") == [stored]
    assert store.list(category="ÉPICERIE") == []
    epicerie = store.add(make(category="Épicerie"))
    assert store.list(category="épicerie") == [epicerie]


def test_category_filter_is_exact_not_substring(store: SqliteExpenseStore) -> None:
    store.add(make(category="food"))
    assert store.list(category="foo") == []
    assert store.list(category="%") == []
    assert store.list(category="_ood") == []


@pytest.mark.parametrize(
    "malicious",
    [
        "' OR 1=1 --",
        "food' OR '1'='1",
        "food'; DROP TABLE expenses; --",
        '" OR ""="',
    ],
)
def test_injection_string_category(store: SqliteExpenseStore, malicious: str) -> None:
    store.add(make(category="food"))
    assert store.list(category=malicious) == []
    stored = store.add(make(category=malicious))
    assert store.list(category=malicious) == [stored]
    assert len(store.list()) == 2  # table intact


def test_combined_filters(store: SqliteExpenseStore) -> None:
    store.add(make(date="2026-10-01", category="food"))
    match = store.add(make(date="2026-10-05", category="Food"))
    store.add(make(date="2026-10-05", category="travel"))
    store.add(make(date="2026-11-01", category="food"))
    items = store.list(
        date_from=dt.date(2026, 10, 2), date_to=dt.date(2026, 10, 31), category="food"
    )
    assert items == [match]


def test_no_matches(dated: SqliteExpenseStore) -> None:
    assert dated.list(category="travel") == []
    assert dated.list(date_from=dt.date(2027, 1, 1)) == []


# --------------------------------------------------------------------------- deps.get_store


@pytest.fixture
def fresh_deps():
    deps.reset_store()
    yield deps
    deps.reset_store()


def test_import_does_not_touch_disk(tmp_path: Path) -> None:
    # A fresh interpreter, so the import really happens (no module cache).
    db_path = tmp_path / "import.db"
    env = dict(os.environ)
    env["EXPENSE_DB_PATH"] = str(db_path)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.run(
        [sys.executable, "-c", "import app.expenses.deps, app.expenses.store"],
        cwd=tmp_path,
        env=env,
        check=True,
        timeout=60,
    )
    assert not db_path.exists()
    assert list(tmp_path.iterdir()) == []


def test_get_store_uses_env_path_lazily(
    fresh_deps, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "env.db"
    monkeypatch.setenv("EXPENSE_DB_PATH", str(db_path))
    assert not db_path.exists()
    store = fresh_deps.get_store()
    assert isinstance(store, SqliteExpenseStore)
    assert store.db_path == str(db_path)
    assert db_path.exists()
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600


def test_get_store_returns_same_instance(
    fresh_deps, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EXPENSE_DB_PATH", str(tmp_path / "same.db"))
    assert fresh_deps.get_store() is fresh_deps.get_store()


def test_get_store_default_path(
    fresh_deps, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EXPENSE_DB_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    fresh_deps.get_store()
    assert (tmp_path / "expenses.db").exists()
