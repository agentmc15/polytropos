# polytropos

> *aesop tells the fables; polytropos finds the way.*

`CLAUDE CODE` · `GITHUB COPILOT CLI` · `CODEX CLI`

**Policy-guided routing** · **evidence-gated recovery** · **maintained documentation**

Polytropos is a cross-harness routing and workflow kit for coding agents. It helps you select an appropriate model before an expensive task, preserve a clear plan, and use independent verification with recovery based on evidence. Start in the CLI you already use.

![Polytropos compass with colorful paths: plan clearly, route wisely, verify independently.](docs/assets/readme/hero.svg)

## Start here

Choose one harness. Install paths and model rosters are intentionally separate; each has its own configuration and pricing data.

| Harness | Install | First useful action |
|---|---|---|
| **Claude Code** | `/plugin marketplace add /path/to/polytropos`<br>`/plugin install polytropos@polytropos-local`<br>CLI: `claude plugin marketplace add /path/to/polytropos`<br>`claude plugin install polytropos@polytropos-local` | Run `/polytropos:route <task>` before a substantial task. |
| **GitHub Copilot CLI** | `python3 bin/harness_select.py detect`<br>`python3 bin/harness_select.py install --harness copilot` | In Copilot, choose `/agent` → `route`, or run `copilot --agent route --prompt "<task>"`. |
| **Codex CLI** | `codex plugin marketplace add /path/to/polytropos`<br>`codex plugin add polytropos@polytropos-local` | Open `/skills` and invoke `$route <task>`; do not rely on a bare `/route` alias. |

Claude Code can also use a one-off checkout with `claude --plugin-dir /path/to/polytropos`. Copilot’s installer refreshes only its unchanged managed files and preserves conflicting personal edits; use `--dry-run` to inspect destinations first. Codex packages are cached, so start a new task after installing. For Codex package preparation and optional project roles, use the [Codex harness guide](docs/CODEX-HARNESS.md).

Once installed, discover the workflows in your host: Claude uses `/polytropos:*` commands; Copilot uses `/skills reload`, `/skills list`, and `/agent` (a skill name is not a native slash command); Codex uses `/skills` and `$skill` invocations. Claude’s `/polytropos:setup` manages its own status line; Codex’s `$setup` configures the native Codex status line, while `$usage` reads local activity. The [Copilot installation guide](copilot-docs/INSTALL.md) and [Codex skill guide](docs/CODEX-HARNESS.md#skills-and-legacy-copies) explain the different discovery and setup paths.

## The workflow in one screen

![The Polytropos workflow: route, plan, execute, independently verify, and recover only from recorded evidence.](docs/assets/readme/workflow.svg)

Routine work can go straight from routing to a suitable worker. Complex work gets a planning pass; failed verification carries evidence into targeted recovery and another check. Routing is advice and a policy boundary, not a claim that every host dispatch is observed. Each harness records what it can know, keeps direct user-selected runs outside the policy boundary, and leaves unverified runtime facts marked as unknown.

## What you get

- A task-first router that compares suitable candidates and returns the next command.
- A plan → execute → independently verify loop for work that warrants it.
- Escalation that carries failure evidence instead of routinely starting at the most capable model.
- Local usage, freshness, graph-grounding, assessment, and benchmark-planning tools, with capability differences documented per harness.

The detailed mechanics, limits, and examples live in the [documentation site](https://agentmc15.github.io/polytropos/), [architecture guide](docs/HOW-IT-WORKS.md), and [complete guide & cookbook](docs/GUIDE.md). For harness-specific behavior, see [Claude skills](skills/), [Copilot CLI](docs/COPILOT-HARNESS.md), and [Codex CLI](docs/CODEX-HARNESS.md).

Polytropos also has a [Cursor headless harness](docs/CURSOR-HARNESS.md). Its adapter and bundle are separate from the three quick starts above, and its usage remains unpriced where no rates are known.

## Current models: public releases vs. configured rosters

This is a deliberately compact **availability snapshot as of 2026-09-24**, not a pricing table and not a promise of picker availability. Public provider catalogs change independently of a local harness. Polytropos does **not** automatically add, route, or expose a newly announced model; it must be deliberately verified and configured in that harness’s canonical pricing/roster file.

| Provider surface | Public release/catalog snapshot | What Polytropos currently configures |
|---|---|---|
| [Anthropic models](https://platform.claude.com/docs/en/models/overview) | Fable 5.1; Opus 5.5; Sonnet 5; Haiku 4.5 | Claude data snapshot: **2026-09-21** — Fable 5.1 and Fable 5, Opus 5 (plus historical 4.7/4.8), Sonnet 5/4.6, Haiku 4.5. |
| [OpenAI models](https://developers.openai.com/api/docs/models) | GPT-6 Astra, Sol, Luna | Codex data snapshot: **2026-09-05** — `gpt-6-astra`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, legacy entries, and `codex-auto-review`. |
| [GitHub Copilot models & pricing](https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing) | New GPT-6 family; Fable 5.1; Opus 5.5; Gemini 3.8 Flash; MAI-Code-1.1-Flash; Grok 4.7; Kimi K3; and other GitHub-listed models | Copilot data snapshot: **2026-09-21** — a separately curated roster spanning configured Claude, GPT, Gemini, Kimi, MAI, and Grok entries. Every rate is from GitHub’s page on that date; nine newly added entries are picker-unconfirmed, and five that GitHub no longer lists are kept and marked delisted. |

In GitHub’s current catalog, the following names are **not in this repo’s Copilot roster**: GPT-6 Sol and Luna, and Claude Opus 5.5. None of the three was on the 2026-09-21 page the roster was captured from. This comparison is about documentation coverage, not permission to dispatch them.

The canonical files remain [Claude `data/pricing.json`](data/pricing.json), [Codex `data/pricing.codex.json`](data/pricing.codex.json), and [Copilot `data/pricing.copilot.json`](data/pricing.copilot.json). This comparison changes none of them: no prices are inferred from it, and a provider’s public listing is not evidence that a model is installed, selectable, or policy-routable. In particular, check Copilot’s `/model` picker and each file’s notes before treating a listed name as available.

## Important security boundaries

> **Read this before unattended use.** On macOS, kit verification commands run inside an OS boundary (`bin/exec_policy.py`, `sandbox-exec`): writes are confined to the workspace, network access is denied, and credential stores are unreadable. This is the default and it refuses rather than silently downgrading.
>
> **Linux and Windows do not yet have a confinement backend.** Verification there requires the explicit `--exec-mode trusted-host`, which enforces nothing. Benchmark candidate and judge dispatch are not yet confined on any platform. Read [SECURITY.md](SECURITY.md) for the enforced scope, exclusions, and operating guidance.

The Codex repo-bench port is planning-only and structurally refuses live candidate and judge dispatch. A ChatGPT-plan dollar figure is an API-equivalent proxy, not an actual bill or a spend ceiling. The Copilot and Claude tools likewise label the limits and provenance of their own estimates—do not combine their pricing surfaces.

## Keep going

- [Manual documentation site](https://agentmc15.github.io/polytropos/) — maintained, cross-harness reference.
- [Full reference](docs/REFERENCE.md) — every model, role, skill, engine and harness on one long page.
- [How it works](docs/HOW-IT-WORKS.md) — architecture and policy rationale.
- [Guide & cookbook](docs/GUIDE.md) — skill reference and worked examples.
- [Copilot documentation center](copilot-docs/README.md) — task-oriented Copilot material.
- [Release support matrix](docs/RELEASE.md) — verified versus unknown capability status.
- [Update skill](skills/update/SKILL.md) — read-only freshness check before a refresh.

Polytropos is named for the “many-wayed” Odysseus: use the smallest capable path, keep the evidence, and make the exceptional path explicit.
