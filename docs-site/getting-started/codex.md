# Getting started on OpenAI Codex CLI

Codex loads polytropos as a **repo-local plugin**: it reads the skills out of the checkout
you have open, rather than from a copied install. There is nothing to materialize for the
core roster, which makes this the shortest install of the three — and the one where the
checkout is not optional.

## Prerequisites

- Codex desktop, CLI, or the IDE integration.
- `git` and `python3` 3.8 or newer. Nothing to `pip install`.
- A clone of the repository, opened in Codex — see
  [Getting started](index.md#start-with-a-checkout).

## Install

1. Open this repository in Codex and restart Codex so it discovers the repo marketplace at
   `.agents/plugins/marketplace.json`.
2. Open `/plugins`, find **Polytropos Local**, and install and enable **Polytropos**.
3. Open `/skills` and confirm the skills appear.

Agents are a separate, optional surface — installing the plugin does not install them.
Preview first; the preview is byte-read-only:

```bash
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components plugin,agents --agent-scope project --dry-run
python3 bin/harness_select.py install --harness codex --repo-root . --codex-home <codex-home> --components plugin,agents --agent-scope project
```

Project-scoped agents land in this checkout's `.codex/agents/`; `--agent-scope user` puts
them under the Codex home you supply instead. Start a new task after changing agents.

If a skill does not show up, `$doctor` diagnoses the install read-only before you change
anything — it prints one line per component with its state and the reason, and never
repairs. See [doctor](../skills/codex/doctor.md).

## Where you stand matters

Codex reads the plugin from the checkout, so the *skills* always know where the repository
is: each one derives `POLYTROPOS_ROOT` from its own file location, or — for a copied
install — from the value the installer resolved, and refuses to run against a guessed path
or an unresolved placeholder.

**Your shell gets none of that.** Enabling the plugin does not put `bin/` on your `PATH`.
The bare form used throughout this manual —

```bash
python3 bin/codex_pricing.py models --profile <PROFILE>
```

— **assumes your working directory is a polytropos checkout.** From another directory,
either `cd` there or spell the path out:
`python3 /path/to/polytropos/bin/codex_pricing.py models --profile <PROFILE>`. You will
also see Codex skill text and the `doctor` example write commands with an explicit
`"$POLYTROPOS_ROOT/bin/…"` prefix; that is the same idea from the model's side, where the
working directory is whatever project it is helping with.

## Your first invocation

Note the sigil: `$route` is the canonical form, **not** a bare `/route`.

```
$route add input validation to the signup handler
```

You can also just describe what you want and let Codex match your request against the skill
descriptions.

Success looks like a tier recommendation with a live estimate, framed the way you actually
pay: under a ChatGPT plan the lead figure is a burn index, because plan runs are
usage-limited rather than token-billed, and any dollar figure shown is a labeled
API-equivalent proxy — never a bill. Under an API key, the token-metered dollars are real
and authoritative. This roster deliberately shows no model ids: they are best-effort for a
preview generation, so the skill re-derives them from data instead of naming one from
memory.

## Next

- [Codex CLI skills](../skills/codex/index.md) — the full roster, the `$name` invocation
  form, and the optional agent surface.
- [Billing modes](../concepts/billing-modes.md) — burn versus dollars, and why the
  distinction is not cosmetic.
- [Deep dive: Codex harness](../deep-dives/codex-harness.md) — what loads where, the full
  install and refresh command set, and the ownership rules that keep your edits.
