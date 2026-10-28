# {req}: {title}

Type: change · Status: draft · Stage: requirements · Priority: must / should / could
Updates: {links}

<!--
A change alters behaviour that already exists. Write only what changes: every section is a delta against today.
Size S → one line per section, or "n/a: <reason>". Size M/L → every section in full. Never leave a section empty.
-->

## 1. Why change it
<!-- Who asked, what is wrong or missing today, why now, and the success metric (metric, baseline → target). -->
- Reason:
- Success metric:
- Stakeholders (who asked, who approves, who is affected):

## 2. Current behaviour
<!-- Filled by the req-change-impact-analyst from the code, tests and linked specs. Cite paths. -->

## 3. Desired behaviour
<!-- What should be true after the change, in one paragraph. Users and roles affected. -->

### Business rules changed
<!-- BR-n added, changed or removed; cite the linked spec's rule ids. -->
-

### Acceptance criteria
<!-- New or changed behaviour only. Each AC gets an ID used by tests ("REQ-xxx AC-n") and a priority. -->
- **AC-1** (must)
  - Given
  - When
  - Then

### Replaces
<!-- Acceptance criteria of linked work items that this change makes untrue, e.g. "REQ-001 AC-4 → replaced by AC-2".
Every other linked AC must keep passing. Write "none" if nothing is replaced. -->
-

## 4. Workflow and user experience
<!-- Today → after, for the flows that change; exception and failure flows; changed screens, responses and messages. -->
- Today:
- After:
- Messages and UI:

## 5. Impact
<!-- Filled by the req-change-impact-analyst. -->
- Code touched:
- Existing tests that must change (and why):
- API / data compatibility (breaking for clients? migration or backfill needed?):
- Size: S / M / L
- Risk: low / medium / high, because

## 6. Quality, data and security delta
<!-- Filled by the req-nfr-analyst. Only what this change moves; "unchanged" is a valid answer. -->
- Performance, scalability, availability:
- Data (new/changed fields, sensitivity, retention, migration):
- Integrations:
- Security, privacy, compliance, audit logging:

## 7. Rollout and acceptance
- Rollout: <!-- feature flag? backward compatibility window? who must be told (clients, support)? -->
- Rollback: <!-- how to undo it, including data -->
- UAT scenarios:
- Definition of done: all acceptance criteria pass; linked ACs not in Replaces still pass; review approved;

## 8. Risks and dependencies
| Type | Item | Impact | Owner / mitigation |
| --- | --- | --- | --- |
| Risk |  |  |  |

## Open questions
<!--
How to answer (humans): write your decision on the **Answer:** line under each question and tick its box.
Answer every question marked "blocking" before scope approval.
Then run `/sdlc-reject <REQ> Apply my answers` and `/sdlc-run <REQ>`: the req-analyst folds the
answers into the acceptance criteria and moves them to "Resolved decisions". Approve after that.
-->
- [ ] **Q1 (AC-?, blocking|non-blocking):** <question, with options (a) / (b) / (c) where possible>
  **Answer:**

## Resolved decisions
<!-- Filled by the req-analyst from answered questions: "Q1: decision → affects AC-2". This is the decision log. -->
-
