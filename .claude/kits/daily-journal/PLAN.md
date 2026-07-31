# PLAN — daily-journal

A nightly work journal for the user's AI-assisted work. A deterministic, stdlib-only
**collector** ingests the day's usage across every tool (Claude Code, Copilot CLI, Codex CLI —
all clean JSONL — plus read-only `git log` activity), pre-structures next-day signals (open kit
tasks, a local inbox, uncommitted work), and writes a machine-readable `digest.json`. A separate
**summarizer** turns that digest into three model-written documents — `narrative.md` (the story
of the day), `technical.md` (sessions, costs, models, repos), `next-day.md` (what to start, what
to run and how, to-dos) — via an injectable `claude -p` dispatch routed to a cheap/mid model
with one-step escalation. A **scheduler** provides a macOS launchd installer/uninstaller and a
manual one-shot path (~22:00 local, configurable). All output and the inbox live under a
**gitignored** `journal/` tree so personal data never lands in git.

Sources are built on a **pluggable source-adapter architecture**: Cursor and VS Code
(`state.vscdb` SQLite) are DEFERRED — the adapter contract is designed so they slot in later,
but v1 ships only registered stubs + design notes. External augmentation (Teams/Outlook) is a
LOCAL INBOX in v1; the Microsoft Graph / MCP-connector paths are DESIGNED-but-DEFERRED (see
"Still deferred") — no OAuth, no tokens, no network anywhere in v1.

## Goal

Ship four new `bin/` scripts + tests + a skill + docs, end-to-end verified without ever reading
or writing the real `~/.claude`, `~/.copilot`, or `~/.codex` from a test, without ever invoking
a real `claude`/`copilot`/`codex` CLI from a test or verify command, and without ever opening a
SQLite file:

1. **`bin/journal_sources.py`** — the adapter engine: a pinned per-source report contract, an
   ordered `ADAPTERS` registry, day-window helpers, and six adapters — `claude_code`,
   `copilot_cli` (both reusing the proven parsers via importlib), `codex_cli` (new, tolerant,
   UNPRICED), `git` (read-only `git log`/`status` over configured repo roots), and
   `cursor`/`vscode` deferred stubs.
2. **`bin/journal_collect.py`** — the deterministic collector CLI: `--date` (default today,
   local tz; `--utc` for deterministic tests), per-source root overrides, `journal/config.json`
   (repos list), the inbox reader, kit-task + WIP signal pre-structuring, and the pinned
   `digest.json` written to `journal/<YYYY-MM-DD>/`. No model, no network, always runs.
3. **`bin/journal_summarize.py`** — reads a digest, builds three prompts (pure function),
   routes to the first model of the start tier in `data/pricing.json` file order (default tier
   `sonnet`, one escalation step max, capped at `opus` tier), dispatches via an INJECTABLE
   runner whose default shells `claude -p --model <id>` with the prompt on stdin, checks output
   deterministically, and writes `narrative.md` / `technical.md` / `next-day.md` +
   `summary-meta.json`. `--dry-run` prints the prompts and model choice and spawns/writes
   NOTHING.
4. **`bin/journal_schedule.py`** — `install` (renders a launchd plist via `plistlib` into
   `--launch-agents-dir`, default `~/Library/LaunchAgents`, and PRINTS the `launchctl`
   commands — it never executes `launchctl` itself), `uninstall`, `status`, and `run` (the
   manual one-shot: collect then summarize, in-process via importlib, injectable mains,
   `--dry-run`/`--collect-only` passthrough). The module imports no `subprocess` at all.

Plus: `.gitignore` gains `journal/`; `skills/journal/SKILL.md` (the ONE sanctioned addition
under `skills/`) gives `/polytropos:journal` for manual runs; `docs/DAILY-JOURNAL.md` +
README paragraph + CLAUDE.md pinned insertions document it; four new test files cover it all
with synthetic fixtures in temp dirs.

**Done looks like:** `python3 -m unittest discover -s tests -v` green with the four new test
files; a full synthetic demo — fixture homes → `journal_collect.py --utc --journal-dir <tmp>` →
`digest.json` with the pinned schema → `journal_summarize.py --dry-run` printing three prompts
and writing nothing — works end to end; `git check-ignore journal/anything` succeeds;
`journal_schedule.py install --launch-agents-dir <tmp>` writes a valid plist and `status`/
`uninstall` behave; the skill and docs exist with their pinned headings; CLAUDE.md carries the
pinned insertions; `git status` shows nothing outside the sanctioned new files + the four pinned
edit targets (`.gitignore`, `README.md`, `CLAUDE.md`, and nothing else among existing files);
`data/`, `.claude-plugin/`, existing `skills/*`, `copilot/`, existing `bin/`+`tests/` files, and
the completed kits are byte-identical to HEAD.

## Research findings — the data surfaces (CONFIRMED read-only by the architect; do NOT re-inspect `~/.claude` or `~/.copilot`)

- **Claude Code:** `~/.claude/projects/<project-slug>/**/*.jsonl` — one JSON object per line;
  per-message `message.model` and `message.usage{input_tokens, output_tokens,
  cache_read_input_tokens, cache_creation_input_tokens}`, top-level `timestamp` (ISO, often
  `Z`-suffixed), `sessionId`, and on many entries `cwd` and `gitBranch`. Subagent turns are
  woven into the main transcript (and also duplicated in a per-session tasks dir under tmp) —
  which is why dedupe by `message.id` is mandatory. `bin/cost_report.py` /
  `bin/session_cost.py` already parse all of this; REUSE, never re-implement:
  `cost_report.load_pricing / match_model / rates_for / price / parse_timestamp /
  extract_record` (extract_record returns `(model, usage_dict, message_id, tool_uses)` or
  None; `price(key, u, when, pricing)` applies cache multipliers and intro pricing by date).
- **Copilot CLI:** `~/.copilot/session-state/<uuid>/events.jsonl` + sibling `workspace.yaml`
  (+ a `session.db` that is NOT usage and must never be opened). `session.shutdown` carries
  `totalNanoAiu`/`tokenDetails` (cumulative snapshots — element-wise MAX, never sum);
  `assistant.message` carries `model`+`outputTokens`+`apiCallId`. All parsed by
  `bin/copilot_usage.py` — REUSE: `parse_events, collect_sessions, effective_tokens,
  price_tokens, usd_to_aic, match_model, parse_workspace, parse_timestamp`.
  `collect_sessions(session_dir)` returns `(sessions, errors)` where each session dict carries
  the `parse_events` result + `workspace` + the dir name as id.
- **Codex CLI:** `~/.codex/` holds `session_index.jsonl` and `history.jsonl` (JSONL), plus
  `sqlite/codex-dev.db` which v1 NEVER opens. The JSONL field names are NOT pinned here — the
  implementer of the codex adapter has ONE sanctioned research step: read a few lines of the
  two real JSONL files strictly read-only (e.g. `head -20`) to learn field names, then encode
  them as candidate-key constants in a tolerant parser that degrades gracefully (activity
  counted even when token fields are absent). There is NO Codex pricing in `data/` — Codex is
  counted but UNPRICED; never invent prices.
- **Cursor / VS Code:** usage lives in `state.vscdb` SQLite (undocumented, schema drifts) —
  DEFERRED. Opening a live SQLite DB can spawn `-wal`/`-shm` side files even read-only, which
  is exactly what the read-only contract forbids; v1 is JSONL-only.
- **Teams/Outlook:** no local data surface exists — hence the local inbox
  (`journal/inbox.md`), with Graph/MCP designed-but-deferred.
- **Kit tasks:** `.claude/kits/*/TASKS.md` all follow one contract; `bin/copilot_execute.py`'s
  `parse_tasks(text)` already parses it (returns dicts with `id, title, status, model, depends,
  independent, brief, verify`; raises ValueError on malformed status). REUSE it for the
  kit-task signal.
- **Importlib reuse pattern (the repo convention):** `bin/` is not a package; load siblings by
  absolute path: `spec_from_file_location(name, Path(__file__).resolve().parent /
  f"{name}.py")`. `bin/session_cost.py` does exactly this with cost_report.

## Architecture & key decisions

- **D1 — Read-only ingestion, JSONL only, is the load-bearing invariant.** The collector reads
  `~/.claude/projects`, `~/.copilot/session-state`, and `~/.codex` at RUNTIME only, strictly
  read-only: `read_text(errors="replace")` / line-streamed reads of pinned filenames, no write
  primitive ever aimed under a source root, no `*.db`/SQLite file ever opened (WAL side-file
  risk), and no CLI (`claude`/`copilot`/`codex`) ever invoked to GATHER. `Path.home()` appears
  ONLY in runtime-default constants — exactly 3 in `bin/journal_collect.py`
  (claude/copilot/codex roots) and 1 in `bin/journal_schedule.py` (LaunchAgents dir) — and
  never in `bin/journal_sources.py`, `bin/journal_summarize.py`, or any test. Every test and
  verify command uses synthetic fixtures in `tempfile` dirs with every root flag overridden,
  and proves the negative by snapshotting fixture trees (file set + bytes) before/after.
- **D2 — The adapter contract is a uniform pure-ish function over an explicit context.** Each
  adapter is `collect_<name>(ctx) -> report`. `ctx` keys (pinned): `day_start`, `day_end`
  (timezone-aware datetimes), `claude_projects`, `copilot_home`, `codex_home` (Path or None),
  `repos` (list[Path]), `pricing_claude`, `pricing_copilot` (dicts or None). Every adapter
  returns the pinned report shape (see D4) built from an `empty_report(source, priced)`
  helper. The ordered registry is `ADAPTERS = (("claude_code", collect_claude),
  ("copilot_cli", collect_copilot), ("codex_cli", collect_codex), ("git", collect_git),
  ("cursor", collect_cursor), ("vscode", collect_vscode))`, and the engine
  `run_adapters(ctx)` calls each inside try/except — an adapter exception lands in that
  source's `errors` list and the nightly run continues (a journal with one broken source is
  infinitely better than no journal). Rationale: explicit-context functions are trivially
  testable without touching real homes, new sources are one function + one registry row (the
  Cursor/VS Code promise), and pricing-as-parameter means tests never depend on real pricing
  values.
- **D3 — Reuse the proven parsers via importlib; never edit them.** The claude adapter drives
  `cost_report.extract_record/match_model/price/parse_timestamp`; the copilot adapter drives
  `copilot_usage.collect_sessions/effective_tokens/price_tokens/usd_to_aic/match_model`; the
  kit-task signal drives `copilot_execute.parse_tasks`. All loaded read-only via the
  `session_cost.py` importlib pattern. No parsing logic is duplicated, so format knowledge
  stays in one place per source.
- **D4 — The per-source report and digest schema are pinned (schema_version 1).** Every
  adapter returns: `{"source": str, "available": bool, "priced": bool, "deferred": bool,
  "sessions": int, "first_ts": str|None, "last_ts": str|None (ISO), "models": {key_or_raw_id:
  {"input": int, "output": int, "cache_read": int, "cache_write": int, "messages": int,
  "usd": float|None}}, "totals": {"input": int, "output": int, "cache_read": int,
  "cache_write": int}, "usd": float|None, "projects": [str], "tool_uses": int,
  "errors": [str], "notes": [str], "extra": dict}`. The digest is `{"schema_version": 1,
  "date": "YYYY-MM-DD", "generated_at": iso, "day_start": iso, "day_end": iso,
  "timezone": str, "sources": {name: report}, "totals": {"usd_priced": float,
  "sessions": int, "sources_active": [str], "unpriced_sources": [str]},
  "signals": {"kit_tasks": [...], "inbox": {...}, "wip": [...]}}` (field details pinned in the
  T6 brief). **Content hygiene is part of the schema:** the digest carries METADATA ONLY —
  no transcript/message text ever. The only free-text fields are commit subjects, kit task
  titles, inbox lines (user-authored), project/repo names, and error strings. This is the
  no-secrets-in-the-journal guarantee made structural.
- **D5 — Day scoping is explicit and per-source honest.** `--date YYYY-MM-DD` (default: today
  in the local timezone) defines `[local midnight, next local midnight)` as aware datetimes;
  `--utc` computes the window in UTC instead (what tests and verify commands use, so they
  never depend on the machine's timezone). Claude records are day-filtered per MESSAGE
  timestamp; records with no parseable timestamp cannot be day-assigned and are EXCLUDED but
  counted (`extra["untimestamped_records"]`) — a deliberate divergence from `cost_report.py`'s
  keep-regardless rule, because a daily journal must not attribute unknown-day work to today.
  Copilot sessions carry cumulative totals, so a session is attributed to the day of its LAST
  event (`last_seen` in window); untimestamped sessions are excluded and counted. Codex
  records follow the same in-window rule with tolerant timestamp parsing (ISO or epoch
  seconds/milliseconds). Git commits use `git log --since/--until` with the aware ISO bounds.
- **D6 — Codex is counted, never priced.** The codex adapter reads ONLY
  `session_index.jsonl` and `history.jsonl` (never `sqlite/`), extracts fields via pinned
  candidate-key lists (timestamps, session ids, models, cwd, token usage under
  `usage`-like keys) refined once against the real files (D1-sanctioned read-only peek),
  skips malformed lines, and reports `priced: False, usd: None` with per-model token counts
  where present and a pinned note that no Codex pricing exists in `data/` by design. Inventing
  a Codex price would violate the repo's source-of-truth invariant; honest "unpriced activity"
  is the correct output.
- **D7 — Git activity is a first-class deterministic source.** For each configured repo root
  (from `journal/config.json` `"repos"` + repeatable `--repo` flags): `git -C <root> log
  --since <day_start> --until <day_end> --pretty=format:%h%x1f%aI%x1f%an%x1f%s%x1e
  --no-show-signature` (unit/record separators — commit subjects with `|` can't break
  parsing), `git -C <root> status --porcelain` (dirty/untracked counts), `git -C <root>
  rev-parse --abbrev-ref HEAD` (branch). All read-only plumbing, `subprocess.run` with
  `timeout=20`, per-repo failures collected into `errors`. Commits capped at 50/repo (note
  when truncated). This is the cheap, high-signal "what I shipped" record, and the ONLY
  subprocess use in the collector path.
- **D8 — Deterministic collector and model summarizer are separate scripts with one seam:
  `digest.json`.** The collector is cheap, testable, model-free, and ALWAYS runs; the
  summarizer is a pure consumer of the digest file. This means the nightly schedule still
  produces a complete structured record even if the model step fails, tests can exercise
  either side alone, and the summarizer can be re-run (or re-routed to a different model)
  against an existing digest at any time.
- **D9 — The summary dispatch is an injectable callable; the default shells `claude -p`.**
  `runner(argv, prompt) -> (rc, text)`; `build_dispatch(model_id, claude_bin) -> [claude_bin,
  "-p", "--model", model_id]` with the prompt on STDIN (no ARG_MAX risk, nothing sensitive in
  `ps` output). This reuses the user's existing Claude Code auth — no API key, no new
  dependency (same seam as `bin/copilot_execute.py`'s injectable runner). Tests inject fake
  runners or a temp stub executable NEVER named `claude`; `--dry-run` prints the model ladder,
  argv, and all three prompts, and spawns/writes nothing. Routing is data-driven: tier ladder
  `("haiku", "sonnet", "opus")` (structural tier vocabulary, like cost_report's
  `EXPENSIVE_TIERS` — never model ids), start tier default `sonnet`, model = FIRST model of
  that tier in `data/pricing.json` file order, at most ONE escalation to the next tier, capped
  at `opus` (a nightly journal never auto-escalates to frontier). A doc is accepted when
  `rc == 0` and `output_ok(text)` (non-empty, ≥ 200 chars, first non-whitespace char `#`).
  **Disclosed privacy consideration:** the summary step SENDS THE DIGEST to a model —
  project/repo names, commit subjects, kit task titles, and inbox text leave the machine via
  the user's own Claude account. This is stated in the module docstring, the `--dry-run`
  header, the skill, and the docs. (D4's metadata-only rule bounds what can leak.)
- **D10 — Next-day planning = deterministic signals, then prose.** The collector pre-structures
  three signal families into the digest: `kit_tasks` (status `pending`/`in-progress` from
  every `.claude/kits/*/TASKS.md`, via `parse_tasks` — kit, id, title, status, model; capped
  at 100), `inbox` (lines from `journal/inbox.md`: blank and `#` lines skipped, leading
  `-`/`*`/`[ ]` markers stripped, capped at 100 with a truncation note — this is where the
  user drops meeting notes and email to-dos today, and where Graph/MCP output would land
  later), and `wip` (repos with dirty/untracked files + current branch, from the git source).
  The summarizer's next-day prompt turns exactly these signals into `next-day.md`: what to
  start, what to run AND HOW (concrete commands), tasks/to-dos.
- **D11 — One gitignored personal-data root: `journal/`.** Layout: `journal/<YYYY-MM-DD>/`
  (`digest.json`, `narrative.md`, `technical.md`, `next-day.md`, `summary-meta.json`),
  `journal/inbox.md`, `journal/config.json` (v1 keys: `"repos"`; unknown keys ignored),
  `journal/logs/` (launchd stdout/stderr). A single `.gitignore` entry (`journal/`) covers
  everything personal — simpler and safer than scattering an output tree and a `tasks/` inbox
  across two roots. The gitignore entry lands FIRST (Phase 1) so no real run can ever race a
  commit. Default journal root = `<plugin root>/journal`; every test overrides
  `--journal-dir` to a temp dir.
- **D12 — Scheduling: launchd plist, installer that writes but never loads.**
  `journal_schedule.py install` renders the plist with `plistlib` (Label
  `com.polytropos.daily-journal`, `ProgramArguments = [sys.executable,
  <abs bin/journal_schedule.py>, "run"]`, `StartCalendarInterval` Hour/Minute — default
  22:00, `WorkingDirectory` = plugin root, `StandardOutPath`/`StandardErrorPath` under
  `journal/logs/`), writes it into `--launch-agents-dir`, and PRINTS the `launchctl bootstrap
  gui/$UID <plist>` / `bootout` commands for the USER to run. The script itself never
  executes `launchctl` — in fact `bin/journal_schedule.py` contains no `subprocess` import at
  all: its `run` subcommand calls the collector's and summarizer's `main(argv)` in-process
  via importlib (injectable as `cmd_run(args, collect_main=None, summarize_main=None)` for
  tests), with `--dry-run` and `--collect-only` passthrough. Absolute paths inside the plist
  are correct and necessary (the statusline precedent: no `${CLAUDE_PLUGIN_ROOT}` outside
  plugin context); they are computed at install time, never committed. During this kit the
  installer only ever targets temp `--launch-agents-dir` dirs.
- **D13 — `skills/journal/` is the ONE sanctioned addition under `skills/`.** The plugin is
  installed live, so the new SKILL.md is runtime behavior: `/polytropos:journal` runs
  the collector via `${CLAUDE_PLUGIN_ROOT}` (absolute-path fallback rule), then lets the
  CURRENT session draft the three documents from `digest.json` using the exact prompts from
  `journal_summarize.py --dry-run` (default — no nested model spend), with the headless
  `journal_summarize.py` run as the alternative; it also documents inbox usage and the
  schedule installer, and states the privacy note. No existing skill, mirror, or
  `.claude-plugin/` file changes.

## Constraints and OUT-OF-SCOPE fence

Executors must NOT:

- **Read OR write the real `~/.claude`, `~/.copilot`, or `~/.codex` from any test or verify
  command.** Runtime defaults may point there (D1's four `Path.home()` constants); execution
  never does. One narrow exception: the T3 implementer's sanctioned read-only peek at
  `~/.codex/session_index.jsonl` / `~/.codex/history.jsonl` (`head`-style, a few lines, never
  a write, never the sqlite dir) to learn field names — nothing else, and nothing under
  `~/.claude` or `~/.copilot` ever.
- **Open any SQLite/`*.db` file anywhere** — not `~/.codex/sqlite/`, not Copilot's
  `session.db`, not Cursor/VS Code's `state.vscdb` (deferred precisely for this reason). No
  `import sqlite3` in any new file. JSONL and flat text only.
- **Invoke a real `claude`, `copilot`, or `codex` CLI from tests, verify commands, or anything
  run during execution.** The summarizer's real dispatch (`claude -p`) is runtime-only:
  tests inject runners/stub executables (never named `claude`) and `--dry-run` is the only
  CLI smoke path. `bin/journal_schedule.py` never spawns processes at all.
- **Execute `launchctl`, or write outside this repo and the test temp dirs** — `~/.claude/`
  and `~/Library/LaunchAgents` included. The plist installer runs only against temp
  `--launch-agents-dir` dirs during this kit; loading the schedule is the user's later, manual
  step. Do not re-install/refresh the plugin.
- **Add network, OAuth, tokens, or secrets in any form.** The Graph/MCP augmentation is
  deferred BY DESIGN — documented, not built. No `urllib` fetches, no credentials, nothing
  secret written to the journal, logs, or git.
- **Edit `data/pricing.json` or `data/pricing.copilot.json`**, or hardcode prices, credit
  values, allowances, or model ids anywhere new (tier-vocabulary strings like `"sonnet"` /
  `"opus"` and synthetic fixture ids/values in tests are the sanctioned exceptions). No Codex
  pricing may be invented (D6).
- **Edit any existing `bin/` or `tests/` file, existing `skills/*`, the generated
  `skills/*/references/` mirrors, `.claude-plugin/`, `copilot/`, or the completed kits**
  (`harden-plugin`, `aesop-bridge`, `copilot-harness`, `copilot-workflow`, `copilot-costviz`)
  or their agents. Existing bin scripts are imported read-only. Sanctioned edit targets among
  existing files: `.gitignore` (T1), `README.md` (T13), `CLAUDE.md` (T14) — pinned insertions
  only. Everything else this kit creates is a NEW file (`bin/journal_*.py`,
  `tests/test_journal_*.py`, `skills/journal/SKILL.md`, `docs/DAILY-JOURNAL.md`).
- **Add dependencies or tooling.** Python stdlib-only; no pip, no pytest, no requirements
  files; no node/npm; no YAML parser (none is needed — `parse_workspace` is reused).
- **Build the deferred work**: no Cursor/VS Code adapter implementation beyond the registered
  stubs + notes; no Teams/Outlook/Graph/MCP code; no per-message live watching, no daemons
  beyond the launchd plist.
- **Commit or push.**

## Risks & tripwires

- **Live-home safety — THE #1 RISK.** These scripts default to the user's real `~/.claude`,
  `~/.copilot`, `~/.codex`, and `~/Library/LaunchAgents`. TRIPWIRES: any test or verify
  command that runs a journal script without overriding EVERY root flag to a temp fixture;
  `Path.home()` anywhere except the four pinned runtime-default constants; any write
  primitive (`open(...,"w")`, `write_text`, `mkdir`, `rename`, `unlink`, `chmod`) aimed under
  a SOURCE root (the journal dir is the only write target, and in tests it is always a temp
  dir); any `*.db` open or `sqlite3` import. Tests prove read-only by byte-snapshotting
  fixture homes around full runs.
- **A real model call from tests — the #2 risk.** Every dispatch goes through the injectable
  runner; the default runner is exercised only against temp stub executables never named
  `claude`. TRIPWIRE: any test or verify path that could resolve the real `claude` binary
  (or `copilot`/`codex`), or a `--dry-run` that spawns anything.
- **Personal data in git.** The journal and inbox contain project names, commit subjects, and
  the user's own notes. TRIPWIRE: `journal/` missing from `.gitignore`, any task writing a
  real digest into the repo's `journal/` during execution (tests use temp `--journal-dir`
  only), or any fixture containing realistic personal data.
- **Privacy of the summary step.** The digest leaves the machine when summarized (D9,
  disclosed). TRIPWIRE: transcript/message TEXT entering the digest (D4 forbids it — the only
  free text is commit subjects, kit titles, inbox lines, names, errors), or the privacy note
  missing from the summarizer docstring/dry-run/skill/docs.
- **Codex format drift / guessing.** The codex JSONL is not format-pinned. TRIPWIRE: a codex
  parser that crashes on unknown shapes instead of skipping-and-counting; token/cost fields
  fabricated when absent; a Codex price appearing anywhere; the sqlite dir touched.
- **Timezone flakiness.** Day windows depend on local tz. TRIPWIRE: a test or verify that
  asserts day membership without `--utc` (or without passing explicit aware windows to
  adapters); wall-clock-dependent assertions.
- **Escalation runaway.** TRIPWIRE: more than one escalation per document, any auto-escalation
  past `opus` tier, or a hardcoded model id in the ladder (must be computed from
  `data/pricing.json` file order per tier at run time).
- **Same-file collisions.** T2→T3→T4 all build `bin/journal_sources.py` and are strictly
  serial; dispatching them in parallel corrupts the file. TRIPWIRE: parallel dispatch of
  same-file tasks.
- **Suite/paths quirks.** Verify commands use `python3 -m unittest discover -s tests
  [-p '<file>.py']` — never the dotted-module form (broken on this machine). Paths via
  `Path(__file__).resolve()`, never `$PWD`. No `/private/tmp/` session-scratchpad path in any
  deliverable.

## Still deferred after this kit (designed, not built)

1. **Cursor and VS Code adapters.** Usage sits in `state.vscdb` (SQLite, undocumented,
   drifting schema). The adapter contract (D2) already reserves their registry rows; the
   implementation needs a safe-copy read strategy (copy the DB + WAL to a temp dir, open the
   COPY read-only, so the live files are never touched) and per-version schema probing —
   design notes live in `docs/DAILY-JOURNAL.md`'s Deferred section. Slot-in cost: one
   `collect_<name>(ctx)` function + fixtures; no engine changes.
2. **Teams/Outlook augmentation.** Two designed paths, both deferred: (a) Microsoft Graph API
   (OAuth device-code flow, `Calendars.Read`/`Mail.Read`, a token cache OUTSIDE the repo,
   network at collect time) writing pre-structured items into the same `signals.inbox`
   shape; (b) an MCP connector (Teams/Outlook MCP server queried by the session running the
   journal skill) appending to `journal/inbox.md` itself. Either lands as a new signal
   provider feeding the SAME inbox signal — no digest schema change. v1 stays offline: the
   user drops notes into `journal/inbox.md` by hand.
3. **Cross-day/weekly rollups** (a `--week` mode aggregating digests) — the dated digest
   files are already the substrate; explicitly not in v1.
