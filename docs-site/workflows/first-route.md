# Route one task

**Goal:** before running something non-trivial, see which tier it needs and what it will
cost — then act on that in one command.

Routing spends nothing on its own. It reads a task description, classifies it, prices two
or three candidates from the harness's pricing data at run time, and hands you a decision.

## Step 1 — Ask

**On Claude Code:**

```
/polytropos:route add retry-with-backoff to the webhook publisher
```

Prefix the description with `--api` or `--sub` to force the billing framing when the
default guess is wrong for this particular question — see
[billing modes](../concepts/billing-modes.md).

**On Copilot CLI:**

```bash
copilot --agent route --prompt "add retry-with-backoff to the webhook publisher"
```

or pick `route` from the `/agent` picker inside a session.

**On Codex CLI:**

```
$route add retry-with-backoff to the webhook publisher
```

Note the sigil — `$route`, not `/route`.

## Step 2 — Read the table

You get candidates with an estimated cost and a one-line rationale each, recommendation in
bold. The estimate's *framing* is the part to read carefully: real dollars under
pay-per-token billing, an explicitly labeled API-equivalent figure under a plan. Copilot
shows credits beside dollars; Codex leads with a burn index when you are signed in with a
ChatGPT plan, because plan runs are usage-limited rather than token-billed.

If the recommendation surprises you low, that is the point — most tasks do not need the
model you happen to be sitting on.

## Step 3 — Act

There is always exactly one next command, and the skill prints it.

- **Dispatch it.** Delegated work can run on a different model than your session, so the
  router can simply run the task on the recommended model with a self-contained brief. It
  will tell you the subagent does not share your conversation; that is why the brief is
  written out rather than assumed.
- **Switch your session.** The router prints the exact switch command for you to paste.
  It cannot switch for you — see [the one constraint](../concepts/the-one-constraint.md).
- **Escalate to planning.** If the task is big — a codebase review, a migration, anything
  with an execution phase — the default offer is architecting instead of a plain frontier
  dispatch. Follow [run a kit](run-a-kit.md) from there.
- **Building an app?** Then the answer is not a session change at all: you get the model
  string and the API parameters to paste into your code, because the question was an
  `api`-mode question all along.

## Getting numbers without a session

The routers are wrappers over engines you can run yourself from a checkout:

```bash
python3 bin/copilot_pricing.py est <PROFILE> <MODEL_OR_TIER>
python3 bin/codex_pricing.py models --profile <PROFILE>
```

## Boundaries

- Routing **estimates what a task is about to cost**. It is not a spend report — that is
  [measure the savings](measure-the-savings.md).
- A recommendation is only as good as the description you give it. "Fix the bug" routes
  badly; two sentences of scope routes well.
- On Codex, no model id appears on the page by design — the roster is best-effort for a
  preview generation, so the skill re-derives ids from data instead of naming one from
  memory.

## Related

- [route on Claude Code](../skills/claude/route.md),
  [on Copilot](../skills/copilot/route.md), [on Codex](../skills/codex/route.md).
- [escalate](../skills/claude/escalate.md) — run it cheap behind a verify gate and climb
  only on failure, when you would rather not decide up front.
- [fable-check](../skills/claude/fable-check.md) — the deeper go/no-go when the frontier
  tier is specifically the question.
