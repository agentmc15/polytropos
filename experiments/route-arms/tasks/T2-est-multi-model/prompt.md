# Task: compare several models in one `copilot_pricing.py est` call

`python3 bin/copilot_pricing.py est PROFILE MODEL_ID [--cache-hit F] [--json]` estimates one
task's cost on one model. Extend it so `MODEL_ID` may be a comma-separated list, for example
`est M gpt-6-luna,claude-opus-5.5`.

## Required behaviour

1. **One id is unchanged.** With a single id (no comma), text and `--json` output, exit codes,
   and error messages are byte-for-byte what they are today.
2. **Parsing.** Split on commas; whitespace around each id is ignored
   (`"a, b"` == `"a,b"`). An empty segment (`"a,,b"`, `"a,"`) or a repeated id exits 2 with a
   message on stderr and nothing on stdout.
3. **Unknown ids.** If any id in a list of two or more is not a model in
   `data/pricing.copilot.json`, exit 2, print nothing on stdout, and name **every** unknown id
   on stderr.
4. **Text output (2+ ids).** For each id, in the order given, print exactly the block the
   single-id command prints for that id; separate consecutive blocks with one empty line.
   After the last block print one line: `cheapest: <model_id> (<aic> AIC)` where `<aic>` is
   formatted like the block's `aic:` line (one decimal). A tie goes to the id listed first.
5. **JSON output (2+ ids).** A JSON array (same `indent=2` style) of the per-model objects the
   single-id command emits, in the order given. No other keys or wrapper.
6. `--cache-hit` and the profile apply to every id. An unknown profile still exits 2.
7. Update the `est` argument's `--help` text to mention the list form.

## Scope and rules

Change only `bin/copilot_pricing.py` and files under `tests/`. All numbers come from the
pricing data at run time: do not hardcode prices, AIC rates or model ids in `bin/`. Add unit
tests for the new behaviour. The existing suite must stay green:
`python3 -m unittest discover -s tests -p test_copilot_pricing.py` (run from the repo root).
