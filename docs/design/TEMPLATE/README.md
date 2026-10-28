# Design: {req} {title}

Status: proposed · Spec: specs/{req}.md · Size: S / M / L

<!--
The design pack for one work item. This file is the overview and the decision; each workstream that applies has
its own file next to it, written by its own agent. Size S: this file only, one line per section, the rest "n/a".
Only the design-architect edits this file, except "Decision" (the engine).
-->

## Workstreams
<!-- Which design files this item needs. The architect ticks them; the orchestrator dispatches only those. -->
- [ ] data.md: database and data design
- [ ] api.md: API and integration design
- [ ] ux.md: UI/UX design
- [ ] operations.md: deployment, observability, scaling, recovery
- [x] lld.md: detailed technical design and test design
- [x] security.md: threat model and security design

## Context
<!-- What the spec needs, which constraints apply (from the spec, the code and docs/architecture/), with paths. -->

## Options
<!-- 2-3 real alternatives, not one good one and two straw men. -->
### Option A:
- How it works:
- Pros:
- Cons:
- Effort:

### Option B:
- How it works:
- Pros:
- Cons:
- Effort:

## Recommendation
<!-- Agent recommends; a human decides at the design gate. 2-4 sentences. -->

## High-level design
<!-- System boundary, components and responsibilities, how they talk. A mermaid diagram (C4 container/component
or flowchart) for M/L. Say which parts of docs/architecture/overview.md change. -->

### Technology choices
<!-- New libraries, services or tools: why, licence, maintenance health, alternatives. "none new" is fine. -->
| Choice | Why | Licence | Alternatives |
| --- | --- | --- | --- |

### Architecture decisions
<!-- Decisions that outlive this item (new database, framework, pattern, service boundary) get their own ADR:
`sdlc adr {req} "<decision title>"`. List them here. -->
-

## Migration, rollout and compatibility
- Data migration: <!-- expand/contract steps, backfill, how long, reversible? -->
- Backward compatibility: <!-- API versions, old clients, old data -->
- Rollout: <!-- feature flag, stages, who is told -->
- Rollback: <!-- how to undo code and data -->

## Cost and capacity
<!-- New infrastructure or paid services and their monthly cost; expected load. "no new cost" is fine. -->

## Traceability
<!-- Where each acceptance criterion lives in the design. -->
| AC | Component / endpoint / screen | Design file |
| --- | --- | --- |
| AC-1 |  |  |

## Risks
| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |

## Decision
<!-- Filled by Agentic SDLC when the design gate is approved: by whom, when, comment. -->
