# TASKS — copilot-skills-parity

Repo root: `/path/to/polytropos`. Run all verify commands from
there. Read `PLAN.md` (same directory) first — especially the Ground truth (it replaces any
live verification: NEVER invoke a real CLI or fetch the web to "check"), decisions D1–D9, the
OUT-OF-SCOPE fence, and the risks/tripwires. Status vocabulary:
`pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `copilot-skills-parity-implementer` (the parameter overrides the
agent's frontmatter default). Dispatch `copilot-skills-parity-reviewer` at each phase end.

Warm-cluster hints: T1 → T7 is ONE strictly serial chain — every task edits
`copilot/aesop.yaml` and `tests/test_copilot_bundle.py`, and all seven carry `model: sonnet` —
so warm implementer clusters apply: serve T1–T4 with one warm implementer, then start a fresh
one for T5–T7 (cap ~4 tasks per warm agent). T8 (`haiku`) is always a fresh spawn, as is the
verifier.

Standing rules for every task: NEVER invoke the real `copilot`, `codex`, or `claude` CLI in
any form (real runs spend real AI Credits and hit the network; command lines you WRITE into
skill bodies are runtime instructions, not commands you run); nothing outside this repo —
`~/.copilot`, `~/.codex`, `~/.claude` included; never edit `skills/`, `codex/`, `bin/`
(`bin/harness_select.py` included — its skills glob already installs the bundle skills),
`data/` (all three pricing files), `.claude-plugin/`, `README.md`, any `*.agent.md` file,
`copilot/.github/skills/lessons-loop/`, or any completed kit; no node/npm/`aesop compile`, no
network; test edits are ADDITIVE at the seams each brief pins — every other test
class/method/constant stays byte-intact; skill files carry `{{POLYTROPOS_ROOT}}`, never
an absolute path, never `${CLAUDE_PLUGIN_ROOT}`, never `data/pricing.json` or
`data/pricing.codex.json`; skill frontmatter is `name` + `description` ONLY (a `model:` line
is a defect) and no frontmatter value contains an unquoted `: `; skill bodies quote ONLY the
argparse flags pinned in PLAN.md's Ground truth and never a pricing-key model id; verify
commands use `python3 -m unittest discover -s tests [-p '<file>.py']` (the dotted-module form
is broken on this machine). Where a brief pins content verbatim, reproduce it exactly; if a
pinned anchor is not present verbatim in the target file, STOP and report the discrepancy.

Shared shape for every new skill (D2 — apply in every skill task):

- File: `copilot/.github/skills/<name>/SKILL.md`. Frontmatter exactly three lines of content
  (`---`, `name: <name>`, `description: <pinned sentence>`, `---`).
- Body ~40–70 lines: the operative core of the same-named agent
  (`copilot/.github/agents/<name>.agent.md` — read it first; condense, don't copy verbatim):
  engine commands with `{{POLYTROPOS_ROOT}}` paths, the honesty rails, the decision
  guidance. Keep the AIC-are-real-money framing where cost appears.
- Close every body with these two paragraphs (adapt `<name>` only):

  ```markdown
  ## Same-named agent

  For persona-isolated runs — a separate dispatch that should carry its own model pin
  instead of this session's model — use the `<name>` custom agent: pick it in the `/agent`
  picker, or run `copilot --agent <name> -p "<task>"`. This skill and that agent are the
  same capability on two surfaces; the agent's frontmatter carries the model pin, this
  skill runs on whatever model the session already uses.

  ## Installed?

  If the literal `{{POLYTROPOS_ROOT}}` text is still visible above, the bundle is not
  installed — tell the user to run `python3 bin/harness_select.py install --harness copilot`
  (then `/skills reload` picks the skills up in-session).
  ```

- Manifest: append `- <name>` to `copilot/aesop.yaml` `primitives:` → `skills:` (after the
  existing entries, matching `- lessons-loop`'s exact indentation).
- Tests: the task's pinned additive seam in `tests/test_copilot_bundle.py`. Suite green at
  the task boundary (set-equality atomicity).

---

## Phase 1 — Decision-aid skills

### T1 — `route` skill + the three generic skill sweeps
- status: done
- model: sonnet
- depends: (none)
- independent: no (serial chain head)

**Brief.** Land the flagship `/route` skill (D1/D2) plus, ONCE, the generic skill sweeps that
auto-cover every later skill (D6). Read first: `copilot/.github/agents/route.agent.md` (the
source content + voice), `copilot/.github/skills/lessons-loop/SKILL.md` (format precedent),
`tests/test_copilot_bundle.py` in full (helpers `_frontmatter`, `_iter_bundle_files`, the
`FrontmatterYamlSafetyTests` regex you will mirror), and PLAN.md's Ground truth (argparse
surfaces).

Three files, one atomic change:

1. **`copilot/aesop.yaml`** — in `primitives:` → `skills:`, append `- route` after
   `- lessons-loop`, exact same indentation. Nothing else.
2. **`copilot/.github/skills/route/SKILL.md`** — new dir + file, shared shape.
   `description:` pinned verbatim (same as the agent's):
   `Pick the right Copilot model for a task and estimate its cost in AI Credits before running it. Use when the user asks which model to use, what a task will cost, whether a cheaper model would do, or how much of their plan allowance a job will burn.`
   Body sections (condensed from the agent):
   - **Get the numbers from data — never from memory**: the three engine lines
     (`python3 {{POLYTROPOS_ROOT}}/bin/copilot_pricing.py est <PROFILE> <MODEL_ID>`,
     `... models --profile <PROFILE>`, `... runway <PLAN> <PROFILE> <MODEL_ID>`); never quote
     prices, ratios, allowances, or the AIC-to-USD rate from memory — the unit itself is data
     (`billing_unit.usd_per_credit`).
   - **Load routing lessons first**: if `tasks/lessons.md` exists, apply `routing` entries
     (the `lessons-loop` skill) before classifying.
   - **Classify into a tier**: the four-value vocabulary (`cheap|mid|strong|frontier`) with
     the agent's one-line characterizations; between two tiers pick the cheaper and name the
     failure signal that justifies upgrading; compare candidates within a tier from the data,
     not vendor loyalty. Do NOT name any model id — tier words and engine output only.
   - **Estimate**: map to the closest `task_profiles` size (XS–XL), run the engine for 2–3
     candidates plus one lane cheaper, present USD + AIC (AIC are money), add `runway` when
     the plan is known.
   - **Recommend, then act**: the agent's real-control-surfaces table verbatim in spirit —
     one-shot `copilot -p "<task>" --model <model-id>`, interactive `/model`, session
     `COPILOT_MODEL`, persistent `"model"` in settings.json, per-agent `model:` frontmatter.
     Output shape: short table, recommended row bold, then the single action command.
   - The two pinned closing paragraphs (shared shape).
3. **`tests/test_copilot_bundle.py`** — additive edits only, appended AFTER
   `FrontmatterYamlSafetyTests` (before the `if __name__` block), nothing else changed:
   - Helper at module level (after `_frontmatter`):
     ```python
     def _iter_skill_md_files():
         if not SKILLS_DIR.is_dir():
             return []
         return sorted(SKILLS_DIR.glob("*/SKILL.md"))
     ```
   - `class SkillFrontmatterTests(unittest.TestCase)` — iterate `_iter_skill_md_files()`;
     for each, with `subTest(skill=<dir name>)`: frontmatter has `name:` exactly equal to the
     parent dir's name (regex `^name:\s*(\S+)\s*$`), a non-empty `description:` line, and NO
     line matching `^model:` — skills carry no model pin (D2).
   - `class SkillFrontmatterYamlSafetyTests(unittest.TestCase)` — one test method applying
     the SAME unquoted-`': '` scan `FrontmatterYamlSafetyTests` uses (copy its loop body,
     swapping the iterator to `_iter_skill_md_files()` and the offender label to
     `<skill dir>/SKILL.md [<key>]`). Do not modify the agent-side class.
   - `class SkillNoModelIdTests(unittest.TestCase)` — one test method: load
     `PRICING_COPILOT_JSON`, and for every file from `_iter_skill_md_files()` assert no key
     of `pricing["models"]` appears in the file text (ids derived at test time — no literal
     ids in the test).
   - `class RouteSkillContractTests(unittest.TestCase)` — `_text(self)` reads
     `SKILLS_DIR / "route" / "SKILL.md"`; four methods:
     `test_route_estimates_from_engine` (asserts `"bin/copilot_pricing.py"` and `"est"` in
     the text), `test_route_uses_placeholder` (asserts `"{{POLYTROPOS_ROOT}}"`),
     `test_route_points_at_agent` (asserts `"copilot --agent route"`),
     `test_route_reads_lessons` (asserts `"tasks/lessons.md"`).

**Acceptance.**
- Manifest skills block lists exactly `lessons-loop`, `route`; skill file in shared shape with
  the pinned description byte-exact; no `model:` line; body quotes only pinned flags and no
  pricing-key id; the three generic sweeps pass over BOTH `lessons-loop` and `route` (do not
  edit lessons-loop); only the pinned helper + four classes added to the test file.
- Verify command green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_bundle.py' -v
```

### T2 — `usage` + `journal` skills
- status: done
- model: sonnet
- depends: T1
- independent: no (serial chain)

**Brief.** Two read-only reporter skills (D1/D2). Read first:
`copilot/.github/agents/usage.agent.md` and `copilot/.github/agents/journal.agent.md` (source
content — condense each), PLAN.md's Ground truth (their pinned argparse surfaces).

Five files, one atomic change:

1. **`copilot/aesop.yaml`** — append `- usage` then `- journal` after `- route`, same
   indentation.
2. **`copilot/.github/skills/usage/SKILL.md`** — shared shape. `description:` pinned verbatim
   (the agent's):
   `Analyze historical Copilot CLI spend from local session logs — spend by model and session in USD and AI Credits, read-only. Use when the user asks what they've spent, which models they've been using, or where they could save.`
   Body: run `python3 {{POLYTROPOS_ROOT}}/bin/copilot_usage.py --days 30` (flags:
   `--days`, `--top`, `--copilot-home`/`--session-dir` — no others); the engine reads
   `session-state/*/events.jsonl` strictly read-only, never the `*.db` stores, and NEVER
   invokes the `copilot` CLI to gather; everything priced from `data/pricing.copilot.json`
   at run time (USD + AIC — AIC are money); this skill reports history — for "what should I
   use next" point at `/route`. The two pinned closing paragraphs.
3. **`copilot/.github/skills/journal/SKILL.md`** — shared shape. `description:` pinned
   verbatim (the agent's):
   `Generate the daily work journal — collect today's AI usage across Claude Code, Copilot CLI, and Codex CLI plus git activity into a digest, then write the narrative, technical, and next-day-plan summaries. Use when the user asks for their work journal, daily summary, "what did I do today", or to plan tomorrow.`
   Body: collect with `python3 {{POLYTROPOS_ROOT}}/bin/journal_collect.py --print`
   (flags: `--date YYYY-MM-DD`, `--repo PATH` repeatable, `--journal-dir DIR` — no others;
   model-free, strictly read-only over the three homes, writes only under gitignored
   `journal/`); then the IN-SESSION two-pass flow ONLY:
   `python3 {{POLYTROPOS_ROOT}}/bin/journal_summarize.py --date <date> --dry-run`
   prints the prompts and spawns nothing — YOU write the three summaries from those prompts
   in this session and save them where the dry-run output indicates. Never recommend the
   headless summarize path from this harness (it dispatches the Claude CLI). The two pinned
   closing paragraphs.
4. **`tests/test_copilot_bundle.py`** — append after `RouteSkillContractTests`:
   - `class UsageSkillContractTests(unittest.TestCase)` — `_text` reads the usage SKILL.md;
     three methods: `test_usage_mentions_engine_and_placeholder` (asserts
     `"bin/copilot_usage.py"` and `"{{POLYTROPOS_ROOT}}"`), `test_usage_is_read_only`
     (asserts `"read-only"`), `test_usage_points_at_agent` (asserts
     `"copilot --agent usage"`).
   - `class JournalSkillContractTests(unittest.TestCase)` — `_text` reads the journal
     SKILL.md; three methods: `test_journal_mentions_collector` (asserts
     `"bin/journal_collect.py"`), `test_journal_pins_dry_run` (asserts `"--dry-run"`),
     `test_journal_points_at_agent` (asserts `"copilot --agent journal"`).

**Acceptance.**
- Manifest skills block: `lessons-loop`, `route`, `usage`, `journal`; both files in shared
  shape, descriptions byte-exact, no `model:` lines, no pricing-key ids (generic sweeps
  green over them automatically); only the two pinned classes added to the test file.
- Verify command green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_bundle.py' -v
```

### T3 — `frontier-check` + `effort` skills
- status: done
- model: sonnet
- depends: T2
- independent: no (serial chain)

**Brief.** The two judgment-dial skills, with the kit's tightest honesty rails (D7). Read
first: `copilot/.github/agents/frontier-check.agent.md` and
`copilot/.github/agents/effort.agent.md` (source content — the effort agent's picker facts
and unconfirmed-headless language are the model to condense), `codex/skills/effort/SKILL.md`
(the cross-harness skill precedent — do NOT copy its Codex flags).

Five files, one atomic change:

1. **`copilot/aesop.yaml`** — append `- frontier-check` then `- effort`, same indentation.
2. **`copilot/.github/skills/frontier-check/SKILL.md`** — shared shape. `description:`
   pinned verbatim (the agent's):
   `Decide whether a task is worth the harness's frontier-tier model versus a strong or mid model, and how to run it optimally — effort, task spec, refusal fallbacks. Use when the user asks "is the top model worth it here" or how to get the most out of it.`
   Body: never name a model — the roster changes, the tier does not; derive the frontier
   row(s) with `python3 {{POLYTROPOS_ROOT}}/bin/copilot_pricing.py models --json`
   (filter `tier == "frontier"`), then `est <PROFILE> <MODEL_ID>` once for the frontier
   candidate and once each for a strong and a mid candidate so the cost ratio is computed
   for THIS task's size, never remembered; the agent's worth-it/not-worth-it judgment
   guidance condensed; surface per-model `notes` from the data (refusal/safety caveats)
   when recommending the frontier row. The word `fable-check` must NOT appear. The two
   pinned closing paragraphs.
3. **`copilot/.github/skills/effort/SKILL.md`** — shared shape. `description:` pinned
   verbatim (the agent's):
   `Control the reasoning-effort dial for Copilot models — Copilot's per-model "Reasoning" setting, covering which models have it, how to set it, and when to turn it up or down. Use when the user asks to raise/lower reasoning effort, run at extra-high, or make a model think harder or cheaper.`
   Body (condense the effort agent — every rail survives):
   - Ladder from data, never memory:
     `python3 {{POLYTROPOS_ROOT}}/bin/copilot_pricing.py knobs` — relay what it
     prints; Title-Case display words, NOT other CLIs' lowercase tokens; never enumerate
     the ladder yourself.
   - The mechanism (the only confirmed one): set INTERACTIVELY in the `/model` picker —
     select the row, left/right arrow keys (footer: `←/→ reasoning effort`); per-model;
     rows showing `—` have no dial. State plainly that a headless surface is UNCONFIRMED
     to exist — no flag, no settings key; point at the correctable point in the data's
     knobs note; never invent or guess a flag.
   - Up/down guidance: leave the default for routine work; step UP one level at a time on
     concrete failure evidence only; step DOWN for bulk/latency-sensitive work; higher
     effort inflates output tokens and AIC are real money — size stakes with
     `est <PROFILE> <MODEL_ID>` (the printed number is a floor, not a ceiling).
   - Orthogonality: model choice is `/route`, verify-gated tier climbing is `/escalate`;
     effort fixes thinking-time gaps, tier jumps fix capability gaps.
   - The strings `--effort` and `model_reasoning_effort` must NOT appear anywhere in the
     file. The two pinned closing paragraphs.
4. **`tests/test_copilot_bundle.py`** — append after `JournalSkillContractTests`:
   - `class FrontierCheckSkillContractTests(unittest.TestCase)` — `_text` reads the
     frontier-check SKILL.md; three methods: `test_frontier_check_derives_from_data`
     (asserts `"bin/copilot_pricing.py"` and `"frontier"`),
     `test_frontier_check_is_not_named_fable` (asserts `"fable-check"` NOT in
     `_text().lower()`), `test_frontier_check_points_at_agent` (asserts
     `"copilot --agent frontier-check"`).
   - `class EffortSkillContractTests(unittest.TestCase)` — `_text` reads the effort
     SKILL.md; four methods mirroring `EffortAgentContractTests` byte-for-byte in spirit:
     `test_effort_derives_ladder_from_knobs` (asserts `"bin/copilot_pricing.py"` and
     `"knobs"`), `test_effort_teaches_interactive_picker` (asserts `"/model"` in the text
     and `"arrow"` in its lower()), `test_effort_headless_honesty` (asserts
     `"unconfirmed"` in its lower()), `test_effort_no_borrowed_or_invented_flag` (asserts
     `"--effort"` NOT in the text and `"model_reasoning_effort"` NOT in the text).

**Acceptance.**
- Manifest skills block has six names; both files in shared shape, descriptions byte-exact;
  `grep -rn -e '--effort' -e 'model_reasoning_effort' copilot/` empty; only the two pinned
  classes added.
- Verify command green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_bundle.py' -v && ! grep -rn -e '--effort' -e 'model_reasoning_effort' copilot/
```

---

## Phase 2 — Workflow skills

### T4 — `escalate` skill
- status: done
- model: sonnet
- depends: T3
- independent: no (serial chain)

**Brief.** The verify-gated ladder as a `/escalate` skill (D1/D2). Read first:
`copilot/.github/agents/escalate.agent.md` (source — its Step 0–4 structure condenses
cleanly), PLAN.md's Ground truth (`copilot_execute.py` pinned surface).

Three files, one atomic change:

1. **`copilot/aesop.yaml`** — append `- escalate`, same indentation.
2. **`copilot/.github/skills/escalate/SKILL.md`** — shared shape. `description:` pinned
   verbatim (the agent's):
   `Run one task on the cheapest sufficient model behind a machine-checkable success check, escalating to a stronger tier — frontier last — only if the check fails. Use for "try it cheap first, fall back to the top model if it doesn't work".`
   Body (condense the agent's five steps, keeping every rail):
   - Pin a machine-checkable success condition first; if none exists, say so plainly — a
     vibe is not a verify.
   - Pick the cheapest sufficient tier from the data
     (`python3 {{POLYTROPOS_ROOT}}/bin/copilot_pricing.py models --json`), candidate
     id from the tier's rows at run time, never memory.
   - Dispatch `copilot -p "<self-contained brief>" --model <model-id>` (the run sees
     nothing of this session — brief must be self-contained, including the verify command).
   - Verify YOURSELF; on fail retry once with the exact failure output; on second fail
     climb: tiers strictly ABOVE the current tier in `cheap → mid → strong → frontier`
     order, FIRST model in pricing-file order per tier, empty tiers skipped — the same rule
     `bin/copilot_execute.py` implements; each hop carries the failure evidence. Frontier
     last; report which rung passed (AIC are money — the ladder's savings are the point).
   - Kit tasks: prefer the driver —
     `python3 {{POLYTROPOS_ROOT}}/bin/copilot_execute.py run --kit <dir> --task <id> --max-escalations <N>`
     (this skill is for one-off tasks; for multi-task work see `/architect` + `/execute`).
   - The two pinned closing paragraphs.
3. **`tests/test_copilot_bundle.py`** — append after `EffortSkillContractTests`:
   `class EscalateSkillContractTests(unittest.TestCase)` — `_text` reads the escalate
   SKILL.md; three methods: `test_escalate_is_verify_gated` (asserts `"verify"`),
   `test_escalate_points_at_execute_driver` (asserts `"bin/copilot_execute.py"`),
   `test_escalate_derives_ladder_from_data` (asserts `"bin/copilot_pricing.py"`).

**Acceptance.**
- Manifest skills block has seven names; file in shared shape, description byte-exact, no
  pricing-key id in the body (tier words only); only the pinned class added.
- Verify command green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_bundle.py' -v
```

### T5 — `architect` skill
- status: done
- model: sonnet
- depends: T4
- independent: no (serial chain; fresh warm cluster starts here)

**Brief.** The plan-once-emit-a-kit capability as `/architect` (D1/D4). Read first:
`copilot/.github/agents/architect.agent.md` (source — kit contract language is verbatim
there) and `codex/skills/architect/SKILL.md` (the cross-harness precedent, including its
no-pin honesty paragraph).

Three files, one atomic change:

1. **`copilot/aesop.yaml`** — append `- architect`, same indentation.
2. **`copilot/.github/skills/architect/SKILL.md`** — shared shape. `description:` pinned
   verbatim:
   `Do the expensive planning once — deep-plan a complex task and write an execution kit (PLAN.md + TASKS.md with model-pinned, self-contained briefs) under tasks/kits/<slug>/ for the execute driver to dispatch on cheaper models. Use when the user says "architect this", "plan this big task", or asks for an execution kit.`
   Body (condense the agent; the kit-contract elements are load-bearing — the driver parses
   them):
   - What you produce: `tasks/kits/<slug>/` with `PLAN.md` (goal + checkable done,
     constraints + out-of-scope fence, decisions with rationale, risks/tripwires) and
     `TASKS.md` (ordered `## Phase N` headings; each task carries `id`, `title`, `status`,
     `model`, `depends:`/`independent:`, a SELF-CONTAINED brief, acceptance criteria, a
     runnable verify command). `NOTES.md` is owned by the execute driver — do not create it.
   - Status vocabulary verbatim: `pending | in-progress | done | blocked`; new tasks start
     `pending`.
   - Pin every task's model from data, never memory
     (`python3 {{POLYTROPOS_ROOT}}/bin/copilot_pricing.py models` /
     `est <PROFILE> <MODEL_OR_TIER>`); tier guidance: cheap = mechanical, mid = the default
     lane, strong = multi-file/hard/review, frontier = only what strong would genuinely
     fail, and say why.
   - Verify commands: runnable from the repo root, prove acceptance mechanically, and never
     invoke the real `copilot` CLI — dispatch is the execute driver's job and real runs
     spend real AI Credits.
   - Model honesty (D4): this skill carries no `model:` pin — planning quality tracks the
     model driving it, so either switch the session to the frontier tier first (`/model`;
     find the frontier row via `models --json`, never from memory) or use
     `copilot --agent architect`, whose frontmatter pin carries the frontier model.
   - Hand off: report slug, phase/task breakdown, per-task pins with one-line rationale;
     execution belongs to `/execute`.
   - The two pinned closing paragraphs.
3. **`tests/test_copilot_bundle.py`** — append after `EscalateSkillContractTests`:
   `class ArchitectSkillContractTests(unittest.TestCase)` — `_text` reads the architect
   SKILL.md; four methods: `test_architect_emits_kits` (asserts `"tasks/kits/"`),
   `test_architect_status_vocabulary` (asserts
   `"pending | in-progress | done | blocked"`), `test_architect_pins_from_data` (asserts
   `"bin/copilot_pricing.py"`), `test_architect_points_at_agent` (asserts
   `"copilot --agent architect"`).

**Acceptance.**
- Manifest skills block has eight names; file in shared shape, description byte-exact, kit
  contract elements present verbatim, no pricing-key id in the body; only the pinned class
  added.
- Verify command green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_bundle.py' -v
```

### T6 — `execute` skill (the honest orchestration surface)
- status: done
- model: sonnet
- depends: T5
- independent: no (serial chain)

**Brief.** The Claude `/polytropos:execute` experience, ported honestly (D3): Copilot
drives kits through `bin/copilot_execute.py` serially — it does NOT have Claude Code's
parallel Agent-tool fan-out or warm SendMessage clusters, and this skill says so instead of
faking an orchestrator. Read first: `copilot/.github/agents/implementer.agent.md` +
`verifier.agent.md` + `reviewer.agent.md` (the agents the driver dispatches), PLAN.md's
Ground truth (the driver's pinned `status`/`run`/`review` surface — quote NO other flags).

Three files, one atomic change:

1. **`copilot/aesop.yaml`** — append `- execute`, same indentation.
2. **`copilot/.github/skills/execute/SKILL.md`** — shared shape. `description:` pinned
   verbatim (new — not copied from an agent):
   `Run an execution kit under tasks/kits/<slug>/ — drive bin/copilot_execute.py task by task, verify each result, and climb the pricing tiers only on failure. Use when the user says to execute, continue, or resume a kit or plan.`
   Body:
   - Role framing: the expensive thinking is already in the kit — your job is faithful
     dispatch, verification, and state-keeping; do not re-litigate the plan. Read the kit's
     `PLAN.md` fence before starting.
   - See state: `python3 {{POLYTROPOS_ROOT}}/bin/copilot_execute.py status --kit <dir>`
     (add `--json` for machine-readable). Status vocabulary verbatim:
     `pending | in-progress | done | blocked`.
   - Run tasks: `python3 {{POLYTROPOS_ROOT}}/bin/copilot_execute.py run --kit <dir> --task <id>`
     — the driver dispatches the task to the `implementer` agent on the task's pinned
     model (`--agent <name>` overrides which agent), runs the verify command, retries with
     failure evidence, and climbs the pricing-tier ladder only on failure
     (`--max-escalations <N>` caps the climbing). Omit `--task` to take the first eligible
     pending task. `--dry-run` previews the exact dispatch without spending AI Credits —
     real runs spend real AI Credits, so preview when unsure.
   - Verify independently: the driver runs each task's verify command, but re-run it
     yourself before trusting a `done` — a dispatched run's claim of success is not
     evidence.
   - Phase boundaries:
     `python3 {{POLYTROPOS_ROOT}}/bin/copilot_execute.py review --kit <dir> --phase <n>`
     dispatches the reviewer agent against PLAN.md.
   - **What this harness does NOT have (say it, don't fake it)**: Claude Code's execute
     skill fans tasks out to parallel subagents and keeps warm agent clusters; Copilot CLI
     has no equivalent surface — kit tasks run serially, one `run` invocation at a time,
     and a task marked `independent:` means "safe to run in any order", not "runs in
     parallel". Escalation lives in the driver's ladder, not in a session-side valve.
   - End of run: report tasks completed/blocked/remaining with verify output, then check
     the kit's PLAN.md "done" definition.
   - The two pinned closing paragraphs — but for the "Same-named agent" paragraph use the
     `implementer` phrasing instead: there is no `execute` agent; the driver IS the
     orchestrator, and the agents it dispatches (`implementer`, `verifier`, `reviewer`)
     carry the model pins. Pin this replacement paragraph verbatim:

     ```markdown
     ## Agents under the hood

     There is no `execute` agent — this skill drives `bin/copilot_execute.py`, and the
     driver dispatches the kit's work to the `implementer`, `verifier`, and `reviewer`
     custom agents (`copilot --agent <name>` also reaches them directly). Each task's
     `model` pin from TASKS.md decides what the dispatch runs on, not this session's model.
     ```
3. **`tests/test_copilot_bundle.py`** — append after `ArchitectSkillContractTests`:
   `class ExecuteSkillContractTests(unittest.TestCase)` — `_text` reads the execute
   SKILL.md; four methods: `test_execute_drives_the_driver` (asserts
   `"bin/copilot_execute.py"` and `"--kit"`), `test_execute_status_vocabulary` (asserts
   `"pending | in-progress | done | blocked"`), `test_execute_caps_escalation` (asserts
   `"--max-escalations"`), `test_execute_orchestration_honesty` (asserts `"parallel"` in
   `_text().lower()` and `"serially"` in `_text().lower()` — the honesty paragraph, not a
   fake orchestrator).

**Acceptance.**
- Manifest skills block has nine names (`lessons-loop` + the eight new); file in shared
  shape, description byte-exact, only pinned driver flags quoted, the honesty paragraph
  present, "Agents under the hood" replaces the same-named-agent paragraph verbatim; only
  the pinned class added.
- Verify command green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_bundle.py' -v
```

---

## Phase 3 — Closeout

### T7 — Instructions sentence (manifest-first) + `docs/COPILOT-PARITY.md`
- status: done
- model: sonnet
- depends: T6
- independent: no

**Brief.** Tell Copilot — and the user — that the skills exist (D8). Read first:
`copilot/aesop.yaml`'s `instructions:` block and `copilot/.github/copilot-instructions.md`
in full (both doctrine sentences must survive byte-intact), `docs/EFFORT-DIAL.md` (docs
house style).

Three files:

1. **`copilot/aesop.yaml`** — inside `primitives:` → `instructions:` → `blocks:` →
   `content: |`, append as a new final paragraph line (matching the block's existing
   indentation), pinned verbatim:
   `Every optimizer capability is also invocable as a skill — type /route, /usage, /journal, /frontier-check, /escalate, /effort, /architect, or /execute in the prompt (or let Copilot auto-load one when the request matches its description); the same-named custom agents remain the persona surface for isolated --agent runs, and /skills reload picks up newly installed skills in-session.`
2. **`copilot/.github/copilot-instructions.md`** — append the SAME sentence verbatim as a
   new final paragraph. Pure appends in both files; nothing existing changes.
3. **`docs/COPILOT-PARITY.md`** — new file, the user-facing parity map. Contents:
   - Intro: the Claude Code plugin experience and its Copilot twin; skills are the
     `/name`-invocable surface (typed slash or auto-loaded by description match), agents
     the persona surface; sourced from the 2026-07-18 capture of GitHub's docs.
   - The parity table (pin this mapping):

     | Claude Code | Copilot CLI |
     |---|---|
     | `/polytropos:route` | `/route` skill, or `copilot --agent route` |
     | `/polytropos:cost-report` | `/usage` skill, or `copilot --agent usage` |
     | `/polytropos:journal` | `/journal` skill, or `copilot --agent journal` |
     | `/polytropos:fable-check` | `/frontier-check` skill, or `copilot --agent frontier-check` |
     | `/polytropos:escalate` | `/escalate` skill, or `copilot --agent escalate` |
     | `/polytropos:architect` | `/architect` skill, or `copilot --agent architect` (carries the frontier pin) |
     | `/polytropos:execute` | `/execute` skill driving `bin/copilot_execute.py` (serial; no parallel-subagent equivalent) |
     | (no Claude twin) | `/effort` skill — Copilot's per-model Reasoning dial |
     | `/polytropos:setup` (statusline) | already wired — settings.json `statusLine` → `bin/copilot_statusline.py`; no skill needed |
     | memory skill | deferred — a future cross-harness kit |
   - Install/refresh: `python3 bin/harness_select.py install --harness copilot` (agents →
     `~/.copilot/agents/`, skills → `~/.copilot/skills/`, placeholder resolved), then
     `/skills reload` in a live session; `/skills` lists, `/skills info <name>` inspects.
   - Honest limits: true custom slash COMMANDS are not supported in Copilot CLI (open
     feature requests github/copilot-cli #618 and #1113; the extensions SDK is a separate,
     out-of-scope surface) — skill `/name` invocation is the parity mechanism; no headless
     reasoning-effort surface is confirmed; kit execution is serial via the driver.
   - No prices, no model ids — point at `data/pricing.copilot.json` + the engines.

**Acceptance.**
- Both instruction surfaces carry the pinned sentence byte-identically; both doctrine
  sentences intact (`DoctrineSentenceSyncTests` green); the doc exists with the table,
  install steps, and honest-limits section; no price or pricing-key model id in the doc.
- Verify command green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_bundle.py' -v && grep -c "Every optimizer capability is also invocable as a skill" copilot/aesop.yaml copilot/.github/copilot-instructions.md
```

### T8 — Full-suite + frozen-surface audit
- status: done
- model: haiku
- depends: T7
- independent: no

**Brief.** Mechanical closeout. Run the checks below EXACTLY and report their output
faithfully — fix nothing yourself; a failure is reported, not patched.

1. Full suite: `python3 -m unittest discover -s tests -v` — expect fully green.
2. Frozen surfaces byte-untouched:
   `git diff --quiet -- skills codex bin data .claude-plugin README.md copilot/.github/agents copilot/.github/skills/lessons-loop && echo FROZEN-OK`
   — expect `FROZEN-OK`.
3. Roster shape: `ls copilot/.github/skills` — expect exactly `architect effort escalate
   execute frontier-check journal lessons-loop route usage` (nine dirs).
4. Rail greps (all must find nothing):
   `! grep -rn -e '--effort' -e 'model_reasoning_effort' copilot/`
   `! grep -rn 'CLAUDE_PLUGIN_ROOT' copilot/`
   `! grep -rn '/Users/' copilot/`
   `! grep -rn 'fable-check' copilot/.github/skills/`
5. Placeholder present in every new skill:
   `grep -L 'POLYTROPOS_ROOT' copilot/.github/skills/*/SKILL.md` — expect ONLY the
   lessons-loop path (the one pre-existing skill legitimately has no engine calls).

**Acceptance.** All five checks pass with the expected output, reported verbatim.

**Verify.**
```bash
python3 -m unittest discover -s tests -v 2>&1 | tail -3 && git diff --quiet -- skills codex bin data .claude-plugin README.md copilot/.github/agents copilot/.github/skills/lessons-loop && echo FROZEN-OK
```
