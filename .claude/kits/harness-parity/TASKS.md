# TASKS — harness-parity

Repo root: `/path/to/polytropos`. Run all verify commands from
there. Read `PLAN.md` (same directory) first — especially the ground-truth pins, decisions
D1–D10, the OUT-OF-SCOPE fence, and the risks/tripwires. Status vocabulary:
`pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `harness-parity-implementer` (the parameter overrides the
agent's frontmatter default). Tasks marked `independent: yes` within the same phase may run in
parallel; `depends:` lists hard ordering. Dispatch `harness-parity-reviewer` at each phase end.

Warm-cluster hints: the **Copilot lane** T1 → T3 → T5 → T7 is strictly serial and shares
`copilot/aesop.yaml` + `tests/test_copilot_bundle.py` (all `model: sonnet` — one warm
implementer may serve the chain). The **Codex lane** T2 → T4 → T6 → T8 is strictly serial and
shares `tests/test_codex_bundle.py` (all `model: sonnet` — a second warm implementer). The two
lanes are mutually independent and may run in parallel with each other. The verifier is always
a fresh spawn.

Standing rules for every task: NEVER invoke the real `copilot`, `codex`, or `claude` CLI in
any form (they spend real credits/usage limits and hit the network — the `copilot -p` /
`codex exec` lines you WRITE into bundle bodies are runtime instructions for the user, not
commands you run); nothing outside this repo — `~/.copilot`, `~/.codex`, `~/.claude` included;
never edit `bin/`, `data/` (all three pricing files), `skills/`, `.claude-plugin/`, `docs/`,
`README.md`, the ten pre-existing bundle files (five `copilot/.github/agents/*.agent.md`, five
`codex/prompts/*.md`), `copilot/.github/skills/`, or any completed kit; no node/npm/`aesop
compile`; test edits are ADDITIVE at the seams each brief pins — every other test
class/method/constant stays byte-intact; bundle files carry `{{POLYTROPOS_ROOT}}`, never
an absolute path, never `${CLAUDE_PLUGIN_ROOT}`, never another harness's pricing path; verify
commands use `python3 -m unittest discover -s tests [-p '<file>.py']` (the dotted-module form
is broken on this machine). Where a brief pins content verbatim, reproduce it exactly; if a
pinned anchor is not present verbatim in the target file, STOP and report the discrepancy.

---

## Phase 1 — Easy wins: usage + journal (engines already exist)

### T1 — Copilot `usage` agent (manifest + bundle + tests, atomic)
- status: done
- model: sonnet
- depends: (none)
- independent: yes (Copilot-lane head; parallel with T2)

**Brief.** Port the Claude `cost-report` skill's intent to a Copilot custom agent named
`usage`, wrapping the existing `bin/copilot_usage.py` engine. Read first:
`tests/test_copilot_bundle.py` (what you must keep green and where you extend),
`copilot/.github/agents/route.agent.md` (the house agent format and voice),
`skills/cost-report/SKILL.md` (the source intent you are porting), and the module docstring +
`main()` of `bin/copilot_usage.py` (the real flags and honesty rules — do not invent flags).

Three files, one atomic change (PLAN.md D2 — the roster test is set-equality, so all three
land together):

1. **`copilot/aesop.yaml`** — in `primitives:` → `agents:`, append `- usage` after
   `- reviewer`, matching the existing entries' exact indentation. Touch nothing else in the
   manifest.
2. **`copilot/.github/agents/usage.agent.md`** — new file, house format (frontmatter `name`,
   `description`, `model`, then body):
   - `name: usage`.
   - `description:` one sentence, route-agent style: analyze historical Copilot CLI spend
     from local session logs — spend by model and session in USD and AI Credits, read-only;
     use when the user asks what they've spent, which models they've been using, or where
     they could save.
   - `model:` a LIVE **cheap-tier** model id — open `data/pricing.copilot.json` and take the
     FIRST model in file order whose `tier` is `"cheap"`. Copy the id from the data file at
     implementation time, not from anywhere else (PLAN.md D5).
   - Body (model it on route.agent.md's structure and length, ~40–70 lines):
     - Run `python3 {{POLYTROPOS_ROOT}}/bin/copilot_usage.py --days 30` (flags:
       `--days N` lookback, `--top N` sessions listed, default 30/10). The engine reads
       `~/.copilot/session-state/*/events.jsonl` strictly read-only and prices from
       `{{POLYTROPOS_ROOT}}/data/pricing.copilot.json` — never quote a price, credit
       value, or model id from memory, and NEVER invoke the `copilot` CLI to gather usage
       (the logs are the source).
     - Summarize the emitted markdown rather than dumping it: a headline (total USD + AIC
       over the window, dominating model), the by-model table as emitted, downgrade
       candidates as emitted, and ONE actionable recommendation. AIC are money — each credit
       costs `billing_unit.usd_per_credit` from the data.
     - Honesty rules carried from the engine: multi-model sessions are flagged `≈` (the whole
       token split is attributed to the last model — never fabricate a per-model split);
       `totalNanoAiu` is a labeled cross-check only, never converted to USD/AIC; missing or
       empty logs are reported as such, never guessed.
     - Close with the placeholder paragraph mirroring route.agent.md's: if the literal
       `{{POLYTROPOS_ROOT}}` text is still visible, the bundle is not installed — run
       `python3 bin/harness_select.py install --harness copilot`.
3. **`tests/test_copilot_bundle.py`** — two additive edits, nothing else changed:
   - Add `"usage": "cheap",` to the `WORKFLOW_AGENT_TIERS` dict (~line 174).
   - Add a NEW class `PortedAgentContractTests(unittest.TestCase)` after
     `WorkflowAgentContractTests`, with a `_text(self, stem)` helper identical in shape to
     `WorkflowAgentContractTests._text`, and two methods:
     `test_usage_mentions_engine_and_placeholder` asserting both `"bin/copilot_usage.py"` and
     `"{{POLYTROPOS_ROOT}}"` are in `self._text("usage")`, and
     `test_usage_is_read_only` asserting `"read-only"` is in `self._text("usage")`.

**Acceptance.**
- `copilot/aesop.yaml` agents block lists exactly six names ending `- usage`; nothing else in
  the manifest changed.
- `usage.agent.md` exists; frontmatter has `name`/`description`/`model`; the `model:` value is
  a key of `data/pricing.copilot.json` with tier `cheap`; body contains no absolute path, no
  `CLAUDE_PLUGIN_ROOT`, no `data/pricing.json` mention, no invented engine flags (only
  `--days`/`--top` from the real argparse surface).
- `tests/test_copilot_bundle.py`: only the pinned dict entry + new class added; every
  pre-existing class/method byte-intact.
- Verify command green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_bundle.py' -v
```

### T2 — Codex `usage` prompt (bundle + roster test, atomic)
- status: done
- model: sonnet
- depends: (none)
- independent: yes (Codex-lane head; parallel with T1)

**Brief.** Port the Claude `cost-report` skill's intent to a Codex custom prompt named
`usage`, wrapping the existing `bin/codex_usage.py` engine. Read first:
`tests/test_codex_bundle.py` (roster + contract cases), `codex/prompts/route.md` (house
prompt format and the billing-honesty voice), `codex/AGENTS.md` (the proxy-not-a-bill
doctrine), `skills/cost-report/SKILL.md` (source intent), and the module docstring + `main()`
of `bin/codex_usage.py` (real flags: `--days N`, `--top N`, `--codex-home DIR`, `--json`; the
honesty ladder).

Two files, one atomic change (PLAN.md D3):

1. **`codex/prompts/usage.md`** — new file. Frontmatter is EXACTLY a `description:` line
   between `---` fences — NO `model:` line (test-enforced). Description: analyze historical
   Codex CLI activity from local session logs, read-only — honestly unpriced or
   labeled-proxy; use when the user asks what they've used, burned, or spent. Body
   (~40–70 lines, route.md's voice):
   - Run `python3 {{POLYTROPOS_ROOT}}/bin/codex_usage.py --days 30` (`--top N` for the
     session list; `--json` for machine-readable). The engine walks
     `~/.codex/session_index.jsonl`, `history.jsonl`, and `sessions/YYYY/MM/DD/*.jsonl`
     strictly read-only (JSONL only, never a `*.db`), prices only tokens it actually finds
     from `{{POLYTROPOS_ROOT}}/data/pricing.codex.json`, and NEVER invokes `codex`.
   - Relay the engine's honesty ladder faithfully: tokens found → per-model table with
     API-equivalent dollars PLUS the engine's standing disclaimer (figures are a
     relative-burn proxy; subscription usage is usage-limited, not token-billed — never
     present a subscription figure as a bill); activity but no tokens → counts only,
     unpriced, say so; nothing → say the logs are empty. Never fabricate or zero-fill a
     dollar figure.
   - Summarize, don't dump: headline, table, one actionable recommendation (e.g. a tier or
     effort change), in the mode-appropriate framing (real dollars ONLY for
     `OPENAI_API_KEY`-metered use).
   - Placeholder paragraph mirroring route.md's (`install --harness codex`).
   - Model names in your report come from the ENGINE's output at run time — this file must
     not contain any real model id from the pricing data (test-enforced) nor the string
     "fable" in any case.
2. **`tests/test_codex_bundle.py`** — additive edits at pinned seams, nothing else changed:
   - Directly under `EXPECTED_PROMPT_STEMS`, add a module-level
     `PORTED_PROMPT_STEMS = ("usage",)` and change the assignment to
     `EXPECTED_PROMPT_STEMS = {"route", "architect", "implementer", "verifier", "reviewer"} | set(PORTED_PROMPT_STEMS)`.
   - In `PromptRosterTests`, rename `test_prompt_roster_is_exactly_five` to
     `test_prompt_roster_matches_expected_stems` and update the class docstring to say the
     roster is exactly the expected workflow + ported prompts (the assertion body is
     unchanged). This rename happens ONCE, here — later tasks only extend
     `PORTED_PROMPT_STEMS`.
   - Add a NEW class `PortedPromptContractTests(unittest.TestCase)` with a
     `_text(self, stem)` helper reading `CODEX_PROMPTS_DIR / f"{stem}.md"`, and three
     methods: `test_placeholder_in_all_ported_prompts` (every stem in `PORTED_PROMPT_STEMS`
     contains `hs.PLACEHOLDER`), `test_no_fable_in_any_ported_prompt` (for every stem,
     `"fable" not in text.lower()`), and `test_usage_mentions_engine_and_proxy` (asserts
     `"bin/codex_usage.py"` in the usage text and `"proxy"` in it).

**Acceptance.**
- `codex/prompts/usage.md` exists; frontmatter is description-only; body carries the
  placeholder, the honesty-ladder framing, no real codex model id, no "fable", no absolute
  path, no other harness's pricing path.
- `tests/test_codex_bundle.py`: only the pinned seam edits (stems tuple + union, the single
  rename, the new class); all installer/other cases byte-intact.
- Verify command green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_codex_bundle.py' -v
```

### T3 — Copilot `journal` agent (manifest + bundle + tests, atomic)
- status: done
- model: sonnet
- depends: T1
- independent: no (shares aesop.yaml + test file with T1)

**Brief.** Port the Claude `journal` skill to a Copilot agent named `journal`. The journal
engine is harness-AGNOSTIC (it already reads `~/.claude`, `~/.copilot`, and `~/.codex`
read-only), so this agent instructs the SAME two-pass flow and produces the same
cross-harness journal. Read first: `skills/journal/SKILL.md` (the source flow you are
porting — follow its structure closely), `tests/test_copilot_bundle.py`, the argparse
surfaces of `bin/journal_collect.py` (flags `--date`, `--print`, `--repo` repeatable,
`--journal-dir`), `bin/journal_summarize.py` (`--date`, `--dry-run`; without `--dry-run` it
dispatches the CLAUDE CLI via `--claude-bin`), `bin/journal_askpack.py` (`--date`,
`--print`), and `bin/journal_plan.py` (subcommands `build [--for D] [--print]`, `prompt`,
`check`, `done <id>`, `defer <id> --to <date>`).

Three files, atomic:

1. **`copilot/aesop.yaml`** — append `- journal` after `- usage` in `primitives.agents`.
2. **`copilot/.github/agents/journal.agent.md`** — new file, house format:
   - `name: journal`; `description:` one sentence (generate the daily work journal — collect
     today's AI usage across Claude Code, Copilot CLI, and Codex CLI plus git activity into
     a digest, then write the narrative, technical, and next-day-plan summaries).
   - `model:` a LIVE **mid-tier** model id — FIRST model in file order in
     `data/pricing.copilot.json` whose `tier` is `"mid"`, copied from the data at
     implementation time.
   - Body (~50–80 lines), porting the skill's sections:
     - **Collect**: `python3 {{POLYTROPOS_ROOT}}/bin/journal_collect.py --print`
       (`--date YYYY-MM-DD` for a specific day; `--repo PATH` repeatable). Deterministic,
       read-only over the three homes, never calls a model or the network; writes only under
       the gitignored `journal/<date>/`.
     - **Write the summaries in-session (the ONLY mode from this harness)**: run
       `python3 {{POLYTROPOS_ROOT}}/bin/journal_summarize.py --date <date> --dry-run`
       to print the three prompts (narrative, technical, next-day-plan) without dispatching
       anything; read `journal/<date>/digest.json` for the facts; write the three documents
       YOURSELF (this session is already paid for) to `journal/<date>/narrative.md`,
       `technical.md`, `next-day.md`, following each printed prompt's required headings
       exactly, digest facts only. Then summarize and link the paths — don't paste full
       drafts. Pin the warning explicitly: NEVER run `journal_summarize.py` without
       `--dry-run` from this harness — its headless mode dispatches the Claude CLI, a
       cross-harness spend (PLAN.md D6).
     - **Inbox & ask-the-tools**: drop notes into `journal/inbox.md`;
       `python3 {{POLYTROPOS_ROOT}}/bin/journal_askpack.py --date <date> --print`
       generates the offline per-tool prompts (Copilot Studio / Teams / Outlook) — the user
       runs them in their own tools and pastes bullets back into the inbox; re-collect after.
       No network/OAuth/Graph, ever.
     - **Next-day runbook**: `python3 {{POLYTROPOS_ROOT}}/bin/journal_plan.py build`
       (then `prompt` to enrich What/How bodies in-session — keep every other line
       byte-identical; `check`/`done`/`defer` to track). Advisory only — it never schedules
       or executes anything.
     - **Privacy** paragraph carried from the skill: the digest is metadata-only (no
       transcript text); everything stays under gitignored `journal/`.
     - Placeholder paragraph (install line, as in T1).
3. **`tests/test_copilot_bundle.py`** — additive: `"journal": "mid",` in
   `WORKFLOW_AGENT_TIERS`; two methods appended to `PortedAgentContractTests`:
   `test_journal_mentions_collector` (asserts `"bin/journal_collect.py"` in
   `self._text("journal")`) and `test_journal_pins_dry_run` (asserts `"--dry-run"` in it).

**Acceptance.**
- Manifest agents block ends `- usage`, `- journal`; agent file in house format with a live
  mid-tier pin; body pins the `--dry-run`-only rule and contains no absolute path /
  `CLAUDE_PLUGIN_ROOT` / `data/pricing.json` mention / invented flags.
- Test file: only the pinned dict entry + two methods added.
- Verify green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_bundle.py' -v
```

### T4 — Codex `journal` prompt (bundle + roster test, atomic)
- status: done
- model: sonnet
- depends: T2
- independent: no (shares test file with T2; parallel with the Copilot lane)

**Brief.** Port the Claude `journal` skill to `codex/prompts/journal.md` — the same engine,
flow, and warnings as T3's Copilot port, in the Codex prompt format. Read first:
`skills/journal/SKILL.md`, `codex/prompts/route.md` (format/voice), T3's brief above for the
flow outline (collect → `--dry-run` prompts → write the three documents yourself → askpack →
runbook → privacy), and the same four `bin/journal_*.py` argparse surfaces.

1. **`codex/prompts/journal.md`** — new file, description-only frontmatter (no `model:`
   line). Body mirrors T3's five sections with `{{POLYTROPOS_ROOT}}/bin/...` paths, the
   same explicit warning that headless `journal_summarize.py` (without `--dry-run`) dispatches
   the Claude CLI and must never be run from this harness, and the placeholder paragraph
   (`install --harness codex`). No real codex model id, no "fable" (any case), no
   `data/pricing.json` or `data/pricing.copilot.json` mention (all test-enforced — when
   naming the journal's pricing sources generically, say "the pricing data files" rather than
   spelling the other harnesses' paths).
2. **`tests/test_codex_bundle.py`** — additive: extend the tuple to
   `PORTED_PROMPT_STEMS = ("usage", "journal")` (the placeholder and no-fable tests iterate
   it automatically); append one method to `PortedPromptContractTests`:
   `test_journal_mentions_collector_and_dry_run` (asserts `"bin/journal_collect.py"` and
   `"--dry-run"` in the journal text).

**Acceptance.** Prompt file exists in format; roster test green over seven stems; the
sweeping cases (frontmatter, placeholder, no-fable, no-model-id, harness separation) all pass
over the new file; only the pinned seam edits in the test file.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_codex_bundle.py' -v
```

---

## Phase 2 — Frontier adaptations: frontier-check + escalate

### T5 — Copilot `frontier-check` agent (manifest + bundle + tests, atomic)
- status: done
- model: sonnet
- depends: T3
- independent: no (Copilot lane)

**Brief.** Adapt the Claude `fable-check` skill into a Copilot agent named `frontier-check`:
"is this task worth the harness's FRONTIER-tier model (vs strong/mid), and if yes, how should
it be run." Never name it after a model (PLAN.md D1). Read first:
`skills/fable-check/SKILL.md` (the judgment being ported), `copilot/.github/agents/route.agent.md`
(tier framing + action table), `bin/copilot_pricing.py` flags, and the `models`/`plans`/
`billing_unit` shapes in `data/pricing.copilot.json`.

Three files, atomic:

1. **`copilot/aesop.yaml`** — append `- frontier-check` after `- journal`.
2. **`copilot/.github/agents/frontier-check.agent.md`** — new file:
   - `name: frontier-check`; `description:` one sentence (decide whether a task is worth the
     frontier-tier model versus a strong or mid model, and how to run it optimally; use when
     the user asks "is the top model worth it here" or how to get the most out of it).
   - `model:` a LIVE **mid-tier** id (first in file order, from the data — same rule as T3).
   - Body (~50–80 lines):
     - **Derive, never recall**: get the frontier model at run time via
       `python3 {{POLYTROPOS_ROOT}}/bin/copilot_pricing.py models --json` — the row(s)
       whose `tier` is `frontier`. Derive the frontier-vs-strong and frontier-vs-mid cost
       ratios by running `est <PROFILE> <MODEL_ID>` for the frontier model and one candidate
       from each lower tier — never quote a ratio, price, or model id from memory, and never
       write one into this file. If the user's plan is known, add
       `runway <PLAN> <PROFILE> <MODEL_ID>` (share of monthly allowance per task).
     - **Worth it when** (ported judgment): long-horizon autonomous work expected to complete
       without correction; a CONCRETE failure by a strong-tier model on this same task (the
       strongest signal); the deepest reasoning/multi-source synthesis; heavy parallel
       sub-agent orchestration. **Not worth it for**: routine coding, tasks with well-known
       solutions, anything a strong-tier model handles — everything a strong model can do,
       route to strong. AIC are money: the frontier tier burns allowance fastest on the
       roster, so the recommendation must say what makes the task frontier-worthy.
     - **Caveats to surface every time frontier is recommended**: check the frontier model's
       `notes` in the data and relay them; if its notes or vendor indicate safety-classifier
       refusals for cyber/bio-adjacent work, state the fallback — rerun on a strong-tier
       model and say why.
     - **How to run it optimally** (ported): full spec up front (goal, constraints, "done");
       de-prescribe migrated prompts (state goals, not steps); let it delegate and give it a
       notes file for multi-session work; require it to ground progress claims in tool
       results.
     - **Action lines** (copy the mechanism table rows from route.agent.md, don't invent):
       one-shot `copilot -p "<task>" --model <model-id>`; interactive `/model`; per-agent
       `model:` frontmatter pin.
     - **Standing recommendation**: for multi-task frontier-class work prefer the `architect`
       agent (the frontier model plans once into `tasks/kits/<slug>/`, cheaper tiers
       execute); for a single verify-gated task use the `escalate` agent. Point at both by
       name.
     - Placeholder paragraph (as T1).
3. **`tests/test_copilot_bundle.py`** — additive: `"frontier-check": "mid",` in
   `WORKFLOW_AGENT_TIERS`; two methods appended to `PortedAgentContractTests`:
   `test_frontier_check_derives_from_data` (asserts `"bin/copilot_pricing.py"` and
   `"frontier"` in `self._text("frontier-check")`) and
   `test_frontier_check_is_not_named_fable` (asserts `"fable-check" not in
   self._text("frontier-check").lower()`).

**Acceptance.** Manifest + file + tests land together; frontmatter pin is a live mid-tier
key; the BODY contains no model id that is a key of `data/pricing.copilot.json` (hand-check —
the frontmatter pin is the only one; PLAN.md D5/risk 3) and no invented flags; verify green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_bundle.py' -v
```

### T6 — Codex `frontier-check` prompt (bundle + roster test, atomic)
- status: done
- model: sonnet
- depends: T4
- independent: no (Codex lane)

**Brief.** Adapt `fable-check` for Codex: "is this task worth the frontier tier of the
GPT-5.6 family." Read first: `skills/fable-check/SKILL.md`, `codex/prompts/route.md`
(billing-mode-first rule, knobs/speed guidance, action table — copy its mechanisms, don't
invent), `codex/AGENTS.md` (proxy doctrine), `bin/codex_pricing.py` flags, and
`data/pricing.codex.json`'s `tier_note`, `knobs`, and `plans` shapes.

1. **`codex/prompts/frontier-check.md`** — new file, description-only frontmatter. Body
   (~50–80 lines):
   - **Billing mode FIRST** (mirror route.md): ChatGPT sign-in ⇒ subscription framing — the
     frontier question is about usage-limit burn, and any dollar figure is a labeled
     API-equivalent proxy, never a bill; `OPENAI_API_KEY` ⇒ real dollars. If unsure, ask.
   - **Derive, never recall**: the frontier model comes from
     `python3 {{POLYTROPOS_ROOT}}/bin/codex_pricing.py models --json` (the `frontier`
     tier row) or directly via `est <PROFILE> frontier` — `est` accepts a tier word, and per
     the data's `tier_note` an unpopulated tier resolves UPWARD (strong resolves to the
     frontier model on today's roster). Compare against the mid and cheap tiers the same
     way. This file must contain NO real model id (test-enforced).
   - **Worth it when / not worth it** — the T5 judgment list adapted: concrete failure by
     the MID tier is the strongest signal here (the data ships no populated strong tier);
     not worth it for routine work the mid tier handles, nor for low-latency work (the cheap
     tier is the speed lane per the data's knobs).
   - **How to run it optimally**: full spec up front; de-prescribe; sweep reasoning effort
     via `-c model_reasoning_effort=<minimal|low|medium|high|max>` instead of defaulting to
     `max` — `max` and `ultra` mode trade speed for depth (facts from the data's `knobs` and
     model `notes` only — surface them, never invent a flag; Codex fast mode's CLI surface is
     unpublished as of the data's `cached_date`, so point at release notes); the frontier
     model's Cerebras availability is a speed fact in its `notes`.
   - **Action lines** (from route.md's table): `codex exec "<task>" --model <model-id>` (add
     `--full-auto` when it must edit files); `/model` picker; `model = "<model-id>"` in
     `~/.codex/config.toml`.
   - **Standing recommendation**: multi-task frontier-class work → the `architect` prompt
     (plan once on frontier, execute on cheaper tiers); single verify-gated task → the
     `escalate` prompt.
   - Placeholder paragraph. No "fable" in any case.
2. **`tests/test_codex_bundle.py`** — additive: extend to
   `PORTED_PROMPT_STEMS = ("usage", "journal", "frontier-check")`; append one method to
   `PortedPromptContractTests`: `test_frontier_check_derives_from_data` (asserts
   `"bin/codex_pricing.py"` and `"frontier"` in the frontier-check text).

**Acceptance.** File + roster land together; description-only frontmatter; sweeping cases
green (placeholder, no-fable, no-model-id, harness separation); proxy framing present; only
pinned seam edits in the test file.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_codex_bundle.py' -v
```

### T7 — Copilot `escalate` agent (manifest + bundle + tests, atomic)
- status: done
- model: sonnet
- depends: T5
- independent: no (Copilot lane)

**Brief.** Port the Claude `escalate` skill to a Copilot agent named `escalate`: run ONE task
on the cheapest sufficient model behind a machine-checkable success check, escalating up the
pricing tiers — frontier last — only when the check fails. Read first:
`skills/escalate/SKILL.md` (the ladder discipline being ported), the module docstring and the
`escalation_ladder` function (~lines 204–260) of `bin/copilot_execute.py` (the ladder rule you
must mirror in prose), `copilot/.github/agents/route.agent.md` (dispatch surfaces), and
`bin/copilot_pricing.py` flags.

Three files, atomic:

1. **`copilot/aesop.yaml`** — append `- escalate` after `- frontier-check`.
2. **`copilot/.github/agents/escalate.agent.md`** — new file:
   - `name: escalate`; `description:` one sentence (run one task on the cheapest sufficient
     model behind a machine-checkable check, escalating to a stronger tier — frontier last —
     only if the check fails; use for "try it cheap first, fall back to the top model if it
     doesn't work").
   - `model:` a LIVE **mid-tier** id (first in file order, from the data).
   - Body (~50–80 lines), the ported ladder:
     - **Step 0 — the trigger**: pin a machine-checkable success condition before dispatching
       anything (a test command, a build, a lint, a script that exits non-zero on failure).
       If the task has no checkable outcome, say so plainly and fall back to escalating on a
       blocked report or your own adversarial read — don't pretend a vibe is a verify.
     - **Step 1 — first tier**: the cheapest tier you'd actually trust for the task, from the
       data's four-value vocabulary (`cheap|mid|strong|frontier`) via
       `python3 {{POLYTROPOS_ROOT}}/bin/copilot_pricing.py models --json`. Use the
       `route` agent's framing if unsure.
     - **Step 2 — dispatch**: `copilot -p "<self-contained brief>" --model <model-id>` — the
       dispatched run sees nothing of this session, so the brief must carry the task, the
       needed context, and the verify command with an instruction to run it and report
       output.
     - **Step 3 — verify independently**: run the verify command YOURSELF; the dispatched
       run's success claim is not evidence. Pass → done; note it never needed the frontier
       tier. Fail → retry ONCE on the same model, handing it the exact failure output.
       Fail again → escalate.
     - **Step 4 — climb the ladder**: exactly the rule `bin/copilot_execute.py` implements
       for kits — tiers strictly ABOVE the current model's tier in
       `cheap → mid → strong → frontier` order, FIRST model in pricing-file order per tier,
       empty tiers skipped; derive the ladder from the data at run time, never from memory.
       Each hop carries evidence only: what was tried and the exact check output — the
       diagnosis is what keeps the expensive hop short. The frontier rung is last: say what
       makes the task frontier-worthy when you reach it; if the frontier model declines the
       request (vendor safety classifiers — see the model's `notes`), fall back to a
       strong-tier hop and say why. If the top rung still fails, stop and report honestly —
       what each tier tried, the final check output, and whether the task looks
       mis-specified.
     - **Cost posture**: AIC are money — when asked, price attempts with
       `copilot_pricing.py est <PROFILE> <MODEL_ID>`; always report which rung passed so the
       ladder's savings are visible.
     - **Kit tasks**: for a task that lives in a `tasks/kits/<slug>/` kit, prefer
       `python3 {{POLYTROPOS_ROOT}}/bin/copilot_execute.py run --kit <dir> --task <id>`
       — the driver implements this same ladder with statuses and `--max-escalations`; this
       agent is for one-off tasks outside a kit. For multi-task work, prefer the `architect`
       agent over calling this in a loop.
     - Placeholder paragraph (as T1).
3. **`tests/test_copilot_bundle.py`** — additive: `"escalate": "mid",` in
   `WORKFLOW_AGENT_TIERS`; two methods appended to `PortedAgentContractTests`:
   `test_escalate_is_verify_gated` (asserts `"verify"` in `self._text("escalate")`) and
   `test_escalate_points_at_execute_driver` (asserts `"bin/copilot_execute.py"` in it).

**Acceptance.** Manifest + file + tests together; live mid-tier frontmatter pin; the body
mirrors the strictly-above/first-in-file-order/skip-empty ladder rule and contains no model-id
literal, no invented CLI flags (only surfaces present in route.agent.md /
`copilot_execute.py`); verify green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_bundle.py' -v
```

### T8 — Codex `escalate` prompt (bundle + roster test, atomic)
- status: done
- model: sonnet
- depends: T6
- independent: no (Codex lane)

**Brief.** Port `escalate` for Codex, mirroring T7's ladder with Codex surfaces. Read first:
`skills/escalate/SKILL.md`, the module docstring (lines 1–60) and `resolve_tier`/
`resolve_model` of `bin/codex_execute.py` (the skip-up rule + ladder), `codex/prompts/route.md`
(dispatch surfaces + billing honesty), and `bin/codex_pricing.py` flags.

1. **`codex/prompts/escalate.md`** — new file, description-only frontmatter. Body
   (~50–80 lines): Steps 0–4 as in T7, with these Codex adaptations:
   - Dispatch: `codex exec "<self-contained brief>" --model <model-id>` (add `--full-auto`
     when it must edit files).
   - Tier words are first-class: a tier word resolves to the FIRST model in pricing-file
     order carrying it, and an unpopulated tier resolves UPWARD (`strong` → the frontier
     model on today's roster, per the data's `tier_note`) — the same rule
     `bin/codex_execute.py` implements. Derive everything from
     `python3 {{POLYTROPOS_ROOT}}/bin/codex_pricing.py models --json` at run time.
   - The extra lever the frontier hop has here: reasoning effort — prefer
     `-c model_reasoning_effort=medium` for the first frontier attempt and step up
     (`high`/`max`) only if the check still fails; don't start at `max`.
   - Billing honesty (route.md's rule): under a ChatGPT plan the hop costs usage-limit burn
     and any dollar figure is a labeled API-equivalent proxy, never a bill; real dollars only
     under `OPENAI_API_KEY`. Report which rung passed.
   - Kit tasks → `python3 {{POLYTROPOS_ROOT}}/bin/codex_execute.py run --kit <dir>
     --task <id> [--effort E]` (the driver implements this same ladder); multi-task work →
     the `architect` prompt.
   - Placeholder paragraph. No real model id, no "fable" (any case).
2. **`tests/test_codex_bundle.py`** — additive: extend to
   `PORTED_PROMPT_STEMS = ("usage", "journal", "frontier-check", "escalate")`; append one
   method to `PortedPromptContractTests`: `test_escalate_dispatches_and_points_at_driver`
   (asserts `"codex exec"` and `"bin/codex_execute.py"` in the escalate text).

**Acceptance.** File + roster land together; the final `EXPECTED_PROMPT_STEMS` set has nine
stems; all sweeping cases green over the four ported prompts; only pinned seam edits in the
test file.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_codex_bundle.py' -v
```

---

## Phase 3 — Closeout

### T9 — Instruction surfaces: one pinned sentence per harness (manifest-first)
- status: done
- model: haiku
- depends: T7, T8
- independent: no

**Brief.** Make the ported roster discoverable from each harness's instructions surface.
Three append-only edits with PINNED content — reproduce each verbatim; if an anchor below is
absent, STOP and report.

1. **`copilot/aesop.yaml`** — inside `primitives.instructions.blocks[0].content: |`, after
   the existing line beginning `Before any expensive run, use the \`route\` agent`, append
   this line at the SAME indentation as the block's other content lines:

   `Beyond routing, four ported agents complete the optimizer surface: the usage agent (historical Copilot spend from local logs, read-only), the journal agent (the daily work journal), the frontier-check agent (is a task worth the frontier tier), and the escalate agent (verify-gated dispatch that climbs the tiers only on failure).`

2. **`copilot/.github/copilot-instructions.md`** — append the SAME sentence verbatim as a
   new final paragraph (blank line before it).
3. **`codex/AGENTS.md`** — append this paragraph verbatim as a new final paragraph (blank
   line before it):

   `Beyond /route, four ported prompts complete the optimizer surface: /usage (historical Codex activity from local logs, read-only — priced only when the logs carry tokens, and then only as a labeled API-equivalent proxy), /journal (the daily work journal), /frontier-check (is a task worth the frontier tier), and /escalate (verify-gated dispatch that climbs the tiers only on failure).`

The two doctrine sentences (one per harness, byte-verbatim test-enforced) must be untouched —
these edits are pure appends and change no existing line.

**Acceptance.** All three surfaces carry their pinned text exactly once; every pre-existing
line in all three files byte-identical; both bundle test files green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_co*_bundle.py' -v
```

### T10 — Full-suite + frozen-surface audit
- status: done
- model: haiku
- depends: T9
- independent: no

**Brief.** Final gate. Run and report, in order:

1. `python3 -m unittest discover -s tests -v` — must be fully green.
2. `git diff --quiet -- bin data skills .claude-plugin docs README.md && echo FROZEN-CLEAN` —
   must print `FROZEN-CLEAN`.
3. `git status --porcelain` — the changed/untracked set must be EXACTLY: the two edited test
   files, `copilot/aesop.yaml`, `copilot/.github/copilot-instructions.md`, `codex/AGENTS.md`,
   the eight new bundle files, and this kit's own files
   (`.claude/kits/harness-parity/`, `.claude/agents/harness-parity-*.md`, the CLAUDE.md
   fence). Flag ANYTHING else, including any diff to the ten pre-existing bundle files.
4. Leak sweeps (each must produce NO matches):
   - `grep -rn "/Users/\|/home/" copilot/.github codex`
   - `grep -rn "CLAUDE_PLUGIN_ROOT" copilot/.github codex`
   - `grep -rni "fable" codex`
   - `python3 -c "import json,pathlib; ids=list(json.load(open('data/pricing.copilot.json'))['models']); bodies={p: p.read_text().split('---',2)[2] for p in pathlib.Path('copilot/.github/agents').glob('*.agent.md')}; hits=[f'{p}: {i}' for p,b in bodies.items() for i in ids if i in b]; print('\n'.join(hits) if hits else 'COPILOT-BODIES-CLEAN')"
     — must print `COPILOT-BODIES-CLEAN` (frontmatter pins are excluded by the split; bodies
     must carry no pricing-key model id).
5. Confirm the Copilot manifest agents block and the `.agent.md` stems both list nine names,
   and `codex/prompts/` holds nine `.md` files.

Report each command's actual output. Any failure, unexplained file, or leak-sweep hit means
the task is `blocked` with the evidence — do not fix things yourself.

**Acceptance.** All five checks pass with outputs shown verbatim.

**Verify.**
```bash
python3 -m unittest discover -s tests -v
```
