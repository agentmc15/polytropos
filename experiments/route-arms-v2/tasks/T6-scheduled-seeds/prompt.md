# Task: Date-aware scheduled runbook seeds

`bin/journal_plan.py` builds the next-day runbook from digest signals, carried cards, and hand-written `journal/plan/seed.md` lines. Today every seed line becomes a card on every build. Add a small offline scheduling grammar for `seed.md` so recurring/manual reminders can appear only on the intended runbook dates, while preserving all existing runbook behaviour when the new grammar is absent.

## Required behaviour

1. Keep ordinary seed lines byte-compatible with the existing behaviour: after the existing blank/comment skip and one leading marker strip (`- `, `* `, or `[ ] `), a line with no scheduling directive still becomes one `seed` card on every build, with the same title, `source`, `model-hint`, and two-line What/How body as before.
2. Recognise scheduling directives after the existing marker stripping and whitespace trim. Directive keywords are case-insensitive; titles are stripped of surrounding whitespace; the rendered card title and What/How body must contain only the title, never the directive prefix.
3. Support one-time seeds: `on YYYY-MM-DD: title`. Include the seed only when the runbook date being built (`--for`, or the default day after `--date`) equals that date. Valid dates use real calendar validation, so leap days are accepted only in leap years and month/year boundaries are handled by `datetime.date`, not string arithmetic.
4. Support interval seeds: `from YYYY-MM-DD every Nd: title`, where `N` is an integer from 1 through 366. Include the seed when the runbook date is on or after the start date and the whole-day difference from the start date is divisible by `N`. Exclude it before the start date. Month-end, year-end, and leap-year differences must work correctly.
5. Support weekday seeds: `every mon[,tue,wed,thu,fri,sat,sun...]: title`. The allowed weekday tokens are the three-letter names `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, and `sun` (case-insensitive, with optional spaces around commas). Include the seed when the runbook date's weekday is one of the listed days.
6. Invalid scheduled seed directives must not abort the build and must not create a card. Instead, add a note to the rendered runbook exactly as `invalid seed directive in seed.md line <N>: <reason>`, where `<N>` is the 1-based physical line number in `seed.md` before blank/comment skipping. Use these exact reason strings where applicable: `expected 'on YYYY-MM-DD: title'`, `expected 'from YYYY-MM-DD every Nd: title'`, `expected 'every mon[,tue...]: title'`, `invalid date '<value>'`, `interval must be 1..366 days`, `unknown weekday '<token>'`, and `missing title`.
7. Comments and blank lines in `seed.md` remain silently ignored and do not produce invalid-directive notes. A mixture of valid, invalid, and ordinary seeds should build successfully with exit code `0`; valid cards keep the same relative order they had in `seed.md` after carried and digest cards.
8. Rebuild and dedup semantics stay unchanged except for directive stripping: scheduled seed cards use `source: seed` and deduplicate by the stripped title just like ordinary seed cards. Existing carried/enriched cards with the same title still win over newly due scheduled seed cards.
9. Existing output must be byte-for-byte unchanged for runs whose `seed.md` has only ordinary seed lines (aside from pre-existing harness estimate data that the current code already computes). Existing `check`, `done`, `defer`, and `prompt` behaviour must remain unchanged.

## Scope and rules

- You may change `bin/journal_plan.py` and add/update tests under `tests/` only.
- Keep the module offline and advisory-only: no subprocesses, no schedulers/dispatchers, no network, no database opens, and no reads from real home directories.
- Python remains stdlib-only: do not add dependencies, do not use pip, and do not use pytest.
- Add unit tests for the new scheduled-seed behaviour using fixture directories and explicit dates only.
- The existing regression command must stay green from the repo root: `python3 -m unittest discover -s tests -p test_journal_plan.py`.
