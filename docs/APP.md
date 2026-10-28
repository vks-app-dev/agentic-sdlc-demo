# agentic-sdlc-demo

A small FastAPI service to record and list expenses (REQ-001). Data is stored
in a local SQLite file (`./expenses.db` by default, or the path in
`EXPENSE_DB_PATH`), created with mode `0600`.

## Setup

```sh
uv sync
```

## Run

```sh
uv run --with uvicorn uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

- `--host 127.0.0.1` binds to loopback only. The API is then reachable at
  `http://127.0.0.1:8000` or `http://localhost:8000`. Requests with any other
  `Host` header are rejected with 400 (protection against DNS rebinding).
- `--workers 1`: the design assumes a single worker process.
- `--no-access-log`: access log lines include query strings (for example the
  `category` filter), which are personal financial data. Keep the access log
  off, or treat it as containing personal data.

### No network exposure until authentication exists

This API has **no authentication**. Anyone who can reach the port can read
every expense and add new ones. Until an authentication work item has shipped
and passed a new security review, do **not**:

- bind to `0.0.0.0`, `::` or any non-loopback address,
- publish the port from a container (`-p 8000:8000`) or VM,
- put the service behind a reverse proxy or tunnel,
- add CORS, or add hosts to `ALLOWED_HOSTS` in `app/main.py`.

Rate limiting and pagination must also land before any network exposure.

## Development

```sh
uv run pytest
uv run ruff check .
```
