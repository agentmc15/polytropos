# The P0 spec review — PLAN.md against TASKS.md, before the first dispatch

`kit_contract.py analyze` reads a kit mechanically and judges nothing. This review is the
judging half. One fresh-context reviewer reads the spec against the tasks once, and you, the
orchestrator, adjudicate what it returns before anything is dispatched. It is a phase review
with the phase token `P0`, recorded in the existing `reviewer:` family. It is not a roster
role, so it writes no `agent:` line and no `outcome:` line.

## When it runs

- Once per kit, after `graph`, `roster` and `analyze` (SKILL.md, "The loop"), and before step 1
  of the first task.
- Only when NOTES.md carries no `reviewer: P0` line yet. A resumed kit that has one is not
  re-reviewed; that line is the review of record.
- Never when `roster` reported `workflow=direct`, because that kit opted out of independent
  review. Dispatch nothing. Write one NOTES.md prose line saying the P0 spec review was skipped
  because the kit declared `direct`, then go on to the first task.
- Not after `analyze` exited 3 and you stopped. A stopped run dispatches nothing, and that
  includes this review.

## Who runs it

The kit's `<slug>-reviewer` agent runs it: the phase reviewer, model opus, read-only tools
(`tools: Bash, Read, Grep, Glob`). Dispatch it with the Agent tool and `model: opus`. When the
kit has no reviewer agent, use the Agent tool directly on `model: opus` with the same prompt,
and say so in one NOTES.md prose line. That fallback is read-only only because the prompt says
so; no tools pin holds it.

## The prompt — pass it verbatim

Replace `<slug>` with the kit slug. Replace `<ledger>` with the absolute path of this skill's
`references/ledger.md`: resolve `${CLAUDE_PLUGIN_ROOT}/skills/execute/references/ledger.md`,
falling back to the `ledger.md` beside this file. Change nothing else. Below the prompt, paste
the full text output of the `analyze` run you just made, unedited.

```text
You are the P0 spec review of the kit in .claude/kits/<slug>/. No task has been dispatched
yet. Read and report only: change no file, run no verify command, and run no claude, codex,
copilot or agent CLI.

Read from disk:
1. PLAN.md: its Goal and "done" list, and its Constraints / out-of-scope section.
2. GUARDRAILS.md, when it exists: the kit's fences.
3. TASKS.md: every task's acceptance and its verify block. Read a task's brief only as far as
   checking those needs.
4. The analyze output pasted below this prompt. It comes from kit_contract.py analyze, which
   ran nothing and judged nothing. It lists paths a brief or a verify names that do not exist,
   commands not on PATH, and verify blocks the drivers cannot read.

Return ONLY findings of these three sorts:
A. Acceptance clauses that cannot all hold. This covers clauses within one task, a task
   against a fence (GUARDRAILS.md or PLAN.md's Constraints), and a verify against its own
   acceptance: a verify that passes before the work is done, cannot fail, or checks something
   other than what the acceptance requires.
B. A "done" item in PLAN.md that no task's acceptance covers.
C. An analyze warning you judge a real defect: a path, script or command that will still be
   missing when that task's verify runs, because no task at or before it creates it and the
   brief names no place for it. A file some task creates, a git ref, a pattern or any other
   value is not a defect. Leave those out.

For each finding write one block:
  F<n> task=<task id, or - for the kit as a whole> kind=<kind>
  at: <file:line>[, <file:line> for the other side of a conflict]
  claim: <one sentence: what cannot hold, or what is uncovered or missing>
  fix: <the smallest TASKS.md or PLAN.md edit that removes it, or "needs the architect">

<kind> is exactly one of the sanctioned defect kinds defined in <ledger>, under "Architect
brief defects". Two clauses that cannot both hold are contradictory-acceptance. If no
sanctioned kind fits, say so in the claim. Never coin a new kind.

Count findings as distinct claims. Write one block per defect: never two defects bundled into
one block, never one defect split across two. No style remarks, no design opinions, and no
suggestions beyond a finding's fix. If nothing qualifies, reply exactly: no findings
```

## Adjudication

Check each finding against the kit files. PLAN.md, TASKS.md and GUARDRAILS.md are kit state, so
read them directly. Send any question about the source tree to a scout, per the lean-driver
rule. A finding is **confirmed** only when it produces a TASKS.md or PLAN.md edit or a
stop-and-report. A finding you acknowledge but change nothing for is not confirmed. When you
are unsure, it is not confirmed. Adjudicate once and never revisit it.

For each confirmed finding:

- **Fix TASKS.md when the fix is unambiguous**, or PLAN.md for a kit-level defect. Examples are
  a stale path, a misnamed script or test, a verify that checks the wrong file, and a brief
  that never says it creates the file its verify runs. The edit must leave every task's scope
  and acceptance as the architect meant them. Note the edit in one NOTES.md prose line.
- **Otherwise, stop and report to the user before any dispatch.** This covers two clauses that
  cannot both hold, a "done" item no task covers, and anything that needs a choice between
  readings. Changing a task's scope or acceptance is the architect's call (SKILL.md, "What
  binds, what adapts").

## Recording

Append these lines to NOTES.md before any dispatch, so before any `outcome:` line exists for
the run. The grammar is in `references/ledger.md`:

    reviewer: P0 model=opus findings=<n> confirmed=<n> result=<accepted|revised|blocked>
    defect: <task-id> kind=<kind> when=pre-run

- `findings` is the number of blocks the review returned, counted as it presented them.
  `confirmed` is how many you adjudicated as real. A reply of "no findings" is `findings=0
  confirmed=0`, and the line is still written, so a resumed kit is not re-reviewed.
- `result` is the fate of the review itself, as on every `reviewer:` line. It is `accepted`
  when the verdict stood, `revised` when you materially overturned it, and `blocked` when it
  could not be adjudicated. A stop-and-report stops the kit, not the review, so a confirmed
  contradiction that stops the run is still `result=accepted`.
- Write one `defect:` line per confirmed defect, with the task token `-` for a kit-level one.
  The scorecard keeps the first line per task and kind, so one defect never counts twice.
- Backtick `reviewer:` and `defect:` whenever you quote them in NOTES.md prose. A line that
  merely starts with one parses as real data.

## `analyze`'s findings as ledger lines

`analyze` reports four kinds of finding. The review may raise one as a sort-C finding, or you
may meet one yourself: exit 3 is a `verify-unparseable` that you fix or stop on before the
review. Either way, a confirmed one is recorded as follows:

- A confirmed `verify-missing-path`, `verify-missing-executable` or `verify-unparseable` is `defect: <task-id> kind=unrunnable-verify when=pre-run`.
- A confirmed `brief-missing-path` is `defect: <task-id> kind=unspecified-path when=pre-run`.

An exit-3 finding is confirmed whether you fixed TASKS.md or stopped, since it produced an edit
or a stop; log it even when the fix was easy. It is not counted in the review's `findings=`,
because the review did not raise it. A warning the review raised as sort C is counted there.

Only the interactive loop adjudicates `analyze`'s warnings. The headless drivers and
`workflow: direct` kits print them, and nothing judges them.
