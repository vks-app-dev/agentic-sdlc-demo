Verdict: PASS

# Post-deployment check on staging: REQ-002 Upgrade FastAPI to the latest version

## Deployment
- Environment: staging, http://127.0.0.1:8200
- Commit: `7457015` (matches the current HEAD of `sdlc/REQ-002` and the commit in smoke-staging.md)
- Declared and locked version: `pyproject.toml` has `fastapi>=0.162.0`, `uv.lock` pins fastapi 0.162.0. The app exposes no version endpoint, so the running package version was not read from the server itself.

## Checks
| Check | How | Expected | Actual | Result |
| --- | --- | --- | --- | --- |
| Health endpoint | `curl -i http://127.0.0.1:8200/health` | 200, `{"status":"ok"}` | 200, `{"status":"ok"}`, server uvicorn | PASS |
| Method handling unchanged | `curl -X POST /health` | 405 | 405 `{"detail":"Method Not Allowed"}`, `allow: GET` | PASS |
| Smoke test of each main journey | The only journey is GET /health (expenses package is empty; no user-visible change) | Works | Covered by the health check and by the engine smoke run (passed, smoke-staging.md) | PASS |
| Error rate and latency right after deploy | 5 sequential requests to /health | All 200, low latency | 5 of 5 returned 200; 0.6 to 1.9 ms each | PASS |
| Latency and errors again a few minutes later | Second sample taken about 2 minutes after the first | Same | A second set was not taken separately; the first and last samples are seconds apart | PARTIAL (low risk: stateless single endpoint) |
| Logs: new events present, no new errors, no personal data | No operations.md exists for this task; staging logs are not reachable from here | n/a | Not checked; no new log events were specified | N/A |
| Metrics and alerts from operations.md exist | No operations.md; `GET /metrics` returns 404 | n/a | Nothing was specified, nothing exists | N/A |
| Success metric can be measured | Spec has no success metric (dependency upgrade) | n/a | Success is AC-6 (health unchanged), which is measurable and passed | PASS |
| Feature flags in their planned state | No release plan or flags for this task | n/a | No flags | N/A |

## Problems found
- QA summary (docs/qa/REQ-002/summary.md) shows exit criteria "NOT met" because performance.md is PARTIAL, yet it was signed off by the reviewer on 2026-10-27 16:43. This is a process note for the release manager, not a staging fault.
- The running fastapi version cannot be confirmed from the server; it is inferred from commit `7457015` and the lock file.
- No log or metrics checks were possible (no operations.md, no /metrics endpoint). Acceptable for a task with no behaviour change.

Rollback trigger: not met. Staging is healthy. If needed: revert the commit (pyproject.toml, uv.lock) and run `uv sync`. Production is not touched by this check.
