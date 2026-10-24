# Task: Add project filters to cost_report

`bin/cost_report.py` reports Claude transcript usage by scanning project directories. Large local stores often contain many unrelated projects, so the report needs opt-in project-name filters while preserving the existing unfiltered report exactly.

## Required behaviour

1. Add repeatable CLI options `--project PATTERN` and `--exclude-project PATTERN`. Both options filter by the transcript project name, defined exactly as the first path component under `projects_dir` for each `*.jsonl` file.
2. Filter patterns use `fnmatch.fnmatchcase` shell-style matching against the whole project name. Matching is case-sensitive. `--project` patterns are ORed; with no `--project`, every project is initially included. `--exclude-project` patterns are ORed and always win over includes.
3. Each filter option may be passed more than once, and each argument may contain comma-separated patterns. Preserve normalized pattern order. Trim whitespace around comma-separated pieces.
4. Reject an empty pattern (including whitespace-only arguments or empty comma pieces such as `alpha,`) and reject any pattern containing `/` or `\`. The CLI must exit with argparse's normal error status 2 and an error message containing `project filter patterns must not be empty` or `project filters match project names only, not paths` respectively.
5. `build_report_payload(...)` must accept keyword arguments `project=None` and `exclude_project=None`. They accept the same string/list inputs as the CLI, apply the same validation, and add a JSON-serializable `project_filters` object of the exact form `{"include": [...], "exclude": [...]}` to every payload branch, including missing-directory payloads.
6. Add module-level helpers `normalize_project_patterns(raw)` and `project_allowed(project, include, exclude)` implementing the same validation and matching semantics so callers can reuse the filter logic directly.
7. Project filters apply before reading, parsing, message-id deduplication, unknown-model aggregation, session aggregation, downgrade-candidate selection, and parse/read error accounting. Excluded projects must leave no trace in totals, sessions, by-model rows, unknown models, downgrade candidates, labels except the filter labels, or dedupe state.
8. When any filter is active, append payload labels `project include: <patterns>` and/or `project exclude: <patterns>` where `<patterns>` is the comma-space joined normalized list. Do not add these labels when the corresponding normalized list is empty.
9. The existing unfiltered markdown output must remain byte-for-byte unchanged. When filters are active, the markdown report must insert exactly one line after the title blank line and before the total line: `Project filters: include \`a\`, \`b\`; exclude \`c\`` using only the active clauses and backticks around each pattern. End that line with a blank line before the total.
10. If filters select no priced records, keep the existing absence semantics: `dir_present` stays true for a present directory, `found` is false, totals are zero, and the `no transcripts in window: <projects_dir>` label is present.
11. Keep the existing pricing, timestamp handling, unknown-model handling, session ordering, downgrade-candidate rules, JSON mode, and missing-directory markdown exit behaviour unchanged except for the documented filter fields/labels/output line.

## Scope and rules

- You may change `bin/cost_report.py` and add or update unit tests under `tests/` only.
- Python is stdlib-only; do not add dependencies, do not use pytest, and do not invoke `copilot`, `codex`, `claude`, `agent`, or other external CLIs.
- Do not hardcode prices, model ids, pricing dates, or assumptions from `data/pricing.json`; derive them at run time.
- Add unit tests for the new behaviour, including validation failures, include/exclude precedence, glob matching, JSON payload shape, and unchanged unfiltered markdown.
- Run from the repo root and keep green: `python3 -m unittest discover -s tests -p test_cost_report.py`. If you add another `test_cost_report*.py` module, it must also pass with `python3 -m unittest discover -s tests -p 'test_cost_report*.py'`.
