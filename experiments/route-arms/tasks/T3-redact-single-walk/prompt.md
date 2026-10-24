# Task: one pattern walk in `bin/redact.py`

`scan()` and `redact()` in `bin/redact.py` each contain their own loop that walks `PATTERNS`
(or the `patterns` argument), substitutes the placeholder, and counts matches by kind. The
two loops are written differently but must agree, and keeping them in step is a maintenance
hazard in a security-sensitive module.

## Required change

Refactor so the loop that applies the patterns exists **exactly once** in the module, and both
`scan()` and `redact()` rely on it. A private helper is the expected shape.

## Constraints

1. **No behaviour change.** For every input — including `None`, empty strings, overlapping
   credential shapes, custom `patterns` arguments, and every `limit` value — `scan`, `redact`,
   `redact_all`, `describe`, and `_cli` return and print exactly what they do today.
2. **Public surface unchanged.** Same public names, signatures, defaults and module constants
   (`PLACEHOLDER`, `PATTERNS`, `DEFAULT_FIELD_LIMIT`, `TRUNCATION_NOTE`). Any new name is
   private (leading underscore).
3. Keep the module's docstrings and comments truthful after the change.

## Scope

Change only `bin/redact.py` and files under `tests/`. Tests proving the two functions still
agree are welcome. Existing users must stay green:
`python3 -m unittest discover -s tests -p test_privacy_primitives.py` and
`python3 -m unittest discover -s tests -p test_journal_collect.py` (run from the repo root).
