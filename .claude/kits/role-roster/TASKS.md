# role-roster — tasks

Dispatch preamble: T1 → T2 are strictly serial (same primary file,
`bin/routing_scorecard.py`, both sonnet) — a warm-cluster candidate. T3 is independent of
T1/T2 (different files). T4 and T5 are serial with each other ONLY in the sense that both
touch the shared contract — run T4 then T5, each a FRESH opus dispatch (no warm cluster
across contract edits; fresh eyes are the point). T6 depends on T2 (quotes the real
--roles surface); T7 last. Statuses: pending | in-progress | done | blocked.

## Phase 1 — Ledger + scorecard (the measurement backbone)

### T1 — Extend the agent-line grammar: seven role tokens + marginal=
- id: T1
- title: AGENT_ROLES extension (documented supersession) + marginal= field
- status: done
- model: sonnet
- independent: yes

Edit only `bin/routing_scorecard.py` and `tests/test_role_ledger.py` (plus, ONLY if the
tripwire below fires, the single test file holding an event-key lock).

1. `AGENT_ROLES` (currently line ~183, `("implementer", "verifier", "escalation")`) grows
   to exactly:
   `("implementer", "verifier", "escalation", "scout", "test-author", "second-verifier",
   "red-team", "security-auditor", "docs-editor", "synthesizer")`
   Keep the guard semantics identical (unknown role → whole line dropped with the
   existing "unrecognized agent line" note; `chef` still drops).
2. `parse_agents` learns an OPTIONAL `marginal=<n>` pair: meaningful only when
   `findings=`/`confirmed=` are both present and valid; constraint
   `0 <= marginal <= confirmed`; any violation (negative, non-int, > confirmed, or
   present without findings/confirmed) degrades `marginal` to None WITH a note while the
   line survives — mirror the existing findings/confirmed degradation code path and note
   style exactly. Event dicts gain a `"marginal"` key (None when absent).
3. `tests/test_role_ledger.py`: REPLACE `test_agent_roles_untouched` (line ~59, comment
   "D1 must not extend AGENT_ROLES") with `test_agent_roles_extended_exactly` pinning the
   new 10-tuple, carrying a comment naming this kit: superseded by role-roster D1 —
   extension is additive-tolerant (old ledgers parse byte-identically; out-of-vocab still
   drops). Add tests: each new token parses and survives; `chef` still drops with the
   note; `marginal=` happy path; each degradation case (>confirmed, negative, orphan
   without findings/confirmed); absent marginal → None; legacy lines (no marginal) parse
   with event `marginal is None`.
4. TRIPWIRE (from PLAN Risks): if any existing test pins the agent event dict's exact
   key set, update that single lock in lockstep (pin the NEW exact set — never a subset
   match) and record which test in your report for NOTES.
5. PROOF OF ZERO DRIFT (acceptance, not optional): run
   `python3 -m unittest tests.test_routing_scorecard tests.test_routing_history
   tests.test_crossrepo_trend tests.test_per_task_dollars tests.test_role_ledger -q`
   — the four byte-goldens (`GOLDEN_DEMO_MARKDOWN`, `GOLDEN_DEMO_HISTORY_MARKDOWN`, both
   JSON goldens) and the three 9-key card locks must pass UNCHANGED. If any golden
   fails, STOP and report — do not update a golden in this task.

Acceptance: extended tuple pinned by the replacement test; marginal parsing + all
degradations test-pinned; all named suites green with zero golden edits; full suite green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 -m unittest tests.test_role_ledger tests.test_routing_scorecard tests.test_routing_history tests.test_crossrepo_trend tests.test_per_task_dollars -q && python3 -m unittest discover -s tests -q
```

### T2 — The --roles view + by-task extras + demo
- id: T2
- title: Per-role value measurement (--roles) with roster derivation
- status: done
- model: sonnet
- depends: T1

Edit only `bin/routing_scorecard.py` and `tests/test_role_ledger.py` (new test classes
live there — role measurement is this file's concern).

1. **New flag `--roles`** (composable like `--history`; also `--demo --roles` for the
   synthetic smoke). It renders its OWN markdown card and its own `--json` object — it
   must NOT add keys to the existing kit/history cards or sections to `--history`
   markdown (PLAN D3).
2. **Per-kit roster derivation (D5):** distinct roles observed = `agent:` role tokens ∪
   {"reviewer" if any `reviewer:` line} ∪ {"implementer" if any outcome line}. Label
   R<count>. Escalation does NOT count toward roster size (it is a valve, not a roster
   role) — state this in the card's legend.
3. **The per-role value table** (aggregate across kits, plus a per-kit section):
   columns: role, dispatches, findings, confirmed, precision, marginal, marginal rate
   (marginal/dispatches), dollars. Honesty per PLAN D4: precision None-rendered as "n/a"
   when unmeasured (never 0); rows absent when zero dispatches; "insufficient sample
   (n<5)" tag from `MIN_ROLE_DISPATCHES = 5`; legacy lines without `marginal=` counted
   as "marginal unmeasured" (a separate count column or footnote — visible, never folded
   into 0); escalation excluded from the table with the one-line existing-law note.
   Reviewer rows come from the `reviewer:` family (which has no marginal field —
   reviewer marginal arrives only via future `agent:`-recorded phase roles… NO: keep it
   honest and simple: the reviewer: family gains NOTHING in this kit; the card notes
   "reviewer marginal: unmeasured (reviewer: family carries no marginal field)" — a
   future kit may extend that family).
4. **Dollars:** reuse the `--by-task` transcript-pricing machinery (`--session` +
   task-dirs discovery) — when invoked with `--session`, per-role dollar subtotals
   aggregate from the same events; without it, the dollars column reads "n/a (no
   --session)". Never fabricate; never sum across actual/estimated bases.
5. **`--by-task` markdown extras (additive):** when a task row carries dollars in any
   non-trio role, print an indented extras line under that row naming each extra role
   and its subtotal. The three-column table header and existing cells are byte-unchanged;
   run `tests/test_per_task_dollars.py` to prove the needle set survives.
6. **Demo:** `--demo --roles` builds a synthetic multi-kit fixture in-memory (the
   existing demo pattern) covering: an R3 kit (legacy, no marginal), an R7 kit with
   marginal data, an insufficient-sample role, and an out-of-vocab probe line — exercising
   every honesty label. Exit 0. This is the CLAUDE.md run-line smoke.
7. **Zero-drift proof again** (same suite list as T1's step 5) — goldens and locks
   untouched.

Acceptance: --roles renders per-kit + aggregate with every D4 honesty feature
test-pinned (new test classes; pin the demo's full markdown as this view's OWN golden so
future drift is deliberate); JSON shape pinned; by-task extras additive with needles
green; all prior goldens/locks pass unchanged; full suite green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 bin/routing_scorecard.py --demo --roles >/dev/null && echo roles-demo-ok && python3 -m unittest tests.test_role_ledger tests.test_routing_scorecard tests.test_routing_history tests.test_crossrepo_trend tests.test_per_task_dollars -q && python3 -m unittest discover -s tests -q
```

## Phase 2 — Templates + the two contract-sensitive skill edits

### T3 — Seven role templates
- id: T3
- title: skills/architect/references/roles/ — the seven agent skeletons
- status: done
- model: sonnet
- independent: yes

Create `skills/architect/references/roles/` with exactly seven files: `scout.md`,
`test-author.md`, `second-verifier.md`, `red-team.md`, `security-auditor.md`,
`docs-editor.md`, `synthesizer.md`. Nothing else.

Each file is a complete kit-agent skeleton the architect copies to
`.claude/agents/<slug>-<role>.md`, using the literal placeholder `<slug>` throughout
(the repo's `/path/to/polytropos` placeholder for repo paths). Required per file:

- Frontmatter: `name: <slug>-<role>`; a description in the repo's dispatch-guidance
  style ("Dispatch … during /polytropos:execute <slug> …"); `model:` default per PLAN's
  table (scout haiku, test-author sonnet, second-verifier sonnet, red-team sonnet,
  security-auditor sonnet, docs-editor haiku, synthesizer haiku); `tools: Bash, Read,
  Grep, Glob` for the four read-only roles (scout, second-verifier, red-team,
  security-auditor) — NO tools pin for test-author/docs-editor/synthesizer.
- Body: the role's mission (one tight paragraph, mission-bounded per PLAN's sprawl
  tripwire: verifier checks acceptance, red-team attacks BEYOND acceptance;
  security-auditor is fences/leaks only, never general review; second-verifier must
  state its lens differs from the first verifier's — spec-compliance vs breakage); its
  hook point; its recording contract (what it must return so the orchestrator can
  adjudicate findings/confirmed/marginal); the stop-and-report rule for brief conflicts.
- Read-only roles: the damage-restore practice paragraph (non-mutating checks first;
  mutate only copies in temp dirs; restore byte-for-byte and say so; close with
  `git status --porcelain`, own unexpected changes as YOUR defect) — same substance as
  the existing verifier/reviewer agents.
- Write-capable roles: a scoped-write law instead — test-author touches ONLY test files;
  docs-editor ONLY docs/comments; synthesizer ONLY NOTES.md prose (never its machine
  lines — backtick the six family tokens if mentioned); anything else is the agent's own
  defect.

Acceptance: seven files, correct frontmatter per role (programmatically checkable:
tools-pin present iff read-only role; model matches the table); `<slug>` placeholder
present in every `name:`; no absolute paths, no prices, no model-id price claims; full
suite green (no test enumerates these files — the suite proves nothing broke elsewhere).

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 - <<'EOF'
from pathlib import Path
import re
d = Path("skills/architect/references/roles")
want = {"scout":("haiku",True),"test-author":("sonnet",False),"second-verifier":("sonnet",True),
        "red-team":("sonnet",True),"security-auditor":("sonnet",True),"docs-editor":("haiku",False),
        "synthesizer":("haiku",False)}
files = sorted(p.stem for p in d.glob("*.md"))
assert files == sorted(want), files
for stem,(model,pinned) in want.items():
    t = (d / f"{stem}.md").read_text()
    fm = re.match(r"---\n(.*?)\n---\n", t, re.S).group(1)
    assert f"name: <slug>-{stem}" in fm, stem
    assert f"model: {model}" in fm, (stem, model)
    assert ("tools:" in fm) == pinned, (stem, "tools pin mismatch")
    assert "/Users/" not in t, stem
print("templates ok")
EOF
python3 -m unittest discover -s tests -q
```

### T4 — Architect skill: the roles: family + instantiation
- id: T4
- title: skills/architect/SKILL.md learns the roles dial
- status: done
- model: opus
- depends: T2, T3

Edit only `skills/architect/SKILL.md`. Additive-only (zero deletions or modifications of
existing lines — `git diff --numstat` second field 0), two insertions:

1. In Step 1's optional-dial list (beside the Autonomy/Budget bullets), a **Roles
   roster (optional)** bullet mirroring the budget bullet's structure: a single
   `roles: <token> <token> ...` line anywhere in PLAN.md; tokens from exactly the seven
   (scout, test-author, second-verifier, red-team, security-auditor, docs-editor,
   synthesizer); absent = the trio, today's behavior; a PLAN.md line family, never a
   task field — the task-field contract is unchanged. Include the tier ladder (R3/R5/
   R7/R10 per PLAN's table) as the recommended comparison shape, and the guidance:
   consult `python3 bin/routing_scorecard.py --roles` (the cross-kit per-role value
   evidence — marginal catch rate vs cost) before declaring; declare roles to TEST them,
   keep them only when their measured marginal value earns it.
2. In the Project-subagents section, after the trio: when PLAN.md declares roles,
   instantiate each from `skills/architect/references/roles/<role>.md` — copy to
   `.claude/agents/<slug>-<role>.md`, replace `<slug>`, keep the template's model
   default and tools posture unless the kit has a specific reason (state it in PLAN if
   so); never reuse an aesop-manifest agent name.

HARD FENCE: shared kit contract. After editing, re-check BOTH skills against CLAUDE.md's
contract bullet (layout, task fields, status vocabulary, phase headings,
depends/independent, model-field authority) and state in your report that the contract
text is untouched and both files agree. The new bullet must describe `roles:` with the
same "line family, never a task field" wording the autonomy/budget bullets use.

Acceptance: additive-only diff; both insertions present; tier ladder + evidence-first
guidance included; contract recheck stated; full suite green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && git diff --numstat skills/architect/SKILL.md | awk '{exit ($2!=0)}' && grep -q 'roles:' skills/architect/SKILL.md && grep -q 'references/roles' skills/architect/SKILL.md && python3 -m unittest discover -s tests -q
```

### T5 — Execute skill: reading the dial, hook points, recording
- id: T5
- title: skills/execute/SKILL.md learns dispatch + ledger rules for the seven
- status: done
- model: opus
- depends: T4

Edit only `skills/execute/SKILL.md`. Two changes — one additive section, one surgical
single-sentence amendment (this is the ONLY permitted modification of an existing line):

1. **New section `## Roles roster — optional extended roles, measured`** placed after
   the Budget-dial section. Contents, in the file's voice:
   - Setup reads PLAN.md's optional `roles:` line once (mirror the budget-dial reading
     sentence); absent = the trio, today's behavior everywhere.
   - Hook points, pinned: scout — before a declared-roster task's implementer dispatch
     (orchestrator MAY skip per task; every actual dispatch is recorded); test-author —
     after the implementer claims done, before the verifier; its failing tests are
     findings, fed to the implementer as retry evidence; second-verifier — parallel
     with the verifier, different lens; red-team — after verify passes, before `done`;
     security-auditor — phase end, parallel with the reviewer; docs-editor — phase end,
     after review adjudication; synthesizer — end of run, before the report.
   - Recording: EVERY declared-role dispatch appends an `agent:` line with its role
     token. Per-task roles use the task id; phase-scoped roles (security-auditor,
     docs-editor) use the phase token (`P1`) in the task slot; synthesizer uses `-`.
     Quality fields follow the existing adjudication law, plus `marginal=<n>`: of the
     confirmed findings, how many no EARLIER pipeline layer raised on that task/phase.
     Write the canonical order OUT IN FULL in the skill text (corrected at P1 review —
     never reference "PLAN's role order"):
     scout → implementer → test-author → verifier → second-verifier → red-team →
     reviewer → security-auditor → docs-editor → synthesizer;
     plus the parallel-pair tiebreaks verbatim: a finding raised by both verifier and
     second-verifier is the verifier's (not marginal for second-verifier); one raised by
     both reviewer and security-auditor is the reviewer's (not marginal for
     security-auditor); a finding is never counted marginal twice. Deflationary
     defaults, verbatim: unsure = not marginal; a finding with no artifact = not
     confirmed, hence never marginal. Backtick every quoted grammar token (the existing
     rule binds).
   - The dial is measurement, not mandate: declared roles run to be MEASURED
     (`--roles`); dropping a role that isn't earning its marginal keep is the expected
     outcome, decided by the human between kits, never mid-run.
2. **The scout-exception amendment.** The Agent-ledger section's sentence currently
   reading "Do NOT record phase reviewers or ad-hoc scouts: …" is amended (surgical, this
   sentence only) to distinguish BOTH halves (scope extended at P1 review — the new
   phase-token recording rule contradicts the sentence's rationale unless the same
   amendment explains it): ad-hoc lean-driver scouts remain unrecorded exactly as before,
   while a scout DECLARED via the roles roster is a per-task dispatch and IS recorded
   (role=scout); phase REVIEWERS remain recorded only via their own `reviewer:` family
   exactly as before, while declared phase-scoped roster roles (security-auditor,
   docs-editor) ARE recorded as `agent:` lines under the phase token — their transcripts
   are still never split per task (the never-split law is why their dollars stay n/a in
   the roles card).
   Also extend the grammar line's role enumeration `role=<implementer|verifier|escalation>`
   to name the full ten-token vocabulary (or reference the roster section) — pick the
   form that keeps the line readable; the scorecard's tuple is the source of truth.

HARD FENCE: shared kit contract — same recheck as T4, stated in your report. The SIX
machine-read line families stay six (no new family); `reviewer:` family untouched;
`outcome:`/`defect:`/`reroute:`/`session:` untouched.

Acceptance: the new section present with all seven hook points + recording rules +
deflationary defaults; the amendment touches exactly one sentence plus the grammar
line's role vocabulary; contract recheck stated; full suite green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && grep -q '## Roles roster' skills/execute/SKILL.md && grep -q 'marginal=' skills/execute/SKILL.md && grep -c 'role=scout' skills/execute/SKILL.md >/dev/null && python3 -m unittest discover -s tests -q
```

## Phase 3 — Protocol + wiring

### T6 — The experiment protocol doc
- id: T6
- title: docs/ROLE-EXPERIMENT.md — how to actually run the 3→10 test
- status: done
- model: sonnet
- depends: T2

Create `docs/ROLE-EXPERIMENT.md` only. Contents:

- The question ("do more roles pay?") and the method (marginal-catch on real kits — why
  it beats cross-kit A/B for this repo: self-controlled within each task/phase, no
  duplicate spend; and its honest limits: kits differ in difficulty, adjudication is
  human, sample accrues slowly).
- The tier ladder (R3/R5/R7/R10 with the exact role additions per tier) and the
  suggested cadence: run the next few kits at ascending tiers, then read
  `python3 bin/routing_scorecard.py --roles`.
- How to read the card, column by column, honesty labels included (insufficient sample,
  marginal-unmeasured legacy lines, n/a-not-zero, escalation exclusion, reviewer-marginal
  unmeasured).
- FOUR structural limits the P1 review pinned (mandatory content, each in plain words):
  (1) phase/run-scoped roles (security-auditor, docs-editor, synthesizer) can never
  carry per-task dollars under the never-split law — their cost side is structurally
  unmeasurable today, so "does it pay?" for them rests on marginal catches vs a cost you
  estimate from dispatch counts; (2) the marginal rate's denominator is MEASURED
  dispatches only (post-amendment) — quote of how to read it beside the unmeasured
  count; (3) marginal is ORDER-DEPENDENT, not role-intrinsic: earlier layers are
  structurally advantaged, and a late role's low marginal never proves the role
  worthless — it proves the earlier layers caught things first (do not read it as "drop
  the verifier"); (4) scout, docs-editor, and synthesizer produce no adjudicable
  findings by design — their rows are dispatch-cost with indirect value (grounding,
  docs freshness, distilled learnings), judged qualitatively, and the card's legend says
  so.
- Decision guidance (judgment, not law): a role earns a standing place when its marginal
  rate is materially non-zero over ≥ MIN_ROLE_DISPATCHES dispatches at a cost per
  marginal catch you'd pay again; drop roles that measure zero-marginal over a real
  sample; re-test after model-generation changes. This week's three reviewer marginal
  catches are the worked example — cite them from the harness-update/graphify-skill
  NOTES (no dollars invented).
- No prices, no model ids, no absolute paths; derived facts point at the engines.

Acceptance: file exists covering method/tiers/reading/decision guidance with the honest
limits stated; suite green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 - <<'EOF'
t = open("docs/ROLE-EXPERIMENT.md").read()
for needle in ("marginal", "R3", "R5", "R7", "R10", "insufficient sample", "--roles",
               "not law", "/Users"):
    assert (needle in t) != (needle == "/Users"), needle
print("protocol doc ok")
EOF
python3 -m unittest discover -s tests -q
```

### T7 — CLAUDE.md run-line + KIT_SENTINELS
- id: T7
- title: Wire role-roster into the repo's law
- status: done
- model: haiku
- depends: T5, T6

Two edits, nothing else:

1. `CLAUDE.md` "How to run things" — one line, matching the block's comment style:
   `python3 bin/routing_scorecard.py --demo --roles      # per-role marginal-value smoke (synthetic kits; lands with the role-roster kit)`
   Budget: CLAUDE.md was 14,511 bytes before this kit; stay ≤ 16,000. No Invariants
   bullet — the roles dial is kit-law (GUARDRAILS + the two skills), not an always-on
   repo invariant.
2. `tests/test_guardrails_layout.py` `KIT_SENTINELS` — add:
   `"role-roster": "Extended roles are measured, never mandated",`
   (Capital E — quoted from GUARDRAILS.md line 6 bytes, where the phrase sits inside a
   bold marker on one physical line; verified with grep at authoring time. Do not edit
   GUARDRAILS.md; if the substring does not match the file's bytes, STOP and report.)

Acceptance: `wc -c CLAUDE.md` ≤ 16000; sentinel entry matches file bytes; full suite
green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && grep -q 'role-roster' tests/test_guardrails_layout.py && grep -q 'demo --roles' CLAUDE.md && python3 -m unittest discover -s tests -q
```
