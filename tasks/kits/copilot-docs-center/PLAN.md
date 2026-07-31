# PLAN — copilot-docs-center

## Goal

Build a comprehensive top-level `copilot-docs/` documentation center for using this
repository through GitHub Copilot CLI. The center must be useful to a first-time user, accurate
enough for maintainers, available as paired Markdown and styled HTML, explain every currently
installed Copilot skill and custom agent, emphasize model/tier differences, and publish a
mechanically reproducible estimated AIC cost for every Markdown and HTML document.

This kit plans the work only. Execution must not edit the runtime Copilot bundle or its pricing
sources.

## Audience

- **New users** installing the repository's Copilot harness and learning how to discover and
  invoke skills and agents.
- **Working users** choosing models, routing tasks, running execution kits, reviewing usage, and
  using the journal/lessons workflows.
- **Maintainers** updating skills, agents, model data, or documentation without allowing the
  docs, HTML, or AIC report to drift.

## Definition of done

Done is mechanically checkable:

1. The complete file tree below exists, with `README.md`/`index.html` as the landing pair and
   every other user guide present in both Markdown and HTML.
2. The docs accurately distinguish the two Copilot surfaces:
   - skills are instruction bundles that can be explicitly requested with `/name` in a prompt
     and can auto-load when their `description:` matches;
   - agents are persona-isolated surfaces selected with `/agent` or `copilot --agent`;
   - skill `/name` invocation is **not** a true user-defined Copilot slash-command registry.
3. Installation and discovery cover `bin/harness_select.py`, `/skills reload`, `/skills`,
   `/skills list`, `/skills info <name>`, skill auto-loading, agent selection, user-home
   precedence, and the installed-placeholder troubleshooting path.
4. `SKILLS.md` individually covers exactly the skills discovered from disk:
   `architect`, `effort`, `escalate`, `execute`, `frontier-check`, `journal`,
   `lessons-loop`, `route`, and `usage`.
5. `AGENTS.md` individually covers exactly the agents discovered from disk:
   `architect`, `effort`, `escalate`, `frontier-check`, `implementer`, `journal`,
   `reviewer`, `route`, `usage`, and `verifier`.
6. `MODELS.md` derives its roster, vendor, tier, rates, notes/task fit, reasoning-knob facts,
   task profiles, and active preference snapshot from runtime sources. No authored prose or
   generator code hardcodes a live model id, price, allowance, cached date, or ratio.
7. The active preference snapshot used to build the checked-in artifacts honors the current
   repository prefs: the frontier slot resolves to `gpt-5.6-sol` and
   `claude-fable-5` is excluded. Excluded models may appear only as clearly labeled,
   data-derived roster facts; they are never selected, recommended, or pinned by this kit.
8. `WORKFLOWS.md` gives practical, safe procedures for:
   route a task; architect → execute; verify → escalate; usage/cost review; journal;
   effort/frontier choice; and the lessons loop.
9. `COSTS.md` and the generated AIC report distinguish prospective estimates from historical
   usage estimates, Copilot-reported AIU from AIC, and subscription/API-equivalent proxies from
   bills.
10. `bin/copilot_docs.py build` deterministically refreshes generated Markdown blocks, all HTML,
    and the AIC report; `python3 bin/copilot_docs.py check` performs the same work in memory,
    writes nothing, and exits nonzero on drift.
11. `aic-report.json` and `AIC-REPORT.md` contain separate rows for each Markdown and HTML
    document, use the exact accounting policy below, tie generated numeric facts to
    `data/pricing.copilot.json`'s `cached_date`, and never double-count deterministic HTML.
12. Dedicated stdlib-only tests prove generation determinism, pricing-engine reuse, preference
    handling, source/roster drift detection, skill/agent inventory coverage, safe path handling,
    local-link validity, HTML parity, and the no-live-CLI/no-real-home contract.
13. `README.md` and `docs/COPILOT-HARNESS.md` contain small discoverability links to the new
    center. No other existing documentation is rewritten.
14. `python3 -m unittest discover -s tests` and `python3 bin/copilot_docs.py check` pass.

## Proposed complete file tree

```text
copilot-docs/
├── README.md
├── index.html
├── INSTALL.md
├── install.html
├── SKILLS.md
├── skills.html
├── AGENTS.md
├── agents.html
├── MODELS.md
├── models.html
├── WORKFLOWS.md
├── workflows.html
├── COSTS.md
├── costs.html
├── SAFETY.md
├── safety.html
├── AIC-REPORT.md
├── aic-report.html
├── aic-report.json
├── manifest.json
└── assets/
    └── style.css

bin/
└── copilot_docs.py

tests/
├── test_copilot_docs.py
└── test_copilot_docs_content.py

README.md                    # one discoverability link block
docs/COPILOT-HARNESS.md      # one discoverability link
```

`AIC-REPORT.md`, `aic-report.html`, `aic-report.json`, and every HTML file are generator-owned.
The other Markdown files and `manifest.json` are reviewed source material, except for explicitly
marked generated blocks within `SKILLS.md`, `AGENTS.md`, and `MODELS.md`.

## Source-of-truth and generation architecture

### 1. Canonical content

- Markdown is the canonical human-authored format.
- HTML is deterministic output from Markdown; it is never independently authored.
- `manifest.json` is the machine-readable document inventory and policy declaration. It carries
  relative Markdown/HTML paths, titles, authoring mode, symbolic tier, symbolic pricing profile,
  source-set dependencies, and ordering. It carries no live model id or rate.
- Generated Markdown blocks use stable comments:
  `<!-- BEGIN GENERATED: <name> -->` and `<!-- END GENERATED: <name> -->`.
  The generator replaces only the contents between matching markers.

### 2. Read-only source material

The generator and authors read, but never edit:

- `data/pricing.copilot.json`
- `bin/copilot_pricing.py`
- `bin/copilot_prefs.py`
- `bin/harness_select.py`
- `copilot/.github/skills/*/SKILL.md`
- `copilot/.github/agents/*.agent.md`
- `copilot/.github/copilot-instructions.md`
- `copilot/aesop.yaml`
- `README.md`
- `docs/COPILOT-HARNESS.md`
- `docs/COPILOT-WORKFLOW.md`
- `docs/COPILOT-PARITY.md`
- `docs/COPILOT-COSTVIZ.md`
- `docs/EFFORT-DIAL.md`
- `docs/DAILY-JOURNAL.md`
- `docs/how-it-works.html`

The manifest declares source globs/paths. The generator hashes the resolved source set so a
skill, agent, pricing, or relevant-guide change makes `check` fail until the docs are reviewed
and rebuilt.

### 3. One stdlib-only generator

`bin/copilot_docs.py` owns four deterministic jobs:

1. validate the manifest and reject absolute paths, `..` traversal, duplicates, missing pairs,
   unknown tiers/profiles, or writes outside `copilot-docs/`;
2. derive generated skill, agent, model, preference, knob, profile, and source-freshness blocks;
3. render the supported Markdown subset to accessible, offline HTML using only stdlib
   (`html`, `re`, `json`, `hashlib`, `pathlib`, `argparse`, `importlib`, and peers);
4. compute and render the per-document AIC report.

The CLI is:

```bash
python3 bin/copilot_docs.py build
python3 bin/copilot_docs.py check
python3 bin/copilot_docs.py report
```

- `build` uses the active repo prefs, writes only generator-owned files/blocks under
  `copilot-docs/`, and records the effective preference snapshot. A prefs source inside the repo
  is serialized as a repo-relative path (for the default, `prefs/copilot.json`), never as a
  machine-specific absolute path.
- `check` is read-only. It reproduces expected artifacts in memory from the recorded snapshot,
  compares bytes, and also checks current pricing/source hashes. This keeps CI deterministic
  even when another machine has no personal `prefs/copilot.json`.
- `report` uses the currently active prefs and prints a prospective report without writing,
  allowing another user to see personalized document estimates.

Tests call pure functions with temporary roots and synthetic pricing/prefs; the production CLI
has no `--root` escape hatch.

### 4. Reuse, never reimplement, Copilot pricing

The generator loads `bin/copilot_pricing.py` and `bin/copilot_prefs.py` through the repository's
existing `importlib.util.spec_from_file_location` convention.

For each authored Markdown document it:

1. resolves the manifest tier through `copilot_prefs.resolve_tier`;
2. takes the assumed input-token count from the selected
   `pricing["task_profiles"][profile]`;
3. measures the document's AI-accounted output with the lexical policy below;
4. adds one ephemeral in-memory task profile to a copied pricing dict; and
5. calls `copilot_pricing.est_cost` for the resolved model, passing
   `today=date.fromisoformat(pricing["cached_date"])` so promo warnings are tied to the pricing
   snapshot rather than the wall clock.

The generator contains no duplicate USD/AIC formula, no copied rate fields, and no model-id
switch. Long-context behavior, promotional warnings, cached-input treatment, and the
USD-to-AIC conversion remain owned by `copilot_pricing.est_cost`.

### 5. HTML rendering

- One external `assets/style.css`, visually aligned with `docs/how-it-works.html`: warm neutral
  palette, readable serif body, monospace code, bordered tables, callouts, responsive layout.
- No JavaScript, CDN, font download, analytics, or network dependency.
- Supported Markdown is intentionally bounded and test-covered: headings, paragraphs, emphasis,
  inline code, fenced code, links, blockquotes/callouts, simple ordered/unordered lists, and
  simple pipe tables. Unsupported/ambiguous constructs fail generation rather than silently
  producing misleading HTML.
- The renderer creates stable heading ids, rewrites links between manifest Markdown documents to
  their HTML companions, includes a shared navigation area, and links back to the Markdown source.

## Exact AIC cost-per-document semantics

### Report scope

The report inventories every `*.md` and `*.html` path declared by the manifest. JSON is the
machine-readable authority; Markdown and HTML are human-readable renderings of that JSON.

### Telemetry and honesty

No per-document generation telemetry exists. Therefore every nonzero figure is labeled
**prospective authoring estimate**, never actual spend. The report does not infer a document's
cost from Copilot session logs and does not divide a session total across documents.

### Measured output policy

For each document the generator records:

- UTF-8 byte count of the final file;
- Unicode word count;
- a stdlib lexical-token approximation: count each Unicode word run and each standalone
  non-whitespace punctuation/symbol as one lexical unit.

There is no chars-per-token constant or vendor-specific tokenizer claim. The lexical count is
explicitly an approximation and is reported as such.

For authored Markdown, `ai_output_lexemes` excludes text inside generated markers. This separates
AI-authored narrative from deterministic roster/table expansion. Whole-file measurements remain
visible.

### Assumed input context

Each authored Markdown document declares one symbolic input profile in `manifest.json`. The
numeric assumed input tokens and profile label are read at runtime from
`pricing["task_profiles"]`. They represent source-reading and prompt context, not measured
telemetry. The report displays measured output separately from this assumed input.

Initial manifest policy:

| Markdown | Tier slot | Input profile | Rationale |
|---|---|---|---|
| `README.md` | mid | S | concise landing synthesis |
| `INSTALL.md` | mid | S | procedural guide |
| `SAFETY.md` | mid | S | focused guardrail guide |
| `SKILLS.md` | strong | M | synthesis across every skill |
| `AGENTS.md` | strong | M | synthesis across every agent and pin/prefs caveats |
| `MODELS.md` | strong | M | pricing, roster, knob, and preference synthesis |
| `COSTS.md` | strong | M | estimate/actual/proxy accounting distinctions |
| `WORKFLOWS.md` | mid | M | established workflows assembled from pinned sources |
| `AIC-REPORT.md` | deterministic | none | generated from manifest/report JSON |

Tier slots resolve through the preference snapshot; model ids never live in the manifest.

### Pricing call

The ephemeral profile uses:

- input tokens from the selected runtime pricing profile;
- output tokens equal to `ai_output_lexemes`;
- the existing `est_cost` cache behavior, obtained from the imported engine rather than copied
  into the generator.

The report records the engine's effective assumption and `rates_used`/warnings. Promo evaluation
uses the pricing file's own `cached_date`, not today's wall clock, so builds remain deterministic
and all warnings belong to the labeled snapshot. This is an estimate with uncertainty, especially
when actual prompts, caching, hidden reasoning tokens, or model-specific tokenization differ.

### Markdown versus HTML

- Authored Markdown receives one prospective authoring estimate.
- Its HTML companion is a deterministic local render: **AI authoring AIC = 0** and
  **render AIC = 0**. The HTML row points to its Markdown source instead of copying the source
  estimate.
- Totals sum authored Markdown estimates only. HTML is never double-counted.
- `AIC-REPORT.md` and `aic-report.html` are themselves deterministic report artifacts and receive
  zero AIC. Their self-referential size fields are `n/a` with an explicit reason; all other rows
  have measured fields.

### Snapshot labeling

Every generated model/cost block and report prints:

- the pricing file path;
- `cached_date` from the pricing data;
- a pricing-file SHA-256;
- a roster digest;
- the recorded effective pins, excludes, tier resolutions, and notes.

Generated numeric/model-id content is permitted only inside these labeled blocks/artifacts.

## Preference and roster drift handling

Research at kit creation found:

```text
cheap     -> claude-haiku-4.5
mid       -> claude-sonnet-5
strong    -> claude-opus-4.8
frontier  -> gpt-5.6-sol (cross-tier user pin)
excluded  -> claude-fable-5
```

Execution-task pins use the resolved cheap/mid/strong ids above. No execution task earns the
frontier lane; the frontier model was used for planning only.

The generated docs must also expose an important limitation: `prefs/copilot.json` is consumed by
this repository's pricing/execute engines; it does not rewrite a custom agent's checked-in
frontmatter. If an agent's configured pin is excluded, the generated agent inventory flags the
conflict and the prose tells users not to dispatch that agent blindly. This is disclosure, not a
recommendation of the excluded model.

Drift rules:

- pricing bytes or `cached_date` change → `check` fails;
- model add/remove/reorder or tier/rate/note change → generated roster/report changes and
  `check` fails;
- active prefs used by a new `build` change → generated preference snapshot and estimates change;
- local prefs differing from the recorded snapshot do not make CI nondeterministic; `report`
  shows the local active view without writing;
- skill/agent add/remove/rename/source change → source digest or inventory coverage tests fail;
- a manifest document missing its pair or an undeclared Markdown/HTML file under
  `copilot-docs/` → check fails.

## Architecture decisions and rationale

### D1 — Canonical Markdown, generated HTML

Hand-maintaining two prose copies guarantees drift and would double the apparent authoring cost.
One canonical source plus deterministic rendering gives parity and an honest zero-AI HTML cost.

### D2 — A dedicated generator is justified

The product needs HTML parity, generated model facts, active preference resolution,
per-document accounting, source hashing, and drift checks. Existing scripts provide pricing and
prefs logic but no document inventory/renderer/report layer. One small stdlib-only generator is
less risky than scattered ad hoc scripts or hand-maintained snapshots.

### D3 — Import the existing engines

`data/pricing.copilot.json` remains the only numeric source, `copilot_pricing.est_cost` remains
the only cost formula, and `copilot_prefs` remains the only preference resolver. The docs layer
adapts document measurements into an ephemeral task profile; it does not fork the math.

### D4 — Manifest plus generated report

The manifest makes the document set, pair mapping, source dependencies, and symbolic accounting
policy reviewable. The JSON report makes estimates machine-checkable; the Markdown/HTML report
makes them usable. This also solves roster/source drift without embedding logic in prose.

### D5 — Generated blocks for mutable facts

Roster, rates, model ids, reasoning vocabulary, agent pins, profile sizes, cached dates, and
preference outcomes are too volatile to author manually. Stable prose explains how to interpret
them; generated blocks supply current facts.

### D6 — Separate skills and agents guides

Users repeatedly confuse these surfaces. Dedicated guides can explain every item without a giant
landing page, and can state the two exceptions clearly: there is no `execute` agent and no
`lessons-loop` agent.

### D7 — Preference conflict is documented, not hidden

The current excluded model still appears in runtime agent frontmatter and pricing data. Editing
runtime files is out of scope, and silently omitting the conflict would be unsafe. The agent
inventory labels configured pins versus effective prefs and gives safe usage guidance.

### D8 — Prospective, not fabricated, per-document cost

Without telemetry, a content-based estimate plus declared input context is the strongest honest
claim available. HTML and generated reports are zero-AI artifacts. Historical session analysis
stays in `copilot_usage.py`; this report never pretends to be that.

## Constraints

- Python standard library only. No pip, npm, Node, browser tooling, Markdown package, or
  `aesop compile`.
- Never invoke real `copilot`, `claude`, or `codex` in implementation, tests, builds, or verify
  commands.
- Never read or write real `~/.copilot`, `~/.claude`, or `~/.codex`. Tests use temporary paths;
  the docs generator reads only repository files.
- No writes outside the repository; the production generator writes only under `copilot-docs/`.
- Runtime skill/agent files and pricing data are read-only source material.
- No hardcoded live model ids, prices, credit values, allowances, cached dates, or numeric
  comparisons in new docs/scripts outside labeled generated snapshots.
- Every estimate must say it is an estimate and carry uncertainty.
- New task statuses start exactly `pending`.
- No commits or pushes.

## Explicit out-of-scope fence

Do **not** build or change:

- true custom slash-command extensions, `.prompt.md` commands, Copilot extensions, plugins, MCP
  servers, hooks, or cloud-agent configuration;
- any file under `copilot/.github/`, `copilot/aesop.yaml`, `data/`, `prefs/`, `skills/`,
  `codex/`, `.claude-plugin/`, or completed kits;
- `bin/copilot_pricing.py`, `bin/copilot_prefs.py`, `bin/harness_select.py`,
  `bin/copilot_execute.py`, `bin/copilot_usage.py`, journal engines, statusline engines, Ralph,
  scorecards, or installers;
- a general-purpose CommonMark implementation, JavaScript renderer, search index, web server,
  PDF/EPUB output, generated screenshots, or hosted documentation site;
- live model/roster research during execution; the authoritative repo sources are pinned above;
- actual per-document telemetry attribution, session-cost splitting, hidden-reasoning token
  guesses, or conversion of Copilot AIU to AIC;
- automatic installation, modification of user settings, or any write to a real Copilot home;
- rewrites of existing long-form docs. Only the two small discoverability links are sanctioned.

## Risks and tripwires

- **Pricing fork:** any cost formula in `copilot_docs.py` is a defect. Tests monkeypatch
  `copilot_pricing.est_cost` and prove it is called.
- **Personal-prefs CI flake:** `check` must use the recorded snapshot, not whatever prefs happen
  to exist on the checking machine.
- **Excluded agent pin:** the agent guide must not turn a data-derived disclosure into a
  recommendation. Selected document models must be disjoint from recorded excludes.
- **Generated-marker corruption:** missing, nested, duplicated, or mismatched markers are hard
  errors; generated blocks are never silently appended.
- **Report self-reference:** report artifacts are deterministic zero-AI rows with `n/a` size,
  avoiding unstable fixed-point generation.
- **HTML drift:** no HTML is hand-edited; byte comparison and heading/link parity tests catch it.
- **Renderer overreach:** unsupported Markdown fails. Do not expand toward full CommonMark.
- **Stale inventory:** disk discovery and set-equality tests catch added/removed skills or agents.
- **Hardcoded-model relapse:** tests derive live model ids from pricing and reject them in
  generator code, manifest, or authored prose outside generated blocks.
- **Numeric snapshot without provenance:** every generated numeric block must carry cached date
  and hashes; unlabeled numbers are a failure.
- **Estimate/actual confusion:** use the words prospective/estimated for document costs and keep
  usage-log actual/proxy caveats explicit.
- **Direct-agent precedence:** prefs do not mutate agent frontmatter. The docs must say so.
- **Unsafe verification:** a verify command containing a live harness invocation or touching a
  real home is invalid even if it would otherwise pass.

## Testing strategy

### Generator unit tests (`tests/test_copilot_docs.py`)

- load modules with the house importlib pattern;
- synthetic pricing/prefs only for calculation tests;
- manifest validation and traversal rejection;
- generated-marker replacement and failure modes;
- lexical measurement determinism;
- Markdown subset rendering, escaping, stable ids, link rewriting, and accessibility shell;
- build/check byte determinism in temporary trees;
- pricing-engine call-through via monkeypatch, with no duplicate formula;
- pin/exclude resolution, cross-tier note, and excluded-model rejection;
- separate Markdown/HTML rows, zero-AI deterministic render, no double counting, report
  self-row handling;
- pricing/roster/source hash drift detection;
- no subprocess/network/`Path.home()` and no writes beyond the temp docs root.

### Live content tests (`tests/test_copilot_docs_content.py`)

- exact manifest inventory and no undeclared Markdown/HTML;
- exact skill and agent set coverage from disk;
- required installation/discovery/workflow/safety headings and key phrases;
- no affirmative claim that true custom slash commands exist;
- every local link resolves;
- every HTML file matches generator output and its Markdown headings;
- no live model id in generator, manifest, or authored Markdown outside generated blocks;
- generated preference snapshot selects no excluded model and records the active frontier pin;
- generated reports carry pricing cached date/hashes and all documents separately;
- README and `docs/COPILOT-HARNESS.md` links exist.

### Final verification

```bash
python3 bin/copilot_docs.py check
python3 -m unittest discover -s tests -p 'test_copilot_docs*.py' -v
python3 -m unittest discover -s tests
```
