# TASKS — fusion-tier1

Repo root: `/path/to/polytropos`. Run all verify commands from
there. Read `PLAN.md` (same directory) first — especially Repo facts, decisions D1–D11, the
OUT-OF-SCOPE fence, and the risks/tripwires.
Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `fusion-tier1-implementer` (the parameter overrides the agent's
frontmatter default). Tasks marked `independent: yes` within the same phase may run in
parallel; `depends:` lists hard ordering. **T1 → T2 → T3 are strictly serial (same file
`skills/execute/SKILL.md`, same model — a warm-cluster candidate: one continued implementer
may serve all three). T4 follows T3. T5 → T6 are serial. T7 ‖ T8 are independent of each
other.** Dispatch `fusion-tier1-reviewer` at each phase end.

Standing rules for every task:

- **The architect/execute shared kit contract is the #1 invariant.** Skill edits are BODY-only
  — never touch the YAML frontmatter of any `skills/*/SKILL.md` (the plugin is installed
  LIVE; skill files are runtime behavior). Every pinned contract element must survive in BOTH
  skills after every task. If a brief's anchor text is not found verbatim, STOP and report
  the discrepancy — never fuzzy-match, never improvise.
- Never edit `bin/cost_report.py`, `bin/session_cost.py`, `bin/copilot_execute.py`, any other
  existing `bin/`/`tests/` file, `data/` (either pricing file), `.claude-plugin/`, `copilot/`,
  the generated `skills/*/references/` mirrors, or the completed kits and their agents.
  Sanctioned existing-file edits: `skills/execute/SKILL.md` (T1–T3),
  `skills/architect/SKILL.md` (T4), `README.md` + `CLAUDE.md` (T8) — pinned insertions only.
- Never hardcode a price, price ratio, or real model id. Sanctioned exceptions: tier
  vocabulary (`frontier`/`opus`/`sonnet`/`haiku`), the alias map
  `TASK_MODEL_TIERS = {"fable": "frontier"}`, synthetic fixture ids/values in tests, and the
  demo's pinned token VOLUMES (counts, not prices). Demo model ids are computed from
  `data/pricing.json` at run time.
- Never read the real `~/.claude` from a test or verify command — every scorecard test/verify
  run passes `--projects-dir` (and `--tasks-dir`/`--no-subagents`) against temp fixtures.
  `Path.home()` count in the two new Python files: ZERO. Never write outside this repo and
  temp dirs. No network. Do not commit or push.
- Python stdlib-only. Verify with `python3 -m unittest discover -s tests [-p '<file>.py']`
  (the dotted-module form is broken on this machine). Paths via `Path(__file__).resolve()`,
  never `$PWD`. No `/private/tmp/` path in any deliverable.

---

## Phase 1 — Rework /execute and sync /architect (the contract-sensitive phase)

### T1 — Add the warm-sidekick dispatch modes to skills/execute/SKILL.md
- status: done
- model: sonnet
- depends: (none)
- independent: no

**Brief.** Per PLAN.md D1/D2/D3. Two edits to `skills/execute/SKILL.md`, body only.

*Edit 1* — in "## The loop" step 2, replace the exact sentence:

```
Do not pad it with your own interpretation.
```

with:

```
Do not pad it with your own interpretation. Choose the dispatch mode per **Dispatch modes — fresh fan-out vs warm sidekick** below.
```

*Edit 2* — insert a new section between the end of the "## The loop" section (i.e. after the
paragraph `Run parallel dispatches for tasks TASKS.md marks as independent — one message,
multiple Agent calls.`) and the heading `## Escalation valve — blocked tasks go back to
Fable, one at a time`. Insert this text verbatim (blank line before and after):

```markdown
## Dispatch modes — fresh fan-out vs warm sidekick

Fresh, parallel subagents remain the default for tasks marked `independent:` with disjoint
files — one message, multiple Agent calls, no shared state (this rule is unchanged).

For a **cohesive cluster**, keep ONE warm implementer instead of paying N cold prompt-cache
starts: spawn it for the cluster's first task, then for each subsequent task continue the
SAME agent via SendMessage with the next brief — a continued agent keeps its context, and its
already-read files, intact, so the cluster's shared files are read and cached once. A
cohesive cluster is a maximal run of tasks that:

- form a serial `depends:` chain within one phase (each task depends on the previous), and
- share a primary file or subsystem — the same file named in their briefs, or the TASKS.md
  preamble flagging them as a same-file/serial chain (the architect leaves these hints), and
- carry the SAME `model` value. A continued agent keeps its spawn model and SendMessage
  cannot override it, so a model-pin change ALWAYS ends the cluster — the task's `model`
  field stays authoritative at dispatch; never serve an `opus`-pinned task with a warm
  `sonnet` agent, or vice versa.

The trade-off to respect: a warm agent accumulates context and eventually needs compaction,
which destroys the cache advantage — warmth is for clusters, not universal. Cap a warm
sidekick at ~4 tasks, end it early if its replies degrade or it reports context pressure, and
start the next cluster fresh. Each continuation message is still the next task's
self-contained brief verbatim, prefixed only with "Previous cluster task is done; next
task:". Verification is NEVER warmed: the verifier agent is always a fresh spawn — its value
IS the adversarial fresh context. Record warm-cluster use in NOTES.md (which tasks shared one
agent) so later phases and the scorecard can see it.
```

Change nothing else — in particular do not touch the frontmatter, "## Setup", steps 1/3–6,
the escalation valve, or "## End of run".

**Acceptance.** Both edits landed exactly once; the new H2 sits between the parallel-dispatch
paragraph and the escalation valve; every pre-existing contract element still present
(verify's grep list); frontmatter untouched (`git diff` on the file shows no change in lines
1–4); suite + sync check green.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && python3 bin/sync_pricing_refs.py --check && echo 'T1 OK'
t = open('skills/execute/SKILL.md').read()
assert t.startswith('---\nname: execute\n'), "frontmatter touched"
for s in [
    "## Setup", "## The loop", "`in-progress` in TASKS.md", "mark `done`", "mark `blocked`",
    "skip `done`, stop at `blocked` deps",
    "passing the task's `model` value as the Agent tool's `model` parameter",
    "overrides the agent's frontmatter default", "NOTES.md", "Phase boundaries",
    "reviewer agent", "independent — one message, multiple Agent calls",
    "## Escalation valve", "`model: fable`", "## End of run",
]:
    assert s in t, f"contract element lost: {s!r}"
assert t.count("## Dispatch modes — fresh fan-out vs warm sidekick") == 1, "new H2 missing or duplicated"
for s in ["SendMessage", "SAME `model` value", "always a fresh spawn", "~4 tasks",
          "Previous cluster task is done; next task:", "compaction"]:
    assert s in t, f"warm-sidekick element missing: {s!r}"
assert t.index("independent — one message, multiple Agent calls") < t.index("## Dispatch modes") < t.index("## Escalation valve"), "section misplaced"
assert "Dispatch modes — fresh fan-out vs warm sidekick** below" in t, "step-2 pointer missing"
print("T1 structural checks ok")
PY
```

---

### T2 — Add the lean-driver operating rule to skills/execute/SKILL.md
- status: done
- model: sonnet
- depends: T1
- independent: no

**Brief.** Per PLAN.md D4. Two edits to `skills/execute/SKILL.md` (same file as T1 — serial),
body only.

*Edit 1* — insert a new section between the end of the "## Setup" section (i.e. after the
aesop-managed item, before the heading `## The loop`) and `## The loop`. Insert verbatim
(blank line before and after):

```markdown
## Operating rule — lean driver

Your own context is the single most expensive artifact of the run — it is priced, cached,
and re-sent on every subsequent turn, and every inline read brings compaction closer. Take
minimal actions:

- Read only kit state — PLAN.md, TASKS.md, NOTES.md — plus the output of verify commands you
  run. Do not inline-read source files, implementer diffs, or logs to "get oriented".
- Delegate every exploratory read, grep, and "what does this file look like now" question to
  a cheap scout subagent (Agent tool, `model: haiku`) that returns a few-line conclusion —
  never file dumps.
- Delegate independent verification the same way (the kit's verifier agent): you consume
  verdicts, not evidence dumps.
- You still run each task's verify command yourself — its exit status is orchestrator-owned
  evidence — but keep only the decisive tail of long output, and hand failure investigation
  to a scout instead of digging inline.
- Keep NOTES.md terse: outcomes and learnings, never transcripts.

Default posture: delegate and monitor. You touch files directly only to keep TASKS.md and
NOTES.md state current.
```

*Edit 2* — in "## The loop" step 3, replace the exact sentence:

```
The implementer's claim of success is not evidence.
```

with:

```
The implementer's claim of success is not evidence. Stay lean while verifying (see **Operating rule — lean driver**): take the verifier's verdict, not its evidence dumps.
```

Change nothing else.

**Acceptance.** Both edits landed exactly once; section order is Setup → Operating rule →
The loop → Dispatch modes → Escalation valve → End of run; T1's additions and every contract
element intact; frontmatter untouched; suite + sync check green.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && python3 bin/sync_pricing_refs.py --check && echo 'T2 OK'
t = open('skills/execute/SKILL.md').read()
assert t.startswith('---\nname: execute\n'), "frontmatter touched"
for s in [
    "## Setup", "## The loop", "`in-progress` in TASKS.md", "mark `done`", "mark `blocked`",
    "skip `done`, stop at `blocked` deps",
    "passing the task's `model` value as the Agent tool's `model` parameter",
    "overrides the agent's frontmatter default", "NOTES.md", "Phase boundaries",
    "reviewer agent", "independent — one message, multiple Agent calls",
    "## Escalation valve", "`model: fable`", "## End of run",
    "## Dispatch modes — fresh fan-out vs warm sidekick",
]:
    assert s in t, f"element lost: {s!r}"
assert t.count("## Operating rule — lean driver") == 1, "new H2 missing or duplicated"
for s in ["`model: haiku`", "never file dumps", "verify command yourself",
          "Delegate independent verification", "delegate and monitor"]:
    assert s in t, f"lean-driver element missing: {s!r}"
order = ["## Setup", "## Operating rule — lean driver", "## The loop",
         "## Dispatch modes — fresh fan-out vs warm sidekick", "## Escalation valve", "## End of run"]
idx = [t.index(h) for h in order]
assert idx == sorted(idx), f"section order wrong: {order}"
assert "Stay lean while verifying" in t, "step-3 pointer missing"
print("T2 structural checks ok")
PY
```

---

### T3 — Add the outcome ledger to skills/execute/SKILL.md
- status: done
- model: sonnet
- depends: T2
- independent: no

**Brief.** Per PLAN.md D5. Five edits to `skills/execute/SKILL.md` (same file — serial), body
only. The ledger grammar here is THE contract for `bin/routing_scorecard.py` (T5) — reproduce
it exactly.

*Edit 1* — in "## The loop" step 4, replace the exact text:

```
4. **On pass**: mark `done`, note anything learned that later tasks need (append to a `NOTES.md` in the kit dir).
```

with:

```
4. **On pass**: mark `done`, note anything learned that later tasks need (append to a `NOTES.md` in the kit dir), and append the task's `outcome:` line (see **Outcome ledger** below).
```

*Edit 2* — in step 5, replace the exact text:

```
If it fails again, mark `blocked` with the failure details and move to the next independent task.
```

with:

```
If it fails again, mark `blocked` with the failure details, append its `outcome:` line (`result=blocked`), and move to the next independent task.
```

*Edit 3* — insert a new section between the end of the "## Dispatch modes — fresh fan-out vs
warm sidekick" section and the heading `## Escalation valve — blocked tasks go back to Fable,
one at a time`. Insert verbatim (blank line before and after):

```markdown
## Outcome ledger — one line per finished task

The moment a task reaches `done` or `blocked`, append ONE machine-readable line to NOTES.md —
this is the input `bin/routing_scorecard.py` turns into the kit's routing-quality scorecard:

    outcome: <task-id> model=<model> attempts=<n> result=<result> review=<review>

- `model` — what the task actually ran on: its `model` pin, or the escalation target when a
  Fable consult did the fixing.
- `attempts` — implementer dispatches, counting retries and escalation (clean first try = 1).
- `result` — exactly one of `pass` (first dispatch, verify passed) | `retry-pass` (passed on
  the retry) | `escalated-pass` (passed only via the escalation valve) | `blocked`.
- `review` — exactly one of `clean` (verifier/reviewer accepted the work unchanged) |
  `revised` (changes were required after the implementer claimed done) | `none` (no
  independent review beyond the verify command).

Unknown `key=value` pairs are ignored by the parser, and re-running a task just appends a
fresh line — the scorecard takes the LAST line per task id.
```

*Edit 4* — at the end of the "## Escalation valve" section's paragraph, after the exact
sentence ending `you never pay Fable prices for routine execution.`, append (same paragraph):

```
 When the consult unblocks the task, record `result=escalated-pass` (with the consult's model) in its `outcome:` line.
```

*Edit 5* — in "## End of run", after the exact sentence ending `run the plan's overall "done"
check from PLAN.md and state the result.`, append (same paragraph):

```
 Then offer the routing-quality scorecard: `python3 bin/routing_scorecard.py <slug>` (first-try pass rate, model mix, cheap-model review survival, and — with `--session` — dollars vs an all-frontier counterfactual).
```

Change nothing else. (T5 builds the script this section names; the skill text landing first
is fine — the kit ships as one unit.)

**Acceptance.** All five edits landed exactly once; grammar line and both vocabularies
(`pass|retry-pass|escalated-pass|blocked`, `clean|revised|none`) present verbatim; section
order Setup → Operating rule → The loop → Dispatch modes → Outcome ledger → Escalation valve
→ End of run; all prior contract elements intact; frontmatter untouched; suite + sync green.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && python3 bin/sync_pricing_refs.py --check && echo 'T3 OK'
t = open('skills/execute/SKILL.md').read()
assert t.startswith('---\nname: execute\n'), "frontmatter touched"
for s in [
    "## Setup", "## Operating rule — lean driver", "## The loop",
    "## Dispatch modes — fresh fan-out vs warm sidekick",
    "`in-progress` in TASKS.md", "mark `done`", "mark `blocked`",
    "skip `done`, stop at `blocked` deps",
    "passing the task's `model` value as the Agent tool's `model` parameter",
    "overrides the agent's frontmatter default", "Phase boundaries", "reviewer agent",
    "independent — one message, multiple Agent calls", "## Escalation valve",
    "`model: fable`", "## End of run",
]:
    assert s in t, f"element lost: {s!r}"
assert t.count("## Outcome ledger — one line per finished task") == 1
for s in ["outcome: <task-id> model=<model> attempts=<n> result=<result> review=<review>",
          "`retry-pass`", "`escalated-pass`", "`clean`", "`revised`", "`none`",
          "the LAST line per task id", "append the task's `outcome:` line",
          "`result=blocked`", "`result=escalated-pass`", "bin/routing_scorecard.py"]:
    assert s in t, f"ledger element missing: {s!r}"
order = ["## Setup", "## Operating rule — lean driver", "## The loop",
         "## Dispatch modes — fresh fan-out vs warm sidekick",
         "## Outcome ledger — one line per finished task", "## Escalation valve", "## End of run"]
idx = [t.index(h) for h in order]
assert idx == sorted(idx), "section order wrong"
print("T3 structural checks ok")
PY
```

---

### T4 — Sync skills/architect/SKILL.md and re-check the shared contract in BOTH skills
- status: done
- model: opus
- depends: T3
- independent: no

**Brief.** Per PLAN.md D3/D5 and the CLAUDE.md invariant ("if you touch either skill you MUST
re-check both"). Two pinned edits to `skills/architect/SKILL.md` (body only), then the
dual-file contract audit.

*Edit 1* — in the "### `TASKS.md` (same kit directory)" section, replace the exact bullet:

```
- Note that execute maintains a `NOTES.md` alongside PLAN.md/TASKS.md for cross-task learnings — the architect does not create it.
```

with:

```
- Note that execute maintains a `NOTES.md` alongside PLAN.md/TASKS.md for cross-task learnings, plus one machine-readable `outcome:` line per finished task (consumed by `bin/routing_scorecard.py` for the routing-quality scorecard) — the architect does not create it.
```

*Edit 2* — insert a new bullet immediately after the exact bullet line:

```
- Each task marks ordering explicitly: `depends: <ids>` or `independent: yes` — execute parallelizes only tasks marked independent.
```

New bullet (verbatim):

```
- Flag **warm-cluster candidates** as free text in the TASKS.md dispatch preamble (e.g. "T2 → T3 → T4 are strictly serial (same file)"): serial `depends:` chains that share a primary file and carry the same `model` pin. Execute may then serve the whole cluster with one continued (warm) implementer instead of N cold spawns; tasks marked `independent:` still fan out fresh. This is a hint, not a new task field — the task-field contract is unchanged.
```

Change nothing else in the file.

*The audit* — after editing, re-check BOTH `skills/architect/SKILL.md` and
`skills/execute/SKILL.md` against the full shared contract (the verify below encodes it):
kit layout (`PLAN.md`, `TASKS.md`, `NOTES.md` owned by execute); task fields `id`, `title`,
`status`, `model`, brief, acceptance, verify; status vocabulary exactly
`pending | in-progress | done | blocked`; `## Phase N — <name>` headings;
`depends:`/`independent:`; the model-override-at-dispatch rule stated in both files; the
warm-sidekick text in execute being opt-in (fresh fan-out sentence intact) and
model-pin-safe; the ledger grammar identical in spirit between execute's section and the
architect's new mention. If ANY element is missing or contradicted, STOP and report — that is
a T1–T3 defect to fix via the orchestrator, not something to patch ad hoc here.

**Acceptance.** Both architect edits landed exactly once; the dual-file grep audit passes;
architect frontmatter untouched; no other file changed by this task; suite + sync green.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && python3 bin/sync_pricing_refs.py --check && git diff --quiet -- bin/cost_report.py bin/session_cost.py bin/copilot_execute.py data && echo 'T4 OK'
a = open('skills/architect/SKILL.md').read()
e = open('skills/execute/SKILL.md').read()
assert a.startswith('---\nname: architect\n'), "architect frontmatter touched"
assert e.startswith('---\nname: execute\n'), "execute frontmatter touched"
# --- architect contract elements ---
for s in [
    "`id`, `title`, `status` (pending/in-progress/done/blocked), `model`",
    "Self-contained brief", "Acceptance criteria", "Verify command",
    "`## Phase N — <name>` headings",
    "`depends: <ids>` or `independent: yes`",
    "overrides the implementer agent's frontmatter default",
    "NOTES.md", "-implementer.md", "-verifier.md", "-reviewer.md",
    "## Step 1", "## Step 2", "## Step 3",
]:
    assert s in a, f"architect element lost: {s!r}"
assert a.count("warm-cluster candidates") == 1, "architect warm-cluster bullet missing/duplicated"
assert "not a new task field" in a and "still fan out fresh" in a
assert a.count("`outcome:` line per finished task") == 1, "architect ledger mention missing/duplicated"
assert "bin/routing_scorecard.py" in a
# --- execute contract elements (full list, final state) ---
for s in [
    "## Setup", "## Operating rule — lean driver", "## The loop",
    "## Dispatch modes — fresh fan-out vs warm sidekick",
    "## Outcome ledger — one line per finished task",
    "`in-progress` in TASKS.md", "mark `done`", "mark `blocked`",
    "skip `done`, stop at `blocked` deps",
    "passing the task's `model` value as the Agent tool's `model` parameter",
    "overrides the agent's frontmatter default", "Phase boundaries", "reviewer agent",
    "independent — one message, multiple Agent calls", "## Escalation valve",
    "`model: fable`", "## End of run",
    "outcome: <task-id> model=<model> attempts=<n> result=<result> review=<review>",
    "SAME `model` value", "always a fresh spawn",
]:
    assert s in e, f"execute element lost: {s!r}"
print("dual-file contract audit ok")
PY
```

---

*Phase 1 end — dispatch `fusion-tier1-reviewer` before starting Phase 2.*

---

## Phase 2 — The routing scorecard

### T5 — Create bin/routing_scorecard.py
- status: done
- model: opus
- depends: T4
- independent: no

**Brief.** Per PLAN.md D6–D10: the routing-quality scorecard. New file
`bin/routing_scorecard.py`, stdlib-only, executable header matching the other `bin/` scripts.
Module docstring states: what it is (turns an executed kit's TASKS.md + NOTES.md outcome
ledger into a routing-quality scorecard — the "did cheap models hold quality" companion to
the dollar tools); that it is READ-ONLY (never writes into a kit dir or NOTES.md; only
`--demo` writes, into its own temp dir); that quality parsing is TOLERANT (kits without
ledger lines degrade to status-only with a note); and that TASKS.md parsing and transcript
pricing are REUSED read-only from `copilot_execute` and `session_cost` via importlib — never
re-implemented.

**Loading (pinned):** `_load(name)` — the `bin/session_cost.py` importlib pattern
(`spec_from_file_location(name, Path(__file__).resolve().parent / f"{name}.py")`). Then
`ce = _load("copilot_execute")`, `sc = _load("session_cost")`, and `cr = sc.cr` (session_cost
already loads cost_report — do NOT load it twice). No `Path.home()` anywhere in this file:
the projects-dir default is `sc.DEFAULT_PROJECTS_DIR`.

**Constants (pinned):**
- `PLUGIN_ROOT = Path(__file__).resolve().parent.parent`
- `DEFAULT_KITS_DIR = PLUGIN_ROOT / ".claude" / "kits"`
- `SCHEMA_VERSION = 1`
- `RESULTS = ("pass", "retry-pass", "escalated-pass", "blocked")`
- `REVIEWS = ("clean", "revised", "none")`
- `TASK_MODEL_TIERS = {"fable": "frontier"}` — comment: structural vocabulary mapping the
  Agent-tool model alias to the pricing.json tier; all other aliases equal their tier name.
- `OUTCOME_RE = re.compile(r"^\s*(?:[-*]\s+)?outcome:\s+(\S+)\s+(.+)$")` and
  `PAIR_RE = re.compile(r"(\w+)=(\S+)")`
- `MD_H2S = ("## Verdict", "## Task outcomes", "## Model mix", "## Review survival", "## Dollars")`
- `DEMO_TASKS_MD`, `DEMO_NOTES_MD`, `DEMO_VOLUMES` — see Demo below.

**Pure functions (unit-testable, pinned signatures):**
- `parse_outcomes(text) -> (outcomes, notes)` — scan every line with `OUTCOME_RE`; parse
  pairs with `PAIR_RE`. An outcome needs `model` and a `result` in `RESULTS`; otherwise
  append `f"unrecognized outcome line: {line.strip()!r}"` to notes and skip. `attempts`:
  int() with fallback 1 + note on garbage. `review`: default `"none"`; values outside
  `REVIEWS` → note + `"none"`. Unknown keys ignored (forward-compatible). Later lines for the
  same task id REPLACE earlier ones (last wins). Returns `({task_id: {"model", "attempts",
  "result", "review"}}, [notes])`.
- `tier_for(alias) -> str` — `TASK_MODEL_TIERS.get(alias, alias)`.
- `is_cheap(alias, expensive_tiers) -> bool` — `tier_for(alias) not in expensive_tiers`
  (callers pass `cr.EXPENSIVE_TIERS` at run time; tests pass their own set).
- `build_scorecard(kit_name, tasks, outcomes, notes, cost=None,
  expensive_tiers=frozenset()) -> dict` — the pinned D10 JSON shape. `tasks` is
  `ce.parse_tasks` output. Per task: attach its outcome dict or None; an outcome whose id is
  not a task id → note `f"outcome for unknown task id {tid!r} ignored"`. `quality`: `total`
  (len tasks), `with_outcome`, `first_try_pass` (`result == "pass"`), `retry_pass`,
  `escalated_pass`, `blocked` (from outcomes), `first_try_rate` = first_try_pass /
  with_outcome (None when with_outcome 0), `escalation_rate` likewise. `model_mix`:
  `{effective_model: task_count}` where effective model = outcome `model` else the task's
  `model` field else `"unspecified"`. `review`: `cheap_reviewed` (effective model cheap AND
  outcome present AND review != "none"), `cheap_clean` (of those, review == "clean"),
  `survival_rate` = cheap_clean / cheap_reviewed (None when 0). `cost` passed through (dict
  or None). When `with_outcome == 0`, append note
  `"no outcome ledger found — quality limited to TASKS.md statuses"`. Top-level keys exactly:
  `schema_version, kit, generated_at, tasks, quality, model_mix, review, cost, notes`.
- `session_cost_summary(session_id, projects_dir, tasks_dirs, includes, no_subagents, vs,
  pricing) -> (dict_or_None, notes)` — `mt = sc.find_main_transcript(session_id,
  projects_dir)`; None → `(None, [f"no transcript for session {session_id!r} under
  {projects_dir}"])`. task_dirs = `[]` if no_subagents else (explicit tasks_dirs or
  `sc.discover_task_dirs(session_id)`). `files = sc.gather_files(mt, task_dirs, includes)`;
  `data = sc.collect(files, pricing)`; `cf = sc.resolve_counterfactual_model(vs, pricing)`
  (ValueError → propagate to caller for `sys.exit`); `rep = sc.build_report(data, cf,
  pricing, pricing.get("billing_mode", "api"))`. Return
  `({"session": session_id, "files_scanned": data["files_read"], "actual_usd":
  rep["actual_total"], "counterfactual_usd": rep["cf_total"], "counterfactual_model":
  {"key": rep["cf_key"], "display": rep["cf_display"]}, "delta_usd": rep["savings"],
  "ratio": rep["ratio"], "pricing_cached": pricing.get("cached_date")}, [])`.
- `render_markdown(card) -> str` — H1 `# Routing scorecard — {kit}`, then EXACTLY the five
  `MD_H2S` in order. Verdict: one bold line, e.g.
  `**3/6 tasks passed verify first-try on their pinned model · cheap-model review survival
  75% · $A actual vs $C all-<display> (Δ $D saved)**` — every unavailable number renders
  `n/a` (rates with None, cost section absent). Task outcomes: a table
  `| Task | Model | Status | Result | Attempts | Review |` with `—` for missing outcome
  fields. Model mix: `| Model | Tasks |` table. Review survival: the counts, the rate (or
  `n/a`), and one line stating the definition (cheap = below the expensive tiers; survival =
  review-clean share of reviewed cheap tasks). Dollars: the cost dict rendered (actual,
  counterfactual model + total, delta, ratio, files scanned, `prices cached <pricing_cached>`)
  or exactly `n/a — pass --session to fold in transcript dollars.` Then any notes as a
  bulleted `Notes:` list. USD via `:,.2f`.
- `main(argv=None)` — argparse: positional `kit` (nargs="?"; slug under `--kits-dir`, or a
  path to a kit dir — treat as path when it contains a separator or names an existing dir);
  `--kits-dir` (default `DEFAULT_KITS_DIR`); `--session`; `--projects-dir` (default
  `str(sc.DEFAULT_PROJECTS_DIR)` — runtime-only, always overridden in tests); `--tasks-dir`
  (append, default []); `--include` (append, default []); `--no-subagents` (store_true);
  `--vs`; `--json` (store_true); `--demo` (store_true). Rules: `--demo` with a positional kit
  → `sys.exit("--demo takes no kit argument")`; neither kit nor `--demo` →
  `sys.exit("kit slug required (or --demo)")`. Kit flow: resolve kit dir; missing dir or
  missing `TASKS.md` → `sys.exit` naming the path; `tasks = ce.parse_tasks(text)` with
  ValueError → `sys.exit(f"malformed TASKS.md: {e}")`; NOTES.md read if present
  (`errors="replace"`), else note `"no NOTES.md at <path> — quality limited to TASKS.md
  statuses"`; pricing = `cr.load_pricing()`; cost only when `--session` given (ValueError
  from a bad `--vs` → `sys.exit`), else the D8 no-session note; build; print markdown or
  `json.dumps(card, indent=2)`. Exit 0 on success, including degraded output.

**Demo (pinned — the sanctioned smoke test):** `--demo` builds everything inside ONE
`tempfile.TemporaryDirectory` and runs the normal pipeline (same build/render code paths),
printing markdown (or `--json`), then cleans up. Exit 0.
- `DEMO_TASKS_MD`: a valid kit TASKS.md fragment with six task blocks (headings
  `### D1 — <title>` … `### D6 — <title>`, each with `- status:` and `- model:` lines) —
  statuses: D1–D5 `done`, D6 `blocked`; models: D1 `haiku`; D2, D3, D4, D6 `sonnet`; D5
  `fable`.
- `DEMO_NOTES_MD`: prose plus exactly these ledger lines (and one deliberately bad line
  `outcome: D9 result=???` that must be skipped with a note):
  `outcome: D1 model=haiku attempts=1 result=pass review=clean`
  `outcome: D2 model=sonnet attempts=1 result=pass review=clean`
  `outcome: D3 model=sonnet attempts=1 result=pass review=revised`
  `outcome: D4 model=sonnet attempts=2 result=retry-pass review=clean`
  `outcome: D5 model=fable attempts=3 result=escalated-pass review=clean`
  `outcome: D6 model=sonnet attempts=2 result=blocked review=none`
  → expected quality (verify asserts these): total 6, with_outcome 6, first_try_pass 3,
  retry_pass 1, escalated_pass 1, blocked 1, first_try_rate 0.5; model_mix
  `{"haiku": 1, "sonnet": 4, "fable": 1}`; review `cheap_reviewed 4, cheap_clean 3,
  survival_rate 0.75` (with `cr.EXPENSIVE_TIERS = {"frontier", "opus"}`: haiku+sonnet cheap,
  fable → frontier not cheap; D6 review=none excluded).
- Demo transcript: session id `fusion-demo`; layout
  `<tmp>/projects/-demo/fusion-demo.jsonl`. Model ids COMPUTED at run time: for each tier in
  `("haiku", "sonnet", "opus", "frontier")`, the first model id in `pricing["models"]` file
  order with that tier (skip tiers absent from pricing). One transcript line per found model:
  `{"timestamp": <iso>, "message": {"model": <id>, "id": "demo-<tier>", "usage":
  {"input_tokens": I, "output_tokens": O}}}` with `DEMO_VOLUMES = {"haiku": (200000, 8000),
  "sonnet": (900000, 45000), "opus": (150000, 12000), "frontier": (60000, 9000)}` (pinned
  token VOLUMES — counts, not prices). Cost computed via `session_cost_summary("fusion-demo",
  <tmp>/projects, [], [], True, None, pricing)` — `--no-subagents` semantics so nothing scans
  tmp bases.

GOTCHAS: zero `Path.home()`; zero real model-id literals (grep-verified — demo ids are
computed); never write except the demo temp dir; never modify NOTES.md; rates None (not 0)
on zero denominators; `parse_tasks` needs the spaced em dash in demo headings (`### D1 — x`);
floats compared with tolerance in the verify, exact ints asserted exactly.

**Acceptance.**
- `python3 bin/routing_scorecard.py --demo` prints the H1 + all five pinned H2s and exits 0;
  `--demo --json` parses, `schema_version == 1`, top-level keys exactly the D10 set, the
  pinned demo quality/mix/review numbers hold, `cost["actual_usd"] > 0` and
  `cost["delta_usd"]` ≈ `counterfactual_usd - actual_usd`, and the bad `D9` line landed in
  `notes` as unrecognized (or unknown-id) — not in `tasks`.
- A real-kit run against THIS kit dir (`fusion-tier1`) exits 0 and reports
  `with_outcome == 0` degradation gracefully (no NOTES.md yet at T5 time, or a ledger-free
  one) — no crash, `first_try_rate` null.
- Greps: no `Path.home()`, no `sqlite`, no real model ids in the file; reused scripts and
  `data/` unchanged (`git diff --quiet`).
- Full suite green; only `bin/routing_scorecard.py` new.

**Verify.**
```bash
cd /path/to/polytropos && python3 bin/routing_scorecard.py --demo && python3 - <<'PY' && ! grep -n 'Path.home()' bin/routing_scorecard.py && ! grep -n 'sqlite' bin/routing_scorecard.py && ! grep -nE 'claude-(fable|opus|sonnet|haiku)' bin/routing_scorecard.py && git diff --quiet -- bin/cost_report.py bin/session_cost.py bin/copilot_execute.py data && python3 -m unittest discover -s tests && echo 'T5 OK'
import json, subprocess, sys
r = subprocess.run([sys.executable, "bin/routing_scorecard.py", "--demo"], capture_output=True, text=True)
assert r.returncode == 0, r.stderr
for h in ("# Routing scorecard —", "## Verdict", "## Task outcomes", "## Model mix", "## Review survival", "## Dollars"):
    assert h in r.stdout, f"missing heading: {h}"
j = subprocess.run([sys.executable, "bin/routing_scorecard.py", "--demo", "--json"], capture_output=True, text=True)
assert j.returncode == 0, j.stderr
c = json.loads(j.stdout)
assert set(c) == {"schema_version", "kit", "generated_at", "tasks", "quality", "model_mix", "review", "cost", "notes"}, set(c)
assert c["schema_version"] == 1
q = c["quality"]
assert (q["total"], q["with_outcome"], q["first_try_pass"], q["retry_pass"], q["escalated_pass"], q["blocked"]) == (6, 6, 3, 1, 1, 1), q
assert abs(q["first_try_rate"] - 0.5) < 1e-9, q
assert c["model_mix"] == {"haiku": 1, "sonnet": 4, "fable": 1}, c["model_mix"]
rv = c["review"]
assert (rv["cheap_reviewed"], rv["cheap_clean"]) == (4, 3) and abs(rv["survival_rate"] - 0.75) < 1e-9, rv
assert c["cost"] and c["cost"]["actual_usd"] > 0, c["cost"]
assert abs(c["cost"]["delta_usd"] - (c["cost"]["counterfactual_usd"] - c["cost"]["actual_usd"])) < 1e-9
assert any("D9" in n for n in c["notes"]), c["notes"]
assert not any(t["id"] == "D9" for t in c["tasks"])
# graceful degradation on a ledger-free real kit (this one)
g = subprocess.run([sys.executable, "bin/routing_scorecard.py", "fusion-tier1", "--json"], capture_output=True, text=True)
assert g.returncode == 0, g.stderr
gc = json.loads(g.stdout)
assert gc["quality"]["first_try_rate"] is None or gc["quality"]["with_outcome"] > 0
assert gc["cost"] is None and any("--session" in n for n in gc["notes"]), (gc["cost"], gc["notes"])
print("scorecard demo + degradation ok")
PY
```

---

### T6 — Regression tests (tests/test_routing_scorecard.py)
- status: done
- model: sonnet
- depends: T5
- independent: no

**Brief.** Create `tests/test_routing_scorecard.py`, stdlib `unittest`, loading
`bin/routing_scorecard.py` via the importlib `_load` convention off
`BIN_DIR = Path(__file__).resolve().parent.parent / "bin"` (copy the header pattern from
`tests/test_journal_sources.py`, including a module docstring stating the safety contract:
no test reads the real `~/.claude`; `--projects-dir` and kit paths always point at temp
fixtures; the pricing dict used by unit tests is a SYNTHETIC module constant — the real
pricing file is opened only indirectly by the `--demo` subprocess smoke, read-only).

Fixtures: `P` = synthetic pricing dict — `cached_date`, `billing_mode: "api"`,
`cache_read_multiplier` 0.1, `cache_write_multiplier_5m` 1.25, and `models` with fake ids
covering tiers `haiku`/`sonnet`/`frontier` (round rates, frontier the most expensive; NO
`intro_pricing`). `EXP = {"frontier", "opus"}`. Helpers to write a temp kit dir (TASKS.md +
optional NOTES.md) and a temp projects tree with transcript JSONL lines.

Minimum cases:
1. `parse_outcomes`: happy path; last-line-wins per id; leading `- ` and `* ` bullets parse;
   unknown `key=value` pairs ignored; missing `model` or bad `result` → skipped + note;
   non-integer `attempts` → 1 + note; bad `review` → `"none"` + note; a NOTES.md with zero
   ledger lines → `({}, [])`.
2. `tier_for` / `is_cheap`: `fable` → `frontier` (not cheap vs `EXP`); `haiku`/`sonnet`
   cheap; `opus` not cheap; custom expensive set honored.
3. `build_scorecard`: replicate the demo math with an independent fixture (asserted key by
   key); zero-outcome kit → rates None, degradation note present; outcome for unknown id →
   note, not a task row; top-level key set asserted as a frozen set (schema lock);
   `model_mix` falls back to the task's `model` field when no outcome, `"unspecified"` when
   neither.
4. `session_cost_summary` against temp fixtures + `P`: hand-math `actual_usd` for one
   cheap-model transcript line; counterfactual = the frontier fake id with
   `delta == cf - actual` (tolerance 1e-9); dedupe across a main transcript + a fake
   subagent `*.output` file sharing a message id (pass it via `tasks_dirs`); missing session
   → `(None, [note])`; bad `vs` → ValueError propagates.
5. CLI end-to-end via `subprocess.run([sys.executable, "bin/routing_scorecard.py", ...])`:
   temp kit with ledger → `--json` parses, expected numbers; markdown mode → the five pinned
   H2s in order; kit without NOTES.md → exit 0 + degradation note; malformed TASKS.md (bad
   status) → nonzero exit, message mentions TASKS.md; no args → nonzero; `--demo` with a kit
   arg → nonzero; `--demo` and `--demo --json` → exit 0 (parse the JSON, spot-check
   `schema_version` and quality totals).
6. READ-ONLY proof: byte-snapshot the temp kit dir + projects tree before/after a full CLI
   run — identical (the scorecard never writes into a kit).
7. No real-home reach: every CLI invocation in the tests passes an explicit kit path/slug
   with `--kits-dir`, and `--projects-dir`/`--no-subagents` whenever `--session` is used.

**Acceptance.** All new tests pass; full suite green; safety greps clean (below); only this
file new.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_routing_scorecard.py' -v && python3 - <<'PY' && python3 -m unittest discover -s tests && git diff --quiet -- bin/cost_report.py bin/session_cost.py bin/copilot_execute.py data && echo 'T6 OK'
import re
text = open('tests/test_routing_scorecard.py').read()
assert 'Path.home()' not in text
assert '~/.claude' not in text, "real home path in tests"
assert not re.search(r'claude-(fable|opus|sonnet|haiku)', text), "real model id in tests"
assert '--projects-dir' in text and 'snapshot' in text.lower(), "read-only/CLI coverage missing"
print('safety greps ok')
PY
```

---

*Phase 2 end — dispatch `fusion-tier1-reviewer` before starting Phase 3.*

---

## Phase 3 — Documentation

### T7 — Write docs/FUSION-TIER1.md
- status: done
- model: sonnet
- depends: T5
- independent: yes

**Brief.** Per PLAN.md D11. New file `docs/FUSION-TIER1.md` documenting what this kit built
and what it deliberately did not. Match the tone/format of the other `docs/*.md` files (H1 +
H2 sections, concrete commands). Required structure — H1
`# Fusion Tier 1 — multi-model orchestration borrows`, then EXACTLY these five H2s in order:

1. `## The three borrows` — one subsection or bold lead per borrow: **Warm sidekick**
   (fresh-per-task was N cold prompt-cache starts; a cohesive cluster — serial `depends:`
   chain, shared primary file, same `model` pin — is now served by ONE continued implementer
   via SendMessage; capped ~4 tasks because a warm agent accumulates context toward
   compaction; verifier always fresh); **Lean driver** (the orchestrator's context is the
   most expensive artifact in a run — priced, cached, re-sent every turn; it now reads only
   PLAN/TASKS/NOTES + verify output and delegates all exploration to haiku scouts returning
   conclusions); **Quality scorecard** (the plugin measured only dollars and asserted
   quality; now `/execute` records outcomes and `bin/routing_scorecard.py` measures quality
   retained). Name `skills/execute/SKILL.md` sections where each landed.
2. `## The outcome ledger` — the grammar block verbatim from the execute skill
   (`outcome: <task-id> model=<model> attempts=<n> result=<result> review=<review>`), the two
   vocabularies, last-line-wins, tolerance for old ledger-free kits.
3. `## The scorecard` — usage (`python3 bin/routing_scorecard.py <slug>`, `--json`,
   `--session <id>` for dollars vs the all-frontier counterfactual, `--demo` as the synthetic
   smoke); the metric definitions from PLAN.md D7 (first-try rate, escalation rate, model
   mix, cheap-model review survival — cheap = below the expensive tiers per pricing.json,
   `fable` aliasing the frontier tier); the read-only reuse contract (parse via
   `copilot_execute.parse_tasks`, dollars via `session_cost` — never re-implemented, never
   edited).
4. `## Upstream limitation — main-session model switching` — nothing in a plugin can switch
   the MAIN session's model (only the user, via `/model`); Fusion's remaining structural
   trick — swap the driver to a cheaper model at context-compaction boundaries, where the
   prompt cache is invalidated anyway — therefore needs Claude Code / the Agent SDK to
   expose main-session model control; state it as the upstream ask, and that the warm
   sidekick + lean driver are the in-plugin equivalents until then.
5. `## Deferred — Tier 2` — dynamic mid-kit re-routing (execute consulting live scorecard
   numbers to re-pin later tasks' models) behind an opt-in autonomy dial; explicitly a
   planned follow-up kit, with this kit's outcome ledger as its data substrate.

No prices, no real model ids (tier names and `fable`-as-alias are fine), no `/private/tmp/`
paths.

**Acceptance.** File exists with the H1 + exactly those five H2s in order; grammar line
verbatim; mentions `--demo`, `--session`, `SendMessage`, `/model`, and the Agent SDK ask;
greps clean; suite green; only this file new.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && echo 'T7 OK'
import re
t = open('docs/FUSION-TIER1.md').read()
assert t.lstrip().startswith('# Fusion Tier 1 — multi-model orchestration borrows')
h2s = [l for l in t.splitlines() if l.startswith('## ')]
assert h2s == ['## The three borrows', '## The outcome ledger', '## The scorecard',
               '## Upstream limitation — main-session model switching', '## Deferred — Tier 2'], h2s
assert 'outcome: <task-id> model=<model> attempts=<n> result=<result> review=<review>' in t
for s in ('--demo', '--session', 'SendMessage', '/model', 'Agent SDK', 'routing_scorecard.py',
          'parse_tasks', 'session_cost'):
    assert s in t, f'missing: {s}'
assert not re.search(r'claude-(fable|opus|sonnet|haiku)-?[0-9]', t), 'real model id in doc'
assert '/private/tmp' not in t
print('doc structure ok')
PY
```

---

### T8 — Pinned README + CLAUDE.md insertions
- status: done
- model: haiku
- depends: T5
- independent: yes

**Brief.** Three pinned insertions, nothing else. If any anchor below is not found verbatim,
STOP and report.

*Insertion 1 — README.md, Skills table.* Immediately AFTER the table row that starts
`| \`bin/session_cost.py\` (script) |`, insert this new row (one line):

```
| `bin/routing_scorecard.py` (script) | Turns an executed kit's outcomes into a routing-quality scorecard: verify passed first-try vs retry vs escalated vs blocked, the model mix, the share of cheap-model work that survived review unchanged, and — with `--session` — dollars vs an all-Fable counterfactual (via `session_cost`). Read-only; `--json` for machine output; `--demo` runs on a built-in synthetic kit. |
```

*Insertion 2 — README.md, "## Key constraint to know" section.* At the end of that section's
existing paragraph (which ends `...so `/route` offers to run a task in a subagent pinned to
the cheaper model.`), append to the same paragraph:

```
 The same constraint blocks the strongest remaining multi-model trick — swapping the main-session model at context-compaction boundaries — which stays an upstream ask, documented in [docs/FUSION-TIER1.md](docs/FUSION-TIER1.md).
```

*Insertion 3 — CLAUDE.md, "## How to run things" code block.* Immediately AFTER the line
that starts `python3 bin/session_cost.py`, insert this line into the same code block:

```
python3 bin/routing_scorecard.py --demo           # routing-quality scorecard smoke (synthetic kit, no real data)
```

**Acceptance.** All three insertions present exactly once; no other lines changed in either
file (`git diff --stat` shows only README.md and CLAUDE.md among files this task touched);
suite green.

**Verify.**
```bash
cd /path/to/polytropos && python3 - <<'PY' && python3 -m unittest discover -s tests && echo 'T8 OK'
r = open('README.md').read(); c = open('CLAUDE.md').read()
assert r.count('| `bin/routing_scorecard.py` (script) |') == 1, "README row missing/duplicated"
i_sc = r.index('| `bin/session_cost.py` (script) |'); i_rs = r.index('| `bin/routing_scorecard.py` (script) |')
assert i_rs > i_sc and r[i_sc:i_rs].count('\n') == 1, "scorecard row not directly after session_cost row"
assert r.count('swapping the main-session model at context-compaction boundaries') == 1
assert 'docs/FUSION-TIER1.md' in r
assert c.count('python3 bin/routing_scorecard.py --demo') == 1, "CLAUDE.md run-line missing/duplicated"
assert c.index('bin/session_cost.py') < c.index('python3 bin/routing_scorecard.py --demo')
print('insertions ok')
PY
```

---

*Phase 3 end — dispatch `fusion-tier1-reviewer`, then run PLAN.md's overall done-check.*
