# copilot-measure-parity — tasks

Repo root: `/path/to/polytropos`. Run all verify commands
from the repo root. Read `PLAN.md` and `GUARDRAILS.md` in this directory before any task.

Dispatch preamble: **T1 → T2 and T3 → T4 are warm-cluster candidates** — each pair is strictly
serial (the agent mirrors its skill's operative content), shares the same `model` pin, and may
be served by one continued implementer. The two pairs are independent of each other. T5 and T6
are strictly serial after both pairs.

## Phase 1 — Bundle surfaces

### T1 — context-weight Copilot skill + manifest line

- status: done
- model: sonnet
- depends: (none)
- independent: yes

**Brief.** Create `copilot/.github/skills/context-weight/SKILL.md` (target 40–70 lines) AND add
`    - context-weight` to the `skills:` block of `copilot/aesop.yaml` in this same task
(PLAN.md D6 — set-equality tests fail if either lands alone).

Frontmatter: `name: context-weight` and a one-line `description:` with real triggers (context
is huge, cache reads high, "should I compact", what filled the window) — no `model:` line, and
no unquoted `: ` inside the description value (YAML-safety sweep). Body, in the D2
condensed-twin voice (study `copilot/.github/skills/usage/SKILL.md` for register and for the
two closing paragraphs, which must be copied with only the name changed):

1. **What this skill cannot do** — it cannot remove anything from a context window; only the
   harness can. Two-to-three sentences, ported from the Claude-side skill's opening stance.
2. **Run the engine** — the real argparse surface only, each command using the
   `{{POLYTROPOS_ROOT}}` placeholder:
   `python3 {{POLYTROPOS_ROOT}}/bin/context_weight.py session --harness copilot`,
   `... overview --harness copilot`, `... audit` (sizes resident config surfaces — including
   `copilot-instructions.md` — against a token budget), `... demo` (synthetic, no real data).
   Note all take `--json`. Confirm each against `python3 bin/context_weight.py --help` before
   writing it down; do not invent flags.
3. **Copilot's honest fidelity** — the load-bearing section: Copilot's logs record no per-turn
   input/cache split, so there is **no growth curve** on this harness; `session` reports a
   `session-average` weight instead, and the skill must name that as the honest substitute,
   not a curve. `watch` is Claude-only — `watch copilot` prints an honest refusal rather than
   a fabricated number — so there is no live threshold here: apply the levers on a schedule,
   not on a threshold.
4. **The three levers in priority order** — prevent (delegate/cap before mass enters the
   window; free and lossless), prune (compaction; cheap but lossy), measure (session/overview/
   audit tell you which of the first two is the move). Include the checkpoint habit: write
   decisions and open questions to a notes file BEFORE compacting.
5. **Honesty rules** — estimated figures are labeled `est.` and are ranks/magnitudes, never
   priced; each harness is reported at its own fidelity, never Claude's.
6. The two pinned closing paragraphs: **Same-named agent** (mentioning
   `copilot --agent context-weight -p "<task>"` and the `/agent` picker) and **Installed?**
   (literal-placeholder check pointing at
   `python3 bin/harness_select.py install --harness copilot` and `/skills reload`).

No pricing-key model id anywhere in the file (sweep-enforced). No prefs paragraphs (PLAN.md
D4). ALSO add `"context-weight"` to the `EXPECTED_SKILLS` set in
`tests/test_copilot_docs_content.py` (PLAN.md D8 — the docs-coverage tripwire is updated in
lockstep; keep the set's existing formatting and alphabetical grouping, and change nothing
else in that file). ALSO author a `## context-weight` section in `copilot-docs/SKILLS.md`
(PLAN.md D9), placed alphabetically between `## architect` and `## effort`, matching the
existing sections' voice and carrying exactly these bolded subsections in this order:
**When to use it.** / **How to request it.** / **What it does.** / **Safety and cost notes.**
/ **Same-named agent.** Study the `## usage` section as the closest sibling (a read-only
reporter). Content must be true to the skill: measurement-only, session-average fidelity with
no growth curve on this harness, `watch` is Claude-only, reads local logs read-only, spends
nothing. Do NOT touch anything between the `<!-- BEGIN GENERATED: skills-inventory -->` and
`<!-- END GENERATED: skills-inventory -->` markers. After writing all four edits, run
`python3 bin/copilot_docs.py build` (regenerates `skills.html` from your authored source),
then the full suite.

**Acceptance.** File exists with compliant frontmatter; the four engine subcommands appear
with the placeholder and `--harness copilot` on session/overview; the fidelity section names
`session-average`, the missing growth curve, and the `watch` refusal; both closing paragraphs
present; `copilot/aesop.yaml` `skills:` block contains `context-weight`; docs rebuilt; full
suite green.

**Verify.**
```bash
cd /path/to/polytropos && test -f copilot/.github/skills/context-weight/SKILL.md && grep -c 'POLYTROPOS_ROOT}}/bin/context_weight.py' copilot/.github/skills/context-weight/SKILL.md && grep -q 'session-average' copilot/.github/skills/context-weight/SKILL.md && grep -q 'copilot --agent context-weight' copilot/.github/skills/context-weight/SKILL.md && grep -q 'install --harness copilot' copilot/.github/skills/context-weight/SKILL.md && grep -q 'context-weight' copilot/aesop.yaml && python3 bin/copilot_docs.py build >/dev/null && python3 -m unittest discover -s tests 2>&1 | tail -2
```

### T2 — context-weight Copilot agent + manifest line

- status: done
- model: sonnet
- depends: T1
- independent: no

**Brief.** Create `copilot/.github/agents/context-weight.agent.md` AND add
`    - context-weight` to the `agents:` block of `copilot/aesop.yaml` in this same task.

Frontmatter: `name: context-weight`, a one-line `description:` (may differ from the skill's
but must carry the same triggers), and `model: claude-haiku-4.5` — the read-only-reporter pin
per PLAN.md D5 (`usage`/`verifier` precedent; must remain a live `data/pricing.copilot.json`
key, which `ModelPinLiveTests` enforces). Body: the long-form persona twin of T1's skill —
same engine commands with the `{{POLYTROPOS_ROOT}}` placeholder, same fidelity honesty
(session-average, no growth curve, watch refusal), same three-levers guidance, written as a
persona ("You report…") the way `usage.agent.md` is. Include a short presentation section:
lead with the session-average weight and the ranked practices, keep `est.` labels on
estimates, and point at the `route` agent for "what should I use next" questions. Study
`usage.agent.md` for structure; do not copy the skill verbatim (agents keep the long form).

ALSO add `"context-weight"` to the `EXPECTED_AGENTS` set in
`tests/test_copilot_docs_content.py` (PLAN.md D8; change nothing else in that file), and
author a `## context-weight` section in `copilot-docs/AGENTS.md` (PLAN.md D9) in alphabetical
position, matching the existing sections' voice with exactly these bolded subsections:
**When to use it.** / **How to invoke it.** / **What it does.** / **Same-named skill.**
Study the `## usage` agent section as the closest sibling; state that the role is configured
for a cheap model because the work is mechanical reporting rather than judgment. Never edit
between the `agents-inventory` generated markers.
After the edits, `python3 bin/copilot_docs.py build`, then the full suite.

**Acceptance.** Agent file exists; frontmatter has the haiku pin and YAML-safe values; body
carries the engine path with placeholder and the fidelity honesty; `agents:` block lists
`context-weight`; `EXPECTED_AGENTS` updated; docs rebuilt; full suite green.

**Verify.**
```bash
cd /path/to/polytropos && test -f copilot/.github/agents/context-weight.agent.md && grep -q 'model: claude-haiku-4.5' copilot/.github/agents/context-weight.agent.md && grep -q 'POLYTROPOS_ROOT}}/bin/context_weight.py' copilot/.github/agents/context-weight.agent.md && grep -q 'session-average' copilot/.github/agents/context-weight.agent.md && python3 bin/copilot_docs.py build >/dev/null && python3 -m unittest discover -s tests 2>&1 | tail -2
```

### T3 — bench-routing Copilot skill + manifest line

- status: done
- model: sonnet
- depends: (none)
- independent: yes

**Brief.** Create `copilot/.github/skills/bench-routing/SKILL.md` (target 40–70 lines) AND add
`    - bench-routing` to the `skills:` block of `copilot/aesop.yaml` in this same task.

Frontmatter: `name: bench-routing`, one-line `description:` (triggers: should a new/higher
model replace what a role runs on; benchmark-informed routing recommendation) — no `model:`
line, YAML-safe. Body in the D2 voice:

1. **Run the engine** — placeholder commands, confirmed against
   `python3 bin/bench_routing.py --help` and each subcommand's `--help`:
   `python3 {{POLYTROPOS_ROOT}}/bin/bench_routing.py rank --top 10`,
   `... roles --harness copilot`, `... demo`. The dataset is
   `{{POLYTROPOS_ROOT}}/data/benchmarks.aa.json` — a screenshot-transcribed snapshot of
   the Artificial Analysis Intelligence Index (name its `cached_date`/provenance honesty:
   flag as re-verify-worthy if stale). Never edit that file from this skill.
2. **What `roles --harness copilot` means** — availability is derived at run time from
   `data/pricing.copilot.json`; a benchmark entry matching no dispatchable Copilot model is
   reported UNAVAILABLE, never silently dropped. Role floors are this repo's editorial
   judgement, overridable with repeatable `--floor "role=N"`.
3. **The `compare` honesty** — the load-bearing section: `compare` joins the benchmark prior
   against this repo's measured kit ledger, which is CLAUDE-harness evidence (implementer
   role only). From the Copilot side there is no measured per-role outcome data, so the
   benchmark recommendation stands unchallenged here — say that plainly instead of borrowing
   Claude-side evidence, and point users who want the measured check at the Claude harness.
4. **Presentation rules** — `usd_per_task` is a ranking ratio, never a bill and never added to
   real spend figures (`usage` owns those); the Intelligence Index is a general-capability
   composite, not a coding or agentic board — state that before recommending a routing change
   for an agentic role; tier words only, never a specific model id (the roster changes; the
   tier does not).
5. The two pinned closing paragraphs: **Same-named agent** (mentioning
   `copilot --agent bench-routing -p "<task>"`) and **Installed?** (same wording as T1's).

No pricing-key model id anywhere in the file. No prefs paragraphs (PLAN.md D4 — the engine
does not consume prefs; do not teach a mechanism that does not exist). ALSO add
`"bench-routing"` to the `EXPECTED_SKILLS` set in `tests/test_copilot_docs_content.py`
(PLAN.md D8; change nothing else in that file), and author a `## bench-routing` section in
`copilot-docs/SKILLS.md` (PLAN.md D9) in alphabetical position (between `## architect` and
`## context-weight`), matching the existing voice with exactly these bolded subsections:
**When to use it.** / **How to request it.** / **What it does.** / **Safety and cost notes.**
/ **Same-named agent.** Content must be true to the skill: a benchmark prior ranked from a
screenshot-transcribed snapshot, availability derived from the Copilot pricing file,
`compare`'s measured-outcome join is Claude-harness evidence so the benchmark stands
unchallenged here, and `usd_per_task` is a ranking ratio never a bill. Never edit between the
`skills-inventory` generated markers. After all four edits,
`python3 bin/copilot_docs.py build`, then the full suite.

**Acceptance.** File exists with compliant frontmatter; `rank`, `roles --harness copilot`, and
`demo` appear with the placeholder; UNAVAILABLE semantics, compare-is-Claude-evidence honesty,
never-a-bill and index-scope caveats present; both closing paragraphs present;
`copilot/aesop.yaml` `skills:` lists `bench-routing`; docs rebuilt; full suite green.

**Verify.**
```bash
cd /path/to/polytropos && test -f copilot/.github/skills/bench-routing/SKILL.md && grep -q 'POLYTROPOS_ROOT}}/bin/bench_routing.py' copilot/.github/skills/bench-routing/SKILL.md && grep -q 'roles --harness copilot' copilot/.github/skills/bench-routing/SKILL.md && grep -q 'UNAVAILABLE' copilot/.github/skills/bench-routing/SKILL.md && grep -q 'never a bill' copilot/.github/skills/bench-routing/SKILL.md && grep -q 'copilot --agent bench-routing' copilot/.github/skills/bench-routing/SKILL.md && python3 bin/copilot_docs.py build >/dev/null && python3 -m unittest discover -s tests 2>&1 | tail -2
```

### T4 — bench-routing Copilot agent + manifest line

- status: done
- model: sonnet
- depends: T3
- independent: no

**Brief.** Create `copilot/.github/agents/bench-routing.agent.md` AND add
`    - bench-routing` to the `agents:` block of `copilot/aesop.yaml` in this same task.

Frontmatter: `name: bench-routing`, one-line YAML-safe `description:`, and
`model: claude-sonnet-5` — the decision-aid pin per PLAN.md D5 (`route`/`frontier-check`
precedent; live pricing key). Body: long-form persona twin of T3 — same engine commands with
placeholder, same UNAVAILABLE / compare-is-Claude-evidence / never-a-bill / index-scope
honesty, written as a persona in the register of `route.agent.md`. Presentation guidance:
lead with the `roles` pick for the asked role, name the floor it cleared, keep tier words
(the agent's OWN frontmatter pin is the only model id in the file).

ALSO add `"bench-routing"` to the `EXPECTED_AGENTS` set in
`tests/test_copilot_docs_content.py` (PLAN.md D8; change nothing else in that file), and
author a `## bench-routing` section in `copilot-docs/AGENTS.md` (PLAN.md D9) in alphabetical
position, matching the existing voice with exactly these bolded subsections:
**When to use it.** / **How to invoke it.** / **What it does.** / **Same-named skill.**
Never edit between the `agents-inventory` generated markers.
After the edits, `python3 bin/copilot_docs.py build`, then the full suite.

**Acceptance.** Agent file exists with the sonnet pin; engine path with placeholder present;
compare honesty and never-a-bill wording present; `agents:` block lists `bench-routing`;
`EXPECTED_AGENTS` updated; docs rebuilt; full suite green.

**Verify.**
```bash
cd /path/to/polytropos && test -f copilot/.github/agents/bench-routing.agent.md && grep -q 'model: claude-sonnet-5' copilot/.github/agents/bench-routing.agent.md && grep -q 'POLYTROPOS_ROOT}}/bin/bench_routing.py' copilot/.github/agents/bench-routing.agent.md && grep -q 'never a bill' copilot/.github/agents/bench-routing.agent.md && python3 bin/copilot_docs.py build >/dev/null && python3 -m unittest discover -s tests 2>&1 | tail -2
```

## Phase 2 — Contracts and closeout

### T5 — Contract test classes for both new capabilities

- status: done
- model: sonnet
- depends: T1, T2, T3, T4
- independent: no

**Brief.** Extend `tests/test_copilot_bundle.py` (no new test file — PLAN.md D7) with two
classes mirroring the existing per-skill pattern (`UsageSkillContractTests` is the closest
shape). Insert them after `ExecuteSkillContractTests`, keeping the file's class ordering
style. Stdlib unittest only; text reads only.

`ContextWeightSkillContractTests` asserts, against
`copilot/.github/skills/context-weight/SKILL.md`:
engine path `bin/context_weight.py` + `{{POLYTROPOS_ROOT}}` present;
`--harness copilot` present; `session-average` present; the honesty pair present (`watch` AND
a refusal/Claude-only wording — assert on `watch` plus the substring `refus`); the agent
pointer `copilot --agent context-weight` present; and a negative: the string `growth curve`
may appear only in a sentence that denies it — implement as: the file must contain
`no growth curve`.

`BenchRoutingSkillContractTests` asserts, against
`copilot/.github/skills/bench-routing/SKILL.md`:
engine path `bin/bench_routing.py` + placeholder; `roles --harness copilot`; `UNAVAILABLE`;
`never a bill`; `Intelligence Index`; the compare honesty (assert substring
`stands unchallenged`); agent pointer `copilot --agent bench-routing`.

Each class also carries one agent-side test asserting the same-named agent file exists and
contains the engine path with the placeholder (the pin values are already covered by
`ModelPinLiveTests`; do not duplicate tier→id assertions).

If any anchor string is missing from a T1–T4 file, the brief for THAT file is authoritative —
fix the bundle file to carry its pinned anchor, do not weaken the test. Full suite green.

**Acceptance.** Both classes exist and pass; anchors match the strings pinned in T1–T4; no
new test file; full suite green.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest tests.test_copilot_bundle -v 2>&1 | grep -cE 'ContextWeightSkillContract|BenchRoutingSkillContract' && python3 -m unittest tests.test_copilot_bundle 2>&1 | tail -2 && python3 -m unittest discover -s tests 2>&1 | tail -2
```

### T6 — Closeout sweep: install surface, docs freshness, separation

- status: done
- model: haiku
- depends: T5
- independent: no

**Brief.** Mechanical final checks; change nothing unless a check fails, in which case stop
and report (do not improvise fixes). (1) Confirm the installer picks up all four new files
without writing anything:
`python3 bin/harness_select.py install --harness copilot --dry-run` output must list
destination paths for `context-weight.agent.md`, `bench-routing.agent.md`, and both new
`SKILL.md` files. (2) Confirm docs freshness: `python3 bin/copilot_docs.py check` reports no
drift. (3) Harness separation greps over the four new files: no `fable` (case-insensitive),
no `cost-report`, no `CLAUDE_PLUGIN_ROOT`. (4) Full suite green.

**Acceptance.** All four checks pass exactly as specified; no file modified by this task.

**Verify.**
```bash
cd /path/to/polytropos && python3 bin/harness_select.py install --harness copilot --dry-run | grep -c 'context-weight\|bench-routing' && python3 bin/copilot_docs.py check && ! grep -riE 'fable|cost-report|CLAUDE_PLUGIN_ROOT' copilot/.github/skills/context-weight/SKILL.md copilot/.github/skills/bench-routing/SKILL.md copilot/.github/agents/context-weight.agent.md copilot/.github/agents/bench-routing.agent.md && python3 -m unittest discover -s tests 2>&1 | tail -2
```

### T7 — Phase 1 review remediation (added mid-run, 2026-07-25)

- status: done
- model: sonnet
- depends: T6
- independent: no

**Brief.** Fix the seven confirmed findings from the Phase 1 review (see NOTES.md "Phase 1
review"). Each fix is narrow; make no other change.

1. **(F1, blocking) `copilot/.github/agents/bench-routing.agent.md`** — its presentation
   section instructs "implementer gets the measured-outcome check from the Claude-harness
   ledger; every other role gets the 'stands unchallenged' caveat". That carve-out contradicts
   PLAN.md D3, the file's own earlier section, and its twin skill. From the Copilot side
   EVERY role gets the caveat: the ledger's implementer evidence measures Claude tiers, while
   `roles --harness copilot` picks an entirely different vendor's model, so applying one to
   the other is borrowed evidence. Rewrite that step so no role gets a Copilot-side
   measured-evidence claim; keep the existing correct section intact.
2. **(F2, blocking) BOTH context-weight files** —
   `copilot/.github/skills/context-weight/SKILL.md` and
   `copilot/.github/agents/context-weight.agent.md` both claim estimated figures are "never
   priced". Run `python3 bin/context_weight.py session --harness copilot` and read its output:
   it prints a `context carry cost:` line in USD and AIC carrying the mandatory label
   `API-equivalent dollars — an estimate, not a bill.` Correct the honesty rule in both files:
   the `est.`/never-priced claim holds for the attribution and audit figures, but the
   session/overview cards DO carry an API-equivalent carry cost, and a presenter must relay it
   WITH its "estimate, not a bill" label — never stripped, and never added to real spend
   (`usage` owns actual spend). Model the wording on the bench-routing pair's existing
   "never a bill, and never added to real spend figures" sentence. Keep the strings
   `session-average` and `no growth curve` intact — T5's tests pin them.
3. **(F4) BOTH bench-routing files** — both say an undispatchable entry "is reported
   UNAVAILABLE". Verify: `python3 bin/bench_routing.py roles --harness copilot | grep -c
   UNAVAILABLE` returns 0 — the text card prints only `N/M benchmark entries dispatchable`,
   and the per-entry labels live in the `--json` card. Reword both so the claim is true of
   what a user actually sees: the entry is counted out of the dispatchable total in the text
   output and named UNAVAILABLE in `--json`, never silently dropped. The literal string
   `UNAVAILABLE` must REMAIN in the skill (T5 pins it) — keep it while making the sentence
   accurate, and mention `--json` as where the labels appear.
4. **(F5) `copilot/.github/skills/bench-routing/SKILL.md`** — add the fact its twin agent
   already carries: `compare` has no `--harness` flag; never imply one exists.
5. **(F6) `copilot-docs/AGENTS.md`** — the authored "Skills versus agents at a glance" table
   (around line 230, well past the `END GENERATED: agents-inventory` marker, so authored
   source) enumerates every other name but omits `bench-routing` and `context-weight`. Add
   both rows in alphabetical position, matching the table's existing column semantics exactly.
6. **(F8a) `copilot/.github/skills/bench-routing/SKILL.md`** — it opens straight into
   `## Run the engine`; every other bundle skill except `lessons-loop` (and the new
   context-weight skill) opens with a "You <verb>…" stance sentence. Add one, matching the
   register of `copilot/.github/skills/route/SKILL.md`.

NOT in scope (deliberate): F7, the stale roster prose in `copilot/.github/copilot-instructions.md`
and its `aesop.yaml` mirror — GUARDRAILS freezes that file and this kit never sanctioned it;
it is recorded as a follow-up instead. F8b/F8c (the `# H1` titles and the `## Same-named
skill` agent sections) are ACCEPTED as-is: both new files are internally consistent and the
pattern reads well; churning ten existing agents to match is out of scope.

After the edits run `python3 bin/copilot_docs.py build`, then the full suite. Re-read the two
engines' actual output before writing any honesty sentence — if a sentence you are about to
write conflicts with what the engine prints, the ENGINE wins.

**Acceptance.** All six fixes applied; the F1 carve-out gone; both context-weight files
acknowledge the carry-cost line with its label; both bench-routing files' UNAVAILABLE claim
matches text-vs-json reality while keeping the literal string; compare's no-`--harness` fact
in the skill; both rows in the at-a-glance table; a stance sentence opening the bench-routing
skill; T5's pinned anchors (`session-average`, `no growth curve`, `UNAVAILABLE`, `never a
bill`, `Intelligence Index`, `stands unchallenged`) all still present; docs rebuilt; full
suite green.

**Verify.**
```bash
cd /path/to/polytropos && ! grep -q 'implementer gets the measured-outcome check' copilot/.github/agents/bench-routing.agent.md && grep -q 'not a bill' copilot/.github/skills/context-weight/SKILL.md && grep -q 'not a bill' copilot/.github/agents/context-weight.agent.md && grep -q 'session-average' copilot/.github/skills/context-weight/SKILL.md && grep -q 'no growth curve' copilot/.github/skills/context-weight/SKILL.md && grep -q 'json' copilot/.github/skills/bench-routing/SKILL.md && grep -q 'UNAVAILABLE' copilot/.github/skills/bench-routing/SKILL.md && grep -q 'harness' copilot/.github/skills/bench-routing/SKILL.md && grep -c 'bench-routing\|context-weight' copilot-docs/AGENTS.md && python3 bin/copilot_docs.py build >/dev/null && python3 -m unittest discover -s tests 2>&1 | tail -2
```

### T8 — Close the UNAVAILABLE tail (added mid-run, 2026-07-25)

- status: done
- model: sonnet
- depends: T7
- independent: no

**Brief.** The final review confirmed F4 was fixed in the two bundle files but not in the
authored docs sections, and that the fix left a shoehorned clause behind because T5's test
pins a string the engine never emits. Close both, in this order.

1. **Repin the test to reality.** In `tests/test_copilot_bundle.py`, the assertion
   `self.assertIn("UNAVAILABLE", self._text())` (in
   `BenchRoutingSkillContractTests`, around line 653) pins an uppercase literal that appears
   in NO engine output — confirm for yourself: `python3 bin/bench_routing.py roles --harness
   copilot --json | grep -c UNAVAILABLE` returns 0, and the JSON key is the lowercase
   `unavailable`. Repin the assertion to the lowercase `unavailable` (the real key) and
   rename the test method if its name references the uppercase form. Keep the assertion's
   shape and the class's existing style; change nothing else in the file.
2. **Drop the shoehorn.** In BOTH `copilot/.github/skills/bench-routing/SKILL.md` and
   `copilot/.github/agents/bench-routing.agent.md`, the clause claiming `--json` is "where the
   per-entry `UNAVAILABLE` labels actually live" is false — the JSON emits a key named
   `unavailable` holding a bare list of display names, with no per-entry label field. Reword
   so both files describe exactly that: the text card counts the entry out of the
   `N/M benchmark entries dispatchable` total, and `--json` lists it by name under
   `unavailable`. Keep the preceding accurate clause and the never-silently-dropped point.
3. **Fix the published docs.** `copilot-docs/SKILLS.md` (`## bench-routing`, ~line 86) and
   `copilot-docs/AGENTS.md` (`## bench-routing`, ~line 80) both still say an entry "reported
   UNAVAILABLE" — the exact wording confirmed untrue of what a user sees. Reword both to match
   the corrected bundle wording, preserving each section's voice and its required bolded
   subsections. These are authored source (PLAN.md D9); never edit between BEGIN/END GENERATED
   markers.

Then `python3 bin/copilot_docs.py build` and the full suite. Every remaining T5 anchor
(`session-average`, `no growth curve`, `never a bill`, `Intelligence Index`,
`stands unchallenged`) must survive.

**Acceptance.** The test pins the lowercase `unavailable`; no file claims `--json` carries
per-entry UNAVAILABLE labels; neither published doc section claims an entry is "reported
UNAVAILABLE"; every other T5 anchor intact; docs rebuilt; full suite green.

**Verify.**
```bash
grep -q '"unavailable"' tests/test_copilot_bundle.py && ! grep -q 'UNAVAILABLE' copilot-docs/SKILLS.md && ! grep -q 'UNAVAILABLE' copilot-docs/AGENTS.md && grep -q 'stands unchallenged' copilot/.github/skills/bench-routing/SKILL.md && grep -q 'never a bill' copilot/.github/skills/bench-routing/SKILL.md && grep -q 'Intelligence Index' copilot/.github/skills/bench-routing/SKILL.md && grep -q 'session-average' copilot/.github/skills/context-weight/SKILL.md && grep -q 'no growth curve' copilot/.github/skills/context-weight/SKILL.md && python3 bin/copilot_docs.py build >/dev/null && python3 -m unittest discover -s tests 2>&1 | tail -2
```

### T9 — Correct the resident roster prose (added mid-run, 2026-07-25)

- status: done
- model: sonnet
- depends: T8
- independent: no

**Brief.** `copilot/.github/copilot-instructions.md` and its mirrored `instructions.blocks`
prose in `copilot/aesop.yaml` still describe the pre-parity roster, so they are now false by
omission about the two capabilities this kit shipped. Per PLAN.md D10 those two sentences (and
only those) are unfrozen. Fix both files identically.

Two sentences, each appearing in BOTH files (keep them mirrored byte-for-byte with each other):

1. **"Beyond routing, four ported agents complete the optimizer surface: …"** — it names usage,
   journal, frontier-check, escalate. Two more now exist: `context-weight` and `bench-routing`.
   Update the count word and add both, each with a SHORT parenthetical in the register of the
   existing ones (they run ~6–10 words each): context-weight measures what filled the context
   window; bench-routing checks a benchmark-informed routing recommendation against measured
   outcomes. Verify the count word matches the number you actually list.
2. **"Every optimizer capability is also invocable as a skill — type /route, /usage, /journal,
   /frontier-check, /escalate, /effort, /architect, or /execute …"** — add `/bench-routing`
   and `/context-weight` to that list, keeping its existing ordering convention and the
   sentence's remaining clauses intact.

HARD CONSTRAINTS:
- **This is a resident surface**, resubmitted on every Copilot call. Add names and short
  parentheticals, never descriptions or a new paragraph. The `context-weight` skill this kit
  just shipped teaches keeping resident surfaces lean and proportionate — do not violate it in
  the same kit that ships it. Report the before/after character count of each file.
- **Do not touch the doctrine sentence** ("Derive every number from `data/pricing.copilot.json`
  at run time …"). `DoctrineSentenceSyncTests` requires it verbatim in both files.
- Change nothing else in either file. No new bundle files, no docs edits beyond the builder.
- Never invoke the real `copilot` CLI; never touch the real `~/.copilot`.

Then `python3 bin/copilot_docs.py build` and the full suite.

**Acceptance.** Both sentences corrected in BOTH files and identical between them; the count
word matches the list; `/bench-routing` and `/context-weight` in the skills list; doctrine
sentence untouched; net growth modest (report the counts); docs rebuilt; full suite green.

**Verify.**
```bash
grep -q '/context-weight' copilot/.github/copilot-instructions.md && grep -q '/bench-routing' copilot/.github/copilot-instructions.md && grep -q '/context-weight' copilot/aesop.yaml && grep -q '/bench-routing' copilot/aesop.yaml && grep -c 'context-weight' copilot/.github/copilot-instructions.md && ! grep -q 'four ported agents' copilot/.github/copilot-instructions.md && ! grep -q 'four ported agents' copilot/aesop.yaml && python3 -m unittest tests.test_copilot_bundle 2>&1 | tail -2 && python3 bin/copilot_docs.py build >/dev/null && python3 -m unittest discover -s tests 2>&1 | tail -2
```
