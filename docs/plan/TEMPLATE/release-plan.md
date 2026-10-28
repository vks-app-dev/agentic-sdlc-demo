# Release plan: {req} {title}

<!-- Written by the plan-release-planner from the design's operations.md, security.md and README rollout section. -->

## Environment readiness
<!-- For each environment the project has (from docs/architecture/overview.md; often only local and prod at first). -->
| Environment | Config and secrets | Migrations | Access | Ready? |
| --- | --- | --- | --- | --- |
| local / dev |  |  |  |  |

## Risk register
<!-- From the spec's RAID, the design's risks and the security verdict, plus delivery risks. -->
| ID | Risk | Likelihood | Impact | Mitigation | Contingency (if it happens) |
| --- | --- | --- | --- | --- | --- |
| R1 |  |  |  |  |  |

## Release plan
- CI/CD changes: <!-- new pipeline steps, checks, secrets in CI -->
- Feature flags: <!-- name, default, who turns it on, when it is removed -->
- Migration order: <!-- before / with / after the code; expand-contract steps -->
- Release steps:
  1.
- Rollback: <!-- trigger, steps for code and data, time to roll back -->
- Release approval: <!-- which Agentic SDLC gate approves the release -->

## Monitoring and post-release verification
<!-- From operations.md. What proves the release works, checked right after deploy and again after a day. -->
| Check | How | When | Pass if |
| --- | --- | --- | --- |
| Smoke test |  | right after deploy |  |
| Error rate |  | first hour |  |

- Logs, metrics and alerts to confirm exist:
- Dashboards:
