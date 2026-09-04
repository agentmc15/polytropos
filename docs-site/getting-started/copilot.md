# Getting started on GitHub Copilot CLI

The Copilot side ships as a **bundle**: agent and skill files that get materialized into a
Copilot home. Copilot has no runtime variable pointing back at a plugin directory, so the
installer resolves the repository's absolute path into every copied file as it writes them.
That one detail explains most of what follows.

## Prerequisites

- The GitHub Copilot CLI, on your `PATH`.
- `git` and `python3` 3.8 or newer. Nothing to `pip install`.
- A clone of the repository — see [Getting started](index.md#start-with-a-checkout).

## Install

From the checkout:

```bash
python3 bin/harness_select.py detect
python3 bin/harness_select.py install --harness copilot
```

`detect` reports which harness CLIs are on your `PATH` and prints the right next step for
each. The install copies every bundled agent and skill file into your Copilot home,
rewriting the repository-root placeholder to this checkout's absolute path along the way.
The default home is `~/.copilot`; override it with `--copilot-home <dir>`. Add `--dry-run`
first to see every destination path without writing a byte.

If you would rather have the configuration checked into a project than materialized into a
personal home, a repo can adopt the bundle directly by copying `copilot/.github/` into
itself.

**Precedence gotcha:** an agent under `~/.copilot/agents/` overrides a same-named agent
defined at the repo level, so a stale installed copy silently shadows an updated one until
you reinstall.

## Where you stand matters

This is the step people miss, so it gets its own section.

**Installing the bundle does not put `bin/` on your `PATH`, and it does not give your shell
access to this repository.** What the installer wrote into your Copilot home is *agent and
skill text* with the repo's absolute path baked into it. That path is for the model to
shell out with during a session. It does nothing for you at a terminal.

So the two conventions you will see in this manual are both correct, in different frames:

- Inside a Copilot skill or agent, engine commands carry the resolved repository root,
  because the model may be working in any project and needs an absolute path.
- Everywhere else in this manual, engine commands are written bare —
  `python3 bin/copilot_pricing.py …` — and **that form assumes your working directory is a
  polytropos checkout.**

If you installed the bundle and never cloned the repository, or you cloned it and are now
sitting in some other project, the bare form will not run. Either `cd` to the checkout, or
spell the path out:

```bash
python3 /path/to/polytropos/bin/copilot_pricing.py est <PROFILE> <MODEL_OR_TIER>
```

## Your first invocation

Two surfaces, and they are not interchangeable. An **agent** is an isolated persona you
switch into, and it can carry its own model pin:

```bash
copilot --agent route --prompt "add input validation to the signup handler"
```

or pick `route` from the `/agent` picker inside a session. A **skill** steers the session
you are already in — type its name in a prompt, or let Copilot load one when your wording
matches its description closely enough. A skill carries no model pin, so it runs on
whatever model the session already has selected.

Success looks like a tier classification (`cheap` / `mid` / `strong` / `frontier`), a
compact table of two or three candidates with their cost in both dollars and AI Credits and
a one-line rationale each, the recommendation bolded, and then the single command to act on
it.

## Next

- [Copilot CLI skills](../skills/copilot/index.md) — the full roster, plus the session
  commands for reloading and inspecting installed skills.
- [budget](../skills/copilot/budget.md) — the one to know when credits are tight.
- [Billing modes](../concepts/billing-modes.md) — why every Copilot recommendation carries
  a credit figure beside the dollar one.
- [Deep dive: Copilot harness](../deep-dives/copilot-harness.md) — install mechanics, the
  five ways to act on a model recommendation, and how AI Credits are accounted.
