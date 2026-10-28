# API guidelines

<!-- Agentic SDLC default. The data/API designer, coders and the doc writer follow this. -->

- **Resources:** plural nouns (`/expenses`, `/expenses/{id}`); verbs only for actions that are not CRUD (`/invoices/{id}/send`).
- **Methods:** GET reads (safe, cacheable), POST creates, PUT replaces, PATCH updates part, DELETE removes. GET never changes state.
- **Status codes:** 200 OK, 201 Created (with `Location`), 204 No Content, 400 invalid input, 401 not signed in, 403 not allowed, 404 not found, 409 conflict, 422 validation failed, 429 rate limited, 500 server error.
- **Errors:** one shape everywhere, e.g. `{"error": {"code": "amount_negative", "message": "Amount must be positive", "field": "amount"}}`. Codes are stable; messages are for people.
- **Naming:** `snake_case` (or the project's existing convention) in JSON, consistently. Dates in ISO 8601 UTC. Money as integer minor units plus currency.
- **Lists:** paginate (`limit`, `cursor` or `page`), with a maximum page size; stable default ordering.
- **Compatibility:** never remove or rename a field or change its meaning without a new version. Adding optional fields is fine.
- **Contract:** the OpenAPI (or equivalent) spec is updated in the same PR as the code.
