"""Shared pytest fixtures (REQ-001).

``client`` is a ``TestClient`` for ``app.main.app`` whose ``get_store``
dependency is overridden with a fresh SQLite store in ``tmp_path``, so every
test starts with an empty database and nothing touches ``./expenses.db``.

Test modules may define their own ``client`` fixture (e.g. the acceptance
suite); a module-level fixture overrides this one for that module.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.expenses.deps import DB_PATH_ENV, get_store
from app.expenses.store import SqliteExpenseStore
from app.main import app


@pytest.fixture
def store(tmp_path, monkeypatch) -> SqliteExpenseStore:
    """A fresh per-test SQLite store; ``EXPENSE_DB_PATH`` points at it too."""
    db_path = tmp_path / "expenses.db"
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    return SqliteExpenseStore(str(db_path))


@pytest.fixture
def client(store: SqliteExpenseStore) -> Iterator[TestClient]:
    """TestClient bound to the per-test ``store``."""
    app.dependency_overrides[get_store] = lambda: store
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_store, None)
