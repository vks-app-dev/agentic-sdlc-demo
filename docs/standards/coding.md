# Coding standards

<!-- Agentic SDLC default. Replace or edit it: agents read this file before writing or reviewing code.
Keep rules that a reviewer can check; delete what does not fit this codebase. -->

## Style
- The project's formatter and linter are the source of truth (`stack.commands.lint` in `sdlc.config.yaml`). Code that fails them is not done.
- Match the style of the file you are changing before any personal preference.
- Names say what a thing is or does: `unpaid_invoices`, not `data2`. Booleans read as questions: `is_active`, `has_access`.
- Functions do one thing. Over ~40 lines or more than ~4 parameters is a smell: split or group.
- No dead code, commented-out code or unused imports.

## Structure
- Keep the existing layering (e.g. routes → services → repositories). Do not call the database from a route handler.
- New modules go where similar code already lives. Do not create `utils`/`helpers` dumping grounds.
- Public functions and types have docstrings or comments that explain *why*, not *what*.

## Errors and edge cases
- Validate input at the boundary (API, CLI, message consumer); trust it inside.
- Never swallow errors. Catch only what you can handle; otherwise let it propagate with context.
- Errors returned to users are clear and never leak internals (stack traces, SQL, file paths, secrets).
- Handle the empty, missing, duplicate and too-large cases the spec lists.

## Data and money
- Money is stored in integer minor units or a decimal type, never floats.
- Times are stored in UTC with time zone; convert only for display.

## Dependencies
- Prefer the standard library and dependencies the project already has.
- A new dependency needs a reason in the PR: what it does, why not the existing ones, licence, maintenance.
- Pin versions through the lock file.

## Logging
- Log events, not noise: one line per meaningful event, with the work item's ids.
- Never log secrets, tokens, passwords or personal data.

## Configuration
- No secrets or environment-specific values in code. Read them from configuration or the environment, and document new ones in `.env.example`.
