# NOTES — harden-plugin execution

Cross-task learnings maintained by the execute orchestrator. Read before dispatching later tasks.

## Progress
- **T1 — done.** `parse_timestamp` coerces naive → UTC. Verified independently (`T1 OK`).
- **T2 — done.** `match_model` tightened to exact-or-dash-suffix; synthetic (`<...>`) models skipped in the unpriced tally; explanatory comment added. Verified independently (`T2 OK`).
- **T3 — done.** 28 stdlib tests (18 cost_report + 10 statusline), adversarially verified PASS:
  discover resolves to local `./tests/`, both NOTES hazards honored (session_id-gated segment
  tests use isolated temp state dirs; real `~/.claude/polytropos/state/` untouched).
  The exact-output guard `⬢ Fable 5 | $<redacted> | ctx 42%` depends on payloads WITHOUT `session_id`
  — T5's setup-skill sample must stay session_id-free or update the expected shape accordingly.
- **T4 — done** (opus). Kit contract mirrored into both architect+execute skills; adversarially
  verified PASS (all D5 elements present identically in substance).
- **T5 — done** (sonnet), one correction round: the first pass added a concrete
  `$<redacted>` output example to skills/setup/SKILL.md, which broke done-definition #5's
  `grep -rE '\$[0-9]' skills/` gate; fixed to the pinned shape wording (no `$<digit>` anywhere
  in skills/ now). Sample payload stays session_id-free per the T3 note. Verified PASS.
- **T6 — done** (haiku). Four pinned replacements exact; D1 sweep greps clean. Verified PASS.
- **T7 — done** (sonnet). README Install section leads with marketplace add/install (CLI syntax
  confirmed against `claude plugin --help` per the tripwire); `--plugin-dir` kept as
  session-only secondary. Verified by orchestrator (`T7 OK`).
- **T8 — done** (sonnet). Verification-only final sweep: suite green (28 tests), D1 greps clean,
  pricing.json untouched and structurally intact, docs price tables match pricing.json (no
  drift), both scripts run end-to-end, scope confined to allowed paths. Rerun independently by
  orchestrator (`T8 OK`).

## ⚠️ For T8 — parallel aesop-bridge kit files in the working tree
`.claude/kits/aesop-bridge/`, `.claude/agents/aesop-bridge-*.md`, and one CLAUDE.md bullet
("For `aesop-bridge` specifically: ...") belong to a separate, not-yet-executed kit architected
this session. They fall under allowed paths (step 6's scope check: `.claude/kits/`,
`.claude/agents/`, `CLAUDE.md`) — do not flag or revert them.

## ⚠️ For T3 and T8 — `unittest discover` name collision
Before `tests/` exists, `python3 -m unittest discover -s tests -v` from repo root resolves to an
UNRELATED `tests` package in site-packages (Polymarket CLOB client — ~115 tests, one errors on a
missing `responses` module). This is pre-existing environment noise, NOT a regression.
After T3 creates `./tests/test_cost_report.py` + `./tests/test_statusline.py`, **explicitly confirm
`discover -s tests` resolves to the LOCAL `./tests/` dir** (the run should list our test names, not
Polymarket's). If discover still picks up site-packages, the T3/T8 verify commands are testing the
wrong thing. Per D2 the local `tests/` has no `__init__.py`; that's intended.

## ⚠️ For T3 — statusline.py gained segments AFTER the kit was architected
Outside this kit, `bin/statusline.py` was extended with three new segments: a token total next to
cost (`$X · NNN tok`), a live `⚡ N agents` subagent count, and an always-on `🔥 Fable ×N` daily
Fable-usage tally (bright when a Fable subagent is active). These read per-session/daily state files
under `~/.claude/polytropos/state/` written by `bin/agent_tracker.py` hooks.
- T3's briefed test_statusline cases STILL HOLD as written: the new segments only render when the
  payload carries a `session_id` (real sessions) — the brief's exact-match payloads omit it, so the
  extra segments stay hidden and `⬢ Fable 5 | $<redacted> | ctx 42%` remains exact. Verified.
- T3 SHOULD additionally add cases WITH a `session_id` + seeded state files to cover the new token /
  `⚡ agents` / `🔥 Fable ×N` rendering, so they don't regress. Keep all state under a temp/unique
  session id and clean up (do not pollute the real `state/` dir or today's `fable-usage-*.count`).
- Do NOT revert or "simplify" these statusline segments — they are intended, shipped behavior.
