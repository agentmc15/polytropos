# Task: Harden session_cost transcript edge cases

`bin/session_cost.py` prices one Claude Code session by reading a main JSONL transcript plus optional task/subagent JSONL files. It already handles valid transcript records correctly. Fix the edge cases below without changing the report for valid records.

## Required behaviour

1. Validate token counts before pricing or deduplication. For each extracted usage dict, the four public token buckets are `input`, `output`, `cache_read`, and `cache_write`. A missing or `None` bucket is zero. A bucket is valid only when it is an integer `>= 0`; booleans, strings, floats, negative integers, lists, objects, and any other type are invalid. If any bucket is invalid, skip the whole record without raising and without adding its message id to the dedupe set. A record whose four normalized buckets are all zero remains ignored as it is today.
2. Unknown model records must not crash even when the raw model value is not a string. Treat unknown model labels as `str(model)` for the `unpriced` map. Unknown labels whose string form begins with `<` are placeholders and must be ignored, as placeholder strings are today. Unknown, placeholder, zero-usage, and malformed records must not reserve a duplicate message id.
3. Deduplicate by message id only after a record has valid non-zero usage and a known priced model. Only a non-empty string message id participates in deduplication. If two accepted priced records have the same string id, the first accepted priced record wins and later accepted priced records with that id are skipped. Records with no id or a non-string id are never deduped against each other and are each counted when otherwise valid.
4. The public `unique_messages` value returned by `collect(...)` and emitted in JSON under `sources.unique_messages` must mean the number of accepted priced messages after deduplication. Count accepted priced records without a string id. Do not count unpriced, placeholder, malformed, zero-usage, or duplicate-priced records.
5. Keep all valid-record pricing behaviour unchanged. Costs, cache-read/cache-write accounting, intro/base timestamp handling, per-model rows, grand token buckets, unpriced token totals, read-error collection, and row ordering must still derive from `data/pricing.json` through the existing pricing helpers; do not hardcode prices, model ids, dates, or multipliers.
6. `gather_files(...)` and the CLI `--include` option must support absolute glob patterns such as `/some/repo/fixtures/*.jsonl` as well as the existing relative globs, directories, and explicit paths. Matching files are added in sorted order and then de-duplicated by resolved path. A glob with no matches adds nothing and must not crash.
7. `sources.subagent_transcripts` in JSON, and the markdown source sentence, must count only unique existing `*.output` files found through `--tasks-dir` or automatic task-dir discovery. Extra files supplied by `--include` are scanned and included in `sources.files_scanned`, but they are not subagent transcripts. `--no-subagents` still disables task-dir discovery/counting, but must not disable `--include` scanning.
8. Keep existing behaviour outside these fixes unchanged: malformed JSON lines are ignored, unreadable files are reported in `read_errors`, unknown non-placeholder models are not priced, missing sessions still exit, `--json` shape stays compatible except for corrected counts, and the existing markdown wording stays the same except where the corrected subagent count changes the already-existing source sentence.

## Scope and rules

- You may change `bin/session_cost.py` and add or update unit tests under `tests/` only.
- Python is stdlib-only; do not add dependencies, do not use pytest, and do not invoke `copilot`, `codex`, `claude`, `agent`, or other external CLIs.
- Do not hardcode prices, model ids, pricing dates, cache multipliers, or assumptions from `data/pricing.json`; derive them at run time.
- Add unit tests for malformed usage values, negative values, unknown and non-string models, duplicate ids, id-less records, absolute include globs, and corrected subagent counts.
- Run from the repo root and keep green: `python3 -m unittest discover -s tests -p test_session_cost.py`. If you add another `test_session_cost*.py` module, it must also pass with `python3 -m unittest discover -s tests -p 'test_session_cost*.py'`.
