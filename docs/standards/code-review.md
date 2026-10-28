# Code review checklist

<!-- Agentic SDLC default. The code reviewer and PR reviewer use it; edit it to match what your team checks. -->

Review in this order and report findings as **blocking** or **suggestion**:

1. **Correctness:** does it do what the task's ACs say, including the edge cases? Any off-by-one, null, concurrency or time-zone bug?
2. **Tests:** does each AC have a test that would fail without the change? Are tests meaningful, not just coverage?
3. **Security:** input validation, authorisation per object, injection, secrets, personal data in logs (see `security.md`).
4. **Design:** does it follow the approved design and the existing layering? Any duplication of existing code?
5. **Maintainability:** clear names, small functions, no dead code, comments where the *why* is not obvious (see `coding.md`).
6. **Performance:** N+1 queries, unbounded lists, work in loops that belongs outside, missing indexes for new queries.
7. **Operations:** logging, configuration, migrations that can roll back, docs updated.

Blocking means it must change before merge. Be specific: file, line, what is wrong, a suggested fix.
