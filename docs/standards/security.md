# Security standards

<!-- Agentic SDLC default. Designers, coders, reviewers and the security tester follow this. -->

- **Secrets:** never in code, logs, tests or commits. Read from the environment or a secret store. The secret scan in `sdlc check` must pass.
- **Input:** validate type, length, range and format at every boundary. Reject, don't repair.
- **Injection:** parameterised queries only; never build SQL, shell commands or HTML by string concatenation.
- **Authentication and authorisation:** every endpoint states who may call it; check permissions on the server for every request and every object (no IDOR).
- **Personal data:** collect the minimum, never log it, mask it in errors, and follow `docs/product/compliance.md`.
- **Errors:** generic messages to clients; details only in server logs.
- **Dependencies:** no known critical or high vulnerabilities (`audit` in `sdlc check`). Update rather than ignore.
- **Transport and storage:** HTTPS only outside local development; sensitive data encrypted at rest where the platform allows.
- **Limits:** rate limits and size limits on public endpoints and uploads.
- **Threat model:** changes touching auth, PII, payments or public APIs get a security review in Design (`docs/design/<REQ>/security.md`).
