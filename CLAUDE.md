# polytropos — executor guardrails

This repo is a Claude Code plugin (model routing + cost optimization). It is installed live at
user scope from this directory via a local marketplace — **skill files are runtime behavior, not
just docs**. Edit accordingly.

## Invariants (violating any of these is a wrong change, even if it "works")

Each rule is stated once; `docs/` and `SECURITY.md` carry the detail behind it. This file is
loaded into every session, so keep it a list of rules — not history, not rationale, not a
changelog.

- **Pricing data is the single numeric source of truth — one file per harness, never merged.**
  `data/pricing.json` (Claude), `data/pricing.copilot.json`, `data/pricing.codex.json`; no
  harness's config reads another's. Never hardcode prices, ratios, plan facts, credit values,
  model IDs, or pricing dates into skills, scripts, or bundle content — derive them at run time
  (the AIC unit itself is data: `billing_unit.usd_per_credit`). Codex model ids are best-effort
  (`model_ids_note`); corrections land in that file and nowhere else. `README.md` and `docs/`
  tables are labeled snapshots tied to a file's `cached_date` — change them only in the same edit
  as the file. A gloss beside its field name ("`cache_read_multiplier` (0.1×)") is fine in a
  skill; a standalone literal is not. Generated mirrors under
  `skills/{route,fable-check}/references/` are never hand-edited — regenerate with
  `python3 bin/sync_pricing_refs.py` (`tests/test_pricing_refs.py` fails on drift).
- **A subscription run is usage-limited, not token-billed.** Every dollar figure for a
  ChatGPT-plan Codex run is a labeled API-equivalent relative-burn proxy, never a bill:
  `billed_usd` stays null, the source stays `priced: false` / `usd: null`, and proxy dollars
  never enter a priced total or a digest's totals.
- **Never invoke the real `copilot` CLI from tests, kit verify commands, or anything run during
  execution** — and the same holds for `codex` and `claude`. Those calls spend the user's real
  credits and hit the network, and the user has live `~/.copilot`, `~/.codex`, and `~/.claude`
  homes. A dispatcher spawning its own CLI on the user's explicit run is the point; anything
  else is not. Every dispatcher (`bin/{copilot,claude,codex}_execute.py`, `bin/copilot_ralph.py`,
  `bin/journal_summarize.py`) takes an injectable runner; tests stub or mock every dispatch using
  temp stub executables and temp home dirs only; `--dry-run` / `--demo` are the sole sanctioned
  CLI smoke paths and spawn nothing.
- **Reading a harness home is read-only and JSONL-only.** `bin/copilot_usage.py`,
  `bin/codex_usage.py`, `bin/context_weight.py`, and `bin/journal_*.py` read `~/.claude`,
  `~/.copilot`, and `~/.codex` strictly read-only at run time — never a `*.db`/SQLite open, never
  a write, never a CLI invocation to gather.
- **The daily journal is read-only ingestion with gitignored output.** Output, inbox, and config
  live under gitignored `journal/`; the digest carries metadata only, never transcript text.
- **Python is stdlib-only** (`bin/`, `tests/`). No pip installs, no requirements files, no
  pytest. The docs site's own toolchain (below) is the one exception.
- **Skills resolve plugin files via `${CLAUDE_PLUGIN_ROOT}`**, with "relative to this SKILL.md"
  as the stated fallback (resolve to absolute before shelling out — bash cwd is not the skill
  dir). The one exception: commands written into `~/.claude/settings.json` (statusline) must be
  literal absolute paths — that env var doesn't exist outside plugin context.
- **One kit contract, one place: `bin/kit_contract.py`.** Task parsing, readiness, status
  writing, budget admission, run ids, and the outcome vocabulary are defined there ONCE and
  re-exported by the drivers. Never add a second copy to a driver — the three had 27 shared
  names, and extracting them surfaced three divergences nobody had noticed, including two
  drivers dispatching tasks whose dependencies were unfinished.
  `tests/test_kit_contract.py` fails if any implementation reappears in two drivers. What stays
  per-harness is what must: dispatch argv, the host's own loop, its escalation ladder, and its
  pricing file. A capability is only relied on when `primitives/harness-capabilities.json`
  records it verified — `unknown` there means no, and stays `unknown` until someone runs it.

- **The architect and execute skills share one kit contract — keep them in sync.** If you touch
  either `skills/architect/SKILL.md` or `skills/execute/SKILL.md`, re-check both against: layout
  `.claude/kits/<slug>/PLAN.md` + `TASKS.md` + `GUARDRAILS.md` (kit-scoped fences,
  architect-owned; execute reads it at setup) (+ `NOTES.md`, owned by execute); task fields `id`,
  `title`, `status`, `model`, brief, acceptance, verify; status vocabulary exactly
  `pending | in-progress | done | blocked`; phase headings; `depends:`/`independent:` marking;
  and the rule that a task's `model` field overrides the implementer agent's frontmatter at
  dispatch.
- **Never touch `~/.claude/` or anything outside this repo.** Do not re-install or refresh the
  plugin.
- **Do not commit or push** unless the user explicitly asks.
- **Every local store is personal data, written by its own engine ONLY, and lives outside the
  plugin tree.** `memory/` is gitignored user data; so are `telemetry/`, `benchruns/`,
  `journal/`, `prefs/`, `trends/`. Their default location comes from `bin/runtime_data.py` — a
  per-user application-data dir, per checkout, `0700`/`0600` — never a hardcoded path under the
  repo, because this tree is distributed, cached, and often cloud-synced. An in-tree store that
  already exists keeps being used; nothing is ever relocated or deleted automatically. Runtime
  code reaches a store only through that engine's explicit `--memory-dir`/`--store-dir`-style
  seam; every test and verify uses a temp fixture dir (memory also pins an explicit `--now`, and
  carries zero `Path.home()`), never a real store. Nothing may bulk-inject a store, its index, or
  an uncapped record set into a session's context — memory recall is pull-only, relevance-gated,
  and budget-capped by design, and carries each fact's provenance and scope so an imported
  observation is never rendered as an instruction. `.gitignore` carries a root-anchored
  `/memory/`; the leading slash is load-bearing so `skills/memory/` stays tracked.
- **User free text is redacted and bounded before it is persisted or sent to a model.** Inbox
  lines, and any future free-text field, go through `bin/redact.py`. Report what was caught by
  KIND and COUNT, never by value — and never write a sentence claiming no secret can get
  through: shape-matching cannot prove absence, and the old "nothing secret is ever written"
  line was true only about git.
- **A stored record is never hand-authored, backdated, or reconstructed from prose.** Capturing a
  still-existing source late is fine; fabricating an evaporated one never is. Telemetry envelopes
  (`telemetry/<source>/<YYYY-MM-DD>.json`) are dated by CAPTURE date, honesty labels (est.,
  unpriced, partial coverage) ride inside the record, and readers degrade with a note when a
  store is absent.
- **`bin/repo_bench.py` can spend real tokens — only behind `--live` plus an explicit `--max-usd`
  ceiling; `plan`/`demo` and every test spend nothing.** Tests stub every dispatch and `gh`
  runner and use fixture repos in temp dirs. Target repos are read-only by construction
  (allowlisted git verbs; sandboxes are history-free tree extractions). Verdicts below the
  evidence floor are never applied, and routing changes only through the explicit `apply` step.
- **Installation never overwrites what it does not own.** `bin/harness_select.py` classifies
  every destination before writing, restates that precondition at the moment it writes, and rolls
  back only bytes the same run wrote. It never writes `config.toml`, never overwrites a differing
  `AGENTS.md` or skill dir, and resolves `{{POLYTROPOS_ROOT}}` in `copilot/` and `codex/` bundle
  files to an absolute path at install time — the only place that substitution ever happens.
- **`bin/harness_update.py` check is strictly read-only; apply writes only the Copilot/Codex homes
  via `harness_select`'s own writers plus the repo's generated mirrors — never `~/.claude` (the
  remedy is printed, never executed), never pricing numbers or docs tables.** Codex prompts are
  plugin-generated mirrors, overwritten with every differing rewrite listed. Tests use temp
  fixture homes only.
- **One path helper, one execution boundary, one process runner.** Every write, read, or delete
  into a caller-selected root goes through `bin/safe_paths.py` — never a hand-composed
  destination path. Verify commands run under `bin/exec_policy.py`, whose `--exec-mode
  trusted-host` is the sole opt-out and reports itself as one. Every external process is started
  by `bin/proc_runner.py`, which validates the working directory, bounds wall time and output,
  gives the process its own group so nothing it spawned outlives it, and names each way a run
  can fail — never a bare `subprocess.run`, which inherits the launch directory and bounds
  none of that. `SECURITY.md` states what the three do and do not promise; keep it true when
  any of them changes.
- **graphify is an external, user-installed CLI (`uv tool install graphifyy`) — never vendored,
  never auto-installed, and never invoked by tests, verify commands, or kit execution.**
  `bin/graph_brief.py` only ever READS a graph.json; skill-sanctioned graphify subcommands are
  the offline set only (no `extract`/`label`/backends/`add`/`clone`/`watch`/`global`/platform-
  `install` hooks without explicit user opt-in). `/graphify-out/` stays gitignored.
- **Generated documentation is never hand-edited.** `docs-site/skills/` and
  `docs-site/deep-dives/` are written only by `bin/docs_build.py`, and `copilot-docs/` only by
  `bin/copilot_docs.py`. Edit the SOURCE (a SKILL.md, `docs/*.md`, `README.md`, `SECURITY.md`,
  `docs-src/fragments/`) and run that generator's `build`; both have drift tests that fail
  otherwise. `mkdocs.yml` + `docs-site/` are the one surface with a non-stdlib toolchain
  (mkdocs-material, installed only in CI or a throwaway venv). That toolchain is LOCKED, not
  ranged: `docs-src/requirements.txt` pins every transitive package with a sha256 and CI
  installs with `--require-hashes`; every Action is pinned to a full commit SHA with its
  version in a comment; deploy credentials live only in the deploy job. Never loosen one of
  those to make a build pass. Generated pages accept only the URL schemes in
  `copilot_docs.ALLOWED_URL_SCHEMES`. No SKILL.md ever points into `docs-site/` (site content is human-facing, never
  model-loaded), and no generator reads a home dir or a gitignored store.

## How to run things

Every engine takes `--help`. `demo` / `--demo` is always synthetic, offline, and spends nothing.

```bash
# from the repo root
python3 -m unittest discover -s tests -v   # FULL SUITE — run before claiming any script task done

# cost, routing, benchmarks
python3 bin/cost_report.py --days 30                 # transcript cost report (markdown to stdout)
python3 bin/session_cost.py                          # one session's cost + all-Fable counterfactual
python3 bin/routing_scorecard.py --demo              # routing quality; add --live/--history/--by-task/--trend/--roles
python3 bin/repo_bench.py demo                       # full benchmark pipeline: fixture repo, stub dispatch, all four oracles
python3 bin/repo_bench.py plan --repo . --models sonnet,haiku   # priced matrix + ceiling; only `run --live --max-usd` spends
echo '{"model":{"id":"claude-fable-5","display_name":"Fable 5"},"cost":{"total_cost_usd":1.23},"context_window":{"used_percentage":42},"rate_limits":{"five_hour":{"used_percentage":12},"seven_day":{"used_percentage":34}}}' | python3 bin/statusline.py

# per-harness pricing and usage
python3 bin/copilot_pricing.py est M claude-fable-5  # Copilot estimate (USD + AIC); also `knobs`, `prefs`
python3 bin/codex_pricing.py models --profile M      # Codex roster + burn index vs cheapest; also `knobs`
python3 bin/copilot_usage.py --days 30               # reads ~/.copilot read-only
python3 bin/codex_usage.py --days 30                 # reads ~/.codex read-only; honest unpriced fallback
python3 bin/copilot_ralph.py --demo                  # Ralph goal-loop mock (no model, no network, no AIC)

# journal, memory, telemetry, context
python3 bin/journal_collect.py --print               # today's digest (homes read-only; writes journal/)
python3 bin/journal_summarize.py --dry-run           # the prompts + routed model; spawns nothing
python3 bin/journal_askpack.py --print               # offline Teams/Outlook/Copilot-Studio ask-prompts
python3 bin/journal_plan.py check                    # next-day runbook: cards due/overdue today
python3 bin/memory_recall.py --demo                  # budget-capped recall: gate + stale + budget visible
python3 bin/memory_store.py review                   # staleness report over the gitignored store
python3 bin/telemetry_snapshot.py                    # capture today's snapshots; `--list` inspects the store
python3 bin/runtime_data.py where                    # where each store resolves; also `migrate`/`export`/`forget`
python3 bin/context_weight.py session                # what filled this window (--harness codex|copilot); also `demo`

# freshness, boundaries, generated docs  (installing is the user's action, not a dev command)
python3 bin/harness_update.py check                  # all-harness freshness card (exit 3 on drift); also `demo`
python3 bin/exec_policy.py check                     # what OS execution boundary this host enforces (exit 3 if none)
python3 bin/graph_brief.py demo                      # architect-grounding brief from a graphify graph.json
python3 bin/docs_build.py check                      # docs-site freshness (exit 1 on drift); `build` regenerates
python3 bin/copilot_docs.py check                    # Copilot doc center freshness; `build` regenerates
python3 bin/primitives.py check copilot/aesop.toml   # AI-primitive manifest validation (exit 2 on findings)
```

## When executing a kit task

- Run the task's **verify command yourself, from the repo root, before claiming done**. Your
  claim without its output counts as failure.
- The brief is authoritative. If it conflicts with repo reality (beyond shifted line numbers),
  stop and report the discrepancy — do not improvise a different fix.
- Check `.claude/kits/<slug>/PLAN.md` for the active kit's out-of-scope fence before starting.
  Each kit's own fences live in `.claude/kits/<slug>/GUARDRAILS.md` — read it together with
  that kit's PLAN.md before starting any of its tasks. Those fences are kit-scoped law: they
  bind only while that kit's tasks run and never generalize to other work. The Invariants
  above are the only always-on rules.
