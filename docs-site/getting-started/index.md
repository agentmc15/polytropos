# Getting started

polytropos is one repository that installs into three different agentic CLIs. The routing
judgment is shared; the install mechanics are not, and they are not interchangeable. Pick
the harness you actually work in and follow that page end to end.

- [Claude Code](claude.md) — the plugin's native home, installed from a local marketplace.
- [GitHub Copilot CLI](copilot.md) — a bundle of agents and skills materialized into your
  Copilot home.
- [OpenAI Codex CLI](codex.md) — a repo-local plugin that Codex loads from the checkout
  itself.

## Start with a checkout

All three paths begin with a clone, and one of them never leaves it.

```bash
git clone https://github.com/agentmc15/polytropos.git
cd polytropos
python3 -m unittest discover -s tests
```

You need `git`, `python3` 3.8 or newer, and at least one of the three CLIs. There is
nothing to `pip install` and nothing to compile — the Python here is stdlib-only, so this
step just proves your checkout runs. It should end in `OK`, with a couple of skips that
depend on local state. Any failure or error means your checkout is not clean; re-clone
and try again before going further.

One placement rule: keep the checkout **outside any cloud-synced folder** — not under a
Dropbox, Drive, or OneDrive tree. The gitignored personal stores this repo writes would
otherwise sync wholesale, and the test suite fails when it detects a synced location. See
the [privacy deep dive](../deep-dives/privacy.md) for what those stores hold.

## Where you stand matters

Read this once now and you will not be confused later. Throughout this manual, engine
commands appear in their bare form:

```bash
python3 bin/<engine>.py …
```

**That form assumes your shell's working directory is a polytropos checkout.** Installing
a harness bundle copies configuration into that harness's home directory — it does not add
`bin/` to your `PATH`, and it does not make these commands runnable from an arbitrary
project folder. From anywhere else, spell the path out:

```bash
python3 /path/to/polytropos/bin/<engine>.py …
```

Inside a session, the skills resolve the repo root for themselves — through
`${CLAUDE_PLUGIN_ROOT}` on Claude Code, and through an installer-resolved
`POLYTROPOS_ROOT` on the Copilot and Codex bundles. That is a separate mechanism that
serves the model, not your terminal. If you install a bundle and never clone the repo, the
skills still work and the shell examples in this manual do not.

## What each install actually writes

| Harness | What lands where | Diagnose with |
|---|---|---|
| Claude Code | A plugin registered from the local marketplace in your checkout | `/polytropos:update` |
| Copilot CLI | Agent and skill files copied into a Copilot home, with the repo path resolved into them | `python3 bin/harness_select.py detect` |
| Codex CLI | A plugin loaded live from the checkout; agents are a separate, optional copy | `$doctor` |

Nothing here writes outside its own harness home, and every installer has a `--dry-run`
or read-only preview that shows the plan before a byte moves.

## Then what

- [Route your first task](../workflows/first-route.md) — the five-minute version of what
  this tool is for.
- [Concepts](../concepts/index.md) — the four ideas the whole design rests on. Read
  [billing modes](../concepts/billing-modes.md) first if you are on a subscription.
- [Skills reference](../skills/index.md) — every skill on every harness, generated from
  the files the models actually read.
