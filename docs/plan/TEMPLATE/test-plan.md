# Test plan: {req} {title}

<!-- Written by the plan-test-planner. Says which tests prove the work, at which level, with what data, and when
testing is done. The dev-test-writer and dev-code-reviewer follow it; QA uses it. -->

## Scope and approach
- In scope:
- Out of scope:
- Levels: unit / integration / API / end-to-end / contract

## Coverage
<!-- Every AC, NFR and security mitigation, and how it is tested. -->
| Covers | Test level | What is checked | Automated? |
| --- | --- | --- | --- |
| AC-1 |  |  | yes |

## Regression
<!-- Existing behaviour that must keep working: linked work items' ACs, suites to run, areas touched. -->
-

## Performance and load
<!-- One test per NFR target: scenario, data volume, target, how it is measured. "n/a: <reason>" if none apply. -->
| NFR | Scenario | Target | How measured |
| --- | --- | --- | --- |

## Security tests
<!-- One per mitigation in docs/design/{req}/security.md (SEC-n), plus input fuzzing and auth checks that apply. -->
| Mitigation | Test |
| --- | --- |

## UAT
<!-- The spec's UAT scenarios: steps, expected result, who or what runs them (an agent with a scripted check, or a person). -->
| Scenario | Steps | Expected |
| --- | --- | --- |

## Test data and environments
- Data:
- Environments:

## Entry and exit criteria
- Start testing when:
- Done when: all must ACs pass in automated tests; regression suite green; NFR targets met; no open high-severity findings
