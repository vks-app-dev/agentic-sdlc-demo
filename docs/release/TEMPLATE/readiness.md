Verdict: PASS / FAIL / PARTIAL

# Release readiness: {req} {title}

<!-- Written by the rel-readiness-checker. Every row needs evidence (a file, a command and its output, a link).
The release manager reads this at the Release gate. -->

| # | Check | Evidence | Result |
| --- | --- | --- | --- |
| 1 | QA signed off; no open release blockers; non-blocking defects listed | docs/qa/{req}/summary.md |  |
| 2 | Pull request approved by a person and CI green; branch not behind the base |  |  |
| 3 | Checks passed on the commit being released | docs/dev/{req}/checks.md |  |
| 4 | Migrations reviewed, reversible, ordered with the code | docs/plan/{req}/release-plan.md |  |
| 5 | Feature flags: names, defaults (off unless the plan says otherwise), who turns them on |  |  |
| 6 | Config and secrets for staging and production listed (names only) and present where they must be |  |  |
| 7 | Rollback rehearsed on staging or locally | rollback.md |  |
| 8 | Deployed to staging and the post-deployment check passed | verification.md |  |
| 9 | Runbook, logs, metrics and alerts in place for what changed | docs/runbooks/, operations.md |  |
| 10 | Release notes and changelog written; version chosen | release-notes.md |  |

## Open items for the release manager
-
