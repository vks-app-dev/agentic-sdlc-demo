# Agentic SDLC demo

A small expense-tracking API, already set up with [Agentic SDLC](https://github.com/vks-app-dev/agentic-sdlc), so
you can see AI agents take real work from a request to a release, with you approving every step.

- **[`examples/`](examples/)** has two finished work items, with every document the agents wrote:
  - **REQ-001** "Record and list expenses": a *feature*, through Requirements → Design → Development.
  - **REQ-002** "Upgrade FastAPI to the latest version": a *task*, through Development → QA → Release.
- **The app** (`app/`, `tests/`) is the result of REQ-001: a FastAPI service with tests. Details are in
  [docs/APP.md](docs/APP.md).
- **The setup** shows what Agentic SDLC adds to any repo:
  - `sdlc.config.yaml`;
  - `docs/standards/` (the rules agents follow);
  - templates under `specs/` and `docs/`;
  - a local staging script (`scripts/staging.sh`);
  - a section in `CLAUDE.md`.

## Try it in 10 minutes

You need [Claude Code](https://claude.com/claude-code), [uv](https://docs.astral.sh/uv/) and git.

```bash
# 1. Install Agentic SDLC (once per machine)
uv tool install git+https://github.com/vks-app-dev/agentic-sdlc@v0.8.0
claude plugin marketplace add vks-app-dev/agentic-sdlc
claude plugin install agentic-sdlc@agentic-sdlc

# 2. Get this demo
git clone https://github.com/vks-app-dev/agentic-sdlc-demo && cd agentic-sdlc-demo
uv sync && uv run pytest -q          # the app's own tests
sdlc doctor                          # checks the setup

# 3. Open the dashboard
sdlc dashboard                       # http://127.0.0.1:8765
```

On **Home**, the panel "What your AI team can do" shows the kinds of work, and "Your AI team" shows every agent.
Press **▶ See how they work on a task** for a short walkthrough.

## Requests to try

Paste one into the box on Home and press **Ask**. You'll see what kind of work it is, which agents will do it and
where you approve. Then press **Create and start the agents**.

| Request | Kind | What happens |
| --- | --- | --- |
| *Expenses can be edited after they are recorded* | Change | Agents describe today's behaviour, write the new rules, build it with tests, then QA and Release |
| *Listing expenses fails when the category has spaces* | Bug | The bug triager reproduces it first and finds the cause; the fix comes with a regression test |
| *Let users export their expenses as CSV* | Feature | The full lifecycle: requirements, design, planning, development, QA, release |
| *Add a request ID to every log line* | Task | Straight to development, then QA and release |

While it runs, open the item on the **Board**. **Live** shows the orchestrator directing each stage and its
sub-agents working. When a stage finishes, it waits in **Waiting for you**: read the files, then approve or
send it back. After the Release approval the item is **Ready to go live**. Going live is always done by a person.

**Cost:** agent runs use your Claude Code account. A task or a small change is typically a few dollars end to end;
the dashboard shows the AI cost of each item as it goes.

**Pull requests:** these are off in this demo, so the agents don't try to push to this repository. In your own fork,
set `integrations.pull_requests: true` in `sdlc.config.yaml` (needs the GitHub CLI, `gh`) to get one pull request per
work item.

## Use it in your own repo

Install as in step 1. Then, in your repo, run `claude` and type `/agentic-sdlc:sdlc-init`. It scans your code,
asks a few questions, and adds the same setup you see here. See the
[Agentic SDLC README](https://github.com/vks-app-dev/agentic-sdlc#quick-start).

## License

MIT
