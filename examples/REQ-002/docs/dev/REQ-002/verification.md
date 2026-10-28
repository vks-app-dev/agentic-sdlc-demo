# Verification: REQ-002 Upgrade FastAPI to the latest version

Branch `sdlc/REQ-002` at `1674a36`. No frontend, database, migrations, config settings or integrations in scope.

| Check | How (command) | Expected | Actual | Result |
| --- | --- | --- | --- | --- |
| Fresh install | `uv sync` | succeeds | Resolved 23, checked 21 packages | PASS |
| Build | not configured | n/a | n/a | n/a |
| AC1 floor in pyproject | read pyproject.toml | `fastapi>=<latest>` | `fastapi>=0.162.0` | PASS |
| AC2 lock at latest | `uv lock --upgrade-package fastapi --dry-run` | no lockfile changes | "No lockfile changes detected"; uv.lock fastapi 0.162.0 | PASS |
| AC3 tests | `uv run pytest` | all pass, none skipped | 1 passed, 0 skipped (1 Starlette httpx deprecation warning from TestClient) | PASS |
| AC4 lint | `uv run ruff check .` | pass | All checks passed | PASS |
| AC5 secrets | `gitleaks detect --no-banner --redact` | no findings | no leaks found (21 commits) | PASS |
| Run app | `sdlc env up dev-verify --port 8090` | answers | up on 8090 | PASS |
| AC6 health | `curl -i http://127.0.0.1:8090/health` | 200 `{"status":"ok"}` | 200, `{"status":"ok"}` | PASS |
| Error path | `curl -i -X POST http://127.0.0.1:8090/health` | 405 | 405 `{"detail":"Method Not Allowed"}`, allow: GET | PASS |
| Contract | `curl /openapi.json` | only GET /health | only GET /health | PASS |
| AC7 no app/API changes | `git diff 1186dc9~2 HEAD --stat -- app tests` | none | empty diff | PASS |
| Teardown | `sdlc env down dev-verify` | stopped, data removed | stopped | PASS |

Note: "latest on PyPI" was confirmed only via `uv lock --upgrade-package fastapi --dry-run` (resolver reaches the index and found nothing newer than 0.162.0).

## Problems found
None. Minor observation (not a defect): the pytest run emits a StarletteDeprecationWarning that `httpx` with `starlette.testclient` is deprecated in favour of `httpx2`. This is in the test client dependency, not an AC failure; tests must not be changed in this item.
