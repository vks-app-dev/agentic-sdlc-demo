"""Non-functional requirement tests for REQ-001 (T9).

- Performance (spec NFR, Q19; ADR "Tests"): with 10,000 stored expenses, 20
  unfiltered ``GET /expenses`` calls through the in-process ``TestClient``
  have a p95 latency under 200 ms. Marked ``perf``, so the default
  ``uv run pytest`` skips it; run it with ``uv run pytest -m perf``.
- Concurrency (spec Q18 NFR; ADR "Concurrency"): 50 parallel creates yield 50
  distinct IDs and a list of 50 (also exercises AC-19: identical bodies are
  all stored as separate expenses and all counted in the total).
"""

from __future__ import annotations

import datetime as dt
import math
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.expenses.store import (
    _INSERT_SQL,
    CREATED_AT_FORMAT,
    SqliteExpenseStore,
    category_key,
)

PERF_ROWS = 10_000
PERF_CALLS = 20
PERF_P95_LIMIT_SECONDS = 0.200

PARALLEL_CREATES = 50

CATEGORIES = ("food", "Travel", "rent", "Office supplies", "health")
CURRENCIES = ("USD", "EUR", "GBP")


def _seed_rows(count: int) -> list[tuple[str, ...]]:
    """Build ``count`` varied rows matching the store's insert statement."""
    base_date = dt.date(2026, 1, 1)
    base_created = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    rows = []
    for i in range(count):
        category = CATEGORIES[i % len(CATEGORIES)]
        rows.append(
            (
                str(uuid.uuid4()),
                f"{(i % 50_000) / 100 + 0.01:.2f}",
                CURRENCIES[i % len(CURRENCIES)],
                category,
                category_key(category),
                (base_date + dt.timedelta(days=i % 365)).isoformat(),
                f"seeded note {i}" if i % 2 else None,
                (base_created + dt.timedelta(seconds=i)).strftime(CREATED_AT_FORMAT),
            )
        )
    return rows


def _bulk_insert(store: SqliteExpenseStore, rows: list[tuple[str, ...]]) -> None:
    """Insert rows in one transaction using the store's own schema and SQL."""
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        conn.executemany(_INSERT_SQL, rows)


def _p95(samples: list[float]) -> float:
    """Nearest-rank 95th percentile."""
    ordered = sorted(samples)
    rank = math.ceil(0.95 * len(ordered))
    return ordered[rank - 1]


# ------------------------------------------------------------------ performance
@pytest.mark.perf
def test_list_p95_under_200ms_with_10k_rows(
    client: TestClient, store: SqliteExpenseStore, record_property
) -> None:
    _bulk_insert(store, _seed_rows(PERF_ROWS))

    # Warm-up call (imports, first connection, page cache); not measured.
    warm = client.get("/expenses")
    assert warm.status_code == 200, warm.text
    assert len(warm.json()["items"]) == PERF_ROWS

    timings: list[float] = []
    for _ in range(PERF_CALLS):
        start = time.perf_counter()
        response = client.get("/expenses")
        timings.append(time.perf_counter() - start)
        assert response.status_code == 200, response.text

    body = response.json()
    assert len(body["items"]) == PERF_ROWS
    assert set(body["total"]) == set(CURRENCIES)

    p95 = _p95(timings)
    record_property("list_p95_ms", round(p95 * 1000, 1))
    print(f"\nGET /expenses with {PERF_ROWS} rows: p95 = {p95 * 1000:.1f} ms")
    assert p95 < PERF_P95_LIMIT_SECONDS, (
        f"p95 {p95 * 1000:.1f} ms over {PERF_CALLS} calls exceeds "
        f"{PERF_P95_LIMIT_SECONDS * 1000:.0f} ms"
    )


# ------------------------------------------------------------------ concurrency
def test_50_parallel_creates_give_50_distinct_ids_and_list_of_50(
    client: TestClient,
) -> None:
    body = {
        "amount": "1.25",
        "currency": "USD",
        "category": "food",
        "date": "2026-10-01",
        "note": "parallel",
    }
    barrier = threading.Barrier(PARALLEL_CREATES)

    def create(_: int) -> tuple[int, dict]:
        barrier.wait(timeout=30)
        response = client.post("/expenses", json=body)
        return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=PARALLEL_CREATES) as pool:
        results = list(pool.map(create, range(PARALLEL_CREATES)))

    statuses = [status for status, _ in results]
    assert statuses == [201] * PARALLEL_CREATES, results
    ids = [payload["id"] for _, payload in results]
    assert len(set(ids)) == PARALLEL_CREATES

    listing = client.get("/expenses")
    assert listing.status_code == 200, listing.text
    listed = listing.json()
    assert len(listed["items"]) == PARALLEL_CREATES
    assert {item["id"] for item in listed["items"]} == set(ids)
    assert Decimal(listed["total"]["USD"]) == Decimal("1.25") * PARALLEL_CREATES
    assert set(listed["total"]) == {"USD"}
