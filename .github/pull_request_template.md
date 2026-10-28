<!-- agentic-sdlc:pr-template. Agentic SDLC fills the {placeholders} for agent PRs. For a PR you open by hand,
replace them yourself. Keep the headings: reviewers rely on them. -->
## {req}: {title}

**Type:** {type} · **Work item:** {documents} {links}

### Why
{summary}

### What changed
{changes}

### How to test
{how_to_test}

### Evidence
- **Checks:** {checks}
- **Traceability:** {traceability}
- **Task reviews:** {reviews}

### Tasks
{tasks}

### Risk and rollback
{risk}

### Known limitations
{limitations}

### Reviewer checklist
- [ ] The change does what the spec's acceptance criteria say, and nothing outside its scope
- [ ] Tests cover the acceptance criteria and the error paths; nothing was weakened
- [ ] No secrets, credentials or personal data in code, tests, logs or fixtures
- [ ] Migrations and config changes are reversible and documented
- [ ] Docs (API, architecture, runbook) match what was built
