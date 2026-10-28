Version: v0.1.0

# Release notes: REQ-002 Upgrade FastAPI to the latest version

<!-- Written by the rel-notes-writer for the people who use and support the product. Also adds an entry to
CHANGELOG.md. The version follows semantic versioning: breaking change = major, feature = minor, fix = patch. -->

## What's new
- Nothing new for users in this release. This is a maintenance upgrade of the web framework the API is built on.

## Changes and fixes
- The FastAPI framework is upgraded to 0.162.0 (from 0.161.1), picking up the upstream security and bug fixes in that line.
- The declared minimum FastAPI version is raised to 0.162.0 so it matches the version actually in use.
- No change to the API responses. GET /health still returns `{"status": "ok"}` with HTTP 200.

## Breaking changes and actions needed
none

## Known issues
- None open. The QA report records no open defects.

## Deployment
- Migrations: none.
- Feature flags: none.
- Config: none to change at runtime. The dependency floor in `pyproject.toml` is now `fastapi>=0.162.0`. Run `uv sync` after pulling.

## Approval
<!-- Written by SDLC Pilot when the Release gate is approved. -->
