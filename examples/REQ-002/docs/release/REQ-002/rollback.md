Verdict: PASS

# Rollback rehearsal: REQ-002 Upgrade FastAPI to the latest version

<!-- Written by the rel-rollback-rehearser, on staging or a local copy. Never on production. -->

## Environment
- Where: local staging, http://127.0.0.1:8200 (`scripts/staging.sh`, git worktree `.staging/app`, own database `.staging/expenses.db`). Production was not touched.
- Starting version (before this release): `5e3ff2d` (`pyproject.toml` has `fastapi>=0.110`). Staging was already deployed at the REQ-002 HEAD `7457015` when the rehearsal began, and `.staging/previous` held `5e3ff2d`, so two versions had been deployed.

## Steps
| Step | Command | Expected | Actual | Time |
| --- | --- | --- | --- | --- |
| Deploy this release (starting state) | `scripts/staging.sh deploy` (done earlier in the stage) | HEAD `7457015` healthy | `/health` returned 200 `{"status":"ok"}`; `.staging/current` = `7457015` | n/a |
| Run migrations | none | no migrations (spec and handover: "Migrations: none") | not applicable | n/a |
| Roll back code | `scripts/staging.sh rollback` | previous commit `5e3ff2d` running and healthy | `staging: 5e3ff2d on http://127.0.0.1:8200`; `/health` 200 `{"status":"ok"}`; worktree `pyproject.toml` shows `fastapi>=0.110` | about 3 s |
| Roll back data (down migrations / restore) | none | nothing to do: no schema or data change, expenses package is empty | not applicable | n/a |
| Re-deploy this release | `scripts/staging.sh deploy` | HEAD `7457015` running and healthy | `staging: 7457015 on http://127.0.0.1:8200`; `/health` 200 `{"status":"ok"}`; worktree HEAD = `745701566674de7c0c958d010d11a7b28741d087` | about 5 s |

## Result
- Time to roll back: about 3 seconds (rollback command to healthy `/health`).
- Data after rollback: intact. The change has no data or migrations, and the app has only the `/health` endpoint.
- Problems found: none. Staging ends deployed at the REQ-002 HEAD commit `7457015`.
- Limits: the previous version's dependency set was started from the worktree via `uv run`, so the rollback restored the old `pyproject.toml` and `uv.lock` state. The rehearsal did not print the installed FastAPI version on either side, only `/health` and the declared floor. The spec's own rollback (revert the commit and run `uv sync`) is equivalent in effect.
