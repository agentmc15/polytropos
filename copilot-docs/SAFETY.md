# Safety and cost boundaries

This guide is a map of what in this repository's Copilot CLI bundle and documentation
generator can spend AI Credits (AIC), what is model-free/read-only, and where the honesty
boundaries are.

## What can spend AIC versus what is free

- **Can spend AIC:** dispatching a skill or agent in a live Copilot CLI session (for example `/route`, `/architect`, or `copilot --agent NAME -p "TASK"`), and any kit execution driven through `/execute` or `bin/copilot_execute.py` against a real Copilot CLI invocation.
- **Model-free / read-only:** installing the bundle (`bin/harness_select.py`), reading usage history (`bin/copilot_usage.py`), pricing and preference lookups (`bin/copilot_pricing.py`, `bin/copilot_prefs.py`), and everything in this documentation generator (`bin/copilot_docs.py build`/`check`/`report`).

## Tests, builds, and verifiers never invoke a real harness CLI

Every test and kit verify command in this repository is required to run without spending a
real user's AI Credits or touching the network. Tests that exercise dispatch logic stub or
mock the Copilot/Codex/Claude CLI entirely; the only sanctioned live-CLI smoke paths are
explicit `--dry-run`/`--demo` flags, which spawn nothing.

## No real home access in this documentation generator

`bin/copilot_docs.py` never reads or writes a real user home directory. It resolves its
manifest and docs root from its own file location inside this repository, reads pricing
and preferences through the repository's own `data/pricing.copilot.json` and
`prefs/copilot.json` (never `~/.copilot`), and every test for it uses temporary
directories.

## Prospective estimates versus historical usage estimates

Two kinds of numbers appear across this center and are never mixed:

- A **prospective document estimate** (in `AIC-REPORT.md`) is a forecast of what authoring one Markdown document in this center would cost, computed before any real generation happens.
- A **historical usage estimate** (from `bin/copilot_usage.py`) is an accounting of AI Credits already spent in past sessions, read from local session logs after the fact.

Neither one is derived from the other, and neither is a bill.

## AIC versus AIU, and API-equivalent/proxy honesty

Copilot itself reports usage in AI Usage units (AIU); this repository's pricing engine
works in AI Credits (AIC), a separate accounting unit defined by
`data/pricing.copilot.json`'s own billing-unit data. Figures labeled **API-equivalent** or
**relative-burn proxy** anywhere in this repository (including for subscription-billed
Codex activity) are never presented as an actual bill — a proxy dollar figure never enters
a billed total.

## Preferences never rewrite an agent's own frontmatter

`prefs/copilot.json` pins or excludes model ids only for tier resolution performed by this
repository's own drivers (for example `bin/copilot_execute.py`'s escalation ladder). It
never edits a `*.agent.md` file's own frontmatter `model:` default — dispatching an agent
directly, with no override, still resolves through Copilot's own agent-frontmatter
mechanism untouched by this repository's preferences.

## Serial kit execution and what `independent:` means

Kit execution through `/execute` runs one task at a time against
`bin/copilot_execute.py` — there is no parallel-subagent fan-out equivalent to Claude
Code's Agent tool. A task marked `independent:` in a kit's `TASKS.md` means it is safe to
run in any order relative to its siblings, not that it runs concurrently with them.

## Journal privacy and generated-doc provenance

The daily work journal reads session logs strictly read-only and writes its output only
under a gitignored `journal/` tree, so personal data never lands in git. Separately, every
generated artifact in this documentation center (`index.html`, `install.html`,
`safety.html`, `AIC-REPORT.md`, `aic-report.html`, `aic-report.json`) is produced entirely
by `bin/copilot_docs.py build` from the authored Markdown and current pricing/preference
data — never hand-edited, and always reproducible by re-running `build`.

## Stop if

Treat any of the following as a hard stop rather than proceeding:

- An installed agent or skill still shows the literal placeholder text `{{POLYTROPOS_ROOT}}` instead of a resolved path — reinstall before trusting it.
- `python3 bin/copilot_docs.py check` reports drift against current pricing — the pricing snapshot this center was built against is stale; rebuild before trusting its numbers.
- A configured pin in `prefs/copilot.json` resolves to a model id that is also in the configured excludes — this is a hard configuration error, not a resolvable preference.
- A verify command or skill instruction asks you to invoke a real harness CLI (`copilot`, `codex`, or `claude`) from inside a test or automated check rather than an interactive session — that is unsafe and out of scope for anything automated in this repository.
