# {req}: {title}

Type: feature · Status: draft · Stage: requirements · Priority: must / should / could

<!--
How much to write: size S → one line per section, or "n/a: <reason>". Size M/L → every section in full.
Never leave a section empty: empty means "not considered", and the req-ambiguity-checker will ask about it.
Facts that hold for the whole product (stakeholders, personas, data fields, integrations, regulations) live in
docs/product/. Link to them and add what is new there; don't copy them here.
-->

## 1. Business context
### Problem
<!-- Who has the problem, what it costs them, why now. Two to four sentences. -->

### Objectives and success metrics
<!-- Measurable: metric, baseline → target, how it is measured. e.g. "Expenses logged per user per week: 0 → 5 (event counts)". -->
-

### Expected benefits
<!-- The business case: time or money saved, revenue, risk removed, who benefits. -->
-

### Stakeholders
<!-- Who asked, who decides (approves this spec), who is affected. Roles from docs/product/overview.md. -->
-

## 2. Users and functional requirements
### Users and roles
<!-- Personas this touches (docs/product/overview.md) and what each role may do here. -->
-

### User story
As a <role>, I want <capability>, so that <benefit>.

### Scope
**In scope**
-

**Out of scope**
-

### Business rules
<!-- BR-1, BR-2 ...: rules that hold whatever the UI: limits, calculations, states, who may do what. ACs cite them. -->
- **BR-1**

### Acceptance criteria
<!-- Each AC gets an ID used by tests ("REQ-xxx AC-n") and a priority. Cover the main path, error paths and edge cases. -->
- **AC-1** (must)
  - Given
  - When
  - Then

## 3. Non-functional requirements
<!-- Numbers, not adjectives: "p95 < 200 ms at 10k rows", not "fast". Security and privacy are in section 6. -->
- Performance and latency:
- Scalability and capacity:
- Availability, reliability and recovery:
- Compatibility (clients, browsers, API versions, platforms):
- Accessibility and usability:

## 4. Process and user experience
### Current and future workflow
<!-- How it is done today (or "not possible today"), and how it will be done after this change. -->
- Today:
- After:

### Flows
<!-- Main flow, then exception, cancellation and failure flows. A mermaid flowchart helps for M/L. -->
1.

### UI and messages
<!-- Screens or API responses users see, validation and error messages (exact wording where it matters),
and a wireframe link or ASCII sketch. "n/a: API only" is fine. -->
-

## 5. Data and integrations
### Data
<!-- New or changed fields: name, type, required, rules, owner, sensitivity (public / internal / PII / financial / secret).
Add them to docs/product/data.md too. -->
| Field | Type | Required | Rules | Sensitivity |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

### Integrations and external dependencies
<!-- APIs, services, other teams: direction, contract owner, what happens when they fail. Add new ones to docs/product/integrations.md. -->
-

### Migration, quality, retention and deletion
<!-- Existing data to migrate or backfill, data quality rules, how long data is kept, how it is deleted on request. -->
-

## 6. Security, privacy and compliance
- Authentication and authorization:
- Sensitive data and how it is protected:
- Regulatory and contractual obligations: <!-- project.compliance in sdlc.config.yaml and docs/product/compliance.md -->
- Audit logging: <!-- which actions are logged with which fields; never log secret or personal values -->
- Risks for the threat model: <!-- abuse cases to look at; the threat model itself is written in Design -->

## 7. Testing and acceptance
- Test strategy: <!-- unit / API / end-to-end, what is hard to test and how -->
- UAT scenarios: <!-- 2-5 end-to-end scenarios a person runs to accept the feature -->
- Test data and environments:
- Definition of done: all acceptance criteria pass in automated tests; review approved; docs/product updated;
<!-- Traceability is built for you: tests name their AC as "REQ-xxx AC-n", and `sdlc trace` writes docs/rtm/{req}.md. -->

## 8. Delivery
### Assumptions, dependencies, risks and issues (RAID)
| Type | Item | Impact | Owner / mitigation |
| --- | --- | --- | --- |
| Assumption |  |  |  |

### Estimate
- Areas of the codebase touched:
- Size: S / M / L
- Risk: low / medium / high, because

## Open questions
<!--
How to answer (humans): write your decision on the **Answer:** line under each question and tick its box.
Answer every question marked "blocking" before scope approval. For non-blocking ones you may write
"accept assumption" or "defer to Design".
Then run `/sdlc-reject <REQ> Apply my answers` and `/sdlc-run <REQ>`: the req-analyst folds the
answers into the acceptance criteria and moves them to "Resolved decisions". Approve after that.
-->
- [ ] **Q1 (AC-?, blocking|non-blocking):** <question, with options (a) / (b) / (c) where possible>
  **Answer:**

## Resolved decisions
<!-- Filled by the req-analyst from answered questions: "Q1: decision → affects AC-2, AC-5". This is the decision log. -->
-
