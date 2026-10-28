"""FastAPI dependencies for the expenses router.

``get_store`` builds one process-wide ``SqliteExpenseStore`` lazily on first
use, from the ``EXPENSE_DB_PATH`` environment variable (default
``./expenses.db``). Nothing touches the disk at import time, so importing the
app (e.g. ``tests/test_health.py``) never creates a database file. Tests swap
the store with ``app.dependency_overrides[get_store]``.
"""

from __future__ import annotations

import os
import threading

from app.expenses.store import ExpenseStore, SqliteExpenseStore

DB_PATH_ENV = "EXPENSE_DB_PATH"
DEFAULT_DB_PATH = "./expenses.db"

_store: SqliteExpenseStore | None = None
_lock = threading.Lock()


def get_store() -> ExpenseStore:
    """Return the process-wide expense store, creating it on first call."""
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                _store = SqliteExpenseStore(os.environ.get(DB_PATH_ENV) or DEFAULT_DB_PATH)
    return _store


def reset_store() -> None:
    """Forget the cached store so the next ``get_store`` re-reads the env."""
    global _store
    with _lock:
        _store = None
