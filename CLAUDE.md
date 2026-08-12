# polytropos — executor guardrails

This repo is a Claude Code plugin (model routing + cost optimization). It is installed live at
user scope from this directory via a local marketplace — **skill files are runtime behavior, not
just docs**. Edit accordingly.

## Invariants (violating any of these is a wrong change, even if it "works")

- **`data/pricing.json` is the single numeric source of truth.** Never hardcode prices, price
  ratios, model IDs, or pricing dates into skills or scripts — instruct/compute from pricing.json
  at run time. Exception: `README.md` and `docs/` tables are labeled snapshots tied to
  `cached_date`; update them only together with pricing.json. A gloss directly beside its field
  name (e.g. "`cache_read_multiplier` (0.1×)") is acceptable in skills; a standalone literal is not.
  Generated mirrors `skills/route/references/pricing.json` and `skills/fable-check/references/pricing.json`
  keep aesop-vendored copies of those skills self-contained — never edit a mirror by hand;
  regenerate with `python3 bin/sync_pricing_refs.py` whenever `data/pricing.json` changes
  (`tests/test_pricing_refs.py` fails on drift).
- **`data/pricing.copilot.json` is the Copilot-side numeric source of truth** — same rules as pricing.json: never hardcode Copilot prices, credit values, plan allowances, or model IDs into `copilot/` content or scripts; derive them at run time (the AIC unit itself is data: `billing_unit.usd_per_credit`). README/docs Copilot tables are labeled snapshots tied to its `cached_date`. The two pricing files never merge, and neither harness's config reads the other's file; bundle files under `copilot/.github/` reference `{{POLYTROPOS_ROOT}}`, resolved to an absolute path only by `bin/harness_select.py` at install time.
- **`data/pricing.codex.json` is the Codex-side numeric source of truth** — same rules: never hardcode Codex prices, cache multipliers, plan facts, or model IDs into `codex/` content or scripts; derive them at run time. Its GPT-5.6 model ids are best-effort (see its `model_ids_note`) — corrections land there and only there. Subscription (ChatGPT-plan) Codex runs are usage-limited, not token-billed: every dollar figure shown for them is a labeled API-equivalent relative-burn proxy, never a bill (`billed_usd` stays null). The three pricing files never merge and no harness reads another's; the daily journal counts Codex activity and may additionally show a clearly-labeled API-equivalent relative-burn proxy priced from `pricing.codex.json` at run time (wired read-only into `bin/journal_*.py` by the `journal-augment` kit) — never a bill: `billed_usd` stays null and the proxy never enters the digest's priced totals. Bundle files under `codex/` carry `{{POLYTROPOS_ROOT}}`, resolved only by `bin/harness_select.py` at install time, which never writes `config.toml` and never overwrites a differing `AGENTS.md`.
- **Never invoke the real `copilot` CLI from tests, kit verify commands, or anything run during execution** — `copilot -p` / `copilot --agent` calls spend the user's real AI Credits and hit the network, and the user has a live `~/.copilot`. `bin/copilot_execute.py` and `bin/copilot_ralph.py` take injectable dispatch runners; tests stub or mock every dispatch (temp stub executables and temp `--copilot-home` dirs only), and `--dry-run` / `--demo` are the only sanctioned CLI smoke paths. `bin/copilot_usage.py` reads `~/.copilot/session-state/*/events.jsonl` strictly read-only at run time (never the `*.db` stores, never a write, never a `copilot` invocation); its tests use synthetic fixtures in temp `--copilot-home` dirs and never touch the real `~/.copilot`.
- **The daily journal is read-only ingestion with gitignored output.** `bin/journal_*.py` read `~/.claude/projects`, `~/.copilot/session-state`, and `~/.codex` strictly read-only at run time (JSONL only — never a `*.db`/SQLite open, never a CLI invocation to gather); output, inbox, and config live under gitignored `journal/`; the digest carries metadata only (no transcript text); the summarizer's `claude -p` dispatch is injectable, mocked in every test, and `--dry-run` prints the prompts and spawns nothing; Codex activity is counted and may additionally carry a clearly-labeled API-equivalent relative-burn proxy sourced from `data/pricing.codex.json` at run time — never presented as a bill (`billed_usd` stays null, the codex source stays `priced: false`/`usd: null`, and proxy dollars never enter `usd_priced`).
- **Python is stdlib-only** (`bin/`, `tests/`). No pip installs, no requirements files, no pytest.
- **Skills resolve plugin files via `${CLAUDE_PLUGIN_ROOT}`**, with "relative to this SKILL.md"
  as the stated fallback (resolve to absolute before shelling out — bash cwd is not the skill
  dir). The one exception: commands written into `~/.claude/settings.json` (statusline) must be
  literal absolute paths — that env var doesn't exist outside plugin context.
- **The architect and execute skills share one kit contract — keep them in sync.** If you touch
  either `skills/architect/SKILL.md` or `skills/execute/SKILL.md`, re-check both against:
  layout `.claude/kits/<slug>/PLAN.md` + `TASKS.md` + `GUARDRAILS.md` (kit-scoped fences, architect-owned; execute reads it at setup) (+ `NOTES.md`, owned by execute); task fields
  `id`, `title`, `status`, `model`, brief, acceptance, verify; status vocabulary exactly
  `pending | in-progress | done | blocked`; phase headings; `depends:`/`independent:` marking;
  and the rule that a task's `model` field overrides the implementer agent's frontmatter at
  dispatch.
- **Never touch `~/.claude/` or anything outside this repo.** Do not re-install or refresh the
  plugin.
- **Do not commit or push** unless the user explicitly asks.
- **The memory store (`memory/` at the repo root) is gitignored user data.** Fact files under
  it are private, local-only, and never committed (`.gitignore` carries a root-anchored
  `/memory/` — the leading slash is load-bearing so `skills/memory/` stays tracked). Runtime
  code touches the store only via the `bin/memory_*.py` engines' explicit `--memory-dir`
  seam, and every test/verify uses temp `--memory-dir` fixtures with an explicit `--now` —
  never a real store, zero `Path.home()` in the memory code. Recall is pull-only,
  relevance-gated, and budget-capped by design: nothing may ever bulk-inject the store, its
  index, or uncapped fact sets into a session's context.
- **The telemetry store (`telemetry/` at the repo root) is gitignored personal data,
  written by `bin/telemetry_snapshot.py` ONLY.** It captures other tools' JSON output
  into dated envelopes (`telemetry/<source>/<YYYY-MM-DD>.json`); the filename date is
  always the capture date, honesty labels (est., unpriced, partial coverage) ride
  inside every envelope, and no envelope is ever hand-authored, backdated, or
  reconstructed from prose — late capture of a still-existing source is fine,
  fabricating an evaporated one never is. Readers degrade with a note when the store
  is absent, tests use temp `--store-dir` fixtures only, and nothing bulk-injects the
  store into a session's context.
- **`bin/repo_bench.py` measures models on a target repo and can spend real tokens — but
  only behind `--live` plus an explicit `--max-usd` ceiling; `plan`/`demo` and every test
  spend nothing.** Tests stub every dispatch and `gh` runner and use fixture repos in temp
  dirs. Target repos are read-only by construction (allowlisted git commands; sandboxes
  are history-free tree extractions). Its store (`benchruns/`, gitignored) is written by
  `bin/repo_bench.py` only — never hand-authored or backdated; verdicts below the evidence
  floor are never applied, and routing changes only via the explicit `apply` step writing
  gitignored `prefs/repo-bench.json`.
- **`bin/harness_update.py` check is strictly read-only; apply writes only the Copilot/Codex homes via `harness_select`'s own writers plus the repo's generated mirrors — never `~/.claude` (the remedy is printed, never executed), never pricing numbers or docs tables.** Codex prompts are plugin-generated mirrors, overwritten in place with every differing rewrite listed; AGENTS.md and skill dirs stay no-clobber. Tests use temp fixture homes only.

## How to run things

```bash
# from the repo root
python3 -m unittest discover -s tests -v          # full test suite — run before claiming any script task done
python3 bin/cost_report.py --days 30              # transcript cost report (markdown to stdout)
python3 bin/session_cost.py                       # one session's cost + all-Fable counterfactual (main + subagents, read-only)
python3 bin/routing_scorecard.py --demo           # routing-quality scorecard smoke (synthetic kit, no real data)
python3 bin/routing_scorecard.py --demo --live    # live re-route signal smoke (synthetic mid-run kit, upgrade-only, never frontier)
python3 bin/routing_scorecard.py --demo --history # cross-kit routing-history smoke (synthetic kits, dollars labeled partial)
python3 bin/routing_scorecard.py --demo --by-task # per-task dollars smoke (synthetic kit; shared warm agent + missing transcript honesty proofs)
python3 bin/routing_scorecard.py --demo --history --trend # cross-repo + trend smoke (two synthetic repos, two dated snapshots, text trend table)
python3 bin/copilot_pricing.py est M claude-fable-5   # Copilot-side cost estimate (USD + AIC)
python3 bin/copilot_ralph.py --demo               # Ralph goal-loop mock (no model, no network, no AIC)
python3 bin/copilot_usage.py --days 30            # Copilot usage report (reads ~/.copilot read-only)
python3 bin/codex_pricing.py models --profile M   # Codex-side roster + estimates (API $ + burn index vs cheapest)
python3 bin/codex_usage.py --days 30                  # Codex usage report (reads ~/.codex read-only; honest unpriced fallback)
python3 bin/journal_collect.py --print            # today's work-journal digest (reads ~/.claude, ~/.copilot, ~/.codex read-only; writes journal/)
python3 bin/journal_summarize.py --dry-run        # show the journal prompts + routed model (spawns nothing)
python3 bin/journal_askpack.py --print            # ready-to-paste Teams/Outlook/Copilot-Studio ask-prompts (offline; writes gitignored journal/; lands with the journal-augment kit)
python3 bin/journal_plan.py check                 # next-day runbook: cards due/overdue today (reads/writes only gitignored journal/plan/; spawns nothing; lands with the next-day-runbook kit)
python3 bin/memory_recall.py --demo               # budget-capped memory recall smoke (synthetic store in its own temp dir; gate + stale + budget visible; lands with the memory-skill kit)
python3 bin/memory_store.py review                # memory staleness report (read-only over the gitignored memory/ store; empty store prints its friendly line; lands with the memory-skill kit)
python3 bin/context_weight.py demo                # context-weight smoke: per-call weight curves, ranked contributors, resident-surface audit — all synthetic, no real data (lands with the context-weight kit)
python3 bin/context_weight.py session             # what filled this window: latest Claude session's per-call weight, growth curve, ranked contributors (reads ~/.claude read-only; --harness codex|copilot at their honest fidelity)
python3 bin/telemetry_snapshot.py               # capture today's telemetry snapshots (reads home dirs read-only; writes only gitignored telemetry/; lands with the telemetry-store kit)
python3 bin/telemetry_snapshot.py --list        # what the telemetry store holds per source (tolerant of an absent store)
python3 bin/repo_bench.py demo                  # repo-bench full-pipeline smoke: fixture repo, stub dispatch, all four oracles, below-floor verdict honesty — no network, no spend (lands with the repo-bench kit)
python3 bin/repo_bench.py plan --repo . --models sonnet,haiku   # priced models×tasks matrix for a repo, from pricing.json — prints the ceiling and stops; only `run --live --max-usd` ever spends
python3 bin/copilot_pricing.py knobs              # Copilot reasoning-effort facts from pricing.copilot.json (display-form ladder + interactive-picker mechanism notes; lands with the effort-dial kit)
python3 bin/codex_pricing.py knobs                # Codex reasoning-effort ladder + modes notes from pricing.codex.json (lands with the effort-dial kit)
python3 bin/copilot_pricing.py prefs              # active Copilot model pins/excludes + what each tier now resolves to (gitignored prefs/copilot.json + per-run flags; lands with the copilot-model-prefs kit)
echo '{"model":{"id":"claude-fable-5","display_name":"Fable 5"},"cost":{"total_cost_usd":1.23},"context_window":{"used_percentage":42},"rate_limits":{"five_hour":{"used_percentage":12},"seven_day":{"used_percentage":34}}}' | python3 bin/statusline.py
python3 bin/harness_update.py check           # all-harness freshness card (read-only; exit 3 on drift; lands with the harness-update kit)
python3 bin/harness_update.py demo            # synthetic check/apply smoke — temp trees only, no real homes
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
