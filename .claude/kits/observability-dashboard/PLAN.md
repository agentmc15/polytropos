# PLAN — observability-dashboard: one offline HTML page over the ledger, the scorecard, the telemetry and the evals

autonomy: advisory
budget: max-dispatches=22 max-escalations=4 max-consults=3
roles: red-team security-auditor
workflow: extended

## Goal

The user asked for "an observability and telemetry and data dashboard that takes data from the
ledger and logs and scorecard and that is currently being [done] with the RSI". This kit builds
a new stdlib-only engine, `bin/dashboard.py`, that reads every store this repo already keeps —
the attempt ledger and its history projection, the routing scorecard over every checkout's
kit ledgers, the telemetry envelopes and journal digests, the workflow-evaluation runs with
their policy / approval / activation records and the training-data switches — and writes ONE
self-contained HTML file into the user's private data folder. They open it in a browser and
rebuild to refresh. The page is a presentation layer over what the owning engines already
output, with every honesty label those owners emit rendered verbatim; it is never a second
analysis authority, never a server, never a hosted artifact, never a terminal card.

The recursive-improvement work (RSI) is in flight on a Codex branch. The RSI panel therefore
lands as its own phase: what exists on `main` today is rendered now, and the record-consuming
task is gated on Codex's R02 read seam merging (D12).

## Done means (all checkable from the checkout root)

1. `python3 bin/dashboard.py demo` exits 0, builds from synthetic data in a temp directory it
   creates and removes, prints the page's temp path plus a one-screen summary, and leaves
   nothing behind — no real store read, no real store written, no process spawned.
2. `POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 bin/dashboard.py build --out-dir <tmp>
   --checkout <tmp-checkout> --projects-dir <empty-tmp> --no-git` writes `<tmp>/index.html`
   mode `0600` whose `<head>` carries exactly the CSP meta tag of D9, contains no `<script`,
   no external `src=`/`href=`, and renders every panel's absent state as text ("no ledger
   found", "never captured", "no evaluation runs") — never as a zero.
3. `python3 bin/dashboard.py build` with no flags lands `index.html` and `build.json` under the
   `dashboard` row of `python3 bin/runtime_data.py where`, `0700` directory, `0600` files, and
   `git status --porcelain` shows nothing new inside the checkout.
4. The real data home (1,512 namespaces on 2026-09-25, 1,508 of them test residue) builds in
   bounded time: residue is counted and labelled, never opened beyond a shallow listing, never
   deleted, and the page shows every cap that was hit.
5. `skills/dashboard/SKILL.md` exists, prints the path and the `--json` summary, and never reads
   the HTML into a session; `python3 bin/docs_build.py check`, `python3 bin/copilot_docs.py
   check`, `python3 bin/sync_codex_surfaces.py check` and `python3 bin/release_gate.py check`
   all exit 0.
6. `POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -v` is green,
   `python3 bin/kit_contract.py graph --kit .claude/kits/observability-dashboard` reports a
   valid graph, and `CLAUDE.md` is byte-identical to its state before the kit ran.

## Decisions (each with the why — executors follow these, not their own taste)

**D1 — Form: one self-contained HTML file, built by an engine, opened from `file://`.** The
user chose this over a live server, a hosted artifact and a terminal card. Everything is
inline: CSS in a `<style>` block, charts as inline `<svg>` rendered by Python, no `<script>`
at all in v1, no webfont, no CDN, no `<img src=http…>`, no `<link>`. The page cannot fetch
anything because its CSP forbids it (D9) and because nothing in it references a URL. Refresh
is a rebuild, not a reload — so staleness is a property of the file, and the page prints its
own build time at the top. Interactivity that would need JS (tabs, filters) is replaced by an
anchor navigation bar and `<details>` blocks; a later kit may add hash-pinned inline JS if a
real need appears, but v1 proves the page is complete without any.

**D2 — The dashboard is a consumer and a presentation layer, never an authority.** It renders
what owners output and computes nothing an owner already computes. Its own arithmetic is
limited to: counting things it enumerated (namespaces, files, records it was handed), taking
the difference between two dates (age), and picking the latest of a set of dated things. It
never prices, never sums costs, never ranks, never classifies a failure, never infers a
dispatch, never re-derives a first-try rate. R07 ("Independent analysis and attribution
report") on the RSI branch owns RSI analysis; `bin/routing_scorecard.py` owns routing math;
`bin/attempt_history.py` owns the join. Where an owner has no read API for something the page
needs, the rule is: a THIN read adapter inside `bin/dashboard.py` is allowed only when the
owner's record carries a pinned `schema_version`/`v` the adapter can gate on and the adapter
does nothing but load, version-check and select fields (D3 lists the three such adapters);
anything else is a stop-and-report, never a re-implementation of the owner's logic.

**D3 — Sources and the owner each panel reads through.** Every reuse is import-and-call via
the house sibling loader (`importlib.util.spec_from_file_location` on `Path(__file__).parent /
"<name>.py"`, the `bin/telemetry_snapshot.py` `_mod` shape); the dashboard shells out to
NOTHING except the two read-only `git` verbs of D4.

| Panel | Owner call(s) | What is rendered |
|---|---|---|
| Attempts (ledger + history) | `attempt_history.join_kits(kits_dir, store=<ns>/attempts)` → `attempt_history.summarize(records, notes, coverage)`; for namespaces with no matching checkout, `attempt_ledger.AttemptLedger(root, ns).events()` + `.open_attempts()` | records, by source, by harness × tier × result, unknown counts, `cost.by_basis` (one row per basis), `duration.by_basis`, `latest` per task, lineage counts, coverage, notes; raw event-kind counts and open attempts for unmapped ledgers |
| Routing scorecard | `routing_scorecard.assemble_history_card(tokens, projects_dir=…)` with one `label=path` token per discovered kits dir; `routing_scorecard.scan_kits(kits_dir)` → `routing_scorecard.build_roles_card(records, kits_dir, extra_notes=notes)` per kits dir (the `run_roles` bare-shape sequence) | tiers table, kits table, `dollars` block with `coverage` and `pricing_cached`, role quality, brief-defect kinds, reroutes, notes; roles aggregate table with "insufficient sample" as the owner prints it |
| Telemetry snapshots | `telemetry_snapshot.build_list_summary(store_dir)`, `telemetry_snapshot.read_source_snapshots(store_dir, source)` for the latest envelope per source | per-source count / first / last / latest status / latest labels; per latest envelope: `capture_date`, `period`, `status`, `labels`, `notes`, and a bounded set of HEADLINE payload fields per registered source (D7) |
| Journal digests | thin adapter: `journal/<YYYY-MM-DD>/digest.json`, gated on `schema_version == 1` (`journal_collect.SCHEMA_VERSION`, read from the module, never hardcoded) | per day: `totals.usd_priced` (labelled as the journal's own priced total), `totals.sessions`, `sources_active`, `unpriced_sources`; per source: `available`, `priced`, `sessions`, `usd`; NO free-text field (inbox items, `signals` prose) in v1 |
| Evals / policy / activation / training | `workflow_eval.list_runs(store_dir)`, `workflow_eval.read_envelope` + `workflow_eval.build_card`, `workflow_eval.policy_report(prefs_dir)`, `workflow_eval.approval_report(prefs_dir)`, `workflow_eval.activation_report(prefs_dir)`, `training_data.status(repo_root=<checkout>)` | run rows; per run (bounded) the card's `variants` with `below_floor`, `spend`, `sample`, `labels` verbatim, `ranking` ONLY when the owner set it non-`None`; policy in force / history versions / proposals with decisions; approvals with states and refusals; activation scopes and `confined_dispatch_wired`; training switches, store path, notes |
| Kits in flight (checkout-local) | `kit_contract.parse_tasks(text)` + `kit_contract.validate_graph` / `kit_contract.graph_state` per kit dir | per kit: task status counts and graph state; per checkout: `.claude/kits/*` and `tasks/kits/*` |
| RSI (Phase 4) | presence of `bin/recursive_improvement.py` in each checkout, its `*_VERSION` constants read as data; the `tasks/kits/recursive-improvement` kit through the kits-in-flight path and `attempt_history.notes_records`; records ONLY through the read seam R02 lands (T11) | engine present/absent, contract versions, R-task statuses and outcome lines, and until T11: the sentence "no RSI records exist yet — R02 (durable links and history projection) has not landed on main" |

Three thin adapters exist and no more: the journal digest reader (above), the residue
classifier (D4), and the RSI presence probe (D12). Each is version- or shape-gated and renders
"unknown version, not rendered" for anything it does not recognise.

**D4 — Scope is every checkout, and namespaces are mapped one way.** `bin/runtime_data.py`
namespaces the data home per checkout as `<basename>-<sha256(realpath)[:8]>`; the digest
cannot be reversed, so the dashboard maps namespaces by hashing candidate checkout roots.
Candidates come from four places, in this order: the PRIMARY checkout — the git toplevel
of the working directory (`git rev-parse --show-toplevel` through `proc_runner`, falling
back to the working directory itself), never `PLUGIN_ROOT`, because a skill runs the
engine from the plugin cache and a cache is not a checkout — then every `--checkout PATH`
flag (the skill always passes the session's repo), the optional `checkouts` list in
`<dashboard store>/config.json` (user-authored, the `journal/config.json` precedent), and the
worktrees of every candidate so far from `git worktree list --porcelain`, run in each
candidate checkout and never in `PLUGIN_ROOT` (the plugin cache when the skill runs the engine).
Those two verbs are the engine's only subprocesses: each runs ONLY through `proc_runner.run([...],
cwd=<checkout>, timeout=GIT_TIMEOUT_SECONDS)`, both are read-only (`release_gate.GIT_READ_VERBS`
precedent), `--no-git` disables both, and either failing is a note rather than an error. For each candidate checkout C the
namespace roots are `C` and `C/tasks/kits`, because `attempt_ledger.kit_repo_root` maps a
`tasks/kits/<slug>` kit (the Codex planning kits) to `tasks/kits` — that is why the real data
home holds a `kits-<digest>` namespace beside `polytropos-<digest>`. A namespace matching a
candidate is labelled with the scrubbed checkout path; one matching nothing is "unmapped" and
is read only through the ledger owner with shallow stats; one matching the residue heuristic
is "residue". The residue rule (measured 2026-09-25: 1,508 of 1,512 namespaces) is a
HEURISTIC and says so on the page: directory name matches
`RESIDUE_NAMESPACE_RE = ^tmp[a-z0-9_]{8}-[0-9a-f]{8}$` (a `tempfile` basename plus the digest)
AND its top-level entries are a subset of `{"attempts"}`. Residue is counted, listed as a
count, excluded from every total, and never opened deeper than that one listing. The
dashboard never deletes anything, residue included — the cleanup is the user's separate call.

**D5 — Every scan is bounded, and every cap hit is shown.** Module constants, each with a
comment stating why the number: `MAX_NAMESPACES_LISTED` (the shallow listing over all
namespaces — high enough for today's 1,512 with room, so the residue COUNT is exact),
`MAX_NAMESPACES_READ` (mapped + unmapped namespaces read in depth, mapped first),
`MAX_LEDGER_BYTES` (a ledger file larger than this is skipped with a note rather than
handed to `events()`, whose reader loads the whole file), `MAX_KITS_PER_DIR`,
`MAX_EVAL_RUNS_RENDERED`, `MAX_JOURNAL_DAYS`, `MAX_TELEMETRY_ENVELOPES_PER_SOURCE`. Every cap
that truncates something appends a note to that panel AND to the page-level "bounds" section
AND to `build.json`. The point is that a page which silently shows less is worse than one
that shows less and says so; a reader must be able to tell "there is nothing" from "I stopped
looking".

**D6 — Output: a new `dashboard` store, written by `bin/dashboard.py` only.** The repo's law is
one store per engine, outside the tree, resolved through `bin/runtime_data.py`; no existing
store may be written by a second engine, so the page cannot live under `telemetry/` or
`journal/`. `"dashboard"` is appended to `runtime_data.STORES`; the out dir is
`runtime_data.store_path("dashboard", <primary checkout>)`, resolved inside `main` at call
time — never at import (a parse-time default captures the wrong environment) and never
against `PLUGIN_ROOT` (the page belongs to the checkout being observed, and the plugin
cache must never own a store); the store holds `index.html` and `build.json` (the
receipt: `schema_version`, built-at, data home (scrubbed), checkouts, namespace counts by
class, per-panel source dates, caps hit, notes). `build.json` carries an integer
`BUILD_SCHEMA_VERSION = 1` on the `telemetry_snapshot.STORE_SCHEMA_VERSION` precedent and is
NOT registered in `release_gate.VERSION_SOURCES` — deliberately, because Codex's RSI branch
edits that tuple and the generated block beside it, and a receipt is not a contract another
engine consumes. Every write goes `runtime_data.ensure_private(root)` then
`safe_paths.confined_replace(root, "index.html", data, what="dashboard page", mode=0o600)`
(atomic replace, `O_NOFOLLOW`, never a hand-composed path); `--out-dir DIR` is the SAME writer
over a caller-selected root and is how every test writes. Because the page aggregates every
namespace but lands in the primary checkout's namespace, the page says which checkout built
it. Consequences this kit must carry in the same task as the store: a root-anchored
`/dashboard/` rule in `.gitignore` (`tests/test_privacy_layout.py` derives its list from
`STORES` and `release_gate packaging` fails without the rule), a row in `docs/PRIVACY.md`'s
table and its store lists, "Nine stores" → ten in `docs/REFERENCE.md` (census row and prose),
the store sentence in `SECURITY.md`, `python3 bin/release_gate.py build` (the private-store
table in `docs/RELEASE.md` is generated) and `python3 bin/docs_build.py build` (the deep-dive
mirrors of those docs).

**D7 — Honesty rendering is the contract, stated once here and enforced by tests.**
(a) Cost bases are separate facts: `attempt_history.COST_BASES` and `DURATION_BASES` render as
one row per basis with the basis named, and no cell anywhere on the page adds two bases, two
harnesses or two owners together — a "total" appears only when an owner emitted it, under the
owner's own label. (b) A Codex subscription figure is an "API-equivalent relative-burn proxy,
never a bill" and the page prints the owner's proxy label beside it every time; `billed_usd`
null stays "null (usage-limited)". (c) Unknown is the word `unknown` — never `0`, never `$0.00`,
never an empty cell; absence is "absent" / "never captured" / "no runs" with the owner's
absence label when it has one. (d) Every panel header shows source (engine name), the
observation or capture date the owner recorded, age in days relative to the build, and the
panel's notes; a stale telemetry source says "run `python3 bin/telemetry_snapshot.py` to
refresh". (e) Owners' `labels`/`notes` lists render verbatim, escaped, in full — a label is
never shortened, softened or dropped to make a table fit; the `NOT_A_RANKING` and
`BELOW EVIDENCE FLOOR` labels from `workflow_eval` are the canonical example. (f) Truncation
is shown (D5). (g) The headline payload fields per telemetry source are a fixed allowlist in
the engine (`cost_report`: `totals.usd`, `mode`, `pricing_cached_date`; `codex_usage`:
`branch`, `priced`; `copilot_usage`: `totals.usd`, `totals.aic`; `context_overview`: each
section's `found`; `routing_history`: `dollars.coverage`; `attempts`: the coverage labels) —
a field missing from a payload renders `unknown`, and a payload of an unregistered source
renders labels only.

**D8 — Privacy: the page holds personal data and stays on this machine.** It carries dollar
figures, task titles, kit names, repo paths and namespace digests. Rules: every string is
`html.escape`d; every absolute path is scrubbed in the render layer by `scrub(text, home)`
which replaces the user's home prefix with `~` (the `home` value is resolved once in `main`
via `os.path.expanduser("~")` — the `codex_usage.py` seam convention; pure functions take it
as a parameter and tests pass a fake); the ledger's bounded `report` and `tail` text fields are
NOT rendered (counts, `signature`, `failures`, `rc` and `outcome` are); no transcript, prompt
or message text can appear because no owner the dashboard calls returns any; journal free
text (`inbox`, `signals` prose) is not rendered in v1 even though the owner already redacted
and bounded it — nothing on the page should need `bin/redact.py` because nothing free-form
reaches it, and the test that greps the page for the fixture's fake home path and for a
canary string planted in a fixture inbox is the enforcement. The skill (D11) never pastes,
publishes or attaches the page; there is no "share" path and `docs/PRIVACY.md` gains the
store row so the bump-and-prune runbook covers it.

**D9 — HTML quality bar.** `<meta http-equiv="Content-Security-Policy" content="default-src
'none'; style-src 'unsafe-inline'; img-src data:">` exactly, in `<head>` before any other
element that could load; `<meta name="viewport" …>`; one `<style>` block using CSS custom
properties for colours with a `prefers-color-scheme: dark` override and a `body` background
set explicitly in both; a system font stack; `max-width` content column with 16px side
gutters and `overflow-x: auto` on every table wrapper so a phone-width window never scrolls
horizontally; every chart is an inline `<svg viewBox=…>` with `role="img"`, a `<title>` and a
`<desc>`, drawn from the same rows as an ADJACENT `<table>` that carries the numbers (the
chart is never the only place a number lives); no `<script>`; anchor navigation to panel ids;
`<details>` for long tables. Rendering is deterministic for the same inputs except the
build-time line, which tests strip before diffing two builds.

**D10 — Reuse by import; the owners are never edited by this kit.** `bin/attempt_ledger.py`,
`bin/attempt_history.py`, `bin/recursive_improvement.py` (on the branch), and everything under
`tasks/kits/` are being edited by Codex concurrently and are untouchable here — as are
`bin/routing_scorecard.py`, `bin/telemetry_snapshot.py`, `bin/workflow_eval.py`,
`bin/training_data.py`, `bin/journal_*.py`, `bin/kit_contract.py`, `bin/runtime_data.py`
beyond the one-tuple `STORES` append, `bin/safe_paths.py`, `bin/proc_runner.py` and every
pricing file. If an owner's signature or return shape differs from a brief, the owner is
authoritative: adapt only the dashboard's adapter layer, keep the brief's SEMANTICS (verbatim
labels, no summing, unknown stays unknown), and record the delta in NOTES.md. Tolerance is
structural: an owner raising, a store absent, a record with an unknown `v`/`schema_version`,
an undecodable file — each becomes a note on the panel, never a crash and never a guess.

**D11 — One Claude-side skill, no ports in v1.** `skills/dashboard/SKILL.md` (name
`dashboard`, `allowed-tools: Bash`) runs `build`, then relays the path and the one-screen
summary from `build --json`. Its context-hygiene law: never `cat`, `Read`, `grep` or otherwise
load `index.html` into the session (the page is for a browser; the summary is for the
session); never paste, publish, attach or upload the page or the receipt anywhere; opening
the file is the user's action, not the skill's (no `open`/`xdg-open`). Copilot, Codex and
Cursor ports are OUT of scope: the engine is a harness-neutral CLI any harness user can run,
and a port would touch three bundle rosters, their tests and `copilot-docs/` for no new
capability — the harness-update kit's single-source precedent (its D1). Consequences of a
new Claude skill, all in one task so the tree is never red between them: the "In practice"
fragment at `docs-src/fragments/skills/claude/dashboard.md` per `docs-src/fragments/TEMPLATE.md`;
a `### claude/dashboard` entry in `.claude/kits/docs-site/AUDIT.md` with the five fields in
pinned order and the disposition-summary counts updated (`tests/test_docs_audit.py` checks
the roster equals the live inventory); a `dashboard: skills/claude/dashboard.md` line in
`mkdocs.yml`'s Claude nav block; `tests/test_docs_build.py`'s `LiveTreeInventoryTests` Claude
count 15 → 16 (its own comment calls it a roster tripwire to re-derive when a skill lands);
`docs/REFERENCE.md`'s Claude-skill count and its skills section; then `python3
bin/docs_build.py build`. `copilot_docs.py` and `sync_codex_surfaces.py` are unaffected
because their rosters are the bundles'.

**D12 — Phasing, and how the RSI gate works.** Phases 1–3 deliver a useful, honest v1 from the
sources that exist on `main` today. Phase 4 is RSI: T10 renders what exists on `main` now —
whether `bin/recursive_improvement.py` is present in each checkout (it is not on `main` at
kit-authoring time; it is on `feat/rsi-evidence-foundation`), its `*_VERSION` constants read
as data by `importlib` when present, the `tasks/kits/recursive-improvement` kit's task
statuses and `outcome:` lines, and the plain sentence that no RSI records exist yet. T11
consumes RSI records through the read seam R02 ("Durable links, recovery and history
projection") lands, and is GATED: before dispatching T11 the orchestrator runs the gate
command in T11's brief (the module must exist on the executing checkout AND expose a read
function over stored RSI records; on 2026-09-25 R01's module is validators only and has no
store). If the gate fails, T11 is set to `blocked` WITHOUT a dispatch, with a plain NOTES.md
line naming the gate (not an `outcome:` line — nothing ran), and the kit is reported as
complete except T11; re-run execute after the RSI branch merges to `main`. Tolerance of
unknown or newer RSI record versions (render "unknown version, not rendered") is a T10
deliverable that T11 inherits, so a Codex schema bump can never crash the page.

**D13 — Roles: `red-team` and `security-auditor`, declared to test them against stated
risks.** The `--roles` card (2026-09-25) records no dispatch of either role in any kit, so
they are absent from the value table, not zero; this kit's two characteristic risks are
exactly their missions. The red-team attacks what acceptance never anticipated on a page
built from sparse, partly corrupt, residue-heavy data: unknown record versions, undecodable
files, a symlinked namespace, unicode in a task title, an empty data home, caps set to 1. The
security-auditor checks the fences a page can quietly break: a URL in the output, a `<script`,
a home path unscrubbed, a write outside the store, a real-home read in a test, a transcript
field rendered. `test-author` (measured 88% precision, 82% marginal rate) is NOT declared:
the kit's acceptance lines already pin the honesty contract as tests each task must write,
and the verifier at sonnet re-derives them; adding a third per-task role would push the
dispatch count past what the budget line allows. `tests/test_role_contract.py` pins the exact
set of kits declaring roles; the architect extended that dict with this kit in the same change
as this PLAN so the suite stays green — a future kit declaring roles extends it again.

**D14 — Model pins, from the routing history (pulled 2026-09-25).** sonnet 90% first-try
(187 outcomes), opus 90% (73), haiku 91% (33), no escalations recorded: cheap pins are safe
for well-specified work. Verifier is **sonnet** (recorded precision sonnet 94% vs haiku 60%);
reviewer **opus** (82% over 337 findings). Opus is pinned where a wrong micro-decision is a
privacy or safety defect rather than a bug: T2 (bounded enumeration, checkout discovery,
the private writer, scrubbing) and T10/T11 (tolerating a concurrent branch's contracts).
Everything else is sonnet; the documentation-only wiring task is haiku. The architect's own
brief-defect floor (contradictory-acceptance 24, stale-plan-decision 16, stale-pin 10,
unspecified-path 10) is why every brief below pins exact paths and function names, uses
content assertions rather than line numbers, and ends in a verify block that can fail.

**D15 — The one live harness-home read is the scorecard's own transcript pricing.** Usage and
cost numbers (`cost_report`, `codex_usage`, `copilot_usage`, `context_overview`) are rendered
from the TELEMETRY ENVELOPES, not recomputed — the dashboard is a consumer of stores, and the
page tells the user to run the snapshot when they are stale. The exception is the routing
history's dollars: kit ledgers live in checkouts, not stores, and the cross-kit verdict is
priced by `routing_scorecard` from Claude transcripts under its `projects_dir` seam (JSONL,
read-only, the owner's own code path). The dashboard passes its `--projects-dir` through
(default: the scorecard's own default) and offers `--no-transcripts`, which passes an empty
temp directory so the card renders "dollars n/a" with the owner's own label; tests always
pass a temp projects dir. No `*.db` is ever opened, and no other home-dir path is read.

**D16 — `CLAUDE.md` is not touched.** It is 15,992 of the 16,000 bytes
`tests/test_guardrails_layout.py` allows; the rules for this kit live in `GUARDRAILS.md`,
and the drift guard is a `KIT_SENTINELS` entry (T9) rather than a CLAUDE.md line. The
run-line the "How to run things" block would normally gain is deferred to a later trim of
that file — it is named as unfinished in T9 rather than squeezed in.

## Constraints

- Python stdlib only; `unittest` only; no pip, no pytest. Every test isolates the data home
  with `setUpModule` + `mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": tmp})` (the
  `tests/test_copilot_execute.py` idiom), builds synthetic namespaces and stores in temp dirs,
  pins `--projects-dir` to an empty temp dir, and carries zero `Path.home()`.
- Every verify block that runs the full suite runs it as
  `POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -v`, because the
  test-hygiene leak (`tests/test_copilot_budget.py`, `tests/test_codex_execute_policy.py`) is
  being fixed in a separate PR and kit execution must never add residue to the real home.
- Never invoke the real `claude` / `codex` / `copilot` / `agent` CLI; the engine's only
  subprocesses are the two read-only git verbs of D4, through `bin/proc_runner.py`.
- The engine writes only under its own store or `--out-dir`; it never writes, moves or
  deletes anything in any other store, any namespace, any harness home or the checkout.
- No hardcoded prices, model ids, pricing dates, plan facts or contract-version strings
  outside fixture-local synthetic values; tier and basis vocabularies are read from the owning
  modules (`attempt_history.COST_BASES`, `workflow_eval.EVAL_VERSION`,
  `journal_collect.SCHEMA_VERSION`, `telemetry_snapshot.SOURCES`) at run time.
- Do not commit, push, merge or create branches from a task; the orchestrator commits at green
  boundaries on the working branch.

## OUT OF SCOPE — executors must NOT

- Add any JavaScript, webfont, CDN reference, external stylesheet, image URL, iframe, form or
  network-capable element to the page, or any "share"/"publish"/"open in browser" behaviour
  to the engine or the skill.
- Recompute, re-price, re-rank or re-classify anything an owner already outputs; add analysis
  R07 owns; add a trend engine (`routing_scorecard --trend` and `trends/` stay as they are).
- Edit `bin/attempt_ledger.py`, `bin/attempt_history.py`, `bin/recursive_improvement.py`,
  anything under `tasks/kits/`, any owner listed in D10, any pricing file, any generated mirror
  by hand, any skill's YAML frontmatter other than the new skill's own, any existing kit's
  NOTES.md, or `CLAUDE.md`.
- Port the skill to Copilot, Codex or Cursor; touch `copilot/`, `codex/`, `cursor/`,
  `copilot-docs/` or their roster tests.
- Delete, move, compact or "clean up" residue namespaces or any store content; fix the test
  leak (that is the separate PR).
- Render transcript, prompt, report or inbox text; render an unscrubbed home path.
- Read the RSI worktree (`~/Developer/reposV2/polytropos-rsi-plan`) or run anything in it;
  the branch is inspected only via `git show feat/rsi-evidence-foundation:<path>` and
  `git log main..feat/rsi-evidence-foundation`.

## Risks and tripwires

- **R1 — Concurrent Codex edits to the ledger, the history projection and the RSI module.**
  Tripwire: any diff this kit produces in `bin/attempt_ledger.py`, `bin/attempt_history.py`,
  `bin/recursive_improvement.py` or `tasks/kits/**` is a fence violation — revert and report.
  Before any merge of this kit's branch, `git fetch` and compare against `main`; a rebase or
  merge conflict in those files means stop and report to the user, never resolve it in a
  task.
- **R2 — Generated-doc conflicts with the RSI branch.** Both this kit (D6) and Codex's
  branch rewrite the generated block of `docs/RELEASE.md` and its mirror
  `docs-site/deep-dives/release.md`. Tripwire: a conflict there is resolved ONLY by
  regenerating (`python3 bin/release_gate.py build` then `python3 bin/docs_build.py build`),
  never by hand-merging hunks. `release_gate.py check` exits 3 on a hand-merged block.
- **R3 — A silent zero.** Tripwire: any `or 0`, `.get(k, 0)`, `f"${x:.2f}"` over a value that
  may be `None`, or an empty cell in the page for a value the owner did not observe. The
  verifier and the red-team hunt this first; a fixture with a record whose `cost` is `None`
  must render the word `unknown`.
- **R4 — A cell that sums across bases, harnesses or owners.** Tripwire: any `sum(` in
  `bin/dashboard.py` over cost or duration values, or a "total" row the owner did not emit.
  Counting rows and files is the only summation allowed.
- **R5 — A page that can reach the network.** Tripwire: `<script`, `src=`, `href="http`,
  `href="//`, `@import`, `url(` in the output, or a missing/altered CSP meta. The test
  asserts each; the security-auditor reruns the check at every phase end.
- **R6 — Real-home reads or writes from tests or verify probes.** Tripwire: a test without
  the `setUpModule` data-home patch, a `Path.home()` outside `main`, a probe that runs
  `build` without `--out-dir` and `--projects-dir`, or a fixture under the real
  `~/Library/Application Support/polytropos`. The verifier greps for all four.
- **R7 — Unbounded scans over residue.** Tripwire: opening a residue namespace's
  `events.jsonl`, calling `events()` on a ledger over `MAX_LEDGER_BYTES`, or a build over the
  synthetic 1,500-residue fixture taking more than a few seconds. The test builds that
  fixture and asserts the residue count, the exclusion from totals and the "not opened"
  note.
- **R8 — Hand-edited generated docs.** Tripwire: `python3 bin/docs_build.py check`,
  `python3 bin/copilot_docs.py check` or `python3 bin/release_gate.py check` non-zero after a
  task; any diff under `docs-site/` or `copilot-docs/` not produced by the generator.
- **R9 — The CLAUDE.md byte ceiling.** Tripwire: any diff in `CLAUDE.md`. The kit adds
  nothing there (D16).
- **R10 — Roster and inventory tripwires in the suite.** `tests/test_role_contract.py`
  (kits declaring roles), `tests/test_docs_build.py` `LiveTreeInventoryTests` (Claude skill
  count) and `tests/test_docs_audit.py` (AUDIT.md roster) each pin a snapshot the kit
  changes. Tripwire: the suite going red on one of these after a task means the task
  forgot its paired edit (D11, D13); the fix is the paired edit, never loosening the test.
- **R11 — Sparse and stale data on the real machine.** The real primary namespace holds one
  telemetry day (2026-09-06), two journal digests and one evaluation run; other namespaces
  hold a single ledger each. Tripwire: a panel that renders an error, a crash or a zero
  instead of its absent/stale state on the real build (Done-means 3) — that build is the
  final smoke and its output is reported faithfully, not tidied.
- **R12 — The owner's shape differs from the brief.** Tripwire: an implementer finding that
  a named function, key or label differs from a brief stops and reports (the owner is
  authoritative, D10); the fix lands in the dashboard's adapter with a NOTES.md delta line,
  never in the owner and never by loosening a label.

## Handoff

Kit ready at `.claude/kits/observability-dashboard/`. Run `/polytropos:execute
observability-dashboard` from the daily driver; T11 stays gated until Codex's R02 merges to
`main`, and the executor recognises the gate by the command in T11's brief.
