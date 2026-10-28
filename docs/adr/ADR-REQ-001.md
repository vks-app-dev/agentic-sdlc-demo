# ADR-REQ-001: Record and list expenses

Status: proposed · Spec: specs/REQ-001.md

## Context
**What the spec needs.** `POST /expenses` to create an expense and `GET /expenses` to list them, with optional `from`/`to` (inclusive) and `category` filters and a per-currency total. Answers recorded in the spec's Open questions are treated as binding here. The spec's "Resolved decisions" section has not been filled in yet, so some ACs still use the old wording (see the end of this section).

**Existing code.**
- `app/main.py` (lines 1-8): `app = FastAPI(title="Expense API")` and `GET /health`. No routers, no persistence, no error handlers, no settings module.
- `tests/test_health.py`: builds `TestClient(app)` at module level and does not use the lifespan context. Any design that needs startup hooks must still let this test pass unchanged.
- `pyproject.toml`: the only runtime dependency is `fastapi>=0.110`. `uv.lock` pins fastapi 0.161.1, pydantic 2.14.1 and starlette 1.9.0. `requires-python = ">=3.11"`, but the spec NFR says 3.12. Nothing in this design needs more than 3.11.
- There are no earlier ADRs, so there is no house pattern for storage, layering or errors yet. This ADR sets that pattern.

**Binding decisions from the spec answers.**
| Topic | Decision (spec Q#) |
| --- | --- |
| Storage | SQLite, persistent across restarts (Q4), single worker (Q18) |
| Paths and params | `/expenses`, `from`, `to`, `category` (Q7) |
| Amount on the wire | JSON string only, e.g. `"12.50"` (Q9a). At most 2 decimals and > 0 (AC-4). No upper limit (Q5) |
| Total | Always a map keyed by currency. An empty result gives `{}` (Q8a) |
| Errors | One shape for every 4xx: `{"error": {"code", "message", "fields": [{"field", "message"}]}}`. Validation errors use 422. Submitted input is never echoed (Q10) |
| Category | Free text (Q2). Trimmed, then 1-50 characters. Stored with case kept. Filtering is case-insensitive (Q11, AC-17) |
| Currency | Must match `^[A-Z]{3}$`. No normalisation (AC-6, Q11). No whitelist (Q5) |
| Note | Trimmed. An empty note is stored as `null`. At most 500 characters (Q11, AC-8) |
| Date | Strict `YYYY-MM-DD` calendar date. Future dates are allowed (Q3, Q13) |
| ID / timestamps | UUID v4 string. `created_at` is in UTC, ISO 8601 (Q12) |
| Order | `date` descending, then `created_at` descending (Q6, Q12) |
| Body edge cases | null, wrong type, extra field, empty body, malformed JSON and non-object body all return 422 (Q14) |
| Filter edge cases | An empty value counts as not supplied. A repeated `category` returns 422. `from == to` is valid (Q15) |
| Concurrency | 50 parallel creates yield 50 distinct IDs (Q18 NFR) |
| Tests | The store is injected through a FastAPI dependency. Each test uses its own temp SQLite file (Q20). The perf test is marked `perf`, with p95 < 200 ms over 20 calls on 10k rows (Q19) |
| App shell | `/health` (200 and body) and the app title stay unchanged. The router lives in `app/expenses/` (Q21) |

**Points still open for the design gate (I assumed an answer; please confirm or override).**
1. *Amount formatting.* AC-5 says "returned exactly as submitted", but the Q9 answer did not say whether `"12.5"` comes back as `"12.5"` or `"12.50"`. **Assumed:** accept 0-2 decimals and always return 2 decimals (`"12.5"` is returned as `"12.50"`). Totals are also returned with 2 decimals. Inputs submitted with 2 decimals (all inputs used in the ACs) are returned unchanged.
2. *Amount bound.* Q5 says "no limit", but the security NFR says "input is validated and bounded in length". **Assumed:** there is no numeric maximum, but the amount string is capped at 32 characters, so the bound is on length rather than value.
3. *Stale AC wording.* AC-9 and AC-10 still say a total of `20.00` / `0`. Under Q8a they become `{"USD": "20.00"}` / `{}`. The requirement-analyst should restate them. Coders will implement Q8a.
4. *Security review.* Notes are free text and expense data is personal financial data. This matches the `pii` trigger in `sdlc.config.yaml` (`security_review_on: [auth, pii]`). **I recommend running the security review for this item.**

## Options
Q4 already fixes SQLite as the engine. What is new to the project, and so laid out here for a human to pick, is how we talk to SQLite, how money is stored and summed, and how the schema evolves.

### Option A: stdlib `sqlite3` repository, amount stored as canonical decimal TEXT, totals computed in Python with `Decimal`
- How it works: A small `SqliteExpenseStore` class wraps the stdlib `sqlite3` module and opens a short-lived connection per call. Filters (`date` range, `category_key`) and ordering run in SQL with bound parameters. Amounts are stored as TEXT in canonical 2-decimal form. The list endpoint already loads every matching row (there is no pagination), so totals are summed in Python with `decimal.Decimal`, grouped by currency. The schema is created idempotently on first use, and `PRAGMA user_version` records the schema version.
- Pros: No new dependency. Exact decimal arithmetic with no overflow, so Q5 "no limit" holds. Very little code, and easy to read and test. Per-call connections avoid sharing a connection across threads in FastAPI's threadpool.
- Cons: Hand-written SQL. There is no migration tooling beyond `user_version`. SQL cannot do numeric comparison or aggregation on amounts, which is not needed for this item. If pagination is added later, totals must be computed in a separate pass.
- Effort: S-M (about 1.5-2 dev days including tests).

### Option B: stdlib `sqlite3` repository, amount stored as INTEGER minor units (cents), totals computed with SQL `SUM ... GROUP BY currency`
- How it works: Same store and connection approach as Option A, but `"12.50"` is stored as `1250` INTEGER. Totals come from `SELECT currency, SUM(amount_minor) ... GROUP BY currency` with the same WHERE clause. Values are converted back to a 2-decimal string at the API edge.
- Pros: No new dependency. Exact integer arithmetic. Aggregation in SQL survives the addition of pagination without loading all rows. Amounts can be compared and indexed numerically.
- Cons: SQLite INTEGER is a signed 64-bit value, so the single-amount and total limit is about 9.2e16 major units. `SUM` raises `integer overflow`, which would surface as a 500 unless caught. That contradicts "no limit" (Q5), so a bound or an overflow error contract would have to be added to the spec. Hard-coding scale 2 means JPY/KWD support later needs a per-currency scale column and a data migration. Each request needs two queries (rows and totals).
- Effort: M (about 2 dev days, plus the spec change for the bound).

### Option C: SQLAlchemy 2.0 Core + Alembic migrations, amount stored as TEXT (or a custom `TypeDecorator` to `Decimal`)
- How it works: Add `sqlalchemy` (and `alembic`) as runtime dependencies. A `Table` definition plus a repository using Core `select()` with bound parameters. Alembic manages the schema with a first revision that creates `expenses`. A session or connection is provided through a FastAPI dependency. Totals are computed as in Option A (SQLAlchemy's `Numeric` on SQLite goes through float, so it must not be used for money).
- Pros: Versioned migrations from day one. Portable if the project later moves to Postgres. Parameterisation is the default. It is a familiar pattern for future contributors.
- Cons: Two new runtime dependencies plus migration scaffolding (`alembic.ini`, `migrations/`) for a single table. More setup in tests (run migrations per temp DB). Monetary handling still needs custom care because `Numeric` on SQLite is not exact. That is more moving parts than the spec asks for ("smallest design").
- Effort: M (about 2.5-3 dev days).

## Recommendation
**Option A.** It meets every acceptance criterion and the binding answers with no new dependencies. It also keeps "no limit" on amounts literally true, because Python `Decimal` sums cannot overflow, while Option B needs a spec change to add an upper bound. Since the list is unpaginated, summing the already-fetched rows in Python costs nothing extra at the 10k-row NFR. Choose Option C instead if the team already expects a move to Postgres or several more tables soon. Option A's `user_version` scheme can be replaced by Alembic later without changing the API.

## Design
(For Option A.)

### Components and responsibilities
| Module | Responsibility |
| --- | --- |
| `app/main.py` | Unchanged title and `/health`. Adds `app.include_router(expenses_router)` and `register_error_handlers(app)`. |
| `app/errors.py` | `ApiError` envelope models. Exception handlers for `RequestValidationError` (422, `code="validation_error"`) and `StarletteHTTPException` (any 4xx, e.g. `not_found`, `method_not_allowed`), all in the Q10 shape. Builds `fields` from `loc`/`msg` only and **never** includes `input` or `ctx`. Logs nothing about the request body. |
| `app/expenses/__init__.py` | Exports `router`. |
| `app/expenses/schemas.py` | Pydantic v2 models: `ExpenseCreate` (`extra="forbid"`, validators below), `Expense` (response), `ExpenseList` (`items`, `total`). Shared validators: `parse_amount`, `parse_iso_date`. |
| `app/expenses/store.py` | `ExpenseStore` protocol (`add(ExpenseCreate) -> Expense`, `list(date_from, date_to, category) -> list[Expense]`) and `SqliteExpenseStore(db_path)`. Owns the schema creation and all SQL. |
| `app/expenses/router.py` | `APIRouter(prefix="/expenses")`. Request-level checks (repeated `category`, empty-as-absent, `from > to`). Sums totals with `Decimal`. |
| `app/expenses/deps.py` | `get_store()` returns a process-wide `SqliteExpenseStore`, built lazily from the `EXPENSE_DB_PATH` env var (default `./expenses.db`). Tests use `app.dependency_overrides[get_store]` with a `tmp_path` DB. Nothing touches disk at import time, so `tests/test_health.py` is unaffected. |
| `tests/conftest.py` | Fixture `client` that overrides `get_store` with a fresh temp-file store per test. Registers the `perf` marker. |
| `pyproject.toml` | Only `[tool.pytest.ini_options] markers = ["perf: ..."]` and `addopts = "-m 'not perf'"`. No dependency changes. |
| `.gitignore` | Add `*.db`, `*.db-wal`, `*.db-shm`. |

### Validation rules (`ExpenseCreate`)
- `amount`: strict `str` (a JSON number is a type error, so 422). Must match `^(0|[1-9][0-9]*)(\.[0-9]{1,2})?$`, be 32 characters or fewer, and have `Decimal(value) > 0`. This rejects `"0"`, `"-1"`, `"abc"`, `"12.500"`, `"1e1"`, `"NaN"`, `"Infinity"`, `" 12.50 "` and `""`. The value is normalised to `Decimal.quantize(Decimal("0.01"))`.
- `currency`: strict `str`, `^[A-Z]{3}$`.
- `category`: strict `str`, trimmed, then 1-50 characters (counted in Python `len`, i.e. code points).
- `date`: strict `str`, `^\d{4}-\d{2}-\d{2}$`, then `datetime.date.fromisoformat`. An invalid calendar date returns 422. Datetimes, time zones and integers are rejected by the regex or the strict type.
- `note`: optional strict `str | None`, trimmed, at most 500 characters. An empty result becomes `None`.
- `model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)`. Trimming is explicit per field so that `amount`/`currency` are not trimmed silently.
- Error messages are fixed strings per rule (e.g. "must be a positive decimal string with at most 2 decimal places"). The submitted value is never interpolated.

### API contracts
**`POST /expenses`**
Request (`application/json`):
```json
{"amount": "12.50", "currency": "USD", "category": "food", "date": "2026-10-01", "note": "lunch"}
```
`201 Created`:
```json
{"id": "6f1c...-uuid4", "amount": "12.50", "currency": "USD", "category": "food",
 "date": "2026-10-01", "note": "lunch", "created_at": "2026-10-23T09:15:02.123456Z"}
```
`422`: Q10 envelope, e.g.
```json
{"error": {"code": "validation_error", "message": "Request validation failed",
  "fields": [{"field": "amount", "message": "Field required"}]}}
```
`field` is the dotted `loc` with the `body` / `query` prefix removed (`amount`, `from`). Malformed JSON, an empty body or a non-object body give `field: "body"`.

**`GET /expenses?from=YYYY-MM-DD&to=YYYY-MM-DD&category=text`** (all optional)
`200 OK`:
```json
{"items": [ {...Expense...}, ... ], "total": {"USD": "20.00", "EUR": "20.00"}}
```
- `items` is ordered by `date` DESC, then `created_at` DESC, then `rowid` DESC (a final tie-break for identical timestamps under parallel inserts).
- `total` has one key per currency present in `items`, with a 2-decimal string value. No matches gives `{"items": [], "total": {}}`.
- `422` (same envelope) is returned for: an invalid `from`/`to` (same strict date rule as the body), `from > to` (`fields: [{"field": "from", "message": "must be on or before 'to'"}]`), or a repeated `category`.
- Empty `from=`, `to=` or `category=` (and a whitespace-only `category`) count as not supplied.

**Other 4xx** (unknown path, wrong method) return the same envelope with `code` `not_found` / `method_not_allowed`. `/health` is unchanged.

### Data model / migrations
SQLite file at `EXPENSE_DB_PATH`. On first `SqliteExpenseStore` construction: `PRAGMA journal_mode=WAL`, then, if `PRAGMA user_version` = 0, run this in one transaction and set `user_version = 1`:
```sql
CREATE TABLE IF NOT EXISTS expenses (
  id           TEXT PRIMARY KEY,          -- uuid4 string
  amount       TEXT NOT NULL,             -- canonical 2dp decimal, e.g. '12.50'
  currency     TEXT NOT NULL,             -- ^[A-Z]{3}$
  category     TEXT NOT NULL,             -- trimmed, case kept
  category_key TEXT NOT NULL,             -- category.casefold(), used for filtering
  date         TEXT NOT NULL,             -- 'YYYY-MM-DD' (lexical order = date order)
  note         TEXT,                      -- NULL when absent/empty
  created_at   TEXT NOT NULL              -- UTC '%Y-%m-%dT%H:%M:%S.%fZ' (fixed width, sortable)
);
CREATE INDEX IF NOT EXISTS ix_expenses_date ON expenses(date);
CREATE INDEX IF NOT EXISTS ix_expenses_category_key ON expenses(category_key);
```
- `category_key` uses Python `str.casefold()` because SQLite `LOWER()`/`NOCASE` only fold ASCII. The filter compares `category_key = ?` with `filter.strip().casefold()`.
- Future schema changes bump `user_version` with ordered, idempotent steps in `store.py`. There is no existing data to migrate.
- Connections: `sqlite3.connect(path, timeout=5)` per store call, closed with `contextlib.closing`. Writes use `with conn:` for the transaction. The busy timeout makes the 50 parallel creates in the NFR wait instead of failing. All SQL uses `?` placeholders. The WHERE clause is built only from a fixed set of fragments and never from user strings.

### Sequence of calls
**Create**: client `POST /expenses`, then FastAPI parses the JSON into `ExpenseCreate` (on failure, `RequestValidationError` goes to `errors.py` and a 422 envelope is returned with nothing stored). Next, `router.create` gets `store` from `Depends(get_store)` and calls `store.add(payload)`, which generates `uuid4()`, `created_at = datetime.now(UTC)` and `category_key`, then runs `INSERT` (parameterised) and commits. It returns `Expense`, and the router responds 201.

**List**: client `GET /expenses?...`, then `router.list_expenses(request, from_, to, category, store)`:
1. Reject if `request.query_params.getlist("category")` has more than one value (422).
2. Map empty or whitespace-only values to `None`. Parse `from`/`to` with `parse_iso_date` (422 on failure).
3. If both are set and `from > to`, return 422.
4. `store.list(from_, to, category)` runs `SELECT ... WHERE [date >= ?] AND [date <= ?] AND [category_key = ?] ORDER BY date DESC, created_at DESC, rowid DESC`.
5. The router folds `items` into `dict[currency, Decimal]` and formats each value with 2 decimals.
6. Return 200 with `ExpenseList`.

## Security review
<!-- Filled by the security-reviewer: STRIDE, authn/authz, PII, OWASP. -->
**Scope.** Reviewed Option A. Entry points: `POST /expenses` and `GET /expenses`, plus the global 4xx handler in `app/errors.py`. Data flows: client JSON to `ExpenseCreate` to `SqliteExpenseStore`, and SQLite to the router (Decimal totals) to JSON. Store: the SQLite file at `EXPENSE_DB_PATH`, with its `-wal`/`-shm` files. Trigger: `pii` (`security_review_on: [auth, pii]`). `project.compliance` is empty, so no regulatory regime applies.

**Authn/authz.** None. `app/main.py` has no middleware, dependencies or security schemes, and the spec defers auth on purpose. Anyone who can reach the port can read every expense and add new ones. That is acceptable only for a single user on loopback, so the first two rows below are deployment conditions for this design.

**PII.** `note` (free text), `category` and the amount/date history are personal financial data. The design already avoids echoing input in 422 bodies and logging request bodies. The rows below close the remaining leak paths (tracebacks, reflected keys, file permissions).

| Threat | Where | Severity (H/M/L) | Mitigation required |
| --- | --- | --- | --- |
| S/E/I: No authentication. Any network client can read all financial data and write records (OWASP A01 Broken Access Control, A07 Identification and Authentication Failures) | Both `/expenses` routes; how the server is run | H | Serve on loopback only. Keep uvicorn's default `--host 127.0.0.1` and state in the README and run command that binding to `0.0.0.0`, a container port or a reverse proxy is not allowed until an auth work item ships. The design gate must record that this residual risk is accepted. |
| S/I: DNS rebinding. A malicious web page rebinds its host name to 127.0.0.1 and reads `GET /expenses` as same-origin, so loopback binding alone does not stop it | `app/main.py` | M | Add `TrustedHostMiddleware(allowed_hosts=["localhost", "127.0.0.1", "testserver"])`. Do not add `CORSMiddleware`, and never use a wildcard origin. Simple cross-site `POST` requests are already rejected: FastAPI parses only `application/json` bodies, so `text/plain` gets a 422. Add a test that this stays true. |
| D/T: A Decimal context overflow can break the list endpoint permanently. The default context has `prec=28`. A 32-character amount such as `"9"*32` makes `quantize(Decimal("0.01"))` raise `InvalidOperation`, which surfaces as a 500. Two 26-digit amounts are accepted, but their sum rounds silently (wrong total) and then the total's `quantize` raises. Edit and delete are out of scope, so such rows cannot be removed and every unfiltered list returns 500 from then on | `parse_amount`, the router's total fold | H | Do all money arithmetic in one module-level `decimal.Context(prec=64, traps=[InvalidOperation, Inexact, Overflow, DivisionByZero])` for parsing, quantising and summing. 64 digits covers 32-character amounts times any realistic row count. Format with `format(d, "f")`, never `str()`, to avoid exponent notation. Tests: `"9"*32` is accepted or cleanly rejected (never a 500), and two `"9"*29 + ".99"` rows give an exact total. The other way out is to cap integer digits (for example 15), but that needs Q5 to be reopened. |
| D: Request body size is unbounded. Starlette reads the whole body and parses the JSON before Pydantic's length checks run (OWASP A04 Insecure Design / unrestricted resource consumption) | `POST /expenses` | M | Reject bodies over 16 KiB before parsing with a small middleware: check `Content-Length` and count bytes while streaming. Return 413 in the Q10 envelope (`code: "payload_too_large"`). The valid maximum body is about 2.5 KB. |
| D: Unbounded writes and lists. No rate limit, no row cap and no pagination, so an unauthenticated writer can fill the disk and make each `GET` heavier | `POST`/`GET /expenses` | L (loopback) / H (if exposed) | Accepted for loopback, single user (Q16, Q17). Pagination and rate limiting must come before any network exposure, together with the auth item. |
| I: PII in logs through tracebacks. Pydantic `ValidationError.__str__` includes `input_value`, so a `ResponseValidationError`, or a handler that logs `exc`, would write `note` to the logs. The uvicorn access log writes query strings, including `category` | `app/errors.py`, uvicorn logging | M | Handlers must not log `exc`, `exc.errors()` or `exc.body`. Add a catch-all `Exception` handler that returns a generic 500 envelope and logs only the exception type and request path. Keep `debug=False`. Treat access logs as containing personal data (`category`), or turn them off with `--no-access-log`. Test: the `note` text appears in neither 422/500 bodies nor `caplog`. |
| I: Reflected input in 422 `fields`. With `extra="forbid"`, `loc` holds the client-supplied unknown key, which may be arbitrarily long and contain PII. That breaks the Q10 rule against echoing input | `app/errors.py` field mapping | L | For `extra_forbidden` errors, report `field: "body"` with the message "unknown field". Otherwise cap `field` at 64 characters. Build `field` only from known model field names. |
| I: The database file is world-readable at rest. SQLite creates it with the process umask (typically `0644`), and `-wal`/`-shm` copy its mode. The data is unencrypted. The default `./expenses.db` sits in the working directory | `SqliteExpenseStore.__init__`, `deps.py` | M | Before the first `connect`, create the file with `os.open(path, os.O_CREAT, 0o600)`, or set `os.umask(0o077)` around creation. Test that the mode is `0600`. Keep `*.db*` in `.gitignore`. Accept the lack of encryption at rest as residual risk for single-user local use (rely on OS disk encryption). SQLCipher or app-level encryption is a follow-up if the data ever leaves the user's machine. |
| T: SQL injection (OWASP A03 Injection) | `store.py` | L | The design already requires `?` placeholders for all values and a WHERE clause built only from fixed fragments. Also: no `LIKE`, no f-string SQL, and `ORDER BY` stays fixed. The code reviewer should check this, and a test should use a `category` of `' OR 1=1 --`. |
| T: Stored content injection. `note`/`category` accept control characters, NUL, bidi overrides and HTML. They are harmless in this JSON API, but a future UI or CSV export could be exposed to them | `ExpenseCreate` validators | L | Reject C0/C1 control characters (`\x00-\x1f`, `\x7f-\x9f`) in `category` and `note`. Responses stay `application/json` only. Any future renderer must output-encode. |
| T: Validation bypass through Unicode digits. `\d` matches non-ASCII digits in both Python and Pydantic (Rust) regex | `date` and `from`/`to` regex | L | Use `^[0-9]{4}-[0-9]{2}-[0-9]{2}$`. The amount regex already uses `[0-9]`. Apply `max_length` before the pattern and Decimal parsing (`StringConstraints(max_length=32, pattern=...)`). The amount regex is anchored with no nested quantifiers, so it has no ReDoS risk. |
| R: No actor or audit trail. The only record is `created_at` | Store | L | Accepted. There is one user and no edit/delete, so the table is append-only. Revisit with the auth item, when a user ID per row is needed. |
| I: OpenAPI `/docs` and `/openapi.json` are public | `app/main.py` | L | Accepted on loopback. Turn them off (`docs_url=None, openapi_url=None`) or protect them before network exposure. |

**32-character amount cap.** A length bound on the string is a sound DoS control, and with an anchored linear regex it is cheap to enforce. On its own, though, it does not bound arithmetic. The 32-character cap is above the default Decimal precision of 28 digits, which is the H finding above. Keep the cap, enforce it before the regex, and fix the Decimal context. Category (50) and note (500) are measured in code points, which is at most about 2 KB of UTF-8, so those bounds are fine.

**Verdict: OK with mitigations.** The two H rows are required before merge: the Decimal context fix, and loopback-only serving with the risk explicitly accepted at the design gate. The M rows are required in this item's task plan. Exposing the service beyond loopback is **not** covered by this review and needs authentication plus a fresh security sign-off.

## Risks
| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Blast radius: changes to `app/main.py` break `/health` or the title (AC-20) | Low | Medium | `main.py` only gains `include_router` and handler registration. The existing `test_health.py` stays untouched. Add an assertion for the 200 status and the OpenAPI title. |
| Global 4xx handler changes the error body for routes outside `/expenses` | Low | Low | This is intended by Q10 ("every 4xx"). `/health` has no error paths. Covered by a test for an unknown path. |
| Float leaks into money (Pydantic lax coercion, SQLite REAL affinity, `json` encoding) | Medium | High | Strict `str` amount, TEXT column, `Decimal` only, response fields typed `str`. AC-5 test (`0.10 + 0.20 == "0.30"`) plus a test that a JSON number amount returns 422. |
| Validation errors echo `note` or other input in the body or logs | Medium | Medium (PII) | Custom handler builds `fields` from `loc`/`msg` only. Fixed messages. No request-body logging. A test asserts the note text is absent from 422 bodies. |
| Pydantic lax date parsing accepts datetimes or timestamps | Medium | Low | Regex check before `fromisoformat`, with a strict `str` type. Tests cover `2026-10-01T00:00:00`, `1696118400` and `10/01/2026`. |
| SQLite `database is locked` under parallel creates | Low | Medium | WAL mode, `timeout=5`, short transactions, single worker (Q18). The 50-parallel-creates test enforces it. |
| Multiple uvicorn workers or several processes on the same file | Low | Low | SQLite with WAL is safe across processes. Single worker is still the documented setup. |
| Performance: 10k unpaginated rows serialised per request | Low | Medium | Indexed filters. Pydantic v2 serialisation of 10k small objects is expected to stay well under 200 ms in-process. Enforced by the `perf`-marked test (Q19). If it fails, return rows as tuples and build the response model once. |
| No amount upper bound (Q5): very large strings or values | Low | Low | 32-character length cap. `Decimal` sums cannot overflow. Confirm at the gate (Context, item 2). |
| Backward compatibility of the DB file across releases | Low | Low | `PRAGMA user_version` versioning from v1. There is no existing data. Option C (Alembic) remains a drop-in later. |
| Spec text still contradicts Q8a (AC-9/AC-10 scalar totals) | High | Low | Flagged in Context, item 3. The requirement-analyst should restate the ACs before the task plan. |
| Personal financial data at rest is unencrypted in a local SQLite file | Medium | Medium | Out of scope for this item (no auth, single user). Flagged for the security reviewer. `*.db` is added to `.gitignore` so data is never committed. |
| Security (H): the unauthenticated API exposes all personal financial data to anyone who can reach the port | Medium | High | Serve on loopback only (`127.0.0.1`), add `TrustedHostMiddleware` against DNS rebinding, and add no CORS. Record risk acceptance at the design gate. Any network exposure first needs an auth work item and a new security sign-off. See Security review. |
| Security (H): default Decimal precision (28) is below what the 32-character amount cap allows. `quantize` and sums raise `InvalidOperation` (500) or round silently, and one stored row can break `GET /expenses` for good, since there is no delete | Medium | High | Do all money arithmetic in a dedicated `decimal.Context(prec=64)` that traps `Inexact`/`InvalidOperation`/`Overflow`, and format with `format(d, "f")`. Add tests with 32-character and near-limit amounts and their totals. See Security review. |

## Task plan
<!-- Summary of .sdlc/plans/REQ-001.json written by the task-planner. -->
Planned against Option A, including all security-review mitigations (H and M rows).
- T1: Money module (`app/money.py`): Decimal context prec=64 with traps, parse/quantize/sum, `format(d, "f")`. Covers AC-4, AC-5 and AC-18
- T2: Error envelope and handlers (`app/errors.py`): 422/4xx envelope, no input echoed, catch-all 500 that logs only the type and path. Covers AC-3
- T3 (after T1): Expense schemas (`app/expenses/schemas.py`): strict validators, control-character rejection, ASCII date regex. Covers AC-2, AC-3, AC-4, AC-6, AC-7 and AC-8
- T4 (after T2): 16 KiB body-size limit middleware (`app/middleware.py`) that returns a 413 envelope
- T5 (after T3): `SqliteExpenseStore` and `get_store` (`store.py`, `deps.py`): DB file with mode 0600, WAL, parameterised SQL, `.gitignore`. Covers AC-1, AC-11, AC-12, AC-13, AC-17 and AC-19
- T6 (after T2, T5): `POST /expenses` router, `main.py` wiring, `conftest.py`. Covers AC-1, AC-2, AC-3, AC-4, AC-6, AC-7, AC-8, AC-19 and AC-20
- T7 (after T6): `GET /expenses` with filters and per-currency totals. Covers AC-5 and AC-9 to AC-18
- T8 (after T4, T6): Hardening in `main.py`: TrustedHostMiddleware, body limit mounted, no CORS. Adds a README run command that binds to 127.0.0.1 only, plus PII and logging tests. Covers AC-20
- T9 (after T7): NFR tests: `perf` marker in `pyproject.toml`, 10k-row p95 < 200 ms, 50 parallel creates. Covers AC-9 and AC-19

Longest chain: T1 -> T3 -> T5 -> T6 -> T7 -> T9 (6 tasks). T7 and T8 can run in parallel because they edit different files.

## Decision
<!-- Filled at approval: chosen option, by whom, date. -->
