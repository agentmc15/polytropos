# PLAN — memory-skill

Add a **memory** skill to the polytropos plugin: a durable, cross-session fact store
PLUS a smart-retrieval layer, engineered so that having memory **never degrades the model's
answers**. That non-degradation property is the spine of this design, addressed structurally
across all three failure modes:

- **(a) Context bloat/rot** → recall is pull-only, script-computed, and budget-capped. The
  corpus never enters model context; the model only ever sees a block of at most
  `MAX_FACTS`/`BUDGET_CHARS`.
- **(b) Stale/wrong memories** → every fact carries freshness metadata (created /
  last_verified / expires / confidence); expired facts are withheld, stale facts are
  down-ranked and surfaced with an explicit "verify before relying" marker, and a review
  flow prunes the store.
- **(c) Irrelevant/noisy recall** → a hard relevance gate: a fact below the gate is NOT
  surfaced, and an empty recall is a correct, successful outcome — better nothing than noise.

Ships like the existing skills: `skills/memory/SKILL.md` + stdlib-only `bin/memory_*.py`
engines + `tests/test_memory_*.py`, with the store under gitignored `memory/` at the plugin
root (the `journal/` precedent). The feature prices nothing and dispatches nothing.

autonomy: advisory

## Goal

One new skill, two new stdlib engines with their test suites, the store gitignored before any
engine can write it, and a demonstrable recall-under-budget path — full suite green, every
frozen surface byte-untouched.

**Done looks like:**

1. `skills/memory/SKILL.md` exists in house format (frontmatter `name`/`description`/
   `allowed-tools`, the `${CLAUDE_PLUGIN_ROOT}` resolution preamble, body sections for
   recall / save / review / privacy, and an explicit effectiveness-contract paragraph).
   No manifest edit exists or is needed — see Ground truth below.
2. `bin/memory_store.py` and `bin/memory_recall.py` exist, stdlib-only, zero `Path.home()`,
   zero `subprocess`, and pass `tests/test_memory_store.py` + `tests/test_memory_recall.py`
   (every test uses temp `--memory-dir` fixtures and an explicit `--now`).
3. `.gitignore` carries a root-anchored `/memory/` entry:
   `git check-ignore -q memory/facts/probe.md` succeeds AND
   `git check-ignore -q skills/memory/SKILL.md` fails (the skill dir must NOT be ignored).
4. `python3 bin/memory_recall.py --demo` prints a deterministic, byte-stable demo (synthetic
   store in its own temp dir) that visibly demonstrates all three safeguards: the relevance
   gate excluding an irrelevant fact, a stale fact down-ranked and marked
   `STALE — verify before relying`, an expired fact withheld, and the budget cap dropping a
   fact with an honest `+N more` line.
5. Named tests cover each degradation mode: gate-returns-nothing on an irrelevant query,
   expired-withheld / stale-downweighted-and-marked, and whole-fact budget truncation.
6. `python3 -m unittest discover -s tests -v` fully green, and
   `git diff --quiet -- bin/journal_collect.py skills/journal skills/route skills/architect skills/execute skills/escalate skills/cost-report skills/fable-check skills/setup data .claude-plugin copilot codex README.md` exits 0
   (existing skills, all three pricing files, the plugin manifest, both harness bundles, and
   README byte-untouched; CLAUDE.md's insertions were pre-made by the architect).

## Ground truth (verified against the tree at kit-build time — pinned so no executor needs it)

- **Skill registration is directory auto-discovery.** `.claude-plugin/plugin.json` and
  `.claude-plugin/marketplace.json` carry NO skill roster — the daily-journal kit added
  `skills/journal/` with zero manifest edits and it registered fine. Therefore this kit has
  NO manifest task; do not invent one. `.claude-plugin/` stays byte-untouched.
- **House skill format** (from `skills/journal/SKILL.md`): frontmatter `name`,
  `description` (one sentence with "Use when..." triggers), `allowed-tools`; body opens with
  the root-resolution preamble: use `${CLAUDE_PLUGIN_ROOT}` if set, else resolve `../..`
  relative to the SKILL.md to an ABSOLUTE path (bash cwd is not the skill dir), call it
  `$ROOT`.
- **House engine format** (from `bin/journal_collect.py`): module docstring stating the
  read/write contract up top; `PLUGIN_ROOT = Path(__file__).resolve().parent.parent`;
  runtime defaults derive from `PLUGIN_ROOT`, never `Path.home()` (the store needs no home
  read at all — unlike the journal, ALL memory paths derive from the plugin root or an
  explicit flag); argparse `main(argv)` returning an int; module-level pinned constants.
- **Cross-module reuse pattern**: siblings load via
  `importlib.util.spec_from_file_location` (`journal_collect._load`); `bin/` is not a
  package. `memory_recall.py` loads `memory_store.py` this way, read-only, for the shared
  schema functions.
- **Test conventions** (from `tests/test_journal_collect.py`): stdlib `unittest`; a SAFETY
  CONTRACT docstring; engines loaded via importlib by absolute path; every `main([...])`
  call passes explicit `--memory-dir`/`--now` overrides at temp fixtures; the only
  subprocess anywhere is one sanctioned self-invocation smoke via `sys.executable`.
- **Verify command form**: `python3 -m unittest discover -s tests -p '<file>.py' -v` (the
  dotted-module form is broken on this machine).
- **Gitignore precedent**: `/journal/` and `/trends/` are root-anchored entries with a
  one-line comment each. Root anchoring is load-bearing here: an unanchored `memory/`
  pattern would ALSO ignore `skills/memory/` (gitignore dir patterns match at any depth).
- **Borrowed schema** (from the user's personal file-memory at
  `~/.claude-personal/projects/-Users-<name>/memory/` — READ-ONLY reference, never
  modified by this kit): one-line-per-fact index file + one `*.md` per fact with
  frontmatter `name`/`description`/`type` and a markdown body that may link related facts
  with `[[slug]]`. This kit flattens its nested `metadata.type` to a flat `type:` line and
  adds the freshness fields (D2).

## Decisions

- **D1 — Host = `skills/memory/` inside this plugin; registration = nothing.** Skills
  auto-discover from `skills/` (ground truth above). `skills/memory/` is the ONE sanctioned
  addition under `skills/`; no `.claude-plugin/` edit anywhere in this kit.
- **D2 — Store schema: one markdown file per fact, flat frontmatter, derived index.**
  `memory/facts/<slug>.md` with a flat `key: value` frontmatter between `---` fences,
  parsed by a pinned ~15-line stdlib parser (split each line on the FIRST `": "`) — NEVER a
  YAML library (none exists in stdlib; importing one is a fence violation). Fields, all on
  every fact: `schema: 1`, `name`, `description` (one line — it feeds the index and the
  ranker), `type` (`user|feedback|project|reference|decision` — the personal system's four
  plus `decision`), `tags` (comma-separated lexical hooks — the save-time antidote to
  lexical ranking's synonym blindness), `created` (YYYY-MM-DD), `last_verified`
  (YYYY-MM-DD), `expires` (YYYY-MM-DD or `never`), `confidence` (`high|medium|low`),
  `source` (free text: where this came from). Unknown keys round-trip unchanged. Body is
  markdown; `[[slug]]` wikilinks are stored verbatim (not resolved in v1). Slugs match
  `^[a-z0-9][a-z0-9-]{0,63}$`, validated BEFORE any path is composed (the trends
  date-grammar precedent — nothing can escape the store dir). `memory/index.md` is a
  DERIVED artifact — one line per fact, fully regenerated on every mutation; fact files are
  the only source of truth. Rationale: files are diffable, hand-editable, and recoverable;
  the flat grammar keeps the parser trivial and stdlib.
- **D3 — Store location: gitignored `memory/` at the plugin root, flag-overridable.**
  Default `PLUGIN_ROOT / "memory"` (exactly how `journal/` works), overridden only via
  `--memory-dir`. No env var, no `Path.home()` anywhere in the new code — the memory
  feature has zero legitimate home-dir need. The store is private user data: root-anchored
  `/memory/` in `.gitignore`, landed as an independent task so it exists before any engine
  can write.
- **D4 — Recall mechanism (the anti-bloat spine): pull-only, script-computed,
  budget-capped.** A deterministic stdlib script (`bin/memory_recall.py`) reads the store
  and returns only the winners — the corpus never enters model context; the model sees at
  most the capped block. Defaults pinned: `MAX_FACTS = 5`, `BUDGET_CHARS = 4000` (~1k
  tokens), flags `--max-facts`/`--budget-chars` to tune per call. Truncation is WHOLE-FACT:
  a fact that would overflow the budget is dropped (never emitted half-way), with one
  honest trailing line `(+N more above the gate — raise --max-facts/--budget-chars or read
  memory/index.md)`; the single edge case where the TOP fact alone exceeds the budget emits
  its header line plus a pointer at its file instead of the body. No curator subagent in
  v1: a subagent would spend tokens and a dispatch to do what a deterministic script does
  for free, less testably — the script IS the context-isolation layer. NO hook and NO
  session-start injection: push injection is deferred by design; the default posture is
  on-demand pull, and the skill says so.
- **D5 — Ranking: pure-stdlib lexical BM25-lite, pinned concretely.** Tokenize with
  `re.findall(r"[a-z0-9]+", text.lower())`, drop 1-char tokens and the pinned `STOPWORDS`
  set. Fields are weighted: `FIELD_WEIGHTS = {"name": 3, "tags": 3, "description": 2,
  "body": 1}` (weighted term frequency `wtf` = sum of field weight × count). IDF per term:
  `idf(t) = ln(1 + (N - df + 0.5) / (df + 0.5))` over the fact corpus. Raw score = sum over
  DISTINCT matched query terms of `idf(t) * wtf / (wtf + K_SAT)` with `K_SAT = 1.2`
  (BM25-style saturation; no doc-length norm at this corpus scale — an accepted, documented
  limitation). Final score = raw × staleness multiplier (fresh 1.0, stale
  `STALE_MULT = 0.6`) × confidence multiplier (`CONF_MULT = {"high": 1.0, "medium": 0.9,
  "low": 0.7}`). Ordering: score desc, then `last_verified` desc, then slug asc (full
  determinism). Model-assisted re-ranking is deliberately NOT built — the stdlib path is
  the feature and must never require a model; the skill layers judgment on TOP of the
  script's output.
- **D6 — Relevance gate: better nothing than noise.** A fact is surfaced only if BOTH hold:
  (i) it matched at least `GATE_MIN_TERMS = 2` distinct query terms, OR at least one query
  term is an EXACT token of its `tags`; and (ii) its final score ≥ `GATE_MIN_SCORE = 1.0`.
  Nothing passing prints the pinned line
  `no memory above the relevance gate for this query` and exits 0 — an empty recall is a
  SUCCESS, not an error, and the skill instructs proceeding without memory in that case.
  Query derivation is the caller's job and the skill pins it: pass 5–15 salient keywords
  from the task at hand (nouns, tool names, file names), never a whole prompt.
- **D7 — Freshness: typed soft-TTLs, three states, an explicit verify-before-use flag.**
  `TYPE_TTL_DAYS = {"user": 365, "feedback": 365, "project": 90, "reference": 180,
  "decision": 180}` (projects churn fastest; user preferences endure).
  `staleness_state(meta, today)` returns `expired` if `expires` is a date ≤ today; else
  `stale` if `last_verified` (fallback `created`) is more than the type's TTL ago; else
  `fresh`. Expired facts are WITHHELD from recall by default (`--include-expired` to
  override, for review flows); stale facts rank ×0.6 and carry the literal marker
  `STALE — verify before relying` on their header line. `memory_store.py verify <slug>`
  bumps `last_verified`; `update` also bumps it (an update IS a verification);
  `review` prints every stale/expired fact with a suggested action (verify / update /
  remove). All date math flows through an explicit `--now YYYY-MM-DD` seam (default:
  today) so every test and the demo are deterministic.
- **D8 — Write/curate flow: dedup-gated add, update-over-duplicate, explicit remove.**
  `add` computes token-set Jaccard similarity (over name + description + body) against
  every existing fact; ≥ `DEDUP_JACCARD = 0.5` → exit 2 with the colliding slug and the
  instruction to `update` it instead (`--force` overrides deliberately). The skill pins the
  save discipline: remember durable facts the repo does NOT already record (user
  preferences, decisions + their rationale, environment facts, corrections the user gave);
  never secrets/credentials, never transient state, never things CLAUDE.md or the repo
  already records. Wrong fact → `remove`, immediately.
- **D9 — Integration surface: the skill is the only entry point, and it carries the
  effectiveness contract.** Body sections: Recall (derive keywords → run the script →
  treat the block as advisory context → obey stale markers by re-verifying against
  repo/reality before relying), Save (the D8 discipline), Review & prune, Privacy (the
  store is local-only gitignored user data; recalled text does enter model context — only
  what the user chose to remember, capped). One pinned paragraph states the contract:
  NEVER bulk-inject — never paste `memory/index.md`, the store directory, or uncapped fact
  sets into context; recall goes through `bin/memory_recall.py` and its budget, always.
- **D10 — Executor pins: sonnet default, opus for the recall engine, haiku for mechanical.**
  Routing history (15 kits, 72/73 first-try; haiku 12/12, sonnet 44/45, opus 16/16; no
  dollars — no `session:` lines) says well-pinned briefs execute cleanly at sonnet. Sonnet
  takes the store engine, freshness lifecycle, skill, and doc; opus takes T4 only — the
  recall engine is the densest algorithmic surface (scoring + gate + budget + freshness
  interaction + byte-stable demo) and the feature's spine, worth one tier up; haiku takes
  the gitignore entry and the final audit. The per-task escalation valve covers surprises.

## OUT-OF-SCOPE fence (do NOT build)

- **No cross-harness parity** — no `copilot/` or `codex/` ports of the memory capability
  (a possible FUTURE kit, mirroring how `harness-parity` followed `codex-harness`). Both
  bundle trees stay byte-untouched.
- **No hooks, no auto-injection, no session-start bulk load** — recall is pull-only in v1.
  No `hooks/` dir, no settings.json wiring, no statusline change.
- **No embeddings, no vector store, no model-assisted ranking, no pip, no network** —
  ranking is the pinned stdlib lexical algorithm and nothing else. Zero `subprocess` in
  either engine (tests' one sanctioned subprocess is the `sys.executable` self-invocation
  smoke). No `urllib`/`http.client`/`socket` import in any new file.
- **The feature prices NOTHING** — no pricing file is read, imported, or edited; no price
  or real model id appears in any new file.
- **No edits to existing skills, the shared architect/execute kit contract,
  `.claude-plugin/`, `bin/` engines, `data/`, `copilot/`, `codex/`, `docs/` (beyond the one
  new doc), or any completed kit.** No README changes. CLAUDE.md and README.md are NOT
  executor edit targets — the architect pre-made CLAUDE.md's run-lines, invariant bullet,
  and this kit's fence.
- **The store is never committed** — `/memory/` is gitignored (root-anchored) before any
  engine lands; no test or verify ever reads or writes a real store (temp `--memory-dir`
  always); zero `Path.home()` in any new file.
- **The personal memory system at `~/.claude-personal/.../memory/` is reference-only** —
  never read at runtime by the new engines, never written by anything in this kit.
- **Nothing outside this repo**; no commit, no push.

## Risks & tripwires

- **Context-bloat regression by prose drift**: a skill sentence like "read the index for
  context" reintroduces bulk injection. The effectiveness-contract paragraph (D9) is pinned
  verbatim in T5; the reviewer checks recall reaches the model ONLY via the capped script
  output.
- **The unanchored-gitignore trap**: `memory/` (no leading slash) also ignores
  `skills/memory/` — the skill would silently vanish from git. The entry MUST be
  `/memory/`; T2's verify proves both directions.
- **Store accidentally committed**: T2 is independent and lands first-in-phase; the T7
  audit greps the ignore entry and checks `git status --porcelain` for any `memory/` path.
- **Gate too loose = noise wins**: the gate constants are pinned (D6) and
  `test_irrelevant_query_recalls_nothing` is a required, named test — an executor "helpfully"
  lowering `GATE_MIN_SCORE` to make a test pass is a defect.
- **Stdlib lexical ranking weakness (synonyms/paraphrase)**: accepted and documented;
  mitigated at save time (tags are mandatory lexical hooks) and at query time (the skill
  derives keyword-rich queries). Do not compensate with a model call.
- **YAML temptation**: there is no stdlib YAML; any `import yaml` is a fence violation. The
  flat `key: value` grammar and its ~15-line parser are the schema.
- **`Path.home()` leak**: the memory feature has no legitimate home read; the T7 audit
  greps all four new Python files for `Path.home` and expects zero.
- **Dedup false positives blocking saves**: Jaccard 0.5 is deliberately conservative;
  `--force` is the documented escape hatch — do not silently lower the threshold.
- **Nondeterminism in demo/tests**: every ordering has a pinned tie-breaker (D5), all date
  math goes through `--now`, and the demo pins its own dates — `--demo` twice must be
  byte-identical (tested).

## Phases

- **Phase 1 — Store foundation:** the store engine + schema (T1) and the gitignore entry
  (T2, independent — may run in parallel).
- **Phase 2 — Freshness, then recall:** the freshness lifecycle lands in the store engine
  (T3), then the recall engine builds on it (T4).
- **Phase 3 — Integration:** the skill (T5).
- **Phase 4 — Docs + closeout:** the design doc (T6) and the full-suite/frozen-surface
  audit (T7).

Warm-cluster hint: T1 → T3 is a strictly serial same-file chain (`bin/memory_store.py` +
`tests/test_memory_store.py`, both `model: sonnet`) — one warm implementer may serve both.
T2 is independent of everything and parallel with T1. T4 (opus) is always a fresh spawn.
The verifier is always a fresh spawn.
