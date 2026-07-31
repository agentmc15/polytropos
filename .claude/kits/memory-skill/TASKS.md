# TASKS — memory-skill

Repo root: `/path/to/polytropos`. Run all verify commands from
there. Read `PLAN.md` (same directory) first — especially the ground-truth pins, decisions
D1–D10, the OUT-OF-SCOPE fence, and the risks/tripwires. Status vocabulary:
`pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `memory-skill-implementer` (the parameter overrides the agent's
frontmatter default). Tasks marked `independent: yes` within the same phase may run in
parallel; `depends:` lists hard ordering. Dispatch `memory-skill-reviewer` at each phase end.

Warm-cluster hints: **T1 → T3** is a strictly serial same-file chain (`bin/memory_store.py` +
`tests/test_memory_store.py`, both `model: sonnet`) — one warm implementer may serve both. T2
is independent and may run parallel with T1. T4 is `model: opus` and always a fresh spawn.
The verifier is always a fresh spawn.

Standing rules for every task: Python is stdlib-only (no pip, no requirements, no pytest —
`import yaml` is a fence violation; the flat frontmatter grammar pinned below IS the schema);
zero `Path.home()` and zero `subprocess` in the two new engines (the ONE sanctioned subprocess
anywhere is a test's `sys.executable` self-invocation smoke); every test/verify uses temp
`--memory-dir` fixtures and an explicit `--now` — NEVER a real store, never the user's home;
the engines read/import NO pricing file and contain no price or model id; never edit existing
skills, `bin/` engines, `data/`, `.claude-plugin/`, `copilot/`, `codex/`, `README.md`,
`CLAUDE.md` (the architect pre-made its insertions), or any completed kit; no
network/`urllib`/`http.client`/`socket` imports; verify commands use
`python3 -m unittest discover -s tests [-p '<file>.py']` (the dotted-module form is broken on
this machine). Where a brief pins content, constants, or names verbatim, reproduce them
exactly; if repo reality contradicts the brief, STOP and report — do not improvise.

---

## Phase 1 — Store foundation

### T1 — `bin/memory_store.py` core + tests (schema, CRUD, dedup, index)
- status: done
- model: sonnet
- depends: (none)
- independent: yes (parallel with T2)

**Brief.** Create the durable fact store: `bin/memory_store.py` (new file) and
`tests/test_memory_store.py` (new file). Read first for conventions:
`bin/journal_collect.py` (module-docstring contract style, `PLUGIN_ROOT` pattern, argparse
`main(argv) -> int`, module-level constants) and `tests/test_journal_collect.py` (SAFETY
CONTRACT docstring, importlib loading via `BIN_DIR`, temp-dir fixtures, `_call_main` stdout
capture). PLAN.md D2/D3/D8 govern.

**The engine.** Module docstring states: the store is gitignored user data; the ONLY writes
are under `--memory-dir` (default `PLUGIN_ROOT / "memory"`); zero home-dir access, zero
subprocess, zero network, no pricing. Pinned module-level constants:

```python
SCHEMA_VERSION = 1
FACT_TYPES = ("user", "feedback", "project", "reference", "decision")
CONFIDENCE_LEVELS = ("high", "medium", "low")
DEDUP_JACCARD = 0.5
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
FACTS_SUBDIR = "facts"
INDEX_NAME = "index.md"
```

Fact file format (flat frontmatter between `---` fences; parser splits each line on the FIRST
`": "` — no YAML library exists in stdlib and none may be imported):

```
---
schema: 1
name: Deploy target
description: Where the dashboard deploys
type: reference
tags: deploy, cloudflare
created: 2026-01-10
last_verified: 2026-01-10
expires: never
confidence: high
source: user stated in session
---
The dashboard deploys to Cloudflare Workers. Related: [[legacy-build-flow]].
```

Pinned functions (memory_recall.py will import these read-only in T4 — keep the signatures):
`validate_slug(slug) -> bool`; `slugify(name) -> str` (lowercase, non-alnum runs → `-`,
strip/collapse, truncate to 64, must satisfy `SLUG_RE`); `parse_fact(text) -> (meta, body)`
(meta is a dict preserving unknown keys; missing fences → `ValueError`);
`render_fact(meta, body) -> str` (round-trips: `parse_fact(render_fact(m, b)) == (m, b)` for
canonical input); `fact_path(memory_dir, slug) -> Path` (calls `validate_slug` FIRST — an
invalid slug raises before any path is composed; the trends date-grammar precedent);
`load_store(memory_dir) -> list[(slug, meta, body)]` (sorted by slug; unreadable/malformed
files are skipped with a note collected into a `notes` list, never a crash);
`token_set(text) -> set` (`re.findall(r"[a-z0-9]+", text.lower())`, drop 1-char tokens);
`jaccard(a, b) -> float`; `rebuild_index(memory_dir, now) -> None`; `main(argv) -> int`.

CLI surface (argparse subcommands; every subcommand takes `--memory-dir DIR` and
`--now YYYY-MM-DD`, defaults `PLUGIN_ROOT / "memory"` and today; `--json` where noted):

- `add --name N --type T [--description D] [--tags a,b] [--body TEXT | --body-file F]
  [--slug S] [--expires YYYY-MM-DD|never] [--confidence high|medium|low] [--source S]
  [--force] [--json]` — validates type/confidence/slug (slug defaults to `slugify(name)`);
  sets `created`/`last_verified` to `--now`, `expires` default `never`, `confidence` default
  `high`, `schema` to `SCHEMA_VERSION`. **Dedup gate (D8)**: before writing, compute
  `jaccard(token_set(new name+description+body), token_set(existing ...))` against every
  stored fact; any ≥ `DEDUP_JACCARD` → print
  `duplicate of [<slug>] — update it instead (or pass --force)` and exit 2, writing nothing.
  Existing slug collision (exact) → same refusal path. On success: `mkdir(parents=True)` the
  facts dir, write the file, regenerate the index, print the slug, exit 0.
- `update <slug> [--name|--description|--tags|--body|--body-file|--expires|--confidence|
  --type|--source ...]` — rewrites only the given fields, preserves unknown keys, bumps
  `last_verified` to `--now` (an update IS a verification — PLAN D7), regenerates the index.
  Unknown slug → message + exit 2.
- `remove <slug>` — deletes the fact file, regenerates the index. Unknown slug → exit 2.
- `list [--json]` — one line per fact: `[<slug>] <name> — <description> (<type>, <confidence>)`;
  `--json` emits `{"schema_version": 1, "facts": [...meta + slug...], "notes": [...]}`.
  Empty/missing store → `no facts stored yet` + exit 0.

(`verify` and `review` subcommands land in T3 — do NOT build them here, but structure the
subparser dispatch so T3 adds them additively.)

Index format (regenerated fully on every mutation; a derived artifact — say so in a comment
at the top of the generated file): header `# Memory index (generated — facts/ is the source
of truth)` then one line per fact sorted by slug:
`- [<name>](facts/<slug>.md) — <description> (<type>)`. (T3 will extend the line with the
staleness state; keep `rebuild_index` a single function so the extension is one edit.)

**The tests** (`tests/test_memory_store.py`, all through temp `--memory-dir` +
explicit `--now`, in-process `main([...])` calls with stdout captured): slug validation +
slugify edge cases + `fact_path` raising on a bad slug (e.g. `../escape`); add → file exists,
frontmatter round-trips, index regenerated; add with exact-duplicate content → exit 2, nothing
written; `--force` overrides; update preserves unknown keys and bumps `last_verified`; remove
deletes + reindexes; list on empty store; malformed fact file is skipped with a note (not a
crash); one `sys.executable` self-invocation smoke of `list` against a temp dir. SAFETY
CONTRACT docstring at the top mirroring `tests/test_journal_collect.py`'s: no real home, no
real store, no `Path.home()`, subprocess only for the sanctioned self-invocation.

**Acceptance.**
- Both new files exist; nothing else in the tree changed.
- `grep -n "Path.home\|subprocess" bin/memory_store.py` → no matches;
  `grep -n "import yaml" bin/memory_store.py tests/test_memory_store.py` → no matches.
- All pinned constants/signatures present with the pinned values/names.
- Verify green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_memory_store.py' -v
```

### T2 — Gitignore the store (root-anchored)
- status: done
- model: haiku
- depends: (none)
- independent: yes (parallel with T1)

**Brief.** Append exactly these two lines to the END of `/path/to/polytropos/.gitignore`
(matching the existing `/journal/` + `/trends/` comment style; change no existing line):

```
# memory-skill fact store (private user data — never committed)
/memory/
```

The leading slash is LOAD-BEARING (PLAN.md tripwire 2): an unanchored `memory/` pattern would
also ignore the new `skills/memory/` directory and the skill would silently vanish from git.

**Acceptance.** `.gitignore` gains exactly the two pinned lines at the end; every
pre-existing line byte-identical; the verify command prints both `IGNORED` and
`SKILL-NOT-IGNORED`.

**Verify.**
```bash
git check-ignore -q memory/facts/probe.md && echo IGNORED; git check-ignore -q skills/memory/SKILL.md || echo SKILL-NOT-IGNORED
```

---

## Phase 2 — Freshness, then recall

### T3 — Freshness lifecycle in the store (`verify`, `review`, staleness states)
- status: done
- model: sonnet
- depends: T1
- independent: no (same files as T1 — warm-cluster tail)

**Brief.** Extend `bin/memory_store.py` and `tests/test_memory_store.py` (additively — every
T1 test stays green and byte-intact except where this brief pins a seam) with the freshness
model of PLAN.md D7. New pinned module-level constant:

```python
TYPE_TTL_DAYS = {"user": 365, "feedback": 365, "project": 90, "reference": 180, "decision": 180}
```

New pinned function (memory_recall.py imports it in T4 — keep the signature):
`staleness_state(meta, today) -> str` returning one of `"fresh" | "stale" | "expired"`:
`expired` if `meta["expires"]` is a date ≤ `today` (the string `never` never expires);
else `stale` if `last_verified` (fallback `created`; unparseable dates count as stale, never
a crash) is more than `TYPE_TTL_DAYS[type]` days before `today` (unknown type → 180); else
`fresh`. Dates are `YYYY-MM-DD` strings compared via `datetime.date` — all date math flows
through the subcommands' existing `--now` seam.

New subcommands (additive to the T1 dispatch):

- `verify <slug>` — sets `last_verified` to `--now`, rewrites the fact, regenerates the
  index, prints `verified [<slug>] — fresh until +<ttl>d`. Unknown slug → exit 2.
- `review [--json]` — loads the store and prints one line per NON-fresh fact:
  `[<slug>] <name> — <state> (last_verified <date>, ttl <n>d) → verify, update, or remove`,
  expired facts first, then stale, each group sorted by slug; a fully-fresh store prints
  `all <n> facts fresh` and exits 0. `--json` emits
  `{"schema_version": 1, "expired": [...], "stale": [...], "fresh_count": n, "notes": [...]}`.
  Read-only except that it never writes anything at all (report only).

Also extend `rebuild_index` (the single-function seam T1 left): the index line becomes
`- [<name>](facts/<slug>.md) — <description> (<type>, <state>)` with the state computed at
rebuild time from `--now`. Extend `list` output the same way:
`[<slug>] <name> — <description> (<type>, <confidence>, <state>)` — this is the ONE
sanctioned change to a T1 output shape; update the affected T1 assertions minimally and note
it in the test diff.

New tests (additive): expired vs stale vs fresh boundary cases (exactly-at-TTL is fresh;
TTL+1 day is stale; `expires` = today is expired); `verify` flips stale → fresh; `review`
ordering (expired before stale) and the all-fresh line; `--now` determinism (same store, two
different `--now` values, different states); index carries the state.

**Acceptance.**
- `staleness_state` and `TYPE_TTL_DAYS` present with pinned semantics; `verify`/`review`
  subcommands work as pinned; index/list lines carry the state.
- T1's tests still pass (only the pinned list/index assertion updates changed).
- Still zero `Path.home()`/`subprocess` in the engine.
- Verify green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_memory_store.py' -v
```

### T4 — `bin/memory_recall.py` + tests (ranking, gate, budget, demo)
- status: done
- model: opus
- depends: T3
- independent: no

**Brief.** The anti-bloat spine (PLAN.md D4/D5/D6 — read them in full before writing code).
Create `bin/memory_recall.py` and `tests/test_memory_recall.py`. The engine is STRICTLY
read-only over the store (`--demo` writes only inside its own `tempfile.TemporaryDirectory`);
zero `Path.home()`, zero `subprocess`, no pricing, no network. Load the store module
read-only via the house importlib pattern (copy `_load` from `bin/journal_collect.py`;
`ms = _load("memory_store")`) and REUSE `ms.load_store`, `ms.parse_fact`,
`ms.staleness_state`, `ms.token_set` — never re-implement them.

Pinned module-level constants:

```python
MAX_FACTS = 5
BUDGET_CHARS = 4000
GATE_MIN_SCORE = 1.0
GATE_MIN_TERMS = 2
K_SAT = 1.2
STALE_MULT = 0.6
CONF_MULT = {"high": 1.0, "medium": 0.9, "low": 0.7}
FIELD_WEIGHTS = {"name": 3, "tags": 3, "description": 2, "body": 1}
STOPWORDS = frozenset("a an and are as at be but by for from has have how in is it its of on
or that the this to was what when where which who will with you your".split())
GATE_EMPTY_LINE = "no memory above the relevance gate for this query"
```

(Reformat the STOPWORDS literal to valid Python — one `.split()` string — keeping exactly
these words.)

**Scoring (D5, implement exactly):** query terms = tokenized query (store's `token_set`
tokenization: `[a-z0-9]+`, lowercase, drop 1-char) minus STOPWORDS. Per fact, per field,
term counts from `re.findall(r"[a-z0-9]+", field_text.lower())` (keep counts — not the set
helper — dropping 1-char tokens and stopwords); weighted term frequency
`wtf(t) = Σ_field FIELD_WEIGHTS[field] * count(t, field)`. Corpus stats over ALL non-expired
facts (expired facts are excluded from recall AND from N/df unless `--include-expired`):
`idf(t) = math.log(1 + (N - df + 0.5) / (df + 0.5))`, `df` = number of facts where
`wtf(t) > 0`. Raw score = `Σ` over DISTINCT matched query terms of
`idf(t) * wtf(t) / (wtf(t) + K_SAT)`. Final = raw × (`STALE_MULT` if state is `stale` else
1.0) × `CONF_MULT[confidence]` (unknown confidence → treated as `low`). Sort: final desc,
`last_verified` desc, slug asc.

**Gate (D6, implement exactly):** surfaced only if (distinct matched terms ≥ `GATE_MIN_TERMS`
OR ≥ 1 query term is an exact token of the fact's `tags` field) AND final score ≥
`GATE_MIN_SCORE`. Zero survivors → print `GATE_EMPTY_LINE`, exit 0. Missing/empty store →
`no memory store yet` , exit 0 (a fresh install must not error).

**Budget (D4, implement exactly):** take gate survivors in order; stop before exceeding
`--max-facts` (default `MAX_FACTS`) or `--budget-chars` (default `BUDGET_CHARS`, counted over
the rendered output block). Truncation is WHOLE-FACT — never emit a partial body; facts
dropped by either cap produce one trailing line:
`(+N more above the gate — raise --max-facts/--budget-chars or read memory/index.md)`.
Edge case: if the TOP survivor alone exceeds the char budget, emit its header line plus
`(body exceeds budget — read memory/facts/<slug>.md)` instead of the body.

**CLI:**
```
memory_recall.py --query "words ..." [--memory-dir DIR] [--max-facts N] [--budget-chars N]
                 [--include-expired] [--now YYYY-MM-DD] [--json]
memory_recall.py --demo
```
Markdown output (default): header
`## Recalled memory (<n> facts, <chars> chars, query: <terms joined by space>)`, then per
fact: `### [<slug>] <name> — <type>/<confidence>, verified <last_verified>` with
` — STALE, verify before relying` appended to the header line when stale, then the body,
then the trailing budget/withheld lines as applicable (withheld expired facts → one line:
`(<n> expired fact(s) withheld — memory_store.py review to prune)`). `--json` emits
`{"schema_version": 1, "query": [...], "facts": [{"slug","name","type","confidence","state",
"score","chars","body"}...], "dropped_for_budget": n, "withheld_expired": n, "notes": [...]}`
with scores rounded to 4 decimals.

**`--demo` (pinned, byte-stable):** inside its own temp dir, write six synthetic facts with
FIXED dates (create them via direct `render_fact` writes or `ms.main add` calls with
`--now` pinned per fact), then run the pinned query TWICE against `--now 2026-01-15`,
labeling the two runs:

1. `editor-prefs` — user/high, created+verified `2026-01-10` (fresh; irrelevant to the query),
   tags `editor, formatting`.
2. `deploy-target` — reference/high, created+verified `2026-01-10` (fresh), tags
   `deploy, cloudflare`, body mentioning Cloudflare Workers.
3. `legacy-build-flow` — project/medium, created+verified `2025-09-01` (stale: >90d), tags
   `build, deploy`, body about the old build/deploy steps.
4. `deprecated-endpoint` — reference/low, `expires: 2025-12-31` (expired), tags
   `deploy, api`.
5. `favorite-color` — user/high, fresh, tags `preference`, body unrelated.
6. `test-runner-choice` — project/high, fresh, tags `tests, unittest`, body unrelated.

Query: `deploy the build to cloudflare workers`. Run A (defaults) must show `deploy-target`
first, `legacy-build-flow` second WITH the stale marker, the expired-withheld line, and the
irrelevant facts absent (gate). Run B (`--max-facts 1`) must show only `deploy-target` plus
the `+1 more` budget line. Print a one-line header noting everything is synthetic and in a
temp dir. Two consecutive `--demo` runs must be byte-identical.

**Tests** (temp `--memory-dir`, explicit `--now`, in-process `main` calls; SAFETY CONTRACT
docstring as in T1): REQUIRED named tests `test_irrelevant_query_recalls_nothing` (a store
with facts, a query about none of them → `GATE_EMPTY_LINE`, exit 0),
`test_expired_withheld_and_stale_marked` (expired absent + counted; stale present, marked,
and scored below an otherwise-identical fresh fact), `test_budget_truncates_whole_facts`
(a fact that would overflow `--budget-chars` is dropped entirely with the `+N more` line;
no partial body ever emitted). Plus: gate tag-exception (single-term query matching an exact
tag surfaces the fact); ordering tie-breakers (equal scores → fresher `last_verified` first,
then slug); `--json` shape; missing store dir; determinism (`--demo` twice, byte-equal, via
the sanctioned `sys.executable` self-invocation); constants present with pinned values.

**Acceptance.**
- Engine reuses `memory_store` via importlib (no schema re-implementation); pinned
  constants/values exact; gate/budget/staleness behaviors exactly as pinned.
- `python3 bin/memory_recall.py --demo` output matches the pinned demo structure and is
  byte-stable across two runs.
- `grep -n "Path.home\|subprocess" bin/memory_recall.py` → no matches.
- The three REQUIRED named tests exist and pass; verify green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_memory_recall.py' -v && python3 bin/memory_recall.py --demo
```

---

## Phase 3 — Integration

### T5 — `skills/memory/SKILL.md`
- status: done
- model: sonnet
- depends: T4
- independent: no

**Brief.** Create `skills/memory/SKILL.md` — the ONE sanctioned addition under `skills/`
(nothing else under `skills/` changes; the plugin is LIVE, so this file is runtime behavior).
Read first: `skills/journal/SKILL.md` end-to-end (house structure, tone, the root-resolution
preamble, the privacy-section precedent) and PLAN.md D4/D6/D8/D9. The engines' real argparse
surfaces are authoritative — read `main()` of both `bin/memory_store.py` and
`bin/memory_recall.py` and quote only flags that exist.

Frontmatter (house format):
- `name: memory`
- `description:` one sentence with triggers, e.g.: Remember durable facts across sessions and
  recall only the few relevant ones under a strict budget — never bulk-injected. Use when the
  user says "remember this", asks "what do you remember about…", wants a preference or
  decision saved, or when a stored fact would materially help the current task.
- `allowed-tools: Bash, Read, Write`

Body sections (journal-skill voice; ~80–130 lines):

1. **Root preamble** — copy the journal skill's `${CLAUDE_PLUGIN_ROOT}`/`$ROOT` paragraph
   pattern verbatim in structure.
2. **Recall (the default operation — pull, on demand).** Derive 5–15 salient keywords from
   the task at hand (nouns, tool names, file names, error strings — never a whole prompt);
   run `python3 "$ROOT/bin/memory_recall.py" --query "<keywords>"`. Treat the returned block
   as advisory context. A fact marked `STALE — verify before relying` must be re-checked
   against the repo or reality before you act on it. `no memory above the relevance gate` is
   a SUCCESS — proceed without memory; do not loosen the query to force a match. Flags:
   `--max-facts` / `--budget-chars` to tighten further, `--json` for scripting.
3. **The effectiveness contract** — include this paragraph verbatim:

   > Memory must never make answers worse. Never bulk-inject: do not paste `memory/index.md`,
   > the store directory, or uncapped fact sets into context — recall goes through
   > `bin/memory_recall.py` and its budget (at most 5 facts / 4000 chars by default), always.
   > Expired facts are withheld, stale facts arrive down-ranked and flagged, and an empty
   > recall is the system working as designed.

4. **Save.** What is worth remembering: durable user preferences, decisions plus their
   rationale, environment facts, corrections the user gave. What is NOT: anything the repo or
   CLAUDE.md already records, secrets/credentials, transient state. Command:
   `python3 "$ROOT/bin/memory_store.py" add --name "..." --type <user|feedback|project|reference|decision> --description "..." --tags a,b --body "..."`.
   Always set meaningful `--tags` — they are the retrieval hooks for the lexical ranker. Exit
   code 2 with `duplicate of [<slug>]` means UPDATE that fact instead
   (`memory_store.py update <slug> ...`) — update over duplicate, always. A fact the user says
   is wrong: `remove <slug>` immediately.
5. **Review & prune.** Periodically (or when the user asks "what do you remember"):
   `python3 "$ROOT/bin/memory_store.py" review` — then `verify <slug>` for facts that still
   hold, `update` for drifted ones, `remove` for dead ones. `list` shows everything with
   freshness states.
6. **Privacy.** The store lives under the gitignored `memory/` directory at the plugin root —
   local-only, never committed, and it holds only what the user chose to remember. Recalled
   text enters the model's context (that is its purpose); nothing else in the store does.

**Acceptance.**
- File exists in house format; every quoted flag exists on the real argparse surfaces; the
  effectiveness-contract paragraph is present verbatim; the recall section is pull-only (no
  hook, no session-start injection, no "read the index for context" phrasing anywhere).
- `git status --porcelain -- skills` shows ONLY the new `skills/memory/SKILL.md`.
- Verify green (whole suite — the skill can't break it, but this proves the tree).

**Verify.**
```bash
test -f skills/memory/SKILL.md && [ -z "$(git status --porcelain -- skills | grep -v 'skills/memory/')" ] && python3 -m unittest discover -s tests -p 'test_memory_*.py' && echo SKILL-OK
```

---

## Phase 4 — Docs + closeout

### T6 — `docs/MEMORY-SKILL.md`
- status: done
- model: sonnet
- depends: T5
- independent: no

**Brief.** Write the design doc `docs/MEMORY-SKILL.md` (new file; no other `docs/` file
changes), in the voice of the existing kit docs (skim `docs/NEXT-DAY-RUNBOOK.md` for tone
and length — aim for its scale, not a novel). Content, drawn from PLAN.md and the shipped
code (read both engines' docstrings — the doc must match reality, not just the plan):

- What it is: durable store + budget-capped recall inside the plugin; where the store lives
  (gitignored `memory/`; private user data).
- The non-degradation design, one subsection per failure mode: context bloat (pull-only,
  script-computed, MAX_FACTS/BUDGET_CHARS caps, whole-fact truncation), staleness (typed
  TTLs, three states, expired withheld, stale flagged, verify/review flow), noise (the gate,
  and why empty recall is success).
- The schema (fact file example + field meanings) and the index as a derived artifact.
- The ranking algorithm in one paragraph (lexical BM25-lite, field weights, multipliers,
  tie-breakers) with its stated limitation (synonyms) and the mitigation (tags + keyword
  queries).
- How to use it day-to-day (mirror the skill's recall/save/review commands).
- Deferred by design: hooks/auto-injection, cross-harness (copilot/codex) parity — a
  possible future kit mirroring `harness-parity` — model-assisted re-ranking, and any
  embedding/vector approach.

**Acceptance.** Doc exists; every command/flag/constant it quotes matches the shipped code;
no price or model id; `git status --porcelain -- docs` shows only the new file.

**Verify.**
```bash
test -f docs/MEMORY-SKILL.md && [ -z "$(git status --porcelain -- docs | grep -v 'docs/MEMORY-SKILL.md')" ] && echo DOC-OK
```

### T7 — Full-suite + frozen-surface audit
- status: done
- model: haiku
- depends: T2, T6
- independent: no

**Brief.** Final gate. Run and report, in order (each command's ACTUAL output verbatim):

1. `python3 -m unittest discover -s tests -v` — fully green.
2. `python3 bin/memory_recall.py --demo > /tmp/demo1.txt && python3 bin/memory_recall.py --demo > /tmp/demo2.txt && diff /tmp/demo1.txt /tmp/demo2.txt && echo DEMO-STABLE` — must print `DEMO-STABLE`.
3. `git check-ignore -q memory/facts/probe.md && echo IGNORED; git check-ignore -q skills/memory/SKILL.md || echo SKILL-NOT-IGNORED` — both lines.
4. `git diff --quiet -- data .claude-plugin copilot codex README.md && echo FROZEN-CLEAN` — must print `FROZEN-CLEAN`; additionally `git status --porcelain -- skills docs bin tests` must list ONLY the new files (`skills/memory/SKILL.md`, `docs/MEMORY-SKILL.md`, `bin/memory_store.py`, `bin/memory_recall.py`, `tests/test_memory_store.py`, `tests/test_memory_recall.py`).
5. Leak sweeps (each must produce NO matches):
   - `grep -n "Path.home" bin/memory_store.py bin/memory_recall.py tests/test_memory_store.py tests/test_memory_recall.py`
   - `grep -n "subprocess" bin/memory_store.py bin/memory_recall.py`
   - `grep -n "urllib\|http.client\|socket" bin/memory_store.py bin/memory_recall.py`
   - `grep -n "import yaml" bin/memory_store.py bin/memory_recall.py tests/test_memory_store.py tests/test_memory_recall.py`
   - `grep -rn "pricing" bin/memory_store.py bin/memory_recall.py skills/memory`
6. `git status --porcelain | grep -E '^\?\? memory/|^.. memory/'` — must be EMPTY (no real
   store was created in the repo during execution).
7. Confirm the two CLAUDE.md pre-made run-lines execute: `python3 bin/memory_recall.py --demo`
   exits 0 and `python3 bin/memory_store.py review` exits 0 (an empty/absent store prints its
   friendly line — that is a pass).

Any failure, unexplained file, or leak-sweep hit means `blocked` with the evidence — do not
fix things yourself.

**Acceptance.** All seven checks pass with outputs shown verbatim.

**Verify.**
```bash
python3 -m unittest discover -s tests -v
```
