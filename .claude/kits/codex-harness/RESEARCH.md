# RESEARCH — codex-harness T1 sanctioned peek

Read-only, bounded peek at the real `~/.codex` per PLAN.md D9, using exactly the command set
pinned in T1's brief. Nothing under `~/.codex` was written; no `*.db` was opened; the `codex`
binary was never invoked. Content hygiene: only key names, shapes, and model-id strings are
recorded below — no prompt text, no transcript text, no thread titles.

## Files present

Directly under `~/.codex` (from `ls -la`): `config.toml`, `session_index.jsonl`,
`history.jsonl` (see below — absent), `sessions/` directory, plus a number of files/dirs
outside this kit's scope that were NOT opened or read further (hard limit: no `*.db`, no extra
reads): `auth.json`, `installation_id`, `models_cache.json`, `.codex-global-state.json(.bak)`,
`.personality_migration`, and several SQLite stores (`goals_1.sqlite`, `logs_2.sqlite` +
`-shm`/`-wal`, `memories_1.sqlite`, `state_5.sqlite`, a `sqlite/` dir) and other dirs
(`cache/`, `computer-use/`, `plugins/`, `rules/`, `shell_snapshots/`, `skills/`, `tmp/`,
`vendor_imports/`, `ambient-suggestions/`). None of these were listed further or opened.

`ls -R ~/.codex/sessions`: layout is **confirmed** `YYYY/MM/DD/rollout-*.jsonl` — observed
`sessions/2026/05/10/rollout-2026-05-10T20-05-11-<uuid>.jsonl` and two files under
`sessions/2026/05/27/rollout-2026-05-27T13-3{5,7}-*-<uuid>.jsonl`.

`history.jsonl`: **absent** on this machine (`head -c` returned nothing / exit 1) — recorded
honestly per the brief's "if a path is absent, record absent" instruction.

`session_index.jsonl`: present, non-empty (3 lines sampled within the 2000-byte bound).

## config.toml

Top-level keys/tables observed within the first 2000 bytes: `model`, `model_reasoning_effort`,
`notify`, `[marketplaces.<name>]` (with `last_updated`/`source_type`/`source`),
`[plugins."<name>@<source>"]` (with `enabled`), `[projects."<path>"]` (with `trust_level`),
`[desktop]` (+ `[desktop.open-in-target-preferences]` / `.perPath`), `[features]`,
`[mcp_servers.<name>]` (+ `.env`). No `[profiles.*]` table was observed, but the read was
truncated at 2000 bytes mid-way through an `[mcp_servers.*]` block, so absence of
`[profiles.*]` is **inconclusive**, not confirmed-absent.

Literal `model` value: `"gpt-5.5"`. Literal `model_reasoning_effort` value: `"xhigh"`. Both are
model-id/config strings, not content. No GPT-5.6 id string appears in the sampled window.

## Rollout record shapes

Sampled file: the newest rollout by `find | sort | tail -1`
(`sessions/2026/05/27/rollout-2026-05-27T13-37-08-<uuid>.jsonl`), read with `head -c 4000`.

Only one record was reached within the 4000-byte bound: `type: "session_meta"`. Wrapper keys:
top-level `timestamp`, `type`, `payload`. `payload` keys observed: `id`, `timestamp`, `cwd`,
`originator` (value `"Codex Desktop"` — this `~/.codex` is shared with the Codex Desktop app,
not CLI-only), `cli_version`, `source` (value `"vscode"`), `thread_source`, `model_provider`
(value `"openai"`), `base_instructions` (an object with a `text` field — free text, deliberately
NOT harvested).

No explicit `model` id field appears inside this `session_meta` payload (only
`model_provider: "openai"`); the 4000-byte bound was consumed entirely by
`base_instructions.text` before the file reached any `turn_context`, `event_msg`, or
`token_count` record. **No usage fields observed within the sampled window** — this is
inconclusive (bound exhausted), not a confirmed absence of the `info.total_token_usage` /
`last_token_usage` structure PLAN.md flags as medium-confidence.

## Model ids observed

- `"gpt-5.5"` — `config.toml`'s `model` key.
- No other model-id strings were reached within the sampled windows (the rollout sample never
  got past `session_meta`'s `base_instructions.text` before the 4000-byte bound).
- **No GPT-5.6 id string of any spelling appears anywhere in this peek.**

## Implications

- Confirmed (upgrades a "high confidence" PLAN.md item to observed-on-this-machine): the
  `sessions/YYYY/MM/DD/rollout-*.jsonl` layout is real, and `session_meta` is a real record
  `type` with a `payload` wrapper, matching PLAN.md's medium-confidence shape claim.
- Not confirmed, not contradicted: `turn_context`/`event_msg`/`token_count` record shapes and
  the `info.total_token_usage`/`last_token_usage` usage fields — the 4000-byte bound was spent
  on one large `base_instructions.text` field before reaching them. `config.toml`'s
  `[profiles.*]` table is likewise inconclusive (read truncated before it would have appeared).
- No GPT-5.6 model id was observed anywhere (only `"gpt-5.5"` in `config.toml`). **T2's pinned
  best-effort ids (`gpt-5.6-sol` / `gpt-5.6-terra` / `gpt-5.6-luna`) need NO substitution** —
  nothing here contradicts or confirms them; they remain UNCONFIRMED exactly as PLAN.md states.
- `codex_usage.py` (T11) cannot be shown by this peek to have real token data to lean on: the
  one sampled record with a usage-relevant shape (`session_meta`) carries none, and the
  token-usage record types were never reached. T11 should still implement both branches of the
  D8 honesty ladder (token-priced + activity-only), but must not assume the token branch will
  ever fire on this machine — the activity-only, unpriced branch is the safe expected default.
- The real `~/.codex` also holds several SQLite stores (`logs_2.sqlite` notably, 26MB+) that
  plausibly carry richer usage/telemetry data than the JSONL surfaces — but these are
  explicitly OFF-LIMITS (hard limit: never open a `*.db`) both for this peek and for
  `codex_usage.py` at run time, reinforcing why the JSONL-only honesty ladder (not a DB read)
  is the correct, safe design for T11.
- `history.jsonl` is absent on this machine (unlike the daily-journal kit's earlier peek, which
  found it present but content-thin) — one more reason `codex_usage.py` must degrade gracefully
  when expected files are simply missing, not just when they're present-but-empty.
