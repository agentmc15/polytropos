# TASKS — copilot-docs-center

Repository root: `/path/to/polytropos`.
Run every verify command from that directory. Read this kit's `PLAN.md` before changing files.

Status vocabulary is exactly:
`pending | in-progress | done | blocked`.

Active model preferences were read before this kit was written:

```text
cheap     -> claude-haiku-4.5
mid       -> claude-sonnet-5
strong    -> claude-opus-4.8
frontier  -> gpt-5.6-sol (user pin; model's own tier is strong)
excluded  -> claude-fable-5
```

Every task below uses an exact non-excluded id from that resolution. No execution task is
frontier-shaped, so none is pinned to the frontier slot. The frontier model was reserved for the
architecture pass that produced this kit.

Standing rules for every task:

- Never invoke real `copilot`, `claude`, or `codex`. Commands shown in documentation are examples
  only; tests/builds/verifiers never execute them.
- Never read or write real `~/.copilot`, `~/.claude`, or `~/.codex`.
- Never write outside this repository. New production code is Python stdlib-only.
- Never run pip, npm, Node, `aesop compile`, or network research.
- Treat `data/pricing.copilot.json`, `bin/copilot_pricing.py`, and `bin/copilot_prefs.py` as the
  only numeric/pricing/preference authorities. Reuse them; do not copy their math.
- Do not handcode a live model id, rate, allowance, cached date, or numeric model comparison in
  `copilot-docs/` authored prose, `manifest.json`, or `bin/copilot_docs.py`. Such values may
  appear only in labeled generated blocks/artifacts.
- Do not edit runtime bundle files, pricing files, prefs, installers, drivers, or unrelated docs.
- `AIC-REPORT.md`, `aic-report.html`, `aic-report.json`, and all HTML files are generator-owned.
- If a pinned source path, marker, or anchor is absent, stop and report the discrepancy instead
  of inventing a replacement.

## Phase 1 — Generator foundation

### T1 — Build the manifest and HTML generation core

- id: `docs-generator-foundation`
- title: Build manifest validation and deterministic HTML rendering
- status: done
- model: claude-opus-4.8
- depends: (none)
- independent: no

**Brief.**

Create the non-pricing foundation of a new stdlib-only generator and its unit tests.

**Sanctioned files**

- `bin/copilot_docs.py` (new)
- `tests/test_copilot_docs.py` (new)

**Frozen files**

Everything else. In particular, do not create `copilot-docs/` yet and do not edit any existing
`bin/`, `tests/`, `data/`, `copilot/`, `docs/`, `README.md`, or prefs file.

**Pinned design**

1. Follow the house import/test convention:
   `BIN_DIR = Path(__file__).resolve().parent.parent / "bin"` in tests, and
   `importlib.util.spec_from_file_location` for loading sibling `bin/` modules later.
2. The production CLI will eventually expose `build`, `check`, and `report`; establish the parser
   and pure artifact-planning seams now, but T2 owns pricing/prefs/report behavior. There is no
   public CLI `--root` option. Tests may call pure functions with an explicit temporary root.
3. Manifest schema:
   - top-level string `schema`;
   - `source_sets`: name → list of repo-relative paths or glob patterns;
   - ordered `documents` list;
   - each document has `markdown`, `html`, `title`, `authoring`, and `sources`;
   - `authoring.mode` is `estimated` or `deterministic`;
   - an estimated document also has symbolic `tier` and `input_profile`;
   - paths are relative to `copilot-docs/`; source paths are relative to repo root.
4. Validation rejects: absolute paths, any `..` component, duplicate Markdown/HTML paths,
   a Markdown path not ending `.md`, an HTML path not ending `.html`, missing title, unknown
   authoring mode, malformed source-set references, paths outside the docs root, and undeclared
   Markdown/HTML files when live-tree checking is enabled.
5. Generated markers are exactly:
   `<!-- BEGIN GENERATED: <name> -->` and
   `<!-- END GENERATED: <name> -->`.
   Replacement is pure and deterministic. Missing, duplicate, nested, reversed, or mismatched
   markers are hard errors; never append a missing block.
6. Implement a bounded Markdown renderer, not full CommonMark. It must support:
   - H1–H4 headings with stable unique ids;
   - paragraphs;
   - inline code, emphasis, strong text, and Markdown links;
   - fenced code blocks with escaped content;
   - blockquotes rendered as callouts;
   - simple ordered/unordered lists;
   - simple pipe tables;
   - HTML escaping everywhere.
   Unsupported raw HTML and ambiguous/nested constructs must fail clearly rather than render
   silently.
7. The HTML shell must be accessible and offline:
   `<!DOCTYPE html>`, language, UTF-8, viewport, title, skip link, navigation placeholder,
   `<main>`, companion Markdown link, and relative `assets/style.css`; no JavaScript or external
   resource.
8. When a Markdown link targets another document declared in the manifest, rewrite it to that
   document's HTML path. Preserve non-document repo links and anchors.
9. Implement pure artifact planning as a mapping of repo-relative output path to exact bytes.
   A writer may create/replace only paths under `copilot-docs/`. A checker compares expected
   bytes without writing and returns/report stale or missing paths.
10. No wall clock, random values, subprocess, shell, network module, `Path.home()`, or implicit
    current-directory path logic.

**Tests to create in `tests/test_copilot_docs.py`**

- valid minimal manifest round-trip;
- each validation failure above, including traversal;
- marker replacement success and every malformed-marker failure;
- stable heading ids with duplicate headings;
- escaping of code/text/links;
- each supported block type;
- rejection of raw HTML/unsupported nesting;
- manifest-link rewrite and preservation of external/repo links;
- deterministic bytes across two identical temp trees;
- writer scope rejection outside the temp docs root;
- checker is read-only by before/after byte snapshot;
- static safety assertion that the module has no process/network/home primitive.

Do not add pricing, prefs, source hashes, or AIC calculations in this task.

**Acceptance.**

- Both new files exist and are stdlib-only.
- All pinned validation, marker, renderer, link, determinism, and write-scope tests pass.
- The test suite never creates or reads a real user home and never launches a process.
- No pre-existing file changed.

**Verify.**

```bash
python3 -m unittest discover -s tests -p 'test_copilot_docs.py' -v
```

### T2 — Add source snapshots and exact AIC reporting

- id: `docs-aic-accounting`
- title: Add pricing reuse, preference snapshots, drift detection, and AIC reports
- status: done
- model: claude-opus-4.8
- depends: T1
- independent: no

**Brief.**

Extend the T1 generator and tests with all data-derived blocks, source freshness, preference
handling, and per-document AIC accounting. There is still no live `copilot-docs/` tree in this
task; prove behavior with temporary fixtures.

**Sanctioned files**

- `bin/copilot_docs.py`
- `tests/test_copilot_docs.py`

**Frozen files**

Everything else, especially `data/pricing.copilot.json`, `bin/copilot_pricing.py`,
`bin/copilot_prefs.py`, `prefs/`, `copilot/`, and all existing docs/tests.

**Authoritative reusable logic**

- `copilot_pricing.load_pricing()` loads the pricing file.
- `copilot_pricing.est_cost(pricing, profile, model_id, cache_hit=<engine default>, today=None)`
  owns the complete USD/AIC formula, long-context choice, promo warning, cache treatment, and
  `billing_unit.usd_per_credit` conversion.
- `copilot_prefs.effective_prefs(...)` and `copilot_prefs.resolve_tier(...)` own pins/excludes.
- Load both through the house importlib-by-path pattern. Do not import `bin` as a package.

**Pinned behavior**

1. Resolve every manifest source set deterministically (sorted files, repo-contained only).
   Compute SHA-256 for:
   - exact pricing bytes;
   - ordered roster-relevant pricing data;
   - each source file and the combined source set.
2. `build` reads active repository prefs through `effective_prefs`, resolves every used tier,
   and records `source`, `pins`, `excludes`, `resolved`, `resolved_via`, and `notes`.
   Normalize an in-repo prefs source to a repo-relative path; never serialize a machine-specific
   absolute path. A used tier resolving to `None`, or a selected model appearing in excludes, is
   a hard error.
3. `check` must not read machine-local active prefs. It loads the recorded effective snapshot
   from `copilot-docs/aic-report.json`, validates every recorded id against current pricing,
   reconstructs equivalent prefs in memory, and generates expected bytes. Pricing/roster/source
   hashes are compared to current repo files, so drift fails even though personal prefs do not
   make CI nondeterministic.
4. `report` is read-only, uses current active prefs, and prints the human-readable prospective
   report to stdout without changing files.
5. Generated block providers:
   - `skills-inventory`: discover every `copilot/.github/skills/*/SKILL.md`, parse `name` and
     one-line `description`, and render a source-path table;
   - `agents-inventory`: discover every `*.agent.md`, parse `name`, `description`, and configured
     `model`; derive configured tier from pricing; label whether the configured model is excluded
     and whether it matches the active resolution for its tier;
   - `model-preferences`: active pins, excludes, tier resolutions, cross-tier notes;
   - `model-roster`: every pricing model in file order, with display, vendor, tier, base rates,
     optional promo/long-context facts, notes/task fit, and preference eligibility;
   - `reasoning-knobs`: render `pricing["knobs"]` without an authored ladder;
   - `task-profiles`: render profile labels and token counts from pricing.
6. Every generated block begins with a visible snapshot line naming
   `data/pricing.copilot.json`, its runtime `cached_date`, pricing hash, and roster digest.
7. Measurement:
   - whole-file UTF-8 bytes;
   - Unicode words;
   - lexical units from regex semantics “Unicode word run OR standalone non-whitespace
     punctuation/symbol”;
   - authored Markdown `ai_output_lexemes` excludes generated-marker bodies.
8. Cost:
   - resolve the document tier through prefs;
   - read input tokens from the manifest profile in `pricing["task_profiles"]`;
   - copy pricing in memory and add one ephemeral profile using those input tokens and
     `ai_output_lexemes` as output tokens;
   - call `copilot_pricing.est_cost`;
   - pass `today=date.fromisoformat(pricing["cached_date"])`, never the wall clock, so promo
     warnings are deterministic and tied to the labeled pricing snapshot;
   - record resolved model id/display/vendor/tier, symbolic profile and runtime profile label,
     assumed input tokens, measured output approximation, engine cache assumption, `rates_used`,
     warnings, USD, AIC, and uncertainty text.
   There must be no duplicated rate formula in this module.
9. Report rows:
   - one distinct row for every manifest Markdown and HTML document;
   - estimated Markdown gets prospective authoring cost;
   - deterministic Markdown gets zero;
   - every HTML row has zero authoring/render AIC and points to its Markdown source;
   - totals include estimated Markdown only;
   - `AIC-REPORT.md` and `aic-report.html` self rows are zero with measured-size fields set to
     `null`/`n/a` and an explicit self-reference note.
10. Generated outputs:
    - `copilot-docs/aic-report.json` is the machine authority;
    - `copilot-docs/AIC-REPORT.md` renders it;
    - `copilot-docs/aic-report.html` is deterministic HTML rendered from that Markdown.
11. No generated timestamp. Snapshot identity comes from pricing `cached_date` and hashes, keeping
    output byte-stable.

**Tests to add**

- use only fake model ids/rates/prefs in arithmetic tests;
- monkeypatch/wrap `copilot_pricing.est_cost` and prove the generator calls it;
- mutate fake rates and billing unit and prove report values follow the engine;
- pin wins, exclude skips, cross-tier note preserved, excluded selection rejected;
- `check` ignores a different local prefs fixture but fails on pricing, roster, or source drift;
- inventory add/remove/rename is reflected deterministically;
- live model ids are absent from generator source;
- generated block provenance labels exist;
- Markdown and HTML rows are separate; HTML/report artifacts are zero and totals do not
  double-count;
- `report` and `check` are read-only by byte snapshot.

**Acceptance.**

- T1 tests remain green and new accounting/drift tests pass.
- No formula, rate, model id, cached date, or allowance is copied into the generator.
- No production/test path touches a real home or launches a process.
- No pre-existing file outside the two sanctioned files changed.

**Verify.**

```bash
python3 -m unittest discover -s tests -p 'test_copilot_docs.py' -v
```

## Phase 2 — Documentation center

### T3a — Add canonical authored-Markdown integration

- id: `docs-authored-markdown-integration`
- title: Preserve authored Markdown while generating blocks, HTML, and reports
- status: done
- model: claude-opus-4.8
- depends: T2
- independent: no

**Brief.**

Close the Phase 1 implementation gap discovered when the original T3 dispatch was blocked:
`plan_artifacts()` currently synthesizes stub Markdown for every manifest document, but PLAN
sections “Canonical content” and D1 require Markdown to be the canonical human-authored source.
Extend the generator so later documentation tasks can author real Markdown while `build` and
`check` deterministically own only generated marker bodies, HTML, CSS, and report artifacts.

**Sanctioned files**

- `bin/copilot_docs.py`
- `tests/test_copilot_docs.py`

**Frozen files**

Everything else. In particular, do not create `copilot-docs/`, do not edit pricing/prefs/runtime
bundle files, and do not change existing docs or README.

**Pinned behavior**

1. For every non-report manifest document, read its canonical Markdown from
   `<repo-root>/copilot-docs/<markdown path>`. A missing canonical source is a clear hard error.
2. Preserve all authored bytes outside generated marker bodies. Never replace an authored
   document with a title/tier/profile stub.
3. Apply generated block providers only to marker names actually present in the document. Every
   present marker must have a known provider; unknown markers are hard errors. A provider that is
   not used by a document is not an error.
4. Keep the existing strict marker validation: missing pairs, duplicates, nesting, reversal, and
   mismatches fail rather than append or repair content.
5. Render HTML from the post-splice Markdown bytes, using the existing bounded renderer and link
   rewriting.
6. AIC measurement and estimation use the same post-splice Markdown, while
   `ai_output_lexemes` continues to exclude generated marker bodies.
7. `build` may write changed generated marker bodies back into canonical Markdown, but otherwise
   preserves authored content byte-for-byte. `check` computes the same expected bytes in memory
   and writes nothing.
8. `AIC-REPORT.md`, `aic-report.html`, and `aic-report.json` remain wholly generator-owned and
   keep their existing self-reference semantics.
9. Pure functions retain explicit temporary-root seams for tests. The production CLI remains
   fixed to the repository `copilot-docs/` root with no public path override.
10. Do not broaden the Markdown subset or duplicate pricing/prefs logic.

**Tests to add**

- canonical authored Markdown survives planning unchanged when it has no generated markers;
- text before and after a generated block is byte-preserved while only the body changes;
- multiple known blocks splice deterministically;
- unknown, malformed, duplicated, nested, reversed, and mismatched markers fail;
- missing canonical Markdown fails clearly;
- HTML is rendered from the post-splice Markdown;
- AIC measurement uses post-splice Markdown and excludes generated bodies from AI output;
- writer updates only generated bodies plus generator-owned outputs;
- checker detects stale generated bodies/HTML and remains read-only;
- production parser still exposes no root/manifest path override;
- all existing 90 generator/accounting tests remain green.

**Acceptance.**

- The generator implements PLAN’s canonical-Markdown architecture rather than synthesizing stubs.
- Authored content is preserved, known generated blocks refresh deterministically, and unknown or
  malformed markers fail closed.
- HTML and AIC reporting consume the same post-splice Markdown.
- No file outside the two sanctioned files changes.

**Verify.**

```bash
python3 -m unittest discover -s tests -p 'test_copilot_docs.py' -v
```

### T3 — Create the landing, install, and safety shell

- id: `docs-center-shell`
- title: Create the documentation center shell and first rendered artifacts
- status: done
- model: claude-sonnet-5
- depends: T3a
- independent: no

**Brief.**

Create the top-level docs center, initial manifest, shared styling, three authored guides, and the
first generated report/HTML set.

**Sanctioned files**

- `copilot-docs/manifest.json`
- `copilot-docs/assets/style.css`
- `copilot-docs/README.md`
- `copilot-docs/INSTALL.md`
- `copilot-docs/SAFETY.md`
- generator-owned outputs under `copilot-docs/`:
  `index.html`, `install.html`, `safety.html`, `AIC-REPORT.md`,
  `aic-report.html`, `aic-report.json`

**Frozen files**

All files outside `copilot-docs/`, including `bin/copilot_docs.py` and tests, plus any
`copilot-docs/` path not named above. T3a is the only task that may repair the canonical-Markdown
generator seam; if that seam is still missing, stop rather than widening this task.

**Manifest**

Use string schema `copilot-docs`. Declare source sets for:

- pricing: `data/pricing.copilot.json`, `bin/copilot_pricing.py`, `bin/copilot_prefs.py`;
- installer: `bin/harness_select.py`;
- skills: `copilot/.github/skills/*/SKILL.md`;
- agents: `copilot/.github/agents/*.agent.md`;
- bundle: `copilot/.github/copilot-instructions.md`, `copilot/aesop.yaml`;
- `existing-guides`: `README.md`, `docs/COPILOT-HARNESS.md`,
  `docs/COPILOT-WORKFLOW.md`, `docs/COPILOT-PARITY.md`,
  `docs/COPILOT-COSTVIZ.md`, `docs/EFFORT-DIAL.md`,
  `docs/DAILY-JOURNAL.md`, `docs/how-it-works.html`.

Initial ordered document entries:

1. `README.md` → `index.html`, estimated, tier `mid`, profile `S`;
2. `INSTALL.md` → `install.html`, estimated, tier `mid`, profile `S`;
3. `SAFETY.md` → `safety.html`, estimated, tier `mid`, profile `S`;
4. `AIC-REPORT.md` → `aic-report.html`, deterministic.

**Shared HTML style**

Adapt the visual conventions of `docs/how-it-works.html` without copying model-specific color
names: warm neutral background, dark readable text, serif body, monospace code, bordered tables,
callout, responsive width/tables, visible focus states, print-friendly behavior, and generic
`.tier-cheap/.tier-mid/.tier-strong/.tier-frontier` accents. No external resource.

**`README.md` required sections**

- H1 identifying this as the GitHub Copilot CLI documentation center;
- “Start here” quick path;
- “Choose a guide” table;
- “Skills versus agents” callout with the exact honesty:
  skills can be explicitly requested with `/name` in a prompt and can auto-load, but this is not
  a true custom slash-command registry; agents are isolated personas;
- “Cost labels” explaining estimated document AIC versus usage history;
- “Sources and freshness” pointing to pricing `cached_date`/generated report without copying a
  date or rate;
- links to the Markdown guides and their HTML companions.

**`INSTALL.md` required sections**

- install preview and install commands using only:
  `python3 bin/harness_select.py install --harness copilot --dry-run` and the real install form;
- optional `--copilot-home <dir>` explanation;
- what is copied: agents and skills, with root-placeholder resolution;
- in-session discovery:
  `/skills reload`, `/skills` (manage/toggle), `/skills list`, `/skills info <name>`, `/agent`;
- explicit skill request syntax such as “Use the `/route` skill …”, auto-loading by description,
  and agent one-shot syntax with placeholders only;
- personal-agent precedence/stale installed copy warning;
- literal-placeholder troubleshooting and reinstall guidance;
- no claim that `/route` is a native user-defined command.

**`SAFETY.md` required sections**

- which documented operations can spend AIC versus model-free/read-only operations;
- tests/builds/verifiers never invoke any real harness CLI;
- no real home access in this documentation generator/tests;
- prospective document estimates versus historical usage estimates;
- AIC versus Copilot-reported AIU and API-equivalent/proxy honesty;
- direct-agent frontmatter is not rewritten by `prefs/copilot.json`;
- serial kit execution and `independent:` meaning;
- journal privacy and generated-doc provenance;
- a “Stop if” checklist for an uninstalled placeholder, stale pricing, excluded configured pin,
  or an unsafe verify command.

Do not put live model ids, prices, allowances, dates, or reasoning-ladder values in authored
prose. Run `python3 bin/copilot_docs.py build` only after all source files/markers are valid.

**Acceptance.**

- Exactly the listed initial docs exist and all HTML/report artifacts are generator output.
- The three Markdown guides contain all required sections and links.
- HTML is styled, navigable, offline, and linked to Markdown companions.
- `aic-report.json` records the active prefs from the repo and selects no excluded model.
- Generator check and generator unit tests pass.

**Verify.**

```bash
python3 bin/copilot_docs.py check && python3 -c 'from pathlib import Path; req=["copilot-docs/README.md","copilot-docs/index.html","copilot-docs/INSTALL.md","copilot-docs/install.html","copilot-docs/SAFETY.md","copilot-docs/safety.html","copilot-docs/AIC-REPORT.md","copilot-docs/aic-report.html","copilot-docs/aic-report.json","copilot-docs/manifest.json","copilot-docs/assets/style.css"]; missing=[p for p in req if not Path(p).is_file()]; assert not missing, missing' && python3 -m unittest discover -s tests -p 'test_copilot_docs.py' -v
```

### T4 — Write the complete skills and agents references

- id: `docs-skill-agent-reference`
- title: Document every current Copilot skill and custom agent
- status: done
- model: claude-opus-4.8
- depends: T3
- independent: no

**Brief.**

Add the two comprehensive reference guides, their manifest entries, generated inventories, HTML,
and refreshed AIC report.

**Sanctioned files**

- `copilot-docs/SKILLS.md`
- `copilot-docs/AGENTS.md`
- `copilot-docs/manifest.json`
- all generator-owned `copilot-docs/*.html`
- `copilot-docs/AIC-REPORT.md`
- `copilot-docs/aic-report.json`
- `bin/copilot_docs.py`, only for the demonstrated generated-description placeholder escaping fix
- `tests/test_copilot_docs.py`, only for its focused regression test

**Frozen files**

- Existing authored `copilot-docs/README.md`, `INSTALL.md`, `SAFETY.md`, and CSS;
- everything outside `copilot-docs/` except the two narrowly sanctioned generator/test files.

Generated HTML navigation may change mechanically because the manifest gains documents. Do not
hand-edit any HTML.

The prior dispatch exposed one generator defect: real skill descriptions contain angle-bracket
placeholders such as `<slug>`, and generated inventory tables must render those as safe inline
code rather than raw HTML. Fix only that generated-cell escaping seam and add a regression proving
the real shape renders safely. Do not weaken the authored-Markdown raw-HTML rejection.

**Manifest additions**

- `SKILLS.md` → `skills.html`, estimated, tier `strong`, profile `M`,
  sources `skills`, `bundle`, `installer`, `pricing`;
- `AGENTS.md` → `agents.html`, estimated, tier `strong`, profile `M`,
  sources `agents`, `bundle`, `installer`, `pricing`.

Place both before the deterministic AIC report entry.

**`SKILLS.md`**

Start with:

- what a skill is;
- explicit `/name`-in-prompt request versus auto-loading from `description:`;
- skills run on the current session model and carry no `model:` pin;
- `/skills reload`, `/skills`, `/skills list`, `/skills info <name>`;
- “not true custom slash commands” honesty.

Include one `skills-inventory` generated marker block.

Then include exactly one H2 section for each current disk skill (heading is the bare name):

- `architect`: plans only; writes `tasks/kits/<slug>/PLAN.md` and `TASKS.md`; never creates
  `NOTES.md`; checks prefs before task pins; skill quality follows the current session model.
- `effort`: reads `copilot_pricing.py knobs`; teaches the interactive `/model` left/right
  Reasoning control; no confirmed headless flag; step up only on evidence.
- `escalate`: one task; requires a machine-checkable condition; retry once then climb tiers;
  frontier last; kit tasks should use the execute driver.
- `execute`: drives `copilot_execute.py status/run/review`; task model overrides implementer
  frontmatter by kit contract; serial only; dry-run before real spend; there is no execute agent.
- `frontier-check`: compare frontier/strong/mid at runtime; use strong first unless genuine
  frontier evidence; honor pins/excludes and data notes.
- `journal`: collect locally, then use `journal_summarize.py --dry-run` and write in-session;
  never launch the headless Claude summarizer from Copilot.
- `lessons-loop`: read `tasks/lessons.md` at session start; append concise project-scoped lessons
  after human corrections or model escalations; no same-named agent.
- `route`: read routing lessons and prefs; classify tier, estimate with the pricing engine,
  recommend one action; decision aid, not usage history.
- `usage`: read-only historical reporter over Copilot session text logs; never invoke Copilot or
  open SQLite; explain multi-model approximation and AIU/AIC distinction.

Every skill section must contain: when to use, how to request it, what it does, key safety/cost
notes, and whether a same-named agent exists. Commands use placeholders, never live ids.

**`AGENTS.md`**

Start with:

- agents are persona-isolated surfaces chosen via `/agent` or one-shot CLI;
- frontmatter can pin a model;
- the execute driver may pass a task model;
- active repo prefs do not rewrite agent frontmatter;
- user-home agents shadow same-named repo agents;
- internal workflow agents are usually driver-dispatched.

Include one `agents-inventory` generated marker block. It must show configured model/tier and
preference eligibility from disk/data, with any excluded configured pin clearly flagged as
“do not dispatch blindly,” not recommended.

Then include exactly one H2 section for each current disk agent:

- `architect`: isolated kit planner; no implementation; direct pin/prefs caveat.
- `effort`: isolated reasoning-dial advisor.
- `escalate`: isolated one-task verify-gated ladder.
- `frontier-check`: isolated frontier-worth judgment.
- `implementer`: executes exactly one kit brief, runs its verify, never writes status/NOTES,
  normally driver-dispatched.
- `journal`: isolated daily journal persona, in-session/dry-run safety.
- `reviewer`: read-only phase-boundary drift/fence reviewer; strong judgment role.
- `route`: isolated routing/cost advisor.
- `usage`: cheap read-only usage reporter.
- `verifier`: fresh-context adversarial rerun of one task; no fixes/status writes.

Close with a comparison table covering skill-only names (`execute`, `lessons-loop`) and
agent-only workflow roles (`implementer`, `reviewer`, `verifier`).

**Acceptance.**

- Manifest entries, Markdown, HTML, inventories, and report all regenerate cleanly.
- Disk-discovered skill and agent sets equal the H2 sets exactly.
- Every item has individual coverage with the pinned distinctions.
- Excluded configured pins are disclosures only; no excluded model is selected/recommended.
- No live model id or numeric model fact appears outside generated blocks.

**Verify.**

```bash
python3 bin/copilot_docs.py check && python3 -c 'from pathlib import Path; skills={p.parent.name for p in Path("copilot/.github/skills").glob("*/SKILL.md")}; agents={p.name[:-len(".agent.md")] for p in Path("copilot/.github/agents").glob("*.agent.md")}; sh={line[3:].strip() for line in Path("copilot-docs/SKILLS.md").read_text().splitlines() if line.startswith("## ")}; ah={line[3:].strip() for line in Path("copilot-docs/AGENTS.md").read_text().splitlines() if line.startswith("## ")}; assert skills==sh,(skills,sh); assert agents==ah,(agents,ah)' && python3 -m unittest discover -s tests -p 'test_copilot_docs.py' -v
```

### T5 — Write the model and cost guides

- id: `docs-model-cost-guides`
- title: Document model differences and honest AIC accounting
- status: done
- model: claude-opus-4.8
- depends: T4
- independent: no

**Brief.**

Add the model guide and cost guide. All mutable model/numeric facts must be generated from the
pricing data and active preference snapshot.

**Sanctioned files**

- `copilot-docs/MODELS.md`
- `copilot-docs/COSTS.md`
- `copilot-docs/manifest.json`
- all generator-owned `copilot-docs/*.html`
- `copilot-docs/AIC-REPORT.md`
- `copilot-docs/aic-report.json`

**Frozen files**

- All existing authored `copilot-docs/*.md` except the two new files and generator-owned
  `AIC-REPORT.md`;
- `copilot-docs/assets/style.css`;
- everything outside `copilot-docs/`.

**Manifest additions**

- `MODELS.md` → `models.html`, estimated, tier `strong`, profile `M`,
  sources `pricing`, `agents`, `bundle`;
- `COSTS.md` → `costs.html`, estimated, tier `strong`, profile `M`,
  sources `pricing`, `existing-guides`.

Place both before the deterministic report entry.

**`MODELS.md` required structure**

1. Explain that vendor, tier, model ids, prices, notes, promo/long-context facts, and reasoning
   vocabulary are data, not prose.
2. Generated block `model-preferences`.
3. Explain tier resolution, pins/excludes, and cross-tier overrides without naming a live model
   in authored text. State that excluded rows are informational only and ineligible for
   recommendations.
4. Generated block `model-roster`.
5. Interpret tiers and task fit using generic tier language; the row notes are the runtime task-fit
   authority.
6. Generated block `reasoning-knobs`.
7. Explain reasoning is per-model and interactive in `/model`; rows without control are identified
   by the generated data note; no headless flag/settings key is confirmed.
8. Generated block `task-profiles`.
9. Show runtime commands:
   `python3 bin/copilot_pricing.py prefs`,
   `models --json`, `models --profile <PROFILE>`,
   `est <PROFILE> <MODEL_ID>`, and `knobs`.
10. Explain pricing/AIC implications: output/reasoning can dominate, long-context/promo warnings
    come from data/engine, and a tier pin is priced at that model's own rates.
11. Explain refresh/drift: edit pricing only at its source, bump cached date there, rebuild docs,
    run check/tests. Do not instruct editing generated tables.

No live model display name, model id, price, ratio, allowance, date, or reasoning-ladder value may
appear in authored text; generated blocks provide all of them.

**`COSTS.md` required structure**

1. “Three different questions”:
   - prospective task estimate (`copilot_pricing.py est`);
   - historical usage-log estimate (`copilot_usage.py`);
   - prospective per-document authoring estimate (this center).
2. AIC unit/value comes from pricing data; never state a literal conversion in authored prose.
3. Explain pricing engine profile input/output, cached-input behavior, warnings, and runway using
   placeholders only.
4. Historical honesty:
   multi-model session last-model attribution is approximate; per-turn output-only view is the
   exact cross-model slice; missing shutdown details undercount; AIU is not AIC.
5. Proxy honesty:
   API-equivalent or relative-burn figures are not bills and are never merged into billed totals.
6. Exact document accounting policy from PLAN:
   measured bytes/words/lexemes; generated blocks excluded from AI output; assumed input profile;
   prefs-resolved model; existing `est_cost`; Markdown estimate; HTML zero; report artifacts zero;
   totals authored Markdown only; uncertainty.
7. How to regenerate:
   `python3 bin/copilot_docs.py build`, `check`, and `report`.
8. Link to `AIC-REPORT.md`, `aic-report.html`, and `aic-report.json`.

Run `build` and inspect the generated current-preference snapshot. It must reflect the active prefs
file without hand-writing either id.

**Acceptance.**

- Both guides and HTML companions exist and are complete.
- Generated blocks contain all current model/prefs/knob/profile facts with cached-date/hash labels.
- The report's recorded prefs exactly match the active repo prefs at build time.
- Every selected document model is outside the exclude set.
- No live id/rate/date/ratio appears in generator code, manifest, or authored text outside blocks.

**Verify.**

```bash
python3 bin/copilot_docs.py check && python3 -c 'import json; from pathlib import Path; prefs=json.loads(Path("prefs/copilot.json").read_text()); report=json.loads(Path("copilot-docs/aic-report.json").read_text()); snap=report["inputs"]["prefs"]; assert snap["pins"]==prefs.get("pins",{}),(snap,prefs); assert snap["excludes"]==prefs.get("excludes",[]),(snap,prefs); excluded=set(snap["excludes"]); bad=[r["path"] for r in report["documents"] if r.get("resolved_model_id") in excluded]; assert not bad,bad' && python3 -m unittest discover -s tests -p 'test_copilot_docs.py' -v
```

### T6 — Write the practical workflow guide

- id: `docs-workflows`
- title: Document the end-to-end Copilot operating workflows
- status: done
- model: claude-sonnet-5
- depends: T5
- independent: no

**Brief.**

Add the practical workflow guide, HTML companion, manifest entry, and refreshed report.

**Sanctioned files**

- `copilot-docs/WORKFLOWS.md`
- `copilot-docs/manifest.json`
- all generator-owned `copilot-docs/*.html`
- `copilot-docs/AIC-REPORT.md`
- `copilot-docs/aic-report.json`

**Frozen files**

- Existing authored documentation-center Markdown/CSS;
- everything outside `copilot-docs/`.

**Manifest addition**

`WORKFLOWS.md` → `workflows.html`, estimated, tier `mid`, profile `M`,
sources `skills`, `agents`, `pricing`, `bundle`, `existing-guides`.
Place it before the deterministic report entry.

**Required introduction**

- choose skill versus agent;
- explicit skill request is `/name` inside a prompt, not a custom command;
- agent is isolated and may carry a configured model;
- check active prefs before cost/model decisions;
- dry-run/model-free commands are safe, while real execute/review dispatches spend AIC.

**Exactly seven H2 workflow sections**

1. `Route a task`
   - read lessons/prefs;
   - size to a runtime profile;
   - compare candidates and act;
   - keep recommendation versus usage-report roles separate.
2. `Architect → execute`
   - architect creates only PLAN/TASKS;
   - execute status, dry-run, run, phase review;
   - task model is the driver dispatch pin;
   - serial execution and `independent:` honesty;
   - `NOTES.md` belongs to the driver.
3. `Verify → escalate`
   - machine check first;
   - independent verification;
   - retry once with evidence;
   - climb only after failure; frontier last;
   - stop honestly if the ladder fails.
4. `Usage and cost review`
   - run pricing estimates before work;
   - run usage report after work;
   - interpret approximation, AIU, and proxies;
   - no real CLI is needed to gather existing logs.
5. `Daily journal`
   - deterministic collector;
   - summarizer `--dry-run`;
   - write summaries in-session;
   - metadata/privacy boundary;
   - optional next-day plan as advisory, not dispatch.
6. `Effort and frontier decision`
   - read knob data;
   - interactive `/model` only;
   - increase one step on evidence;
   - distinguish thinking-time gap from capability gap;
   - prefer strong before frontier unless evidence says otherwise.
7. `Lessons loop`
   - load lessons at start;
   - record human corrections and routing escalations;
   - concise project-scoped rule;
   - feed future routing without hardcoded model ids/rankings.

Use safe copy/paste command examples with `<...>` placeholders. For commands that would spend
AIC, label them explicitly and pair them with a dry-run/status/read-only predecessor where one
exists. Do not execute any command while writing this guide.

**Acceptance.**

- Exactly the seven H2 sections above, plus an H1/introduction.
- All required workflows and safety/honesty points are present.
- No custom-slash-command claim, no invented flags, no live model id/numeric fact in authored text.
- HTML/report regenerate and check cleanly.

**Verify.**

```bash
python3 bin/copilot_docs.py check && python3 -c 'from pathlib import Path; text=Path("copilot-docs/WORKFLOWS.md").read_text(); expected=["Route a task","Architect → execute","Verify → escalate","Usage and cost review","Daily journal","Effort and frontier decision","Lessons loop"]; got=[line[3:].strip() for line in text.splitlines() if line.startswith("## ")]; assert got==expected,(got,expected)' && python3 -m unittest discover -s tests -p 'test_copilot_docs.py' -v
```

### T6a — Complete the generated shared stylesheet

- id: `docs-shared-style-repair`
- title: Implement the pinned accessible offline documentation styling
- status: done
- model: claude-sonnet-5
- depends: T6
- independent: no

**Brief.**

Resolve the Phase 2 review finding that T3's rich stylesheet requirement was structurally blocked:
`copilot-docs/assets/style.css` is generator-owned by `DEFAULT_STYLE_CSS`, but T3 froze the
generator. Update the generator-owned stylesheet and focused tests without changing documentation
content or widening the renderer.

**Sanctioned files**

- `bin/copilot_docs.py`, only `DEFAULT_STYLE_CSS`
- `tests/test_copilot_docs.py`, only focused stylesheet regressions
- generator-owned `copilot-docs/assets/style.css` and `copilot-docs/*.html` refreshed by build
- generator-owned AIC report artifacts only if build changes their measured bytes

**Frozen files**

- all authored `copilot-docs/*.md` except generator-owned `AIC-REPORT.md`
- `copilot-docs/manifest.json`
- everything outside the sanctioned generator/test/generated-output paths

**Pinned style contract**

- warm neutral page background and dark readable text;
- serif body copy and monospace code/pre;
- centered responsive content width;
- bordered, readable tables with horizontal overflow on narrow screens;
- visible blockquote/callout treatment;
- visible keyboard focus states;
- responsive navigation and spacing;
- print-friendly rules that remove decorative backgrounds and preserve readable links/tables;
- generic `.tier-cheap`, `.tier-mid`, `.tier-strong`, `.tier-frontier` accents with no
  model-specific class names;
- no JavaScript, external URL, font download, image, analytics, or network dependency.

Adapt the visual conventions of `docs/how-it-works.html` without copying hardcoded model facts.
Run `python3 bin/copilot_docs.py build`; do not hand-edit generated CSS or HTML.

**Acceptance.**

- The generated stylesheet implements every pinned style-contract item.
- HTML remains accessible, offline, deterministic, and linked to Markdown companions.
- Focused tests prove the four tier classes, serif/monospace/table/callout/focus/responsive/print
  rules, and absence of external dependencies.
- Generator check and all generator unit tests pass.

**Verify.**

```bash
python3 bin/copilot_docs.py check && grep -q '\.tier-cheap' copilot-docs/assets/style.css && grep -q '\.tier-mid' copilot-docs/assets/style.css && grep -q '\.tier-strong' copilot-docs/assets/style.css && grep -q '\.tier-frontier' copilot-docs/assets/style.css && grep -q '@media print' copilot-docs/assets/style.css && python3 -m unittest discover -s tests -p 'test_copilot_docs.py' -v
```

## Phase 3 — Enforcement and integration

### T7 — Add live-tree content and drift tests

- id: `docs-content-tests`
- title: Enforce complete coverage, safe wording, links, and generated parity
- status: done
- model: claude-sonnet-5
- depends: T6a
- independent: no

**Brief.**

Create the dedicated live-content regression suite. Fix documentation-center or generator defects
found by these tests, but do not widen scope.

**Sanctioned files**

- `tests/test_copilot_docs_content.py` (new)
- `tests/test_copilot_docs.py` only if a generator seam needs an additional unit regression
- `bin/copilot_docs.py` only for a demonstrated generator defect
- any `copilot-docs/` source/generated file needed to satisfy the pinned content contract

**Frozen files**

Everything else, including all runtime bundle/pricing/prefs/installer/driver files and existing
top-level docs.

**Create `tests/test_copilot_docs_content.py`**

Use stdlib unittest, repo-relative paths from `Path(__file__).resolve().parent.parent`, and no
process/network/home access. It may import `bin/copilot_docs.py` with the house importlib helper
and call its checker in-process.

Required test groups:

1. **Manifest inventory**
   - exact expected Markdown/HTML pairs from PLAN;
   - no undeclared `*.md`/`*.html` under `copilot-docs/`;
   - only `AIC-REPORT.md` is deterministic Markdown;
   - every estimated entry has a live tier/profile symbol.
2. **Skill coverage**
   - discover `copilot/.github/skills/*/SKILL.md`;
   - set equality with bare H2 headings in `SKILLS.md`;
   - required intro says `/name`, auto-load, current session model, and not true custom commands;
   - each section has when/how/safety content.
3. **Agent coverage**
   - discover `*.agent.md`;
   - set equality with bare H2 headings in `AGENTS.md`;
   - intro states persona isolation, `/agent`, frontmatter pin, prefs limitation, precedence;
   - `execute`/`lessons-loop` are not agent H2s; implementer/reviewer/verifier roles present.
4. **Required guide content**
   - installation/discovery commands and placeholder troubleshooting;
   - exact seven workflow headings;
   - cost estimate/actual/proxy/AIU distinctions;
   - safety no-live-CLI/no-real-home/serial-execution statements.
5. **Slash-command honesty**
   - at least one explicit “not true custom slash commands” statement;
   - reject affirmative patterns such as “custom slash command `/route`” or a statement that the
     repo registers native commands.
6. **Generated provenance and prefs**
   - generated blocks have pricing path, runtime cached date, pricing hash, roster digest;
   - report prefs equal the recorded build snapshot;
   - no selected document model is excluded;
   - frontier resolution equals the recorded frontier pin when a pin exists;
   - an excluded configured agent pin, if present, is flagged rather than recommended.
7. **No hardcoded live ids**
   - derive model keys from pricing;
   - assert no key occurs in `bin/copilot_docs.py` or `manifest.json`;
   - strip all generated blocks from authored Markdown and assert no key remains.
8. **AIC report semantics**
   - exactly one row per manifest Markdown and HTML path;
   - authored Markdown nonnegative prospective estimates;
   - HTML/report artifacts zero;
   - HTML points to Markdown;
   - totals equal authored Markdown sum only;
   - measured and assumed fields are separate;
   - pricing cached date/hashes are present.
9. **HTML parity/accessibility**
   - in-process check reports no drift;
   - each HTML title/H1/headings correspond to its Markdown;
   - skip link, nav, main, companion link, stylesheet exist;
   - no script/external URL.
10. **Link validation**
    - parse Markdown links and HTML `href`;
    - every relative local target/anchor exists;
    - generated HTML document links point at HTML companions.
11. **Safety/static scope**
    - generator contains no process/network/home primitive;
    - check leaves a before/after byte snapshot unchanged.

If an existing authored guide lacks a required phrase or link, make the minimum correction and
run `build`. Do not add new guides or new generator features.

**Acceptance.**

- The new content suite covers every pinned group and passes.
- Generator unit tests still pass.
- `check` is green and read-only.
- No file outside the sanctioned set changed.

**Verify.**

```bash
python3 bin/copilot_docs.py check && python3 -m unittest discover -s tests -p 'test_copilot_docs*.py' -v
```

### T8 — Add small discoverability links

- id: `docs-discovery-links`
- title: Link the new center from existing entry points
- status: done
- model: claude-haiku-4.5
- depends: T7
- independent: no

**Brief.**

Make only two small discoverability edits, then rebuild because both files are hashed source
inputs for the documentation center.

**Sanctioned files**

- `README.md`
- `docs/COPILOT-HARNESS.md`
- generator-owned outputs under `copilot-docs/` whose source hash/report/nav changes after rebuild

**Frozen files**

- All other existing docs;
- all authored `copilot-docs/*.md` except generator-owned `AIC-REPORT.md`;
- `copilot-docs/manifest.json`, CSS, generator, tests;
- all runtime/pricing/prefs/bundle files.

**Exact edits**

1. In `README.md`, in the opening documentation-link block near the existing GitHub Copilot
   harness link, add one concise line:
   - label: `Copilot documentation center`;
   - Markdown link to `copilot-docs/README.md`;
   - HTML link to `copilot-docs/index.html`;
   - description: installation, skills, agents, models, workflows, and per-document AIC estimates.
2. In `docs/COPILOT-HARNESS.md`, immediately after the opening description and before the first
   horizontal rule/H2, add one sentence linking:
   - `../copilot-docs/README.md`;
   - `../copilot-docs/index.html`;
   and describing the center as the task-oriented user guide.

Do not revise, correct, or modernize any other existing prose. Run
`python3 bin/copilot_docs.py build` so source hashes and reports update.

**Acceptance.**

- Both exact entry points link to both Markdown and HTML landing pages.
- No other authored content changed.
- Generator check and content tests pass after rebuild.

**Verify.**

```bash
grep -q 'copilot-docs/README.md' README.md && grep -q 'copilot-docs/index.html' README.md && grep -q '../copilot-docs/README.md' docs/COPILOT-HARNESS.md && grep -q '../copilot-docs/index.html' docs/COPILOT-HARNESS.md && python3 bin/copilot_docs.py check && python3 -m unittest discover -s tests -p 'test_copilot_docs*.py' -v
```

## Phase 4 — Final audit

### T9 — Audit the complete center against the plan

- id: `docs-final-audit`
- title: Perform the cross-document, pricing, preference, and safety audit
- status: done
- model: claude-opus-4.8
- depends: T8
- independent: no

**Brief.**

Perform a fresh, adversarial closeout against every PLAN “done” bullet. This task may fix only
documentation-center/generator/test/link defects exposed by the audit; it must not add scope.

**Sanctioned files**

- `copilot-docs/**`
- `bin/copilot_docs.py`
- `tests/test_copilot_docs.py`
- `tests/test_copilot_docs_content.py`
- `README.md` and `docs/COPILOT-HARNESS.md` only if one of the two required links is defective

**Frozen files**

- `data/**`
- `prefs/**`
- `copilot/**`
- `skills/**`
- `codex/**`
- `.claude-plugin/**`
- every `bin/` file except `bin/copilot_docs.py`
- every `tests/` file except the two Copilot-docs tests
- every existing `docs/` file except the single sanctioned link in
  `docs/COPILOT-HARNESS.md`
- all completed kits; no `NOTES.md` creation by this task

**Audit checklist**

1. Re-run active prefs and models through the existing pricing CLI for inspection only; do not
   copy output into authored prose. Confirm every task/doc selected model is non-excluded.
2. Compare disk skill/agent inventories to the guides and generated inventory blocks.
3. Confirm landing/install/skills/agents/models/workflows/costs/safety/report coverage and paired
   HTML.
4. Confirm the direct-agent frontmatter/prefs limitation is clear and the excluded configured
   model is never recommended.
5. Confirm all mutable model/numeric facts are generated and labeled with cached date/hashes.
6. Confirm AIC semantics exactly match PLAN: lexical approximation, assumed profile input,
   existing `est_cost`, prospective label, Markdown/HTML separation, zero deterministic render,
   report self-row, no double count.
7. Confirm no true-custom-slash-command claim, no invented effort flag, and no invented
   orchestration/parallelism.
8. Confirm no real CLI/home/network/process path exists in generator or tests.
9. Confirm local links, HTML accessibility, offline styling, and deterministic bytes.
10. Run targeted tests, full suite, and frozen-file diff.

If any acceptance cannot be proved mechanically, strengthen the two dedicated tests rather than
adding a prose-only assertion.

**Acceptance.**

- Every PLAN done bullet is satisfied.
- Targeted and full suites pass.
- Generator check passes without writing.
- Frozen tracked surfaces have no diff.
- No excluded model is pinned/recommended, and no frontier execution task was introduced.

**Verify.**

```bash
python3 bin/copilot_docs.py check && python3 -m unittest discover -s tests -p 'test_copilot_docs*.py' -v && python3 -m unittest discover -s tests && git diff --exit-code -- data prefs copilot skills codex .claude-plugin bin/copilot_pricing.py bin/copilot_prefs.py bin/harness_select.py bin/copilot_execute.py bin/copilot_usage.py docs/COPILOT-WORKFLOW.md docs/COPILOT-PARITY.md docs/COPILOT-COSTVIZ.md docs/EFFORT-DIAL.md docs/DAILY-JOURNAL.md
```
