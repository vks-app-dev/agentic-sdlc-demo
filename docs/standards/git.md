# Git, commits and pull requests

<!-- Agentic SDLC default. Coders and the PR responder follow this. -->

- **Branches:** `sdlc/<REQ>` for the work item, `sdlc/<REQ>-<task>` for each task (Agentic SDLC creates them).
- **Commits:** small and focused. Subject in the imperative, max 72 characters, with the work item: `REQ-012: validate expense amount`. Body says *why* when it is not obvious.
- **No noise:** no formatting-only changes mixed with logic, no generated files unless the project commits them, no secrets.
- **Pull requests:** one per work item, opened by Agentic SDLC. The description links the spec, lists the ACs covered and how it was tested.
- **Merging:** people approve and merge. Agents never force-push shared branches and never merge to the base branch themselves.
