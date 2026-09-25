# NOTES — observability-dashboard

Cross-task learnings and the machine-read ledger for this kit. Ledger tokens quoted in prose
are always backticked.

## Run 2026-09-25-7e3a (interactive, autonomy advisory)

- Branch `kit/observability-dashboard`. The test-isolation fix (`fix/tests-isolate-data-home`,
  4c86459) is merged locally at 0d47a47 so the data-home canary guards every new test module;
  it still reaches `main` through its own PR.
- Dispatch vehicle: the session had registered its agent types before the kit's
  `.claude/agents/observability-dashboard-*.md` files existed, so T1's implementer ran as
  `general-purpose` on sonnet, told to load its agent file as operating instructions. The
  kit's agent types registered while T1 ran; every later dispatch uses them, so the
  read-only roles carry their `tools:` pin. The orchestrator still snapshots the tree before
  each read-only dispatch and compares it after; an unexpected change is that agent's defect.
- Open user decisions taken at the architect's defaults: transcript-priced scorecard dollars
  on by default (`--no-transcripts` opts out, PLAN D15); the journal panel renders the
  journal's own priced total under its own label (T6 brief, item 2).

`agent:` lines below record each dispatch as it returns.

agent: T1 id=a6ccfc1fbf532a88e role=implementer model=sonnet
agent: T1 id=afd2e482fc46f7555 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
agent: T1 id=a0f6f482b86af3804 role=red-team model=sonnet findings=1 confirmed=1 marginal=1 result=accepted
defect: T1 kind=unspecified-path

- T1 red-team break (confirmed): `docs/GUIDE.md` lists the stores `runtime_data.py where`
  prints and still named nine after T1; the brief's file list never named that file, so no
  verify clause could see it. Per the roster's consequence rule a confirmed red-team break is
  a failed verify, so T1 retries with that evidence. This adds one hand-authored file
  (`docs/GUIDE.md`) and its generated mirror beyond the brief's list: an orchestrator
  adjudication that serves the task's own title, recorded here rather than silently.
agent: T1 id=a6ccfc1fbf532a88e role=implementer model=sonnet
outcome: T1 model=sonnet attempts=2 result=retry-pass review=revised run=2026-09-25-7e3a
