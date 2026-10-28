Verdict: PASS

# User acceptance testing: REQ-002 Upgrade FastAPI to the latest version

<!-- Written by the qa-uat-tester acting as the business user. The human who approves the QA gate makes the
acceptance decision; this report is the evidence. -->

The spec has no section 7 UAT scenarios and no named persona (type: task, no user-visible change). The scenario below is the business-user view: the service owner wants the dependency current and the service behaving exactly as before.

## Scenarios
| Scenario | As (role) | Steps | Expected business outcome | Actual | Result |
| --- | --- | --- | --- | --- | --- |
| Service still works after upgrade | Service owner / API consumer | `sdlc env up uat --port 8104`; `curl -i http://127.0.0.1:8104/health` | 200 and `{"status":"ok"}` (AC-6) | 200 OK, body `{"status":"ok"}` | PASS |
| Declared floor matches real version | Service owner | Read pyproject.toml and uv.lock | Floor equals locked version (AC-1, AC-2) | `fastapi>=0.162.0` in pyproject.toml; uv.lock pins fastapi 0.162.0 | PASS |
| Quality gates and no user-visible change | Service owner | Reviewed checks.md and verification.md (AC-3 to AC-5, AC-7) | Tests, lint and secret scan pass; no app or test changes | Checks passed at f1306c6 (1 test, none skipped); verification reports an empty app/tests diff | PASS (relied on dev evidence, not re-run by me) |

Not independently verified: that 0.162.0 is the newest release on PyPI. Dev evidence relies on a resolver dry-run, and I had no separate PyPI check.

## Business objectives
The spec defines no success metrics. Its stated aim is to keep current on security and bug fixes and to stop the declared floor lagging the real version.
| Metric | Measurable? | How |
| --- | --- | --- |
| Declared floor equals locked version | Yes | Compare pyproject.toml with uv.lock, or run `uv lock --upgrade-package fastapi --dry-run` and expect no changes |
| No behaviour change | Yes | GET /health returns 200 `{"status":"ok"}`; pytest passes |

## Observations (not defects)
- docs/rtm/REQ-002.md shows "No acceptance criteria found in the spec" (0/0). It was generated before T2 numbered AC-1..AC-7, so it is stale. Regenerate it with `sdlc trace REQ-002` before the gate. The handover has the same 0/0 line.
- Pytest emits a Starlette deprecation warning about httpx in TestClient. It comes from the dependency, and the spec forbids changing tests here.

## Defects
- None
