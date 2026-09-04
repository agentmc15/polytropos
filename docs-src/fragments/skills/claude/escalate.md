### What it does

Runs one task on the cheapest model you'd actually trust for it, behind a check that can
fail — and only calls in Fable 5 when that check actually does. The orchestrator itself
never changes its own model; it dispatches attempts as subagents and grades each one with
its own fresh read, so Fable time is spent on genuine difficulty rather than routine work.

### When to reach for it

- One task, with a machine-checkable outcome — a test, a build, a lint, a curl-and-grep.
- You want "try it cheap, escalate automatically" without babysitting each attempt.
- Several tasks are stacked but each is still checkable individually.
- **Not** for open-ended work with no checkable outcome — say so instead of faking a
  verify, and escalate on a subagent reporting blocked rather than on a green check.

### Worked example

Pin the verify command first, then dispatch: a Sonnet subagent attempts the task, the
orchestrator runs the verify command itself — never trusting the subagent's own claim —
and on failure retries once on the same model with that failure output attached. A second
failure escalates: a Fable 5 subagent gets only the task, the verify command, and both
attempts' failure evidence, never a blank re-attempt. The orchestrator re-verifies Fable's
result the same way, at every step, and relays a plain answer either way.

### Failure modes & fallbacks

- **No checkable outcome exists.** Say so plainly — automatic escalation can't trigger
  reliably on a vibe — and fall back to an adversarial read instead of a faked verify.
- **Fable refuses** (`stop_reason: "refusal"` on cyber/bio-adjacent classifiers). Fall back
  to an Opus subagent at high effort and say why, rather than retrying Fable into success.
- **Fable itself fails.** Stop and report what each tier tried and the final check
  output — never climb effort past `xhigh` chasing a pass.

### Cost & safety

In subscription mode the marginal cost of the Fable hop is rate-limit burn, not money; in
api mode Fable only ever runs on the fraction of tasks the cheaper tier failed, so report
roughly what fraction escalated. This is the per-task sibling of [execute](execute.md)'s
blocked-task valve — for more than one task, a kit beats calling this skill in a loop.

### Related

- [architect](architect.md) — builds the kit that replaces looping this skill over many
  tasks.
- [fable-check](fable-check.md) — whether Fable is worth it at all, before this skill ever
  dispatches it.
- [execute](execute.md) — the multi-task orchestrator this skill's ladder mirrors per task.
