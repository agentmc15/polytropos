# docs-site — tasks

Dispatch preamble: **Every task that runs `python3 bin/docs_build.py build` rewrites every
generated page — those tasks are strictly serial** (T5 → T6 → T7 → T9 → T10 → T11 → T12 →
T13 → T14; never dispatch two of them concurrently). Warm-cluster candidates (serial
`depends:` chains sharing a primary file and one `model` pin): **T4→T5→T6** (all sonnet,
primary file `bin/docs_build.py` + its tests); **T9→T10→T11** (all sonnet, same task shape
over disjoint skill trees, shared inputs AUDIT.md + rebuild — borderline, acceptable);
**T12→T13→T14** (all sonnet, primary surface `docs-src/fragments/` + rebuild). T7, T8, T15
are opus and always fresh dispatches; T16 is haiku. T1, T2, T8 are safe to run in parallel
with each other. The Phase 3 reviewer verdict is the gate that licenses Phases 4–5 — do
not start T9 until it is recorded in NOTES.md. Statuses: pending | in-progress | done |
blocked.

## Phase 1 — Foundations

### T1 — Generator core: inventory + tri-shape frontmatter + fence-aware transforms
- id: T1
- title: Scaffold bin/docs_build.py (inventory, frontmatter, transforms) + unit tests
- status: done
- model: sonnet
- independent: yes

Create `bin/docs_build.py` (new file) and `tests/test_docs_build.py` (new file). Nothing
else may be created or edited by this task.

Module conventions (house style — match `bin/sync_codex_surfaces.py` /
`bin/harness_update.py`): stdlib only; `REPO_ROOT = Path(__file__).resolve().parent.parent`;
argparse CLI added in T5 (this task may stub `main(argv=None)` returning 0);
`if __name__ == "__main__": raise SystemExit(main())`; module docstring stating the
contract in these words or similar: "deterministic, byte-stable, offline — reads only
committed repo content" (do NOT name the banned calls in the docstring: the
introspection test below scans the WHOLE file source, so the literal strings must not
appear anywhere in the module, comments and docstrings included); every function takes
`repo_root` explicitly (defaulting to `REPO_ROOT`). Load
`bin/sync_codex_surfaces.py` as a sibling via the repo's established
`importlib.util.spec_from_file_location` pattern (see `tests/test_harness_select.py`'s
`_load` for the canonical shape; `bin/` is never imported as a package) and REUSE its
`_frontmatter(path)` for frontmatter parsing — never re-implement it. It returns
`(fields_dict, body_str)`, tolerates the Codex nested `metadata:` block (indented lines
are skipped), and raises `ValueError` on missing fences.

Public functions this task must provide:

1. `skill_inventory(repo_root)` → list of dicts, sorted by `(harness, name)`, one per
   skill: `harness` ∈ `("claude", "copilot", "codex")`, `name` (directory name),
   `skill_path` (repo-relative POSIX string), `description` (from frontmatter), `body`
   (frontmatter-stripped markdown), `references` (sorted repo-relative POSIX paths of
   FILES anywhere under that skill's `references/` dir, empty list if none). Harness
   roots: `skills/`, `copilot/.github/skills/`, `codex/skills/`. Every immediate
   subdirectory of a root is a skill and MUST contain `SKILL.md` with frontmatter `name`
   equal to the directory name and a non-empty `description` — any violation raises a
   `ValueError` naming the path (never a silent skip).
2. `demote_headings(text)` → text with every ATX heading line OUTSIDE fenced code blocks
   given one more `#` (cap at 6). Fence detection: a line whose stripped form starts
   with ``` ``` ``` or `~~~` toggles fence state (track the opening fence string; close
   only on a matching fence marker). The same fence machinery is shared with
   `rewrite_links` — write it once (e.g. an internal line-classifier helper).
3. `rewrite_links(text, source_dir, blob_base, page_map)` → text with every INLINE
   markdown link target outside fences rewritten: absolute `http(s)://`, `mailto:`, and
   pure-anchor (`#…`) targets untouched; otherwise resolve the target (minus any
   `#fragment`, which is preserved on the rewritten URL) against `source_dir` (a
   repo-relative POSIX dir); if the resolved repo-relative path is a key in `page_map`
   (maps source path → site-relative page path, e.g. `docs/GUIDE.md` →
   `deep-dives/guide.md`), rewrite to that value; else if it resolves inside the repo,
   rewrite to `blob_base + resolved_path`; if it escapes the repo root, leave unchanged.
   `blob_base` is the module constant
   `GITHUB_BLOB_BASE = "https://github.com/agentmc15/polytropos/blob/main/"`.
   Reference-style (`[text][label]`) links are deliberately NOT rewritten — note this in
   the docstring.

Tests (`tests/test_docs_build.py`, stdlib unittest, mirroring
`tests/test_harness_select.py` conventions: module loaded via `_load`-style helper,
fixtures built with `tempfile.TemporaryDirectory()`): (a) synthetic mini-repo fixtures
proving inventory shape, sort order, and each error path (missing SKILL.md, name
mismatch, empty description); (b) all three real frontmatter shapes parse (write
fixture SKILL.md files copying the Claude `name`+`description`+`allowed-tools` shape,
the Copilot `name`+`description` shape, and the Codex nested `metadata:` shape);
(c) `demote_headings` demotes h1→h2 and caps h6, and does NOT touch `#` lines inside a
fenced block; (d) `rewrite_links` covers: external untouched, anchor-only untouched,
`page_map` hit, blob fallback, fragment preserved, fenced content untouched,
repo-escaping target untouched; (e) a live-tree test asserting the REAL repo inventory
yields exactly 14 claude + 13 copilot + 12 codex records (assert the counts and that
`("claude","route")`, `("copilot","budget")`, `("codex","doctor")` are present);
(f) the introspection guard idiom from `tests/test_codex_setup.py`: the module source
contains no `Path.home`, `subprocess`, `urlopen`, `random.`, `time.time`, or
`date.today`.

Acceptance: all of the above tests exist and pass; the module has zero non-stdlib
imports; `_frontmatter` is reused, not copied.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 -m unittest discover -s tests -p 'test_docs_build.py' -v
```

### T2 — Site skeleton: mkdocs.yml, requirements, landing page, gitignore
- id: T2
- title: Create mkdocs.yml, docs-src/requirements.txt, docs-site/index.md, .gitignore entry
- status: done
- model: sonnet
- independent: yes

Create `mkdocs.yml` (repo root, new), `docs-src/requirements.txt` (new),
`docs-site/index.md` (new), and append to `.gitignore`. Nothing else.

`mkdocs.yml` pinned essentials (exact keys; other theme options are implementer
judgment, kept modest):
- `site_name: polytropos`
- `site_description:` one sentence from README's own framing (picks the right model per
  task, estimates cost, keeps the frontier model for work that needs it).
- `site_url: https://agentmc15.github.io/polytropos/`
- `repo_url: https://github.com/agentmc15/polytropos`
- `docs_dir: docs-site`
- `site_dir: site-build`
- `theme:` → `name: material`, both light and dark `palette` entries with a
  `media`-based automatic default and a manual toggle, `features:` including
  `navigation.sections`, `navigation.top`, `content.code.copy`.
- `markdown_extensions:` → `admonition`, `toc` with `permalink: true`,
  `pymdownx.superfences`, `pymdownx.details` (all ship with mkdocs-material; add
  nothing that needs another pip package).
- `nav:` → exactly one entry for now: `Home: index.md`. Later tasks (T5, T6, T15)
  extend it; do not pre-add entries for pages that don't exist — `--strict` fails on
  missing nav targets.

`docs-src/requirements.txt`: exactly one dependency line, `mkdocs-material>=9.5,<10`,
plus a one-line `#` comment saying this is the site toolchain only — `bin/` and
`tests/` stay stdlib-only (CLAUDE.md invariant).

`docs-site/index.md`: a real landing page (~250–450 words): what polytropos is (route
per task / escalate don't default / see the spend — reuse README's "The intended
workflow" framing), the three harnesses it serves, and where the manual goes next.
**No relative links to site pages that don't exist yet** — external links to the GitHub
repo are fine; T15 rewires the landing page with full internal navigation.

`.gitignore`: append a commented block ignoring `/site-build/` (mkdocs output — built in
CI, never committed). Touch no existing lines (`tests/test_privacy_layout.py` guards the
privacy rules).

Acceptance: all four files as pinned; `.gitignore` diff is append-only; full suite still
green (privacy/layout tests untouched); `mkdocs.yml` parses as YAML is NOT locally
checkable (stdlib has no YAML) — instead acceptance is structural: every pinned key
present, two-space indentation, no tabs.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && grep -q '^docs_dir: docs-site$' mkdocs.yml && grep -q '^site_dir: site-build$' mkdocs.yml && grep -q 'name: material' mkdocs.yml && grep -q 'Home: index.md' mkdocs.yml && grep -q '^mkdocs-material>=9.5,<10$' docs-src/requirements.txt && grep -q '^/site-build/$' .gitignore && ! grep -q "$(printf '\t')" mkdocs.yml && python3 -m unittest discover -s tests -p 'test_privacy_layout.py' -v
```

### T3 — GitHub Actions workflow: build --strict + deploy to Pages
- id: T3
- title: Create .github/workflows/docs-site.yml
- status: done
- model: sonnet
- depends: T2

Create `.github/workflows/docs-site.yml` (new; NOTE: this repo has no `.github/`
directory today — create it; `copilot/.github/` is bundle payload, unrelated). Nothing
else.

Pinned shape:
- `name: docs-site`; triggers: `push` to `main` + `workflow_dispatch`.
- Top-level `permissions:` → `contents: read`, `pages: write`, `id-token: write`;
  `concurrency:` → `group: pages`, `cancel-in-progress: true`.
- Job `build` (ubuntu-latest): `actions/checkout@v4`; `actions/setup-python@v5` with
  `python-version: "3.12"`; `pip install -r docs-src/requirements.txt`;
  `python3 -m unittest discover -s tests -p 'test_docs_*.py' -v` (the drift gate — a
  stale generated page fails the deploy); `mkdocs build --strict`;
  `actions/upload-pages-artifact@v3` with `path: site-build`.
- Job `deploy`: `needs: build`, `environment:` name `github-pages` with
  `url: ${{ steps.deployment.outputs.page_url }}`, single step
  `actions/deploy-pages@v4` with `id: deployment`.
- A header comment block stating: (1) the site publishes at
  https://agentmc15.github.io/polytropos/ once the user sets repo Settings → Pages →
  Source to "GitHub Actions" (manual, one-time); (2) this workflow is the ONLY place
  besides docs-src/requirements.txt that knows about the mkdocs toolchain.

Gotcha: there is no way to execute this locally and no YAML parser in the stdlib — the
verify below is structural (the strings that make the workflow correct), and the real
proof is T17's venv build plus the first CI run. Do not add any step that invokes
`claude`/`copilot`/`codex`/`gh` or touches secrets.

Acceptance: file exists with every pinned element; two-space indentation, no tabs; no
other workflow files created.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && f=.github/workflows/docs-site.yml && test -f "$f" && grep -q 'mkdocs build --strict' "$f" && grep -q "test_docs_\*\.py" "$f" && grep -q 'upload-pages-artifact@v3' "$f" && grep -q 'deploy-pages@v4' "$f" && grep -q 'id-token: write' "$f" && grep -q 'path: site-build' "$f" && grep -q 'docs-src/requirements.txt' "$f" && ! grep -q "$(printf '\t')" "$f" && test "$(ls .github/workflows | wc -l | tr -d ' ')" = "1"
```

## Phase 2 — Generated surfaces & the drift guard

### T4 — Page renderers: skill pages, harness indexes, parity page + fragment splicing
- id: T4
- title: Add render functions + fragment handling to bin/docs_build.py
- status: done
- model: sonnet
- depends: T1

Edit only `bin/docs_build.py` and `tests/test_docs_build.py`.

Add pure render functions (no I/O beyond reading sources handed in by the caller; the
build/check CLI lands in T5). Required elements and ORDER are pinned; exact wording of
generated sentences is the implementer's, but must be identical across all 39 pages
(template, not prose):

1. `render_skill_page(record, fragment_text_or_None, inventory, page_map)` → str.
   Elements in order: (a) h1 `# <name> — <harness label>` with labels exactly `Claude Code`,
   `GitHub Copilot CLI`, `OpenAI Codex CLI`; (b) provenance comment on its own line:
   `<!-- GENERATED by bin/docs_build.py from <skill_path> — do not edit; edit the source and run: python3 bin/docs_build.py build -->`;
   (c) the frontmatter description as a `>` blockquote; (d) a short facts block:
   source link (`GITHUB_BLOB_BASE + skill_path`), "Also available on" — links to each
   sibling harness page for the same skill name (site-relative, e.g.
   `../copilot/route.md`) or a "this harness only — see the [parity matrix](../index.md)"
   line when none; "References shipped with the skill" — blob links to each
   `references/` file, or "none"; (e) IF a fragment exists: `## In practice` then the
   fragment text verbatim; (f) `## The skill card — what the model reads`, then one
   note line explaining that `${CLAUDE_PLUGIN_ROOT}` / `{{POLYTROPOS_ROOT}}` are
   install-time path variables shown as the model sees them, then the body passed
   through `demote_headings` + `rewrite_links` (source_dir = the skill's directory,
   page_map = the deep-dive map from T6's constant — accept it as a parameter now,
   pass `{}` in tests).
2. `render_harness_index(harness, inventory, fragment_text_or_None)` → str: h1 with the
   harness label, provenance comment (source = the harness skills root), a table of
   `skill | description | page link` rows sorted by name, then IF an index fragment
   exists: `## Using these skills` + fragment verbatim.
3. `render_parity_page(inventory, fragment_text_or_None)` → str: h1 `# Skills across
   the three harnesses`, provenance comment, a matrix table — one row per name in the
   sorted union of skill names (currently 20 — derive from the inventory, never
   hardcode), columns Claude Code / GitHub Copilot CLI / OpenAI Codex CLI, each cell a
   relative page link or `—` — then IF `docs-src/fragments/parity.md` content is
   handed in: `## Why the rosters differ` + fragment verbatim.
4. `load_fragment(repo_root, rel_path)` → str or None, plus validation
   `validate_fragment(text, rel_path)`: raise `ValueError` naming the file if any line
   outside a code fence is an ATX h1 or h2 (`# ` / `## ` prefix) — fragments use h3+
   only, because the page owns h1/h2. Fragment locations (pin as constants):
   `docs-src/fragments/skills/<harness>/<name>.md` (per-skill),
   `docs-src/fragments/skills/<harness>/index.md` (per-harness), and
   `docs-src/fragments/parity.md`. A fragment file whose `<harness>/<name>` matches no
   inventory record is an error (raise, never ignore — catches typos).

Tests to add: rendered-page element/order assertions on synthetic records (with and
without fragments); sibling-links correctness (a name on all three harnesses vs a
harness-only name); parity matrix cell correctness for both cases; fragment h1/h2
rejection (including that a `## ` INSIDE a fence is allowed); orphan-fragment rejection;
determinism (rendering twice yields identical bytes).

Acceptance: all render functions pure and deterministic; element order as pinned;
new tests pass alongside all T1 tests.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 -m unittest discover -s tests -p 'test_docs_build.py' -v
```

### T5 — build/check CLI, first real build, drift + nav + link tests
- id: T5
- title: Wire the CLI, generate all 43 skill pages, add tests/test_docs_site.py, nav
- status: done
- model: sonnet
- depends: T4, T2

Edit `bin/docs_build.py`, `mkdocs.yml`; create `tests/test_docs_site.py`; the build
writes `docs-site/skills/**` (43 new generated files). No other files.

CLI (argparse, house shape): subcommands `build` and `check`, both with
`--repo-root PATH` (default `REPO_ROOT`). Core seam: `expected_pages(repo_root)` → dict
mapping repo-relative POSIX paths under `docs-site/` to `bytes` (UTF-8, LF, exactly one
trailing newline). At this task the deep-dive `page_map` does not exist yet — pass an
empty map, so every relative link in an embedded body rewrites to a GITHUB_BLOB_BASE
URL (T6 introduces the map and regenerates). This task's page set:
`docs-site/skills/index.md`,
`docs-site/skills/<harness>/index.md` ×3, `docs-site/skills/<harness>/<name>.md` ×39
(43 total; T6 extends the set). `build`: write every expected page (mkdir -p as
needed), print `written N / unchanged M`, exit 0; exit 2 on any source error
(inventory/fragment ValueError — print the message to stderr, mirroring
`sync_codex_surfaces.main`). `check`: byte-compare every expected page against the
committed file — missing or differing → stale; ALSO scan the generator-owned roots
`docs-site/skills/` and (once T6 lands) `docs-site/deep-dives/` for files NOT in the
expected set → report as `unknown` (drift). Print the stale/unknown lists with the
remedy line `python3 bin/docs_build.py build`; exit 0 fresh / 1 drift / 2 error.
Then RUN `python3 bin/docs_build.py build` and commit-stage the 43 pages it writes
(fragments don't exist yet, so every page legitimately omits its `## In practice`
section — expected).

`mkdocs.yml` nav: add a `Skills` section containing `skills/index.md`, then one
subsection per harness (labels exactly `Claude Code`, `GitHub Copilot CLI`,
`OpenAI Codex CLI`) listing that harness's `index.md` plus all its skill pages, sorted
by name.

`tests/test_docs_site.py` (live-tree, like `tests/test_guardrails_layout.py` — asserts
against the real repo, no fixtures):
1. **Drift**: load `docs_build` (importlib `_load` idiom), call
   `expected_pages(REPO_ROOT)`, assert every expected path exists on disk with exactly
   the expected bytes, and assert no un-expected file exists under the generator-owned
   roots. Failure message must name the stale files and the rebuild command.
2. **Nav coverage, both directions**: read `mkdocs.yml` as text; (a) every expected
   generated page path appears in it exactly once; (b) every token in `mkdocs.yml`
   matching the regex `(?:skills|deep-dives)/[A-Za-z0-9._/-]+\.md` is a key of
   `expected_pages` — the two generated roots are generator-owned, so a hand page may
   never live there.
3. **Offline link integrity**: for every `docs-site/**/*.md`, every inline relative
   link outside code fences (reuse the module's fence/link machinery via the loaded
   module — do not re-implement) that is not `http(s)`/`mailto`/anchor-only must
   resolve to an existing file under `docs-site/`. (Anchors are not validated — say so
   in the test docstring.)
4. **Context-leak fence**: no file matching `skills/*/SKILL.md`,
   `copilot/.github/skills/*/SKILL.md`, or `codex/skills/*/SKILL.md` contains the
   string `docs-site` (PLAN D1 — site content must never be loadable from a skill).

Gotcha: test 1 makes the committed tree and the generator inseparable — that is the
point. If you find yourself editing a generated page by hand to make a test pass, stop:
fix the renderer and rebuild.

Acceptance: `check` exits 0 on the fresh tree; all four test groups pass; full suite
green; the temp-copy mutation probe below proves `check` can actually fail.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 bin/docs_build.py check && python3 -m unittest discover -s tests -p 'test_docs_site.py' -v && TMP="$(mktemp -d)" && cp -R skills copilot codex docs docs-src docs-site bin "$TMP/" && printf '\nmutation-probe\n' >> "$TMP/skills/route/SKILL.md" && ! python3 bin/docs_build.py check --repo-root "$TMP" && rm -rf "$TMP" && python3 -m unittest discover -s tests 2>&1 | tail -2
```

### T6 — Deep-dive mirrors: 24 docs/*.md onto the site
- id: T6
- title: Mirror docs/*.md into docs-site/deep-dives/ with rewritten links
- status: done
- model: sonnet
- depends: T5

Edit `bin/docs_build.py`, `tests/test_docs_build.py`, `tests/test_docs_site.py`,
`mkdocs.yml`; the build writes `docs-site/deep-dives/**` (25 new generated files).
**`docs/*.md` sources are read-only to this task.**

Extend `expected_pages` with: `docs-site/deep-dives/<slug>.md` for every `docs/*.md`
(slug = lowercased filename stem: `COPILOT-HARNESS.md` → `copilot-harness.md`; the two
`.html` files are NOT mirrored — PLAN D6), plus a generated
`docs-site/deep-dives/index.md` (h1, provenance comment, table of `title | page` rows
sorted by slug, title = the text of the source's first h1 line, falling back to the
filename). Currently 24 sources → 25 pages; DERIVE the set from a `docs/` glob, never a
hardcoded list, so a future doc auto-joins (and the nav test forces its nav line).

Each mirror page = provenance comment (naming `docs/<NAME>.md`) + a one-line note
("Mirrored from `docs/<NAME>.md` — edit the source, then run
`python3 bin/docs_build.py build`.") + the source body transformed by `rewrite_links`
ONLY (headings NOT demoted — sources already carry a single h1) with this `page_map`
(build it as a module function, it is also what skill pages receive):
`docs/<NAME>.md` → `deep-dives/<slug>.md` for every mirrored source, plus
`docs/guide.html` → `deep-dives/guide.md` and `docs/how-it-works.html` →
`deep-dives/how-it-works.md`. Because mirror pages and skill pages live at different
depths, `page_map` values must be resolved to correct RELATIVE links per rendered page
(e.g. from `deep-dives/guide.md`, `docs/HOW-IT-WORKS.md` → `how-it-works.md`; from
`skills/claude/route.md` → `../../deep-dives/how-it-works.md`) — implement relative
resolution once, in the renderer layer.

`mkdocs.yml` nav: add a `Deep dives` section: `deep-dives/index.md` first, then all 24
mirror pages sorted by slug (labels = the derived titles, shortened at implementer
judgment).

Tests: unit tests for slug mapping, title extraction, page_map link rewriting at both
depths, and `.html`-exclusion; `test_docs_site.py` needs no structural change (its
drift/nav/link groups automatically cover the new pages — confirm by running it), but
ADD one live assertion: for every `docs/*.md` file a corresponding
`deep-dives/<slug>.md` exists in `expected_pages`.

Then run `python3 bin/docs_build.py build` and stage the 25 pages.

Gotcha: `docs/GUIDE.md` and `docs/HOW-IT-WORKS.md` link to each other and to
`guide.html`/`how-it-works.html`, `AESOP-INTEGRATION.md` links out to another repo
(external — untouched), and several docs link into `bin/`, `skills/`, `data/` — those
become GITHUB_BLOB_BASE URLs. The offline link test is your net: any rewrite the
implementation misses that leaves a dangling relative link fails test group 3.

Acceptance: 68 total generated files committed; check exits 0; nav covers all;
full suite green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 bin/docs_build.py check && test "$(ls docs-site/deep-dives/*.md | wc -l | tr -d ' ')" = "25" && python3 -m unittest discover -s tests -p 'test_docs_build.py' -v && python3 -m unittest discover -s tests -p 'test_docs_site.py' -v && python3 -m unittest discover -s tests 2>&1 | tail -2
```

### T6b — Renderer fixes from the Phase 2 review (executor-added)
- id: T6b
- title: Fix P2 review findings F1-F6/F10 in bin/docs_build.py + rebuild
- status: done
- model: sonnet
- depends: T6

Added by the executor after the Phase 2 review confirmed seven renderer defects in the
committed output. Edit `bin/docs_build.py`, `tests/test_docs_build.py`, and (only if a
pinned assertion is genuinely superseded) `tests/test_docs_build_adversarial.py`; then
rebuild. `docs/*.md` and every SKILL.md stay read-only.

Fixes, each with a regression test:
1. **F1 — HTML-swallowed placeholders.** Generator-emitted description text renders `<slug>`
   as raw inline HTML, so `tasks/kits/<slug>/` displays as `tasks/kits//`. Escape `<`/`>` in
   the description text THE GENERATOR ITSELF emits — the blockquote on skill pages and the
   description cells of harness-index and parity tables. Do NOT touch embedded skill-card
   bodies (that is source content, not generator text).
2. **F2 — empty references line.** Omit the "References shipped with the skill" line entirely
   when a skill ships none (36/39 pages currently carry a "none" that reads as a deficit on
   every Copilot and Codex page). When refs exist, label each with its path relative to the
   skill dir (`references/roles/scout.md`, not bare `scout.md`) so `claude/architect`'s seven
   role files read as a catalog.
3. **F3 — self-referencing mirror links.** When an `.html` companion target rewrites to the
   page currently being rendered, drop the link and render its label as plain text; when two
   links on a page would resolve to the same mirror, that is acceptable, but a page must never
   link to itself.
4. **F4 — mirror note placement.** Move the "Mirrored from `docs/X.md` — edit the source…"
   note BELOW the source's h1 and render it as an `admonition` (`!!! note`; the extension is
   already enabled in `mkdocs.yml` and unused).
5. **F5 — deep-dive index duplicate columns.** Collapse to a single column whose text is the
   title and whose target is the page.
6. **F6 — skill-card honesty.** The note line under `## The skill card — what the model reads`
   currently mentions only path variables, but the generator also strips a leading h1 from
   30/39 bodies, demotes every heading one level, and rewrites relative links. Extend the note
   to say so plainly and point at the linked source as the unmodified original.
7. **F10 — setext headings in fragments.** `validate_fragment` rejects only ATX `#`/`##`; a
   fragment using `Title` + `=====` would emit an h1 inside `## In practice`. Reject setext h1/h2
   outside fences too.

Finish with `python3 bin/docs_build.py build` (all 68 pages regenerate; diffs expected) and
confirm `check` exits 0.

Acceptance: all seven fixed with regression tests; 68 pages still generated; check exits 0;
full suite green beyond the documented 10-error LedgerJoinTests baseline.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 bin/docs_build.py check && test "$(find docs-site/skills docs-site/deep-dives -name '*.md' | wc -l | tr -d ' ')" = "68" && ! grep -rn 'References shipped with the skill:\*\* none' docs-site/skills/ && ! sed -n '5p;7p;13p' docs-site/skills/codex/index.md docs-site/skills/copilot/index.md docs-site/skills/codex/architect.md docs-site/skills/copilot/architect.md | grep -q 'kits/<slug>' && python3 -m unittest discover -s tests -p 'test_docs_build.py' -v && python3 -m unittest discover -s tests -p 'test_docs_site.py' -v && python3 -m unittest discover -s tests 2>&1 | tail -2
```

## Phase 3 — Template proof (pilot) — REVIEW GATE before Phases 4–5

### T7 — Fragment template + three diverse pilot fragments + harness/parity fragments
- id: T7
- title: Author docs-src/fragments/TEMPLATE.md, 3 pilot skill fragments, 3 harness index fragments, parity fragment
- status: done
- model: opus
- depends: T6

Create `docs-src/fragments/TEMPLATE.md`,
`docs-src/fragments/skills/claude/route.md`,
`docs-src/fragments/skills/copilot/budget.md`,
`docs-src/fragments/skills/codex/doctor.md`,
`docs-src/fragments/skills/{claude,copilot,codex}/index.md`,
`docs-src/fragments/parity.md`; then run `python3 bin/docs_build.py build` and stage
the regenerated pages. No skill files, no `bin/`, no test edits.

`TEMPLATE.md` is the single source later batches follow. It pins the six REQUIRED h3
sections, in order, with 2–3 sentences of guidance each and one fully-worked example
fragment inline: `### What it does` (2–4 plain-language sentences, no jargon a newcomer
lacks), `### When to reach for it` (bullets, including at least one "not for…" bullet),
`### Worked example` (a realistic invocation and what the user sees — every command,
flag, and file path shown MUST exist in that skill's SKILL.md, the engine it names
under `bin/`, or the harness doc; nothing invented), `### Failure modes & fallbacks`
(what goes wrong, what the skill does about it, when to escalate),
`### Cost & safety` (what can spend money or write files vs what is read-only — derived
from the skill's own text; NEVER a dollar figure, price ratio, or model id — name
tiers, link the pricing file on GitHub, or show the engine command that prints current
numbers), `### Related` (sibling skills/pages, as links). Fragments are h3-only
(generator-enforced), 150–450 words per skill.

The three pilots are deliberately diverse — `claude/route` (rich skill with
references), `copilot/budget` (harness-only skill: its fragment must make
harness-exclusivity legible), `codex/doctor` (thin, safety-heavy: the fragment carries
the human tutorial the tight skill card refuses to). Ground every claim in:
the skill's SKILL.md, `docs/GUIDE.md`, `docs/HOW-IT-WORKS.md`,
`docs/COPILOT-HARNESS.md`, `docs/CODEX-HARNESS.md`, and the named engine's argparse
source. The three `index.md` fragments (spliced as `## Using these skills`) state each
harness's real invocation surfaces — derive from those harness docs (Claude:
`/polytropos:<name>`; Copilot: `/name` in-prompt, auto-load by description, `/skills
reload`, agents vs skills distinction; Codex: per `docs/CODEX-HARNESS.md` — do not
guess), plus install pointer. `parity.md` (spliced as `## Why the rosters differ`)
explains every harness-only skill in one line each so a `—` in the matrix reads as
design, not omission — derive the harness-only list from the committed rosters, don't
trust this brief's memory of it.

If the template or page anatomy proves wrong in practice (sections that don't fit a
real skill, splice reading badly against the embedded skill card), adjust TEMPLATE.md
(and only it) and record the delta + reasoning in NOTES.md for the phase reviewer — the
Phase 3 review verdict is what licenses applying this template 35 more times.

Acceptance: all 8 fragment files exist; the three pilot pages and three index pages and
the parity page carry the spliced sections; every command shown traces to a real
source; `check` exits 0.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && for f in docs-src/fragments/skills/claude/route.md docs-src/fragments/skills/copilot/budget.md docs-src/fragments/skills/codex/doctor.md; do for h in '### What it does' '### When to reach for it' '### Worked example' '### Failure modes & fallbacks' '### Cost & safety' '### Related'; do grep -qF "$h" "$f" || { echo "MISSING $h in $f"; exit 1; }; done; done && grep -q '## In practice' docs-site/skills/claude/route.md && grep -q '## Why the rosters differ' docs-site/skills/index.md && grep -q '## Using these skills' docs-site/skills/codex/index.md && python3 bin/docs_build.py check && python3 -m unittest discover -s tests -p 'test_docs_site.py' -v
```

### T8 — The 39-skill audit: dispositions under the three-way rule
- id: T8
- title: Write .claude/kits/docs-site/AUDIT.md — per-skill disposition for all 39 skills
- status: done
- model: opus
- independent: yes

Create `.claude/kits/docs-site/AUDIT.md` ONLY. Read all 39 SKILL.md files in full
(`skills/*/SKILL.md`, `copilot/.github/skills/*/SKILL.md`, `codex/skills/*/SKILL.md`)
plus PLAN.md D1. This is a read-and-judge task: no skill file is edited here.

Format (pinned — T9–T14 parse it by eye, keep it uniform, and the verify counts on it:
the ONLY h3 headings in the file are the 39 entry headers). Three `## <harness>`
sections; per skill:

```
### <harness>/<name>
- verdict: keep | enrich | relocate
- skill-md: <the specific additions/moves, or "unchanged">
- references: <references/<file>.md to create, each with a one-line charter, or "none">
- fragment-notes: <2–5 bullets of what the site fragment must cover; gotchas; the
  engine/doc sources to ground it in>
- sentinels: <test files that grep showed pin this skill's text (run
  grep -rlF "<name>" tests/ and inspect), or "none found">
```

Judgment rules (D1 binds you): `enrich` means adding a missing ACTING fact only — a
real flag, a failure signal, a fallback, a "read references/<f>.md when X" pointer —
never prose, never restating the site. `relocate` means SKILL.md content that fails the
D1 litmus moves to a new `references/` file with a pointer (candidates to examine
honestly, not presumptively: the longest bodies — claude architect/execute/repo-bench
are ceiling-bound but ALSO contract-laden and sentinel-pinned, so prefer `keep` there
unless a section is plainly narrative; claude context-weight at ~2.4k words deserves a
hard look). The seven thin skills (claude cost-report; copilot lessons-loop; codex
bench-routing, doctor, memory, context-weight, execute) each get an explicit verdict
with reasoning — remembering thin ≠ deficient (codex skills are deliberately dense).
Expect most of the 39 to be `keep`: the robustness the user asked for lands
overwhelmingly in fragments and references, not in fatter skill cards. For every
`relocate`, note the sentinel risk explicitly. Never propose touching the generated
`references/pricing.json` mirrors (route, fable-check) or `architect/references/roles/`.

Acceptance: all 39 entries present in the pinned format; every thin-seven entry has
explicit reasoning; every `relocate` names its sentinel exposure; no entry proposes
editing pricing mirrors or role templates.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && f=.claude/kits/docs-site/AUDIT.md && test "$(grep -c '^### ' "$f" | tr -d ' ')" = "39" && test "$(grep -c '^- verdict: ' "$f" | tr -d ' ')" = "39" && test "$(grep -c '^- fragment-notes:' "$f" | tr -d ' ')" = "39" && grep -q '### claude/cost-report' "$f" && grep -q '### copilot/lessons-loop' "$f" && grep -q '### codex/bench-routing' "$f" && ! grep -q 'references/pricing.json' "$f"
```

### T7b — Phase 3 review amendments (executor-added; BLOCKS T12)
- id: T7b
- title: Apply the P3 gate rulings to TEMPLATE.md, AUDIT.md, parity.md, codex/doctor.md + rebuild
- status: done
- model: sonnet
- depends: T7, T8

Added by the executor: the Phase 3 review returned GO-WITH-AMENDMENTS and named these as
required before T12 dispatches. Edit ONLY `docs-src/fragments/TEMPLATE.md`,
`.claude/kits/docs-site/AUDIT.md`, `docs-src/fragments/parity.md`, and
`docs-src/fragments/skills/codex/doctor.md`; then rebuild. No skill file, no `bin/`, no test
edits (the companion test change is the test-author's, dispatched separately).

1. **Word budget (P3 finding 1, HIGH).** Replace TEMPLATE.md's 150-450 rule with: per-skill
   fragments are **150-550 words by `wc -w` on the file (scaffolding included) AND at most 450
   words of prose**, where prose = the file with fenced blocks and table rows (lines beginning
   `|`) removed. State both numbers and the reason: a 6-row table costs ~90 `wc -w` tokens, ~41
   of them literal pipes, so a single ceiling makes the budget the output. Index and parity
   fragments get **150-700 `wc -w`**. Also restore `route.md`'s `escalate` link in its
   `### Related` (it survives inline in Failure modes, but the Related entry was cut for budget).
2. **The dollar-figure contradiction (P3 finding 2, HIGH).** `AUDIT.md`'s `claude/repo-bench`
   fragment-notes license "no dollar figure that is not clearly the skill's own quoted
   calibration anecdote" — TEMPLATE.md says never write a dollar figure and GUARDRAILS forbids
   any hardcoded price in a fragment. Fix AUDIT.md to remove the license (state the lesson,
   point at the card below). Add to TEMPLATE.md: **no dollar figure, in prose OR inside a
   fence.**
3. **Source enumeration (P3 ruling, finding 7).** Add to TEMPLATE.md's mechanical rules the
   six-source list the reviewer specified verbatim (skill SKILL.md + its references; the named
   `bin/` engine read in source; any `docs/*.md` — all 24, not only harness docs; README.md and
   SETUP.md; `copilot-docs/**` cite-never-edit; bundle payload under `copilot/.github/` and
   `codex/` for facts about the bundle), the "nothing else" clause, the name-the-file-and-line
   requirement, and the tiebreak: where a generated doc and a SKILL.md disagree, the SKILL.md wins.
4. **Sibling-claim rule (P3 finding 5).** Add to TEMPLATE.md: claims about a sibling skill are
   facts too — check that skill's own card before writing "X covers Y" — and add it as a
   pre-flight item. Then FIX the instance: `docs-src/fragments/skills/codex/doctor.md` says
   `update` "covers Claude and Copilot" in When-to-reach-for-it but "all three harnesses" in
   Related. The second is correct.
5. **Parity roster count (P3 finding 3).** `docs-src/fragments/parity.md` says "Four rows carry a
   dash only because the capability is named for the harness it serves", then its fourth bullet
   says memory is genuinely not built for Copilot — not a rename. TEMPLATE.md also bans roster
   counts as stale-prone. Reword to the reviewer's text: "Some rows carry a dash because the
   capability is named for the harness it serves — and one because it genuinely is not built yet."
6. **T14 carry-forward (P3 finding 6)** — record in AUDIT.md's `codex/memory` fragment-notes that
   the fragment must say the Codex card is deliberately recall-only (it documents `review` only,
   while the Claude skill documents add/update/remove/list/review) so the parity row does not
   read as a half-port. Do not change its `keep` verdict.

Finish with `python3 bin/docs_build.py build` and confirm `check` exits 0.

Acceptance: all six applied; both budget numbers stated in TEMPLATE.md; no dollar-figure license
left in AUDIT.md; the doctor and parity contradictions fixed; check exits 0; full suite shows
exactly 10 errors (all `LedgerJoinTests`) and ZERO failures.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && grep -q '550' docs-src/fragments/TEMPLATE.md && grep -qi 'prose' docs-src/fragments/TEMPLATE.md && ! grep -q 'calibration anecdote' .claude/kits/docs-site/AUDIT.md && ! grep -q 'Four rows' docs-src/fragments/parity.md && ! grep -q 'covers Claude and Copilot' docs-src/fragments/skills/codex/doctor.md && python3 bin/docs_build.py check && python3 -m unittest discover -s tests -p 'test_docs_*.py' 2>&1 | tail -2
```

## Phase 4 — Skill-card robustness (runtime-facing edits)

### T9 — Apply AUDIT dispositions: Claude harness (14 skills)
- id: T9
- title: Apply AUDIT.md to skills/*/SKILL.md + create their references/
- status: done
- model: sonnet
- depends: T7, T8

Edit only: `skills/*/SKILL.md` per AUDIT.md, new files under `skills/*/references/`,
and the regenerated `docs-site/` pages (via build). Read
`.claude/kits/docs-site/AUDIT.md` and apply every `## claude` disposition exactly —
the audit is your spec; if it conflicts with repo reality, stop and report, don't
improvise.

Binding rules (GUARDRAILS.md has the full set): additive-first; before deleting or
rewording ANY existing line run `grep -rF '<distinctive 6+ word phrase>' tests/` and
keep any line a test pins; every new `references/*.md` gets a one-line "read when X"
pointer in its SKILL.md; no SKILL.md exceeds its D1 budget (engine-wrappers ≤ ~900
words of body; architect/execute/repo-bench may only shrink); no price/model-id/date
literals; never touch `skills/route/references/pricing.json`,
`skills/fable-check/references/pricing.json`, or
`skills/architect/references/roles/*`; the string `docs-site` never enters a SKILL.md.
Frontmatter `description` fields may be sharpened ONLY where AUDIT says so (they are
runtime trigger surfaces AND feed the generated pages/parity table).

Finish with `python3 bin/docs_build.py build` (bodies changed → pages must be
regenerated) and stage the regenerated pages together with the skill edits.

Acceptance: every `## claude` AUDIT entry applied or explicitly reported as
conflicting; full suite green; `check` exits 0; word budgets hold.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 bin/docs_build.py check && ! grep -rl 'docs-site' skills/*/SKILL.md && python3 -m unittest discover -s tests 2>&1 | tail -2
```

### T10 — Apply AUDIT dispositions: Copilot harness (13 skills)
- id: T10
- title: Apply AUDIT.md to copilot/.github/skills/*/SKILL.md + references/
- status: done
- model: sonnet
- depends: T9

Same contract as T9, scoped to `copilot/.github/skills/`. Additional gotchas: bundle
files may carry `{{POLYTROPOS_ROOT}}` — preserve the placeholder convention in any new
references content that shells out (and remember `bin/harness_select.py` rglobs the
whole `copilot/.github/skills/` tree at install time, so new `references/` files ship
to users — keep them lean and never put secrets, prices, or absolute paths in them);
`tests/test_copilot_bundle.py` and the aesop manifest (`copilot/aesop.yaml`) pin
aspects of this tree — the full-suite run is your tripwire, and `copilot/aesop.yaml`
is read-only to this task. Finish with `python3 bin/docs_build.py build` + stage.

Acceptance: every `## copilot` AUDIT entry applied or reported; full suite green;
`check` exits 0.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 bin/docs_build.py check && ! grep -rl 'docs-site' copilot/.github/skills/*/SKILL.md && python3 -m unittest discover -s tests 2>&1 | tail -2
```

### T11 — Apply AUDIT dispositions: Codex harness (12 skills) + prompt mirrors
- id: T11
- title: Apply AUDIT.md to codex/skills/*/SKILL.md + references/ + sync codex/prompts
- status: done
- model: sonnet
- depends: T10

Same contract as T9, scoped to `codex/skills/`. THE codex-specific gotcha: seven stems
(architect, effort, escalate, frontier-check, journal, route, usage) are mirrored into
`codex/prompts/*.md` by `bin/sync_codex_surfaces.py` — if AUDIT has you touch any of
those seven SKILL.md files, run `python3 bin/sync_codex_surfaces.py build` and stage
the regenerated prompts, or `tests/test_codex_surfaces.py` fails. Codex frontmatter
carries the nested `metadata: short-description:` block — preserve it byte-for-byte
unless AUDIT says otherwise. `tests/test_codex_bundle.py` pins the exact 12-dir roster
of `codex/skills/` — you are adding files INSIDE skill dirs, never adding/removing a
skill dir. Finish with `python3 bin/docs_build.py build` + stage.

Acceptance: every `## codex` AUDIT entry applied or reported; codex prompt mirrors
fresh; full suite green; `check` exits 0.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 bin/sync_codex_surfaces.py check && python3 bin/docs_build.py check && ! grep -rl 'docs-site' codex/skills/*/SKILL.md && python3 -m unittest discover -s tests 2>&1 | tail -2
```

### T11b — Restore two runtime facts lost in Phase 4 (executor-added)
- id: T11b
- title: Restore the hook-restart trigger and two dropped context-weight clauses
- status: done
- model: sonnet
- depends: T11

Added by the executor from the P4 review's Findings 4 and 5. Both are small D1 misses left by
T9's un-mandated tightening pass — the pass itself was upheld, but it cost two acting facts.
Edit ONLY `skills/setup/SKILL.md` and `skills/context-weight/SKILL.md`, then rebuild.

1. **F4 — the hook-restart fact lost its trigger (the more important of the two).**
   `claude --debug` appears nowhere in `skills/`, `codex/`, `copilot/`, or `docs/` any more. The
   restart requirement itself survived, but ONLY in `skills/setup/references/kit-verify-hook.md`,
   whose pointer trigger reads "read before telling the user what a marker proves". A model that
   completes a hook install and runs step 5 has no trigger to read that file, so it will apply
   the settings edit and never say a restart is needed — the wrong outcome on a normal run,
   which is exactly D1's litmus. Append to step 5 of `skills/setup/SKILL.md` a sentence in the
   reviewer's suggested shape: hook config loads at session start, so tell the user to restart,
   and `claude --debug` confirms registration. Keep it to one sentence.
2. **F5 — two clauses dropped from `skills/context-weight/SKILL.md`.** Restore (a) that
   `watch codex` / `watch copilot` refuses **and exits 0** — verified real at
   `bin/context_weight.py:3259-3263`, where `watch` takes an optional positional harness; without
   it a model may read the refusal as a failure. And (b) the clause noting there is no substitute
   live check for those two harnesses. Restore both in their original wording where the git
   history supports it (`git show HEAD:skills/context-weight/SKILL.md`), not paraphrased.

Do NOT re-open the ~900 budget question: the P4 review ruled the remedy is the PLAN amendment
(already made), not another relocation round. These additions are a handful of words.
Do NOT touch any Copilot skill (the `copilot-docs` coupling freezes that tree for this kit) and
do NOT touch any of the seven mirrored Codex stems.

Acceptance: both facts restored; `check` exits 0; full suite shows exactly 10 errors (all
`LedgerJoinTests`) and ZERO failures; `skills/setup/SKILL.md` step 1's sample JSON still
byte-untouched.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && grep -q 'claude --debug' skills/setup/SKILL.md && grep -q 'exits 0' skills/context-weight/SKILL.md && python3 bin/docs_build.py check && python3 -m unittest discover -s tests -p 'test_docs_*.py' 2>&1 | tail -2 && python3 -m unittest discover -s tests -p 'test_statusline.py' 2>&1 | tail -2
```

## Phase 5 — Fragment authoring at scale

### T12 — Claude fragments: the remaining 13
- id: T12
- title: Author docs-src/fragments/skills/claude/<name>.md for 13 skills
- status: done
- model: sonnet
- depends: T11

Create exactly these 13 files under `docs-src/fragments/skills/claude/`:
`architect.md`, `bench-routing.md`, `context-weight.md`, `cost-report.md`,
`escalate.md`, `execute.md`, `fable-check.md`, `graphify.md`, `journal.md`,
`memory.md`, `repo-bench.md`, `setup.md`, `update.md` (route exists from T7). Then
`python3 bin/docs_build.py build` + stage regenerated pages. No other edits.

Follow `docs-src/fragments/TEMPLATE.md` (as amended by the Phase 3 review, if it was)
— six h3 sections, order pinned, within TEMPLATE.md's word budget (**150–550 `wc -w` total AND ≤450 words of prose**, prose = the file minus fenced blocks and minus table rows — the Phase 3 gate widened the total and re-measured the 450 ceiling as prose specifically, so a grounded table no longer costs you prose room; the number in this brief before the amendment said 150–450 and is superseded), h3-only. Ground every fragment in:
that skill's SKILL.md (post-T9 state), its AUDIT.md `fragment-notes`, `docs/GUIDE.md`
§4–5 (per-skill walkthroughs) and `docs/HOW-IT-WORKS.md`, and the engine sources the
skill names (e.g. `bin/cost_report.py --help`-visible flags read from its argparse
source — do NOT execute engines that read real home dirs; read the source instead).
Honesty law: no invented flags, no dollar figures, no model ids, no plan allowances —
tiers and links only; `### Cost & safety` must state what is read-only vs what
writes/spends, per the skill's own text (e.g. repo-bench spends only behind
`--live --max-usd`; journal output is gitignored; setup writes `~/.claude/settings.json`
with consent).

Acceptance: 13 files, six sections each, grounded; `check` exits 0; the 13 claude
pages carry `## In practice`; full suite green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && for n in architect bench-routing context-weight cost-report escalate execute fable-check graphify journal memory repo-bench setup update; do f="docs-src/fragments/skills/claude/$n.md"; for h in '### What it does' '### When to reach for it' '### Worked example' '### Failure modes & fallbacks' '### Cost & safety' '### Related'; do grep -qF "$h" "$f" || { echo "MISSING $h in $f"; exit 1; }; done; grep -q '## In practice' "docs-site/skills/claude/$n.md" || { echo "NOT SPLICED: $n"; exit 1; }; done && python3 bin/docs_build.py check && python3 -m unittest discover -s tests 2>&1 | tail -2
```

### T13 — Copilot fragments: the remaining 12
- id: T13
- title: Author docs-src/fragments/skills/copilot/<name>.md for 12 skills
- status: done
- model: sonnet
- depends: T12

Create exactly: `architect.md`, `bench-routing.md`, `context-weight.md`, `effort.md`,
`escalate.md`, `execute.md`, `frontier-check.md`, `goliath.md`, `journal.md`,
`lessons-loop.md`, `route.md`, `usage.md` under `docs-src/fragments/skills/copilot/` (budget exists from
T7). Then build + stage. No other edits.

Same template/grounding contract as T12, with Copilot grounding sources:
`docs/COPILOT-HARNESS.md`, `docs/COPILOT-WORKFLOW.md`, `docs/COPILOT-COSTVIZ.md`,
`docs/COPILOT-PINS.md`, `copilot-docs/*.md` (link the copilot-docs center via
GITHUB_BLOB_BASE where it goes deeper — it is the Copilot-native manual and is NOT
absorbed), and the engines (`bin/copilot_pricing.py`, `bin/copilot_usage.py`,
`bin/copilot_execute.py`, `bin/copilot_ralph.py` — read argparse source only).
Copilot-specific honesty: AI Credits are money (`usd_per_credit` is data — never quote
its value); never present a specific model id as a recommendation (tier words only —
mirroring the skills' own law); the `### Cost & safety` section must distinguish
free/read-only operations from AIC-spending dispatches (`copilot -p` spends — the
repo's own tests never invoke it, and neither may an example imply it's free).

Acceptance: 12 files, six sections each; `check` exits 0; spliced; full suite green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && for n in architect bench-routing context-weight effort escalate execute frontier-check goliath journal lessons-loop route usage; do f="docs-src/fragments/skills/copilot/$n.md"; for h in '### What it does' '### When to reach for it' '### Worked example' '### Failure modes & fallbacks' '### Cost & safety' '### Related'; do grep -qF "$h" "$f" || { echo "MISSING $h in $f"; exit 1; }; done; grep -q '## In practice' "docs-site/skills/copilot/$n.md" || { echo "NOT SPLICED: $n"; exit 1; }; done && python3 bin/docs_build.py check && python3 -m unittest discover -s tests 2>&1 | tail -2
```

### T14 — Codex fragments: the remaining 11
- id: T14
- title: Author docs-src/fragments/skills/codex/<name>.md for 11 skills
- status: done
- model: sonnet
- depends: T13

Create exactly: `architect.md`, `bench-routing.md`, `context-weight.md`, `effort.md`,
`escalate.md`, `execute.md`, `frontier-check.md`, `journal.md`, `memory.md`,
`route.md`, `usage.md` under `docs-src/fragments/skills/codex/` (doctor exists from
T7). Then build + stage. No other edits.

Same template/grounding contract, Codex sources: `docs/CODEX-HARNESS.md`,
`docs/EFFORT-DIAL.md`, the skills' own bodies, and engines (`bin/codex_pricing.py`,
`bin/codex_usage.py`, `bin/codex_execute.py` — argparse source only). Codex-specific
honesty (the repo's law, verbatim in spirit): subscription Codex runs are
usage-limited, not token-billed — every dollar figure is a labeled API-equivalent
relative-burn proxy, never a bill; GPT-5.6 model ids are best-effort per the data
file's `model_ids_note` — fragments must say "as listed by `/model`" rather than assert
an id; the root-resolution proof ritual (`POLYTROPOS_ROOT`, doctor remedy) is worth a
plain-language explanation in `### What it does` or `### Failure modes & fallbacks`
since every Codex skill opens with it.

Acceptance: 11 files, six sections each; `check` exits 0; spliced; full suite green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && for n in architect bench-routing context-weight effort escalate execute frontier-check journal memory route usage; do f="docs-src/fragments/skills/codex/$n.md"; for h in '### What it does' '### When to reach for it' '### Worked example' '### Failure modes & fallbacks' '### Cost & safety' '### Related'; do grep -qF "$h" "$f" || { echo "MISSING $h in $f"; exit 1; }; done; grep -q '## In practice' "docs-site/skills/codex/$n.md" || { echo "NOT SPLICED: $n"; exit 1; }; done && python3 bin/docs_build.py check && python3 -m unittest discover -s tests 2>&1 | tail -2
```

### T14b — Two provenance fixes from the Phase 5 review (executor-added; do before T17)
- id: T14b
- title: Fix the unverifiable context-weight figures and the expired intro-pricing clause
- status: done
- model: sonnet
- depends: T14

Added by the executor from the P5 review's Findings 1 and 2. Both are publication-honesty
problems on pages about measurement and money, and T17 is the last gate before CI deploys.
Edit ONLY `docs-src/fragments/skills/claude/context-weight.md` and
`docs-src/fragments/skills/claude/cost-report.md`, then rebuild. No skill file, no test, no
other fragment.

1. **F1 — three measured figures with no reader path to verify them.**
   `context-weight.md` publishes `peak 99% of window (993,900 of 1,000,000 tokens)`,
   `avoidable (tool-ingested) mass: 74,160 est. of 993,900 (7%) — top source: Bash`, and
   `8.4MB → ~450 tokens, a ~4,600× reduction`. They are GENUINE — quoted verbatim from
   `skills/context-weight/SKILL.md` at HEAD and verified twice against git history. But Phase 4's
   T9 removed both passages from the working-tree card, and the executor confirmed the figures now
   appear in **zero** files anywhere in the committed tree outside this fragment. TEMPLATE.md's
   six-source list does not include git history or kit NOTES, so as published a reader (or a
   future reviewer) cannot trace them, and nothing guards a quoted engine-output shape the engine
   may stop producing.
   The placement is right — D1 says a concrete anecdote belongs on the site, not in the card — so
   this is a provenance problem, not a layer problem. Fix it EITHER by (a) keeping the figures and
   labelling them honestly as one recorded development session's measurement, so a reader knows it
   is an illustration rather than something they can reproduce, OR (b) stating the lesson and the
   compression ratio without the session-specific token counts. Do not silently drop the point —
   the reframe (cache reads are usually the cache working, resident-context×calls is the real
   driver) is the fragment's most valuable content.
2. **F2 — an expired pricing regime named on a money page.** `cost-report.md:46`, inside
   `### Cost & safety`, says "Sonnet 5 intro pricing applied by date". `data/pricing.json`'s
   `models.claude-sonnet-5.intro_pricing.until` is **2026-08-31** — that window has closed. The
   sentence traces verbatim to `skills/cost-report/SKILL.md:24` so it is not fabricated, and the
   mechanism claim stays true for historical messages, but it is the only fragment of 39 naming a
   pricing REGIME rather than a mechanism, in the exact section TEMPLATE.md forbids stale numbers
   in. Replace with a mechanism statement — e.g. priced from `data/pricing.json` at run time,
   including any dated intro-pricing window, never a number hardcoded here.

Finish with `python3 bin/docs_build.py build` and confirm `check` exits 0.

Acceptance: both fixed; both fragments still inside 150-550 total / <=450 prose; `check` exits 0;
full suite exactly 10 errors (all `LedgerJoinTests`) and ZERO failures.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && ! grep -q 'Sonnet 5 intro pricing' docs-src/fragments/skills/claude/cost-report.md && python3 bin/docs_build.py check && python3 -m unittest discover -s tests -p 'test_docs_*.py' 2>&1 | tail -2
```

## Phase 6 — Front door & wiring

### T15 — Hand-authored core pages: getting started, concepts, workflows, landing rewire
- id: T15
- title: Author the newcomer funnel pages and complete the nav
- status: done
- model: opus
- depends: T14, T6

Create under `docs-site/`: `getting-started/index.md` (choose your harness),
`getting-started/claude.md`, `getting-started/copilot.md`, `getting-started/codex.md`,
`concepts/index.md`, `concepts/billing-modes.md`, `concepts/the-one-constraint.md`,
`concepts/architect-execute-measure.md`, `concepts/effort-and-context.md`,
`workflows/index.md`, `workflows/first-route.md`, `workflows/run-a-kit.md`,
`workflows/measure-the-savings.md`. Edit `docs-site/index.md` (full landing rewire with
internal links) and `mkdocs.yml` (nav sections `Getting started`, `Concepts`,
`Workflows` between Home and Skills). Nothing under the generated roots; no `docs/`
edits.

These are the site's ONLY hand-authored pages — they are the funnel, and they must be
excellent. Content contracts:
- **Getting started, per harness**: prerequisites, the real install commands (Claude:
  the marketplace add/install pair from README §Install; Copilot/Codex:
  `python3 bin/harness_select.py install --harness …` per their harness docs — copy
  commands from the sources, never from memory), a first invocation, and what success
  looks like. Each page links its harness's skills index and the relevant deep dives.
- **Concepts**: distill README + `docs/HOW-IT-WORKS.md` §§1–3 and 5 into short pages
  (300–700 words each) that LINK the deep dives rather than duplicate them; the
  billing-modes page must carry the api-vs-subscription "opposite goals" framing and
  the mode-attaches-to-the-question subtlety; the one-constraint page carries the
  "nothing switches the main session's model" fact and its two programmable levers.
- **Workflows**: task-shaped walkthroughs (route one task; architect→execute a kit;
  prove the savings with the scorecard) that name real commands and link the per-skill
  pages at each step.
- **No numeric prices anywhere** — link `data/pricing.json` on GitHub or the deep-dive
  snapshots (which carry their own labeled `cached_date`).
- Every internal link must resolve (offline link test enforces this mechanically).

Acceptance: 13 new pages + rewired landing; nav complete and passing the nav test;
no page duplicates a deep dive at length (spot rule: any passage over ~3 sentences
that exists verbatim in `docs/*.md` should be a link instead); full suite green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && for f in getting-started/index.md getting-started/claude.md getting-started/copilot.md getting-started/codex.md concepts/index.md concepts/billing-modes.md concepts/the-one-constraint.md concepts/architect-execute-measure.md concepts/effort-and-context.md workflows/index.md workflows/first-route.md workflows/run-a-kit.md workflows/measure-the-savings.md; do test -f "docs-site/$f" || { echo "MISSING $f"; exit 1; }; grep -q "$f" mkdocs.yml || { echo "NOT IN NAV: $f"; exit 1; }; done && python3 -m unittest discover -s tests -p 'test_docs_site.py' -v && python3 -m unittest discover -s tests 2>&1 | tail -2
```

### T16 — Wire the site into README.md and SETUP.md
- id: T16
- title: Add the published-site pointers (pinned text, mechanical)
- status: done
- model: sonnet
- depends: T15

**EXECUTOR AMENDMENT (P4 review Finding 3 — read before starting).** Re-pinned from haiku to
sonnet, because this task walks into the same structural trap that deferred T10's enrich, and
its original brief called it "pinned, mechanical" while warning only about
`tests/test_harness_update.py`. The trap: `copilot-docs/manifest.json` declares an
`existing-guides` source set containing `README.md`, consumed by three generated pages
(`README.md`, `COSTS.md`, `WORKFLOWS.md`). **Editing README.md stales all three and fails
`test_copilot_docs_content`**, exactly as any Copilot SKILL.md edit does — and
`copilot-docs/**` is read-only to this kit, so the acceptance "full suite green" is
UNACHIEVABLE for the README half until the user rules on that coupling.
`SETUP.md` is in NO source set and is safe to edit.
So: **do the SETUP.md pointer normally. For the README half, check whether the pending
copilot-docs decision has been recorded in NOTES.md; if it has not, STOP and report the README
insertion as deferred — do not run `bin/copilot_docs.py build`, do not edit any test, and do not
improvise a workaround.** A verified stop-and-report here is a success, not a failure.

Edit exactly two files, with pinned insertions — change nothing else in them.

1. `README.md`: insert, immediately after the paragraph line beginning
   `A Claude Code plugin that picks the right model per task,` (and its trailing blank
   line), the following paragraph exactly as written inside this fence (the fence
   itself is not inserted), followed by a blank line:

   ```
   **The manual — full documentation site:** <https://agentmc15.github.io/polytropos/> — every skill on every harness (Claude Code, Copilot CLI, Codex CLI), getting-started guides, workflows, and deep dives. Generated from the skill files themselves and rebuilt on every push to `main` (drift-gated by `tests/test_docs_site.py`).
   ```

2. `SETUP.md`: insert, immediately after the first paragraph — the one whose last
   sentence reads (backticks are in the file): you re-run the installers rather than
   copying `~/.claude` or `~/.copilot` over. — and its trailing blank line, the
   following paragraph exactly as written inside this fence, followed by a blank line:

   ```
   Prefer reading in a browser? The full manual lives at <https://agentmc15.github.io/polytropos/>, built from this repo by `.github/workflows/docs-site.yml`. Local preview: `python3 -m venv /tmp/ptdocs && /tmp/ptdocs/bin/pip install -r docs-src/requirements.txt && /tmp/ptdocs/bin/mkdocs serve` — the venv is throwaway, never a repo dependency.
   ```

Gotchas: `tests/test_harness_update.py` asserts pricing `cached_date` strings appear in
README — you are only ADDING a paragraph, so this holds; do not renumber, reflow, or
"improve" anything else; CLAUDE.md is NOT edited by this task (its docs-site invariant
was placed by the architect and `tests/test_guardrails_layout.py` gates its size).

**EXECUTOR AMENDMENT 2 — the verify command was self-contradictory and is corrected above.**
As written it grepped README.md for the inserted URL, which can NEVER pass while the README
half is correctly deferred — the same defect shape the executor authored into T6b and had to
fix there. The corrected verify asserts the SETUP.md insertion landed AND that README.md is
byte-unchanged (`git diff --quiet README.md`), which is the honest acceptance for a
deferred-README run. If the user later rules that `copilot-docs` may be regenerated, restore
the README grep and drop the `git diff --quiet` clause in the same change that does the insert.

Acceptance (amended): the SETUP.md insertion verbatim at its pinned anchor, README.md
byte-unchanged and its insertion reported as deferred, diffs touching only SETUP.md, full
suite green at the documented baseline.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && grep -q 'agentmc15.github.io/polytropos' SETUP.md && git diff --quiet README.md && python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -v && python3 -m unittest discover -s tests 2>&1 | tail -2
```

### T17 — Venv smoke build: prove `mkdocs build --strict` passes
- id: T17
- title: Build the site for real in a throwaway venv
- status: done
- model: sonnet
- depends: T16

No repo file edits expected. In a temp dir OUTSIDE the repo, create a venv, install
`docs-src/requirements.txt`, and run `mkdocs build --strict` against the repo's
`mkdocs.yml` with `--site-dir` pointed at the temp dir (never write `site-build/`
inside the repo, even though it is gitignored). If the build surfaces a generator gap
(a broken link or bad construct in a GENERATED page), fix `bin/docs_build.py`, rebuild,
re-run tests, and note the fix; if in a HAND page, fix that page. Never hand-edit a
generated page. If pip cannot reach an index (offline sandbox), mark this task
`blocked` with the exact error captured in NOTES.md — the user runs the same commands,
or the first CI run is the proof. Do not soften: a skipped build is a blocked task, not
a pass.

Acceptance: the strict build exits 0 and produced an `index.html`, with the tree left
clean (`git status --porcelain` unchanged vs before the task, unless a genuine
generator fix was needed and verified).

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && V="$(mktemp -d)" && python3 -m venv "$V/venv" && "$V/venv/bin/pip" install -q -r docs-src/requirements.txt && "$V/venv/bin/mkdocs" build --strict -f mkdocs.yml --site-dir "$V/site-build" && test -f "$V/site-build/index.html" && rm -rf "$V" && python3 bin/docs_build.py check
```

### T17b — Three reader-facing fixes from the Phase 6 review (executor-added)
- id: T17b
- title: Restore the calibrating clause, correct the suite claim, and stop over-promising the consult
- status: done
- model: sonnet
- depends: T17

Added by the executor from the P6 review's F1, F3 and F4. All three mislead a reader; all three
are small. Edit ONLY `docs-src/fragments/skills/claude/context-weight.md`,
`docs-site/getting-started/index.md`, and `docs-site/workflows/run-a-kit.md`, then rebuild.

1. **F1 (HIGH) — the surviving sentence inverts the measurement it replaced.** The source said
   the avoidable mass was `74,160 est. of 993,900 (7%)` and then calibrated it: *"It's
   deliberately not most of the window: assistant output and user input make up the rest, and
   neither PREVENT nor PRUNE touches those."* The fragment now says the avoidable mass "traced
   **mostly** to a single tool — Bash". That is literally true of the avoidable SLICE, but a
   reader takes away that prevention is the dominant lever, which is the opposite of what the
   measurement showed. This is the page about measurement honesty, so the inversion matters more
   here than anywhere else on the site. Restore the calibration QUALITATIVELY — the avoidable,
   tool-ingested slice was a small fraction of a near-full window, most of which was assistant
   output and user input that neither prevent nor prune can touch, and Bash was the top source
   *within that slice*. No figures (TEMPLATE.md line 127 bans ratios and the counts are no longer
   traceable to any sanctioned source), and keep the graphify point already there.
2. **F3 — the newcomer funnel walks a stranger into a red suite.** `getting-started/index.md`
   tells a first-time reader to run `python3 -m unittest discover -s tests` and says "a green
   test run is the whole build step." On today's `main` that prints
   `FAILED (errors=10, skipped=2)` — pre-existing calendar rot in `LedgerJoinTests` fixtures,
   which this kit deliberately did not fix. Reword so the success signal is accurate: say what a
   reader should actually expect to see and what would genuinely indicate a problem. Do not
   claim the suite is green when it is not, and do not silently drop the step.
3. **F4 — a spending operation described as automatic when it is offered.** `run-a-kit.md:60`
   says a twice-failed task "gets one frontier consult". `skills/execute/SKILL.md:277` says the
   loop **offers** it, and only acts without asking when the autonomy dial is `auto`; the default
   is `advisory`, and it is additionally capped by PLAN's optional `max-escalations`/
   `max-consults`. Over-promising automation on the one operation that spends frontier money is
   the wrong direction to be wrong in. Two sentences: it is offered by default, automatic only
   under `auto`, and subject to the kit's budget dial if one is declared.

Finish with `python3 bin/docs_build.py build` and confirm `check` exits 0.

Acceptance: all three corrected; the context-weight fragment still inside 150-550 total /
<=450 prose and still carrying no figures; `check` exits 0; full suite exactly 10 errors (all
`LedgerJoinTests`) and ZERO failures.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && ! grep -q 'traced mostly to a single tool' docs-src/fragments/skills/claude/context-weight.md && ! grep -q 'green test run is the whole build step' docs-site/getting-started/index.md && ! grep -q 'It gets one frontier consult' docs-site/workflows/run-a-kit.md && python3 bin/docs_build.py check && python3 -m unittest discover -s tests -p 'test_docs_*.py' 2>&1 | tail -2
```

