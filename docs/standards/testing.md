# Testing standards

<!-- Agentic SDLC default. Agents read this before writing tests, planning tests or reviewing them. -->

## What to test
- Every acceptance criterion (`AC-n`) has at least one test that names it: `test_ac3_rejects_negative_amount` or a comment `# AC-3`.
- Test behaviour through public interfaces, not private helpers.
- Cover the edge cases the spec lists: empty, missing, invalid, duplicate, too large, unauthorised.
- A bug fix starts with a test that fails on the old code (regression test).

## How
- Tests are independent and can run in any order and in parallel. No shared mutable state between tests.
- No real network, clock or randomness: use fakes, fixed clocks and seeds.
- Use the real database engine (or an in-memory one with the same SQL) for repository tests; mock only at the edges.
- One reason to fail per test. Arrange / act / assert, in that order.
- Test names describe the behaviour: `returns_404_when_expense_missing`.

## Levels
- Unit: logic and rules, fast (milliseconds).
- Integration: the API or service with its real storage, one test per contract and error case.
- End to end: only the critical user journeys.

## Quality bar
- `sdlc check` must pass: tests, lint, typecheck and the coverage minimum in `sdlc.config.yaml`.
- Never skip, delete or weaken a test to make a build pass. A flaky test is a bug: fix it or report it.
