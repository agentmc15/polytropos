# crossrepo-trend — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

  For `crossrepo-trend` specifically: NO skill is edited — `skills/` stays byte-unchanged
  (`git diff --quiet -- skills` in every verify; a change there is out of scope, stop and
  report) and therefore no shared-contract edit at all; `bin/routing_scorecard.py` is
  extended ADDITIVELY a FIFTH time — existing flags, signatures, output shapes, exit codes,
  and ALL FOUR prior demos' numbers (`--demo`, `--demo --live`, `--demo --history`,
  `--demo --by-task`) stay byte-stable, a lone `--kits-dir` (or none) keeps `--history`
  output BYTE-IDENTICAL to today (kit names unprefixed, JSON key set exactly the eight
  pre-existing keys — no `kits_dirs`, no `- scanned` lines), and the FOUR frozen test files
  (`tests/test_routing_scorecard.py`, `tests/test_reroute_live.py`,
  `tests/test_routing_history.py`, `tests/test_per_task_dollars.py`) stay byte-untouched
  (new tests go in `tests/test_crossrepo_trend.py`); cross-repo mode namespaces kit rows as
  `<label>/<kit>` (labels derived from the kits-dir path — `<repo>/.claude/kits` → the repo
  basename — or overridden via a `label=path` token; duplicate labels suffixed + noted,
  never silently merged), aggregates tiers/re-routes globally, and prices dollars through
  the SAME single `--projects-dir` under the unchanged degradation ladder (one `collect()`
  per scope, union ids priced once, missing transcripts noted + skipped, coverage labeled —
  never a fabricated figure); the ONE sanctioned real write in the whole script is
  `--history --snapshot`, which writes a date-named JSON card (`<YYYY-MM-DD>.json`,
  latest-wins per day) ONLY under the snapshot dir (default: gitignored `trends/`;
  `write_snapshot` validates the date grammar so nothing can escape the dir) — every other
  mode stays read-only, `--snapshot` is rejected with `--demo`, tests write snapshots only
  to temp `--snapshot-dir` dirs, and pure `--trend` scans no kits and never loads pricing;
  the trend is TEXT-ONLY (no charts/plots) and needs ≥2 snapshots to be called a trend (one
  snapshot renders the point plus a "no trend yet" note; zero → n/a; malformed/rogue
  snapshot files skipped + noted — never fabricated); `scan_kits`/`history_tier_stats`/
  `tally_reroutes`/`build_history`/`kit_cost_summary` and the `session_cost` pipeline are
  reused read-only, never edited or re-implemented; every test/verify uses synthetic kits,
  transcripts, and snapshot stores in temp dirs (`--kits-dir`/`--projects-dir`/
  `--snapshot-dir` always overridden — never the real `~/.claude`), zero `Path.home()` in
  new/edited Python; no hardcoded prices or real model ids (tier vocabulary, the
  `fable`→`frontier` alias, `TREND_SCHEMA_VERSION`, the filename/date/label grammar
  regexes, the `trends` dir name, the pinned demo snapshot dates, and synthetic fixtures
  are the sanctioned literals — demo/test transcript ids are computed from
  `data/pricing.json` at run time); sanctioned edit targets are ONLY
  `bin/routing_scorecard.py`, `.gitignore`, `docs/ROUTING-HISTORY.md`'s pinned pointer
  paragraph, and CLAUDE.md's pinned run-line, with new files
  `tests/test_crossrepo_trend.py` and `docs/ROUTING-TRENDS.md`; no journal coupling, no
  README changes, no new skills, no Copilot-side changes, no changes to
  `/route`/`/escalate`/`/fable-check`, no auto-snapshot scheduling, no per-task or
  per-agent trend aggregation, no main-session model switching.
