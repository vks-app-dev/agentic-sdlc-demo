# Documentation standards

<!-- Agentic SDLC default. The doc writer and analysts follow this. -->

- Write for the next developer and the on-call engineer: what it does, how to run it, how to fix it.
- **README:** what the project is, how to install, configure, run and test it, in that order. Commands are copy-pasteable.
- **API:** the OpenAPI spec (or equivalent) is the reference; keep examples real and working.
- **Architecture:** `docs/architecture/overview.md` changes when components, data flows or integrations change. Decisions go in ADRs (`docs/adr/`).
- **Configuration:** every setting and environment variable is listed with its default in `.env.example` or the config docs.
- **Runbook:** for each new failure mode: the symptom, how to check, how to fix or roll back.
- Plain language, short sentences, active voice. Date anything that will go stale.
