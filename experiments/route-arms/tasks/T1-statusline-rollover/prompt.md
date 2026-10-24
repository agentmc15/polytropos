# Task: fix the K→M rollover in `fmt_tokens`

`bin/statusline.py` renders token counts compactly with `fmt_tokens(n)`:

- below 1,000 → the integer as-is (`999` → `"999"`)
- thousands → whole K (`12_345` → `"12K"`)
- millions → one decimal M (`1_500_000` → `"1.5M"`)

**The bug.** Values just under one million round up to a four-digit K value:
`fmt_tokens(999_999)` returns `"1000K"`, as does `fmt_tokens(999_500)`. A count must never be
shown as 1000 or more of a unit when the next unit up exists.

## Required behaviour

1. Any value whose K rendering would read `1000K` or more is rendered in M instead, using the
   existing one-decimal M format (`999_500` → `"1.0M"`, `999_999` → `"1.0M"`).
2. Everything that renders correctly today renders exactly as it does today, including:
   values below 1,000 (and negative values) returned as `str(int(n))`; whole-K formatting with
   Python's default rounding; one-decimal M for values of 1,000,000 and above; string and float
   inputs coerced with `int(n)` as today.
3. Do not add new units (no `B`/`G`); values of a billion or more stay in M.

## Scope

Change only `bin/statusline.py` and files under `tests/`. Add or update unit tests that cover
the boundary. The existing suite must stay green:
`python3 -m unittest discover -s tests -p test_statusline.py` (run from the repo root).
