# PLAN — journal-augment

autonomy: advisory

Extend the v1-complete daily journal (`bin/journal_*.py`, kit `daily-journal`) in three
locked directions, keeping every journal invariant that still holds and deliberately
reversing exactly one that is now stale:

1. **Ask-the-tools pack (offline external sources).** A new deterministic generator writes
   ready-to-paste prompts the user runs inside their OWN Copilot Studio / Microsoft Teams /
   Outlook AI ("summarize my meetings/emails/chats for <date> as short bullet lines"). The
   user pastes the bullet results back into `journal/inbox.md`, which the digest ALREADY
   ingests. Two-pass flow: collect → generate ask-prompts → user runs them in the MS tools →
   pastes bullets back → re-collect + summarize with the enriched inbox. This is PURE TEXT
   GENERATION — no network, no OAuth, no Graph, no MCP, no secrets, ever. It fully honors the
   journal's hard offline invariant; the Graph/MCP connector paths stay deferred BY DESIGN.
2. **Codex deepen + price with a LABELED proxy.** The journal's codex adapter today reads
   only the shallow `session_index.jsonl` + `history.jsonl` and marks Codex unpriced. It now
   ALSO reads the day's rollout files (`<codex-home>/sessions/YYYY/MM/DD/*.jsonl`, where the
   real token/model data lives) by REUSING `bin/codex_usage.py` read-only, and shows cost as
   an **API-equivalent relative-burn proxy** — explicitly labeled, never a bill, `billed_usd`
   null semantics — priced ONLY from `data/pricing.codex.json` at run time. This REVERSES the
   formerly-pinned "Codex counted-but-unpriced / no Codex pricing exists" stance, which is
   now stale (`data/pricing.codex.json` + `bin/codex_usage.py` exist, shipped by the
   codex-harness kit). The architect has ALREADY reconciled CLAUDE.md's invariant text (see
   D4); the activity count is kept and the proxy is strictly ADDITIVE.
3. **Next-day = ADVISORY harness routing.** A new deterministic advisor computes per-harness
   signals (today's actual usage per harness from the digest + comparable task-cost estimates
   derived from the three pricing files at run time) into `signals.harness`; the summarizer's
   next-day prompt then asks the model to recommend, for each next-day task, a harness
   (Claude Code / Copilot CLI / Codex CLI) + a model tier + a ready-to-paste command + a
   one-line WHY — grounded ONLY in those signals. Advisory only: the user decides and runs
   it; nothing auto-executes. This preserves the journal's deterministic-signals-then-prose
   design (D10 of the daily-journal kit).

## Goal — "done" is checkable

- `python3 -m unittest discover -s tests -v` fully green, INCLUDING the four frozen journal
  test files (`tests/test_journal_sources.py`, `test_journal_collect.py`,
  `test_journal_summarize.py`, `test_journal_schedule.py`) which stay **byte-untouched**
  (`git diff --quiet` on each), plus three NEW test files:
  `tests/test_journal_codex_augment.py`, `tests/test_journal_askpack.py`,
  `tests/test_journal_advisor.py`.
- A synthetic end-to-end proof works offline in temp dirs: fixture codex-home with a
  day-partitioned rollout carrying tokens → `collect_codex` (with a pricing dict) emits token
  totals + `extra["codex_proxy"]` with `billed_usd: None` and the verbatim disclaimer, while
  `priced` stays `False`, `usd` stays `None`, and `totals.usd_priced` excludes the proxy.
- `python3 bin/journal_askpack.py --date <d> --utc --journal-dir <tmp> --print` writes
  `<tmp>/<d>/ask-the-tools.md` with the pinned H1/H2 set and prompts that request at most
  `MAX_ASK_BULLETS` subject-level bullet lines per tool, and spawns nothing.
- `journal_collect.py` digests now carry `signals.harness` (advisory flag, per-harness
  usage-today + estimates + command templates), computed by `bin/journal_advisor.py` from the
  three pricing files at run time — with honest `None` degradation when a pricing dict or
  source is missing, never a fabricated figure.
- `journal_summarize.py --dry-run` prints a technical prompt carrying the single labeled
  proxy exception and a next-day prompt carrying the conditional `## Harness plan` section;
  the three pre-existing H1s and the six pre-existing H2 orderings are unchanged and the
  frozen summarize tests pass untouched.
- `skills/journal/SKILL.md` documents the two-pass ask-the-tools flow, the labeled Codex
  proxy, and the harness plan — BODY-only, frontmatter byte-identical to HEAD.
- `docs/DAILY-JOURNAL.md` covers all three features; the stale "no Codex pricing exists"
  claims in `docs/DAILY-JOURNAL.md`, `docs/HOW-IT-WORKS.md`, and `docs/how-it-works.html`
  are corrected via pinned sentence swaps.
- `git status` shows changes ONLY to the sanctioned targets (see fence); CLAUDE.md already
  carries the architect's pinned insertions and is NOT touched by any task.

## Repo facts (verified by the architect — trust these; re-read the file only if an anchor is missing)

- **Adapter engine** `bin/journal_sources.py`: `_load(name)` importlib loader at module top;
  `cr = _load("cost_report")`, `cu = _load("copilot_usage")` already loaded.
  `collect_codex(ctx)` (PLAN daily-journal D6) reads ONLY `session_index.jsonl` +
  `history.jsonl` directly under `codex_home`, uses `CODEX_TS_KEYS`/`CODEX_SESSION_KEYS`/
  `CODEX_MODEL_KEYS`/`CODEX_CWD_KEYS`/`CODEX_USAGE_KEYS`/`CODEX_TOKEN_FIELD_MAP` +
  `_codex_get`/`_codex_ts`, always `priced=False`/`usd=None`, note constant
  `CODEX_UNPRICED_NOTE` (currently claims "no Codex pricing exists in data/ (by design)" —
  stale, text will change; the frozen test references the CONSTANT, not the literal).
  `empty_report(source, priced)` pins the report skeleton; `_model_bucket()` pins the
  per-model bucket (`usd` stays None until priced); `_span`, `_add_tokens` helpers;
  `run_adapters(ctx)` crash-isolates; ctx keys today: `day_start`, `day_end` (aware
  datetimes), `claude_projects`, `copilot_home`, `codex_home`, `repos`, `pricing_claude`,
  `pricing_copilot`.
- **Collector** `bin/journal_collect.py`: loads `js`, `cr`, `cu`, `ce` via `_load`;
  `Path.home()` appears in EXACTLY three constants (`DEFAULT_CLAUDE_PROJECTS`,
  `DEFAULT_COPILOT_HOME`, `DEFAULT_CODEX_HOME`) — this budget must not grow; builds
  `ctx`, calls `js.run_adapters(ctx)`, then `read_inbox`, `scan_kit_tasks`, `build_wip`,
  assembles `signals = {"kit_tasks":…, "inbox":…, "wip":…}` (+ conditional `kit_errors`,
  `config_notes`), and `build_digest(reports, day_start, day_end, date_str, signals)`.
  The ONLY write is `journal/<date>/digest.json`.
- **Summarizer** `bin/journal_summarize.py`: `build_prompts(digest)` pure →
  `{narrative, technical, next_day}`; pinned H1s and H2 sets (technical: `## Sessions &
  cost`, `## Models`, `## Repos & commits`; next_day: `## Start here`, `## To-dos`,
  `## How to run`); dispatch `runner(argv, prompt)->(rc,text)` injectable; `--dry-run`
  spawns/writes nothing; loads NOTHING via importlib (stdlib + `data/pricing.json` only).
- **Codex reader** `bin/codex_usage.py` (REUSE READ-ONLY, never edit): `load_pricing()` →
  `data/pricing.codex.json` dict; `parse_rollout(lines)` → `{"tokens": {"input","cache_read",
  "output"}|None, "models": [str], "session_ids": set, "records": int, "malformed": int}`
  implementing the cumulative-vs-per-turn MAX rule; `match_model(model_id, pricing)` →
  pricing key or None; `price_tokens(u, key, pricing)` → USD using
  `cache_read_multiplier` from the data; constants `PROXY_DISCLAIMER` ("Figures are
  API-equivalent dollars — a relative-burn proxy. Subscription (ChatGPT-plan) usage is
  usage-limited, not token-billed.") and `UNPRICED_NOTE` ("no token usage found in these
  logs — activity counted, unpriced"). `reasoning_output_tokens` is deliberately unmapped.
- **Codex estimator** `bin/codex_pricing.py` (REUSE READ-ONLY): `load_pricing()`;
  `TIER_ORDER = ("cheap","mid","strong","frontier")`; `resolve_tier(pricing, tier)` with the
  skip-up rule (raises KeyError when nothing at/above the tier);
  `est_cost(pricing, profile, model_or_tier, cache_hit=0.8)` → `{"model_id", "usd_api",
  "subscription": {"billed_usd": None, "api_equivalent_usd", "burn_index_vs_cheapest",
  "cheapest_model_id"}}`.
- **Copilot estimator** `bin/copilot_pricing.py` (REUSE READ-ONLY): `load_pricing()`;
  `est_cost(pricing, profile, model_id, cache_hit=0.8, today=None)` → `{"usd", "aic",
  "rates_used", "warnings"}`. Copilot models carry `tier` ∈ cheap|mid|strong|frontier.
- **Pricing files** (never merged, never edited by this kit): `data/pricing.json` — models
  carry `tier` ∈ haiku|sonnet|opus|frontier, top-level `cache_read_multiplier`,
  `task_profiles` XS/S/M/L/XL with `input_tokens`/`output_tokens`.
  `data/pricing.copilot.json` — `billing_unit.usd_per_credit`, tiers cheap|mid|strong|
  frontier, same `task_profiles` keys. `data/pricing.codex.json` — GPT-5.6 ids are
  BEST-EFFORT (`model_ids_note`); `billing_modes.subscription` pins the not-a-bill framing;
  same `task_profiles` keys. **A gpt-5.6 model id must NEVER appear as a literal in code or
  tests** — compute ids from the file at run time.
- **Frozen key-set tests** (why nothing new lands at the report/digest top level):
  `tests/test_journal_sources.py` asserts `frozenset(report) == REPORT_KEYS` for every
  adapter; `tests/test_journal_collect.py` asserts `frozenset(digest) == DIGEST_TOP_KEYS`.
  Everything this kit adds therefore rides INSIDE `extra` values, `notes`, `models`,
  `totals` values, and `signals` — never as a new report or digest top-level key.
  `_base_ctx` in the frozen sources tests has NO `pricing_codex` key, so the adapter must
  read it via `ctx.get("pricing_codex")` and treat `None` as exact legacy behavior.
- **Dispatch shapes already pinned in this repo** (source of the advisor's command
  templates — never invent CLI flags): `journal_summarize.build_dispatch` →
  `[claude_bin, "-p", "--model", model_id]`; CLAUDE.md's Copilot invariant pins
  `copilot -p` / `copilot --agent`, and `copilot_execute.build_dispatch` passes
  `--model <id> … -p <brief>`; `codex_execute.build_dispatch` →
  `[codex_bin, "exec"] + (["--model", id] if id else []) + ["--full-auto"]`.
- **Inbox seam**: `journal_collect.read_inbox` skips blanks/`#`, strips one leading
  `- `/`* `/`[ ] ` marker, caps at `MAX_INBOX_ITEMS = 100`. The ask-pack's bullet budget
  (3 tools × `MAX_ASK_BULLETS = 15` = 45) stays well under the cap.
- Test suite conventions: stdlib `unittest`; importlib-load bin scripts by absolute path;
  every root flag overridden to `tempfile` dirs; `--utc` wherever day membership matters;
  read-only proofs by byte-snapshotting fixture trees; verify form
  `python3 -m unittest discover -s tests -p '<file>.py'` — NEVER the dotted-module form
  (broken on this machine).

## Architecture & key decisions

- **D1 — External sources are an OFFLINE ask-the-tool pack; the inbox is the return path.**
  New `bin/journal_askpack.py`: `build_ask_prompts(date_str, digest=None)` (pure) returns
  `{"copilot_studio", "teams", "outlook"}` prompt strings; `render_pack(date_str, prompts)`
  (pure) renders one markdown file; the CLI writes `journal/<date>/ask-the-tools.md`
  (gitignored automatically — it lives under `journal/`). Each prompt asks the user's OWN
  Microsoft tool to summarize that date's meetings/chats/emails/agent-sessions as **at most
  `MAX_ASK_BULLETS` (15) short bullet lines, each starting `- `, subject-level only (titles,
  people, decisions, action items — no message bodies, no attachments, no confidential
  excerpts)** — exactly the shape `read_inbox` ingests, and hygiene-bounded so pasted
  content cannot bloat the digest with message bodies. WHY this design: it delivers the
  Teams/Outlook/Copilot-Studio coverage the user asked for with ZERO network/OAuth/MCP —
  the daily-journal kit's deferred item 2 stays deferred, and the return path reuses the
  `signals.inbox` seam that was explicitly reserved for exactly this. When a digest is
  passed, the prompts append a one-line project-name context (union of
  `sources.*.projects`) — names only, honest and optional.
- **D2 — Codex deepening rides the existing adapter behind an OPTIONAL `pricing_codex` ctx
  key; `None` means byte-identical legacy behavior.** `journal_sources.py` gains
  `cxu = _load("codex_usage")` beside `cr`/`cu`. `collect_codex` additionally reads rollout
  files from EXACTLY the digest day's directory
  `<codex_home>/sessions/<YYYY>/<MM>/<DD>/*.jsonl` (zero-padded from
  `ctx["day_start"].date()` — the date-partitioned dir name IS the day-membership rule;
  rollouts outside that one dir are never opened, and non-date-partitioned strays are out of
  scope for a daily view — `codex_usage.py --days` covers those). Each file is reduced with
  `cxu.parse_rollout` (cumulative-vs-per-turn MAX rule reused, never re-implemented);
  tokens land in the report's `models` buckets and `totals` (deepening happens whether or
  not pricing is present); session ids union into the session count. Pricing happens ONLY
  when `ctx.get("pricing_codex")` is a dict: whole-rollout tokens attribute to
  `cxu.match_model(...)`-matched keys (multi-model rollout → last matched key, approx
  flagged — mirrors `codex_usage.py` exactly). WHY: the tolerant shallow parser stays the
  activity backbone (frozen tests prove nothing regressed), the deep knowledge stays in ONE
  place (`codex_usage.py`, reused read-only), and the frozen `_base_ctx` (no `pricing_codex`
  key) keeps every old test green without edits.
- **D3 — Proxy honesty is absolute.** The codex report keeps `priced: False` and
  `usd: None` FOREVER — a relative-burn proxy is not a bill, so it must never flow into
  `totals.usd_priced` (which sums real dollars) and `unpriced_sources` still lists
  `codex_cli`. The proxy lives ONLY in
  `extra["codex_proxy"] = {"billed_usd": None, "api_equivalent_usd_total": float,
  "by_model": {pricing_key: float}, "approx_attribution": bool,
  "disclaimer": cxu.PROXY_DISCLAIMER, "pricing_cached_date": pricing["cached_date"]}`
  — with the disclaimer REUSED from the constant, never retyped. Model buckets' `usd` stays
  `None` for codex (bill semantics). Notes ladder: pricing present + priced tokens →
  `cxu.PROXY_DISCLAIMER` appended to `notes`; pricing present + no tokens →
  `cxu.UNPRICED_NOTE`; pricing present + tokens but nothing matched → new constant
  `CODEX_UNMATCHED_NOTE` + ids in `extra["unpriced_models"]`; pricing `None` → the legacy
  `CODEX_UNPRICED_NOTE` (constant kept, TEXT updated to stay truthful: it no longer claims
  no pricing exists in `data/`, it says none was provided to this run). `build_digest` is
  untouched; no new report or digest top-level key anywhere (frozen key-set tests).
- **D4 — The invariant reversal is deliberate, minimal, and ALREADY MADE.** The architect
  edited CLAUDE.md before execution starts: (a) the global daily-journal bullet no longer
  ends "Codex activity is counted but never priced (no Codex pricing exists in `data/` by
  design)" — it now authorizes a clearly-labeled API-equivalent relative-burn proxy from
  `data/pricing.codex.json`, never a bill, proxy never entering `usd_priced`; (b) the
  global `pricing.codex.json` bullet no longer claims "`pricing.codex.json` is never wired
  into `bin/journal_*.py`"; (c) the completed codex-harness fence's journal clause is
  tensed to historical with a superseded-by-journal-augment pointer. Executors must treat
  the CURRENT CLAUDE.md text as authoritative and must NOT edit CLAUDE.md further. Every
  other invariant is byte-intact. The stale claims in `docs/` are corrected by pinned
  sentence swaps (T9/T10).
- **D5 — The harness advisor is a pure, reuse-driven signal builder.** New
  `bin/journal_advisor.py`: `build_harness_signal(reports, pricing_claude,
  pricing_copilot, pricing_codex, profiles=ADVISOR_PROFILES, cache_hit=ADVISOR_CACHE_HIT)`
  → the pinned `signals.harness` dict (see T5 brief for the exact shape). Per harness it
  combines (i) today's actual usage from the digest reports (`available`, `sessions`,
  `usd`, copilot's `extra.aic`, codex's `extra.codex_proxy` total) and (ii) two comparable
  task-cost estimates per profile in `("S","M")` — a cheap-tier and a mid-tier
  representative model, resolved FROM EACH PRICING FILE at run time (claude: first model of
  tier `haiku`/`sonnet` in file order — the `journal_summarize.pick_models` precedent;
  copilot: first of tier `cheap`/`mid`; codex: `codex_pricing.resolve_tier`). Estimates
  reuse `copilot_pricing.est_cost` and `codex_pricing.est_cost`; the Claude side has no
  existing estimator script, so the advisor computes the SAME formula shape (input ×
  ((1−h)·rate + h·rate·`cache_read_multiplier`) / 1e6 + output/1e6 × out-rate) from
  `data/pricing.json` values — documented parity, no new literal. Codex estimate entries
  carry `billed_usd: None` + are named `usd_api_equivalent` (never plain "cost"). Command
  templates come from the repo-pinned dispatch shapes (Repo facts above) with a `{model}`
  placeholder — the advisor never invents a CLI flag. Degradation: a missing report → an
  entry with `available_today: False`; a `None` pricing dict → `est: None` + a note; an
  unpopulated tier → `None` slot + note — NEVER a fabricated number. WHY pure + advisory:
  fully unit-testable with synthetic dicts, and the user keeps every decision — nothing
  here dispatches, executes, or auto-pins anything.
- **D6 — Digest and prompt growth is additive-only; deterministic-signals-then-prose is
  preserved.** `journal_collect.py` loads `data/pricing.codex.json` via
  `cxu.load_pricing()` (parity with `cr`/`cu`), passes `"pricing_codex"` in ctx, and sets
  `signals["harness"]` via `ja = _load("journal_advisor")` — wrapped in try/except so an
  advisor crash lands as `signals["harness_error"]` (string) and the nightly run continues
  (the `kit_errors`/`config_notes` precedent). `schema_version` stays 1. The summarizer's
  technical prompt gains ONE pinned exception sentence (codex proxy reported only as a
  labeled not-a-bill proxy); the next-day prompt gains a pinned CONDITIONAL `## Harness
  plan` section placed after `## How to run` (the three frozen H2 index assertions still
  pass). The narrative prompt is untouched. Exact replacement strings are pinned verbatim
  in T6 — do not paraphrase them.
- **D7 — Tests: three new files, four frozen files, honest negatives.** New tests go in
  `tests/test_journal_codex_augment.py` (adapter deepening/proxy/honesty/read-only/day
  membership + collect CLI end-to-end), `tests/test_journal_askpack.py`, and
  `tests/test_journal_advisor.py` (advisor + prompt revisions + collect wiring). The four
  frozen journal test files are never edited — passing them unmodified IS the
  backward-compatibility proof. Unit tests feed synthetic pricing dicts through
  ctx/arguments; CLI end-to-end tests may open the real pricing files (sanctioned config
  reuse) but must derive any model id from the file at run time. Read-only proofs
  byte-snapshot fixture homes; a content-hygiene test plants a marker string in a rollout's
  message-like field and asserts it never reaches the digest.
- **D8 — Surfaces.** `skills/journal/SKILL.md` (BODY-only — the plugin is LIVE, frontmatter
  byte-intact) gains the two-pass ask-the-tools section, the labeled-proxy note, and the
  harness-plan mention. `docs/DAILY-JOURNAL.md` gains matching sections and loses its stale
  unpriced claim. `docs/HOW-IT-WORKS.md` + `docs/how-it-works.html` each get ONE pinned
  sentence swap. No README changes; CLAUDE.md is already done (D4).

## Constraints and OUT-OF-SCOPE fence

Executors must NOT:

- **Add network, OAuth, tokens, MCP, or secrets in any form.** The ask-the-tools feature is
  pure text generation. No `urllib`/`http.client`/`socket` import in any new or edited
  file. The Graph/MCP connector paths stay deferred BY DESIGN.
- **Read OR write the real `~/.claude`, `~/.copilot`, or `~/.codex` from any test or verify
  command.** Runtime defaults stay as-is; every test/verify overrides every root flag to
  temp fixtures and passes `--utc` where day membership matters. `Path.home()` stays at
  exactly the four pre-existing pinned constants (3 in `bin/journal_collect.py`, 1 in
  `bin/journal_schedule.py`) — ZERO in `bin/journal_askpack.py`, `bin/journal_advisor.py`,
  and every new test file.
- **Open any SQLite/`*.db` file, or `import sqlite3`, anywhere.** JSONL and flat text only.
  Rollout reads are limited to the digest day's `sessions/YYYY/MM/DD` directory.
- **Invoke a real `claude`/`copilot`/`codex` CLI or `launchctl` from tests, verify commands,
  or anything run during execution.** The summarizer dispatch stays injectable and mocked;
  `--dry-run` spawns nothing; the ask-pack and advisor never spawn anything at all.
- **Edit the reused scripts**: `bin/codex_usage.py`, `bin/codex_pricing.py`,
  `bin/copilot_pricing.py`, `bin/cost_report.py`, `bin/copilot_usage.py`,
  `bin/copilot_execute.py`, `bin/session_cost.py` — importlib read-only. Never re-implement
  `parse_rollout`/`match_model`/`price_tokens`/`est_cost`/`resolve_tier`; call them. Never
  retype `PROXY_DISCLAIMER`/`UNPRICED_NOTE` — reference the constants.
- **Edit the four frozen journal test files** (`tests/test_journal_sources.py`,
  `test_journal_collect.py`, `test_journal_summarize.py`, `test_journal_schedule.py`) or
  `bin/journal_schedule.py`. New tests go ONLY in the three new files.
- **Add a new report or digest top-level key, change `build_digest`, or bump
  `schema_version`.** Everything additive lives inside `extra` values, `notes`, `models`,
  `totals` values, and `signals` (`harness` / conditional `harness_error` are the ONLY new
  signals keys). The codex report keeps `priced: False`, `usd: None`; the proxy never
  enters `totals.usd_priced` or any billed figure; no estimated splitting or zeroed
  stand-ins under any label.
- **Hardcode prices, price ratios, plan facts, or real model ids.** GPT-5.6 ids must never
  appear as literals in code or tests — compute from `data/pricing.codex.json` at run
  time. Sanctioned literals: tier vocabulary (`haiku|sonnet|opus|frontier`,
  `cheap|mid|strong|frontier`), task-profile keys (`"S"`, `"M"`), `MAX_ASK_BULLETS = 15`,
  `ADVISOR_PROFILES = ("S", "M")`, `ADVISOR_CACHE_HIT = 0.8`, the pinned command-template
  strings, pinned note/heading text, and synthetic fixture ids/values in tests. The three
  pricing files never merge; the advisor loads all three but never mixes rates across
  files, and each estimate names its harness.
- **Edit `data/pricing.json`, `data/pricing.copilot.json`, or `data/pricing.codex.json`;
  edit CLAUDE.md or README.md; add any new skill; touch `.claude-plugin/`, `copilot/`,
  `codex/`, the completed kits, or their agents.** Sanctioned existing-file edits are ONLY:
  `bin/journal_sources.py` (T1), `bin/journal_collect.py` (T1, T6),
  `bin/journal_summarize.py` (T6), `skills/journal/SKILL.md` (T8, BODY-only),
  `docs/DAILY-JOURNAL.md` (T9), `docs/HOW-IT-WORKS.md` + `docs/how-it-works.html` (T10,
  one pinned sentence swap each). New files are ONLY: `bin/journal_askpack.py`,
  `bin/journal_advisor.py`, and the three new test files.
- **Auto-execute anything from the advisor or next-day plan** — no auto-dispatch, no
  auto-pin, no main-session model switching; recommendations are print/prose only.
- **Build the deferred work**: Graph/OAuth/MCP connectors, Cursor/VS Code adapters, weekly
  rollups, per-message live watching, daemons. **Commit or push.**

## Risks & tripwires

- **Proxy read as a bill — the #1 semantic risk.** TRIPWIRES: any codex dollar figure
  without the proxy label; `codex_proxy` money summed into `usd_priced` or any billed
  total; `billed_usd` non-null; a model bucket `usd` set for codex; the disclaimer retyped
  instead of referencing `cxu.PROXY_DISCLAIMER`.
- **Frozen-test breakage.** The four frozen files assert exact report/digest key sets, the
  legacy codex path (via `_base_ctx` WITHOUT `pricing_codex`), the three H2 orderings per
  prompt, and dry-run spawn-nothing. TRIPWIRES: a new top-level report/digest key; codex
  legacy behavior differing when `pricing_codex` is None; a pinned H2 renamed/reordered;
  any edit to the four files.
- **Best-effort GPT-5.6 ids.** `model_ids_note` says the ids may be corrected in the
  pricing file at any time. TRIPWIRE: a `gpt-5.6-*` literal in any code or test file
  (compute `next(iter(pricing["models"]))` or tier-resolved ids at run time instead).
- **Ask-pack bloat / hygiene.** Pasted tool output flows into the digest via the inbox and
  is later SENT TO A MODEL by the summarizer. TRIPWIRES: prompts that don't cap bullets at
  `MAX_ASK_BULLETS` or don't say subject-level-only/no-message-bodies; the pack writing
  anywhere but `<journal-dir>/<date>/ask-the-tools.md`; prompts embedding digest content
  beyond project names.
- **Rollout day-membership.** The `sessions/YYYY/MM/DD` dir name is the membership rule
  (D2). TRIPWIRES: scanning more than the one day dir; using mtime; re-implementing
  `iter_rollout_files`' window semantics; opening anything under an out-of-day dir.
- **Advisor fabrication.** TRIPWIRES: a made-up estimate when a pricing dict is None or a
  tier is unpopulated (must be `None` + note); an invented CLI flag in a command template;
  rates from one pricing file applied to another harness's model.
- **Same-file collisions.** T1 and T6 both edit `bin/journal_collect.py` — strictly serial
  (T6 `depends: T1`). T6 also edits `bin/journal_summarize.py`. Never dispatch them in
  parallel.
- **Suite/paths quirks.** `python3 -m unittest discover -s tests [-p '<file>.py']` — never
  the dotted-module form. Paths via `Path(__file__).resolve()`, never `$PWD`. No
  `/private/tmp/` session-scratchpad path in any deliverable.

## Still deferred after this kit (designed or noted, not built)

1. **Graph/OAuth and MCP connectors for Teams/Outlook** — the ask-the-tools pack is the
   offline stand-in; the two connector designs in the daily-journal PLAN stand unchanged.
2. **Copilot Studio programmatic access** — unmapped/greenfield; prompts-only here.
3. **Cursor / VS Code adapters** (SQLite safe-copy strategy) — unchanged from daily-journal.
4. **Weekly rollups** across dated digests — unchanged.
5. **Any auto-execution of the harness plan** (auto-dispatch of next-day tasks) — the
   advisor is advisory by design; revisit only as a new architect-planned kit.
