#!/usr/bin/env python3
"""Routing-quality scorecard for an executed kit.

Turns a kit's ``TASKS.md`` (statuses + model pins) and its ``NOTES.md`` outcome
ledger into a routing-quality scorecard — the "did the cheap models actually hold
quality" companion to the dollar tools (``cost_report`` / ``session_cost``). It
answers: how many tasks passed verify first-try on their pinned model, how many
needed a retry or an escalation, which model each task really ran on, and what
share of cheap-model output survived independent review unchanged. Optionally it
folds in one session's transcript dollars vs an all-frontier counterfactual.

READ-ONLY. It never writes into a kit dir and never modifies NOTES.md; the ONLY
thing that writes anything is ``--demo``, and it writes solely into its own
``tempfile.TemporaryDirectory`` (cleaned up on exit). Quality parsing is TOLERANT:
a kit with no ``outcome:`` ledger lines (every kit executed before this one, or a
plain prose NOTES.md) degrades to status-only output with an explicit note — never
a crash, never an invented number, and a zero-denominator rate renders null / n/a,
never a fabricated 0%.

TASKS.md parsing and transcript pricing are REUSED read-only, never
re-implemented: ``copilot_execute.parse_tasks`` for the task table and the
``session_cost`` functions (which themselves reuse ``cost_report``) for the
transcript dollars + counterfactual. All three are loaded via the importlib
``_load`` pattern from ``bin/session_cost.py`` and are never edited.

The ``--live`` mode is a separate, quality-only view for mid-run re-routing: it reads
TASKS.md + the NOTES.md ledger so far and reports each tier's live first-try pass rate
plus any re-route recommendation. It is quality-only (it never loads pricing), it is
read-only (the orchestrator appends ``reroute:`` lines to NOTES.md; this script never
writes one), and its recommendations are UPGRADE-ONLY — exactly one tier step — and
never target frontier.

The ``--history`` mode aggregates every kit's ``TASKS.md`` + ``NOTES.md`` ledger under the
kits dir into a cross-kit per-tier track record (pinned tasks, outcomes, first-try +
escalation rates, and re-route tallies), folding in transcript dollars vs an all-frontier
counterfactual only for kits whose ``NOTES.md`` carries optional ``session:`` lines (the
aggregate is labeled ``partial`` otherwise); like ``--live`` it is read-only and — with no
``session:`` lines anywhere — loads no pricing at all. ``--kits-dir`` is REPEATABLE under
``--history``: with more than one dir (or any explicit ``label=path`` token) kit rows are
namespaced ``<label>/<kit>`` so two repos' same-named kits don't collide, tiers and re-route
tallies aggregate globally, and dollars ride the same single ``--projects-dir`` with the
degradation rules unchanged; with a lone plain dir the output is byte-identical.

The ``--by-task`` mode prices each recorded subagent's ``*.output`` transcript per task and
role from NOTES.md ``agent:`` lines, reports the main transcript as one un-split orchestrator
line, attributes a warm cluster's shared transcript to the cluster as a unit, and degrades to
n/a (whole-kit dollars unchanged) when no ``agent:`` lines exist. It requires ``--session`` and,
like every other mode, is read-only.

``--history --snapshot`` writes the history card as a dated JSON file into a gitignored
snapshot store, and ``--history --trend`` renders per-tier first-try rate over the stored
snapshots as a text table — a trend needs at least two snapshots, and with zero or one it
says so instead of fabricating. ``--trend`` also renders the T11 (PLAN D11) escalation-rate
alarm — a trailing per-kit baseline derived from the SAME stored snapshots (never a
hardcoded threshold; degrades to an honest insufficient-history line) — and when reached
via ``--snapshot --trend`` together, persists that verdict to
``<snapshot-dir>/alarm/state.json`` so ``bin/statusline.py`` can read it without ever
recomputing it; every other mode, and a bare ``--trend``, stays fully read-only.

The ``--envelope`` mode (U4, PLAN E3) rides ``--history``: it derives per-class (dispatch
tier x ``failure=`` class) task classes from the SAME multi-kit ledger scan and prices each
class's observed escalation-ladder walk against the best two-model cascade, both modeled
from ``pricing.json`` (never a real session's tokens — every dollar is labeled ``est.``). It
answers no question this repo's real history can support yet: with zero outcomes carrying
``failure=`` anywhere (that field is legal only on ``blocked``/``escalated-pass``
outcomes), the report names its evidence base and declines rather than rendering a
whole-history fallback number — see NOTES.md's "PLAN E3's premise is false" finding. It is
purely analytical: no dispatch, pin, escalation, or budget behavior anywhere reads its
output, and it writes nothing.

Usage:
  routing_scorecard.py <kit-slug|kit-dir> [--kits-dir DIR] [--session ID]
      [--projects-dir DIR] [--tasks-dir DIR ...] [--include PATH ...]
      [--no-subagents] [--vs MODEL_ID] [--json]
  routing_scorecard.py <kit-slug|kit-dir> --live [--kits-dir DIR] [--json]
      [--live-threshold F] [--live-min-sample N] [--live-max-auto N]
  routing_scorecard.py --history [--kits-dir DIR|LABEL=PATH ...] [--projects-dir DIR]
      [--no-subagents] [--vs MODEL_ID] [--json]
  routing_scorecard.py --history --snapshot [--snapshot-dir DIR] [--kits-dir DIR ...]
      [--projects-dir DIR] [--json]
  routing_scorecard.py --history --trend [--snapshot] [--snapshot-dir DIR]
      [--trend-alarm-sigma F] [--json]
  routing_scorecard.py --history --envelope [--kits-dir DIR] [--projects-dir DIR] [--json]
  routing_scorecard.py <kit-slug|kit-dir> --session ID --by-task [--kits-dir DIR]
      [--projects-dir DIR] [--tasks-dir DIR ...] [--vs MODEL_ID] [--json]
  routing_scorecard.py --demo [--live|--history|--by-task|--history --trend|--alarm|--envelope]
      [--json]
"""

import argparse
import contextlib
import importlib.util
import io
import json
import os
import re
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KITS_DIR = PLUGIN_ROOT / ".claude" / "kits"
SCHEMA_VERSION = 1

RESULTS = ("pass", "retry-pass", "escalated-pass", "blocked", "budget-stop")
REVIEWS = ("clean", "revised", "none")

# ``budget-stop`` (T9, graph-convergence) is a FIFTH result value, added here rather than
# left unrecognized because the drivers' `budget:` PLAN.md dial (a line family, like
# `autonomy:` -- never a task field; this file never parses that line itself, PLAN.md stays
# execute-owned) must write an in-grammar, honest ledger line when it stops a run cleanly at
# a declared cap. A budget-stop is deliberately NOT a verdict about the task: no dispatch
# happened, so it says nothing about whether the pinned tier could have done the work --
# unlike `pass`/`retry-pass`/`escalated-pass`/`blocked`, which all report on a completed
# verify attempt. Every place below that turns RESULTS into a per-tier or per-kit QUALITY
# signal (first-try rate, escalation rate) therefore excludes `budget-stop` explicitly, with
# a comment at each exclusion point -- counting it there would dilute the rate's denominator
# with an event carrying no pass/fail information at all. It still parses, still joins to its
# task by id, and still appears in `build_scorecard`'s per-task rows (never hidden), it is
# simply held out of the aggregates that measure whether a tier is doing the work.

# --- graph-convergence (T1/T2) — three OPTIONAL fields on the outcome: line, structural
# vocabulary (same species as RESULTS/REVIEWS). ``FAILURE_CLASSES`` is the entire vocabulary
# for ``failure=`` (PLAN D9) — never a price, price ratio, model id, or date. ``run=`` and
# ``parent=`` carry no closed vocabulary (a run id's shape is execute-owned per PLAN D8; a
# parent is a task id), so they need no constant here — only presence/self-parent is checked
# in ``parse_outcomes``. Absent means today's behavior: none of the three change what an
# outcome line without them parses to.
FAILURE_CLASSES = ("execution", "coherence", "verification")

# Structural vocabulary mapping the Agent-tool model alias to the pricing.json
# tier; every other alias equals its tier name. This is the sanctioned exception
# to the no-model-literals rule (it mirrors cost_report.EXPENSIVE_TIERS itself).
TASK_MODEL_TIERS = {"fable": "frontier"}

OUTCOME_RE = re.compile(r"^\s*(?:[-*]\s+)?outcome:\s+(\S+)\s+(.+)$")
PAIR_RE = re.compile(r"(\w+)=(\S+)")

MD_H2S = ("## Verdict", "## Task outcomes", "## Model mix", "## Review survival",
          "## Dollars")

# --- live re-route signal (Tier 2) — structural policy constants, NOT prices. Each
# encodes routing BEHAVIOR (a sample size, a pass-rate threshold, a per-run budget, a
# schema version, and the tier ladder) — never a price, price ratio, model id, or date;
# the same species as SCHEMA_VERSION above. All four knobs are CLI-tunable.
LIVE_SCHEMA_VERSION = 1
LIVE_TIER_ORDER = ("haiku", "sonnet", "opus", "frontier")  # cheap→expensive ladder; an
# upgrade moves exactly one rung right and never lands on ``frontier``.
LIVE_RATE_THRESHOLD = 0.5   # a tier is struggling when its live first-try rate is
                            # STRICTLY below this.
LIVE_MIN_SAMPLE = 3         # completed tasks of a tier before its rate is judged.
LIVE_MAX_AUTO_UPGRADES = 2  # budget guardrail: max ``mode=applied`` re-route events/run.
REROUTE_MODES = ("advisory", "applied")
REROUTE_RE = re.compile(r"^\s*(?:[-*]\s+)?reroute:\s+(\S+)\s+(.+)$")
AUTONOMY_RE = re.compile(r"^\s*autonomy:\s*(advisory|auto)\s*$", re.MULTILINE)

# --- cross-kit history (Tier 3) — the ONLY new constant is a schema version (same
# species as SCHEMA_VERSION / LIVE_SCHEMA_VERSION); the history is DESCRIPTIVE and judges
# nothing, so it needs no policy knobs. ``session:`` is an OPTIONAL, execute-owned NOTES.md
# line (precedent: ``outcome:`` / ``reroute:``) carrying one whitespace-free session id and
# nothing else; neither OUTCOME_RE nor REROUTE_RE can match it, so all prior consumers are
# unaffected and TASKS.md / parse_tasks are untouched.
# v2 (role-ledger D6/D7): the card gains one additive top-level key, ``roles`` (verifier /
# reviewer / escalation / architect quality aggregated by ``role_quality_stats``) —
# everything else in the card is byte-identical in meaning; ``TREND_SCHEMA_VERSION`` and the
# per-kit/live cards' schemas are untouched by this bump.
HISTORY_SCHEMA_VERSION = 2
SESSION_RE = re.compile(r"^\s*(?:[-*]\s+)?session:\s+(\S+)\s*$")
# Looser prefix to flag a line that INTENDS to be a session line (optional bullet + the
# ``session:`` key) but fails the full grammar (e.g. two tokens) — noted, never guessed at.
_SESSION_PREFIX_RE = re.compile(r"^\s*(?:[-*]\s+)?session:")

# --- per-task dollars (Tier 4) — the ONLY new constants are a schema version (same species
# as the other three) and the role vocabulary (same species as RESULTS / REVIEWS); the
# breakdown DESCRIBES and JUDGES nothing, so it needs no policy knobs and no prices. ``agent:``
# is a fourth OPTIONAL, execute-owned NOTES.md line (precedent: ``outcome:`` / ``reroute:`` /
# ``session:``) — a task id plus key=value pairs read with the existing PAIR_RE. None of the
# other three regexes can match it (the keys are disjoint), so every prior NOTES.md consumer is
# unaffected and TASKS.md / parse_tasks are untouched.
BYTASK_SCHEMA_VERSION = 1
AGENT_ROLES = ("implementer", "verifier", "escalation")
AGENT_RE = re.compile(r"^\s*(?:[-*]\s+)?agent:\s+(\S+)\s+(.+)$")

# Structural vocabulary (same species as RESULTS / REVIEWS) for the D1 role-ledger
# extension: optional `result=` on an `agent:` line, shared by verifier/escalation
# quality recording. Defined here, next to AGENT_ROLES, because it governs the same
# line family; it does NOT extend AGENT_ROLES itself (keep/skip criteria are unchanged).
AGENT_RESULTS = ("accepted", "revised", "blocked")

# --- role ledger (D1) — two NEW line families, structural grammars (same species as
# AGENT_RE et al.), disjoint by key (``reviewer:`` / ``defect:``) from all four existing
# families (``outcome:`` / ``reroute:`` / ``session:`` / ``agent:``). Per-phase reviewers are
# deliberately excluded from the ``agent:`` ledger (per-task dollars must never split a
# per-phase transcript per task — PLAN D1); architect brief defects are recorded by execute
# mid-run (PLAN D4) and are neither task- nor agent-scoped. A new line family is invisible to
# every pre-existing parser and vice versa — no ``AGENT_RE``/``OUTCOME_RE``/etc. edit needed.
REVIEWER_RE = re.compile(r"^\s*(?:[-*]\s+)?reviewer:\s+(\S+)\s+(.+)$")
DEFECT_RE = re.compile(r"^\s*(?:[-*]\s+)?defect:\s+(\S+)\s+(.+)$")

# --- cross-repo history + snapshot/trend (Tier 5) — the ONLY new constants are STRUCTURAL
# grammars (same species as the ledger regexes) and a schema version (same species as the
# other four); never a price, price ratio, model id, or pricing date. ``_LABEL_RE`` bounds an
# explicit ``label=path`` token's label to a filesystem-safe, separator-free shape so a repo's
# kits can be namespaced ``<label>/<kit>`` without collision when ``--kits-dir`` is repeated
# under ``--history``. A lone plain ``--kits-dir`` (or none) stays byte-identical: no
# namespacing. ``TREND_SCHEMA_VERSION`` / ``SNAPSHOT_FILENAME_RE`` / the date grammar /
# ``DEFAULT_SNAPSHOT_DIR`` back the snapshot store: filenames are ``<YYYY-MM-DD>.json`` under
# a NEW top-level gitignored dir (``trends/``), the ONE sanctioned real write in the script.
_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

TREND_SCHEMA_VERSION = 1
SNAPSHOT_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")
_SNAPSHOT_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DEFAULT_SNAPSHOT_DIR = PLUGIN_ROOT / "trends"

# --- escalation-rate alarm (T11, PLAN D11) — the ONE new constant is a z-score
# MULTIPLIER, the same species as LIVE_RATE_THRESHOLD's "structural policy, not a
# price" carve-out, but deliberately NOT a percentage: the acceptance criterion is "no
# hardcoded thresholds", so the trip VALUE itself (a percentage) is never written down
# here — build_escalation_alarm always DERIVES it from the trailing data's own
# mean/stdev at run time. ``TREND_ALARM_SIGMA_DEFAULT`` only fixes the textbook
# convention of "how many standard deviations above the mean counts as anomalous" (the
# same one sigma any stats primer reaches for first), and even that is CLI-tunable via
# ``--trend-alarm-sigma`` (mirrors ``--live-threshold`` for LIVE_RATE_THRESHOLD).
TREND_ALARM_SIGMA_DEFAULT = 1.0

# --- pairwise cascade envelope (U4, PLAN E3; corrected by this kit's own NOTES.md finding
# "PLAN E3's premise is false") — the ONE new constant is a ``pricing.json["task_profiles"]``
# KEY (never a price itself; it indexes into the pricing file at run time, same species as
# ``TASK_MODEL_TIERS``'s alias-to-tier mapping being the sanctioned model-literal exception).
# There is no per-task transcript at the (tier x failure-class) granularity U4 analyzes, so
# a per-call cost is MODELED from one fixed task-size profile rather than measured — chosen
# deliberately as a UNIFORM scaling factor: every tier's call is priced at the same profile,
# so the profile size changes only the absolute dollar magnitude, never which of the ladder
# or the cascade comes out cheaper. Every dollar figure U4 renders from it therefore carries
# an ``est.`` label (PLAN E4).
ENVELOPE_SCHEMA_VERSION = 1
ENVELOPE_TASK_PROFILE = "S"


def _load(name):
    """Load a sibling ``bin/<name>.py`` module read-only (the session_cost.py pattern)."""
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / f"{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ce = _load("copilot_execute")   # TASKS.md parser (read-only reuse)
sc = _load("session_cost")      # transcript dollars + counterfactual (read-only reuse)
cr = sc.cr                      # cost_report (already loaded by session_cost) — do not re-load


# --------------------------------------------------------------------------- demo data

DEMO_TASKS_MD = """# TASKS — fusion-demo (synthetic)

## Phase 1 — demo

### D1 — cheap first-try task
- status: done
- model: haiku

### D2 — sonnet clean task
- status: done
- model: sonnet

### D3 — sonnet revised task
- status: done
- model: sonnet

### D4 — sonnet retry task
- status: done
- model: sonnet

### D5 — escalated frontier task
- status: done
- model: fable

### D6 — blocked task
- status: blocked
- model: sonnet
"""

DEMO_NOTES_MD = """# NOTES — fusion-demo (synthetic)

Prose describing the synthetic run this scorecard demo consumes, followed by the
machine-readable outcome ledger. One line is deliberately malformed to exercise the
tolerant parser.

## Outcome ledger
outcome: D1 model=haiku attempts=1 result=pass review=clean
outcome: D2 model=sonnet attempts=1 result=pass review=clean
outcome: D3 model=sonnet attempts=1 result=pass review=revised
outcome: D4 model=sonnet attempts=2 result=retry-pass review=clean
outcome: D5 model=fable attempts=3 result=escalated-pass review=clean
outcome: D6 model=sonnet attempts=2 result=blocked review=none
outcome: D9 result=???
"""

# Pinned token VOLUMES (counts, not prices) keyed by tier. The demo transcript's
# model IDS are COMPUTED from data/pricing.json at run time (never hardcoded).
DEMO_VOLUMES = {
    "haiku": (200000, 8000),
    "sonnet": (900000, 45000),
    "opus": (150000, 12000),
    "frontier": (60000, 9000),
}

# Synthetic MID-RUN kit for ``--demo --live``: nine tasks, four finished (the sonnet
# tier struggling at 1/3 first-try) and five pending. All ids/values are synthetic; the
# only model tokens are tier names plus the ``fable`` alias.
DEMO_LIVE_TASKS_MD = """# TASKS — fusion-live-demo (synthetic, mid-run)

## Phase 1 — live demo

### L1 — cheap first-try task
- status: done
- model: haiku

### L2 — sonnet clean task
- status: done
- model: sonnet

### L3 — sonnet retry task
- status: done
- model: sonnet

### L4 — sonnet blocked task
- status: blocked
- model: sonnet

### L5 — pending sonnet task
- status: pending
- model: sonnet

### L6 — pending sonnet task
- status: pending
- model: sonnet

### L7 — pending opus task
- status: pending
- model: opus

### L8 — pending haiku task
- status: pending
- model: haiku

### L9 — pending fable task
- status: pending
- model: fable
"""

DEMO_LIVE_NOTES_MD = """# NOTES — fusion-live-demo (synthetic, mid-run)

Prose describing the synthetic mid-run this live demo consumes, followed by the
machine-readable ledger so far. The reroute line below was logged earlier in the run as
an advisory recommendation and consumes no budget.

## Outcome ledger
outcome: L1 model=haiku attempts=1 result=pass review=clean
outcome: L2 model=sonnet attempts=1 result=pass review=clean
outcome: L3 model=sonnet attempts=2 result=retry-pass review=revised
outcome: L4 model=sonnet attempts=2 result=blocked review=none
reroute: sonnet to=opus mode=advisory tasks=L5,L6 rate=1/3
"""


# Synthetic multi-kit fixtures for ``--demo --history`` (PLAN D9). All ids/values are
# synthetic; the only model tokens are tier names plus the ``fable`` alias. hist-alpha
# exercises the escalated→dispatch-tier attribution (A5 ran on the Fable fixer but its
# failure counts against SONNET, its dispatch tier) and carries a ``session:`` line;
# hist-beta carries an advisory ``reroute:`` and NO session line (dollars n/a); hist-gamma
# is a pre-ledger kit with NO NOTES.md at all (contributes pins only).
DEMO_HIST_ALPHA_TASKS_MD = """# TASKS — hist-alpha (synthetic)

## Phase 1 — alpha

### A1 — cheap first-try task
- status: done
- model: haiku

### A2 — sonnet clean task
- status: done
- model: sonnet

### A3 — sonnet retry task
- status: done
- model: sonnet

### A4 — opus task
- status: done
- model: opus

### A5 — escalated sonnet task
- status: done
- model: sonnet
"""

DEMO_HIST_ALPHA_NOTES_MD = """# NOTES — hist-alpha (synthetic)

## Outcome ledger
outcome: A1 model=haiku result=pass review=clean
outcome: A2 model=sonnet result=pass review=clean
outcome: A3 model=sonnet attempts=2 result=retry-pass review=revised
outcome: A4 model=opus result=pass review=clean
outcome: A5 model=fable attempts=3 result=escalated-pass review=clean
agent: A1 id=ag-hist-v1 role=verifier model=haiku findings=2 confirmed=2 result=accepted
agent: A2 id=ag-hist-v2 role=verifier model=sonnet findings=3 confirmed=1 result=revised
agent: A4 id=ag-hist-esc role=escalation model=fable result=accepted
reviewer: P1 model=opus findings=2 confirmed=1 result=accepted
defect: A3 kind=stale-pin
defect: - kind=tautological-verify
session: hist-alpha-session
"""

DEMO_HIST_BETA_TASKS_MD = """# TASKS — hist-beta (synthetic)

## Phase 1 — beta

### B1 — cheap task
- status: done
- model: haiku

### B2 — cheap retry task
- status: done
- model: haiku

### B3 — sonnet clean task
- status: done
- model: sonnet

### B4 — sonnet blocked task
- status: blocked
- model: sonnet
"""

DEMO_HIST_BETA_NOTES_MD = """# NOTES — hist-beta (synthetic)

## Outcome ledger
outcome: B1 model=haiku result=pass review=clean
outcome: B2 model=haiku attempts=2 result=retry-pass review=clean
outcome: B3 model=sonnet result=pass review=clean
outcome: B4 model=sonnet attempts=2 result=blocked review=none
reroute: haiku to=sonnet mode=advisory tasks=B2 rate=1/2
"""

DEMO_HIST_GAMMA_TASKS_MD = """# TASKS — hist-gamma (synthetic, pre-ledger)

## Phase 1 — gamma

### C1 — sonnet task
- status: done
- model: sonnet

### C2 — opus task
- status: done
- model: opus

### C3 — pending fable task
- status: pending
- model: fable
"""


# Synthetic fixtures for ``--demo --envelope`` (U4, PLAN E3). All ids/values are synthetic;
# every model token is a bare tier alias (haiku/sonnet/fable — never a concrete pricing id).
# Both kits pin every task at haiku and escalate it (result=escalated-pass, failure=<class>)
# so BOTH land in the (haiku, <class>) envelope class, proving the acceptance criterion's two
# directions from the SAME ladder shape:
#
# ``env-rare`` (failure=execution): 1 of 10 resolves at the immediate next rung (sonnet), 9
#   need the top rung (fable/frontier) — the two-model cascade is forced up to frontier for
#   everyone by those 9 anyway, so skipping the doomed sonnet/opus attempts the ladder would
#   have walked for them makes the CASCADE CHEAPER.
# ``env-often`` (failure=verification): 9 of 10 resolve at the immediate next rung (sonnet),
#   only 1 needs the top rung (fable/frontier) — the ladder resolves most of them cheaply one
#   rung up, while a cascade forced to frontier by that single outlier would overpay for all
#   nine, so the LADDER is cheaper: the "vice versa" direction.
DEMO_ENVELOPE_RARE_TASKS_MD = """# TASKS — env-rare (synthetic, cascade-cheaper demo)

## Phase 1 — rare middle resolution

### R1 — resolves at the next rung
- status: done
- model: haiku

### R2 — needs the top rung
- status: done
- model: haiku

### R3 — needs the top rung
- status: done
- model: haiku

### R4 — needs the top rung
- status: done
- model: haiku

### R5 — needs the top rung
- status: done
- model: haiku

### R6 — needs the top rung
- status: done
- model: haiku

### R7 — needs the top rung
- status: done
- model: haiku

### R8 — needs the top rung
- status: done
- model: haiku

### R9 — needs the top rung
- status: done
- model: haiku

### R10 — needs the top rung
- status: done
- model: haiku
"""

DEMO_ENVELOPE_RARE_NOTES_MD = """# NOTES — env-rare (synthetic, cascade-cheaper demo)

## Outcome ledger
outcome: R1 model=sonnet attempts=2 result=escalated-pass review=clean failure=execution
outcome: R2 model=fable attempts=3 result=escalated-pass review=clean failure=execution
outcome: R3 model=fable attempts=3 result=escalated-pass review=clean failure=execution
outcome: R4 model=fable attempts=3 result=escalated-pass review=clean failure=execution
outcome: R5 model=fable attempts=3 result=escalated-pass review=clean failure=execution
outcome: R6 model=fable attempts=3 result=escalated-pass review=clean failure=execution
outcome: R7 model=fable attempts=3 result=escalated-pass review=clean failure=execution
outcome: R8 model=fable attempts=3 result=escalated-pass review=clean failure=execution
outcome: R9 model=fable attempts=3 result=escalated-pass review=clean failure=execution
outcome: R10 model=fable attempts=3 result=escalated-pass review=clean failure=execution
"""

DEMO_ENVELOPE_OFTEN_TASKS_MD = """# TASKS — env-often (synthetic, ladder-cheaper demo)

## Phase 1 — frequent middle resolution

### O1 — resolves at the next rung
- status: done
- model: haiku

### O2 — resolves at the next rung
- status: done
- model: haiku

### O3 — resolves at the next rung
- status: done
- model: haiku

### O4 — resolves at the next rung
- status: done
- model: haiku

### O5 — resolves at the next rung
- status: done
- model: haiku

### O6 — resolves at the next rung
- status: done
- model: haiku

### O7 — resolves at the next rung
- status: done
- model: haiku

### O8 — resolves at the next rung
- status: done
- model: haiku

### O9 — resolves at the next rung
- status: done
- model: haiku

### O10 — needs the top rung
- status: done
- model: haiku
"""

DEMO_ENVELOPE_OFTEN_NOTES_MD = """# NOTES — env-often (synthetic, ladder-cheaper demo)

## Outcome ledger
outcome: O1 model=sonnet attempts=2 result=escalated-pass review=clean failure=verification
outcome: O2 model=sonnet attempts=2 result=escalated-pass review=clean failure=verification
outcome: O3 model=sonnet attempts=2 result=escalated-pass review=clean failure=verification
outcome: O4 model=sonnet attempts=2 result=escalated-pass review=clean failure=verification
outcome: O5 model=sonnet attempts=2 result=escalated-pass review=clean failure=verification
outcome: O6 model=sonnet attempts=2 result=escalated-pass review=clean failure=verification
outcome: O7 model=sonnet attempts=2 result=escalated-pass review=clean failure=verification
outcome: O8 model=sonnet attempts=2 result=escalated-pass review=clean failure=verification
outcome: O9 model=sonnet attempts=2 result=escalated-pass review=clean failure=verification
outcome: O10 model=fable attempts=3 result=escalated-pass review=clean failure=verification
"""


# Synthetic fixtures for ``--demo --alarm`` (T11, PLAN D11 / Phase 1 F7). All ids/values
# are synthetic; the only model tokens are tier names plus the ``fable`` alias, except
# ``driver-blind``'s outcome line, whose model id is computed from data/pricing.json at
# run time (never hardcoded) -- it exists specifically to carry a CONCRETE pricing id, the
# P34-F1 shape every real driver writes.
#
# ``spike-3`` alone carries a lineage ``parent=`` (SP2 rescuing SP1) and two
# ``failure=verification`` lines -- exercising the T2 Escalation lineage + Failure
# breakdown sections, which no prior ``--demo`` path touched (Phase 1's F7).
DEMO_ALARM_SPIKE_TASKS_MD = """# TASKS — spike-3 (synthetic, escalation-rate alarm demo)

## Phase 1 — spiking

### SP1 — the task whose verify command drifted
- status: blocked
- model: sonnet

### SP2 — consult spawned to rescue SP1
- status: done
- model: sonnet

### SP3 — sonnet task escalated to fable
- status: done
- model: sonnet

### SP4 — sonnet task escalated to fable
- status: done
- model: sonnet

### SP5 — sonnet task escalated to fable
- status: done
- model: sonnet

### SP6 — a second blocked task, same failure class
- status: blocked
- model: sonnet
"""

DEMO_ALARM_SPIKE_NOTES_MD = """# NOTES — spike-3 (synthetic, escalation-rate alarm demo)

A drifting verify command sent nearly every task in this kit up the ladder -- the D11
alarm this demo exercises. SP2 is a consult task spawned to rescue SP1 (lineage
`parent=`); SP1 and SP6 both carry `failure=verification` (failure breakdown).

## Outcome ledger
outcome: SP1 model=sonnet attempts=2 result=blocked review=none failure=verification
outcome: SP2 model=fable attempts=3 result=escalated-pass review=clean parent=SP1
outcome: SP3 model=fable attempts=2 result=escalated-pass review=clean
outcome: SP4 model=fable attempts=2 result=escalated-pass review=clean
outcome: SP5 model=fable attempts=2 result=escalated-pass review=clean
outcome: SP6 model=sonnet attempts=2 result=blocked review=none failure=verification
"""

DEMO_ALARM_BLIND_TASKS_MD = """# TASKS — driver-blind (synthetic, P34-F1 honesty demo)

## Phase 1 — driver dispatch

### DR1 — dispatched by a driver harness, not the Agent tool
- status: done
- model: sonnet
"""


def _alarm_demo_steady_kit_md(prefix, n_pass=9):
    """One STEADY kit for the ``--demo --alarm`` fixture: ``n_pass`` clean sonnet passes
    plus one sonnet task escalated to fable (rescued in place, no ``parent=``) -- a LOW,
    STABLE 1/(n_pass+1) escalation rate, used twice (unchanged) to build the D11 alarm's
    trailing baseline and to prove a stable kit does not trip. All ids/values synthetic.
    """
    tasks = [f"### {prefix}{i} — steady task\n- status: done\n- model: sonnet\n"
             for i in range(1, n_pass + 2)]
    tasks_md = (f"# TASKS — {prefix.lower()} (synthetic, alarm-demo baseline)\n\n"
               f"## Phase 1 — steady\n\n" + "\n".join(tasks))
    lines = [f"outcome: {prefix}{i} model=sonnet attempts=1 result=pass review=clean"
             for i in range(1, n_pass + 1)]
    lines.append(f"outcome: {prefix}{n_pass + 1} model=fable attempts=2 "
                 f"result=escalated-pass review=clean")
    notes_md = (f"# NOTES — {prefix.lower()} (synthetic, alarm-demo baseline)\n\n"
               "## Outcome ledger\n" + "\n".join(lines) + "\n")
    return tasks_md, notes_md


# Synthetic single-kit fixture for ``--demo --by-task`` (PLAN D9). Five done tasks; the agent
# ledger below carries the two honesty proofs — a shared warm agent (``ag-warm`` on P3 + P4,
# one transcript, attributed to the cluster as a unit) and a missing transcript (``ag-ghost``
# on P5, no ``.output`` file, priced null). One agent line is deliberately malformed (role out
# of vocabulary) to exercise the tolerant skip. All ids/values are synthetic; the only model
# tokens are tier names plus the ``fable`` alias.
DEMO_BYTASK_TASKS_MD = """# TASKS — per-task-demo (synthetic)

## Phase 1 — per-task demo

### P1 — cheap first-try task
- status: done
- model: haiku

### P2 — escalated sonnet task
- status: done
- model: sonnet

### P3 — warm-cluster task one
- status: done
- model: sonnet

### P4 — warm-cluster task two
- status: done
- model: sonnet

### P5 — ghost-transcript task
- status: done
- model: sonnet
"""

DEMO_BYTASK_NOTES_MD = """# NOTES — per-task-demo (synthetic)

Prose describing the synthetic run this per-task demo consumes, followed by the machine-readable
outcome ledger and the agent ledger. One agent line is deliberately malformed (an
out-of-vocabulary role) to exercise the tolerant skip.

## Outcome ledger
outcome: P1 model=haiku result=pass review=clean
outcome: P2 model=fable attempts=3 result=escalated-pass review=clean
outcome: P3 model=sonnet result=pass review=clean
outcome: P4 model=sonnet result=pass review=clean
outcome: P5 model=sonnet result=pass review=clean

## Agent ledger
agent: P1 id=ag-p1-impl role=implementer model=haiku
agent: P1 id=ag-p1-verif role=verifier model=haiku
agent: P2 id=ag-p2-impl role=implementer model=sonnet
agent: P2 id=ag-p2-retry role=implementer model=sonnet
agent: P2 id=ag-p2-esc role=escalation model=fable
agent: P3 id=ag-warm role=implementer model=sonnet
agent: P4 id=ag-warm role=implementer model=sonnet
agent: P4 id=ag-p4-verif role=verifier model=sonnet
agent: P5 id=ag-ghost role=implementer model=sonnet
agent: P9 id=ag-bad role=chef model=sonnet
"""

# Pinned token VOLUMES (counts, not prices) keyed by agent id: (tier, input, output). The
# transcript's model IDS are COMPUTED from data/pricing.json at run time (never hardcoded).
# ``ag-ghost`` is deliberately absent (its ``.output`` file is never written — the cleaned-tmp
# case); ``ag-reviewer`` is present but referenced by NO ledger line (the unattributed case).
DEMO_BYTASK_VOLUMES = {
    "ag-p1-impl": ("haiku", 120000, 5000),
    "ag-p1-verif": ("haiku", 40000, 1500),
    "ag-p2-impl": ("sonnet", 200000, 9000),
    "ag-p2-retry": ("sonnet", 220000, 10000),
    "ag-p2-esc": ("frontier", 30000, 4000),
    "ag-warm": ("sonnet", 500000, 24000),
    "ag-p4-verif": ("sonnet", 60000, 2500),
    "ag-reviewer": ("opus", 90000, 6000),
}


# --------------------------------------------------------------------------- pure functions

def parse_outcomes(text):
    """Scan ``text`` for ``outcome:`` ledger lines (D5 grammar, extended by graph-convergence
    T1/T2) and return ``(outcomes, notes)``.

    ``outcomes`` maps ``task_id -> {"model", "attempts", "result", "review"}`` plus THREE
    OPTIONAL keys — ``"run"``, ``"parent"``, ``"failure"`` — present ONLY when the source line
    carried that field and it validated; a line without them parses to exactly the same
    four-key dict as before T2 (absent means today's behavior). Parsing is tolerant: an
    outcome needs ``model`` and a ``result`` in ``RESULTS``, else the whole line is skipped
    with an ``unrecognized outcome line`` note; ``attempts`` falls back to 1 (with a note) on
    non-integer garbage; ``review`` defaults to ``"none"`` and any value outside ``REVIEWS``
    degrades to ``"none"`` with a note; unknown ``key=value`` pairs are ignored
    (forward-compatible); and later lines for the same task id REPLACE earlier ones (re-runs
    append; last wins).

    ONE exception to last-wins, and it exists because ``budget-stop`` is the only result value
    that is NOT a verdict: a ``budget-stop`` NEVER supersedes an already-recorded non-
    ``budget-stop`` outcome for the same task id. Resuming an already-``blocked`` (or passed)
    task after a declared budget cap is spent is an ordinary gesture, and the drivers' budget
    gate fires before any status check, so the appended ``budget-stop`` line would otherwise
    erase a real verdict — and its ``failure=`` class with it — from the kit card and from
    ``--history``. The earlier verdict is kept and the later budget-stop is dropped with a note.
    The reverse order is unaffected (a real verdict recorded AFTER a budget stop replaces it
    normally: the task was eventually dispatched, and that dispatch IS the evidence), and a
    budget-stop with no prior outcome for its id records normally.

    The three optional fields: ``run`` (any non-empty token — a run id's shape is
    execute-owned, so no format is enforced here) is kept verbatim when present; ``parent``
    is kept verbatim UNLESS it equals the outcome's own task id, which is dropped with a note
    (a task is never its own parent); ``failure`` is kept only when it is one of
    ``FAILURE_CLASSES``, else dropped with a note (mirrors the ``review`` degrade, but the
    field is omitted rather than defaulted — there is no sanctioned "none" failure class).
    """
    outcomes = {}
    notes = []
    for line in text.splitlines():
        m = OUTCOME_RE.match(line)
        if not m:
            continue
        tid = m.group(1)
        pairs = dict(PAIR_RE.findall(m.group(2)))
        model = pairs.get("model")
        result = pairs.get("result")
        if not model or result not in RESULTS:
            notes.append(f"unrecognized outcome line: {line.strip()!r}")
            continue
        raw_attempts = pairs.get("attempts")
        if raw_attempts is None:
            attempts = 1
        else:
            try:
                attempts = int(raw_attempts)
            except (TypeError, ValueError):
                attempts = 1
                notes.append(
                    f"outcome {tid}: non-integer attempts {raw_attempts!r}, using 1")
        review = pairs.get("review", "none")
        if review not in REVIEWS:
            notes.append(f"outcome {tid}: unknown review {review!r}, using 'none'")
            review = "none"
        outcome = {"model": model, "attempts": attempts,
                   "result": result, "review": review}

        run = pairs.get("run")
        if run:
            outcome["run"] = run

        parent = pairs.get("parent")
        if parent:
            if parent == tid:
                notes.append(
                    f"outcome {tid}: parent cannot be its own task id — ignored")
            else:
                outcome["parent"] = parent

        raw_failure = pairs.get("failure")
        if raw_failure:
            if raw_failure in FAILURE_CLASSES:
                outcome["failure"] = raw_failure
            else:
                notes.append(
                    f"outcome {tid}: unknown failure class {raw_failure!r} — ignored")

        # The one exception to last-wins (see the docstring): a no-verdict `budget-stop` must
        # never overwrite a recorded verdict for the same task id.
        prior = outcomes.get(tid)
        if (result == "budget-stop" and prior is not None
                and prior["result"] != "budget-stop"):
            notes.append(
                f"outcome {tid}: budget-stop after a recorded {prior['result']!r} outcome — "
                f"the verdict is kept, the budget-stop ignored")
            continue

        outcomes[tid] = outcome
    return outcomes, notes


def tier_for(alias):
    """The pricing.json tier for an Agent-tool model alias (identity except ``fable``)."""
    return TASK_MODEL_TIERS.get(alias, alias)


def is_cheap(alias, expensive_tiers):
    """True iff ``alias``'s tier is NOT one of the expensive tiers.

    Callers pass ``cr.EXPENSIVE_TIERS`` at run time; tests pass their own set.
    """
    return tier_for(alias) not in expensive_tiers


def build_scorecard(kit_name, tasks, outcomes, notes, cost=None,
                    expensive_tiers=frozenset()):
    """Assemble the pinned D10 JSON scorecard from parsed tasks + outcomes.

    ``tasks`` is ``ce.parse_tasks`` output. Each task is joined to its outcome (or
    None). Quality counts run over tasks WITH a recognized outcome; the model mix
    runs over every task (outcome ``model`` else the pinned ``model`` field else
    ``"unspecified"``); cheap-model review survival counts cheap tasks that were
    independently reviewed and the share of those that came back clean. Zero
    denominators yield ``None`` rates, never 0. An outcome whose id is not a task id
    is noted and dropped; when no task carries an outcome, a status-only note is added.

    Each row also carries ``"run"``/``"parent"``/``"failure"`` (T2), but ONLY when the
    task's outcome itself carries that field — a row for a legacy outcome (or no outcome)
    has exactly the same key set as before T2, so a field-less kit's rows, and therefore its
    JSON, are byte-identical to today. The ``quality`` block's ``"budget_stop"`` key (T9) is
    conditional for the same reason: present only when at least one task ended in a
    ``budget-stop``, absent (not zero) otherwise.
    """
    notes = list(notes)
    task_ids = {t["id"] for t in tasks}
    for tid in outcomes:
        if tid not in task_ids:
            notes.append(f"outcome for unknown task id {tid!r} ignored")

    task_rows = []
    model_mix = {}
    with_outcome = 0
    first_try_pass = retry_pass = escalated_pass = blocked = budget_stop = 0
    cheap_reviewed = cheap_clean = 0

    for t in tasks:
        o = outcomes.get(t["id"])
        eff = (o["model"] if o else None) or t.get("model") or "unspecified"
        model_mix[eff] = model_mix.get(eff, 0) + 1
        if o:
            if o["result"] == "budget-stop":
                # T9: a budget-stop carries no verdict about the task's difficulty (nothing
                # dispatched), so it is EXCLUDED from `with_outcome` -- the shared denominator
                # of both `first_try_rate` and `escalation_rate` -- rather than folded into
                # any of the four pass/fail buckets. Counted separately below instead, so it
                # is still visible, never hidden, just not treated as quality evidence.
                budget_stop += 1
            else:
                with_outcome += 1
                if o["result"] == "pass":
                    first_try_pass += 1
                elif o["result"] == "retry-pass":
                    retry_pass += 1
                elif o["result"] == "escalated-pass":
                    escalated_pass += 1
                elif o["result"] == "blocked":
                    blocked += 1
                if is_cheap(eff, expensive_tiers) and o["review"] != "none":
                    cheap_reviewed += 1
                    if o["review"] == "clean":
                        cheap_clean += 1
        row = {
            "id": t["id"],
            "title": t.get("title"),
            "status": t.get("status"),
            "model": t.get("model"),
            "effective_model": eff,
            "result": o["result"] if o else None,
            "attempts": o["attempts"] if o else None,
            "review": o["review"] if o else None,
        }
        if o:
            if o.get("run"):
                row["run"] = o["run"]
            if o.get("parent"):
                row["parent"] = o["parent"]
            if o.get("failure"):
                row["failure"] = o["failure"]
        task_rows.append(row)

    first_try_rate = (first_try_pass / with_outcome) if with_outcome else None
    escalation_rate = (escalated_pass / with_outcome) if with_outcome else None
    survival_rate = (cheap_clean / cheap_reviewed) if cheap_reviewed else None

    # T9: a kit whose only outcomes are budget-stops has ledger evidence (`budget_stop > 0`)
    # even though `with_outcome` is 0 -- that is not the same situation as a kit with NO
    # outcome ledger at all, so the "no outcome ledger found" note is now conditioned on both,
    # and a budget-stop kit gets its own honest note instead (never silently folded into the
    # quality quotient it was excluded from above).
    if with_outcome == 0 and budget_stop == 0:
        notes.append("no outcome ledger found — quality limited to TASKS.md statuses")
    if budget_stop:
        notes.append(
            f"{budget_stop} task(s) ended in budget-stop — excluded from first-try/"
            f"escalation rates (a budget stop carries no verdict about the task's difficulty)"
        )

    # PLAN D6 / GUARDRAILS "optionality is load-bearing": `budget_stop` is a T9 ADDITION to the
    # quality block and therefore CONDITIONAL, exactly like every other field this kit added
    # (`run`/`parent`/`failure` on a task row above, `lineage`/`failure_breakdown` on the
    # history card). Emitting it unconditionally would change the `--json` quality block of
    # every kit ever executed -- none of which can contain a budget-stop, since the result value
    # did not exist when they ran -- which is precisely the byte-identity the goldens exist to
    # protect. Absent means "no budget stop to report"; present means the count, which is always
    # >= 1. Never emit a zero.
    quality = {
        "total": len(tasks),
        "with_outcome": with_outcome,
        "first_try_pass": first_try_pass,
        "retry_pass": retry_pass,
        "escalated_pass": escalated_pass,
        "blocked": blocked,
    }
    if budget_stop:
        quality["budget_stop"] = budget_stop
    quality["first_try_rate"] = first_try_rate
    quality["escalation_rate"] = escalation_rate

    return {
        "schema_version": SCHEMA_VERSION,
        "kit": kit_name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tasks": task_rows,
        "quality": quality,
        "model_mix": model_mix,
        "review": {
            "cheap_reviewed": cheap_reviewed,
            "cheap_clean": cheap_clean,
            "survival_rate": survival_rate,
        },
        "cost": cost,
        "notes": notes,
    }


def session_cost_summary(session_id, projects_dir, tasks_dirs, includes,
                         no_subagents, vs, pricing):
    """Drive the reused session_cost pipeline for one session and return
    ``(cost_dict_or_None, notes)``.

    Missing transcript -> ``(None, [note])``. A bad ``--vs`` id raises ValueError
    (from ``sc.resolve_counterfactual_model``), which propagates for the caller to
    turn into ``sys.exit``. All numbers come from ``session_cost`` / ``cost_report``.
    """
    mt = sc.find_main_transcript(session_id, projects_dir)
    if mt is None:
        return None, [f"no transcript for session {session_id!r} under {projects_dir}"]
    if no_subagents:
        task_dirs = []
    else:
        task_dirs = tasks_dirs or sc.discover_task_dirs(session_id)
    files = sc.gather_files(mt, task_dirs, includes)
    data = sc.collect(files, pricing)
    cf = sc.resolve_counterfactual_model(vs, pricing)
    rep = sc.build_report(data, cf, pricing, pricing.get("billing_mode", "api"))
    return {
        "session": session_id,
        "files_scanned": data["files_read"],
        "actual_usd": rep["actual_total"],
        "counterfactual_usd": rep["cf_total"],
        "counterfactual_model": {"key": rep["cf_key"], "display": rep["cf_display"]},
        "delta_usd": rep["savings"],
        "ratio": rep["ratio"],
        "pricing_cached": pricing.get("cached_date"),
    }, []


# --------------------------------------------------------------------------- rendering

def _rate_pct(rate):
    return f"{rate * 100:.0f}%" if rate is not None else "n/a"


def render_markdown(card):
    """Render the scorecard dict as human markdown: H1 + the five pinned H2s in order.

    T2: the Task outcomes table grows a sixth ``Run`` column ONLY when at least one task
    row carries a ``run`` id — absent everywhere, the table is the same five columns as
    before T2.
    """
    q = card["quality"]
    rv = card["review"]
    cost = card["cost"]
    # When cost is None, distinguish "no --session was passed" from "--session was
    # passed but its transcript wasn't found": the "no session provided" note is
    # appended only in the former case, so the verdict/Dollars lines don't misreport.
    no_session = any(n.startswith("no session provided") for n in card["notes"])
    out = [f"# Routing scorecard — {card['kit']}\n"]

    # Verdict — one bold summary line; unavailable numbers render n/a.
    if q["with_outcome"]:
        seg_first = (f"{q['first_try_pass']}/{q['with_outcome']} tasks passed verify "
                     f"first-try on their pinned model")
    else:
        seg_first = "first-try pass rate n/a (no outcome ledger)"
    seg_surv = f"cheap-model review survival {_rate_pct(rv['survival_rate'])}"
    if cost:
        seg_cost = (f"${cost['actual_usd']:,.2f} actual vs "
                    f"${cost['counterfactual_usd']:,.2f} "
                    f"all-{cost['counterfactual_model']['display']} "
                    f"(Δ ${cost['delta_usd']:,.2f} saved)")
    elif no_session:
        seg_cost = "dollars n/a (no --session)"
    else:
        seg_cost = "dollars n/a (transcript not found)"
    out.append("## Verdict\n")
    out.append(f"**{seg_first} · {seg_surv} · {seg_cost}**\n")

    # Task outcomes. A "Run" column is added ONLY when at least one task row carries a
    # run id (T2) — a kit with no run= anywhere renders the same five-column table as
    # before T2, so the table is byte-identical for every kit executed before this one.
    show_run = any(t.get("run") for t in card["tasks"])
    header_cols = ["Task", "Model", "Status", "Result", "Attempts", "Review"]
    sep_cols = ["---", "---", "---", "---", "---:", "---"]
    if show_run:
        header_cols.append("Run")
        sep_cols.append("---")
    out.append("## Task outcomes\n")
    out.append("| " + " | ".join(header_cols) + " |")
    out.append("|" + "|".join(sep_cols) + "|")
    for t in card["tasks"]:
        result = t["result"] if t["result"] is not None else "—"
        attempts = t["attempts"] if t["attempts"] is not None else "—"
        review = t["review"] if t["review"] is not None else "—"
        cells = [t["id"], t["effective_model"], t["status"], str(result),
                str(attempts), str(review)]
        if show_run:
            cells.append(t.get("run") or "—")
        out.append("| " + " | ".join(cells) + " |")
    out.append("")

    # Model mix.
    out.append("## Model mix\n")
    out.append("| Model | Tasks |")
    out.append("|---|---:|")
    for model, count in card["model_mix"].items():
        out.append(f"| {model} | {count} |")
    out.append("")

    # Review survival.
    out.append("## Review survival\n")
    out.append(f"- Cheap-model tasks reviewed: {rv['cheap_reviewed']}")
    out.append(f"- Reviewed clean (survived unchanged): {rv['cheap_clean']}")
    out.append(f"- Survival rate: {_rate_pct(rv['survival_rate'])}")
    out.append("")
    out.append("*Cheap = a task whose effective model is not in the expensive tiers "
               "(frontier/opus); survival = the review-clean share of reviewed cheap "
               "tasks — the share of cheap-model output that passed independent review "
               "unchanged.*\n")

    # Dollars.
    out.append("## Dollars\n")
    if cost is None:
        if no_session:
            out.append("n/a — pass --session to fold in transcript dollars.")
        else:
            out.append("n/a — no transcript found for the given --session (see notes below).")
    else:
        cf = cost["counterfactual_model"]
        ratio = f"{cost['ratio']:.2f}×" if cost["ratio"] else "n/a"
        out.append(f"- Actual (mixed workflow): ${cost['actual_usd']:,.2f}")
        out.append(f"- All-{cf['display']}: ${cost['counterfactual_usd']:,.2f}")
        out.append(f"- Δ saved vs all-{cf['display']}: ${cost['delta_usd']:,.2f}")
        out.append(f"- Ratio: {ratio}")
        out.append(f"- Files scanned: {cost['files_scanned']}")
        out.append(f"- Prices cached {cost['pricing_cached']}")

    # Per-task dollars (only when --by-task supplied the key; old cards never carry it, so
    # every existing output is byte-identical).
    if card.get("by_task") is not None:
        out.extend(render_by_task_lines(card["by_task"]))

    # Notes.
    if card["notes"]:
        out.append("\nNotes:")
        for n in card["notes"]:
            out.append(f"- {n}")

    return "\n".join(out)


# --------------------------------------------------------------------------- demo

def _first_model_of_tier(pricing, tier):
    """First model id in pricing.json file order carrying ``tier`` (else None)."""
    for key, meta in pricing["models"].items():
        if meta.get("tier") == tier:
            return key
    return None


def run_demo(as_json):
    """Build a synthetic kit + transcript in ONE temp dir, run the real pipeline
    against it, print the scorecard, and clean up. Exit code 0.

    Model ids are computed from data/pricing.json at run time; only the token
    VOLUMES are pinned. This is the sanctioned smoke test.
    """
    pricing = cr.load_pricing()
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        kit_dir = tmp / "kit"
        kit_dir.mkdir()
        (kit_dir / "TASKS.md").write_text(DEMO_TASKS_MD)
        (kit_dir / "NOTES.md").write_text(DEMO_NOTES_MD)

        proj = tmp / "projects" / "-demo"
        proj.mkdir(parents=True)
        ts = "2026-07-01T12:00:00+00:00"
        lines = []
        for tier in ("haiku", "sonnet", "opus", "frontier"):
            model_id = _first_model_of_tier(pricing, tier)
            if model_id is None:
                continue
            inp, outp = DEMO_VOLUMES[tier]
            lines.append(json.dumps({
                "timestamp": ts,
                "message": {
                    "model": model_id,
                    "id": f"demo-{tier}",
                    "usage": {"input_tokens": inp, "output_tokens": outp},
                },
            }))
        (proj / "fusion-demo.jsonl").write_text("\n".join(lines) + "\n")

        tasks = ce.parse_tasks((kit_dir / "TASKS.md").read_text())
        outcomes, notes = parse_outcomes((kit_dir / "NOTES.md").read_text())
        cost, cost_notes = session_cost_summary(
            "fusion-demo", str(tmp / "projects"), [], [], True, None, pricing)
        card = build_scorecard(
            "fusion-demo", tasks, outcomes, list(notes) + list(cost_notes),
            cost=cost, expensive_tiers=cr.EXPENSIVE_TIERS)

    # The card is pure data by here; render after the temp dir is gone.
    print(json.dumps(card, indent=2) if as_json else render_markdown(card))
    return 0


# --------------------------------------------------------------------------- live signal

def parse_reroutes(text):
    """Scan ``text`` for ``reroute:`` ledger lines (D4 grammar) → ``(events, notes)``.

    Grammar: ``reroute: <from-tier> to=<to-tier> mode=<advisory|applied>
    tasks=<id,id,...> rate=<passed>/<completed>``. The first token after ``reroute:`` is
    the from-tier; the remaining ``key=value`` pairs are read with ``PAIR_RE``. An event
    is kept only when the from-tier and ``to=`` are both in ``LIVE_TIER_ORDER`` and
    ``mode=`` is in ``REROUTE_MODES``; otherwise the line is skipped with an
    ``unrecognized reroute line`` note (mirrors ``parse_outcomes``). ``tasks=`` is
    comma-split into a list (missing → ``[]``); ``rate=`` is kept as the raw string
    (informational — no math; missing → ``None``); unknown keys are ignored. Events are
    returned in FILE ORDER (chronology matters for ``effective_alias``). A ``to=frontier``
    event is still kept — honest state reconstruction — but adds an out-of-policy note.
    """
    events = []
    notes = []
    for line in text.splitlines():
        m = REROUTE_RE.match(line)
        if not m:
            continue
        from_tier = m.group(1)
        pairs = dict(PAIR_RE.findall(m.group(2)))
        to_tier = pairs.get("to")
        mode = pairs.get("mode")
        if (from_tier not in LIVE_TIER_ORDER or to_tier not in LIVE_TIER_ORDER
                or mode not in REROUTE_MODES):
            notes.append(f"unrecognized reroute line: {line.strip()!r}")
            continue
        raw_tasks = pairs.get("tasks")
        task_ids = [t for t in raw_tasks.split(",") if t] if raw_tasks else []
        events.append({
            "from": from_tier,
            "to": to_tier,
            "mode": mode,
            "tasks": task_ids,
            "rate": pairs.get("rate"),
        })
        if to_tier == "frontier":
            notes.append("reroute line targets frontier — out of policy")
    return events, notes


def parse_autonomy(text):
    """Read the kit's autonomy posture from PLAN.md ``text`` (or ``None``).

    ``None`` (no PLAN.md) → ``("advisory", ["no PLAN.md — autonomy defaults to
    advisory"])``. Otherwise the FIRST ``AUTONOMY_RE`` match wins → that posture with no
    note. A line beginning ``autonomy:`` with any other value → ``"advisory"`` plus an
    unrecognized-value note. No ``autonomy:`` line at all → ``("advisory", [])``. The
    default is always ``advisory`` — nothing auto-changes unless the kit opts in.
    """
    if text is None:
        return "advisory", ["no PLAN.md — autonomy defaults to advisory"]
    m = AUTONOMY_RE.search(text)
    if m:
        return m.group(1), []
    other = re.search(r"^\s*autonomy:\s*(\S+)", text, re.MULTILINE)
    if other:
        return "advisory", [
            f"unrecognized autonomy value {other.group(1)!r} — using advisory"]
    return "advisory", []


def effective_alias(task, applied_events):
    """The dispatch alias for ``task``: its ``model`` pin, overridden by the LAST applied
    re-route event whose ``tasks`` list names the task's id.

    Legal upgrade targets are non-frontier tiers, which are their own Agent-tool aliases,
    so the event's ``to`` needs no translation. Returns ``None`` when the task has no pin
    and no covering event.
    """
    alias = task.get("model")
    tid = task.get("id")
    for event in applied_events:
        if tid is not None and tid in event.get("tasks", []):
            alias = event["to"]
    return alias


def live_tier_stats(tasks, outcomes, applied_events):
    """Per-tier live first-try stats over the ledger-so-far → ``(stats, notes)``.

    ``stats`` maps EVERY tier in ``LIVE_TIER_ORDER`` to ``{"completed", "first_try",
    "rate"}`` (zeros / rate ``None`` when empty). Outcomes are joined to tasks by id; an
    outcome whose id is not a task id is skipped with a note. Attribution (PLAN D1):
    ``pass`` / ``retry-pass`` / ``blocked`` attribute to ``tier_for(outcome["model"])``
    — the ledger's ``model=`` is what the task actually ran on; ``escalated-pass``
    attributes to ``tier_for(effective_alias(task, applied_events))`` — the ledger's
    ``model=`` on an escalated line names the Fable fixer, so the failure evidence goes to
    the reconstructed DISPATCH tier instead (never frontier). An ``escalated-pass`` with
    no reconstructable dispatch alias, or any outcome whose tier is outside
    ``LIVE_TIER_ORDER`` (garbage alias), is skipped with a note. All four results count
    toward ``completed``; only ``pass`` counts toward ``first_try``;
    ``rate = first_try / completed`` (``None`` when completed is 0). A ``budget-stop``
    (T9) is skipped with a note BEFORE attribution and never counts toward ``completed`` —
    no dispatch happened, so it carries no verdict about the tier's live first-try rate; a
    budget stop is a run-wide event, not a per-tier quality signal.
    """
    stats = {tier: {"completed": 0, "first_try": 0, "rate": None}
             for tier in LIVE_TIER_ORDER}
    notes = []
    tasks_by_id = {t.get("id"): t for t in tasks}
    for tid, o in outcomes.items():
        if tid not in tasks_by_id:
            notes.append(f"outcome for unknown task id {tid!r} ignored")
            continue
        result = o["result"]
        if result == "budget-stop":
            # T9: excluded from the live per-tier signal entirely -- no dispatch happened,
            # so there is nothing to attribute to any tier's first-try rate.
            notes.append(f"outcome {tid}: budget-stop excluded from live per-tier stats")
            continue
        if result == "escalated-pass":
            alias = effective_alias(tasks_by_id[tid], applied_events)
            if alias is None:
                notes.append(
                    f"escalated outcome {tid}: no dispatch model to attribute — skipped")
                continue
            tier = tier_for(alias)
        else:
            tier = tier_for(o["model"])
        if tier not in stats:
            notes.append(
                f"outcome {tid}: tier {tier!r} outside the tier ladder — its per-tier "
                f"attribution is skipped, not the outcome: the line is still parsed and "
                f"valid, it is only absent from the per-tier first-try signal")
            continue
        stats[tier]["completed"] += 1
        if result == "pass":
            stats[tier]["first_try"] += 1
    for s in stats.values():
        s["rate"] = (s["first_try"] / s["completed"]) if s["completed"] else None
    return stats, notes


def upgrade_decision(tasks, outcomes, events, *, threshold=LIVE_RATE_THRESHOLD,
                     min_sample=LIVE_MIN_SAMPLE, max_auto=LIVE_MAX_AUTO_UPGRADES):
    """The upgrade-only re-route decision over the ledger-so-far.

    Reads only ``id`` / ``status`` / ``model`` from each task dict (via ``.get``, so
    tests may pass minimal dicts). Applied re-route events
    (``[e for e in events if e["mode"] == "applied"]``) both reconstruct each pending
    task's effective dispatch tier and count against the budget. Returns
    ``{"signals", "recommendations", "budget", "notes"}``:

    * ``signals[tier]`` = ``{completed, first_try, rate, below_threshold, at_ceiling}``.
      ``below_threshold`` = ``completed >= min_sample and rate is not None and
      rate < threshold`` (STRICTLY below — a tier exactly AT the threshold is not
      struggling). ``at_ceiling`` is True when the tier's next rung is ``"frontier"`` or
      the tier IS ``"frontier"``.
    * ``recommendations`` — one per struggling, non-ceiling tier that has pending tasks:
      ``{"from", "to", "task_ids", "rate", "completed", "first_try"}``, ordered by ladder
      position, ``task_ids`` in TASKS.md order over ``status == "pending"`` tasks whose
      reconstructed dispatch tier equals the struggling tier. NEVER contains
      ``to == "frontier"`` — the ceiling check runs before any emit.
    * ``budget`` — ``{cap, applied, remaining}`` with
      ``remaining = max(0, max_auto - applied)``. Recommendations are STILL listed when
      the budget is exhausted (the skill owns the apply-only-while-remaining rule).
    """
    applied = [e for e in events if e["mode"] == "applied"]
    stats, notes = live_tier_stats(tasks, outcomes, applied)

    signals = {}
    recommendations = []
    for idx, tier in enumerate(LIVE_TIER_ORDER):
        s = stats[tier]
        completed = s["completed"]
        first_try = s["first_try"]
        rate = s["rate"]
        below = (completed >= min_sample and rate is not None and rate < threshold)
        next_rung = (LIVE_TIER_ORDER[idx + 1]
                     if idx + 1 < len(LIVE_TIER_ORDER) else None)
        at_ceiling = (tier == "frontier") or (next_rung == "frontier")
        signals[tier] = {
            "completed": completed,
            "first_try": first_try,
            "rate": rate,
            "below_threshold": below,
            "at_ceiling": at_ceiling,
        }
        if not below:
            continue
        if at_ceiling:
            notes.append(
                f"frontier locked: escalation valve only "
                f"({tier} first-try {first_try}/{completed} below threshold)")
            continue
        task_ids = [t.get("id") for t in tasks
                    if t.get("status") == "pending"
                    and tier_for(effective_alias(t, applied)) == tier]
        if not task_ids:
            notes.append(f"no pending {tier} tasks to upgrade")
            continue
        recommendations.append({
            "from": tier,
            "to": next_rung,
            "task_ids": task_ids,
            "rate": rate,
            "completed": completed,
            "first_try": first_try,
        })

    applied_count = len(applied)
    remaining = max(0, max_auto - applied_count)
    if remaining == 0:
        notes.append("auto-upgrade budget exhausted — advisory only")

    return {
        "signals": signals,
        "recommendations": recommendations,
        "budget": {"cap": max_auto, "applied": applied_count, "remaining": remaining},
        "notes": notes,
    }


def build_live_card(kit_name, decision, autonomy, notes):
    """Assemble the pinned D9 ``--live`` JSON card from an ``upgrade_decision`` dict."""
    return {
        "schema_version": LIVE_SCHEMA_VERSION,
        "kit": kit_name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "autonomy": autonomy,
        "signals": decision["signals"],
        "recommendations": decision["recommendations"],
        "budget": decision["budget"],
        "notes": list(decision["notes"]) + list(notes),
    }


def render_live_markdown(card):
    """Render the live card as human markdown: H1 + posture + per-tier + recs + budget."""
    out = [f"# Live re-route signal — {card['kit']}\n"]
    out.append(f"autonomy: {card['autonomy']}\n")
    for tier in LIVE_TIER_ORDER:
        s = card["signals"][tier]
        if s["completed"] == 0:
            out.append(f"- {tier}: no finished tasks")
        else:
            line = f"- {tier}: first-try {s['first_try']}/{s['completed']}"
            if s["below_threshold"]:
                line += " — below threshold"
            out.append(line)
    out.append("")

    recs = card["recommendations"]
    if recs:
        for r in recs:
            ids = ", ".join(r["task_ids"])
            out.append(f"recommend: {r['from']} → {r['to']} — tasks {ids} "
                       f"(first-try {r['first_try']}/{r['completed']})")
    else:
        out.append("no re-route recommended")
    out.append("")

    b = card["budget"]
    out.append(f"budget: {b['applied']}/{b['cap']} auto-upgrades applied "
               f"({b['remaining']} remaining)")

    if card["notes"]:
        out.append("\nNotes:")
        for n in card["notes"]:
            out.append(f"- {n}")
    return "\n".join(out)


def run_live_demo(as_json):
    """Build a synthetic MID-RUN kit (TASKS.md + NOTES.md, no PLAN.md) in one temp dir
    and run the normal ``--live`` path against it (same functions, same render). Exit 0.

    All ids/values are synthetic; no pricing is loaded (the live branch returns before
    ``cr.load_pricing``). This is the sanctioned live smoke test.
    """
    with tempfile.TemporaryDirectory() as tmp_name:
        kit_dir = Path(tmp_name) / "fusion-live-demo"
        kit_dir.mkdir()
        (kit_dir / "TASKS.md").write_text(DEMO_LIVE_TASKS_MD)
        (kit_dir / "NOTES.md").write_text(DEMO_LIVE_NOTES_MD)
        argv = [str(kit_dir), "--live"]
        if as_json:
            argv.append("--json")
        return main(argv)


# --------------------------------------------------------------------------- history

def parse_sessions(text):
    """Scan ``text`` for ``session:`` NOTES.md lines (D3 grammar) → ``(ids, notes)``.

    Grammar: ``session: <session-id>`` — one whitespace-free token, nothing else on the
    line (an optional ``-`` / ``*`` bullet is tolerated, mirroring ``OUTCOME_RE`` /
    ``REROUTE_RE``). Ids are returned in FILE ORDER, deduped preserving first occurrence.
    The id's SHAPE is harness-owned, so there is no id-format validation. A line that
    starts ``session:`` (after an optional bullet) but does NOT match the full grammar
    (e.g. two tokens) is noted as an ``unrecognized session line`` (mirrors
    ``parse_outcomes``) — never guessed at.
    """
    ids = []
    seen = set()
    notes = []
    for line in text.splitlines():
        m = SESSION_RE.match(line)
        if m:
            sid = m.group(1)
            if sid not in seen:
                seen.add(sid)
                ids.append(sid)
            continue
        if _SESSION_PREFIX_RE.match(line):
            notes.append(f"unrecognized session line: {line.strip()!r}")
    return ids, notes


def history_tier_stats(tasks, outcomes, applied_events):
    """Per-tier cross-kit track record over one kit's tasks + ledger → ``(stats, notes)``.

    ``stats`` maps EVERY tier in ``LIVE_TIER_ORDER`` to ``{"pinned", "with_outcome",
    "first_try", "retry_pass", "escalated_pass", "blocked", "first_try_rate",
    "escalation_rate"}``. ``pinned`` counts tasks by ``tier_for(task.get("model"))`` — the
    RAW pin, NEVER shifted by re-routes (pins-vs-outcomes is the comparison the architect
    needs); a task with no pin or an off-ladder pin is excluded from ``pinned`` and counted
    in ONE note per call. Outcomes are joined to tasks by id; an outcome whose id is not a
    task id is skipped with a note.

    Attribution (PLAN D2 = fusion-tier2 D1, reused verbatim): ``pass`` / ``retry-pass`` /
    ``blocked`` attribute to ``tier_for(outcome["model"])`` — what the task actually ran on;
    ``escalated-pass`` attributes to ``tier_for(effective_alias(task, applied_events))`` —
    the reconstructed DISPATCH tier, because the ledger's ``model=`` on an escalated line
    names the Fable fixer and crediting frontier with a cheap tier's struggle would pollute
    frontier's stats. An ``escalated-pass`` with no reconstructable dispatch alias, or any
    outcome whose tier is outside ``LIVE_TIER_ORDER``, is skipped with a note. All four
    results count in ``with_outcome``; ``first_try_rate = first_try / with_outcome`` and
    ``escalation_rate = escalated_pass / with_outcome`` (both ``None`` when ``with_outcome``
    is 0 — never a fabricated 0%). Reads only ``id`` / ``model`` / ``status`` via ``.get``.
    A ``budget-stop`` (T9) is skipped with a note BEFORE attribution and never enters
    ``with_outcome`` — no dispatch happened, so it would dilute both rates' shared
    denominator with an event that says nothing about whether the tier could do the work.
    """
    stats = {tier: {"pinned": 0, "with_outcome": 0, "first_try": 0, "retry_pass": 0,
                    "escalated_pass": 0, "blocked": 0, "first_try_rate": None,
                    "escalation_rate": None}
             for tier in LIVE_TIER_ORDER}
    notes = []

    unpinned = 0
    for t in tasks:
        tier = tier_for(t.get("model"))
        if tier in stats:
            stats[tier]["pinned"] += 1
        else:
            unpinned += 1
    if unpinned:
        notes.append(f"{unpinned} tasks without a recognized tier pin")

    tasks_by_id = {t.get("id"): t for t in tasks}
    for tid, o in outcomes.items():
        if tid not in tasks_by_id:
            notes.append(f"outcome for unknown task id {tid!r} ignored")
            continue
        result = o["result"]
        if result == "budget-stop":
            # T9: excluded entirely -- no dispatch happened, so there is nothing to
            # attribute to any tier's with_outcome/first_try/escalation counts.
            notes.append(f"outcome {tid}: budget-stop excluded from per-tier track record")
            continue
        if result == "escalated-pass":
            alias = effective_alias(tasks_by_id[tid], applied_events)
            if alias is None:
                notes.append(
                    f"escalated outcome {tid}: no dispatch model to attribute — skipped")
                continue
            tier = tier_for(alias)
        else:
            tier = tier_for(o["model"])
        if tier not in stats:
            notes.append(
                f"outcome {tid}: tier {tier!r} outside the tier ladder — its per-tier "
                f"attribution is skipped, not the outcome: the line is still parsed, and "
                f"still counted in the escalation-lineage section when it carries parent=")
            continue
        s = stats[tier]
        s["with_outcome"] += 1
        if result == "pass":
            s["first_try"] += 1
        elif result == "retry-pass":
            s["retry_pass"] += 1
        elif result == "escalated-pass":
            s["escalated_pass"] += 1
        elif result == "blocked":
            s["blocked"] += 1

    for s in stats.values():
        wo = s["with_outcome"]
        s["first_try_rate"] = (s["first_try"] / wo) if wo else None
        s["escalation_rate"] = (s["escalated_pass"] / wo) if wo else None
    return stats, notes


def tally_reroutes(events):
    """Tally re-route EVENTS (one event = one logged decision) → totals + per-tier counts.

    Returns ``{"events", "applied", "advisory", "by_tier"}`` where ``by_tier`` maps EVERY
    ``LIVE_TIER_ORDER`` tier to ``{"applied_from", "applied_to", "advisory_from",
    "advisory_to"}`` (zeros when untouched). ``parse_reroutes`` already guarantees ``from`` /
    ``to`` are ladder tiers; the ``in by_tier`` guards keep an off-ladder event from crashing
    the tally (it is simply not counted for that tier).
    """
    by_tier = {tier: {"applied_from": 0, "applied_to": 0,
                      "advisory_from": 0, "advisory_to": 0}
               for tier in LIVE_TIER_ORDER}
    applied = advisory = 0
    for e in events:
        mode = e.get("mode")
        frm = e.get("from")
        to = e.get("to")
        if mode == "applied":
            applied += 1
            if frm in by_tier:
                by_tier[frm]["applied_from"] += 1
            if to in by_tier:
                by_tier[to]["applied_to"] += 1
        elif mode == "advisory":
            advisory += 1
            if frm in by_tier:
                by_tier[frm]["advisory_from"] += 1
            if to in by_tier:
                by_tier[to]["advisory_to"] += 1
    return {"events": len(events), "applied": applied, "advisory": advisory,
            "by_tier": by_tier}


def scan_kits(kits_dir):
    """Scan every kit under ``kits_dir`` → ``(records, notes)``, deterministic + tolerant.

    Subdirectories are visited in sorted-by-name order. A subdir with no ``TASKS.md`` is
    skipped with a note; a ``TASKS.md`` that makes ``ce.parse_tasks`` raise ``ValueError``
    skips that kit with a note (never a crash). Otherwise ``NOTES.md`` is read ONCE (if
    present) and fed to ``parse_outcomes`` + ``parse_reroutes`` + ``parse_sessions`` +
    ``parse_agents`` + ``parse_reviewers`` + ``parse_defects``, whose own tolerance notes are
    carried through prefixed ``<kit>: ``. A missing ``NOTES.md`` → empty
    outcomes/events/sessions/agents/reviewers/defects plus the ``<kit>: no outcome ledger —
    status-only`` note (every pre-ledger kit contributes its pins and nothing to the outcome
    counters). Each record: ``{"kit", "tasks", "outcomes", "events", "sessions", "agents",
    "reviewers", "defects", "notes"}``; the returned top-level ``notes`` carry every kit note
    already prefixed with the kit name.
    """
    kits_dir = Path(kits_dir)
    records = []
    notes = []
    for sub in sorted((p for p in kits_dir.iterdir() if p.is_dir()),
                      key=lambda p: p.name):
        name = sub.name
        tasks_path = sub / "TASKS.md"
        if not tasks_path.is_file():
            notes.append(f"{name}: no TASKS.md — skipped")
            continue
        try:
            tasks = ce.parse_tasks(tasks_path.read_text(errors="replace"))
        except ValueError as e:
            notes.append(f"{name}: malformed TASKS.md ({e}) — skipped")
            continue
        rec_notes = []
        notes_path = sub / "NOTES.md"
        if notes_path.is_file():
            notes_text = notes_path.read_text(errors="replace")
            outcomes, out_notes = parse_outcomes(notes_text)
            events, rr_notes = parse_reroutes(notes_text)
            sessions, sess_notes = parse_sessions(notes_text)
            agents, agent_notes = parse_agents(notes_text)
            reviewers, reviewer_notes = parse_reviewers(notes_text)
            defects, defect_notes = parse_defects(notes_text)
            for n in (list(out_notes) + list(rr_notes) + list(sess_notes)
                      + list(agent_notes) + list(reviewer_notes) + list(defect_notes)):
                rec_notes.append(f"{name}: {n}")
        else:
            outcomes, events, sessions = {}, [], []
            agents, reviewers, defects = [], [], []
            rec_notes.append(f"{name}: no outcome ledger — status-only")
        records.append({
            "kit": name,
            "tasks": tasks,
            "outcomes": outcomes,
            "events": events,
            "sessions": sessions,
            "agents": agents,
            "reviewers": reviewers,
            "defects": defects,
            "notes": rec_notes,
        })
        notes.extend(rec_notes)
    return records, notes


def kit_cost_summary(session_ids, projects_dir, no_subagents, vs, pricing):
    """Price one scope's session ids with ONE ``collect()`` → ``(cost_or_None, transcripts,
    notes)`` — never a fabricated number.

    Each id is resolved via ``sc.find_main_transcript`` (missing → note naming the id, id
    skipped — NEVER invented); transcripts are deduped preserving order. Task dirs are the
    union of ``sc.discover_task_dirs`` over the FOUND ids (unless ``no_subagents``). The
    file list is built with ``sc.gather_files(None, task_dirs, [str(t) for t in
    transcripts])`` (its first arg may be ``None``; the explicit paths ride ``includes``),
    and priced with ONE ``sc.collect(files, pricing)`` so the GLOBAL message-id dedupe
    absorbs any overlap between a kit's several sessions (a resumed transcript can embed
    prior messages — summing per-session reports would double count; collecting once
    cannot). Returns ``{"actual_usd", "counterfactual_usd", "delta_usd", "ratio",
    "sessions_priced", "files_scanned"}`` — or ``None`` (with notes) when no transcript was
    found. A bad ``--vs`` raises ``ValueError`` (from ``sc.resolve_counterfactual_model``)
    for the caller to turn into ``sys.exit``.
    """
    transcripts = []
    found_ids = []
    seen = set()
    notes = []
    for sid in session_ids:
        mt = sc.find_main_transcript(sid, projects_dir)
        if mt is None:
            notes.append(f"no transcript for session {sid!r} under {projects_dir}")
            continue
        try:
            rp = mt.resolve()
        except OSError:
            rp = mt
        if rp in seen:
            continue
        seen.add(rp)
        transcripts.append(mt)
        found_ids.append(sid)
    if not transcripts:
        return None, transcripts, notes

    task_dirs = []
    if not no_subagents:
        seen_td = set()
        for sid in found_ids:
            for d in sc.discover_task_dirs(sid):
                try:
                    rd = Path(d).resolve()
                except OSError:
                    rd = Path(d)
                if rd not in seen_td:
                    seen_td.add(rd)
                    task_dirs.append(d)

    files = sc.gather_files(None, task_dirs, [str(t) for t in transcripts])
    data = sc.collect(files, pricing)
    cf = sc.resolve_counterfactual_model(vs, pricing)
    rep = sc.build_report(data, cf, pricing, pricing.get("billing_mode", "api"))
    cost = {
        "actual_usd": rep["actual_total"],
        "counterfactual_usd": rep["cf_total"],
        "delta_usd": rep["savings"],
        "ratio": rep["ratio"],
        "sessions_priced": len(transcripts),
        "files_scanned": data["files_read"],
    }
    return cost, transcripts, notes


def role_quality_stats(records):
    """Aggregate role-quality evidence over every scanned record's ``agents``/``reviewers``/
    ``defects`` (D1/D6/D7) → ``(roles, notes)``.

    ``roles`` has keys exactly ``{"verifier", "escalation", "reviewer", "architect"}``.
    IMPLEMENTER IS DELIBERATELY ABSENT (PLAN D7 — "one number, one home"): implementer
    quality lives in the outcome ledger / per-tier track record only; a ``result=`` on a
    ``role=implementer`` ``agent:`` event is parsed by ``parse_agents`` but never read here.

    - ``roles["verifier"]``: over every record's ``agents`` events with ``role ==
      "verifier"``. Keys exactly ``{"events", "with_precision", "findings", "confirmed",
      "precision", "results", "by_tier"}``. ``with_precision`` counts events whose
      ``findings`` is not ``None``; ``findings``/``confirmed`` are summed over just those
      events; ``precision`` is ``confirmed / findings`` when the findings sum is > 0, else
      ``None`` (never a fabricated 0%). ``results`` tallies ``event["result"]`` into keys
      exactly ``{"accepted", "revised", "blocked", "unrecorded"}`` (``None``, or any value
      outside ``AGENT_RESULTS``, counts as ``"unrecorded"``).
    - ``roles["escalation"]``: ``{"events", "results"}`` — same results tally, from
      ``role == "escalation"`` events. No findings/confirmed/by_tier: escalation carries no
      precision signal.
    - ``roles["reviewer"]``: from every record's ``reviewers`` events. Top-level keys exactly
      ``{"events", "findings", "confirmed", "precision", "results", "by_tier"}`` — no
      top-level ``with_precision`` key, because ``parse_reviewers`` only ever KEEPS a line
      that already carries a valid findings/confirmed pair, so every reviewer event has
      precision by construction (its ``by_tier`` buckets still carry ``with_precision``, for
      shape parity with verifier — it always equals that bucket's ``events``).
    - Both verifier and reviewer carry ``by_tier``: ALWAYS maps every ``LIVE_TIER_ORDER``
      tier to ``{"events", "with_precision", "findings", "confirmed", "precision"}`` (zeros /
      ``None`` when that tier has no events for this role). ``with_precision`` counts, within
      that tier, events whose ``findings`` is not ``None`` — same definition as the top-level
      ``with_precision`` — so a tier with events but ``with_precision == 0`` ("ran, nothing
      recorded") is distinguishable from a tier that genuinely found zero (``with_precision >
      0``, ``findings == 0``); the two are never rendered identically (F4). Attribution is via
      ``tier_for(event["model"])``; an event whose model is missing or off-ladder is still
      counted in the role's top-level ``"events"`` (and top-level ``"findings"``/
      ``"confirmed"`` when it has precision) but excluded from every ``by_tier`` bucket, and
      contributes to ONE aggregate note per role (never one note per event) — so
      ``sum(by_tier[t]["findings"]) <= findings``; the caller discloses any nonzero gap.
    - ``roles["architect"]``: from every record's ``defects``. Keys exactly ``{"defects",
      "kits_recording", "by_kind", "by_kit"}``. ``by_kit`` maps ``rec["kit"]`` to its defect
      count, for kits with >= 1 defect only; ``kits_recording = len(by_kit)``; ``by_kind``
      tallies ``kind`` across every defect in every kit; ``defects`` is the grand total.

    Pure and read-only: no I/O, no fabricated numbers — every empty denominator yields
    ``None``, never 0 or 100%.
    """
    notes = []

    def tally_results(events):
        tally = {"accepted": 0, "revised": 0, "blocked": 0, "unrecorded": 0}
        for e in events:
            r = e.get("result")
            tally[r if r in AGENT_RESULTS else "unrecorded"] += 1
        return tally

    def by_tier_for(events, label):
        by_tier = {tier: {"events": 0, "with_precision": 0, "findings": 0,
                           "confirmed": 0, "precision": None}
                   for tier in LIVE_TIER_ORDER}
        off_ladder = 0
        for e in events:
            tier = tier_for(e.get("model"))
            if tier not in LIVE_TIER_ORDER:
                off_ladder += 1
                continue
            bt = by_tier[tier]
            bt["events"] += 1
            if e.get("findings") is not None:
                bt["with_precision"] += 1
                bt["findings"] += e["findings"]
                bt["confirmed"] += e["confirmed"]
        for tier in LIVE_TIER_ORDER:
            bt = by_tier[tier]
            bt["precision"] = (bt["confirmed"] / bt["findings"]) if bt["findings"] else None
        if off_ladder:
            notes.append(
                f"role quality: {off_ladder} {label} event(s) with missing/unrecognized "
                f"model excluded from by_tier")
        return by_tier

    verifier_events = [e for rec in records for e in rec.get("agents", [])
                        if e["role"] == "verifier"]
    v_with_precision = [e for e in verifier_events if e["findings"] is not None]
    v_findings = sum(e["findings"] for e in v_with_precision)
    v_confirmed = sum(e["confirmed"] for e in v_with_precision)
    verifier = {
        "events": len(verifier_events),
        "with_precision": len(v_with_precision),
        "findings": v_findings,
        "confirmed": v_confirmed,
        "precision": (v_confirmed / v_findings) if v_findings else None,
        "results": tally_results(verifier_events),
        "by_tier": by_tier_for(verifier_events, "verifier"),
    }

    escalation_events = [e for rec in records for e in rec.get("agents", [])
                          if e["role"] == "escalation"]
    escalation = {
        "events": len(escalation_events),
        "results": tally_results(escalation_events),
    }

    reviewer_events = [e for rec in records for e in rec.get("reviewers", [])]
    r_findings = sum(e["findings"] for e in reviewer_events)
    r_confirmed = sum(e["confirmed"] for e in reviewer_events)
    reviewer = {
        "events": len(reviewer_events),
        "findings": r_findings,
        "confirmed": r_confirmed,
        "precision": (r_confirmed / r_findings) if r_findings else None,
        "results": tally_results(reviewer_events),
        "by_tier": by_tier_for(reviewer_events, "reviewer"),
    }

    defects_total = 0
    by_kind = {}
    by_kit = {}
    for rec in records:
        rec_defects = rec.get("defects", [])
        if rec_defects:
            by_kit[rec["kit"]] = len(rec_defects)
        for d in rec_defects:
            defects_total += 1
            by_kind[d["kind"]] = by_kind.get(d["kind"], 0) + 1
    architect = {
        "defects": defects_total,
        "kits_recording": len(by_kit),
        "by_kind": by_kind,
        "by_kit": by_kit,
    }

    return {
        "verifier": verifier,
        "escalation": escalation,
        "reviewer": reviewer,
        "architect": architect,
    }, notes


def build_lineage(records, expensive_tiers):
    """Group escalation outcomes carrying ``parent=`` under their parent task, across every
    scanned kit record (graph-convergence T2 — PLAN D1 lineage; placement enforcement per
    the Phase 1 review's F2/F4 adjudication) → ``(groups, cheap_pin_counts, notes)``.

    A ``group`` is one ``(kit, parent-task-id)`` pair, in first-seen scan order:
    ``{"kit", "parent", "parent_model", "parent_tier", "children"}``. ``parent_model``/
    ``parent_tier`` are the PARENT task's raw TASKS.md pin (never shifted by re-routes — the
    same "raw pin" convention as ``history_tier_stats``'s ``pinned`` bucket); ``parent_tier``
    is ``None`` when the parent has no recognized pin. Each ``children`` entry is
    ``{"task", "model", "result", "run", "failure"}`` for one outcome that named this parent,
    in scan order; a child task may appear only once (one outcome line = one child).

    A carrying outcome is validated before it is grouped, and every rejection is dropped with
    a note — never counted (F2: no line is simultaneously a headline figure and an "ignored"
    line):

    - the outcome's OWN task id must be a known TASKS.md id (mirrors
      ``build_failure_breakdown``'s identical check, so the two functions agree on every id —
      an id unknown to one is unknown to both, never counted by either);
    - the outcome's own ``result`` must be ``escalated-pass`` — the spec restricts ``parent=``
      to escalation/consult outcomes, and ``escalated-pass`` is the only vocabulary value that
      means that (F4: an out-of-grammar placement — e.g. ``parent=`` on a plain ``pass`` —
      is dropped with a note, exactly like an unrecognized ``failure=`` class);
    - the named ``parent=`` must itself be a known TASKS.md id (never guessed at).

    A task is never its own parent (``parse_outcomes`` already drops that case, so it never
    reaches here).

    ``cheap_pin_counts`` is the per-tier "escalations descending from cheap pins" count (PLAN
    D9's routing signal): for every kept child, if the PARENT's raw pin tier is not in
    ``expensive_tiers``, that tier's count is incremented. Keys are exactly the tiers NOT in
    ``expensive_tiers`` (typically haiku/sonnet), each defaulting to 0 — present whenever
    ``groups`` is non-empty, so a tier with zero cheap-pin escalations still reads as an
    explicit 0, never a silent omission.

    A kit with no ``parent=`` anywhere returns ``([], {}, [])`` — the caller uses that
    emptiness to omit the whole ``lineage`` key from the card (T2's optionality contract).
    """
    groups = []
    group_index = {}
    cheap_tiers = [t for t in LIVE_TIER_ORDER if t not in expensive_tiers]
    cheap_pin_counts = {}
    notes = []
    for rec in records:
        tasks_by_id = {t.get("id"): t for t in rec["tasks"]}
        for tid, o in rec["outcomes"].items():
            parent = o.get("parent")
            if not parent:
                continue
            if tid not in tasks_by_id:
                notes.append(
                    f"{rec['kit']}: lineage outcome for unknown task id {tid!r} — ignored")
                continue
            if o["result"] != "escalated-pass":
                notes.append(
                    f"{rec['kit']}: outcome {tid} carries parent= on a {o['result']!r} "
                    f"outcome — out of grammar, ignored")
                continue
            if parent not in tasks_by_id:
                notes.append(
                    f"{rec['kit']}: lineage parent {parent!r} for task {tid} is not a "
                    f"known task id — ignored")
                continue
            if not cheap_pin_counts:
                cheap_pin_counts = {t: 0 for t in cheap_tiers}
            key = (rec["kit"], parent)
            if key not in group_index:
                parent_pin = tasks_by_id[parent].get("model")
                parent_tier = tier_for(parent_pin) if parent_pin else None
                group_index[key] = len(groups)
                groups.append({
                    "kit": rec["kit"],
                    "parent": parent,
                    "parent_model": parent_pin,
                    "parent_tier": parent_tier,
                    "children": [],
                })
            group = groups[group_index[key]]
            group["children"].append({
                "task": tid, "model": o.get("model"), "result": o.get("result"),
                "run": o.get("run"), "failure": o.get("failure"),
            })
            if group["parent_tier"] in cheap_pin_counts:
                cheap_pin_counts[group["parent_tier"]] += 1
    return groups, cheap_pin_counts, notes


def build_failure_breakdown(records):
    """Per-tier ``failure=`` class counts from every scanned record's outcomes
    (graph-convergence T2 — PLAN D9; corrected per the Phase 1 review's F3/F4 adjudication)
    → ``(breakdown, notes)``.

    ``breakdown`` maps tier -> ``{class: count}`` for exactly the ``LIVE_TIER_ORDER`` tiers
    that have at least one ``failure=`` event; a tier with none is omitted (not zeroed) so an
    empty ``breakdown`` (``{}``) is unambiguous with "no failure evidence at all" and the
    caller can use that to omit the whole ``failure_breakdown`` key.

    A failure class is attributed to the tier that FAILED, never the tier that resolved it
    (F3). An outcome carrying ``parent=`` is a child/consult outcome (graph-convergence T2
    lineage) rescuing another task — its own ``failure=``, if any, contributes NOTHING here,
    because the PARENT task's own outcome line already carries the authoritative failure class
    for that struggle; counting the child too would land the failure on the tier that FIXED
    the problem instead of the tier that failed it. This exclusion is silent (not a grammar
    violation — the child outcome is perfectly valid, it is simply not this aggregate's
    attribution source), so it never collides with ``build_lineage``'s counting of the very
    same outcome (F2: no line is simultaneously a headline figure and an "ignored" line).

    For an outcome WITHOUT ``parent=``, attribution mirrors ``history_tier_stats``/
    ``live_tier_stats`` (PLAN D2, reused verbatim): a ``blocked`` outcome attributes to
    ``tier_for(outcome["model"])`` — what it actually ran on; an ``escalated-pass`` outcome
    (the classic single-task escalation valve, rescued in place rather than by a separate
    consult task) attributes to the reconstructed DISPATCH tier via ``effective_alias`` (never
    to frontier, where the Fable fixer's own model= would otherwise land it). A ``failure=``
    on any OTHER result (``pass``/``retry-pass``) is out of grammar — the spec restricts
    ``failure=`` to blocked/escalated outcomes — and is dropped with a note (F4, mirroring the
    existing precedent for an unrecognized failure class). An outcome with no reconstructable
    dispatch alias, or whose tier is outside ``LIVE_TIER_ORDER``, is skipped with a note
    (mirrors the sibling tier functions). ``failure`` values are already validated to
    ``FAILURE_CLASSES`` by ``parse_outcomes``, so no further vocabulary check is needed here.
    """
    breakdown = {}
    notes = []
    for rec in records:
        tasks_by_id = {t.get("id"): t for t in rec["tasks"]}
        applied = [e for e in rec["events"] if e["mode"] == "applied"]
        for tid, o in rec["outcomes"].items():
            failure = o.get("failure")
            if not failure:
                continue
            if tid not in tasks_by_id:
                notes.append(
                    f"{rec['kit']}: failure-class outcome for unknown task id {tid!r} "
                    f"ignored")
                continue
            if o.get("parent"):
                # F3: a child/consult outcome's failure is superseded by its parent's own
                # outcome — excluded, never counted, and not reported as "ignored" (it is
                # valid data; it simply is not this aggregate's attribution source).
                continue
            result = o["result"]
            if result not in ("blocked", "escalated-pass"):
                notes.append(
                    f"{rec['kit']}: outcome {tid}: failure= on a {result!r} outcome is out "
                    f"of grammar — ignored")
                continue
            if result == "escalated-pass":
                alias = effective_alias(tasks_by_id[tid], applied)
                if alias is None:
                    notes.append(
                        f"{rec['kit']}: escalated outcome {tid}: no dispatch model to "
                        f"attribute its failure class — skipped")
                    continue
                tier = tier_for(alias)
            else:
                tier = tier_for(o["model"])
            if tier not in LIVE_TIER_ORDER:
                notes.append(
                    f"{rec['kit']}: outcome {tid}: tier {tier!r} outside the tier ladder "
                    f"— only this outcome's failure-class attribution is skipped, not the "
                    f"outcome and not its failure class: the line is still parsed and remains "
                    f"valid ledger data, the ladder just has no bucket to attribute it to")
                continue
            breakdown.setdefault(tier, {})
            breakdown[tier][failure] = breakdown[tier].get(failure, 0) + 1
    return breakdown, notes


# ------------------------------------------------------------------ envelope (U4, PLAN E3)

def envelope_call_cost(pricing, tier, profile=ENVELOPE_TASK_PROFILE):
    """USD cost of ONE modeled dispatch call at ``tier``, priced via ``cr.price`` — the SAME
    seam ``session_cost.py`` uses for real transcripts, never a reimplemented rate table.
    The token volume comes from ``pricing["task_profiles"][profile]`` (a fixed modeling
    assumption; see ``ENVELOPE_TASK_PROFILE``'s module comment), never a per-task
    measurement — there is no transcript at this granularity to measure. Returns ``None``
    (never a fabricated cost) when ``tier`` has no representative model in ``pricing`` or
    ``profile`` is not a known task profile.
    """
    model_key = _first_model_of_tier(pricing, tier)
    prof = pricing.get("task_profiles", {}).get(profile)
    if model_key is None or prof is None:
        return None
    usage = {"input": prof["input_tokens"], "output": prof["output_tokens"],
              "cache_read": 0, "cache_write": 0}
    return cr.price(model_key, usage, None, pricing)


def derive_envelope_classes(records):
    """Derive ``(origin_tier, failure_class)`` task classes from outcome-level ``failure=``
    evidence (PLAN E3's tripwire, corrected by this kit's NOTES.md "PLAN E3's premise is
    false" finding: real history carries zero such outcomes, so this path is exercised only
    by synthetic fixtures on any real invocation) → ``(classes, notes)``.

    Filtering/attribution mirrors ``build_failure_breakdown`` EXACTLY (same known-task-id,
    ``parent=``-exclusion, ``result in (blocked, escalated-pass)``, and dispatch-tier-via-
    ``effective_alias`` rules) so the two functions never disagree about which outcomes
    carry a class — but this one keeps PER-MEMBER resolution detail
    (``resolved``/``resolved_tier``) that ``build_failure_breakdown``'s counts-only output
    discards, because pricing a ladder-walk vs a cascade needs to know not just THAT a tier
    failed but WHICH tier (if any) resolved each member. A ``blocked`` member is unresolved
    (``resolved_tier`` ``None`` — its own outcome line never carries a passing verdict,
    regardless of any lineage child that may have rescued the SITUATION; that child's own
    outcome is separate ledger data, not a retroactive edit to this one — same convention
    ``build_failure_breakdown``/``build_lineage`` already keep). An ``escalated-pass``
    member is resolved AT ``tier_for(o["model"])`` — the fixer named on that SAME outcome
    line, not a lineage lookup. ``classes`` maps ``(origin_tier, failure)`` to a list of
    ``{"kit", "task", "resolved", "resolved_tier"}`` member dicts, in scan order.
    """
    classes = {}
    notes = []
    for rec in records:
        tasks_by_id = {t.get("id"): t for t in rec["tasks"]}
        applied = [e for e in rec["events"] if e["mode"] == "applied"]
        for tid, o in rec["outcomes"].items():
            failure = o.get("failure")
            if not failure:
                continue
            if tid not in tasks_by_id:
                notes.append(
                    f"{rec['kit']}: envelope outcome for unknown task id {tid!r} ignored")
                continue
            if o.get("parent"):
                # Child/consult outcome — the PARENT's own line is the authoritative
                # failure-class record (mirrors build_failure_breakdown's F3 exclusion).
                continue
            result = o["result"]
            if result not in ("blocked", "escalated-pass"):
                notes.append(
                    f"{rec['kit']}: outcome {tid}: failure= on a {result!r} outcome is out "
                    f"of grammar — ignored")
                continue
            if result == "escalated-pass":
                alias = effective_alias(tasks_by_id[tid], applied)
                if alias is None:
                    notes.append(
                        f"{rec['kit']}: escalated outcome {tid}: no dispatch model to "
                        f"attribute — skipped")
                    continue
                origin_tier = tier_for(alias)
                resolved, resolved_tier = True, tier_for(o["model"])
            else:
                origin_tier = tier_for(o["model"])
                resolved, resolved_tier = False, None
            if origin_tier not in LIVE_TIER_ORDER:
                notes.append(
                    f"{rec['kit']}: outcome {tid}: origin tier {origin_tier!r} outside the "
                    f"tier ladder — skipped")
                continue
            if resolved and resolved_tier not in LIVE_TIER_ORDER:
                notes.append(
                    f"{rec['kit']}: outcome {tid}: resolved tier {resolved_tier!r} outside "
                    f"the tier ladder — treated as unresolved for envelope pricing")
                resolved, resolved_tier = False, None
            elif resolved and (LIVE_TIER_ORDER.index(resolved_tier)
                               < LIVE_TIER_ORDER.index(origin_tier)):
                # An escalated-pass whose fixer sits BELOW its own dispatch tier is out of
                # grammar the same way the shapes above are: the escalation ladder only ever
                # walks upward, so this member has no rung on its own class's ladder to be
                # resolved at. Note and treat as unresolved (never a crash: the downstream
                # ladder-position lookup in price_envelope_class has no index for it).
                notes.append(
                    f"{rec['kit']}: outcome {tid}: resolved tier {resolved_tier!r} is BELOW "
                    f"its origin tier {origin_tier!r} — the ladder never walks downward, so "
                    f"this is treated as unresolved for envelope pricing")
                resolved, resolved_tier = False, None
            classes.setdefault((origin_tier, failure), []).append({
                "kit": rec["kit"], "task": tid,
                "resolved": resolved, "resolved_tier": resolved_tier,
            })
    return classes, notes


def price_envelope_class(origin_tier, failure, members, pricing):
    """Price ONE derived class's OBSERVED ladder-walk cost against its BEST two-model
    cascade, both from ``envelope_call_cost`` (so both sides share the exact same per-tier
    $ — a fair comparison) → ``(row_or_None, note_or_None)``.

    The observed ladder pays for every rung actually walked: ``origin_tier`` for every
    member, plus one call per intermediate rung up to (and including) whichever rung
    resolved it, or all the way to the ladder's top rung for an unresolved (``blocked``)
    member — the same "walk one rung at a time" behavior the real escalation ladder
    performs. A member whose ``resolved_tier`` IS its ``origin_tier`` (an ``escalated-pass``
    whose fixer model sits in the same tier as the dispatch model) never left the first rung:
    it costs exactly one call, counts as resolved AT ``origin_tier`` in
    ``per_tier_resolution``, and is excluded from ``remaining`` for every rung above — so
    the table's per-rung resolutions always sum to the row's ``resolved`` count and no
    higher rung's conditional rate is computed over an inflated denominator.
    ``derive_envelope_classes`` guarantees ``resolved_tier`` is never BELOW ``origin_tier``
    (it notes and downgrades that shape to unresolved), so every resolving tier has a
    position on this class's ladder.

    The cascade is exactly TWO rungs: ``origin_tier`` (unchanged — the same starting point
    the real ledger used) plus ONE second tier ``B``, chosen as the CHEAPEST candidate that
    still resolves every member the observed ladder resolved above ``origin_tier`` (``B``
    must be at or above the highest such resolving tier — a lower ``B`` would fail a task the
    real ladder succeeded at, which would be a quality change disguised as a cost comparison,
    exactly the fabricated-finding shape this kit exists to prevent). Only members that
    actually needed a second rung are billed for one: a member that resolved AT
    ``origin_tier`` pays a single call under the cascade exactly as it did under the ladder
    (billing it a second hop would invent a call history never records). A member that
    escalated walks ``origin_tier`` + ``B`` regardless of which tier actually resolved it in
    history (the cascade has no intermediate rung to try first); a ``blocked`` member costs
    ``origin_tier`` + ``B`` too (it still tries the best available second tier and still
    fails — the same "walked the ladder and still failed" shape, priced at only two calls
    instead of every rung). When NO member ever left ``origin_tier`` the cascade's second
    rung never fires at all: ``cascade_second_tier`` is ``None`` and the two sides tie.

    ``row_or_None`` carries ``per_tier_resolution`` — for EVERY rung from ``origin_tier``
    up, how many members were still unresolved on REACHING it and what fraction resolved AT
    it (``None`` when nothing reaches it) — the per-class per-tier resolution rate PLAN E3
    asks for, independent of the cost comparison. Returns ``(None, note)`` — never a
    fabricated price — when any rung in this class's ladder has no priceable representative
    model.
    """
    oi = LIVE_TIER_ORDER.index(origin_tier)
    ladder = LIVE_TIER_ORDER[oi:]
    call_cost = {t: envelope_call_cost(pricing, t) for t in ladder}
    if any(c is None for c in call_cost.values()):
        return None, (f"class {origin_tier}×{failure}: a tier's call cost could not be "
                       f"priced from pricing.json — class skipped")

    needed_idx = [ladder.index(m["resolved_tier"]) if m["resolved"] else None
                  for m in members]

    observed_total = 0.0
    for idx in needed_idx:
        observed_total += call_cost[origin_tier]
        top = idx if idx is not None else len(ladder) - 1
        for j in range(1, top + 1):
            observed_total += call_cost[ladder[j]]

    resolved_at = {t: 0 for t in ladder}
    for idx in needed_idx:
        if idx is not None:
            resolved_at[ladder[idx]] += 1

    # Every rung — INCLUDING origin — is counted the same way: resolutions AT it, over the
    # members still unresolved on reaching it. origin is not special-cased to zero, so a
    # member that resolved at its origin tier appears in the table (matching the row's
    # ``resolved`` count) and leaves ``remaining`` before the next rung's rate is computed.
    per_tier_resolution = {}
    remaining = len(members)
    for t in ladder:
        reaching = remaining
        resolved_here = resolved_at[t]
        per_tier_resolution[t] = {
            "reaching": reaching, "resolved": resolved_here,
            "rate": (resolved_here / reaching) if reaching else None,
        }
        remaining -= resolved_here

    # Members that never left origin (idx 0) need no second rung; ``None`` (blocked) and any
    # idx above 0 do. ``None != 0`` is True, which is exactly the membership wanted here.
    escalating = [i for i in needed_idx if i != 0]
    if len(ladder) == 1 or not escalating:
        cascade_total = observed_total
        cascade_second_tier = None
    else:
        resolved_needed = [i for i in escalating if i is not None]
        min_b = max(max(resolved_needed) if resolved_needed else 1, 1)
        best_b, best_total = None, None
        for b in range(min_b, len(ladder)):
            total = (len(members) * call_cost[origin_tier]
                     + len(escalating) * call_cost[ladder[b]])
            if best_total is None or total < best_total:
                best_total, best_b = total, b
        cascade_total = best_total
        cascade_second_tier = ladder[best_b]

    return {
        "origin_tier": origin_tier,
        "failure": failure,
        "n": len(members),
        "resolved": sum(1 for m in members if m["resolved"]),
        "blocked": sum(1 for m in members if not m["resolved"]),
        "per_tier_resolution": per_tier_resolution,
        "observed_ladder_usd": observed_total,
        "cascade_usd": cascade_total,
        "cascade_second_tier": cascade_second_tier,
        "savings_usd": observed_total - cascade_total,
    }, None


def build_envelope(kits_dir, records, evidence, pricing, scan_notes):
    """Assemble the U4 envelope card from scanned records + the evidence-base headline
    (PLAN E3, output shape corrected by NOTES.md — see ``derive_envelope_classes``).

    Zero classes (every real invocation today, per NOTES.md's measured finding) is NOT
    rendered as a whole-history fallback row: with ``outcomes_with_failure`` at zero AND
    ``sessions_priced`` thin, any single number here would be exactly the fabricated-finding
    shape this kit exists to prevent, so ``card["classes"]`` stays ``[]`` and the renderer's
    Verdict section names the evidence base and declines instead.
    """
    classes_raw, class_notes = derive_envelope_classes(records)
    notes = list(scan_notes) + list(class_notes)
    rows = []
    for (origin_tier, failure), members in classes_raw.items():
        row, note = price_envelope_class(origin_tier, failure, members, pricing)
        if note:
            notes.append(note)
            continue
        rows.append(row)
    rows.sort(key=lambda r: (LIVE_TIER_ORDER.index(r["origin_tier"]), r["failure"]))

    return {
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kits_dir": str(kits_dir),
        "evidence": evidence,
        "classes": rows,
        "notes": notes,
    }


def render_envelope_markdown(card):
    """Render the U4 envelope card as human markdown: an Evidence base section (always
    rendered — PLAN E4, "name the evidence base"), then either a declining Verdict (zero
    classes) or the per-class ladder-vs-cascade table + per-tier resolution rates.
    """
    ev = card["evidence"]
    classes = card["classes"]
    out = ["# Cascade envelope — ladder vs. two-model counterfactual\n"]

    out.append("## Evidence base\n")
    # "tasks with an outcome", NOT "outcome lines": ``rec["outcomes"]`` is keyed by task id
    # with last-wins, so a task whose ledger carries several outcome lines (a retry after a
    # review, say) contributes exactly one. The numerator below is counted over the same
    # deduped mapping, so the two are directly comparable — which they would not be if this
    # counted raw lines.
    out.append(f"- tasks with an outcome: {ev['tasks_with_outcome']}")
    out.append(f"- carrying failure=: {ev['outcomes_with_failure']}")
    out.append(f"- kits scanned: {ev['kits_total']}")
    out.append(f"- kits with a session: line: {ev['kits_with_session_line']}")
    out.append(f"- sessions priced: {ev['sessions_priced']}/{ev['sessions_found']} found")
    out.append("")

    out.append("## Verdict\n")
    if not classes:
        out.append(
            f"**Unanswerable from this repo's history today.** Task classes need "
            f"`failure=` evidence (legal only on `blocked`/`escalated-pass` outcomes); "
            f"{ev['outcomes_with_failure']}/{ev['tasks_with_outcome']} outcomes carry it, "
            f"so no class exists to price — and this is deliberately NOT rendered as a "
            f"whole-history fallback row: pricing {ev['sessions_priced']}/"
            f"{ev['sessions_found']} sessions across {ev['kits_with_session_line']}/"
            f"{ev['kits_total']} kits is too thin to trust a single number either. The "
            f"ladder-vs-cascade question needs the ledger to accumulate blocked/escalated "
            f"outcomes (and more `session:` coverage) before it can be asked honestly — see "
            f"PLAN E3's premise-is-false finding.")
        out.append("")
    else:
        out.append(
            f"**{len(classes)} task class(es) derived from `failure=` evidence "
            f"({ev['outcomes_with_failure']}/{ev['tasks_with_outcome']} outcomes).** Every "
            f"dollar figure below is `est.` — modeled from pricing.json's task_profile "
            f"{ENVELOPE_TASK_PROFILE!r} (no per-task transcript exists at this granularity "
            f"to measure), never a real session's tokens.")
        out.append("")
        out.append("## Per-class ladder vs. cascade (est.)\n")
        out.append("| Class (origin × failure) | N | Resolved | Blocked "
                   "| Observed ladder $ | Best cascade $ | Cascade 2nd tier | Savings $ |")
        out.append("|---|---:|---:|---:|---:|---:|---|---:|")
        for c in classes:
            # No second tier has two distinct honest causes — say which one, never a
            # tier name a cascade would not actually have dispatched.
            second = c["cascade_second_tier"] or (
                "n/a (top of ladder)" if c["origin_tier"] == LIVE_TIER_ORDER[-1]
                else "n/a (no member escalated)")
            out.append(
                f"| {c['origin_tier']} × {c['failure']} | {c['n']} | {c['resolved']} "
                f"| {c['blocked']} | ${c['observed_ladder_usd']:,.4f} "
                f"| ${c['cascade_usd']:,.4f} | {second} | ${c['savings_usd']:,.4f} |")
        out.append("")
        out.append("## Per-tier resolution rate\n")
        for c in classes:
            out.append(f"- {c['origin_tier']} × {c['failure']}:")
            for t, s in c["per_tier_resolution"].items():
                out.append(f"  - {t}: {s['resolved']}/{s['reaching']} "
                           f"({_rate_pct(s['rate'])})")
        out.append("")

    if card["notes"]:
        out.append("Notes:")
        for n in card["notes"]:
            out.append(f"- {n}")

    return "\n".join(out)


def run_envelope(args):
    """The ``--history --envelope`` flow (PLAN E3; output shape corrected by this kit's
    NOTES.md "PLAN E3's premise is false" finding). READ-ONLY, writes nothing, exit 0
    always — a missing kits dir exits with the same message ``run_history`` uses for one.
    """
    kits_dir = Path(args.kits_dir[0])
    if not kits_dir.is_dir():
        sys.exit(f"kits dir not found: {kits_dir}")
    records, scan_notes = scan_kits(kits_dir)
    scan_notes = list(scan_notes)
    if not records:
        scan_notes.append(f"no kits with a TASKS.md found under {kits_dir}")

    # Session-pricing coverage for the Evidence base headline only (E4's "how many sessions
    # priced out of how many kits"). Reuses sc.find_main_transcript — the SAME resolution
    # step kit_cost_summary uses to decide "priced" — but never walks a transcript's tokens
    # or loads pricing for it: the class $ figures are modeled from pricing.json's
    # task_profiles, never from a real session's tokens, so no dollar ladder runs here.
    union_ids, seen_ids = [], set()
    for rec in records:
        for sid in rec["sessions"]:
            if sid not in seen_ids:
                seen_ids.add(sid)
                union_ids.append(sid)
    sessions_priced = sum(
        1 for sid in union_ids
        if sc.find_main_transcript(sid, args.projects_dir) is not None)

    # ``rec["outcomes"]`` is keyed by task id (last outcome line wins), so both counts below
    # are per-TASK, not per-LINE — a task with a retry outcome after a review contributes one
    # to each. The key is named for what it counts; a raw line count would make the ratio the
    # renderer prints incomparable with its own numerator.
    evidence = {
        "tasks_with_outcome": sum(len(rec["outcomes"]) for rec in records),
        "outcomes_with_failure": sum(
            1 for rec in records for o in rec["outcomes"].values() if o.get("failure")),
        "kits_total": len(records),
        "kits_with_session_line": sum(1 for rec in records if rec["sessions"]),
        "sessions_found": len(union_ids),
        "sessions_priced": sessions_priced,
    }

    pricing = cr.load_pricing()
    card = build_envelope(kits_dir, records, evidence, pricing, scan_notes)
    print(json.dumps(card, indent=2) if args.json else render_envelope_markdown(card))
    return 0


def build_history(kits_dir, records, kit_costs, dollars, notes, expensive_tiers=None):
    """Assemble the pinned D7 history card from scanned records + priced kit costs.

    Top-level keys EXACTLY: ``schema_version``, ``generated_at``, ``kits_dir``, ``kits``,
    ``tiers``, ``reroutes`` (``{events, applied, advisory}`` totals), ``roles`` (D1/D6 —
    ``role_quality_stats(records)``; the schema v2 additive key), ``dollars`` (dict or None),
    ``notes``, PLUS two T2 keys added ONLY when their evidence exists: ``lineage`` (present
    iff any outcome anywhere carries ``parent=``) and ``failure_breakdown`` (present iff any
    outcome anywhere carries ``failure=``). A kit scanned with neither field returns a card
    with the same eight keys as before T2 — byte-identical, per the kit's own optionality
    contract. Per-kit ``history_tier_stats`` sums are merged into ``tiers`` (rates
    recomputed over the MERGED denominators, ``None`` on zero) with ``tally_reroutes``'
    per-tier counts under each tier's ``"reroutes"`` key. The applied events fed to
    ``history_tier_stats`` for a kit are that kit's OWN applied events only. Each ``kits``
    row: ``{"kit", "tasks" (count), "with_outcome", "first_try_pass", "retry_pass",
    "escalated_pass", "blocked", "sessions" (id list), "cost"}``. ``role_quality_stats``'s
    own notes are folded into the returned ``notes`` exactly like every other sub-aggregate.

    ``expensive_tiers`` (T2, optional keyword — the positional signature above it is FROZEN,
    called positionally by ``bin/bench_routing.py``) defaults to ``cr.EXPENSIVE_TIERS`` when
    omitted or ``None``, matching every other caller's convention in this file.
    """
    if expensive_tiers is None:
        expensive_tiers = cr.EXPENSIVE_TIERS
    agg = {tier: {"pinned": 0, "with_outcome": 0, "first_try": 0, "retry_pass": 0,
                  "escalated_pass": 0, "blocked": 0}
           for tier in LIVE_TIER_ORDER}
    all_events = []
    kit_rows = []
    extra_notes = []
    for rec in records:
        applied = [e for e in rec["events"] if e["mode"] == "applied"]
        stats, st_notes = history_tier_stats(rec["tasks"], rec["outcomes"], applied)
        for n in st_notes:
            extra_notes.append(f"{rec['kit']}: {n}")
        all_events.extend(rec["events"])

        row = {"with_outcome": 0, "first_try_pass": 0, "retry_pass": 0,
               "escalated_pass": 0, "blocked": 0}
        for tier in LIVE_TIER_ORDER:
            s = stats[tier]
            for k in ("pinned", "with_outcome", "first_try", "retry_pass",
                      "escalated_pass", "blocked"):
                agg[tier][k] += s[k]
            row["with_outcome"] += s["with_outcome"]
            row["first_try_pass"] += s["first_try"]
            row["retry_pass"] += s["retry_pass"]
            row["escalated_pass"] += s["escalated_pass"]
            row["blocked"] += s["blocked"]
        kit_rows.append({
            "kit": rec["kit"],
            "tasks": len(rec["tasks"]),
            "with_outcome": row["with_outcome"],
            "first_try_pass": row["first_try_pass"],
            "retry_pass": row["retry_pass"],
            "escalated_pass": row["escalated_pass"],
            "blocked": row["blocked"],
            "sessions": list(rec["sessions"]),
            "cost": (kit_costs.get(rec["kit"]) if kit_costs else None),
        })

    role_stats, role_notes = role_quality_stats(records)
    extra_notes.extend(role_notes)

    lineage_groups, cheap_pin_counts, lineage_notes = build_lineage(records, expensive_tiers)
    extra_notes.extend(lineage_notes)

    failure_stats, failure_notes = build_failure_breakdown(records)
    extra_notes.extend(failure_notes)

    reroute_tally = tally_reroutes(all_events)
    tiers = {}
    for tier in LIVE_TIER_ORDER:
        a = agg[tier]
        wo = a["with_outcome"]
        tiers[tier] = {
            "pinned": a["pinned"],
            "with_outcome": wo,
            "first_try": a["first_try"],
            "retry_pass": a["retry_pass"],
            "escalated_pass": a["escalated_pass"],
            "blocked": a["blocked"],
            "first_try_rate": (a["first_try"] / wo) if wo else None,
            "escalation_rate": (a["escalated_pass"] / wo) if wo else None,
            "reroutes": reroute_tally["by_tier"][tier],
        }

    card = {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kits_dir": str(kits_dir),
        "kits": kit_rows,
        "tiers": tiers,
        "reroutes": {"events": reroute_tally["events"],
                     "applied": reroute_tally["applied"],
                     "advisory": reroute_tally["advisory"]},
        "roles": role_stats,
        "dollars": dollars,
        "notes": list(notes) + extra_notes,
    }
    if lineage_groups:
        card["lineage"] = {"groups": lineage_groups,
                           "escalations_from_cheap_pins": cheap_pin_counts}
    if failure_stats:
        card["failure_breakdown"] = failure_stats
    return card


def render_history_markdown(card):
    """Render the history card as human markdown: H1 + the six pinned H2s in order (D6/D7
    adds ``## Role quality`` between ``## Per-tier track record`` and ``## Re-route
    history``, ALWAYS rendered — zero evidence is an explicit line, never a silent
    omission).

    T2 adds two FULLY OPTIONAL sections, ``## Escalation lineage`` and ``## Failure
    breakdown``, both inserted between ``## Re-route history`` and ``## Kits``. Unlike Role
    quality, these are OMITTED WHOLE (no heading at all) when ``card`` carries no
    ``"lineage"``/``"failure_breakdown"`` key — a card built before T2, or a T2-built card
    from a kit with neither field, renders byte-identically to before T2.
    """
    tiers = card["tiers"]
    kits = card["kits"]
    dollars = card["dollars"]
    out = ["# Routing history — cross-kit per-tier track record\n"]

    # Verdict — one bold summary line.
    overall_first = sum(tiers[t]["first_try"] for t in LIVE_TIER_ORDER)
    overall_wo = sum(tiers[t]["with_outcome"] for t in LIVE_TIER_ORDER)
    seg_first = (f"{overall_first}/{overall_wo} first-try"
                 if overall_wo else "first-try n/a (no outcome ledgers)")
    if dollars:
        cf = dollars["counterfactual_model"]
        seg_cost = (f"${dollars['actual_usd']:,.2f} actual vs "
                    f"${dollars['counterfactual_usd']:,.2f} all-{cf['display']} "
                    f"over {dollars['kits_with_sessions']}/{dollars['kits_total']} kits "
                    f"({dollars['coverage']})")
    else:
        seg_cost = "dollars n/a (no session: lines)"
    out.append("## Verdict\n")
    out.append(f"**{len(kits)} kits · {seg_first} · {seg_cost}**\n")

    # Cross-repo scan list (only when --kits-dir was repeated / labeled; old single-dir cards
    # never carry the key, so every existing output stays byte-identical).
    if card.get("kits_dirs"):
        for e in card["kits_dirs"]:
            out.append(f"- scanned {e['label']}: {e['path']}")
        out.append("")

    # Per-tier track record.
    out.append("## Per-tier track record\n")
    out.append("| Tier | Pinned | With outcome | First-try | Retry | Escalated | Blocked "
               "| First-try rate | Escalation rate |")
    out.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for tier in LIVE_TIER_ORDER:
        s = tiers[tier]
        out.append(f"| {tier} | {s['pinned']} | {s['with_outcome']} | {s['first_try']} "
                   f"| {s['retry_pass']} | {s['escalated_pass']} | {s['blocked']} "
                   f"| {_rate_pct(s['first_try_rate'])} | {_rate_pct(s['escalation_rate'])} |")
    out.append("")

    # Role quality (D6/D7) — ALWAYS rendered, zero evidence is an explicit line.
    out.append("## Role quality\n")
    roles = card["roles"]
    v, rv, esc, arch = (roles["verifier"], roles["reviewer"], roles["escalation"],
                        roles["architect"])
    no_evidence = (v["events"] == 0 and rv["events"] == 0 and esc["events"] == 0
                   and arch["defects"] == 0)
    if no_evidence:
        out.append("no role-quality evidence recorded — verifier, reviewer, escalation, "
                   "and architect quality not yet measurable (implementer-only history).")
    else:
        out.append("Implementer quality: see the per-tier track record above "
                   "(outcome ledger).\n")
        out.append("| Role | Events | With precision | Findings | Confirmed | Precision "
                   "| Accepted | Revised | Blocked | Unrecorded |")
        out.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        out.append(f"| verifier | {v['events']} | {v['with_precision']} | {v['findings']} "
                   f"| {v['confirmed']} | {_rate_pct(v['precision'])} "
                   f"| {v['results']['accepted']} | {v['results']['revised']} "
                   f"| {v['results']['blocked']} | {v['results']['unrecorded']} |")
        out.append(f"| reviewer | {rv['events']} | {rv['events']} | {rv['findings']} "
                   f"| {rv['confirmed']} | {_rate_pct(rv['precision'])} "
                   f"| {rv['results']['accepted']} | {rv['results']['revised']} "
                   f"| {rv['results']['blocked']} | {rv['results']['unrecorded']} |")
        out.append(f"| escalation | {esc['events']} | n/a | n/a | n/a | n/a "
                   f"| {esc['results']['accepted']} | {esc['results']['revised']} "
                   f"| {esc['results']['blocked']} | {esc['results']['unrecorded']} |")
        out.append("")

        for role_label, role_stats in (("verifier", v), ("reviewer", rv)):
            for tier in LIVE_TIER_ORDER:
                bt = role_stats["by_tier"][tier]
                if bt["events"] == 0:
                    continue
                if bt["with_precision"] == 0:
                    # "ran, nothing recorded" -- never rendered as a bare findings 0
                    # (F4: that reads identically to "genuinely found zero").
                    out.append(f"- {role_label} {tier}: {bt['events']} event(s), "
                               f"0 with recorded precision — not measured")
                else:
                    out.append(f"- {role_label} {tier}: {bt['events']} event(s), "
                               f"{bt['with_precision']} with recorded precision, "
                               f"findings {bt['findings']}, confirmed {bt['confirmed']}, "
                               f"precision {_rate_pct(bt['precision'])}")
            # Off-ladder/unrecorded-model events land in this role's top-level findings
            # but no by_tier bucket (attribution is PLAN-pinned, not to be changed) — when
            # that leaves a nonzero gap, disclose it explicitly rather than let the tier
            # lines silently under-sum the top-level total.
            tier_findings_sum = sum(role_stats["by_tier"][t]["findings"]
                                     for t in LIVE_TIER_ORDER)
            gap = role_stats["findings"] - tier_findings_sum
            if gap:
                out.append(f"- ({gap} finding(s) from off-ladder or unrecorded models are "
                           f"counted above but attributed to no tier)")

        out.append(f"- Architect: {arch['defects']} brief defects across "
                   f"{arch['kits_recording']} kits (floor — kits run before role-ledger "
                   f"adoption record none)")
        if arch["defects"]:
            kinds = ", ".join(f"{k} {n}" for k, n in sorted(arch["by_kind"].items()))
            out.append(f"  - kinds: {kinds}")
    out.append("")

    # Re-route history.
    out.append("## Re-route history\n")
    rr = card["reroutes"]
    if rr["events"] == 0:
        out.append("no re-route events recorded")
    else:
        out.append(f"- Events: {rr['events']} "
                   f"({rr['applied']} applied, {rr['advisory']} advisory)")
        for tier in LIVE_TIER_ORDER:
            rt = tiers[tier]["reroutes"]
            if any(rt.values()):
                out.append(f"- {tier}: applied_from {rt['applied_from']}, "
                           f"applied_to {rt['applied_to']}, "
                           f"advisory_from {rt['advisory_from']}, "
                           f"advisory_to {rt['advisory_to']}")
    out.append("")

    # Escalation lineage (T2) — omitted WHOLE when no outcome anywhere carries parent=.
    lineage = card.get("lineage")
    if lineage:
        out.append("## Escalation lineage\n")
        cheap = lineage["escalations_from_cheap_pins"]
        cheap_line = ", ".join(f"{tier} {n}" for tier, n in cheap.items())
        out.append(f"- escalations descending from cheap pins: {cheap_line}")
        for g in lineage["groups"]:
            parent_label = g["parent_tier"] or "unspecified"
            out.append(f"- {g['kit']}/{g['parent']} (pinned {parent_label}):")
            for c in g["children"]:
                bits = [f"{c['task']} {c['result'] or '—'}"]
                if c.get("model"):
                    bits.append(f"model={c['model']}")
                if c.get("run"):
                    bits.append(f"run={c['run']}")
                if c.get("failure"):
                    bits.append(f"failure={c['failure']}")
                out.append(f"  - {' '.join(bits)}")
        out.append("")

    # Failure-class breakdown (T2) — omitted WHOLE when no outcome anywhere carries failure=.
    failure_breakdown = card.get("failure_breakdown")
    if failure_breakdown:
        out.append("## Failure breakdown\n")
        out.append("| Tier | " + " | ".join(FAILURE_CLASSES) + " |")
        out.append("|---|" + "---:|" * len(FAILURE_CLASSES))
        for tier in LIVE_TIER_ORDER:
            counts = failure_breakdown.get(tier)
            if not counts:
                continue
            cells = " | ".join(str(counts.get(c, 0)) for c in FAILURE_CLASSES)
            out.append(f"| {tier} | {cells} |")
        out.append("")
        # T11 / Phase 1 F5-P1: this table shipped with no caption while its neighbours
        # (Review survival's italic gloss; Role quality's explicit zero-evidence line)
        # both carry one — nothing told a reader that "Tier" here is the IMPLEMENTER's
        # dispatch tier. Written from build_failure_breakdown's own docstring, not from
        # a plausible-sounding paraphrase (Phase 2's F-C was exactly this sentence
        # written wrong, in the architect skill instead of the renderer).
        out.append(
            "*Tier = the IMPLEMENTER's dispatch tier — never the raw TASKS.md pin, "
            "never the tier that rescued it: a `blocked` outcome attributes to the "
            "model it actually ran on, an `escalated-pass` to the reconstructed "
            "dispatch tier (never frontier, where the Fable fixer's own model= would "
            "otherwise land it), and an outcome carrying `parent=` contributes nothing "
            "here (its parent's own line already carries the class). A tier failing "
            "mostly on `verification` argues for a stronger VERIFIER pin, not a "
            "stronger implementer pin (PLAN D9).*\n")

    # Kits.
    out.append("## Kits\n")
    out.append("| Kit | Tasks | With outcome | First-try | Sessions | Actual $ |")
    out.append("|---|---:|---:|---:|---:|---:|")
    for k in kits:
        cost = k["cost"]
        actual = f"${cost['actual_usd']:,.2f}" if cost else "n/a"
        out.append(f"| {k['kit']} | {k['tasks']} | {k['with_outcome']} "
                   f"| {k['first_try_pass']} | {len(k['sessions'])} | {actual} |")
    out.append("")

    # Dollars.
    out.append("## Dollars\n")
    if dollars is None:
        out.append("n/a — no `session:` lines recorded in any kit's NOTES.md "
                   "(quality-only history).")
    else:
        cf = dollars["counterfactual_model"]
        ratio = f"{dollars['ratio']:.2f}×" if dollars["ratio"] else "n/a"
        out.append(f"- Actual (mixed workflow): ${dollars['actual_usd']:,.2f}")
        out.append(f"- All-{cf['display']}: ${dollars['counterfactual_usd']:,.2f}")
        out.append(f"- Δ saved vs all-{cf['display']}: ${dollars['delta_usd']:,.2f}")
        out.append(f"- Ratio: {ratio}")
        out.append(f"- Sessions priced: {dollars['sessions_priced']}/"
                   f"{dollars['sessions_found']}")
        out.append(f"- Coverage: over {dollars['kits_with_sessions']}/"
                   f"{dollars['kits_total']} kits ({dollars['coverage']})")
        out.append(f"- Prices cached {dollars['pricing_cached']}")

    if card["notes"]:
        out.append("\nNotes:")
        for n in card["notes"]:
            out.append(f"- {n}")

    return "\n".join(out)


def run_history_demo(as_json):
    """Build a synthetic multi-kit root + a synthetic projects dir in ONE temp dir and run
    the normal ``--history`` path against them via ``main`` (the ``run_live_demo`` pattern;
    ``--no-subagents`` keeps it hermetic). Exit 0.

    The demo transcript's model IDS are computed from data/pricing.json at run time (never
    hardcoded); only the token VOLUMES (reused ``DEMO_VOLUMES``) are pinned. This is the
    sanctioned history smoke test.
    """
    pricing = cr.load_pricing()
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        kits = tmp / "kits"

        alpha = kits / "hist-alpha"
        alpha.mkdir(parents=True)
        (alpha / "TASKS.md").write_text(DEMO_HIST_ALPHA_TASKS_MD)
        (alpha / "NOTES.md").write_text(DEMO_HIST_ALPHA_NOTES_MD)

        beta = kits / "hist-beta"
        beta.mkdir(parents=True)
        (beta / "TASKS.md").write_text(DEMO_HIST_BETA_TASKS_MD)
        (beta / "NOTES.md").write_text(DEMO_HIST_BETA_NOTES_MD)

        gamma = kits / "hist-gamma"
        gamma.mkdir(parents=True)
        (gamma / "TASKS.md").write_text(DEMO_HIST_GAMMA_TASKS_MD)  # no NOTES.md by design

        nak = kits / "not-a-kit"
        nak.mkdir(parents=True)
        (nak / "README.md").write_text("a stray subdir with no TASKS.md\n")

        proj = tmp / "projects" / "-demo"
        proj.mkdir(parents=True)
        ts = "2026-07-01T12:00:00+00:00"
        lines = []
        for tier in ("haiku", "sonnet", "opus", "frontier"):
            model_id = _first_model_of_tier(pricing, tier)
            if model_id is None:
                continue
            inp, outp = DEMO_VOLUMES[tier]
            lines.append(json.dumps({
                "timestamp": ts,
                "message": {
                    "model": model_id,
                    "id": f"demo-hist-{tier}",
                    "usage": {"input_tokens": inp, "output_tokens": outp},
                },
            }))
        (proj / "hist-alpha-session.jsonl").write_text("\n".join(lines) + "\n")

        argv = ["--history", "--kits-dir", str(kits),
                "--projects-dir", str(tmp / "projects"), "--no-subagents"]
        if as_json:
            argv.append("--json")
        return main(argv)


def run_envelope_demo(as_json):
    """Synthetic two-kit demo proving BOTH cascade directions the U4 acceptance criterion
    names: one class where the two-model cascade is cheaper (escalation rarely resolves at
    the middle rung, so the ladder wastes money walking it) and one where the ladder is
    cheaper (the vice versa — escalation mostly resolves at the middle rung, so a cascade
    forced up to frontier by a single outlier overpays for everyone else). No real data;
    ``--no-subagents`` and an empty ``--projects-dir`` keep it hermetic (no session: lines
    in either fixture, so no transcript is even looked for). Exit 0.
    """
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        kits = tmp / "kits"

        rare = kits / "env-rare"
        rare.mkdir(parents=True)
        (rare / "TASKS.md").write_text(DEMO_ENVELOPE_RARE_TASKS_MD)
        (rare / "NOTES.md").write_text(DEMO_ENVELOPE_RARE_NOTES_MD)

        often = kits / "env-often"
        often.mkdir(parents=True)
        (often / "TASKS.md").write_text(DEMO_ENVELOPE_OFTEN_TASKS_MD)
        (often / "NOTES.md").write_text(DEMO_ENVELOPE_OFTEN_NOTES_MD)

        proj = tmp / "projects"
        proj.mkdir(parents=True)

        argv = ["--history", "--envelope", "--kits-dir", str(kits),
                "--projects-dir", str(proj), "--no-subagents"]
        if as_json:
            argv.append("--json")
        return main(argv)


# --------------------------------------------------------------------------- snapshot + trend

def write_trend_alarm(alarm, snapshot_dir):
    """The SECOND sanctioned writer in this script (T11, PLAN D11), alongside
    ``write_snapshot``: persists the escalation alarm's CURRENT verdict so
    ``bin/statusline.py`` can read it without ever recomputing it (the T11 pre-flight
    decision in NOTES.md — a live cross-kit baseline would parse every kit dir's whole
    NOTES.md on every prompt render, against the statusline's ~15ms budget).

    Written ONLY from ``run_trend`` when ``args.snapshot`` is True (i.e. reached via
    ``--history --snapshot --trend``) — see that function's docstring. A bare
    ``--trend`` read never calls this, and stays exactly as read-only as
    ``ReadOnlyNonSnapshotTests`` already proves.

    Lives at ``<snapshot_dir>/alarm/state.json`` — a SUBDIRECTORY, deliberately outside
    ``read_snapshots``'s own non-recursive ``glob("*.json")`` over ``snapshot_dir``
    itself, so this file can never be mistaken for a dated history snapshot and never
    trips the "rogue snapshot file skipped" tolerance note on a later ``--trend`` read.
    Latest-wins on every call, mirroring ``write_snapshot``'s same-day overwrite. Returns
    the written ``Path``.
    """
    snapshot_dir = Path(snapshot_dir)
    alarm_dir = snapshot_dir / "alarm"
    alarm_dir.mkdir(parents=True, exist_ok=True)
    path = alarm_dir / "state.json"
    path.write_text(json.dumps(alarm, indent=2) + "\n")
    return path


def write_snapshot(card, snapshot_dir, date_str=None):
    """THE FIRST sanctioned writer in the whole script (besides ``--demo``'s own temp
    dirs and T11's ``write_trend_alarm``) (PLAN D5). Writes ``card`` as
    ``json.dumps(card, indent=2) + "\\n"`` to ``<snapshot_dir>/<date>.json`` and returns
    the ``Path``.

    ``date_str`` ``None`` → UTC today (``datetime.now(timezone.utc).strftime("%Y-%m-%d")``); a
    GIVEN ``date_str`` is validated against ``^\\d{4}-\\d{2}-\\d{2}$`` FIRST and raises
    ``ValueError`` on any other shape — the path-traversal guard that makes escaping the
    snapshot dir impossible, checked before anything is created or written. The dir is then
    ``mkdir(parents=True, exist_ok=True)``; re-snapshotting the same day plainly overwrites
    that day's file (latest-wins per day — deliberate).
    """
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    elif not _SNAPSHOT_DATE_RE.match(date_str):
        raise ValueError(f"invalid snapshot date {date_str!r} — expected YYYY-MM-DD")
    snapshot_dir = Path(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{date_str}.json"
    path.write_text(json.dumps(card, indent=2) + "\n")
    return path


def read_snapshots(snapshot_dir):
    """Read every stored snapshot under ``snapshot_dir`` → ``(dated_cards, notes)`` (PLAN D7),
    tolerant of a missing dir and of malformed/rogue files — never a crash, never a guess.

    A missing dir → ``([], ["snapshot dir not found: <dir>"])``. Otherwise only ``*.json``
    files are considered, sorted by name (ISO date names sort lexicographically, so survivors
    come back ascending by date); a name failing ``SNAPSHOT_FILENAME_RE`` is skipped with a
    ``rogue snapshot file skipped: <name>`` note; an unreadable or undecodable file is skipped
    with a note naming it; decoded JSON that is not a dict, or lacks a dict ``tiers`` key, is
    skipped with a note (old/foreign-shaped files are never guessed at). Survivors are returned
    as ``(date_str, card)`` tuples, ``date_str`` being the filename stem.
    """
    snapshot_dir = Path(snapshot_dir)
    if not snapshot_dir.is_dir():
        return [], [f"snapshot dir not found: {snapshot_dir}"]

    dated_cards = []
    notes = []
    for path in sorted(snapshot_dir.glob("*.json"), key=lambda p: p.name):
        if not SNAPSHOT_FILENAME_RE.match(path.name):
            notes.append(f"rogue snapshot file skipped: {path.name}")
            continue
        try:
            text = path.read_text()
        except OSError as e:
            notes.append(f"snapshot file unreadable, skipped: {path.name} ({e})")
            continue
        try:
            card = json.loads(text)
        except json.JSONDecodeError as e:
            notes.append(f"snapshot file undecodable, skipped: {path.name} ({e})")
            continue
        if not isinstance(card, dict) or not isinstance(card.get("tiers"), dict):
            notes.append(f"snapshot file malformed (no tiers object), skipped: {path.name}")
            continue
        dated_cards.append((path.stem, card))
    return dated_cards, notes


def _kit_escalation_rate(kit_row):
    """Escalation rate for one stored ``kits`` row (PLAN D11): ``escalated_pass /
    with_outcome``, read TOLERANTLY (``.get(..., 0) or 0``, mirroring ``build_trend``'s
    own per-tier tolerance of an old/foreign-shaped card). ``None`` when ``with_outcome``
    is 0 — never a fabricated 0%, the same rule as every other rate in this file.

    This is also the P34-F1 signature from the writer side: a driver-executed kit's row
    structurally has ``with_outcome == 0`` (every driver writes a CONCRETE pricing model
    id into ``model=``, which ``tier_for`` cannot resolve, so ``history_tier_stats``
    excludes those lines from every tier's ``with_outcome`` before the kit row is ever
    summed) — such a kit is invisible HERE too, and callers must treat that as "no
    evidence", never a confident zero.
    """
    wo = kit_row.get("with_outcome") or 0
    esc = kit_row.get("escalated_pass") or 0
    return (esc / wo) if wo else None


def build_escalation_alarm(dated_cards, sigma=TREND_ALARM_SIGMA_DEFAULT):
    """The PLAN D11 escalation-rate alarm: a trailing per-kit baseline from every stored
    snapshot BEFORE the latest, checked against every kit in the LATEST snapshot — PURE,
    no I/O, no pricing (mirrors the rest of the pure ``--trend`` path).

    ``dated_cards`` is ``read_snapshots``' own ``(date_str, card)`` list, ascending by
    date (its own contract) — the same list ``build_trend`` already has in hand, so this
    never re-reads anything.

    Two INDEPENDENT floors gate evaluation, both an honest "insufficient history" degrade
    rather than a fabricated verdict, and both a MATHEMATICAL floor (2 points is the
    minimum for a population standard deviation to mean anything at all) rather than an
    arbitrary policy pick — the same species as ``build_trend``'s own "a trend needs at
    least 2 points":
      * fewer than 2 stored snapshots at all -> no "trailing vs current" split exists;
      * fewer than 2 kits with a computable escalation rate in the trailing snapshots ->
        no variance to derive a threshold from.

    The trailing baseline pools ONE rate per kit NAME: scanning every card strictly
    BEFORE the latest, in date order, a kit's rate OVERWRITES its own prior pooled value
    — so a kit that reappears unchanged across many daily snapshots contributes its most
    RECENT trailing observation once, never one pseudo-replicated sample per snapshot
    date. The threshold is NEVER a fixed percentage: it is always
    ``mean(pooled_rates) + sigma * pstdev(pooled_rates)``, recomputed from whatever the
    trailing data actually shows every time this runs (see ``TREND_ALARM_SIGMA_DEFAULT``
    for why ``sigma`` itself is not in tension with "no hardcoded thresholds").

    Every kit row in the LATEST snapshot is then checked: a rate strictly above the
    threshold is a trip; a kit with NO computable rate (P34-F1's driver-executed case) is
    reported in ``no_evidence`` and is NEVER silently folded into "no escalations" —
    "no evidence" and "0% escalation" must never render identically, the same discipline
    ``build_failure_breakdown``'s ``with_precision`` split already enforces for verifier
    findings.

    Returns a dict (always present, never partially populated):
        {"evaluated": bool, "sigma": float, "insufficient_reason": str | None,
         "baseline": {"kits": int, "mean": float | None, "stdev": float | None,
                      "threshold": float | None},
         "latest_date": str | None,
         "tripped": [{"kit", "rate", "with_outcome", "escalated_pass"}, ...],
         "no_evidence": [kit names, latest snapshot only],
         "notes": []}
    """
    if len(dated_cards) < 2:
        return {
            "evaluated": False,
            "sigma": sigma,
            "insufficient_reason": (
                "insufficient history — need at least 2 stored snapshots (a trailing "
                f"baseline vs a current reading); have {len(dated_cards)}"),
            "baseline": {"kits": 0, "mean": None, "stdev": None, "threshold": None},
            "latest_date": dated_cards[-1][0] if dated_cards else None,
            "tripped": [],
            "no_evidence": [],
            "notes": [],
        }

    trailing = dated_cards[:-1]
    latest_date, latest_card = dated_cards[-1]

    pooled = {}
    for _date, card in trailing:
        for row in (card.get("kits") or []):
            name = row.get("kit")
            if not name:
                continue
            rate = _kit_escalation_rate(row)
            if rate is not None:
                pooled[name] = rate

    if len(pooled) < 2:
        return {
            "evaluated": False,
            "sigma": sigma,
            "insufficient_reason": (
                "insufficient history — need at least 2 kits with a computable "
                "escalation rate in the trailing snapshots to derive a baseline "
                f"variance; have {len(pooled)}"),
            "baseline": {"kits": len(pooled), "mean": None, "stdev": None,
                         "threshold": None},
            "latest_date": latest_date,
            "tripped": [],
            "no_evidence": [],
            "notes": [],
        }

    rates = list(pooled.values())
    mean = statistics.mean(rates)
    stdev = statistics.pstdev(rates)
    threshold = mean + sigma * stdev

    tripped = []
    no_evidence = []
    for row in (latest_card.get("kits") or []):
        name = row.get("kit")
        if not name:
            continue
        rate = _kit_escalation_rate(row)
        if rate is None:
            no_evidence.append(name)
            continue
        if rate > threshold:
            tripped.append({
                "kit": name,
                "rate": rate,
                "with_outcome": row.get("with_outcome") or 0,
                "escalated_pass": row.get("escalated_pass") or 0,
            })

    return {
        "evaluated": True,
        "sigma": sigma,
        "insufficient_reason": None,
        "baseline": {"kits": len(pooled), "mean": mean, "stdev": stdev,
                     "threshold": threshold},
        "latest_date": latest_date,
        "tripped": tripped,
        "no_evidence": no_evidence,
        "notes": [],
    }


def build_trend(snapshot_dir, dated_cards, notes, sigma=TREND_ALARM_SIGMA_DEFAULT):
    """Assemble the pinned D7 trend card from ``read_snapshots`` output → the trend card.

    Top-level keys EXACTLY ``schema_version`` (``TREND_SCHEMA_VERSION``), ``generated_at``,
    ``snapshot_dir`` (str), ``points``, ``escalation_alarm``, ``notes``. Each point:
    ``{"date", "kits", "tiers": {tier: {"with_outcome", "first_try", "first_try_rate"} for
    tier in LIVE_TIER_ORDER}, "dollars"}``. ``kits`` is ``len(card.get("kits") or [])``; tier
    cells are read TOLERANTLY straight from the stored card's own ``tiers[tier]`` (an absent
    tier → zeros + rate ``None``, no note — old-schema tolerance, never recomputed here);
    ``dollars`` is ``{"actual_usd", "delta_usd"}`` when the stored card's ``dollars`` is a
    dict, else ``None`` — dollars-over-time surfaces ONLY where a snapshot carries it, never
    fabricated. Zero points → append ``no snapshots found under <dir> — nothing to trend``;
    exactly one → append ``one snapshot — no trend yet (a trend needs at least 2 points)`` and
    the single point still renders (data shown, trend claim withheld).

    T11 (PLAN D11) adds ``escalation_alarm`` (``build_escalation_alarm`` over the SAME
    ``dated_cards``) — ALWAYS present, unlike the history card's ``lineage``/
    ``failure_breakdown``, which are omitted whole when empty: an alarm must always say
    something (evaluated-clean, evaluated-tripped, or an honest insufficient-history
    reason), never be silently absent. Its own notes are NESTED under
    ``escalation_alarm["notes"]``, never folded into this card's top-level ``notes``
    (mirrors ``by_task["notes"]``'s existing nesting precedent) — so a caller reading only
    ``points``/``notes`` (every consumer before T11) sees byte-for-byte the same card.
    """
    notes = list(notes)
    points = []
    for date_str, card in dated_cards:
        tiers = card.get("tiers") or {}
        tier_cells = {}
        for tier in LIVE_TIER_ORDER:
            t = tiers.get(tier) or {}
            tier_cells[tier] = {
                "with_outcome": t.get("with_outcome", 0) or 0,
                "first_try": t.get("first_try", 0) or 0,
                "first_try_rate": t.get("first_try_rate"),
            }
        raw_dollars = card.get("dollars")
        if isinstance(raw_dollars, dict):
            dollars = {"actual_usd": raw_dollars.get("actual_usd"),
                      "delta_usd": raw_dollars.get("delta_usd")}
        else:
            dollars = None
        points.append({
            "date": date_str,
            "kits": len(card.get("kits") or []),
            "tiers": tier_cells,
            "dollars": dollars,
        })

    if len(points) == 0:
        notes.append(f"no snapshots found under {snapshot_dir} — nothing to trend")
    elif len(points) == 1:
        notes.append("one snapshot — no trend yet (a trend needs at least 2 points)")

    return {
        "schema_version": TREND_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "snapshot_dir": str(snapshot_dir),
        "points": points,
        "escalation_alarm": build_escalation_alarm(dated_cards, sigma),
        "notes": notes,
    }


def render_trend_markdown(card):
    """Render the trend card as human markdown: H1 + one table (rows = dates, columns = the
    four tiers + Kits + Actual $) + the escalation-rate alarm (T11, PLAN D11) + the Notes
    block (PLAN D7).

    Zero points → the line ``no snapshots — n/a``. Otherwise the header is EXACTLY
    ``| Date | haiku | sonnet | opus | frontier | Kits | Actual $ |`` (tier columns generated
    from ``LIVE_TIER_ORDER``, never retyped); a tier cell is
    ``{first_try}/{with_outcome} ({_rate_pct(rate)})`` or ``n/a`` when ``with_outcome`` is 0;
    an ``Actual $`` cell is ``$x.xx`` or ``n/a`` when the point's dollars is ``None``.

    T11: ``## Escalation-rate alarm`` is ALWAYS rendered (mirrors Role quality's own
    "zero evidence is an explicit line" precedent) — the honest insufficient-history
    reason, a "no kit exceeds the trailing baseline" clean line, or the tripped kit(s)
    plus any kit with no computable rate at all (P34-F1 — reported by name, never
    silently folded into "no escalations"). The reported date is the LATEST snapshot's,
    so a reader always sees exactly how stale this verdict is.
    """
    out = ["# Routing trend — per-tier first-try rate over time\n"]
    points = card["points"]
    if not points:
        out.append("no snapshots — n/a")
    else:
        out.append("| Date | " + " | ".join(LIVE_TIER_ORDER) + " | Kits | Actual $ |")
        out.append("|---|" + "---|" * len(LIVE_TIER_ORDER) + "---:|---:|")
        for p in points:
            cells = []
            for tier in LIVE_TIER_ORDER:
                t = p["tiers"][tier]
                if t["with_outcome"] == 0:
                    cells.append("n/a")
                else:
                    cells.append(
                        f"{t['first_try']}/{t['with_outcome']} "
                        f"({_rate_pct(t['first_try_rate'])})")
            dollars = p["dollars"]
            actual = f"${dollars['actual_usd']:,.2f}" if dollars else "n/a"
            out.append(f"| {p['date']} | " + " | ".join(cells) + f" | {p['kits']} | {actual} |")

    out.append("")
    out.append("## Escalation-rate alarm\n")
    alarm = card["escalation_alarm"]
    if not alarm["evaluated"]:
        out.append(alarm["insufficient_reason"])
    else:
        b = alarm["baseline"]
        out.append(
            f"trailing baseline {_rate_pct(b['mean'])} (n={b['kits']} kits, "
            f"σ={_rate_pct(b['stdev'])}) — threshold {_rate_pct(b['threshold'])} "
            f"(+{alarm['sigma']:g}σ), as of {alarm['latest_date']}")
        if alarm["tripped"]:
            for t in alarm["tripped"]:
                out.append(
                    f"- TRIPPED: {t['kit']} — {_rate_pct(t['rate'])} "
                    f"({t['escalated_pass']}/{t['with_outcome']}) exceeds "
                    f"{_rate_pct(b['threshold'])}")
        else:
            out.append("- no kit exceeds the trailing baseline")
        if alarm["no_evidence"]:
            out.append(
                "- no computable rate (driver-executed kits are structurally invisible "
                "to tier attribution here — P34-F1 — never treated as 0% escalation): "
                + ", ".join(alarm["no_evidence"]))
    out.append("")

    if card["notes"]:
        out.append("\nNotes:")
        for n in card["notes"]:
            out.append(f"- {n}")

    return "\n".join(out)


def run_trend(args, extra_notes=()):
    """The ``--trend`` flow: read every stored snapshot, build + print the trend card
    (including the T11 escalation-rate alarm). READ-ONLY and pricing-free in the common
    case (mirrors ``--live``'s pricing-free guarantee); exit 0 for every degraded shape
    (PLAN D6/D7).

    ``notes`` starts from ``extra_notes`` (the snapshot-write note when called from
    ``run_history``'s ``--snapshot --trend`` tail); the existing single-session
    ``--tasks-dir``/``--include`` ignored note is appended when either is passed; a
    ``--kits-dir is ignored by --trend without --snapshot`` note is appended when
    ``--kits-dir`` was explicitly passed on the CLI (``args.kits_dir_passed``, captured in
    ``main`` BEFORE normalization) and ``--snapshot`` is absent.

    T11 (PLAN D11 / the statusline pre-flight in NOTES.md): the ONLY write in this
    function persists the just-computed alarm verdict to
    ``<snapshot_dir>/alarm/state.json`` via ``write_trend_alarm`` — gated STRICTLY on
    ``args.snapshot`` (i.e. only when reached from ``--history --snapshot --trend``). A
    bare ``--trend`` (``args.snapshot`` False) never writes anything, which is exactly
    what ``ReadOnlyNonSnapshotTests`` already proves and must keep proving. This is the
    one sanctioned mechanism the statusline reads (read-only, never recomputing) —
    read_escalation_alarm() in bin/statusline.py.
    """
    notes = list(extra_notes)
    if args.tasks_dir or args.include:
        notes.append("--tasks-dir/--include are ignored by --history "
                     "(single-session affordances; use --session on the plain scorecard)")
    if getattr(args, "kits_dir_passed", False) and not args.snapshot:
        notes.append("--kits-dir is ignored by --trend without --snapshot "
                     "(the trend reads stored snapshots)")

    dated_cards, read_notes = read_snapshots(args.snapshot_dir)
    card = build_trend(args.snapshot_dir, dated_cards, notes + read_notes,
                       sigma=args.trend_alarm_sigma)
    if args.snapshot:
        write_trend_alarm(card["escalation_alarm"], args.snapshot_dir)
    print(json.dumps(card, indent=2) if args.json else render_trend_markdown(card))
    return 0


def run_trend_demo(as_json):
    """Build two synthetic repos + one shared transcript in ONE temp dir, snapshot two history
    cards (day 1 = repo-a alone — a PLAIN single-dir card; day 2 = repo-a + repo-b — a
    NAMESPACED multi card), then render the trend over both stored snapshots via ``main``.
    Exit 0 (PLAN D8).

    This ONE demo exercises BOTH new features: the cross-repo feature has no flag of its own
    (it IS repeatable ``--kits-dir``), so its smoke rides the trend demo's day-2 card. The
    fixtures reuse the existing ``DEMO_HIST_*`` constants read-only (never modified); the demo
    transcript's model IDS are computed from data/pricing.json at run time via
    ``_first_model_of_tier`` (the ``if model_id is None: continue`` guard) — only the token
    VOLUMES (reused ``DEMO_VOLUMES``) are pinned. The pinned dates ``2026-01-01``/``2026-01-02``
    are synthetic fixture dates (same species as the demo transcripts' pinned timestamp). The
    sanctioned combined smoke test — the ONLY place this script writes besides
    ``write_snapshot`` under a real ``--snapshot-dir``, and here it writes only inside its own
    temp dir.
    """
    pricing = cr.load_pricing()
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)

        repo_a_kits = tmp / "repo-a" / ".claude" / "kits"
        alpha = repo_a_kits / "hist-alpha"
        alpha.mkdir(parents=True)
        (alpha / "TASKS.md").write_text(DEMO_HIST_ALPHA_TASKS_MD)
        (alpha / "NOTES.md").write_text(DEMO_HIST_ALPHA_NOTES_MD)

        beta = repo_a_kits / "hist-beta"
        beta.mkdir(parents=True)
        (beta / "TASKS.md").write_text(DEMO_HIST_BETA_TASKS_MD)
        (beta / "NOTES.md").write_text(DEMO_HIST_BETA_NOTES_MD)

        repo_b_kits = tmp / "repo-b" / ".claude" / "kits"
        gamma = repo_b_kits / "hist-gamma"
        gamma.mkdir(parents=True)
        (gamma / "TASKS.md").write_text(DEMO_HIST_GAMMA_TASKS_MD)  # no NOTES.md by design

        proj = tmp / "projects" / "-demo"
        proj.mkdir(parents=True)
        ts = "2026-07-01T12:00:00+00:00"
        lines = []
        for tier in ("haiku", "sonnet", "opus", "frontier"):
            model_id = _first_model_of_tier(pricing, tier)
            if model_id is None:
                continue
            inp, outp = DEMO_VOLUMES[tier]
            lines.append(json.dumps({
                "timestamp": ts,
                "message": {
                    "model": model_id,
                    "id": f"demo-hist-{tier}",
                    "usage": {"input_tokens": inp, "output_tokens": outp},
                },
            }))
        (proj / "hist-alpha-session.jsonl").write_text("\n".join(lines) + "\n")

        snap = tmp / "snapshots"
        projects_dir = tmp / "projects"

        day1_argv = ["--history", "--kits-dir", str(repo_a_kits),
                    "--projects-dir", str(projects_dir), "--no-subagents", "--json"]
        buf1 = io.StringIO()
        with contextlib.redirect_stdout(buf1):
            main(day1_argv)
        card1 = json.loads(buf1.getvalue())

        day2_argv = day1_argv + ["--kits-dir", str(repo_b_kits)]
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            main(day2_argv)
        card2 = json.loads(buf2.getvalue())

        write_snapshot(card1, snap, "2026-01-01")
        write_snapshot(card2, snap, "2026-01-02")

        argv = ["--history", "--trend", "--snapshot-dir", str(snap)]
        if as_json:
            argv.append("--json")
        return main(argv)


def run_alarm_demo(as_json, trend=True):
    """Synthetic multi-kit escalation-alarm demo (T11, PLAN D11 / Phase 1 F7) —
    ``--demo --alarm``. A NEW, standalone demo path that leaves ``run_demo``'s and
    ``run_history_demo``'s own fixtures and goldens completely untouched (T2's
    byte-stability tripwire binds only ``--demo`` and ``--demo --history``).

    Two synthetic ``--history`` scans, snapshotted on two pinned days, in one temp dir:
      * day 1 (the trailing baseline): two STEADY kits (``_alarm_demo_steady_kit_md``),
        each 1/10 escalated (10%) -- pooled baseline mean 10%, stdev 0.
      * day 2 (the current reading): the same two steady kits UNCHANGED (still 10% —
        AT the threshold, never over it, proving a stable kit does not trip), PLUS
        ``spike-3`` (4/6 escalated — a drifting verify command, tripping the alarm) and
        ``driver-blind`` (one outcome line carrying a CONCRETE pricing model id, exactly
        what a driver harness writes per P34-F1 — structurally invisible to
        ``tier_for``, reported as "no evidence", never a fabricated 0%).

    Both days scan the SAME two ``--kits-dir`` roots (a steady dir + an initially-empty
    "extra" dir) so kit names stay consistently namespaced across both snapshots —
    ``spike-3``/``driver-blind`` are simply absent from the extra dir on day 1.

    ``trend=True`` (default) prints the ``--history --trend`` view — the tripped D11
    alarm plus its evidence, dated as of day 2. ``trend=False`` prints day 2's plain
    ``--history`` view instead — the Escalation lineage + Failure breakdown sections
    ``spike-3`` was built to exercise. Either way this writes only inside its own temp
    dir. Exit 0.
    """
    pricing = cr.load_pricing()
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)

        steady_dir = tmp / "steady-kits"
        for prefix in ("ST", "SU"):
            tasks_md, notes_md = _alarm_demo_steady_kit_md(prefix)
            kit = steady_dir / f"steady-{prefix.lower()}"
            kit.mkdir(parents=True)
            (kit / "TASKS.md").write_text(tasks_md)
            (kit / "NOTES.md").write_text(notes_md)

        extra_dir = tmp / "extra-kits"
        extra_dir.mkdir(parents=True)  # empty for day 1 -- populated before day 2 below

        proj = tmp / "projects"
        proj.mkdir()
        snap = tmp / "snapshots"

        argv = ["--history", "--kits-dir", str(steady_dir), "--kits-dir", str(extra_dir),
               "--projects-dir", str(proj), "--no-subagents", "--json"]

        buf1 = io.StringIO()
        with contextlib.redirect_stdout(buf1):
            main(argv)
        card1 = json.loads(buf1.getvalue())

        spike = extra_dir / "spike-3"
        spike.mkdir(parents=True)
        (spike / "TASKS.md").write_text(DEMO_ALARM_SPIKE_TASKS_MD)
        (spike / "NOTES.md").write_text(DEMO_ALARM_SPIKE_NOTES_MD)

        blind = extra_dir / "driver-blind"
        blind.mkdir(parents=True)
        (blind / "TASKS.md").write_text(DEMO_ALARM_BLIND_TASKS_MD)
        concrete_id = (_first_model_of_tier(pricing, "sonnet")
                      or _first_model_of_tier(pricing, "haiku") or "unknown-model")
        (blind / "NOTES.md").write_text(
            "# NOTES — driver-blind (synthetic, P34-F1 honesty demo)\n\n"
            "This kit's outcome line carries a concrete pricing model id, exactly what a "
            "driver harness writes (P34-F1) -- tier_for cannot resolve it, so it is "
            "structurally invisible to the alarm's per-kit rate, reported as 'no "
            "evidence', never a fabricated 0%.\n\n"
            "## Outcome ledger\n"
            f"outcome: DR1 model={concrete_id} attempts=1 result=pass review=clean\n")

        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            main(argv)  # SAME argv -- only the filesystem under extra_dir changed
        card2 = json.loads(buf2.getvalue())

        write_snapshot(card1, snap, "2026-02-01")
        write_snapshot(card2, snap, "2026-02-02")

        if not trend:
            hist_argv = ["--history", "--kits-dir", str(steady_dir),
                        "--kits-dir", str(extra_dir), "--projects-dir", str(proj),
                        "--no-subagents"]
            if as_json:
                hist_argv.append("--json")
            return main(hist_argv)

        trend_argv = ["--history", "--trend", "--snapshot-dir", str(snap)]
        if as_json:
            trend_argv.append("--json")
        return main(trend_argv)


# --------------------------------------------------------------------------- per-task dollars

def parse_agents(text):
    """Scan ``text`` for ``agent:`` ledger lines (D2 grammar) → ``(events, notes)``.

    Grammar: ``agent: <task-id> id=<agent-id> role=<implementer|verifier|escalation>
    model=<model> [findings=<n> confirmed=<n>] [result=<accepted|revised|blocked>]``. The
    first token after ``agent:`` is the task id; the remaining ``key=value`` pairs are read
    with ``PAIR_RE``. An event ``{"task", "agent_id", "role", "model", "findings",
    "confirmed", "result"}`` is kept only when ``id=`` is present and ``role=`` is in
    ``AGENT_ROLES``; otherwise the whole line is skipped with an ``unrecognized agent line``
    note (mirrors ``parse_outcomes``). ``model`` is ``pairs.get("model")`` — informational,
    ``None`` when absent, never validated (the alias vocabulary is execute-owned).

    D1 role-ledger extension (per-task role quality; verifier/escalation, legal-but-ignored
    for implementer per PLAN D7): ``result`` is ``pairs.get("result")``; a value outside
    ``AGENT_RESULTS`` degrades to ``None`` with a note (never dropped, never guessed).
    ``findings``/``confirmed`` are both ``None`` unless BOTH pairs are present; exactly one
    present degrades both to ``None`` with a note (they must appear together); either failing
    to parse as a non-negative int, or ``confirmed > findings``, degrades both to ``None``
    with a note (self-contradictory evidence is dropped, never repaired). A bad quality field
    never drops the line itself — keep/skip criteria for the line are unchanged from above.

    Unknown pairs are ignored (forward-compatible). Events are returned in FILE ORDER; a
    repeated (task-id, agent-id) pair REPLACES the earlier event in place (last wins —
    re-runs append; the first occurrence's position is kept — this is how execute re-emits an
    enriched line once findings are adjudicated). No id-format validation — the agent id's
    shape is harness-owned. ``AGENT_RE`` is disjoint from the ``outcome:`` / ``reroute:`` /
    ``session:`` regexes, so none of the four parsers can match another's lines.
    """
    events = []
    pos_by_pair = {}
    notes = []
    for line in text.splitlines():
        m = AGENT_RE.match(line)
        if not m:
            continue
        tid = m.group(1)
        pairs = dict(PAIR_RE.findall(m.group(2)))
        agent_id = pairs.get("id")
        role = pairs.get("role")
        if not agent_id or role not in AGENT_ROLES:
            notes.append(f"unrecognized agent line: {line.strip()!r}")
            continue

        result = pairs.get("result")
        if result is not None and result not in AGENT_RESULTS:
            notes.append(f"agent {tid}: unknown result {result!r} — ignored")
            result = None

        raw_findings = pairs.get("findings")
        raw_confirmed = pairs.get("confirmed")
        findings = confirmed = None
        if raw_findings is not None or raw_confirmed is not None:
            if raw_findings is None or raw_confirmed is None:
                notes.append(
                    f"agent {tid}: findings/confirmed must appear together — ignored")
            else:
                try:
                    f_val = int(raw_findings)
                    c_val = int(raw_confirmed)
                except (TypeError, ValueError):
                    notes.append(
                        f"agent {tid}: non-integer findings/confirmed "
                        f"({raw_findings!r}/{raw_confirmed!r}) — ignored")
                else:
                    if f_val < 0 or c_val < 0 or c_val > f_val:
                        notes.append(
                            f"agent {tid}: self-contradictory findings/confirmed "
                            f"({f_val}/{c_val}) — ignored")
                    else:
                        findings, confirmed = f_val, c_val

        event = {"task": tid, "agent_id": agent_id, "role": role,
                 "model": pairs.get("model"),
                 "findings": findings, "confirmed": confirmed, "result": result}
        key = (tid, agent_id)
        if key in pos_by_pair:
            events[pos_by_pair[key]] = event
        else:
            pos_by_pair[key] = len(events)
            events.append(event)
    return events, notes


def parse_reviewers(text):
    """Scan ``text`` for ``reviewer:`` ledger lines (D1 grammar) → ``(events, notes)``.

    Grammar: ``reviewer: <phase-token> model=<model> findings=<n> confirmed=<n>
    [result=<accepted|revised|blocked>]``. The first token after ``reviewer:`` is a
    free-form phase label (e.g. ``P1``); the remaining ``key=value`` pairs are read with
    ``PAIR_RE``. Unlike ``agent:``'s quality fields, precision is MANDATORY here — a
    reviewer line exists only to record adjudicated findings — so the whole line is KEPT
    only when ``model=`` is present AND ``findings=``/``confirmed=`` both parse as
    non-negative ints with ``confirmed <= findings``; otherwise the line is skipped with an
    ``unrecognized reviewer line`` note (mirrors ``parse_outcomes``/``parse_agents``), never
    degraded-but-kept. ``result`` is optional; a value outside ``AGENT_RESULTS`` degrades
    that field alone to ``None`` with a note (the line is still kept — the findings/confirmed
    pair already proved out). Event keys are exactly ``{"phase", "model", "findings",
    "confirmed", "result"}``; unknown pairs are ignored. Events are returned in FILE ORDER; a
    repeated phase token REPLACES the earlier event in place (last wins — mirrors
    ``parse_agents``, first occurrence's position kept). ``REVIEWER_RE`` is disjoint from the
    ``outcome:``/``reroute:``/``session:``/``agent:``/``defect:`` regexes.
    """
    events = []
    pos_by_phase = {}
    notes = []
    for line in text.splitlines():
        m = REVIEWER_RE.match(line)
        if not m:
            continue
        phase = m.group(1)
        pairs = dict(PAIR_RE.findall(m.group(2)))
        model = pairs.get("model")
        raw_findings = pairs.get("findings")
        raw_confirmed = pairs.get("confirmed")

        findings = confirmed = None
        valid = bool(model) and raw_findings is not None and raw_confirmed is not None
        if valid:
            try:
                f_val = int(raw_findings)
                c_val = int(raw_confirmed)
            except (TypeError, ValueError):
                valid = False
            else:
                if f_val < 0 or c_val < 0 or c_val > f_val:
                    valid = False
                else:
                    findings, confirmed = f_val, c_val
        if not valid:
            notes.append(f"unrecognized reviewer line: {line.strip()!r}")
            continue

        result = pairs.get("result")
        if result is not None and result not in AGENT_RESULTS:
            notes.append(f"reviewer {phase}: unknown result {result!r} — ignored")
            result = None

        event = {"phase": phase, "model": model, "findings": findings,
                 "confirmed": confirmed, "result": result}
        if phase in pos_by_phase:
            events[pos_by_phase[phase]] = event
        else:
            pos_by_phase[phase] = len(events)
            events.append(event)
    return events, notes


def parse_defects(text):
    """Scan ``text`` for ``defect:`` ledger lines (D1/D4 grammar) → ``(events, notes)``.

    Grammar: ``defect: <task-id-or--> kind=<kebab-token>``. The first token after
    ``defect:`` is a task id, or the sanctioned literal ``-`` for a kit-level defect (a
    stale PLAN decision and the like — not attributable to one task). The line is KEPT only
    when ``kind=`` is present; otherwise skipped with an ``unrecognized defect line`` note.
    Event keys are exactly ``{"task", "kind"}``; unknown pairs are ignored. A repeated
    ``(task, kind)`` pair keeps the FIRST occurrence and adds a note — re-runs must never
    double-count a defect. A defect of the same kind recurring in one task repeats that kind
    verbatim on its own line and the keep-first dedupe stands: one kind counts once per task
    by design. Never suffix a kind (``stale-pin-2``) to force a second count — a suffix is a
    new key that hides the very recurrence it was meant to show. ``DEFECT_RE`` is disjoint
    from the ``outcome:``/``reroute:``/``session:``/``agent:``/``reviewer:`` regexes.
    """
    events = []
    seen = set()
    notes = []
    for line in text.splitlines():
        m = DEFECT_RE.match(line)
        if not m:
            continue
        tid = m.group(1)
        pairs = dict(PAIR_RE.findall(m.group(2)))
        kind = pairs.get("kind")
        if not kind:
            notes.append(f"unrecognized defect line: {line.strip()!r}")
            continue
        key = (tid, kind)
        if key in seen:
            notes.append(
                f"duplicate defect {kind!r} for {tid} — keeping the first occurrence")
            continue
        seen.add(key)
        events.append({"task": tid, "kind": kind})
    return events, notes


def discover_agent_outputs(task_dirs):
    """Map every ``*.output`` file's stem (= agent id) to its Path → ``(mapping, notes)``.

    For each dir in ``task_dirs`` in the given order, ``sorted(Path(d).glob("*.output"))``;
    ``mapping`` is ``{stem: Path}``. A stem already seen (same agent id in two dirs) keeps the
    FIRST file plus a note. A dir that does not exist is noted once; an existing-but-empty dir
    is simply skipped (``discover_task_dirs`` already returns existing dirs only). Read-only.
    """
    mapping = {}
    notes = []
    for d in task_dirs:
        p = Path(d)
        if not p.is_dir():
            notes.append(f"tasks dir not found: {d}")
            continue
        for f in sorted(p.glob("*.output")):
            stem = f.stem
            if stem in mapping:
                notes.append(
                    f"duplicate agent transcript {stem!r} in {d} — keeping the first seen")
                continue
            mapping[stem] = f
    return mapping, notes


def build_by_task(tasks, agent_events, output_map, main_transcript, whole_cost, pricing):
    """Assemble the per-task dollar breakdown (PLAN D3–D6) → the pinned ``by_task`` dict.

    Delegated cost is attributed per task and role from the recorded ``agent:`` events; the
    main transcript is priced standalone and reported as ONE un-attributable orchestrator line
    (NEVER split per task); a warm cluster's shared transcript is attributed to the cluster as
    a unit (NEVER divided); a recorded agent id with no ``.output`` prices ``None`` + a note
    (never a zero, never a guess). Every per-task/role figure is only ever the sum of the
    transcripts that actually exist. The parts-vs-whole reconciliation is a NOTE, never an
    adjustment. Returns the pinned key set ``{"schema_version", "coverage", "tasks",
    "clusters", "orchestrator", "unattributed", "notes"}`` — by-task notes stay NESTED here.
    """
    notes = []
    task_order = [t["id"] for t in tasks]
    task_ids = set(task_order)

    # Zero-events rung (D6): no kept agent: events at all → the breakdown is n/a. Output files
    # are deliberately NOT enumerated (that would be a de-facto breakdown), nothing is priced
    # (not even the orchestrator), and the whole-kit dollars above are left untouched.
    if not agent_events:
        notes.append("no agent: lines recorded — per-task dollars n/a")
        return {
            "schema_version": BYTASK_SCHEMA_VERSION,
            "coverage": None,
            "tasks": [],
            "clusters": [],
            "orchestrator": {"cost_usd": None},
            "unattributed": {"count": 0, "cost_usd": None, "agent_ids": []},
            "notes": notes,
        }

    # Join (D4): drop events naming a task id we don't know (their transcripts, if present and
    # referenced by no known task, land in unattributed); keep the rest in file order.
    known_events = []
    for e in agent_events:
        if e["task"] in task_ids:
            known_events.append(e)
        else:
            notes.append(f"agent line for unknown task id {e['task']} ignored")

    # Group (D4/D5): an agent id referenced by MORE THAN ONE distinct known task is a shared
    # warm agent (a cluster); otherwise it belongs to its single task's role bucket.
    agent_tasks = {}          # agent_id -> ordered-unique known task ids referencing it
    referenced_ids = []       # agent ids referenced by >=1 known event, first-seen order
    for e in known_events:
        aid = e["agent_id"]
        if aid not in agent_tasks:
            agent_tasks[aid] = []
            referenced_ids.append(aid)
        if e["task"] not in agent_tasks[aid]:
            agent_tasks[aid].append(e["task"])
    shared_ids = {aid for aid, tids in agent_tasks.items() if len(tids) > 1}

    # Price each referenced transcript STANDALONE, once each (D3). Absent from output_map, or a
    # file that cannot be read/priced → None + a note naming the id (never a zero, never a guess).
    def price_path(path):
        data = sc.collect([str(path)], pricing)
        if data["files_read"] == 0:
            return None
        return sum(b["cost"] for b in data["by_model"].values())

    agent_cost = {}
    for aid in referenced_ids:
        if aid not in output_map:
            agent_cost[aid] = None
            notes.append(
                f"agent {aid}: no *.output transcript found — cost n/a (the tasks scratch is "
                f"session-scoped tmp and may have been cleaned)")
            continue
        c = price_path(output_map[aid])
        agent_cost[aid] = c
        if c is None:
            notes.append(
                f"agent {aid}: *.output present but could not be read/priced — cost n/a")

    # Task rows (D4): one per known task that at least one kept event names, TASKS.md order.
    # Shared agents are EXCLUDED from a task's roles/total (their cost lives in the cluster
    # row); roles list only the roles that have >=1 of the task's single-task agents.
    task_rows = []
    for tid in task_order:
        row_events = [e for e in known_events if e["task"] == tid]
        if not row_events:
            continue
        roles = {}
        shared_here = []
        missing_here = []
        priced_total = 0.0
        any_priced = False
        for e in row_events:
            aid = e["agent_id"]
            if aid in shared_ids:
                if aid not in shared_here:
                    shared_here.append(aid)
                continue
            if aid not in output_map and aid not in missing_here:
                missing_here.append(aid)
            cost = agent_cost.get(aid)
            bucket = roles.setdefault(e["role"], {"agents": [], "subtotal_usd": None})
            bucket["agents"].append(
                {"agent_id": aid, "model": e["model"], "cost_usd": cost})
            if cost is not None:
                any_priced = True
                priced_total += cost
        for bucket in roles.values():
            priced = [a["cost_usd"] for a in bucket["agents"] if a["cost_usd"] is not None]
            bucket["subtotal_usd"] = sum(priced) if priced else None
        task_rows.append({
            "id": tid,
            "roles": roles,
            "total_usd": (priced_total if any_priced else None),
            "missing_agents": missing_here,
            "shared_agent_ids": sorted(shared_here),
        })

    # Cluster rows (D5): one per shared agent, ordered by first task position; task_ids in
    # TASKS.md order; roles = sorted unique roles observed; cost = the single-file price.
    cluster_rows = []
    for aid in referenced_ids:
        if aid not in shared_ids:
            continue
        tids = [tid for tid in task_order if tid in agent_tasks[aid]]
        roles_observed = sorted({e["role"] for e in known_events
                                 if e["agent_id"] == aid})
        cluster_rows.append({
            "agent_id": aid,
            "task_ids": tids,
            "roles": roles_observed,
            "cost_usd": agent_cost.get(aid),
        })

    # Orchestrator (D3): the main transcript, priced the same standalone way, as ONE
    # un-attributable line — NEVER split per task.
    if main_transcript is None:
        orch_cost = None
        notes.append("main transcript not found — orchestrator cost n/a")
    else:
        orch_cost = price_path(main_transcript)
        if orch_cost is None:
            notes.append(
                "main transcript present but could not be priced — orchestrator cost n/a")

    # Unattributed (D3): files in output_map referenced by NO kept event (phase reviewers,
    # scouts, unrecorded dispatches). Priced standalone; None cost when none priced.
    unattributed_ids = sorted(stem for stem in output_map if stem not in referenced_ids)
    ua_priced = []
    for stem in unattributed_ids:
        c = price_path(output_map[stem])
        if c is not None:
            ua_priced.append(c)
    unattributed = {
        "count": len(unattributed_ids),
        "cost_usd": (sum(ua_priced) if ua_priced else None),
        "agent_ids": unattributed_ids,
    }

    # Coverage (D6): full iff every referenced agent id priced AND the main transcript priced;
    # partial otherwise (there is >=1 kept event by here).
    all_agents_priced = all(agent_cost[aid] is not None for aid in referenced_ids)
    coverage = "full" if (all_agents_priced and orch_cost is not None) else "partial"

    # Reconciliation (D3): the breakdown prices files STANDALONE, so a message id shared across
    # transcripts counts per-transcript here but once in the globally-deduped session total.
    # When the parts differ from the whole by more than half a cent, append ONE explanatory
    # note — a NOTE, never an adjustment of any figure.
    if whole_cost is not None and whole_cost.get("actual_usd") is not None:
        parts = 0.0
        if orch_cost is not None:
            parts += orch_cost
        for aid in referenced_ids:
            c = agent_cost.get(aid)
            if c is not None:
                parts += c
        if unattributed["cost_usd"] is not None:
            parts += unattributed["cost_usd"]
        whole = whole_cost["actual_usd"]
        half_cent = 0.005
        if abs(parts - whole) > half_cent:
            notes.append(
                f"parts-vs-whole reconciliation: the standalone per-transcript prices sum to "
                f"${parts:,.4f} vs the session total ${whole:,.4f} — a message id shared across "
                f"transcripts counts once in the session total but per-transcript in the "
                f"breakdown, and any --include'd transcripts fall outside the attribution; "
                f"this is a note, not an adjustment.")

    return {
        "schema_version": BYTASK_SCHEMA_VERSION,
        "coverage": coverage,
        "tasks": task_rows,
        "clusters": cluster_rows,
        "orchestrator": {"cost_usd": orch_cost},
        "unattributed": unattributed,
        "notes": notes,
    }


def _bt_money(value):
    """A dollar cell: ``$x.xx`` when priced, ``n/a`` when None (never a fabricated 0)."""
    return f"${value:,.2f}" if value is not None else "n/a"


def _bt_role_cell(role):
    """A role cell: ``—`` for an absent role, ``n/a`` for present-but-unpriced, else ``$x.xx``."""
    if role is None:
        return "—"
    return _bt_money(role["subtotal_usd"])


def render_by_task_lines(bt):
    """Render the per-task breakdown (PLAN D7) as markdown lines (H2 + table + bullets).

    On the zero-events rung the section is exactly the pinned n/a sentence; otherwise it emits
    the role table (implementer / verifier / escalation + total, ``*`` on tasks a shared warm
    agent also served), one bullet per cluster, the un-split orchestrator bullet, the
    unattributed bullet (only when count > 0), the coverage bullet, then the nested notes.
    """
    out = ["", "## Per-task dollars\n"]
    if bt["coverage"] is None:
        out.append("n/a — no agent: lines recorded in NOTES.md (the /execute agent ledger); "
                   "the whole-kit dollars above are unaffected.")
        return out

    out.append("| Task | Implementer $ | Verifier $ | Escalation $ | Total $ |")
    out.append("|---|---:|---:|---:|---:|")
    any_shared = False
    for row in bt["tasks"]:
        impl = _bt_role_cell(row["roles"].get("implementer"))
        verif = _bt_role_cell(row["roles"].get("verifier"))
        esc = _bt_role_cell(row["roles"].get("escalation"))
        total = _bt_money(row["total_usd"])
        marker = ""
        if row["shared_agent_ids"]:
            marker = "*"
            any_shared = True
        out.append(f"| {row['id']}{marker} | {impl} | {verif} | {esc} | {total} |")
    if any_shared:
        out.append("")
        out.append("\\* also served by a shared warm agent — see the cluster line; the shared "
                   "transcript is not split into this row.")
    out.append("")

    for c in bt["clusters"]:
        ids = ", ".join(c["task_ids"])
        roles = ", ".join(c["roles"])
        money = _bt_money(c["cost_usd"])
        if c["cost_usd"] is None:
            money = "n/a (transcript missing)"
        out.append(f"shared warm agent `{c['agent_id']}` across {ids} ({roles}): "
                   f"{money} (not split)")

    oc = bt["orchestrator"]["cost_usd"]
    if oc is None:
        out.append("orchestrator (main session): n/a (main transcript not found)")
    else:
        out.append(f"orchestrator (main session): ${oc:,.2f} — interleaved across all tasks; "
                   f"never split per task")

    ua = bt["unattributed"]
    if ua["count"] > 0:
        out.append(f"unattributed subagents (phase reviewers, scouts, unrecorded dispatches): "
                   f"{ua['count']} transcript(s), {_bt_money(ua['cost_usd'])}")

    priced = total_cnt = 0
    for row in bt["tasks"]:
        for role in row["roles"].values():
            for a in role["agents"]:
                total_cnt += 1
                if a["cost_usd"] is not None:
                    priced += 1
    for c in bt["clusters"]:
        total_cnt += 1
        if c["cost_usd"] is not None:
            priced += 1
    out.append(f"coverage: {bt['coverage']} "
               f"({priced}/{total_cnt} recorded agent transcripts priced)")

    for n in bt["notes"]:
        out.append(f"- {n}")
    return out


def run_by_task_demo(as_json):
    """Build a synthetic kit + main transcript + subagent ``*.output`` files in ONE temp dir
    and run the normal ``--by-task`` path against them via ``main`` (the ``run_live_demo``
    pattern; the explicit ``--tasks-dir`` keeps it hermetic — no tmp discovery). Exit 0.

    The fixture carries both honesty proofs: a shared warm agent (``ag-warm`` on P3 + P4) and a
    missing transcript (``ag-ghost``, no ``.output`` written). Model IDS are computed from
    data/pricing.json at run time; only the token VOLUMES are pinned. The sanctioned smoke.
    """
    pricing = cr.load_pricing()
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        kit_dir = tmp / "per-task-demo-kit"
        kit_dir.mkdir()
        (kit_dir / "TASKS.md").write_text(DEMO_BYTASK_TASKS_MD)
        (kit_dir / "NOTES.md").write_text(DEMO_BYTASK_NOTES_MD)

        proj = tmp / "projects" / "-demo"
        proj.mkdir(parents=True)
        ts = "2026-07-01T12:00:00+00:00"
        lines = []
        for tier in ("haiku", "sonnet", "opus", "frontier"):
            model_id = _first_model_of_tier(pricing, tier)
            if model_id is None:
                continue
            inp, outp = DEMO_VOLUMES[tier]
            lines.append(json.dumps({
                "timestamp": ts,
                "message": {
                    "model": model_id,
                    "id": f"demo-bt-main-{tier}",
                    "usage": {"input_tokens": inp, "output_tokens": outp},
                },
            }))
        (proj / "per-task-demo.jsonl").write_text("\n".join(lines) + "\n")

        tasks_out = tmp / "tasks"
        tasks_out.mkdir()
        for agent_id, (tier, inp, outp) in DEMO_BYTASK_VOLUMES.items():
            model_id = _first_model_of_tier(pricing, tier)
            if model_id is None:
                continue
            msg = json.dumps({
                "timestamp": ts,
                "message": {
                    "model": model_id,
                    "id": f"demo-bt-{agent_id}",
                    "usage": {"input_tokens": inp, "output_tokens": outp},
                },
            })
            (tasks_out / f"{agent_id}.output").write_text(msg + "\n")

        argv = [str(kit_dir), "--session", "per-task-demo",
                "--projects-dir", str(tmp / "projects"),
                "--tasks-dir", str(tasks_out), "--by-task"]
        if as_json:
            argv.append("--json")
        return main(argv)


# --------------------------------------------------------------------------- CLI

def _resolve_kit_dir(kit, kits_dir):
    """A positional ``kit`` is a path when it contains a separator or names an
    existing dir; otherwise it is a slug under ``kits_dir``."""
    if os.sep in kit or (os.altsep and os.altsep in kit) or Path(kit).is_dir():
        return Path(kit)
    return Path(kits_dir) / kit


def parse_kits_dir_token(token):
    """Split a ``--kits-dir`` token into ``(label_or_None, path_str)`` (PLAN D3).

    A token containing ``=`` is split on the FIRST ``=``; when the prefix matches
    ``_LABEL_RE`` and contains no path separator (``os.sep`` / ``os.altsep``) it is an
    explicit label and the remainder is the path. Otherwise the WHOLE token is the path with
    label ``None`` — a plain path that itself contains ``=`` (or whose pre-``=`` prefix fails
    the label grammar) keeps working exactly as today.
    """
    if "=" in token:
        prefix, _sep, rest = token.partition("=")
        if (_LABEL_RE.match(prefix)
                and os.sep not in prefix
                and not (os.altsep and os.altsep in prefix)):
            return prefix, rest
    return None, token


def derive_repo_label(path_str):
    """Derive a namespacing label from a kits-dir path — pure path logic, NO filesystem
    access (PLAN D3).

    For a conventional ``<repo>/.claude/kits`` dir (``Path(path).name == "kits"`` and its
    parent is ``.claude``) the label is the repo directory's basename
    (``.parent.parent.name``); otherwise the dir's own basename; an empty result (degenerate
    roots) falls back to ``"kits"``.
    """
    p = Path(path_str)
    if p.name == "kits" and p.parent.name == ".claude":
        label = p.parent.parent.name
    else:
        label = p.name
    return label or "kits"


def resolve_kits_dirs(tokens):
    """Resolve raw ``--kits-dir`` tokens into namespacing entries → ``(entries, notes)``
    (PLAN D3).

    For each token in the GIVEN order: parse it (``parse_kits_dir_token``); derive the label
    when it is not explicit. Each entry is ``{"label", "path", "explicit"}`` where ``path`` is
    the token's path part, verbatim/unresolved. Two tokens resolving (best-effort
    ``Path(path).resolve()``; OSError → the raw path) to the SAME dir keep the FIRST entry plus
    a note. Duplicate labels (after explicit/derived resolution) get deterministic suffixes
    ``-2``, ``-3`` … in occurrence order plus a note per rename — never a silent merge of two
    repos under one label.
    """
    entries = []
    notes = []
    seen_paths = {}
    used_labels = set()
    for token in tokens:
        label, path_str = parse_kits_dir_token(token)
        explicit = label is not None
        if not explicit:
            label = derive_repo_label(path_str)
        try:
            resolved = Path(path_str).resolve()
        except OSError:
            resolved = path_str
        if resolved in seen_paths:
            notes.append(f"duplicate kits-dir {path_str} — already scanned as "
                         f"{seen_paths[resolved]}; skipping the repeat")
            continue
        seen_paths[resolved] = path_str
        if label in used_labels:
            base = label
            n = 2
            while f"{base}-{n}" in used_labels:
                n += 1
            new_label = f"{base}-{n}"
            notes.append(f"duplicate kits-dir label {base!r} — using "
                         f"{new_label!r} for {path_str}")
            label = new_label
        used_labels.add(label)
        entries.append({"label": label, "path": path_str, "explicit": explicit})
    return entries, notes


def assemble_history_card(kits_dirs, projects_dir=None, tasks_dir=(), include=(),
                          no_subagents=False, vs=None):
    """Assemble the cross-kit ``--history`` card — PURE: no printing, no ``sys.exit``, no
    writing (telemetry-store PLAN D3). READ-ONLY over the given dirs.

    This is ``run_history``'s card assembly verbatim, lifted so non-CLI callers (the
    telemetry snapshot tool) get the card as a return value. Failures that the CLI turns
    into exits are raised as ``ValueError`` with the SAME message (``run_history`` catches
    and exits identically): a missing kits dir, and an unresolvable ``vs`` counterfactual.
    ``projects_dir=None`` resolves to ``str(sc.DEFAULT_PROJECTS_DIR)`` — exactly what the
    ``--projects-dir`` argparse default supplies today. The card is returned BEFORE any
    ``--snapshot`` tail note, so it is pure history data.

    ``kits_dirs`` is the list of raw ``--kits-dir`` tokens. A lone plain dir is UNCHANGED —
    today's body, unprefixed kit names, the nine-key card (schema v2's additive ``roles``
    key, PLAN R4). More than one dir, or any explicit ``label=path`` token, switches to
    NAMESPACED mode: each dir is scanned in given order, its records' kit names become
    ``<label>/<kit>``, its scan notes are re-emitted ``<label>/<note>``, tiers and re-route
    tallies aggregate globally, the dollars ladder runs verbatim over the merged records
    (per-kit costs keyed by the NAMESPACED name), and the card carries ``kits_dir`` None plus
    a ``kits_dirs`` list. The dollars degradation is identical in both modes.

    Dollars degradation ladder (PLAN D5): zero ``session:`` lines anywhere → ``dollars``
    None, per-kit costs all None, a quality-only note, and ``cr.load_pricing()`` is NEVER
    called; session lines exist but nothing prices → ``dollars`` None + note (pricing loaded,
    nothing invented); otherwise the aggregate carries a ``coverage`` label (``full`` iff
    every kit has ≥1 session id AND every unique id priced, else ``partial``). A session id
    shared by more than one kit is priced ONCE in the aggregate (a note flags it); the
    single-session ``tasks_dir`` / ``include`` affordances are IGNORED here (folding one
    dir into N sessions would double count) — a note says so when they are passed.
    """
    if projects_dir is None:
        projects_dir = str(sc.DEFAULT_PROJECTS_DIR)
    entries, dir_notes = resolve_kits_dirs(kits_dirs)
    if not entries:
        # No kits dir at all (empty/blank token list). The CLI can never reach this (argparse
        # supplies a default and `main` backstops), but non-CLI callers can — and "nothing to
        # scan" is the SAME failure as "the dir isn't there", so it raises the same
        # ValueError shape rather than reaching entries[0] with an IndexError.
        raise ValueError("kits dir not found: (none specified)")
    for e in entries:
        if not Path(e["path"]).is_dir():
            raise ValueError(f"kits dir not found: {e['path']}")
    namespaced = len(entries) > 1 or any(e["explicit"] for e in entries)
    primary_dir = Path(entries[0]["path"])

    if namespaced:
        # Merge every dir's kits in given order, namespacing kit rows and scan notes so two
        # repos' same-named kits stay distinct. dir_notes (dupe/rename) lead the note stream.
        records = []
        notes = list(dir_notes)
        for e in entries:
            label = e["label"]
            recs, scan_notes = scan_kits(e["path"])
            for rec in recs:
                records.append({**rec, "kit": f"{label}/{rec['kit']}"})
            for n in scan_notes:
                notes.append(f"{label}/{n}")
            if not recs:
                notes.append(
                    f"{label}: no kits with a TASKS.md found under {e['path']}")
    else:
        # Plain mode (one dir, no explicit label): today's body verbatim — byte-identical.
        records, notes = scan_kits(primary_dir)
        if not records:
            notes.append(f"no kits with a TASKS.md found under {primary_dir}")

    if tasks_dir or include:
        notes.append("--tasks-dir/--include are ignored by --history "
                     "(single-session affordances; use --session on the plain scorecard)")

    # Ordered-unique union of every kit's session ids.
    union_ids = []
    seen_ids = set()
    for rec in records:
        for sid in rec["sessions"]:
            if sid not in seen_ids:
                seen_ids.add(sid)
                union_ids.append(sid)

    if not union_ids:
        # Quality-only path — pricing-free by design (like --live).
        dollars = None
        kit_costs = {rec["kit"]: None for rec in records}
        notes.append("no session: lines found — dollars n/a (quality-only history)")
    else:
        pricing = cr.load_pricing()
        try:
            cf_key = sc.resolve_counterfactual_model(vs, pricing)
        except ValueError as e:
            raise ValueError(str(e))
        cf_display = pricing["models"][cf_key]["display"]

        kit_costs = {}
        kits_with_sessions = 0
        for rec in records:
            if rec["sessions"]:
                kits_with_sessions += 1
                cost, _tr, cnotes = kit_cost_summary(
                    rec["sessions"], projects_dir, no_subagents,
                    vs, pricing)
                kit_costs[rec["kit"]] = cost
                for n in cnotes:
                    notes.append(f"{rec['kit']}: {n}")
            else:
                kit_costs[rec["kit"]] = None

        # Flag any session id recorded by more than one kit (priced once in the aggregate).
        id_kits = {}
        for rec in records:
            for sid in dict.fromkeys(rec["sessions"]):
                id_kits.setdefault(sid, []).append(rec["kit"])
        for sid, owners in id_kits.items():
            if len(owners) > 1:
                notes.append(f"session id {sid!r} shared by kits "
                             f"{', '.join(owners)} — priced once in the aggregate")

        agg_cost, _agg_tr, agg_notes = kit_cost_summary(
            union_ids, projects_dir, no_subagents, vs, pricing)
        notes.extend(agg_notes)
        if agg_cost is None:
            dollars = None
            notes.append("session: lines found but no transcript priced — dollars n/a")
        else:
            coverage = ("full"
                        if (kits_with_sessions == len(records)
                            and agg_cost["sessions_priced"] == len(union_ids))
                        else "partial")
            dollars = {
                "kits_with_sessions": kits_with_sessions,
                "kits_total": len(records),
                "sessions_found": len(union_ids),
                "sessions_priced": agg_cost["sessions_priced"],
                "actual_usd": agg_cost["actual_usd"],
                "counterfactual_usd": agg_cost["counterfactual_usd"],
                "delta_usd": agg_cost["delta_usd"],
                "ratio": agg_cost["ratio"],
                "counterfactual_model": {"key": cf_key, "display": cf_display},
                "coverage": coverage,
                "pricing_cached": pricing.get("cached_date"),
            }

    card = build_history(primary_dir, records, kit_costs, dollars, notes)
    if namespaced:
        # ``build_history``'s positional signature is frozen (the untouchable bench file
        # calls it); schema v2's additive ``roles`` key makes ``roles`` the card's NINTH key
        # (PLAN R4) — the single-dir card still keeps ``kits_dir`` a plain string, so the
        # namespaced fields (``kits_dir``: None + ``kits_dirs``) are post-processed onto the
        # dict here rather than threaded through ``build_history``'s own return.
        card["kits_dir"] = None
        card["kits_dirs"] = [{"label": e["label"], "path": e["path"]} for e in entries]

    return card


def run_history(args):
    """The non-demo ``--history`` flow: assemble the card via ``assemble_history_card`` (the
    pure scan → dollars ladder → ``build_history`` path, whose docstring carries the ladder's
    contract), then run the CLI tail — ``--snapshot`` write, ``--trend`` handoff, and the
    print. READ-ONLY; exit 0 including every degraded shape, and the pure function's
    ``ValueError``s (missing kits dir, unresolvable ``--vs``) exit with their exact messages.
    """
    try:
        card = assemble_history_card(
            args.kits_dir, projects_dir=args.projects_dir, tasks_dir=args.tasks_dir,
            include=args.include, no_subagents=args.no_subagents, vs=args.vs)
    except ValueError as e:
        sys.exit(str(e))

    # --snapshot / --trend tail (PLAN D6). The STORED card is written BEFORE any
    # "snapshot written:" note is added, so it is pure history data. ``--history --trend``
    # (without --snapshot) is dispatched straight to ``run_trend`` above main()'s non-demo
    # branch and never reaches here, so ``args.trend`` is only ever True here alongside
    # ``args.snapshot``.
    if args.snapshot:
        path = write_snapshot(card, args.snapshot_dir)
        if args.trend:
            return run_trend(args, extra_notes=[f"snapshot written: {path}"])
        card["notes"].append(f"snapshot written: {path}")

    print(json.dumps(card, indent=2) if args.json else render_history_markdown(card))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Routing-quality scorecard for an executed kit (read-only).")
    ap.add_argument("kit", nargs="?", default=None,
                    help="kit slug under --kits-dir, or a path to a kit dir")
    ap.add_argument("--kits-dir", action="append", default=None,
                    help="kits dir; repeatable with --history, where each value may be "
                         "label=path")
    ap.add_argument("--session", default=None,
                    help="session id to fold in transcript dollars (optional)")
    ap.add_argument("--projects-dir", default=str(sc.DEFAULT_PROJECTS_DIR),
                    help="transcript projects dir (runtime default; override in tests)")
    ap.add_argument("--tasks-dir", action="append", default=[],
                    help="dir of subagent *.output transcripts (repeatable)")
    ap.add_argument("--include", action="append", default=[],
                    help="extra transcript file/dir/glob to fold in (repeatable)")
    ap.add_argument("--no-subagents", action="store_true",
                    help="analyze only the main transcript")
    ap.add_argument("--vs", default=None,
                    help="counterfactual model id (default: the frontier-tier model)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--demo", action="store_true",
                    help="run the whole pipeline against a synthetic kit in a temp dir")
    ap.add_argument("--live", action="store_true",
                    help="live re-route signal for a mid-run kit (quality-only, read-only)")
    ap.add_argument("--history", action="store_true",
                    help="cross-kit routing history aggregated over every kit under "
                         "--kits-dir (read-only; loads no pricing without session: lines)")
    ap.add_argument("--by-task", action="store_true",
                    help="per-task dollar breakdown from NOTES.md agent: lines — "
                         "requires --session")
    ap.add_argument("--live-threshold", type=float, default=LIVE_RATE_THRESHOLD,
                    help="first-try rate below which a tier is judged struggling")
    ap.add_argument("--live-min-sample", type=int, default=LIVE_MIN_SAMPLE,
                    help="completed tasks of a tier before its rate is judged")
    ap.add_argument("--live-max-auto", type=int, default=LIVE_MAX_AUTO_UPGRADES,
                    help="budget cap on applied auto-upgrade events per run")
    ap.add_argument("--snapshot", action="store_true",
                    help="write the history card as a dated JSON snapshot under "
                         "--snapshot-dir — requires --history")
    ap.add_argument("--trend", action="store_true",
                    help="render per-tier first-try rate over stored snapshots as a text "
                         "table — requires --history; with --snapshot, snapshots first")
    ap.add_argument("--snapshot-dir", default=str(DEFAULT_SNAPSHOT_DIR),
                    help="snapshot store dir (runtime default; override in tests)")
    ap.add_argument("--trend-alarm-sigma", type=float, default=TREND_ALARM_SIGMA_DEFAULT,
                    help="PLAN D11 escalation-rate alarm: standard-deviation multiplier "
                         "above the trailing per-kit baseline that counts as a trip — "
                         "the trip VALUE is always derived from the data; this only sets "
                         "how many sigma above the mean counts as anomalous")
    ap.add_argument("--alarm", action="store_true",
                    help="(with --demo) synthetic multi-kit escalation-alarm demo: "
                         "lineage, failure breakdown, and a tripped D11 alarm")
    ap.add_argument("--envelope", action="store_true",
                    help="(rides --history, except under --demo) pairwise cascade "
                         "envelope: per-class (tier x failure=) ladder-walk cost vs the "
                         "best two-model cascade, priced from pricing.json — read-only, "
                         "writes nothing, changes no dispatch/pin/escalation behavior")
    args = ap.parse_args(argv)

    # ``--kits-dir`` is repeatable (action="append"); normalize to a non-empty list of raw
    # tokens. Capture whether it was passed BEFORE defaulting (T2's pure-trend note needs the
    # passed/not-passed signal, not the value) and stash it on ``args`` for ``run_trend``.
    args.kits_dir_passed = args.kits_dir is not None
    args.kits_dir = args.kits_dir or [str(DEFAULT_KITS_DIR)]

    if args.live and args.session is not None:
        sys.exit("--live takes no --session")

    # --history guardrails: mutually exclusive with --live, takes no --session and no kit
    # positional. Checked AFTER the --live+--session rejection and BEFORE the --demo block,
    # so --demo --live --history dies on the mutual-exclusion check first.
    if args.history:
        if args.live:
            sys.exit("--history and --live are mutually exclusive")
        if args.session is not None:
            sys.exit("--history takes no --session — dollars come from "
                     "NOTES.md session: lines")
        if args.kit:
            sys.exit("--history takes no kit argument")

    # --by-task guardrails: per-task dollars attribute ONE session's transcripts. Checked
    # AFTER the --history guardrails and BEFORE the --demo block, so --demo --live --by-task /
    # --demo --history --by-task die on these rejections before reaching a demo dispatch.
    if args.by_task:
        if args.live:
            sys.exit("--live takes no --by-task")
        if args.history:
            sys.exit("--history takes no --by-task — per-task dollars are per-session")
        if args.no_subagents:
            sys.exit("--by-task needs subagent transcripts — drop --no-subagents")
        if args.session is None and not args.demo:
            sys.exit("--by-task requires --session — per-task dollars attribute one "
                     "session's transcripts")

    # --envelope guardrails (U4, PLAN E3): rides --history exactly like --snapshot/--trend
    # (checked after --by-task, before --demo, so every existing combo keeps its message) —
    # EXCEPT under --demo, where it is its own standalone synthetic path (mirrors --alarm,
    # which likewise needs no --history to run its demo). It takes no --session (it prices
    # per-class from pricing.json's task_profiles, never one session's transcripts) and no
    # kit positional, and — unlike --history itself — no repeated --kits-dir (no cross-repo
    # namespacing for the envelope card).
    if args.envelope:
        if args.live or args.by_task:
            sys.exit("--envelope takes no --live/--by-task")
        if args.alarm:
            sys.exit("--envelope takes no --alarm")
        if args.snapshot or args.trend:
            sys.exit("--envelope takes no --snapshot/--trend")
        if args.session is not None:
            sys.exit("--envelope takes no --session — it prices per-class from "
                     "pricing.json, not one session's transcripts")
        if args.kit:
            sys.exit("--envelope takes no kit argument")
        if not args.demo and not args.history:
            sys.exit("--envelope rides --history — pass --history")
        if len(args.kits_dir) > 1:
            sys.exit("--envelope takes one --kits-dir (no cross-repo namespacing)")

    # Repeatable --kits-dir is a --history affordance only; more than one value in any other
    # mode is an error. Placed after the --by-task guardrails and before the --demo block so
    # every existing combo keeps its existing message.
    if len(args.kits_dir) > 1 and not args.history:
        sys.exit("multiple --kits-dir values are a --history affordance — pass one dir")

    # --snapshot/--trend rejections (PLAN D6). Both ride --history (so they inherit ALL of
    # its mutual exclusions above with today's messages); --snapshot never runs under --demo
    # (the demo writes only to its own temp dir). Placed with the other new rejections, after
    # the --by-task guardrails and before the --demo block.
    if args.snapshot and not args.history:
        sys.exit("--snapshot rides --history — pass --history")
    if args.trend and not args.history:
        sys.exit("--trend rides --history — pass --history")
    if args.snapshot and args.demo:
        sys.exit("--demo takes no --snapshot — the demo writes only to its own temp dir")

    if args.demo:
        if args.kit:
            sys.exit("--demo takes no kit argument")
        if args.alarm:
            if args.live or args.by_task:
                sys.exit("--alarm takes no --live/--by-task")
            # T11 / Phase 1 F7: a NEW, standalone demo path -- ``--demo --alarm`` --
            # that never touches run_demo/run_history_demo's own fixtures or goldens.
            # ``--trend`` (default on) prints the tripped D11 alarm; ``--demo --alarm
            # --history`` (no --trend) prints day 2's plain history view instead, the
            # one that carries the Escalation lineage + Failure breakdown sections.
            return run_alarm_demo(args.json, trend=not args.history or args.trend)
        if args.envelope:
            return run_envelope_demo(args.json)
        if args.history and args.trend:
            return run_trend_demo(args.json)
        if args.history:
            return run_history_demo(args.json)
        if args.live:
            return run_live_demo(args.json)
        if args.by_task:
            return run_by_task_demo(args.json)
        return run_demo(args.json)

    if args.envelope:
        return run_envelope(args)

    if args.history and args.trend and not args.snapshot:
        return run_trend(args)

    if args.history:
        return run_history(args)

    if not args.kit:
        sys.exit("kit slug required (or --demo)")

    kit_dir = _resolve_kit_dir(args.kit, args.kits_dir[0])
    kit_name = kit_dir.name
    if not kit_dir.is_dir():
        sys.exit(f"kit dir not found: {kit_dir}")
    tasks_path = kit_dir / "TASKS.md"
    if not tasks_path.is_file():
        sys.exit(f"TASKS.md not found: {tasks_path}")

    try:
        tasks = ce.parse_tasks(tasks_path.read_text(errors="replace"))
    except ValueError as e:
        sys.exit(f"malformed TASKS.md: {e}")

    if args.live:
        # Quality-only, read-only live signal. Returns BEFORE any pricing load: the
        # live path never calls cr.load_pricing(), never writes, and never folds in
        # dollars (which is why --live + --session is rejected up top).
        live_notes = []
        notes_path = kit_dir / "NOTES.md"
        if notes_path.is_file():
            # Read the ledger ONCE and feed BOTH the outcome and reroute parsers.
            notes_text = notes_path.read_text(errors="replace")
            outcomes, out_notes = parse_outcomes(notes_text)
            events, rr_notes = parse_reroutes(notes_text)
            live_notes.extend(out_notes)
            live_notes.extend(rr_notes)
        else:
            outcomes, events = {}, []
            live_notes.append(
                f"no NOTES.md at {notes_path} — live signal limited to TASKS.md statuses")
        plan_path = kit_dir / "PLAN.md"
        plan_text = (plan_path.read_text(errors="replace")
                     if plan_path.is_file() else None)
        autonomy, auto_notes = parse_autonomy(plan_text)
        live_notes.extend(auto_notes)
        decision = upgrade_decision(
            tasks, outcomes, events,
            threshold=args.live_threshold, min_sample=args.live_min_sample,
            max_auto=args.live_max_auto)
        card = build_live_card(kit_name, decision, autonomy, live_notes)
        print(json.dumps(card, indent=2) if args.json else render_live_markdown(card))
        return 0

    notes = []
    notes_path = kit_dir / "NOTES.md"
    if notes_path.is_file():
        outcomes, parse_notes = parse_outcomes(notes_path.read_text(errors="replace"))
        notes.extend(parse_notes)
    else:
        outcomes = {}
        notes.append(f"no NOTES.md at {notes_path} — quality limited to TASKS.md statuses")

    pricing = cr.load_pricing()

    if args.session:
        try:
            cost, cost_notes = session_cost_summary(
                args.session, args.projects_dir, args.tasks_dir, args.include,
                args.no_subagents, args.vs, pricing)
        except ValueError as e:
            sys.exit(str(e))
        notes.extend(cost_notes)
    else:
        cost = None
        notes.append("no session provided — pass --session to fold in transcript dollars")

    card = build_scorecard(kit_name, tasks, outcomes, notes, cost=cost,
                           expensive_tiers=cr.EXPENSIVE_TIERS)

    if args.by_task:
        # Re-read NOTES.md (a SECOND read_text; the existing read above is untouched) for the
        # agent ledger. All by-task notes stay NESTED in card["by_task"]["notes"] — the card's
        # top-level notes are never touched, so the flag-off output is byte-identical.
        agent_text = notes_path.read_text(errors="replace") if notes_path.is_file() else ""
        events, agent_notes = parse_agents(agent_text)
        task_dirs = args.tasks_dir or sc.discover_task_dirs(args.session)
        output_map, disc_notes = discover_agent_outputs(task_dirs)
        main_transcript = sc.find_main_transcript(args.session, args.projects_dir)
        bt = build_by_task(tasks, events, output_map, main_transcript, cost, pricing)
        bt["notes"] = list(agent_notes) + list(disc_notes) + list(bt["notes"])
        card["by_task"] = bt

    print(json.dumps(card, indent=2) if args.json else render_markdown(card))
    return 0


if __name__ == "__main__":
    main()
