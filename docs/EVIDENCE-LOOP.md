# Evidence-Loop: Measuring Governance, Promotion, and Escalation Quality

The evidence-loop kit (`.claude/kits/evidence-loop/`) closes three measurement gaps in how the repo governs itself. It introduces three analysis surfaces — **residency**, **promotion**, and **envelope** — to audit whether the scaffolding survives implementation, whether recurring lessons can become skills, and whether the escalation ladder holds against simpler alternatives. All three are measurement-only: they produce evidence for human decisions, never auto-route or auto-pin anything.

## The Three Surfaces

### Residency: Are Guardrails Still in the Context Window?

**What it measures.** Whether a kit's `GUARDRAILS.md` constraints are actually resident in the reconstructed context window after execution, and at what estimated token weight. This distinguishes two failure modes:

- **Never read:** The constraint file was never loaded into the context at all (a brief gap or an incomplete harness setup).
- **Read then evicted:** The constraint was loaded and then dropped during a compaction, and you lose visibility into what the rewrite rules were.

**How to use it.** Run:

```bash
python3 bin/context_weight.py constraints --kit .claude/kits/<kit-slug> [--session ID]
```

The verdict line is `resident: YES` (with the estimated token weight of the guardrail content currently in the reconstructed window) or `resident: NO`. A transcript with no read of the file at all gets neither — it gets an explicit "never loaded into context here" line, so "never read" is never silently reported as "evicted". A `NO` names *how* the eviction was established: a **confirmed** compaction (an `isCompactSummary` marker actually recorded in the transcript) or an **inferred** one (a weight drop large enough to imply a rewrite, with no marker present — the word "inferred" stays in the printed phrase precisely so it is never mistaken for a recorded fact). A `NO` also carries a note that the execute skill's re-read guarantee is anchored to phase starts, not to compaction, so a compaction landing mid-phase can legitimately show `NO`. **Claude-only:** Codex and Copilot surfaces cannot measure constraint residency today because those harnesses do not preserve full context accounting in their logs.

**Why it matters.** The governance-decay research cited by this kit observes that constraints are often the first content a rewrite drops — they are metadata to the model, not work output, so they rank low in any pruning algorithm. Measuring residency lets you audit whether your scaffolding survived a session, and re-assert it if it did not.

### Promotion: When Do Recurring Lessons Become Skills?

**What it measures.** Clusters `defect:` ledger lines across every kit in the repository, groups them by exact kind token, gates on recurrence (≥2 distinct kits), and drafts candidates for human review. This is the **first gate** of a two-gate promotion process:

- **Gate 1** (this tool): Does the lesson recur in at least 2 distinct kits?
- **Gate 2** (human): Is the lesson general enough, stable enough, and transferable enough to justify adding it as a skill or guardrail?

Run it with:

```bash
python3 bin/lessons_promote.py --print
```

Output is a **draft only** — it writes nothing to scaffolding, `skills/`, `GUARDRAILS.md`, agent files, or tracked files. Without `--print` it writes to the gitignored `journal/promotions/` directory with a date-stamped filename.

**What gets filtered.** The tool also reads `tasks/lessons.md` (a JSON-lines file, not prose, containing lessons learned across work) and reports those entries verbatim in an informational section, but does not try to cluster or promote them — they carry no kit attribution and cannot satisfy the recurrence gate. A human decides whether to promote them separately.

**Why it matters.** The skill-library literature shows that unvalidated promotion pollutes every future kit: a skill extracted from one task may not generalize, may not be stable across contexts, or may codify a transient workaround. Requiring recurrence before human review lets you distinguish signal from noise.

### Envelope: Does the Ladder Beat a Simpler Cascade?

**What it measures.** Prices the observed four-tier escalation ladder (cheap → mid → strong → frontier) against the best tuned two-model cascade (any model threshold X: use cheap unless it fails, then jump to X) for the same set of tasks. Both are modeled from historical ledger data and priced from `data/pricing.json` at run time.

**How to use it.** Run:

```bash
python3 bin/routing_scorecard.py --history --envelope
```

**The honest limitation (today).** This repo does not yet have enough outcome data to answer the envelope question. Specifically:

- **Zero blocked/escalated outcomes, so far:** The `failure=` field (which marks task class) is legal only on `blocked` or `escalated-pass` outcomes. Every outcome recorded in the repo's kits to date has been `pass` or `retry-pass` — so `failure=` has never once been legal to write, and no per-class analysis is possible. The report does **not** fall back to a whole-history total: with no class evidence it renders no table at all and prints its evidence base plus "Unanswerable from this repo's history today" instead (see **What the report prints when data is thin**, below). This is a running total, not a fixed fact — it grows every time a kit runs. Don't trust a number frozen in this doc; run the command above (or `bin/routing_scorecard.py --history --envelope` in `--json` mode) and read `tasks_with_outcome` / `outcomes_with_failure` from its own evidence-base section.
- **Session pricing is sparse, and for a specific reason.** Many kits' `NOTES.md` files *do* carry a `session:` line recording a session id — that part of the ledger is in decent shape. The gap is downstream of that: a session id only turns into a priced dollar figure if the underlying transcript can still be found on disk, and Claude Code transcripts live in session-scoped tmp storage that expires. So the id can outlive the transcript it points to — a kit can faithfully record `session:` and still contribute nothing priceable. The report's evidence base separates these two counts explicitly (kits with a `session:` line, vs. sessions that actually resolved to a transcript) precisely so a reader doesn't conflate "we're not recording session ids" (not the problem) with "we can't recover most of the transcripts we pointed at" (the actual problem). Run the command above for the live split.

**What the report prints when data is thin:** The envelope surface is **designed to degrade gracefully** when evidence is sparse. Rather than inventing a per-class table or claiming a cascade "saves" money, it prints its own evidence base — how many outcomes carry `failure=`, how many kits carry a `session:` line, and how many of the sessions behind those lines still resolve to a priced transcript — and explains why the question cannot be answered yet from those numbers. This is not a limitation to apologize for — it is the surface working as designed. The insight it gives is actionable: "the ladder hypothesis cannot be tested until the ledger accumulates blocked and escalated outcomes, and until more of the recorded `session:` lines resolve to transcripts before they expire."

**Why it matters.** The decision-theoretic research cited by this kit suggests that multi-stage ladders often underperform compared to a simple pairwise threshold. This repo has the structure to test that locally instead of assuming either way. The honest answer on today's data is: we don't have enough evidence yet, and here's what needs to accumulate.

## Reading the Envelope Report: Two Critical Rules

### Rule 1: The Envelope is Evidence for a Human Decision, Never an Auto-Change

The envelope report **never** feeds into routing logic, dispatch conditions, escalation thresholds, or budget controls. It is input to a human reviewing whether the four-tier ladder is the right strategy. The architecture explicitly gates any such change to a different kit that does not exist yet. Until then, envelope analysis stays pure observation.

### Rule 2: `tasks/lessons.md` is Live Routing Input — Promotion is Read-Only

The file `tasks/lessons.md` is actively read by `copilot/.github/skills/lessons-loop/SKILL.md` and `copilot/.github/agents/route.agent.md` at session start. `lessons_promote.py` opens it **strictly read-only** and never appends to it. A promoted lesson becomes live routing input only after a human edits the file — the promotion tool never does that side effect. This enforces the rule that analysis never becomes behavior.

## The Research Grounding

The three surfaces close loops identified in the repo's ongoing work. The kit names this work by description rather than by formal reference:

1. **Constraints decay under compaction.** Governance rules and scaffolding are often the first content a rewrite algorithm drops, because they are metadata rather than generated work. The **residency** surface measures whether constraints survive, so you can detect when a compaction has erased them and re-assert the rules. This observation comes from published research on prompt compaction and governance, cited here by description rather than by formal reference — this repo does not record the original sources.

2. **Experience does not automatically make a good skill.** A lesson learned in one kit may not generalize, may be context-specific, or may codify a temporary workaround. The **promotion** surface requires recurrence across at least two distinct kits before a human even sees a candidate, filtering out one-off learnings. This design principle is established in skill-development literature, again cited here by description rather than formal citation.

3. **A multi-stage ladder often fails to beat a tuned pairwise cascade.** The repo currently routes work through a four-tier escalation ladder: start cheap, escalate to mid on failure, then strong, then frontier. Research on decision-theoretic cascades suggests a simpler two-model threshold (jump to a specific tier on failure rather than climbing one step at a time) might outperform this walk. The **envelope** surface lets you test this hypothesis against your own ledger history rather than assume either way. Again, the research is cited by description here, not by formal reference.

If readers want the original sources for these claims, the honest answer is: this repo does not record them. The claims themselves are embedded in the kit's architecture and PLAN.md; the supporting scholarship exists elsewhere and may be found through literature search on compaction research, skill development, and decision-theoretic routing.

## Deeper Reading

- **Architecture & decision rationale:** `.claude/kits/evidence-loop/PLAN.md` — the full design, E1–E4 decisions, and the risks/tripwires section.
- **Kit guardrails and constraints:** `.claude/kits/evidence-loop/GUARDRAILS.md` — the fences that bind while this kit's tasks run.
- **How the execute skill re-asserts guardrails:** `skills/execute/SKILL.md` — the U1 implementation. Read its "phase starts guaranteed, compaction best-effort" section for what is actually promised: a GUARDRAILS.md re-read at **every phase start** is the guarantee; a re-read after a compaction is **best-effort only**, because the skill cannot detect compaction. Treat the post-compaction re-read as an opportunistic extra, never as coverage — `bin/context_weight.py`'s phase-anchor note exists to keep a `resident: NO` from being misread as a broken guarantee.
- **How context weight measures residency:** `bin/context_weight.py` — see the `constraints` subcommand, and the module docstring for the ladder of fidelity per harness (this is where the per-harness honesty ladder lives).
- **How promotion clusters defects:** `bin/lessons_promote.py` — exact-token clustering on `defect:` lines, gate 1 logic, and the read-only contract for `tasks/lessons.md`.
- **How the envelope analyzes the ladder:** `bin/routing_scorecard.py` — see the `--envelope` mode, the honest-degradation logic, and `envelope_call_cost`, which prices every tier through the same `cost_report.price` seam `session_cost.py` uses. This engine is **Claude-only** — it reads Claude kit ledgers and `data/pricing.json`, and has no per-harness fidelity ladder; that property belongs to `bin/context_weight.py` (previous bullet).
