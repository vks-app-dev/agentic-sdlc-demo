# Security design and threat model: {req} {title}

<!-- Filled by the design-security-reviewer, after the other workstreams. -->

## Data flow
<!-- A mermaid flowchart of the trust boundaries, entry points, stores and external systems this item touches. -->

## Threat model (STRIDE)
| Threat | Where | Severity (H/M/L) | Mitigation required |
| --- | --- | --- | --- |

## Security design
- Authentication and authorization: <!-- who may do what, where it is enforced (file) -->
- Input validation and output encoding:
- Secrets and keys: <!-- where they live, rotation; never in code or logs -->
- Sensitive data: <!-- encryption in transit and at rest, masking, logs -->
- Audit logging: <!-- events, fields, retention, tamper resistance -->
- Dependencies: <!-- new packages, known vulnerabilities -->
- Compliance: <!-- obligations from docs/product/compliance.md and how the design meets them -->

## Verdict
<!-- OK / OK with mitigations / Needs security sign-off. Then one line per mitigation the coders must implement,
labelled SEC-1, SEC-2 ...: the task planner must give each one a task, and `sdlc plan` checks that it did. -->
- SEC-1:
