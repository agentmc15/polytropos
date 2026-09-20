#!/usr/bin/env python3
"""Evaluate complete workflows on held-out tasks, and change routing policy only through a
reviewed, versioned, reversible proposal (step 25).

    workflow_eval.py plan     --repo DIR --harness H --models m1,m2 [--workflows W,..] [--policies P,..]
                              [--repeats N] [--test-cmd CMD] [--mode ..] [--limit N] [--json]
    workflow_eval.py run      ...same... --live --max-usd CEILING [--max-dispatches N] [--store-dir DIR]
    workflow_eval.py card     --run ID [--store-dir DIR] [--json]
    workflow_eval.py adjudicate --run ID --trial T --by WHO --verdict solved|not-solved|unsure [--note ..]
    workflow_eval.py list     [--store-dir DIR]
    workflow_eval.py propose  --run ID --set workflow=W [--set policy=P] [--task-class C] --by WHO
    workflow_eval.py review   --proposal ID --by WHO --decision accept|reject [--note ..]
    workflow_eval.py apply    --proposal ID
    workflow_eval.py rollback [--to VERSION]
    workflow_eval.py policy   [--json]
    workflow_eval.py demo

WHAT IS COMPARED. Not models in isolation -- `bin/repo_bench.py` already does that -- but
WORKFLOWS: the same held-out task, from the same clean snapshot, through `direct` (one
dispatch and the oracle), `reviewed` (one dispatch, then an independent read-only review whose
verdict is recorded and never becomes the grade), and `kit` (the task run as a one-task
execution kit through `bin/kit_contract.py`: claim, budget admission, the task's own check
under the execution boundary, projection, the attempt ledger). Each workflow runs under a
model choice that is `pinned` (the operator named it) or routed by step 19's `reserved` /
`adaptive` policy, with the decision recorded. Repeats are counterbalanced: the order in which
variants meet a task rotates per repeat, so one stochastic result never reads as a ranking.

WHAT IS MEASURED, per variant: accepted completion (the tests oracle alone -- `solved` never
comes from a reviewer, a judge, or the kit's own check), escaped defects (the workflow's own
acceptance disagreeing with the oracle: an INCORRECT ACCEPTANCE), human interventions
(adjudications, resumes), wall-clock, TOTAL workflow usage (every stage, per basis: reported,
estimated, subscription proxy, credits, unpriced -- never summed together), evidence coverage,
a Wilson interval and the evidence floor, stability across repeats, and the security outcomes
the roadmap names: evidence tampering (test paths touched), policy violations (the host attested
a different model), capability refusals, budget overshoot, resume correctness, privacy
eligibility (a statement redacted before dispatch; counts by kind, never values).

WHAT THIS REUSES, AND NEVER FORKS. Mining, sandboxes, prompts, oracles, ceilings and the store
layout are `repo_bench`'s (`mine_tasks`, `prepare_cell_sandbox`, `build_prompt`, `oracle_tests`,
`oracle_structural`, `would_exceed_ceiling`, `new_run_dir`); each harness's argv is its own
driver's builder and its dollars its own pricing file through its own estimator; every dispatch
is recorded before and after in `bin/attempt_ledger.py` and read back through
`bin/attempt_history.py` with tiers from `bin/model_registry.py`. The kit workflow is the
contract, not a copy of a driver.

MONEY. Nothing here spends by default. `run` dispatches only behind BOTH `--live` and
`--max-usd`, re-checks the ceiling before every priced dispatch, and honours a hard operation
cap (`--max-dispatches`, which is what bounds a harness whose dispatches carry no price). The
plan names its caps and says which figures are estimates: a ceiling stops the NEXT dispatch, it
is not a provider-side guarantee, and a subscription harness's figure is a relative-burn proxy,
never a bill. `plan`, `card`, `demo`, and every test spend nothing.

MATERIAL. A run's tasks are not a flat list any more: they are admitted into an immutable,
content-addressed manifest (`MANIFEST_VERSION`, one file per manifest under the run's own
`manifests/` directory, written once and never rewritten) with four partitions -- development,
calibration, promotion, audit. Related issue and mutation VARIANTS of one defect are grouped
and move together, because a group split across partitions is how a held-out result turns out
to have been solved in development already. Calibration is the only partition a fit may touch
and therefore the one partition whose result is never evidence. A problem statement carrying a
reference patch, a future fix message, a fix commit sha or a hidden label is screened out by
kind and count (never by value) and its whole group is quarantined. Exposure and retirement are
an append-only log beside the manifest: a fact recorded, not a permission granted. A cohort is
declared before its results exist or it is refused. NONE of that is enforced by the hashing --
see `NOT_ENFORCEMENT_LABEL`: a digest detects a rewrite, it prevents nothing, and an isolation
boundary is `bin/exec_policy.py`'s question, not a manifest's.

POLICY. `prefs/routing-policy.json` changes only through `propose` (refused below the evidence
floor, on a single repeat, or when the run's tasks already backed the applied policy),
`review` (a person, by name), and `apply` (refused unreviewed, rejected, or stale against the
file it would replace); every version is kept and `rollback` restores one. Nothing in this
repository reads that file automatically: consumption is pull-only, and a driver keeps
reading its kit's PLAN.md until someone wires the applied default in on purpose.
"""

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_VERSION = "polytropos.workflow-eval/1"
PROPOSAL_VERSION = "polytropos.policy-proposal/1"
POLICY_VERSION = "polytropos.routing-policy/1"

WORKFLOWS = ("direct", "reviewed", "kit")
#: The dispatching stages of each workflow; `check` and `project` dispatch nothing.
WORKFLOW_STAGES = {
    "direct": ("implement",),
    "reviewed": ("implement", "review"),
    "kit": ("implement", "check", "project"),
}
POLICIES = ("pinned", "reserved", "adaptive")
HARNESSES = ("claude", "codex", "copilot", "cursor", "stub")
#: The registry key each adapter's capabilities live under (`primitives/harness-capabilities.json`).
REGISTRY_KEYS = {"claude": "claude-code", "codex": "codex", "copilot": "copilot",
                 "cursor": "cursor", "stub": "stub"}
#: What `reviewed` needs from a host, by registry row. `unsupported` refuses the variant;
#: `unknown` runs it labelled unverified (the routing policy's own rule for shapes).
REVIEW_CAPABILITY = "independent_review"
#: Cost bases, `attempt_history.COST_BASES` plus the honest absence. Never added together.
BASES = ("model-reported", "estimated", "proxy", "credits", "unpriced")
ROBUSTNESS = ("incorrect_acceptance", "evidence_tampering", "policy_violation",
              "capability_refusal", "budget_overshoot", "resume", "privacy")
ADJUDICATIONS = ("solved", "not-solved", "unsure")
DEFAULT_REPEATS = 1
DEFAULT_TIMEOUT_SECONDS = 1800
PATCH_PROMPT_CHARS = 20000
STATEMENT_CHARS = 8000
ORDER_STAGES = ("implement", "review")

REVIEW_GRADE_RE = re.compile(r"REVIEW\s+VERDICT=(accept|reject|unsure)", re.IGNORECASE)
REVIEW_INSTRUCTIONS = (
    "You are reviewing a patch written by someone else for the task above. You may read the "
    "repository; you must not change it. Decide whether the patch resolves the task correctly "
    "and completely.\n\nRespond with EXACTLY one line in this grammar, followed by your "
    "rationale on the lines after it:\n\nREVIEW VERDICT=<accept|reject|unsure>\n"
)
ESTIMATE_LABEL = "est. from task_profiles at each harness's own rates -- not a bill"
PROXY_LABEL = ("subscription proxy: an API-equivalent relative-burn figure, never a bill; "
               "billed_usd stays null")
UNPRICED_LABEL = "unpriced: the harness reports no usage and its pricing file carries no rate"
CEILING_NOTE = ("a --max-usd ceiling stops the NEXT priced dispatch; the one in flight completes "
                "and is recorded, so a single-dispatch overshoot is possible and is labelled, not "
                "prevented -- it is not a provider-side guarantee")
NOT_A_RANKING = ("not a ranking: every compared variant must clear the evidence floor and be "
                 "repeated at least twice before an order is stated")
SOLVED_LABEL = ("`solved` = the tests oracle passed on a constructed substrate that withholds "
                "the reference tests -- never a reviewer's verdict, the kit's own check, or a "
                "human adjudication, which are recorded beside it")
#: The claims a card carries whatever the run measured. Which harnesses have never run live
#: is NOT in this tuple: that fact lives in the registry's `workflow_evaluation` rows and is
#: read from there by `untested_claims()`, so the sentence cannot go stale the way a constant
#: did on 2026-09-16, when the first live run on Claude Code left "no workflow has been run
#: live from this repository on any harness" in its own results envelope.
UNTESTED_CLAIMS = (
    "no universal superiority of any workflow, policy, model, or harness is supported; a "
    "variant ranks only within one run, one repository, one instruction version",
    "repricing an observed trace at another harness's rates is a hypothetical comparison, "
    "not evidence that harness would have produced the same result",
    "graph-grounded versus targeted-search prompting is not a variant axis here",
    "lesson versions are not a variant axis here; instruction versions are",
    "the reviewer's read-only mode is the CLI's documented flag, not an OS boundary; only the "
    "kit workflow's check runs under bin/exec_policy.py",
)

_SIBLINGS = {}


def untested_claims():
    """`UNTESTED_CLAIMS`, prefixed by which harnesses' `workflow_evaluation` rows the registry
    still records as unverified -- the registry's word, never a constant's."""
    ha = _ha()
    unrun = []
    for name, key in REGISTRY_KEYS.items():
        if name == "stub":
            continue
        try:
            row = ha.registry_capabilities(key).get("workflow_evaluation")
        except (OSError, ValueError, KeyError):
            row = None
        if row is None or ha.effective(row) != "supported":
            unrun.append(key)
    head = ()
    if unrun:
        head = (f"no workflow has been run live from this repository on {', '.join(unrun)}: "
                f"the registry's `workflow_evaluation` row is unverified there, and every figure "
                f"a live run would produce is unmeasured",)
    return head + UNTESTED_CLAIMS


def _sibling(name):
    if name not in _SIBLINGS:
        path = Path(__file__).resolve().with_name(f"{name}.py")
        spec = importlib.util.spec_from_file_location(f"polytropos_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLINGS[name] = module
    return _SIBLINGS[name]


def _rb():
    return _sibling("repo_bench")


def _kc():
    return _sibling("kit_contract")


def _al():
    return _kc()._al()


def _ah():
    return _sibling("attempt_history")


def _mr():
    return _sibling("model_registry")


def _rp():
    return _sibling("routing_policy")


def _ha():
    return _sibling("harness_adapter")


def _ep():
    return _sibling("exec_policy")


def _pr():
    return _sibling("proc_runner")


def _rd():
    return _sibling("redact")


def _dc():
    return _sibling("decision_contract")


def _de():
    """`bin/decision_eval.py`, loaded by the D23 activation gate for its PREDECLARATION
    VOCABULARY and its own `operator_plan` validator.

    That module owns six of the stop fields a live evaluation must pin and says in its own
    comment that the other three are "workflow_eval.live_requirements's responsibility, not this
    module's". Neither half is the whole, and until D23 nothing composed them. The gate reads
    both owners rather than keeping a seventh list here.
    """
    return _sibling("decision_eval")


def _dp():
    """`bin/decision_policy.py`, loaded by the D23 activation reader for its MODE VOCABULARY.

    Which modes a selection can actually run in is that module's to declare -- `SELECTION_MODES`
    are the two it implements and `DEFERRED_MODES` the two it refuses by name. The pointer
    reader reads both at call time so a mode this repository cannot act on can never be the
    mode a pointer resolves a run to.
    """
    return _sibling("decision_policy")


def _store_default(name):
    rt = _sibling("runtime_data")
    return rt.store_path(name, REPO_ROOT)


DEFAULT_STORE_DIR = _store_default("evals")
DEFAULT_PREFS_DIR = _store_default("prefs")
POLICY_FILE = "routing-policy.json"
POLICY_HISTORY = "routing-policy.history"
POLICY_PROPOSALS = "routing-policy.proposals"
POLICY_JOURNAL = "routing-policy.journal.jsonl"


class EvalError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sha(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# ---- adapters on the repo_bench seam ----------------------------------------------------------------
#
# Each is the plain dict `repo_bench.dispatch_cell` already takes (`name`, `build_argv(bin,
# model, prompt)`, `extract_usage`, `load_pricing`) plus what a workflow needs: a read-only
# review argv, the host's observed model, the harness's own estimator and price, its tier order
# for routing, and its registry key. Every `build_argv` accepts `task_id=` / `workspace=`
# keywords so a prompt-only CLI can name the task and pin its directory.

def _first_of_tier(pricing, word, tier_order):
    """A model id, or the first model in file order carrying tier `word`; KeyError otherwise."""
    models = pricing.get("models") or {}
    if word in models:
        return word
    if word in tier_order:
        for mid, info in models.items():
            if info.get("tier") == word:
                return mid
    raise KeyError(f"unknown model or tier {word!r}; valid ids: {', '.join(models) or '(none)'}")


def claude_adapter():
    rb, ce = _rb(), _sibling("claude_execute")

    def build_argv(bin_, model, prompt, task_id=None, workspace=None):
        return rb.build_claude_argv(bin_, model, prompt)

    def build_review_argv(bin_, model, prompt, task_id=None, workspace=None):
        profile = ce.permission_profile(("Read", "Grep", "Glob"), bypass=False,
                                        source="reviewer: restricted (no bypass)")
        # 2026-09-16, first live run: without the JSON envelope the review's token counts were
        # unreadable and every review stage fell back to the plan estimate while the implement
        # stage beside it was model-reported. Same format args as the implement form.
        return ce.build_dispatch(bin_, model, prompt, extra_args=rb.OUTPUT_FORMAT_ARGS,
                                 permissions=profile)

    def estimate(model, profile, pricing):
        return {"basis": "estimated", "usd": rb.estimate_dispatch_usd(model, profile, pricing),
                "label": ESTIMATE_LABEL}

    def price(model, usage, pricing):
        usd = rb.price_usage(model, usage, pricing) if usage else None
        return None if usd is None else {"basis": "model-reported", "usd": usd,
                                         "label": "priced from harness-reported token counts"}

    return {
        "name": "claude", "registry": REGISTRY_KEYS["claude"], "binary": rb.DEFAULT_CLAUDE_BIN,
        "billing": "api", "build_argv": build_argv, "build_review_argv": build_review_argv,
        "extract_usage": rb.extract_usage, "observed_model": lambda output: None,
        "load_pricing": rb.claude_pricing_loader, "estimate": estimate, "price": price,
        "tier_order": tuple(ce.TIER_ORDER), "default_tier": ce.DEFAULT_ESCALATION_START,
        "resolve_model": ce.resolve_model, "review_mode": "restricted permissions (no bypass; "
                                                          "Read, Grep, Glob)",
    }


def codex_adapter():
    cx, cp, pol = _sibling("codex_execute"), _sibling("codex_pricing"), _sibling("codex_policy")

    def build_argv(bin_, model, prompt, task_id=None, workspace=None):
        return cx.build_dispatch(bin_, model, prompt)

    def build_review_argv(bin_, model, prompt, task_id=None, workspace=None):
        return cx.build_dispatch(bin_, model, prompt, extra_args=["--sandbox", "read-only"])

    def estimate(model, profile, pricing):
        est = cp.est_cost(pricing, profile, model)
        return {"basis": "proxy", "usd": None, "api_equivalent_usd": est["usd_api"],
                "burn_index_vs_cheapest": est["subscription"]["burn_index_vs_cheapest"],
                "label": PROXY_LABEL}

    return {
        "name": "codex", "registry": REGISTRY_KEYS["codex"], "binary": "codex",
        "billing": "subscription", "build_argv": build_argv,
        "build_review_argv": build_review_argv, "extract_usage": lambda output: None,
        "observed_model": lambda output: None, "load_pricing": cp.load_pricing,
        "estimate": estimate, "price": lambda model, usage, pricing: None,
        "tier_order": tuple(pol.TIER_ORDER), "default_tier": cx.DEFAULT_ESCALATION_START,
        "resolve_model": cp.resolve_model, "review_mode": "--sandbox read-only",
    }


def copilot_adapter():
    cpe, cpp = _sibling("copilot_execute"), _sibling("copilot_pricing")

    def build_argv(bin_, model, prompt, task_id=None, workspace=None):
        return cpe.build_dispatch("implementer", prompt, model=model, copilot_bin=bin_)

    def build_review_argv(bin_, model, prompt, task_id=None, workspace=None):
        return cpe.build_dispatch("reviewer", prompt, model=model, copilot_bin=bin_,
                                  allow_all_tools=False)

    def estimate(model, profile, pricing):
        est = cpp.est_cost(pricing, profile, model)
        return {"basis": "estimated", "usd": est["usd"], "credits": est["aic"],
                "credit_unit": pricing["billing_unit"]["name"], "label": ESTIMATE_LABEL}

    return {
        "name": "copilot", "registry": REGISTRY_KEYS["copilot"], "binary": "copilot",
        "billing": "credits", "build_argv": build_argv, "build_review_argv": build_review_argv,
        "extract_usage": lambda output: None, "observed_model": lambda output: None,
        "load_pricing": cpp.load_pricing, "estimate": estimate,
        "price": lambda model, usage, pricing: None, "tier_order": tuple(cpe.TIER_ORDER),
        "default_tier": cpe.DEFAULT_ESCALATION_START,
        "resolve_model": lambda pricing, word: _first_of_tier(pricing, word, cpe.TIER_ORDER),
        "review_mode": "reviewer agent without --allow-all-tools",
    }


def cursor_adapter():
    ca, cue = _sibling("cursor_adapter"), _sibling("cursor_execute")

    def build_argv(bin_, model, prompt, task_id=None, workspace=None):
        return ca.build_dispatch({"id": task_id}, model_id=model, prompt=prompt, cursor_bin=bin_,
                                 workspace=workspace)

    def build_review_argv(bin_, model, prompt, task_id=None, workspace=None):
        return ca.build_dispatch({"id": task_id}, model_id=model, prompt=prompt, cursor_bin=bin_,
                                 workspace=workspace, read_only=True)

    def estimate(model, profile, pricing):
        return {"basis": "unpriced", "usd": None, "label": UNPRICED_LABEL}

    return {
        "name": "cursor", "registry": REGISTRY_KEYS["cursor"], "binary": ca.BINARY,
        "billing": "unpriced", "build_argv": build_argv, "build_review_argv": build_review_argv,
        "extract_usage": lambda output: None,
        "observed_model": lambda output: ca.parse_output(output or "")["observed_model"],
        "load_pricing": cue.load_pricing, "estimate": estimate,
        "price": lambda model, usage, pricing: None, "tier_order": (), "default_tier": None,
        "resolve_model": lambda pricing, word: word, "review_mode": "--mode ask",
    }


def stub_adapter():
    """The conformance harness: a throwaway executable, no pricing, nothing verified."""

    def build_argv(bin_, model, prompt, task_id=None, workspace=None):
        return [bin_, "--task", task_id or "-", "--model", model or "-", "--workspace",
                str(workspace or "."), prompt]

    def build_review_argv(bin_, model, prompt, task_id=None, workspace=None):
        return build_argv(bin_, model, prompt, task_id=task_id, workspace=workspace)[:-1] + \
            ["--mode", "ask", prompt]

    def observed(output):
        m = re.search(r"OBSERVED-MODEL=(\S+)", output or "")
        return m.group(1) if m else None

    return {
        "name": "stub", "registry": REGISTRY_KEYS["stub"], "binary": "stub",
        "billing": "unpriced", "build_argv": build_argv, "build_review_argv": build_review_argv,
        "extract_usage": lambda output: None, "observed_model": observed,
        "load_pricing": lambda: {"cached_date": None, "models": {}, "task_profiles": {}},
        "estimate": lambda model, profile, pricing: {"basis": "unpriced", "usd": None,
                                                     "label": UNPRICED_LABEL},
        "price": lambda model, usage, pricing: None, "tier_order": (), "default_tier": None,
        "resolve_model": lambda pricing, word: word, "review_mode": "--mode ask (stub)",
    }


ADAPTERS = {"claude": claude_adapter, "codex": codex_adapter, "copilot": copilot_adapter,
            "cursor": cursor_adapter, "stub": stub_adapter}


def make_adapter(harness):
    if harness not in ADAPTERS:
        raise EvalError(f"unknown harness {harness!r}; choices: {', '.join(HARNESSES)}")
    return ADAPTERS[harness]()


def capability_states(adapter):
    """`{name: effective state}` from the registry for this adapter's harness."""
    ha = _ha()
    try:
        rows = ha.registry_capabilities(adapter["registry"])
    except (OSError, ValueError, KeyError):
        rows = {}
    return {name: ha.effective(row) for name, row in rows.items()}


# ---- variants and trials --------------------------------------------------------------------------------

def default_instructions():
    return _rb().PROMPT_INSTRUCTIONS


def instruction_version(text):
    return _sha(text)[:12]


def build_variants(harness, models, workflows, policies, instructions=None, review_model=None):
    """Every (workflow, policy, model, instruction version) combination -> a list of variants."""
    instructions = list(instructions) if instructions else [("builtin", default_instructions())]
    variants = []
    for workflow in workflows:
        if workflow not in WORKFLOWS:
            raise EvalError(f"unknown workflow {workflow!r}; choices: {', '.join(WORKFLOWS)}")
        for policy in policies:
            if policy not in POLICIES:
                raise EvalError(f"unknown policy {policy!r}; choices: {', '.join(POLICIES)}")
            model_axis = list(models) if policy == "pinned" else [None]
            for model in model_axis:
                for label, text in instructions:
                    vid = f"{harness}/{workflow}/{policy}" + (f":{model}" if model else "") + \
                        (f"@{label}" if len(instructions) > 1 else "")
                    variants.append({
                        "id": vid, "harness": harness, "workflow": workflow, "policy": policy,
                        "model": model, "review_model": review_model or model,
                        "instructions": label, "instruction_version": instruction_version(text),
                        "instruction_text": text,
                    })
    return variants


def trial_matrix(tasks, variants, repeats):
    """Counterbalanced trials: the variant order rotates by one per repeat, per task."""
    trials = []
    n = 0
    for r in range(int(repeats)):
        shift = r % len(variants) if variants else 0
        order = variants[shift:] + variants[:shift]
        for task in tasks:
            for v in order:
                n += 1
                trials.append({"trial": f"t{n:03d}", "task_id": task["task_id"],
                               "variant": v["id"], "repeat": r + 1, "order": n})
    return trials


def redacted_statement(task):
    rd = _rd()
    raw = (task.get("statement") or task.get("subject") or "").strip()
    out = rd.redact(raw, limit=STATEMENT_CHARS)
    return out["text"], {"redactions": out["redactions"], "truncated": out["truncated"]}


def build_stage_prompt(task, variant, preamble=""):
    """The implement prompt: redacted statement + the variant's instructions -- leak-free."""
    statement, privacy = redacted_statement(task)
    body = f"{statement}\n\n{variant['instruction_text']}"
    return (f"{preamble}\n\n{body}" if preamble else body), privacy


def build_review_prompt(task, patch, preamble=""):
    rd = _rd()
    statement, _privacy = redacted_statement(task)
    shown = rd.redact(patch or "", limit=PATCH_PROMPT_CHARS)["text"]
    body = (f"{statement}\n\n{REVIEW_INSTRUCTIONS}\n\n--- candidate patch ---\n{shown}\n"
            f"--- end of patch ---\n")
    return f"{preamble}\n\n{body}" if preamble else body


def parse_review(output):
    m = REVIEW_GRADE_RE.search(output or "")
    return {"verdict": m.group(1).lower() if m else None, "parsed": bool(m)}


# ---- costs ------------------------------------------------------------------------------------------------

def stage_cost(adapter, model, profile, pricing, usage):
    """One dispatch's cost with its basis: reported tokens priced from the harness's own file,
    else the harness's own estimate (which for a subscription harness is a proxy, and for one
    with no rates is `unpriced`). Never a number without a basis."""
    priced = adapter["price"](model, usage, pricing) if usage else None
    if priced:
        return priced
    try:
        return adapter["estimate"](model, profile, pricing)
    except (KeyError, ValueError, TypeError) as exc:
        return {"basis": "unpriced", "usd": None, "label": f"{UNPRICED_LABEL} ({exc})"}


def empty_totals():
    return {"model-reported": {"n": 0, "usd": 0.0}, "estimated": {"n": 0, "usd": 0.0},
            "proxy": {"n": 0, "api_equivalent_usd": 0.0}, "credits": {"n": 0, "credits": 0.0},
            "unpriced": {"n": 0}, "note": "bases are separate facts and are never summed"}


def add_cost(totals, cost):
    basis = cost.get("basis")
    if basis in ("model-reported", "estimated"):
        totals[basis]["n"] += 1
        totals[basis]["usd"] = round(totals[basis]["usd"] + float(cost.get("usd") or 0.0), 6)
        if cost.get("credits") is not None:
            totals["credits"]["n"] += 1
            totals["credits"]["credits"] = round(totals["credits"]["credits"] + float(cost["credits"]), 4)
    elif basis == "proxy":
        totals["proxy"]["n"] += 1
        totals["proxy"]["api_equivalent_usd"] = round(
            totals["proxy"]["api_equivalent_usd"] + float(cost.get("api_equivalent_usd") or 0.0), 6)
    else:
        totals["unpriced"]["n"] += 1
    return totals


def priced_usd(cost):
    """What counts against a USD ceiling: only a figure with a priced basis."""
    if cost.get("basis") in ("model-reported", "estimated") and cost.get("usd") is not None:
        return float(cost["usd"])
    return 0.0


def _accrue_wall(total, extra):
    """Add a stage's measured `wall_seconds` to a running total without coercing "never
    measured" into "measured zero" (decision-improvement D05). `extra` is `None` for a stage
    that was skipped before any dispatch (routing refusal, a budget stop, a reused prior
    verdict) -- genuinely nothing to add, not an unknown -- and is left out rather than treated
    as `+= 0.0`. `total`
    stays `None` for as long as nothing has ever been added to it, so a trial or a variant that
    never dispatched anything reports `wall_seconds: None` (unmeasured) rather than `0.0`
    (measured and took no time), the same distinction `cost_totals` keeps for money."""
    if extra is None:
        return total
    return (total or 0.0) + extra


# ---- routing ---------------------------------------------------------------------------------------------------

def route_stage(adapter, pricing, variant, task, role, profile):
    """The model for one stage: the pin, or step 19's decision under the variant's policy."""
    if variant["policy"] == "pinned":
        model = variant["model"] if role == "implementer" else (variant.get("review_model") or variant["model"])
        return {"model": adapter["resolve_model"](pricing, model) if model else None,
                "decision": None, "refusal": None}
    rp = _rp()
    tiers = tuple(adapter["tier_order"])
    if not tiers:
        return {"model": None, "decision": None,
                "refusal": f"{adapter['name']} records no tier order; nothing is routable"}

    def estimator(model_id):
        # The routing policy's own estimate shape (codex_policy.default_estimator's): an
        # API-equivalent figure per model, labelled by the decision, never a bill.
        est = adapter["estimate"](model_id, profile, pricing)
        usd = est.get("usd") if est.get("usd") is not None else est.get("api_equivalent_usd")
        return {"api_equivalent_usd": usd, "profile": profile}

    catalog = rp.catalog_from_pricing(pricing, adapter["name"], tiers, estimator=estimator)
    request = {"planned": variant.get("model"), "role": role, "evidence": None,
               "brief_chars": len(task.get("statement") or ""), "tiers": tiers,
               "default_tier": adapter.get("default_tier"), "capabilities": capability_states(adapter),
               "harness": adapter["name"], "task_id": task["task_id"], "in_kit": variant["workflow"] == "kit"}
    try:
        decision = rp.decide(catalog, request, policy=variant["policy"])
    except rp.RoutingError as exc:
        return {"model": None, "decision": None, "refusal": str(exc)}
    return {"model": decision["model"], "decision": rp.explain(decision),
            "refusal": decision["refusal"]}


# ---- the plan -----------------------------------------------------------------------------------------------

def build_plan(target_repo, harness, models, workflows=("direct",), policies=("pinned",),
               repeats=DEFAULT_REPEATS, mode="auto", limit=8, test_cmd=None, commit=None,
               scratch_dir=None, git_runner=None, test_runner=None, gh_runner=None, use_gh=False,
               exclude_subject=(), gh_repo=None, adapter=None, pricing=None, tasks_out=None,
               instructions=None, review_model=None, timeout=DEFAULT_TIMEOUT_SECONDS):
    """Mine the held-out tasks (repo_bench's miner), enumerate the variants and trials, price
    every dispatching stage at the harness's own rates, and name the hard caps -> a card."""
    rb = _rb()
    adapter = adapter or make_adapter(harness)
    pricing = pricing if pricing is not None else adapter["load_pricing"]()
    workflows, policies = tuple(workflows), tuple(policies)
    if "kit" in workflows and not test_cmd:
        raise EvalError("the kit workflow needs --test-cmd: its check is the repository's own "
                        "test command, run under the execution boundary")
    resolved = []
    for m in models:
        mid = adapter["resolve_model"](pricing, m)
        if mid not in resolved:
            resolved.append(mid)
    if "pinned" in policies and not resolved:
        raise EvalError("--models names no model, and the pinned policy has nothing to pin")
    mined = rb.mine_tasks(target_repo, mode=mode, limit=limit, test_cmd=test_cmd, commit=commit,
                          scratch_dir=scratch_dir, git_runner=git_runner, test_runner=test_runner,
                          gh_runner=gh_runner, use_gh=use_gh, exclude_subject=exclude_subject,
                          gh_repo=gh_repo)
    tasks = mined["tasks"]
    if tasks_out is not None:
        tasks_out.extend(tasks)
    variants = build_variants(harness, resolved, workflows, policies, instructions=instructions,
                              review_model=review_model)
    caps = capability_states(adapter)
    review_state = caps.get(REVIEW_CAPABILITY, "unknown")
    refused = []
    kept = []
    for v in variants:
        if v["workflow"] == "reviewed" and review_state == "unsupported":
            refused.append({"variant": v["id"], "reason": f"capability {REVIEW_CAPABILITY} is "
                                                          f"unsupported on {harness}"})
        else:
            kept.append(v)
    trials = trial_matrix(tasks, kept, repeats)
    stages = []
    totals = empty_totals()
    privacy = {}
    for task in tasks:
        _text, priv = redacted_statement(task)
        if priv["redactions"]:
            privacy[task["task_id"]] = priv["redactions"]
    dispatches = 0
    checks = 0
    for t in trials:
        v = next(x for x in kept if x["id"] == t["variant"])
        task = next(x for x in tasks if x["task_id"] == t["task_id"])
        for stage in WORKFLOW_STAGES[v["workflow"]]:
            if stage in ORDER_STAGES:
                role = "implementer" if stage == "implement" else "reviewer"
                routed = route_stage(adapter, pricing, v, task, role, task["size_profile"])
                cost = (stage_cost(adapter, routed["model"], task["size_profile"], pricing, None)
                        if routed["model"] else {"basis": "unpriced", "usd": None,
                                                  "label": routed["refusal"] or "no model"})
                stages.append({"trial": t["trial"], "stage": stage, "model": routed["model"],
                               "cost": cost, "refusal": routed["refusal"]})
                if not routed["refusal"]:
                    dispatches += 1
                    add_cost(totals, cost)
            elif stage == "check":
                checks += 1
    caps_card = {
        "max_dispatches": dispatches,
        "max_check_runs": checks + (len(trials) if test_cmd else 0),
        "max_wall_seconds": dispatches * timeout,
        "dispatch_timeout_seconds": timeout,
        "note": ("hard operation caps: a live run refuses the dispatch that would exceed "
                 "--max-dispatches (default: this count), whatever its price; wall time is "
                 "bounded per dispatch by the process runner"),
    }
    labels = [ESTIMATE_LABEL, SOLVED_LABEL]
    if review_state == "unknown" and any(v["workflow"] == "reviewed" for v in kept):
        labels.append(f"reviewed workflow on {harness}: {REVIEW_CAPABILITY} is unverified in the "
                      f"registry; the review runs as {adapter['review_mode']}")
    if privacy:
        labels.append(f"privacy: {len(privacy)} task statement(s) carry credential shapes and "
                      f"are dispatched REDACTED (counts by kind in the card; never the value)")
    return {
        "v": EVAL_VERSION, "repo": str(target_repo), "base_commit": mined["base_commit"],
        "mode": mined["mode"], "mode_reason": mined["mode_reason"], "harness": harness,
        "registry": _mr().registry().versions(), "pricing_date": pricing.get("cached_date"),
        "candidates": resolved, "workflows": list(workflows), "policies": list(policies),
        "repeats": int(repeats), "test_cmd": test_cmd,
        "tasks": [{"task_id": t["task_id"], "size_profile": t["size_profile"],
                   "oracle_tests_available": t["oracle_tests_available"], "mode": t["mode"],
                   "privacy_redactions": privacy.get(t["task_id"], {})} for t in tasks],
        "variants": [{k: v for k, v in x.items() if k != "instruction_text"} for x in kept],
        "refused_variants": refused, "trials": trials, "stages": stages, "totals": totals,
        "caps": caps_card, "spend_notes": [CEILING_NOTE, PROXY_LABEL, UNPRICED_LABEL],
        "labels": labels + list(mined["labels"]), "notes": list(mined["notes"]),
        "evidence_floor": rb.MIN_EVIDENCE_TASKS,
    }


def render_plan_markdown(card):
    lines = [f"# workflow-eval plan — {card['repo']}", "",
             f"base commit: {card['base_commit']}",
             f"mode: {card['mode']} — {card['mode_reason']}",
             f"harness: {card['harness']} (pricing {card['pricing_date'] or 'none'}; registry "
             f"{card['registry']})",
             f"workflows: {', '.join(card['workflows'])}; policies: {', '.join(card['policies'])}; "
             f"models: {', '.join(card['candidates']) or '(routed)'}; repeats: {card['repeats']}",
             ""]
    lines.append(f"## tasks ({len(card['tasks'])}; evidence floor {card['evidence_floor']} per variant)")
    for t in card["tasks"]:
        extra = f"  privacy={t['privacy_redactions']}" if t["privacy_redactions"] else ""
        lines.append(f"  - {t['task_id']}  size={t['size_profile']}  class={t['mode']}  "
                     f"oracle_tests_available={t['oracle_tests_available']}{extra}")
    lines.append("")
    lines.append(f"## variants ({len(card['variants'])}) and trials ({len(card['trials'])}, counterbalanced)")
    for v in card["variants"]:
        lines.append(f"  - {v['id']}  instructions={v['instructions']}@{v['instruction_version']}")
    for r in card["refused_variants"]:
        lines.append(f"  - REFUSED {r['variant']}: {r['reason']}")
    lines.append("")
    tot = card["totals"]
    lines.append("## total workflow usage (est., per basis — never summed)")
    lines.append(f"  model-reported: n={tot['model-reported']['n']}  estimated: n={tot['estimated']['n']} "
                 f"usd={tot['estimated']['usd']:.4f}  proxy: n={tot['proxy']['n']} "
                 f"api_equivalent_usd={tot['proxy']['api_equivalent_usd']:.4f}  credits: "
                 f"n={tot['credits']['n']} {tot['credits']['credits']:.2f}  unpriced: n={tot['unpriced']['n']}")
    lines.append("")
    caps = card["caps"]
    lines.append("## hard caps")
    lines.append(f"  max dispatches: {caps['max_dispatches']}; max check runs: {caps['max_check_runs']}; "
                 f"max wall: {caps['max_wall_seconds']}s ({caps['dispatch_timeout_seconds']}s per dispatch)")
    lines.append(f"  {caps['note']}")
    lines.append("")
    lines.append("## labels")
    for label in card["labels"]:
        lines.append(f"label: {label}")
    for note in card["spend_notes"]:
        lines.append(f"spend: {note}")
    for note in card["notes"]:
        lines.append(f"note: {note}")
    lines.append("")
    lines.append("to dispatch: add --live --max-usd <ceiling> (and --max-dispatches to lower the cap); "
                 "nothing above was dispatched")
    return "\n".join(lines)


# ---- the run ---------------------------------------------------------------------------------------------------

def default_runner(harness, timeout=DEFAULT_TIMEOUT_SECONDS):
    """A dispatch runner through the process runner, carrying only the harness's own env."""
    pr = _pr()

    def runner(argv, cwd):
        result = pr.run(argv, cwd=cwd, env=pr.dispatch_env(harness), timeout=timeout,
                        name=f"{harness} dispatch")
        output = (result.get("stdout") or "") + (("\n" + result["stderr"]) if result.get("stderr") else "")
        return result.get("rc"), output, result

    return runner


def _unpack(raw):
    """`(rc, output)` | `(rc, output, proc-or-telemetry)` -> `(rc, output, proc, telemetry)`."""
    if raw is None:
        return None, "", {}, {}
    if len(raw) == 2:
        return raw[0], raw[1] or "", {}, {}
    third = raw[2] if isinstance(raw[2], dict) else {}
    if "outcome" in third:
        return raw[0], raw[1] or "", third, {}
    return raw[0], raw[1] or "", {}, third


def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    s = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(max(0.0, (c - s) / d), 4), round(min(1.0, (c + s) / d), 4)]


# ---- immutable grouped partitions, exposure and leak screening -------------------------------
#
# WHY THIS EXISTS. A run's `holdout` used to be a flat list of task ids with no grouping, no
# content identity, and no record of what had already been seen. Three things go wrong with
# that shape, and each of them makes an evaluation lie to itself rather than fail loudly:
#
#   * two mined VARIANTS of the same underlying defect land on opposite sides of the split, so
#     the "held-out" result was already solved, in full view, in development;
#   * material a threshold or a calibrator was FIT on is later cited as held-out evidence,
#     which is not evidence at all -- it is the fit, read back;
#   * the cohort is chosen AFTER the results are in, and the tasks that happened to work are
#     the tasks that count.
#
# WHAT IS ADDRESSED BY CONTENT, AND WHAT THAT BUYS. Every item carries four identities -- code
# (repo + base commit), task (id, mode, defect key, statement digest), acceptance (the test
# command, whether an objective oracle exists, the withheld test blobs' digests) and artifact
# (the reference/setup patch digests) -- and its item id is the digest of exactly those. The
# manifest's own id is the digest of its whole immutable `content`. Recomputing an identity
# from a task record is therefore how staleness is detected: if the acceptance criteria moved,
# every id under them moves, and the old evidence is stale by construction rather than by
# somebody remembering.
#
# WHAT A DIGEST DOES NOT BUY, STATED ONCE AND MEANT: see NOT_ENFORCEMENT_LABEL. A hash detects
# a change; it stops nothing. The rules below are enforced by the controller functions in this
# module -- `build_manifest` (grouping, screening), `declare_cohort` / `select_cohort`
# (ordering), `require_held_out` (roles, exposure, retirement, staleness) -- and an actual
# isolation boundary, if this host has one at all, is `bin/exec_policy.py`'s question, which
# the decision-improvement kit's D07 asks and is allowed to answer `unavailable`.
#
# NOTHING HERE IS A SECOND WRITER. `bin/workflow_eval.py` persists manifests, into its own
# evals store, through `bin/safe_paths.py`'s confined create/append verbs -- the same
# primitives the attempt ledger uses. `bin/repo_bench.py` remains the only writer of the
# benchruns store and the owner of task mining and the content of a task record; this module
# takes identities OF those records and never writes one.

MANIFEST_VERSION = "polytropos.eval-manifest/1"

#: The subdirectory, under whatever root a caller gives the storage functions, where manifests
#: and their exposure logs live. `Evaluation` gives them its own run directory, because the
#: evals store's ROOT holds exactly the run directories and its readers walk it expecting that.
#: A pool partitioned once for a repository and shared across runs is a different root, chosen
#: by whoever owns that pool -- the functions take it as an argument, so a shared manifest set
#: is a different LOCATION and never a different writer. When that root is the store root,
#: `list_runs` skips this name rather than reporting it as a malformed run.
MANIFEST_DIR = "manifests"

NOT_ENFORCEMENT_LABEL = (
    "a content hash identifies and DETECTS change; it never prevents it. This manifest is "
    "tamper-evident, not tamper-proof: anything running with the user's own privileges can "
    "rewrite the file and recompute the digest. What is enforced here is enforced by the "
    "controller -- partition roles, one group to one partition, append-order of cohort "
    "declarations against results, leak screening, retirement -- and a digest, a worktree and "
    "a 0700 mode are none of them an isolation boundary."
)

#: The four partitions, their roles, and the one rule that matters between them: a partition
#: is EITHER somewhere a fit may happen or somewhere a result may be cited as evidence, never
#: both. Material that was fit on is spent; reading it back is reading the fit.
PARTITION_ROLES = {
    "development": {
        "purpose": "development", "fitting": True, "held_out": False, "single_use": False,
        "note": "iteration material: read it, break it, look at it as often as you like",
    },
    "calibration": {
        "purpose": "calibration-fitting", "fitting": True, "held_out": False,
        "single_use": False,
        "note": "the ONLY partition a calibrator or a threshold may be fit on, and therefore "
                "never citable as held-out evidence",
    },
    "promotion": {
        "purpose": "promotion-evidence", "fitting": False, "held_out": True,
        "single_use": False,
        "note": "held-out evidence for a promotion decision; no fit has ever seen it",
    },
    "audit": {
        "purpose": "audit-evidence", "fitting": False, "held_out": True, "single_use": True,
        "note": "the final held-out partition, and a single-use one: any exposure at all spends "
                "the material it touched, which is then retired rather than read twice",
    },
}
PARTITIONS = tuple(PARTITION_ROLES)

#: Where a leaking item goes. NOT a partition: nothing is ever selected from it, and its role
#: is absence of a role. Quarantine is contagious within a group -- see `build_manifest`.
QUARANTINE = "quarantine"
BUCKETS = PARTITIONS + (QUARANTINE,)

#: Why material was seen. Four of them are a partition's own role; `inspection` is the honest
#: word for a human or a tool having looked at material for any other reason, which is exactly
#: the kind of exposure an evaluation forgets to write down.
EXPOSURE_PURPOSES = ("development", "calibration-fitting", "promotion-evidence",
                     "audit-evidence", "inspection")

#: The append-only log's entry kinds. `result` is what makes post-hoc cohort selection
#: detectable: a cohort declared after results for its partition are known is not a cohort.
LOG_KINDS = ("cohort.declared", "exposure", "result", "retirement")

#: How much of a pool each partition draws, by weight. Weights, not counts: the allocation is
#: applied per DEFECT GROUP, so the item counts come out uneven and that is correct -- a
#: defect with six variants moves as one thing.
DEFAULT_ALLOCATION = {"development": 50, "calibration": 20, "promotion": 20, "audit": 10}

GROUPING_RULE = (
    "one defect, one group, one partition. A mined task is grouped by the defect it is a "
    "variant OF -- its issue, else its fix commit, else the path(s) its reference patch "
    "touches -- so related issue variants and mutation variants of the same defect are never "
    "split across partitions. The rule is deliberately COARSE: over-grouping costs only "
    "granularity, while under-grouping contaminates a held-out result, so where the two are "
    "in tension this groups."
)
ASSIGNMENT_RULE = (
    "a group's partition is a pure function of its defect key and the declared allocation -- "
    "not of the repository revision, the run id, the clock, or the order tasks were mined. "
    "That is load-bearing: if assignment moved when the code moved, yesterday's audit material "
    "would be today's development material and every audit result taken since would be "
    "contaminated by an exposure recorded under the old label."
)

#: What a candidate problem statement may never carry. `future-fix-message` includes the case
#: `repo_bench` itself labels "statement from commit message (weaker than issue text)": the
#: message of the commit that FIXED the defect did not exist when the defect did.
LEAK_KINDS = ("reference-patch", "future-fix-message", "fix-commit-identity", "hidden-label")

#: Markers that only ever appear beside an answer. Matched case-insensitively.
HIDDEN_LABEL_MARKERS = ("ANSWER-KEY", "GROUND-TRUTH", "GROUND TRUTH", "EXPECTED-VERDICT",
                        "ORACLE-VERDICT", "HIDDEN-LABEL", "SOLVED=", "EXPECTED_OUTPUT=")
#: Shapes that only a diff has.
DIFF_MARKERS = ("diff --git ", "--- a/", "+++ b/", "@@ -")
#: Below this many characters a line shared with the reference patch is a coincidence
#: (`return 2`, `}`, `import os`), not a leak. Above it, verbatim is verbatim.
MIN_LEAK_LINE_CHARS = 12

_DIFF_PATH_RE = re.compile(r"^diff --git a/(\S+) b/(\S+)\s*$", re.M)
_LABEL_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def _sp():
    return _sibling("safe_paths")


def _canonical(obj):
    """The ONE serialisation every digest in this section is taken over.

    `sort_keys` is what makes a digest independent of dict construction order, and the compact
    separators keep the bytes independent of anyone's formatter. Nothing that varies between
    two runs of the same inputs -- a timestamp, a temp path, a `set`'s iteration order -- may
    reach this function, which is why every collection below is sorted before it is stored.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _frozen(obj):
    """A deep copy through the canonical form: the rules a manifest carries are its own."""
    return json.loads(_canonical(obj))


def manifest_digest(content):
    """The sha256 of a manifest's immutable `content`. Nothing else is in it."""
    return _sha(_canonical(content))


def _normalised_allocation(allocation=None):
    """`[(partition, weight)]` in PARTITIONS order -- never dict order, which is an input."""
    alloc = dict(DEFAULT_ALLOCATION if allocation is None else allocation)
    unknown = sorted(set(alloc) - set(PARTITIONS))
    if unknown:
        raise EvalError(f"unknown partition(s) in the allocation: {', '.join(unknown)}; "
                        f"the four are {', '.join(PARTITIONS)}")
    out = []
    for name in PARTITIONS:
        weight = int(alloc.get(name, 0) or 0)
        if weight < 0:
            raise EvalError(f"allocation weight for {name!r} is negative")
        out.append((name, weight))
    if not sum(w for _, w in out):
        raise EvalError("the allocation gives every partition zero weight; nothing could be "
                        "assigned anywhere")
    return out


def partition_for(defect_key_value, allocation=None):
    """Which partition a DEFECT belongs to -- a pure function of its key (see ASSIGNMENT_RULE)."""
    alloc = _normalised_allocation(allocation)
    total = sum(w for _, w in alloc)
    draw = int(_sha("partition:" + str(defect_key_value))[:16], 16) % total
    upto = 0
    for name, weight in alloc:
        upto += weight
        if draw < upto:
            return name
    return alloc[-1][0]  # unreachable while total == sum(weights)


def patched_paths(patch):
    """Every path a unified diff names, sorted. `/dev/null` included: it is a path a diff names."""
    paths = set()
    for a, b in _DIFF_PATH_RE.findall(patch or ""):
        paths.add(a)
        paths.add(b)
    return sorted(paths)


def defect_key(task):
    """The underlying defect a mined task is a VARIANT of (GROUPING_RULE).

    Issue first (two mined pairs from one issue are one defect), then the fix commit, then the
    path(s) the reference patch touches -- which is what makes two mutation-repair variants of
    the same file one group. The final fallback is the task's own id, i.e. "a group of one",
    which is honest rather than clever: an unrecognisable task is not silently merged with
    anything.
    """
    issue = task.get("issue")
    if issue not in (None, "",):
        return f"issue:{issue}"
    fix = task.get("fix_commit")
    if fix:
        return f"fix:{fix}"
    paths = patched_paths(task.get("reference_patch")) or patched_paths(task.get("setup_patch"))
    if paths:
        return "site:" + "|".join(paths)
    return f"task:{task.get('task_id')}"


def _group_id(key):
    return _sha("group:" + str(key))[:12]


def _blob_digests(blobs):
    out = {}
    for path, blob in sorted((blobs or {}).items()):
        if isinstance(blob, bytes):
            out[str(path)] = hashlib.sha256(blob).hexdigest()
        elif isinstance(blob, str):
            out[str(path)] = _sha(blob)
        else:
            out[str(path)] = _sha(_canonical(blob))
    return out


def item_identity(task, repo, base_commit, acceptance=None, acceptance_sha=None):
    """The four identities an item is addressed by: code, task, acceptance, artifact.

    Digests, never payloads. The reference patch is the ANSWER; a manifest that stored it would
    be a leak vector of its own, so what is stored is its sha256 -- enough to notice it changed,
    useless for solving anything. Same reasoning as the attempt ledger's "a reference, never
    the payload".

    `acceptance` is the acceptance criterion's text (the repository's own test command) and is
    hashed here. `acceptance_sha` carries an ALREADY computed digest instead, which is what a
    freshness re-derivation has: the text is not stored, so a reader that never saw it cannot
    recompute it and must say so rather than pretend (see `verify_manifest`).
    """
    statement = task.get("statement") or ""
    subject = task.get("subject") or ""
    reference = task.get("reference_patch") or ""
    setup = task.get("setup_patch") or ""
    return {
        "code": {
            "repo": str(repo),
            "base_commit": task.get("base_commit") or base_commit,
        },
        "task": {
            "task_id": task.get("task_id"),
            "mode": task.get("mode"),
            "defect": defect_key(task),
            "statement_sha": _sha(statement),
            "statement_source": task.get("statement_source"),
            "subject_sha": _sha(subject) if subject else None,
            "size_profile": task.get("size_profile"),
        },
        "acceptance": {
            "test_cmd_sha": (acceptance_sha if acceptance_sha is not None
                             else (_sha(acceptance) if acceptance else None)),
            "oracle_tests_available": bool(task.get("oracle_tests_available")),
            "test_blobs": _blob_digests(task.get("test_blobs")),
        },
        "artifact": {
            "reference_patch_sha": _sha(reference) if reference else None,
            "setup_patch_sha": _sha(setup) if setup else None,
            "issue": task.get("issue"),
            "fix_commit": task.get("fix_commit"),
        },
    }


def item_id(identity):
    return _sha(_canonical(identity))[:16]


def _patch_lines(patch):
    """The added/removed lines of a diff, long enough that verbatim means verbatim."""
    out = []
    for line in (patch or "").splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line[:1] in ("+", "-"):
            text = line[1:].strip()
            if len(text) >= MIN_LEAK_LINE_CHARS:
                out.append(text)
    return out


def screen_statement(task, statement=None):
    """Leak findings for one candidate problem statement, by KIND and COUNT -- never by value.

    The repository's redaction rule ("report what was caught by kind and count, never the
    value") applies here for the same reason it applies to credentials: a finding that quotes
    the leak copies it somewhere new. And, as with `bin/redact.py`, shape-matching cannot prove
    absence -- an empty finding list means nothing matched these shapes, never that the
    statement is clean.
    """
    text = task.get("statement") if statement is None else statement
    text = text or ""
    found = []

    markers = sum(text.count(m) for m in DIFF_MARKERS)
    if markers:
        found.append({"kind": "reference-patch", "count": markers,
                      "evidence": "unified-diff markers in the statement"})
    shared = 0
    for patch in (task.get("reference_patch"), task.get("setup_patch")):
        shared += sum(1 for line in _patch_lines(patch) if line in text)
    if shared:
        found.append({"kind": "reference-patch", "count": shared,
                      "evidence": f"line(s) of >={MIN_LEAK_LINE_CHARS} chars shared verbatim "
                                  f"with the reference or setup patch"})

    subject = (task.get("subject") or "").strip()
    if len(subject) >= 8 and subject in text:
        found.append({"kind": "future-fix-message", "count": 1,
                      "evidence": "the fix commit's subject appears in the statement (this is "
                                  "what statement_source='commit-message' means)"})
    fix = (task.get("fix_commit") or "").strip()
    if len(fix) >= 7 and fix[:7] in text:
        found.append({"kind": "fix-commit-identity", "count": 1,
                      "evidence": "the fix commit's sha appears in the statement"})

    upper = text.upper()
    labels = sum(upper.count(m) for m in HIDDEN_LABEL_MARKERS)
    if labels:
        found.append({"kind": "hidden-label", "count": labels,
                      "evidence": "answer-key marker(s) in the statement"})
    blobs = task.get("test_blobs") or {}
    named = sum(1 for path in sorted(blobs) if str(path) and str(path) in text)
    if named:
        found.append({"kind": "hidden-label", "count": named,
                      "evidence": "the statement names withheld oracle test path(s)"})
    quoted = 0
    for path in sorted(blobs):
        blob = blobs[path]
        if isinstance(blob, bytes):
            try:
                blob = blob.decode("utf-8")
            except UnicodeDecodeError:
                continue
        for line in str(blob or "").splitlines():
            line = line.strip()
            if len(line) >= MIN_LEAK_LINE_CHARS and line in text:
                quoted += 1
    if quoted:
        found.append({"kind": "hidden-label", "count": quoted,
                      "evidence": "withheld oracle test content quoted in the statement"})

    merged = {}
    for finding in found:
        key = (finding["kind"], finding["evidence"])
        merged.setdefault(key, {"kind": finding["kind"], "count": 0,
                                "evidence": finding["evidence"]})["count"] += finding["count"]
    return [merged[k] for k in sorted(merged)]


def leak_summary(findings):
    """`{kind: count}` over a list of findings -- the shape a label may safely carry."""
    out = {}
    for finding in findings or []:
        out[finding["kind"]] = out.get(finding["kind"], 0) + int(finding["count"])
    return {k: out[k] for k in sorted(out)}


def build_manifest(repo, base_commit, tasks, *, allocation=None, on_leak="reject",
                   acceptance=None, cohorts=(), labels=(), created_by=None, created_at=None):
    """A pool of mined task records -> one immutable, content-addressed, grouped manifest.

    `on_leak="reject"` refuses the whole pool when any statement screens positive, naming kinds
    and counts and no values. `on_leak="quarantine"` admits the item, records its findings, and
    puts its WHOLE GROUP in `quarantine` -- never a partition -- because variants of one defect
    are one defect: knowing the answer to A is knowing the answer to B, so a leak in one variant
    spends them all. An evaluator that has already dispatched against its tasks uses the second
    form: the exposure happened, and refusing to write it down afterwards would lose the fact.

    `created_at` / `created_by` are provenance and are deliberately OUTSIDE the digest, so the
    same pool built twice is the same manifest.
    """
    if on_leak not in ("reject", "quarantine"):
        raise EvalError("on_leak must be 'reject' or 'quarantine'")
    alloc = _normalised_allocation(allocation)
    items, groups = {}, {}
    for task in tasks:
        identity = item_identity(task, repo, base_commit, acceptance=acceptance)
        iid = item_id(identity)
        key = identity["task"]["defect"]
        gid = _group_id(key)
        findings = screen_statement(task)
        items[iid] = {"item": iid, "task_id": task.get("task_id"), "group": gid,
                      "identity": identity, "leaks": findings}
        group = groups.setdefault(gid, {"group": gid, "key": key, "items": [], "leaks": {}})
        if iid not in group["items"]:
            group["items"].append(iid)
        for kind, count in leak_summary(findings).items():
            group["leaks"][kind] = group["leaks"].get(kind, 0) + count

    leaking = {gid: g["leaks"] for gid, g in groups.items() if g["leaks"]}
    if leaking and on_leak == "reject":
        kinds = {}
        for summary in leaking.values():
            for kind, count in summary.items():
                kinds[kind] = kinds.get(kind, 0) + count
        raise EvalError(
            f"{len(leaking)} defect group(s) carry a leaking problem statement "
            f"({', '.join(f'{k}={v}' for k, v in sorted(kinds.items()))}); a candidate statement "
            f"may not carry a reference patch, a future fix message, a fix commit identity or a "
            f"hidden label. Counts by kind only -- the values are never quoted. Pass "
            f"on_leak='quarantine' to record them instead, which keeps the whole group out of "
            f"every partition.")

    buckets = {name: [] for name in BUCKETS}
    for gid in sorted(groups):
        group = groups[gid]
        group["items"] = sorted(group["items"])
        group["partition"] = QUARANTINE if group["leaks"] else partition_for(group["key"], alloc)
        for iid in group["items"]:
            items[iid]["partition"] = group["partition"]
            buckets[group["partition"]].append(iid)
    for name in buckets:
        buckets[name] = sorted(buckets[name])

    declared = []
    for cohort in cohorts or ():
        declared.append(_validated_cohort(cohort, buckets))

    content = {
        "v": MANIFEST_VERSION,
        "repo": str(repo),
        "base_commit": base_commit,
        "rules": {
            "partitions": _frozen(PARTITION_ROLES),
            "allocation": {name: weight for name, weight in alloc},
            "grouping": GROUPING_RULE,
            "assignment": ASSIGNMENT_RULE,
            "quarantine": ("a leak in one variant quarantines its whole group; quarantine is "
                           "not a partition and nothing is ever selected from it"),
            "leak_kinds": list(LEAK_KINDS),
            "on_leak": on_leak,
            "exposure_purposes": list(EXPOSURE_PURPOSES),
            "enforcement": NOT_ENFORCEMENT_LABEL,
        },
        "groups": {gid: groups[gid] for gid in sorted(groups)},
        "items": {iid: items[iid] for iid in sorted(items)},
        "partitions": buckets,
        "cohorts": declared,
        "labels": sorted({NOT_ENFORCEMENT_LABEL, *(labels or ())}),
    }
    sha = manifest_digest(content)
    return {
        "v": MANIFEST_VERSION,
        "id": sha[:16],
        "sha": sha,
        "digest": {
            "algorithm": "sha256",
            "canonical": "json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=True)",
            "over": "content",
            "excludes": ["created_at", "created_by", "id", "sha", "digest"],
            "note": NOT_ENFORCEMENT_LABEL,
        },
        "created_at": created_at or _now(),
        "created_by": created_by or "",
        "content": content,
    }


def _validated_cohort(cohort, buckets):
    """A predeclared cohort: a named subset of ONE partition, fixed in the immutable content."""
    name = str(cohort.get("cohort") or "")
    partition = cohort.get("partition")
    if not _LABEL_RE.match(name):
        raise EvalError(f"cohort id {name!r} must match {_LABEL_RE.pattern}")
    if partition not in PARTITIONS:
        raise EvalError(f"cohort {name!r}: unknown partition {partition!r}")
    members = sorted(set(cohort.get("items") or []))
    stray = [i for i in members if i not in buckets.get(partition, [])]
    if stray:
        raise EvalError(f"cohort {name!r} names {len(stray)} item(s) that are not in the "
                        f"{partition} partition")
    return {"cohort": name, "partition": partition, "items": members,
            "declared_by": str(cohort.get("declared_by") or ""),
            "note": str(cohort.get("note") or "")}


def manifest_ref(manifest):
    """The reference an envelope carries: id, content digest, contract version. Never a payload."""
    if not manifest:
        return None
    return {"id": manifest["id"], "sha": manifest["sha"], "v": manifest["v"]}


def manifest_summary(manifest):
    """Counts only -- what the card and the envelope may repeat without copying the manifest.

    `enforcement` travels with the counts because this summary is what `Evaluation.run` embeds in
    `results.json` under `holdout.manifest`, and a reader of the envelope ALONE would otherwise
    see partition counts with nothing saying they are tamper-evident rather than enforced. The
    disclaimer is inside the manifest file's own `content.rules`, where it is inside the digest;
    this is the same sentence reaching the envelope, and it is a copy of a label, never a second
    authority (Phase 2 review, F5).
    """
    content = manifest["content"]
    return {
        "enforcement": NOT_ENFORCEMENT_LABEL,
        "items": len(content["items"]),
        "groups": len(content["groups"]),
        "partitions": {name: len(content["partitions"].get(name) or []) for name in BUCKETS},
        "quarantined": len(content["partitions"].get(QUARANTINE) or []),
        "leaks": leak_summary([f for item in content["items"].values() for f in item["leaks"]]),
        "allocation": dict(content["rules"]["allocation"]),
    }


# ---- storage: one owner, create-once, append-only ---------------------------------------------

def _manifest_root(store_dir):
    root = Path(store_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _manifest_rel(manifest_id, suffix=".json"):
    mid = _sp().validate_id(manifest_id, "manifest id")
    return f"{MANIFEST_DIR}/{mid}{suffix}"


def write_manifest(store_dir, manifest):
    """Persist a manifest under the evals store. Create-once, and idempotent for the same bytes.

    `safe_paths.confined_create_bytes` is `O_EXCL`: the "is this name free" and the write are
    one kernel operation, and a symlink at the leaf counts as taken rather than being followed.
    Writing the same manifest twice is a no-op that KEEPS THE FIRST (so its `created_at` is the
    real one); writing different content under the same id is refused loudly, because with a
    content-addressed id that means either a sha256 collision or a rewrite.
    """
    sp = _sp()
    root = _manifest_root(store_dir)
    rel = _manifest_rel(manifest["id"])
    body = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    try:
        sp.confined_create_bytes(root, rel, body.encode("utf-8"), what="eval manifest")
    except sp.SafePathExists:
        raw = sp.confined_read_bytes(root, rel, what="eval manifest")
        existing = json.loads(raw.decode("utf-8"))
        if _canonical(existing.get("content")) != _canonical(manifest["content"]):
            raise EvalError(
                f"manifest {manifest['id']} already exists with DIFFERENT content: an id is the "
                f"digest of the content it names, so this is a rewrite (or a sha256 collision), "
                f"not a re-run. Nothing was overwritten.") from None
    return root / MANIFEST_DIR / f"{manifest['id']}.json"


def read_manifest(store_dir, manifest_id):
    """Load a manifest and re-derive its identity. A rewritten file fails here, not later.

    Two checks, and they are the chain of custody such as it is: the digest of `content` must
    still be the `sha` the file carries, and that sha's prefix must still be the id the file is
    FILED under. A tamperer who recomputes the digest changes the id and therefore the filename,
    and the reference in whatever envelope pointed here stops resolving. That is detection, not
    prevention -- see NOT_ENFORCEMENT_LABEL.
    """
    root = Path(store_dir)
    raw = (_sp().confined_read_bytes(root, _manifest_rel(manifest_id), what="eval manifest",
                                     missing_ok=True) if root.is_dir() else None)
    if raw is None:
        raise EvalError(f"no manifest {manifest_id!r} under {store_dir}")
    manifest = json.loads(raw.decode("utf-8"))
    if manifest.get("v") != MANIFEST_VERSION:
        raise EvalError(f"manifest {manifest_id!r} is not a {MANIFEST_VERSION} manifest")
    sha = manifest_digest(manifest.get("content") or {})
    if sha != manifest.get("sha"):
        raise EvalError(f"manifest {manifest_id!r} does not match its own digest: its content "
                        f"has been rewritten since it was written")
    if not str(manifest_id).startswith(sha[:16]) or manifest.get("id") != sha[:16]:
        raise EvalError(f"manifest {manifest_id!r} is filed under an id that is not its content "
                        f"digest ({sha[:16]})")
    return manifest


def _append_log(store_dir, manifest_id, entry):
    root = _manifest_root(store_dir)
    line = _canonical(entry) + "\n"
    _sp().confined_append_bytes(root, _manifest_rel(manifest_id, ".log.jsonl"),
                                line.encode("utf-8"), what="eval manifest log")
    return entry


def exposure_log(store_dir, manifest_id):
    """`(entries, notes)`: every line of the append-only log, in order, with `seq` = position.

    An unparseable line is counted and skipped, never treated as evidence -- the attempt
    ledger's rule, for the same reason: a corrupt line must not silently become an absence.
    """
    root = Path(store_dir)
    entries, notes = [], []
    if not root.is_dir():
        return entries, notes
    raw = _sp().confined_read_bytes(root, _manifest_rel(manifest_id, ".log.jsonl"),
                                    what="eval manifest log", missing_ok=True)
    if raw is None:
        return entries, notes
    for n, line in enumerate(raw.decode("utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            notes.append(f"line {n + 1}: unreadable")
            continue
        if not isinstance(entry, dict) or entry.get("kind") not in LOG_KINDS:
            notes.append(f"line {n + 1}: not a {MANIFEST_VERSION} log entry")
            continue
        entry["seq"] = len(entries)
        entries.append(entry)
    return entries, notes


def _known_items(manifest, items, what):
    known = manifest["content"]["items"]
    chosen = sorted(set(items))
    stray = [i for i in chosen if i not in known]
    if stray:
        raise EvalError(f"{what}: {len(stray)} item id(s) are not in manifest {manifest['id']}")
    return chosen


def record_exposure(store_dir, manifest, *, partition, purpose=None, items=None, by="",
                    run=None, note=""):
    """Write down that material was SEEN. A fact, never a permission.

    Nothing about this call decides whether the material may still be used: that is
    `require_held_out`'s question, asked later, over this log. Recording an exposure of
    quarantined material is allowed and correct -- the exposure happened.
    """
    if partition not in BUCKETS:
        raise EvalError(f"unknown partition {partition!r}")
    purpose = purpose or (PARTITION_ROLES.get(partition) or {}).get("purpose") or "inspection"
    if purpose not in EXPOSURE_PURPOSES:
        raise EvalError(f"unknown exposure purpose {purpose!r}; the vocabulary is "
                        f"{', '.join(EXPOSURE_PURPOSES)}")
    if items is None:
        items = list(manifest["content"]["partitions"].get(partition) or [])
    chosen = _known_items(manifest, items, "exposure")
    return _append_log(store_dir, manifest["id"], {
        "v": MANIFEST_VERSION, "kind": "exposure", "manifest": manifest["id"],
        "partition": partition, "purpose": purpose, "items": chosen, "by": str(by or ""),
        "run": run, "note": str(note or ""), "at": _now(),
    })


def record_results(store_dir, manifest, *, partition, run=None, by="", note=""):
    """Write down that results over a partition are now KNOWN. This is what closes selection."""
    if partition not in BUCKETS:
        raise EvalError(f"unknown partition {partition!r}")
    return _append_log(store_dir, manifest["id"], {
        "v": MANIFEST_VERSION, "kind": "result", "manifest": manifest["id"],
        "partition": partition, "run": run, "by": str(by or ""), "note": str(note or ""),
        "at": _now(),
    })


def retire(store_dir, manifest, *, items, reason, by=""):
    """Retire contaminated material. The manifest does not change -- retirement is a fact about
    exposure, and rewriting the manifest to drop an item would change its id and orphan every
    reference to it. Readers subtract the retired set at read time."""
    if not reason:
        raise EvalError("retirement needs a reason: contaminated material is retired on the "
                        "record, never quietly")
    chosen = _known_items(manifest, items or [], "retirement")
    if not chosen:
        raise EvalError("retirement names no item")
    return _append_log(store_dir, manifest["id"], {
        "v": MANIFEST_VERSION, "kind": "retirement", "manifest": manifest["id"],
        "items": chosen, "reason": str(reason), "by": str(by or ""), "at": _now(),
    })


def declare_cohort(store_dir, manifest, *, partition, cohort, items, by="", note=""):
    """Declare a named cohort of one partition BEFORE its results exist.

    Refused once a `result` entry for that partition is in the log: a cohort chosen after the
    outcomes are known is not a cohort, it is a conclusion. The refusal is on the log's ORDER,
    not on a clock, so it survives a machine whose time moved.
    """
    if partition not in PARTITIONS:
        raise EvalError(f"unknown partition {partition!r}")
    if not _LABEL_RE.match(str(cohort or "")):
        raise EvalError(f"cohort id {cohort!r} must match {_LABEL_RE.pattern}")
    if not by:
        raise EvalError("--by is required: a predeclared cohort names who declared it")
    entries, _notes = exposure_log(store_dir, manifest["id"])
    if any(e["kind"] == "result" and e.get("partition") == partition for e in entries):
        raise EvalError(
            f"post-hoc cohort selection refused: results over the {partition} partition are "
            f"already recorded, so no cohort of it can be declared now. A cohort is declared "
            f"before the outcomes exist or it is not evidence.")
    if any(e["kind"] == "cohort.declared" and e.get("cohort") == str(cohort) for e in entries):
        raise EvalError(f"cohort {cohort!r} is already declared for manifest {manifest['id']}")
    chosen = _known_items(manifest, items or [], "cohort")
    members = set(manifest["content"]["partitions"].get(partition) or [])
    stray = [i for i in chosen if i not in members]
    if stray:
        raise EvalError(f"cohort {cohort!r} names {len(stray)} item(s) outside the {partition} "
                        f"partition")
    if not chosen:
        raise EvalError(f"cohort {cohort!r} names no item")
    return _append_log(store_dir, manifest["id"], {
        "v": MANIFEST_VERSION, "kind": "cohort.declared", "manifest": manifest["id"],
        "partition": partition, "cohort": str(cohort), "items": chosen, "by": str(by),
        "note": str(note or ""), "at": _now(),
    })


def exposure_state(store_dir, manifest):
    """What the log says, per partition and per item. Read-only; it decides nothing."""
    content = manifest["content"]
    entries, notes = exposure_log(store_dir, manifest["id"])
    partitions = {}
    for name in BUCKETS:
        members = list(content["partitions"].get(name) or [])
        partitions[name] = {
            "items": len(members), "exposures": 0, "purposes": {}, "fitted": False,
            "results_known": False, "results_at_seq": None, "cohorts": {},
            "retired": 0, "usable": len(members),
            "held_out": bool((PARTITION_ROLES.get(name) or {}).get("held_out")),
        }
    items = {iid: {"exposures": 0, "purposes": [], "retired": None}
             for iid in content["items"]}
    for entry in entries:
        name = entry.get("partition")
        row = partitions.get(name)
        if entry["kind"] == "exposure":
            if row is not None:
                row["exposures"] += 1
                purpose = entry.get("purpose")
                row["purposes"][purpose] = row["purposes"].get(purpose, 0) + 1
                if purpose == PARTITION_ROLES["calibration"]["purpose"]:
                    row["fitted"] = True
            for iid in entry.get("items") or []:
                if iid in items:
                    items[iid]["exposures"] += 1
                    if entry.get("purpose") not in items[iid]["purposes"]:
                        items[iid]["purposes"].append(entry.get("purpose"))
        elif entry["kind"] == "result":
            if row is not None and not row["results_known"]:
                row["results_known"] = True
                row["results_at_seq"] = entry["seq"]
        elif entry["kind"] == "cohort.declared":
            if row is not None:
                row["cohorts"][entry.get("cohort")] = entry["seq"]
        elif entry["kind"] == "retirement":
            for iid in entry.get("items") or []:
                if iid in items:
                    items[iid]["retired"] = {"reason": entry.get("reason"),
                                             "by": entry.get("by"), "seq": entry["seq"]}
    for name in BUCKETS:
        members = list(content["partitions"].get(name) or [])
        retired = [i for i in members if items.get(i, {}).get("retired")]
        partitions[name]["retired"] = len(retired)
        partitions[name]["usable"] = len(members) - len(retired)
    for iid, row in items.items():
        row["purposes"] = sorted(p for p in row["purposes"] if p)
    return {"manifest": manifest["id"], "partitions": partitions, "items": items,
            "entries": len(entries), "unreadable": len(notes), "notes": notes}


# ---- the controller: what the rules refuse ----------------------------------------------------

def verify_manifest(manifest, tasks=None, acceptance=None):
    """Structural and freshness findings over a manifest -> a list; `[]` is clean.

    What this catches: a digest that no longer matches its content, a group split across
    partitions, a partition list that disagrees with its items, a leaking item sitting in a
    real partition, and -- when `tasks` is supplied -- an item whose source record has moved
    since it was admitted (stale). What it CANNOT catch is a rewrite that fixes every one of
    those consistently, which is the whole of NOT_ENFORCEMENT_LABEL in one sentence.

    `acceptance` is the acceptance criterion the pool is being re-checked under. Without it the
    stored acceptance digest is carried over, so a CHANGED test command is not detected -- the
    text was never stored and cannot be re-derived from its own hash. Supply it to check that
    axis too; a changed command moves every item id under it.
    """
    findings = []
    if manifest.get("v") != MANIFEST_VERSION:
        findings.append({"kind": "version", "detail": f"not a {MANIFEST_VERSION} manifest"})
        return findings
    content = manifest.get("content") or {}
    sha = manifest_digest(content)
    if sha != manifest.get("sha") or manifest.get("id") != sha[:16]:
        findings.append({"kind": "digest",
                         "detail": "the content does not match the id/sha it is filed under"})
    items = content.get("items") or {}
    groups = content.get("groups") or {}
    buckets = content.get("partitions") or {}
    for name in buckets:
        if name not in BUCKETS:
            findings.append({"kind": "unknown-partition", "detail": name})
    listed = {}
    for name in BUCKETS:
        for iid in buckets.get(name) or []:
            listed.setdefault(iid, []).append(name)
    for iid, names in sorted(listed.items()):
        if iid not in items:
            findings.append({"kind": "membership", "item": iid,
                             "detail": f"listed in {', '.join(names)} but not an item"})
        elif len(names) > 1:
            findings.append({"kind": "membership", "item": iid,
                             "detail": f"listed in more than one bucket: {', '.join(names)}"})
        elif items[iid].get("partition") != names[0]:
            findings.append({"kind": "membership", "item": iid,
                             "detail": f"listed in {names[0]} but carries "
                                       f"{items[iid].get('partition')!r}"})
    for iid, item in sorted(items.items()):
        if iid not in listed:
            findings.append({"kind": "orphan", "item": iid,
                             "detail": "in no bucket at all"})
        if item.get("leaks") and item.get("partition") != QUARANTINE:
            findings.append({"kind": "leak-in-partition", "item": iid,
                             "detail": f"screened {leak_summary(item['leaks'])} but sits in "
                                       f"{item.get('partition')!r}"})
        gid = item.get("group")
        if gid not in groups:
            findings.append({"kind": "orphan", "item": iid, "detail": "in no group"})
    for gid, group in sorted(groups.items()):
        if gid != _group_id(group.get("key")):
            findings.append({"kind": "group-key", "group": gid,
                             "detail": "the group id is not the digest of its key"})
        homes = sorted({str(items[i].get("partition"))
                        for i in group.get("items") or [] if i in items})
        if len(homes) > 1:
            findings.append({
                "kind": "group-split", "group": gid, "detail":
                    f"the {len(group.get('items') or [])} variant(s) of defect "
                    f"{group.get('key')!r} are split across {', '.join(homes)} -- a held-out "
                    f"result over any of them was already seen through the others"})
        elif homes and group.get("partition") not in homes:
            findings.append({"kind": "group-split", "group": gid,
                             "detail": f"the group says {group.get('partition')!r}, its items "
                                       f"say {', '.join(homes)}"})
    if tasks is not None:
        by_id = {t.get("task_id"): t for t in tasks}
        for iid, item in sorted(items.items()):
            task = by_id.get(item.get("task_id"))
            if task is None:
                findings.append({"kind": "stale", "item": iid,
                                 "detail": f"task {item.get('task_id')!r} is gone from the pool"})
                continue
            stored_sha = (item.get("identity") or {}).get("acceptance", {}).get("test_cmd_sha")
            fresh = item_identity(
                task, content.get("repo") or "", content.get("base_commit"),
                acceptance=acceptance,
                acceptance_sha=None if acceptance is not None else stored_sha)
            if item_id(fresh) == iid:
                continue
            moved = sorted(k for k in ("code", "task", "acceptance", "artifact")
                           if _canonical(fresh.get(k)) != _canonical(item["identity"].get(k)))
            findings.append({"kind": "stale", "item": iid,
                             "detail": f"{item.get('task_id')} has moved since it was admitted: "
                                       f"{', '.join(moved) or 'identity'} changed"})
    return findings


def _held_out_blockers(manifest, partition, state, chosen):
    role = PARTITION_ROLES.get(partition) or {}
    blockers = []
    if not role.get("held_out"):
        blockers.append(
            f"the {partition} partition's role is {'fitting' if role.get('fitting') else 'none'}"
            f", not held-out evidence: {role.get('note', '')}")
    row = state["partitions"].get(partition) or {}
    if row.get("fitted"):
        blockers.append(f"a calibration fit has been recorded against {partition}; material "
                        f"that was fit on is spent as evidence")
    for iid in chosen:
        item = state["items"].get(iid) or {}
        if item.get("retired"):
            blockers.append(f"{iid} was retired ({(item['retired'] or {}).get('reason')})")
        for purpose in item.get("purposes") or []:
            if purpose != role.get("purpose"):
                blockers.append(f"{iid} was already exposed for {purpose!r}, which is not "
                                f"{partition}'s own role -- retire it rather than cite it")
            elif role.get("single_use"):
                blockers.append(f"{iid} has already been exposed once and {partition} is "
                                f"single-use: read twice, it is not held out the second time")
    return blockers


def require_held_out(store_dir, manifest, partition, *, items=None, tasks=None, acceptance=None):
    """The usable item ids of a HELD-OUT partition, or `EvalError` naming every blocker.

    This is the controller. Everything it refuses -- a partition whose role is fitting, a
    partition a fit has touched, retired material, material exposed for something else, a split
    group, a stale identity, a leaking statement -- is refused by a rule the manifest carries in
    its own immutable content, and none of it is refused by the digest. The digest only says
    whether the rules being read are the rules that were written.
    """
    if partition not in PARTITIONS:
        raise EvalError(f"unknown partition {partition!r}; the four are {', '.join(PARTITIONS)}")
    findings = verify_manifest(manifest, tasks=tasks, acceptance=acceptance)
    state = exposure_state(store_dir, manifest)
    members = list(manifest["content"]["partitions"].get(partition) or [])
    chosen = _known_items(manifest, items, "held-out selection") if items is not None else members
    outside = [i for i in chosen if i not in members]
    blockers = _held_out_blockers(manifest, partition, state, chosen)
    if outside:
        blockers.append(f"{len(outside)} item(s) are not in the {partition} partition")
    for finding in findings:
        blockers.append(f"{finding['kind']}: {finding['detail']}")
    if state["unreadable"]:
        blockers.append(f"{state['unreadable']} unreadable line(s) in the exposure log: the "
                        f"record of what has been seen is incomplete")
    if not chosen:
        blockers.append(f"the {partition} partition is empty")
    if blockers:
        raise EvalError(f"{partition} cannot be cited as held-out evidence: "
                        + "; ".join(blockers))
    return sorted(chosen)


def select_cohort(store_dir, manifest, partition, *, cohort=None, items=None, purpose=None,
                  by="", run=None, tasks=None, acceptance=None, record=True):
    """Freeze the cohort a result will be reported over, and record the exposure.

    Three ways in, and only two of them exist:

      * the whole partition (`cohort=None`), which is the default and needs no declaration;
      * a cohort `declare_cohort` wrote down BEFORE any result over that partition;
      * naming items here -- which is refused, always. That is what post-hoc cohort selection
        looks like from the inside, and there is no argument for it that is not also an
        argument for choosing the cohort after seeing the results.

    The order check is re-applied at READ time, not only at declaration time: a declaration
    appended to the log out of band, after a result, is still refused here. It would not be
    refused by a rewrite of the whole log, which is the honest limit of a file-based record.
    """
    if items is not None:
        raise EvalError(
            "refusing an item list at selection time: a cohort is a rule declared before the "
            "results exist (declare_cohort), or it is the whole partition. Choosing items now "
            "is post-hoc cohort selection.")
    if partition not in PARTITIONS:
        raise EvalError(f"unknown partition {partition!r}")
    entries, _notes = exposure_log(store_dir, manifest["id"])
    result_seqs = [e["seq"] for e in entries
                   if e["kind"] == "result" and e.get("partition") == partition]
    chosen = list(manifest["content"]["partitions"].get(partition) or [])
    if cohort is not None:
        declarations = [e for e in entries
                        if e["kind"] == "cohort.declared" and e.get("cohort") == str(cohort)]
        if not declarations:
            declarations = [dict(c, seq=-1) for c in manifest["content"].get("cohorts") or []
                            if c.get("cohort") == str(cohort)]
        if not declarations:
            raise EvalError(f"cohort {cohort!r} was never declared for manifest "
                            f"{manifest['id']}; an undeclared cohort is a cohort chosen now")
        declaration = declarations[0]
        if declaration.get("partition") != partition:
            raise EvalError(f"cohort {cohort!r} was declared over "
                            f"{declaration.get('partition')!r}, not {partition!r}")
        if result_seqs and declaration.get("seq", -1) > min(result_seqs):
            raise EvalError(
                f"post-hoc cohort selection refused: cohort {cohort!r} was declared at log "
                f"position {declaration['seq']}, after results over {partition} were recorded "
                f"at position {min(result_seqs)}")
        chosen = list(declaration.get("items") or [])
    role = PARTITION_ROLES[partition]
    if role["held_out"]:
        chosen = require_held_out(store_dir, manifest, partition, items=chosen, tasks=tasks,
                                  acceptance=acceptance)
    else:
        findings = verify_manifest(manifest, tasks=tasks, acceptance=acceptance)
        if findings:
            raise EvalError(f"{partition} is not usable: "
                            + "; ".join(f"{f['kind']}: {f['detail']}" for f in findings))
        state = exposure_state(store_dir, manifest)
        retired = [i for i in chosen if (state["items"].get(i) or {}).get("retired")]
        chosen = sorted(i for i in chosen if i not in retired)
    if record:
        record_exposure(store_dir, manifest, partition=partition,
                        purpose=purpose or role["purpose"], items=chosen, by=by, run=run,
                        note=f"cohort {cohort}" if cohort else "whole partition")
    return sorted(chosen)


# =================================================================================================
# PROTECTED TRIAL / AUTOPROMOTION GATE (decision-improvement D08)
#
# WHY THIS EXISTS. D07 (`bin/exec_policy.py`) built an available boundary -- `ProtectedProfile`,
# `protected_profile_status`, `run_sentinels`, `certify_profile` -- but nothing in this repo
# calls any of it yet: a protected live trial (D18) and an autopromotion (D23) are the two future
# callers that will reach a provider runner while claiming that boundary applies. Before either
# exists, this is the AVAILABILITY question they must both answer first.
#
# WHAT THIS DOES NOT DO -- READ THIS BEFORE WIRING IT. It applies NO confinement. Nothing in this
# section constructs a `ProtectedProfile`, builds a `ProtectedLayout`, or calls `wrap_argv`;
# `ProtectedProfile` appears in this file only in prose -- this comment and the docstring that
# tells a caller how to adapt to it -- and in no executable line. `gate_protected_dispatch`
# hands `argv` to the runner it was given, verbatim and unwrapped, so on a host where D07's profile
# IS enforceable it dispatches exactly as unconfined as the runner itself is. Passing through this
# gate confines nothing; it only establishes that a boundary COULD be applied here, and the caller
# owns actually applying one. It also invents no new isolation mechanism, no new evidence shape and
# no fallback. `require_protected_trial` asks D07's own `ProfileStatus.require_enforced` the exact
# question D07 already answers, and an unavailable answer raises the SAME `SandboxUnavailable`
# with the SAME "NO trusted-host fallback" wording, only prefixed with which purpose was
# refused -- so a caller cannot mistake a refused autopromotion for a refused trial, and nothing
# here reads `unavailable` as permission to run unconfined. Offline synthetic analysis (`_demo`,
# `build_plan`, an ordinary `Evaluation` run through `self.runner`) and manual proposal drafting
# (`build_proposal`/`review_proposal`/`apply_proposal`/`rollback_policy`) call NEITHER this gate
# nor a protected profile at all, so an unavailable D07 profile never blocks and is never
# consulted by them.
#
# WHAT "RECORD SKIPPED SENTINELS" MEANS HERE. `protected_trial_evidence` calls D07's OWN
# `run_sentinels` on the unavailable path and passes its report through unreshaped -- the owning
# engine for sentinel evidence is `bin/exec_policy.py`, never this module. `run_sentinels`
# spawns nothing at all when the profile is unavailable (see `bin/exec_policy.py`): it returns
# immediately with every sentinel named and marked `"unavailable"`. On an enforced profile this
# function does NOT re-run the sentinel battery per dispatch -- that is a one-time, host-level
# certification D07's own suite already performs, not a per-trial cost.
# =================================================================================================

#: The two purposes this gate refuses. Not an enum D07 needs to know about -- a plain word that
#: ends up in the refusal message and in the carried evidence, so a reader can tell them apart.
PROTECTED_LIVE_TRIAL = "protected live trial"
AUTOPROMOTION = "autopromotion"


def protected_trial_evidence(profile=None, status=None):
    """Typed, non-dispatching evidence for one named D07 profile. Never runs a model, a harness
    CLI or a provider runner. On an unavailable profile it calls D07's `run_sentinels`, which
    performs no live legs at all and returns immediately with every sentinel named and marked
    `unavailable` -- the cheap, honest 'record skipped sentinels' a refusal carries. On an
    enforced profile it reports the typed status only, without re-running the sentinel battery."""
    ep = _ep()
    profile = profile or ep.DEFAULT_PROTECTED_PROFILE
    status = ep.protected_profile_status(profile) if status is None else status
    evidence = {
        "profile": profile, "status": status.status, "mode": status.mode,
        "reason": status.reason, "missing": list(status.missing),
        "enforcement_label": ep.NOT_ISOLATION_LABEL,
    }
    if status.enforced:
        evidence.update(certified=None, sentinel_outcomes=None, sentinel_count=None)
        return evidence
    report = ep.run_sentinels(profile, status=status)
    certification = ep.certify_profile(report)
    evidence.update(
        certified=certification["certified"],
        sentinel_outcomes=sorted({row["outcome"] for row in report["sentinels"]}),
        sentinel_count=len(report["sentinels"]),
        enforcement_label=report["enforcement_label"],
    )
    return evidence


def _unavailable_classes(ep, status):
    """Every `SandboxUnavailable` class `status.require_enforced()` could actually raise.

    `bin/exec_policy.py` is loaded as a SEPARATE module object in several places --
    `bin/kit_contract.py`, `bin/copilot_ralph.py` and `bin/kit_verify_hook.py` each build their
    own via `spec_from_file_location`, and this module's `_ep()` loads it under the spec name
    `polytropos_exec_policy`. Each load defines a DISTINCT `SandboxUnavailable` class object, so
    a `ProfileStatus` handed in by a caller that loaded D07 through a different loader raises
    THAT loader's class, which `except _ep().SandboxUnavailable` does not catch. The refusal
    still refuses either way -- nothing dispatches -- but the purpose prefix, the `.evidence`
    attachment and therefore the envelope label and note are all silently lost.

    So resolve the exact class the bound method will raise, out of the module globals its own
    function object closes over, and catch that alongside ours. This deliberately does NOT widen
    the catch to `Exception`: an unrelated `AttributeError` or `TypeError` from a malformed
    status must keep propagating as itself, not be redressed as a profile refusal.
    """
    classes = [ep.SandboxUnavailable]
    method = getattr(type(status), "require_enforced", None)
    foreign = (getattr(method, "__globals__", None) or {}).get("SandboxUnavailable")
    if (isinstance(foreign, type) and issubclass(foreign, BaseException)
            and foreign not in classes):
        classes.append(foreign)
    return tuple(classes)


def require_protected_trial(purpose, profile=None, status=None):
    """Refuse `purpose` (`PROTECTED_LIVE_TRIAL` or `AUTOPROMOTION`) unless D07's named profile is
    enforced HERE, raising BEFORE returning -- so a caller that places its provider runner call
    after this one structurally cannot reach it on the unavailable path. There is no
    trusted-host fallback: `status.require_enforced()` is D07's own refusal, worded with that
    guarantee, and this function only prefixes which purpose was refused and attaches the typed
    evidence to the raised exception as `.evidence`, so a caller can carry it into its own
    result owner without recomputing it. A `status` built through a DIFFERENT loader's copy of
    `bin/exec_policy.py` raises that copy's `SandboxUnavailable`; `_unavailable_classes` resolves
    it so the prefix and the evidence survive the crossing (the re-raised refusal is always this
    module's own class, so a caller catches `_ep().SandboxUnavailable` either way). Returning
    grants no confinement -- see `gate_protected_dispatch`. Never call this from an offline or
    manual path -- they do not need it and it does not need them."""
    ep = _ep()
    profile = profile or ep.DEFAULT_PROTECTED_PROFILE
    status = ep.protected_profile_status(profile) if status is None else status
    evidence = protected_trial_evidence(profile, status=status)
    try:
        status.require_enforced()
    except _unavailable_classes(ep, status) as exc:
        refusal = ep.SandboxUnavailable(f"{purpose} refused -- {exc}")
        refusal.evidence = evidence
        raise refusal from exc
    return evidence


def carry_protected_evidence(envelope, evidence, purpose=PROTECTED_LIVE_TRIAL):
    """Append profile/refusal evidence into the SAME `labels`/`notes` an `Evaluation.run()`
    envelope already carries every other run-level caveat in (`"partial (cost-ceiling)"`,
    `"overspend: ..."`, `"aborted: ..."`) -- the existing result owner, never a second store or
    a new top-level key.

    The enforced-path label says ENFORCED, never "certified", and says out loud that this gate
    did not certify anything. Only `exec_policy.certify_profile` earns that word, over a real
    `run_sentinels` report, and this path deliberately calls neither -- `protected_trial_evidence`
    sets `certified=None` on exactly this branch, and the note below prints it. An envelope that
    asserted certification in its label and denied it in its note would be a contradiction a
    reader of `render_card_markdown`'s `## labels` section cannot see past. `protected_profile_status`
    is a platform/backend/usability answer whose own probe docstring says it is not a boundary;
    "enforceable here" is the most this text may claim."""
    if evidence["mode"] is None:
        label = f"{purpose}: profile {evidence['profile']!r} unavailable ({evidence['reason']})"
    else:
        label = (f"{purpose}: profile {evidence['profile']!r} enforced ({evidence['status']}) -- "
                 f"NOT certified by this gate; certification is exec_policy.certify_profile's "
                 f"over a sentinel report, and this path ran none")
    envelope.setdefault("labels", []).append(label)
    envelope.setdefault("notes", []).append(
        f"{purpose} sentinel outcomes: {evidence['sentinel_outcomes']}; "
        f"certified={evidence['certified']}; {evidence['enforcement_label']}"
    )
    return envelope


def gate_protected_dispatch(purpose, runner, argv, cwd, *, profile=None, status=None,
                            envelope=None):
    """Availability gate in front of one provider dispatch. THIS APPLIES NO CONFINEMENT.

    What it does: `require_protected_trial` runs FIRST, so an unavailable D07 profile refuses
    before `runner` is reached at all, and the typed evidence is carried into `envelope`'s own
    `labels`/`notes` (via `carry_protected_evidence`) on both the refused and the enforced path,
    never into a second store.

    What it does NOT do: it does not confine anything. It constructs no `ProtectedProfile`,
    builds no `ProtectedLayout`, and never calls `exec_policy.wrap_argv`. It calls
    `runner(argv, cwd)` with `argv` verbatim, so the dispatch is exactly as confined as `runner`
    itself already is and no more. CONFINEMENT IS THE SUPPLIED RUNNER'S RESPONSIBILITY. Returning
    from this function means "a boundary could be enforced on this host", never "a boundary was
    applied to this dispatch"; a caller that reads it as the latter ships a real, unconfined,
    money-spending dispatch under an envelope that says the profile is enforced.

    Adapting a real boundary to it: `exec_policy.ProtectedProfile.run` has the signature
    `(role, argv, timeout=..., cwd=None)`, while this gate's `runner` contract is the two-
    positional `(argv, cwd)` every other runner seam in this module uses. They do not match, so
    a caller wiring genuine confinement must adapt between them itself -- bind the role (and any
    timeout) and pass something like `lambda argv, cwd: profile.run(role, argv, cwd=cwd)`, having
    created `ProtectedLayout.REQUIRED_DIRS` first, since `exec_policy` creates nothing outside its
    own tempfile trees. Handing this gate a bare provider runner is the unconfined case.

    Offline synthetic analysis and manual proposal drafting never call this function: they
    dispatch through the ordinary `Evaluation.runner`, or nothing at all."""
    ep = _ep()
    profile = profile or ep.DEFAULT_PROTECTED_PROFILE
    status = ep.protected_profile_status(profile) if status is None else status
    try:
        evidence = require_protected_trial(purpose, profile=profile, status=status)
    except ep.SandboxUnavailable as exc:
        if envelope is not None:
            carry_protected_evidence(envelope, exc.evidence, purpose)
        raise
    if envelope is not None:
        carry_protected_evidence(envelope, evidence, purpose)
    result = runner(argv, cwd)
    return result, evidence


# =================================================================================================
# THREE-ARM RECOVERY TRIAL PROTOCOL (decision-improvement D18) -- A SPECIFICATION, NEVER A RUN
#
# WHAT THIS SECTION PRODUCES. One immutable, content-addressed EXPERIMENT SPECIFICATION for the
# kit's first hypothesis -- that on a narrow cohort of cross-module failures, one bounded package
# of previously missing contract context before a same-model retry improves accepted recovery or
# total resources without weakening quality -- plus the read-only accounting a future run's
# results would be read through. It produces no dispatch and no file.
#
# WHAT IT DELIBERATELY DOES NOT DO, AND HOW THAT IS MADE STRUCTURAL RATHER THAN PROMISED. No
# function below takes a runner, a dispatcher, a store, a directory or a path; none of them calls
# `gate_protected_dispatch`, `default_runner`, `Evaluation.run`, a `repo_bench` grader or a miner;
# none of them opens, writes or reads a file. A generated specification is not a completed run,
# and `require_runnable` refuses one for every precondition it cannot see satisfied -- which today
# is always at least one, because `CONFINED_DISPATCH_WIRED` is False and this module will not
# pretend otherwise.
#
# WHY D08'S GATE IS NAMED HERE AND NOT CALLED. `gate_protected_dispatch` is an AVAILABILITY gate:
# its own docstring leads with `THIS APPLIES NO CONFINEMENT.`, it hands `argv` to the supplied
# runner verbatim, and it records nothing in `bin/attempt_ledger.py`. Wiring it as it stands would
# produce a real, unconfined, unledgered, money-spending dispatch under an envelope saying the
# profile is enforced. Two obligations therefore travel together and are named together in
# `CONFINED_DISPATCH_WIRED`: a runner that actually confines, and the ledger open/close this
# repository requires of every dispatch. Until BOTH exist, a live trial is blocked here by
# derivation and not by anyone remembering. This section pins D07 as a REQUIREMENT of a live run
# rather than wiring a gate it cannot honestly complete.
#
# THE PAIRING NOTHING PREVIOUSLY NAMED (Phase 2 review, F4). D06's held-out controller and D08's
# isolation gate never composed: a caller that wired only the gate would get an envelope labelled
# "enforced" over a cohort with zero held-out evidence, and nothing said the two were both
# required. `live_requirements` names them side by side, and `build_trial_protocol` blocks on
# EITHER being unsatisfied -- satisfying one never discharges the other.
#
# EVERY ENFORCEMENT POINT CONSULTS THE THING IT ENFORCES -- INCLUDING ONE LEVEL DOWN (Phase 4
# review). `require_runnable` re-hashes the document it is handed, which stops a caller emptying
# `blockers`. That fixed the document and left the EVIDENCE the document is built from unchecked:
# four of the five rows `live_requirements` produces were discharged by a caller dict nobody
# consulted. A fabricated manifest (`sha` of the caller's choosing, invented partitions and
# items) reported `frozen: True` -- because a `manifest` argument was passed, not because
# anything was frozen -- and a hand-written `{"certified": True, "required": 7, "satisfied": 7,
# "blocking": []}` discharged D07 while `exec_policy` was never called at all. Content addressing
# was never the weak link: `build_trial_protocol` computed a perfectly CORRECT digest over forged
# inputs, so the forgery was INSIDE the digest. So `trial_cohort` now runs `verify_manifest` over
# the manifest and reads nothing out of one that fails, and `_certification_evidence` now takes
# the sentinel REPORT and asks `exec_policy.certify_profile` for the verdict instead of accepting
# one. What is left unauthenticated is named rather than glossed: a report that lies about what
# the OS did still certifies (running the sentinels spawns processes, which this section does
# not do), and the `whole-task-study` row is still a caller's claim that a run happened. Both say
# so in `re_derived_by`, which is None exactly where nothing re-derived the row.
#
# THE COHORT THE DEFAULT PIPELINE CANNOT PRODUCE (D06's product finding). `repo_bench`'s issue
# replay mining without `gh` -- which is the DEFAULT -- builds a problem statement out of the FIX
# COMMIT MESSAGE, which D06's screen correctly flags `future-fix-message`, which quarantines the
# whole defect group, which empties the promotion partition. So a protocol that simply assumed a
# usable held-out cohort would be assuming something the default pipeline cannot deliver.
# `trial_cohort` reads the actual partition out of the actual manifest, and an empty one is a
# `no-held-out-evidence` blocker that names the cause instead of a cohort of zero items dressed
# up as evidence.
#
# THE A=B COLLAPSE. Arm A is the ACTUAL frozen recovery policy, including any retry it already
# performs -- not an idealised do-nothing arm. When that policy already IS the control (one
# same-model extra attempt, the same diagnostics, no targeted package), A and B are the same
# protocol, and running them as two arms is one arm counted twice: it doubles the apparent sample,
# halves the apparent variance and compares a thing with itself. `collapse_equivalent_arms`
# compares arm SIGNATURES -- everything that defines the protocol, never the arm's own name -- and
# keeps one arm carrying both names in `collapsed_from`.
#
# WHAT "PINNED" MEANS. Six facts -- checkpoint, acceptance, model, effort, diagnostics, ceiling --
# live in ONE hashed object that every arm cites by `inputs_sha`. An arm citing a different sha is
# refused, so the arms cannot drift apart between construction and reading. Arm C may differ from
# arm B in exactly one field, `context_package`; a spec that changes the model and the context at
# once is refused by name, because it could not attribute its own result.
#
# WHAT THIS MODULE REFUSES TO INVENT. No sample size, no practical-gain threshold, no allowed
# quality regression, no stopping rule. Those are operator inputs; absent, they are reported as an
# incomplete specification and every corresponding field stays `None`. A number nobody measured
# must never appear as though somebody had.
# =================================================================================================

TRIAL_PROTOCOL_VERSION = "polytropos.trial-protocol/1"

#: The three arms of the first hypothesis, in the order the shared plan states them.
ARMS = ("A", "B", "C")

ARM_ROLES = {
    "A": ("baseline -- the ACTUAL frozen current recovery policy, including any retry it already "
          "performs. Never an idealised do-nothing arm: whatever the shipped policy does on this "
          "failure class is what arm A does, and if that already is arm B then they collapse"),
    "B": ("control -- the same permitted extra attempt, the same model, the same effort and the "
          "same diagnostics as arm C, and NO targeted context package"),
    "C": ("repair -- arm B plus ONE bounded package of previously missing contract context, then "
          "the declared remaining recovery path"),
}

#: The ONE field arm C is permitted to differ from arm B in. Changing the model and the context at
#: once makes the result unattributable, which the shared plan forbids in those words.
REPAIR_DIMENSION = "context_package"

#: Everything that defines an arm's protocol. The arm's own NAME is deliberately absent: two arms
#: that differ only by what they are called are one arm.
ARM_SIGNATURE_FIELDS = ("inputs_sha", "extra_attempts", "diagnostics_applied", "context_package",
                        "remaining_recovery")

#: The six facts every arm shares, hashed into one object. `pin_trial_inputs` refuses any absence.
PINNED_INPUTS = ("checkpoint", "acceptance", "model", "effort", "diagnostics", "ceiling")

#: Both scopes are reported, always. Recovery-only answers "given this failing checkpoint, did the
#: arm recover"; whole-task answers "what did the whole task cost", and the first attempt is in it
#: whether or not this arm re-ran it.
ACCOUNTING_SCOPES = ("recovery-only", "whole-task")

#: Everything that is a cost but not an attempt. Each row names its own scope, because the shared
#: plan puts planning, retrieval, decision, review, judging, proposer and experiment costs "at
#: their actual scope" rather than wherever a total happens to be convenient.
OVERHEAD_KINDS = ("failed-attempt", "planning", "retrieval", "decision", "review", "judging",
                  "proposer", "experiment")

#: What an OPERATOR declares before a live trial. This module supplies none of them and invents no
#: default for any of them; each missing one is a blocker naming itself.
OPERATOR_DECLARATIONS = ("primary_endpoint", "practical_gain_threshold",
                         "allowed_quality_regression", "sample_size", "stopping_rule",
                         "interim_look_rule", "independent_evaluation")

#: The closed vocabulary of reasons a specification is not a run. A reader never has to guess
#: whether a new string means something new.
#:
#: `manifest-unverified` and `no-held-out-evidence` are deliberately TWO codes and never one. A
#: manifest that does not match its own digest is a forgery finding and nothing may be read out of
#: it; a manifest that verifies and whose partition is simply empty is an honest document with
#: nothing in it, and the cause worth printing is D06's mining finding. A reader who could not
#: tell those apart would read a fabricated cohort as a thin one.
PROTOCOL_BLOCKERS = (
    "cohort-not-frozen",
    "manifest-unverified",
    "no-held-out-evidence",
    "protected-profile-uncertified",
    "confining-dispatch-unwired",
    "full-task-study-not-run",
    "operator-declaration-missing",
)

#: Whether this repository has a CONFINING, LEDGERED protected dispatch path. It does not, and the
#: two halves are one fact on purpose. `gate_protected_dispatch` applies no confinement (its own
#: docstring leads with that sentence and an AST test holds it there) and records nothing in
#: `bin/attempt_ledger.py`, which this repository requires of every dispatch, before and after.
#: Whoever wires a live protected trial flips this in the SAME edit that adds both -- and the D18
#: suite fails if either half moves without the other, so the flag cannot drift away from the code
#: it describes.
CONFINED_DISPATCH_WIRED = False

NOT_A_RUN_LABEL = (
    "experiment SPECIFICATION only: nothing here dispatched a model, restored a checkpoint, "
    "graded a candidate or spent anything. A generated specification is not a completed run, and "
    "no figure below was measured"
)

ARM_COLLAPSE_NOTE = (
    "arms with identical protocol signatures are ONE arm carrying both names, never two "
    "independent arms: counting a baseline that already is the control twice doubles the apparent "
    "sample and compares a thing with itself"
)

ANALYTIC_REUSE_LABEL = (
    "initial-attempt cost is attributed to every arm that starts from this checkpoint, INCLUDING "
    "an arm that reuses the checkpoint analytically rather than re-running the first attempt: "
    "the first attempt was not free because a later arm declined to repeat it. An attributed "
    "figure is not a second spend, and the reused count below says how many were attributed"
)

FAILURES_IN_TOTALS_LABEL = (
    "cohort totals carry EVERY item's resources -- accepted, failed and censored alike -- so cost "
    "per accepted task has the failures in its numerator, and is undefined (never 0, never "
    "omitted) when no task was accepted"
)

NO_INVENTED_NUMBER_LABEL = (
    "this module supplies no sample size and no success threshold: both are operator inputs, "
    "chosen from pilot variation and a useful effect size, and their absence is reported as an "
    "incomplete specification rather than filled in with a magic universal minimum"
)

CONDITIONAL_RECOVERY_NOTE = (
    "conditional recovery is P(accepted | this failing checkpoint was restored). Its denominator "
    "counts only RESOLVED outcomes; censored items are counted separately and never silently "
    "become failures. It says nothing about whole-task completion, which is the prospective "
    "full-task study's question"
)

FULL_TASK_STUDY_NOTE = (
    "matched checkpoints estimate CONDITIONAL recovery only. A prospective whole-task study -- "
    "first attempt to accepted or abandoned end, on its own predeclared inputs -- is required "
    "before general rollout and is NOT satisfied by the checkpoint study, however it came out: "
    "the checkpoint cohort conditions on having already failed once, which the population a "
    "rollout would touch does not"
)

RESOURCE_ORACLE_LABEL = (
    "resources: cost by basis and wall time, bases never summed and an unmeasured figure never "
    "reported as zero"
)

EXTRACTION_NOTE = (
    "checkpoints are restored by the existing extraction owner, `bin/repo_bench.py`: a "
    "history-free tree extraction at the pinned base commit, through allowlisted git verbs "
    "against a read-only target. This module copies nothing and extracts nothing itself"
)

OVERLAPPING_INTERVAL_NOTE = (
    "a difference whose intervals overlap is not a result; neither is one that clears no "
    "threshold, because no threshold exists here unless an operator declared one"
)

MANIFEST_VERIFICATION_NOTE = (
    "the manifest is re-checked here by workflow_eval.verify_manifest before ANY count is read "
    "out of it, so a document whose content no longer hashes to the sha it is filed under yields "
    "no cohort at all. What that check cannot see is the STORE -- exposure, retirement, "
    "single-use and calibration fits live there, and workflow_eval.require_held_out is what reads "
    "them at run time. Verifying a manifest is not the same as a partition still being unspent"
)

UNDERIVED_EVIDENCE_NOTE = (
    "re_derived_by is None on this row: its verdict is read off what the CALLER handed in, and "
    "nothing in this module re-derives it. Satisfied here means `the caller asserted it`, which "
    "is weaker than every row that names a function, and a live run must treat it that way"
)


# ---- the pinned inputs -------------------------------------------------------------------------

def _tp_text(value, what):
    text = str(value or "").strip()
    if not text:
        raise EvalError(f"{what} must be a non-empty string")
    return text


def _tp_mapping(value, what):
    if not isinstance(value, dict):
        raise EvalError(f"{what} must be a mapping, not {type(value).__name__}")
    return value


def _tp_count(value, what, *, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvalError(f"{what} must be an int, not {type(value).__name__}")
    if value < minimum:
        raise EvalError(f"{what} must be >= {minimum}")
    return int(value)


def _tp_ceiling_number(value, what):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvalError(f"{what} must be a number, not {type(value).__name__}; a ceiling that is "
                        f"absent is not a ceiling")
    if not math.isfinite(value) or value <= 0:
        raise EvalError(f"{what} must be a finite number greater than zero")
    return float(value)


def _tp_cost(value, what):
    """One cost, validated against this module's OWN basis vocabulary. A figure without a basis
    is not a figure: `BASES` is the same tuple `add_cost` and `priced_usd` already read."""
    cost = _tp_mapping(value, what)
    basis = cost.get("basis")
    if basis not in BASES:
        raise EvalError(f"{what}: basis {basis!r} is not one of {list(BASES)}")
    return _frozen(cost)


def pin_trial_inputs(*, checkpoint, acceptance, model, effort, diagnostics, ceiling):
    """The six pinned facts every arm of one trial shares -> one hashed object.

    Keyword-only, and every parameter is REQUIRED with no default: nothing here is permissive by
    omission, and a caller that has not decided its effort or its ceiling cannot accidentally
    inherit one. The returned `sha` is what each arm cites, so an input that moved between
    building an arm and building the protocol is caught rather than averaged over.

    `checkpoint.initial_attempt` is required even though the checkpoint will be RESTORED rather
    than re-earned: the first attempt is what created the checkpoint, its cost is real, and an
    accounting that drops it reports a recovery that appears to come from nowhere.
    """
    cp = _tp_mapping(checkpoint, "checkpoint")
    pinned_checkpoint = {
        "item": _tp_text(cp.get("item"), "checkpoint.item"),
        "group": _tp_text(cp.get("group"), "checkpoint.group"),
        "manifest": _tp_text(cp.get("manifest"), "checkpoint.manifest"),
        "base_commit": _tp_text(cp.get("base_commit"), "checkpoint.base_commit"),
        "failure_class": _tp_text(cp.get("failure_class"), "checkpoint.failure_class"),
        "restored_by": _tp_text(cp.get("restored_by"), "checkpoint.restored_by"),
        "initial_attempt": _tp_cost(cp.get("initial_attempt"), "checkpoint.initial_attempt"),
    }
    acc = _tp_mapping(acceptance, "acceptance")
    pinned_acceptance = {
        "command": _tp_text(acc.get("command"), "acceptance.command"),
        "sha": _tp_text(acc.get("sha"), "acceptance.sha"),
    }
    if not isinstance(diagnostics, (list, tuple)):
        raise EvalError("diagnostics must be a list or tuple of names -- an empty one is a "
                        "declaration, an absent one is an omission")
    names = [_tp_text(d, "diagnostics entry") for d in diagnostics]
    if len(set(names)) != len(names):
        raise EvalError("diagnostics names must be unique")
    ceil_map = _tp_mapping(ceiling, "ceiling")
    pinned_ceiling = {
        "max_usd": _tp_ceiling_number(ceil_map.get("max_usd"), "ceiling.max_usd"),
        "max_dispatches": _tp_count(ceil_map.get("max_dispatches"), "ceiling.max_dispatches",
                                    minimum=1),
        "max_wall_seconds": _tp_ceiling_number(ceil_map.get("max_wall_seconds"),
                                               "ceiling.max_wall_seconds"),
        "note": CEILING_NOTE,
    }
    pinned = {
        "v": TRIAL_PROTOCOL_VERSION,
        "checkpoint": pinned_checkpoint,
        "acceptance": pinned_acceptance,
        "model": _tp_text(model, "model"),
        "effort": _tp_text(effort, "effort"),
        "diagnostics": sorted(names),
        "ceiling": pinned_ceiling,
    }
    pinned["sha"] = _sha(_canonical(pinned))
    return pinned


# ---- the arms ----------------------------------------------------------------------------------

def _tp_package(value, what):
    """A context package REFERENCE -- an id, a digest and a bound. Never the package itself: a
    specification carries what identifies the intervention, not its payload.

    `items` must be at least 1. A package with nothing in it is not an arm C that does nothing:
    "no applicable context" is a legitimate ABSTENTION, and the checkpoint drops out of the
    cohort rather than being compared against an intervention that was never applied. Counting an
    empty package as a repair would dilute arm C with checkpoints it never touched.
    """
    if value is None:
        return None
    pkg = _tp_mapping(value, what)
    return {
        "id": _tp_text(pkg.get("id"), f"{what}.id"),
        "sha": _tp_text(pkg.get("sha"), f"{what}.sha"),
        "items": _tp_count(pkg.get("items"), f"{what}.items", minimum=1),
        "bound": _tp_text(pkg.get("bound"), f"{what}.bound"),
    }


def build_arm(name, *, inputs, extra_attempts, diagnostics_applied, context_package,
              remaining_recovery):
    """One arm of the trial, citing the pinned inputs by sha. Keyword-only, no defaults.

    Only arm C may carry a context package -- that IS the intervention, and an arm A or B that
    carried one would not be the thing it is named after.
    """
    if name not in ARMS:
        raise EvalError(f"arm {name!r} is not one of {list(ARMS)}")
    pinned = _tp_mapping(inputs, "inputs")
    inputs_sha = _tp_text(pinned.get("sha"), "inputs.sha")
    if not isinstance(diagnostics_applied, (list, tuple)):
        raise EvalError("diagnostics_applied must be a list or tuple")
    applied = sorted({_tp_text(d, "diagnostics_applied entry") for d in diagnostics_applied})
    unknown = [d for d in applied if d not in (pinned.get("diagnostics") or ())]
    if unknown:
        raise EvalError(f"arm {name}: diagnostics {unknown} are not in the pinned diagnostics "
                        f"{list(pinned.get('diagnostics') or ())}; an arm cannot apply a "
                        f"diagnostic the trial never pinned")
    package = _tp_package(context_package, f"arm {name} context_package")
    if package is not None and name != "C":
        raise EvalError(f"arm {name} carries a context package; only arm C may, because the "
                        f"package is the intervention under test")
    arm = {
        "arm": name,
        "role": ARM_ROLES[name],
        "inputs_sha": inputs_sha,
        "extra_attempts": _tp_count(extra_attempts, f"arm {name} extra_attempts"),
        "diagnostics_applied": applied,
        "context_package": package,
        "remaining_recovery": _tp_text(remaining_recovery, f"arm {name} remaining_recovery"),
    }
    arm["signature"] = _sha(_canonical({f: arm[f] for f in ARM_SIGNATURE_FIELDS}))
    return arm


def arm_delta(left, right):
    """Every signature field two arms differ in. The comparison is over the canonical form, so
    `None` and a missing key read alike and key order never matters."""
    return sorted(f for f in ARM_SIGNATURE_FIELDS
                  if _canonical(left.get(f)) != _canonical(right.get(f)))


def collapse_equivalent_arms(arms):
    """`(kept, equivalences)` -- arms with identical signatures collapsed into one.

    A=B is the case the shared plan names: when the frozen current policy already performs the
    same same-model extra attempt with the same diagnostics and no package, arm A IS arm B and
    "record equivalence and collapse the duplicate" is the instruction. The kept arm keeps the
    FIRST name in `ARMS` order and carries every collapsed name in `collapsed_from`, so nothing
    is lost -- the two arms become one arm with two roles, never one arm with one role.
    """
    kept, by_signature = [], {}
    for arm in arms:
        signature = _tp_text(arm.get("signature"), "arm signature")
        first = by_signature.get(signature)
        if first is None:
            copy = _frozen(arm)
            copy["collapsed_from"] = [arm["arm"]]
            copy["collapse_reason"] = None
            by_signature[signature] = copy
            kept.append(copy)
            continue
        first["collapsed_from"].append(arm["arm"])
    equivalences = []
    for arm in kept:
        if len(arm["collapsed_from"]) > 1:
            arm["collapse_reason"] = "arms-equivalent"
            arm["role"] = " || ".join(ARM_ROLES[n] for n in arm["collapsed_from"])
            equivalences.append({
                "arms": list(arm["collapsed_from"]),
                "reason": "arms-equivalent",
                "signature": arm["signature"],
                "note": ARM_COLLAPSE_NOTE,
            })
    return kept, equivalences


# ---- the frozen grouped cohort -------------------------------------------------------------------

def trial_cohort(manifest, partition, *, cohort):
    """The frozen, grouped checkpoint cohort this trial compares over -- counts and ids only.

    Read straight out of D06's immutable manifest content: this function selects nothing, writes
    nothing and opens nothing, so it cannot be the thing that spends single-use material. A live
    run still passes `require_held_out` / `select_cohort` against the STORE, which is where
    exposure, retirement and staleness actually live; the counts here are what a specification may
    state in advance.

    THE MANIFEST IS RE-CHECKED, NEVER TAKEN ON THE CALLER'S WORD. `verify_manifest` -- D06's own
    checker, store-free and defined in this same file -- runs over it FIRST, and its digest test
    is exactly what catches a document whose `content` no longer hashes to the `sha` it is filed
    under. A manifest with ANY finding comes back `verified: False`, `frozen: False`, and with
    `items`, `groups` and `quarantined` left empty: nothing is read out of a document that failed
    its own check, for the reason `require_runnable` does not read the blockers of a tampered
    specification. `frozen` therefore means "an immutable manifest was supplied AND it verifies",
    which is the only reading under which the word is true; it used to mean "a `manifest`
    argument was passed", which is not the same claim and was the defect.
    """
    if partition not in PARTITIONS:
        raise EvalError(f"partition {partition!r} is not one of {list(PARTITIONS)}")
    role = PARTITION_ROLES[partition]
    base = {
        "partition": partition,
        "held_out": role["held_out"],
        "role_note": role["note"],
        "cohort": cohort,
        "manifest_ref": None,
        "items": [],
        "item_count": 0,
        "groups": [],
        "group_count": 0,
        "quarantined": None,
        "frozen": False,
        "verified": None,
        "verification": None,
        "verified_by": "workflow_eval.verify_manifest",
        "verification_note": MANIFEST_VERIFICATION_NOTE,
        "grouping": GROUPING_RULE,
        "assignment": ASSIGNMENT_RULE,
        "enforcement": NOT_ENFORCEMENT_LABEL,
    }
    if manifest is None:
        return base
    content = _tp_mapping(_tp_mapping(manifest, "manifest").get("content"), "manifest.content")
    try:
        findings = verify_manifest(manifest)
    except EvalError:
        raise
    except (AttributeError, TypeError, KeyError, ValueError) as exc:
        raise EvalError(f"manifest {manifest.get('id')!r} is too malformed for "
                        f"verify_manifest to read ({exc!r}); refusing rather than reading a "
                        f"cohort out of it") from None
    base.update(verification=_frozen(findings), verified=not findings)
    if all(key in manifest for key in ("id", "sha", "v")):
        base.update(manifest_ref=manifest_ref(manifest))
    if findings:
        return base
    members = list((content.get("partitions") or {}).get(partition) or ())
    if cohort is not None:
        name = _tp_text(cohort, "cohort")
        declared = [c for c in (content.get("cohorts") or ())
                    if c.get("cohort") == name and c.get("partition") == partition]
        if not declared:
            raise EvalError(f"cohort {name!r} is not declared on the {partition} partition of "
                            f"manifest {manifest.get('id')!r}; a cohort chosen after the fact is "
                            f"not a cohort")
        members = [i for i in declared[0].get("items") or () if i in members]
    items = sorted(set(members))
    by_item = content.get("items") or {}
    groups = sorted({(by_item.get(i) or {}).get("group") for i in items} - {None})
    summary = manifest_summary(manifest)
    base.update(
        items=items,
        item_count=len(items),
        groups=groups,
        group_count=len(groups),
        quarantined=summary["quarantined"],
        frozen=True,
    )
    return base


# ---- the graders, which are repo_bench's own -----------------------------------------------------

def trial_oracles():
    """The four gradings this protocol reads, each naming its existing owner and its own honesty
    label. No new oracle is defined here, and no two classes are blended: `solved` is the tests
    oracle alone, and a judge opinion is never ground truth."""
    rb = _rb()
    return [
        {"oracle": "tests", "owner": "repo_bench.oracle_tests", "objective": True,
         "label": SOLVED_LABEL},
        {"oracle": "structural", "owner": "repo_bench.oracle_structural", "objective": False,
         "label": getattr(rb, "STRUCTURAL_LABEL", None)},
        {"oracle": "judge", "owner": "repo_bench.oracle_judge", "objective": False,
         "label": getattr(rb, "JUDGE_LABEL", None)},
        {"oracle": "resources", "owner": "workflow_eval cost and wall accounting",
         "objective": True, "label": RESOURCE_ORACLE_LABEL},
    ]


def trial_extraction():
    """Where a restored checkpoint comes from: the existing extraction owner, named, not copied."""
    return {
        "owner": "repo_bench",
        "snapshot": "repo_bench.make_sandbox / repo_bench.prepare_cell_sandbox",
        "substrate": "repo_bench.build_grade_substrate",
        "envelope_writer": "workflow_eval",
        "note": EXTRACTION_NOTE,
    }


# ---- what a live run of this specification would require -----------------------------------------

def _certification_evidence(sentinel_report):
    """`(reference, reason_or_None)` for a protected-profile claim, DERIVED here rather than read.

    WHAT CHANGED AND WHY (Phase 4 review). This used to take D07's RESULT and check that its
    arithmetic looked right. That left the verdict as something the caller asserted about itself:
    `{"profile": "made-up", "backend": "none", "certified": True, "required": 7, "satisfied": 7,
    "blocking": []}` discharged the requirement, and no function in this section ever called
    `exec_policy`. It now takes the sentinel REPORT -- what `exec_policy.run_sentinels` produces
    -- and asks `exec_policy.certify_profile` for the verdict. That function is pure over a
    report: it re-derives the sentinel plan for the report's OWN backend, requires every sentinel
    in that plan to be present and to match its expectation, requires each protected leg to name
    that backend as its confinement (so a `trusted-host` leg can never count as enforcement),
    requires an attributing control leg that SUCCEEDED and an OS permission signal behind every
    denial, requires the controller-owned trees to be byte-identical afterwards, and requires
    every acceptance question to be covered. A forger now has to fabricate all of that
    consistently instead of one boolean, and the same report fed in above is refused.

    WHAT THIS STILL DOES NOT DO, said plainly rather than glossed. It cannot RUN the sentinels:
    that is `exec_policy.run_sentinels`, which spawns processes into a temporary tree, and no
    function in this section spawns anything. So a report that LIES about what the OS did is
    still a report this module will certify, and a certification is still only ever about the one
    host the report was produced on. What is gone is the shortcut: the verdict is now D07's own
    arithmetic over the evidence, not a word the caller chose.
    """
    if sentinel_report is None:
        return None, ("no sentinel report was supplied; the evidence must be what "
                      "exec_policy.run_sentinels produces, which this module then puts through "
                      "exec_policy.certify_profile")
    report = _tp_mapping(sentinel_report, "sentinel_report")
    try:
        cert = _ep().certify_profile(report)
    except (AttributeError, TypeError, KeyError, ValueError, IndexError) as exc:
        return None, (f"exec_policy.certify_profile could not read this report ({exc!r}); the "
                      f"evidence must be what exec_policy.run_sentinels produces, not a document "
                      f"shaped like it")
    required = cert.get("required")
    satisfied = cert.get("satisfied")
    if not isinstance(required, int) or isinstance(required, bool) or required < 1:
        return None, (f"exec_policy.certify_profile found no sentinel plan for backend "
                      f"{cert.get('backend')!r}, so this report certifies nothing")
    if cert.get("certified") is not True:
        blocking = [b for b in (cert.get("blocking") or ()) if isinstance(b, dict)]
        named = sorted({str(b.get("id")) for b in blocking})
        return None, (f"exec_policy.certify_profile refused this report: "
                      f"{len(cert.get('blocking') or ())} blocking finding(s) over "
                      f"{named[:6]}{' and more' if len(named) > 6 else ''}")
    if satisfied != required:
        return None, (f"{satisfied} of {required} sentinels satisfied; a partially satisfied plan "
                      f"certifies nothing")
    return {
        "profile": cert.get("profile"),
        "backend": cert.get("backend"),
        "required": required,
        "satisfied": satisfied,
        "not_proven": list(cert.get("not_proven") or ()),
        "label": cert.get("label"),
    }, None


def _study_run_reference(full_task_study_run):
    """`(reference, reason_or_None)` for a prospective full-task study that claims to have run."""
    if full_task_study_run is None:
        return None, ("no whole-task study has run; a checkpoint study conditions on having "
                      "already failed once and cannot answer the rollout population's question")
    run = _tp_mapping(full_task_study_run, "full_task_study_run")
    return {"run_id": _tp_text(run.get("run_id"), "full_task_study_run.run_id"),
            "results_ref": _tp_text(run.get("results_ref"),
                                    "full_task_study_run.results_ref")}, None


def live_requirements(*, cohort, sentinel_report, full_task_study_run, declarations):
    """Every precondition a LIVE run of this specification would have to satisfy, each with the
    owner that can satisfy it, whether the evidence in hand does, and -- in `re_derived_by` --
    which function actually re-derived that verdict, or `None` when nothing did.

    The first two are Phase 2's F4 finding made explicit: D06's held-out controller and D07/D08's
    isolation question are BOTH required, side by side. Satisfying one has never discharged the
    other, and until this list existed nothing said so.

    `re_derived_by` exists because of Phase 4's finding: a row that says `satisfied` over
    evidence nobody consulted is a name broader than its check. Three rows now name the function
    behind them -- `verify_manifest`, `exec_policy.certify_profile`, and this module's own
    `CONFINED_DISPATCH_WIRED` -- and the two that cannot be re-derived offline say so instead of
    reading like the other three.
    """
    certificate, cert_reason = _certification_evidence(sentinel_report)
    study, study_reason = _study_run_reference(full_task_study_run)
    missing_declarations = [name for name in OPERATOR_DECLARATIONS
                            if declarations.get(name) in (None, "", [], {})]
    held_out_reason = held_out_blocker = None
    findings = list(cohort.get("verification") or ())
    if findings:
        kinds = ", ".join(sorted({str(f.get("kind")) for f in findings}))
        held_out_blocker = "manifest-unverified"
        held_out_reason = (
            f"workflow_eval.verify_manifest returned {len(findings)} finding(s) over this "
            f"manifest ({kinds}), so NOTHING was read out of it as a cohort. A `digest` finding "
            f"means the content does not hash to the sha the document is filed under -- a forged "
            f"or altered manifest, which is a different fact from an honest manifest with an "
            f"empty partition and is never reported as one")
    elif not cohort["frozen"]:
        held_out_blocker = "cohort-not-frozen"
        held_out_reason = "no immutable manifest was supplied, so the cohort is not frozen"
    elif not cohort["held_out"]:
        held_out_blocker = "no-held-out-evidence"
        held_out_reason = (f"the {cohort['partition']} partition is fitting material and is never "
                           f"citable as held-out evidence")
    elif not cohort["item_count"]:
        held_out_blocker = "no-held-out-evidence"
        held_out_reason = (
            f"the {cohort['partition']} partition is EMPTY. The usual cause is the default mining "
            f"path: without `gh`, repo_bench builds a problem statement out of the fix commit "
            f"message, the leak screen flags it `future-fix-message`, and quarantine is contagious "
            f"within a defect group, so every group ends in quarantine and no partition fills")
    return [
        {"requirement": "held-out-evidence",
         "owner": ("workflow_eval.verify_manifest here; workflow_eval.require_held_out against "
                   "the store at run time (D06)"),
         "satisfied": held_out_reason is None, "reason": held_out_reason,
         "evidence": cohort["manifest_ref"], "blocker": held_out_blocker,
         "re_derived_by": "workflow_eval.verify_manifest",
         "pairs_with": "protected-profile-certified",
         "note": MANIFEST_VERIFICATION_NOTE},
        {"requirement": "protected-profile-certified",
         "owner": "exec_policy.certify_profile over exec_policy.run_sentinels (D07)",
         "satisfied": cert_reason is None, "reason": cert_reason, "evidence": certificate,
         "blocker": None if cert_reason is None else "protected-profile-uncertified",
         "re_derived_by": "exec_policy.certify_profile",
         "pairs_with": "held-out-evidence",
         "note": ("workflow_eval.gate_protected_dispatch is an AVAILABILITY gate and applies no "
                  "confinement of its own; passing it is not this requirement. The verdict here "
                  "is certify_profile's over the supplied report; this module cannot RUN the "
                  "sentinels, so a report that lies about what the OS did still certifies")},
        {"requirement": "confining-and-ledgered-dispatch",
         "owner": "whichever task wires a live protected trial",
         "satisfied": bool(CONFINED_DISPATCH_WIRED), "evidence": None,
         "blocker": None if CONFINED_DISPATCH_WIRED else "confining-dispatch-unwired",
         "re_derived_by": "workflow_eval.CONFINED_DISPATCH_WIRED",
         "reason": (None if CONFINED_DISPATCH_WIRED else
                    "this repository has no dispatch path that both confines and is recorded in "
                    "bin/attempt_ledger.py before and after the call; the availability gate does "
                    "neither"),
         "pairs_with": "protected-profile-certified"},
        {"requirement": "whole-task-study", "owner": "a prospective study, separately run",
         "satisfied": study_reason is None, "reason": study_reason, "evidence": study,
         "blocker": None if study_reason is None else "full-task-study-not-run",
         "re_derived_by": None,
         "note": f"{FULL_TASK_STUDY_NOTE}. {UNDERIVED_EVIDENCE_NOTE}"},
        {"requirement": "operator-declarations", "owner": "the operator, never this module",
         "satisfied": not missing_declarations, "evidence": None,
         "blocker": None if not missing_declarations else "operator-declaration-missing",
         "re_derived_by": None,
         "reason": (None if not missing_declarations else
                    f"undeclared: {', '.join(missing_declarations)}"),
         "note": f"{NO_INVENTED_NUMBER_LABEL}. {UNDERIVED_EVIDENCE_NOTE}"},
    ]


def _blockers_from(requirements, declarations):
    """The closed-vocabulary blockers behind the unsatisfied requirements. Each row carries its
    own code, so nothing here sniffs a sentence for a word."""
    blockers = []
    for row in requirements:
        if row["satisfied"] or row["blocker"] is None:
            continue
        if row["blocker"] == "operator-declaration-missing":
            for name in OPERATOR_DECLARATIONS:
                if declarations.get(name) in (None, "", [], {}):
                    blockers.append({"blocker": row["blocker"], "detail": name})
            continue
        blockers.append({"blocker": row["blocker"], "detail": row["reason"]})
    unknown = sorted({b["blocker"] for b in blockers} - set(PROTOCOL_BLOCKERS))
    if unknown:  # pragma: no cover -- a closed vocabulary that stopped being closed
        raise EvalError(f"blocker code(s) {unknown} are outside PROTOCOL_BLOCKERS")
    return blockers


# ---- the specification ---------------------------------------------------------------------------

def build_trial_protocol(*, inputs, arms, manifest, partition, cohort, sentinel_report,
                         full_task_study_run, operator_declarations, created_by, created_at):
    """The three-arm recovery trial SPECIFICATION: immutable, content-addressed, and not a run.

    Keyword-only with no defaults, for the same reason `pin_trial_inputs` is: a specification
    assembled out of whatever the caller happened to omit is not a specification. `created_at` and
    `created_by` are provenance and stay OUTSIDE the digest, so the same specification written
    twice by two people is the same specification -- D06's rule, for D06's reason.

    Nothing here dispatches, grades, mines, selects from a store, or writes. The one thing it
    produces is a document that says, in a closed vocabulary, exactly what would have to be true
    before this experiment could run.

    The two pieces of EVIDENCE are re-derived rather than believed. `manifest` goes through
    `verify_manifest` in `trial_cohort` before a single count is read out of it, and
    `sentinel_report` is the raw report `exec_policy.run_sentinels` produces -- never a
    certification -- so the verdict on it is `exec_policy.certify_profile`'s and not the caller's.
    The digest this function then takes is correct either way; that was always the point, and it
    is why an unchecked input inside the digest was the exposure rather than the digest itself.
    """
    pinned = _tp_mapping(inputs, "inputs")
    inputs_sha = _tp_text(pinned.get("sha"), "inputs.sha")
    arm_list = list(arms or ())
    if not arm_list:
        raise EvalError("a trial protocol needs at least one arm")
    names = [a.get("arm") for a in arm_list]
    if len(set(names)) != len(names):
        raise EvalError(f"duplicate arm name(s) in {names}")
    for arm in arm_list:
        if arm.get("inputs_sha") != inputs_sha:
            raise EvalError(f"arm {arm.get('arm')!r} cites inputs {arm.get('inputs_sha')!r} but "
                            f"the trial pins {inputs_sha!r}; the arms are not comparing the same "
                            f"checkpoint, acceptance, model, effort, diagnostics and ceiling")
    by_name = {a["arm"]: a for a in arm_list}
    if "B" in by_name and "C" in by_name:
        delta = arm_delta(by_name["B"], by_name["C"])
        illegal = [f for f in delta if f != REPAIR_DIMENSION]
        if illegal:
            raise EvalError(
                f"arm C differs from arm B in {illegal} as well as {REPAIR_DIMENSION!r}; a trial "
                f"that changes the model, the effort, the diagnostics or the permitted attempts "
                f"at the same time as the context cannot attribute its own result")
        if REPAIR_DIMENSION not in delta:
            raise EvalError(
                f"arm C does not differ from arm B in {REPAIR_DIMENSION!r}, so there is no "
                f"intervention under test; arm C is the bounded context package")
    kept, equivalences = collapse_equivalent_arms([by_name[n] for n in ARMS if n in by_name])
    declarations = {name: _tp_mapping(operator_declarations, "operator_declarations").get(name)
                    for name in OPERATOR_DECLARATIONS}
    selected = trial_cohort(manifest, partition, cohort=cohort)
    requirements = live_requirements(cohort=selected, sentinel_report=sentinel_report,
                                     full_task_study_run=full_task_study_run,
                                     declarations=declarations)
    blockers = _blockers_from(requirements, declarations)
    study, _study_reason = _study_run_reference(full_task_study_run)
    content = {
        "v": TRIAL_PROTOCOL_VERSION,
        "hypothesis": (
            "on a narrow cohort of cross-module failures, one bounded package of previously "
            "missing contract context before a same-model retry improves accepted recovery or "
            "total resources without weakening quality"),
        "inputs": _frozen(pinned),
        "pinned_inputs": list(PINNED_INPUTS),
        "arms": kept,
        "nominal_arms": names,
        "equivalences": equivalences,
        "repair_dimension": REPAIR_DIMENSION,
        "cohort": selected,
        "oracles": trial_oracles(),
        "extraction": trial_extraction(),
        "accounting": {
            "scopes": list(ACCOUNTING_SCOPES),
            "overhead_kinds": list(OVERHEAD_KINDS),
            "initial_attempt": ANALYTIC_REUSE_LABEL,
            "failures": FAILURES_IN_TOTALS_LABEL,
            "conditional_recovery": CONDITIONAL_RECOVERY_NOTE,
            "bases": list(BASES),
            "reader": "workflow_eval.arm_accounting",
        },
        "full_task_study": {
            "status": "prospective" if study is None else "run",
            "run": study,
            "unit": "one whole task, from its first attempt to the accepted or abandoned end",
            "satisfied_by_checkpoint_study": False,
            "required_before": "general rollout",
            "note": FULL_TASK_STUDY_NOTE,
        },
        "declarations": declarations,
        "live_requirements": requirements,
        "blockers": blockers,
        "runnable": False,
        "labels": [NOT_A_RUN_LABEL, NO_INVENTED_NUMBER_LABEL, FAILURES_IN_TOTALS_LABEL,
                   ANALYTIC_REUSE_LABEL, NOT_ENFORCEMENT_LABEL],
        "notes": [ARM_COLLAPSE_NOTE, OVERLAPPING_INTERVAL_NOTE, EXTRACTION_NOTE],
    }
    sha = _sha(_canonical(content))
    return {
        "v": TRIAL_PROTOCOL_VERSION,
        "id": sha[:16],
        "sha": sha,
        "digest": {
            "algorithm": "sha256",
            "canonical": "json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=True)",
            "over": "content",
            "excludes": ["created_at", "created_by", "id", "sha", "digest"],
            "note": NOT_ENFORCEMENT_LABEL,
        },
        "created_at": created_at or _now(),
        "created_by": created_by or "",
        "content": content,
    }


def protocol_ref(spec):
    """What an envelope quotes: id, digest, contract version. Never the specification itself."""
    if not spec:
        return None
    return {"id": spec["id"], "sha": spec["sha"], "v": spec["v"]}


def require_runnable(spec):
    """Refuse to treat a specification as a run. Two refusals, kept textually distinguishable
    because they mean different things.

    FIRST, the document is checked against ITS OWN digest: `content` is re-hashed here exactly the
    way `build_trial_protocol` hashed it, `_sha(_canonical(content))`, and any mismatch -- or a
    `content`/`sha` that is missing or of the wrong type -- is refused as a malformed or TAMPERED
    specification before a single blocker is read. Skipping that check is how this function used
    to be defeated: it trusted the dict it was handed, so a caller who passed
    `{"sha": ..., "content": {"blockers": []}}` discharged every precondition -- including the
    `confining-dispatch-unwired` one derived from code -- without touching the flag. The
    enforcement point has to consult the thing being enforced. A forged specification gets NO code
    in `PROTOCOL_BLOCKERS`: that vocabulary is closed and means "a precondition a live run must
    satisfy", and a fabricated input is not an unsatisfied precondition.

    SECOND, an honest specification is refused for every unsatisfied precondition it carries,
    naming each in that closed vocabulary. For every specification `build_trial_protocol` actually
    produces this is the path taken, and it always raises, because `confining-dispatch-unwired` is
    derived from `CONFINED_DISPATCH_WIRED` and no evidence a caller can hand in changes it. That
    is the exact and narrowed claim, and its limit is stated rather than glossed: content
    addressing detects ALTERATION, it does not authenticate an author, so a caller who empties the
    blockers AND recomputes `sha` over the emptied content is not caught here. What IS guaranteed
    is that no document can claim a digest it does not have, and that every specification this
    module builds is refused.

    THAT LIMIT USED TO BE STATED IN A WAY THAT MISFRAMED THE EXPOSURE, and Phase 4 corrected it.
    The weak link was never the digest: `build_trial_protocol` computes a perfectly CORRECT
    digest over forged inputs, so the unauthenticated evidence sat INSIDE the hash and no check
    here could ever have seen it. The fix belongs one level down, where the document is built --
    `trial_cohort` now puts the manifest through `verify_manifest`, and `_certification_evidence`
    now puts the sentinel report through `exec_policy.certify_profile` -- and this function is
    deliberately unchanged, because it was already doing its own job correctly.

    Returning is not a dispatch and grants nothing: there is no function in this section that
    dispatches, and this one is a precondition check a future caller must pass, not a way in.
    """
    mapping = _tp_mapping(spec, "the specification handed to require_runnable")
    content = mapping.get("content")
    if not isinstance(content, dict):
        raise EvalError(f"malformed specification: `content` must be a mapping, not "
                        f"{type(content).__name__}, so it cannot be checked against its own "
                        f"digest; refusing rather than reading preconditions out of it")
    claimed = mapping.get("sha")
    if not isinstance(claimed, str) or not claimed.strip():
        raise EvalError(f"malformed specification: `sha` must be a non-empty string, not "
                        f"{type(claimed).__name__}, so there is nothing to check `content` "
                        f"against; refusing rather than reading preconditions out of it")
    try:
        derived = _sha(_canonical(content))
    except (TypeError, ValueError) as exc:
        raise EvalError(f"malformed specification: `content` does not canonicalise ({exc}), so no "
                        f"digest can be derived from it; refusing rather than reading "
                        f"preconditions out of it") from None
    if derived != claimed:
        raise EvalError(f"TAMPERED specification: `content` hashes to {derived} but the document "
                        f"carries sha {claimed}. Its blockers were NOT read -- a caller that can "
                        f"rewrite the preconditions can discharge every one of them, so a "
                        f"specification that does not match its own digest is refused outright")
    blockers = list(content.get("blockers") or ())
    if blockers:
        detail = "; ".join(f"{b['blocker']}: {b['detail']}" for b in blockers)
        raise EvalError(f"this is an experiment specification, not a run -- {len(blockers)} "
                        f"unsatisfied precondition(s): {detail}")
    return spec


def carry_trial_protocol(envelope, spec):
    """Append the specification's reference and its caveats into the SAME `labels`/`notes` an
    envelope already carries every run-level caveat in.

    `bin/workflow_eval.py` stays the only envelope writer and this adds no top-level key, no
    second store and no second file -- D08's `carry_protected_evidence` precedent, for D08's
    reason. `NOT_ENFORCEMENT_LABEL` travels with it because a reader of `results.json` alone
    otherwise sees partition counts with nothing saying they are tamper-evident rather than
    enforced (Phase 2 review, F5).
    """
    ref = protocol_ref(spec)
    content = spec["content"]
    cohort = content["cohort"]
    envelope.setdefault("labels", []).append(
        f"three-arm recovery trial protocol {ref['id']} ({ref['v']}): {NOT_A_RUN_LABEL}")
    envelope.setdefault("notes", []).append(
        f"protocol {ref['id']}: arms {[a['arm'] for a in content['arms']]} from nominal "
        f"{content['nominal_arms']}; {len(content['equivalences'])} equivalence(s); cohort "
        f"{cohort['item_count']} item(s) in {cohort['group_count']} group(s) of the "
        f"{cohort['partition']} partition (held_out={cohort['held_out']}); "
        f"{len(content['blockers'])} blocker(s): "
        f"{sorted({b['blocker'] for b in content['blockers']})}")
    envelope.setdefault("notes", []).append(f"protocol {ref['id']}: {NOT_ENFORCEMENT_LABEL}")
    return envelope


# ---- reading a future run's results ---------------------------------------------------------------

_TP_ABSENT = object()


def _tp_outcome(record):
    value = record.get("accepted", _TP_ABSENT)
    if value is _TP_ABSENT:
        raise EvalError("every record needs an explicit `accepted`: True, False, or None for a "
                        "censored outcome. An absent key is not a failure")
    if value not in (True, False, None):
        raise EvalError(f"accepted must be True, False or None, not {value!r}")
    return value


def arm_accounting(arm, records):
    """One arm's cohort accounting over EVERY record -- accepted, failed and censored alike.

    Two things this refuses to do, both of which would flatter the arm:

      * drop the initial attempt for a checkpoint that was reused ANALYTICALLY. The whole-task
        scope carries it either way; `analytically_reused` says how many were attributed rather
        than re-spent, which is a different fact from a second spend and is labelled as one.
      * drop failures out of the cohort totals. Cost per accepted task divides the WHOLE cohort's
        resources by the accepted count, and is `None` with a stated reason when that count is
        zero -- never `0.0`, which would read as free.

    Bases are never summed: `empty_totals`/`add_cost` keep model-reported, estimated, proxy,
    credits and unpriced apart, exactly as every other total in this module does.
    """
    scopes = {name: {"totals": empty_totals(), "priced_usd": 0.0} for name in ACCOUNTING_SCOPES}
    accepted = failed = censored = 0
    reused = 0
    initial_priced = 0.0
    rows = list(records or ())
    for index, raw in enumerate(rows):
        record = _tp_mapping(raw, f"record {index}")
        _tp_text(record.get("item"), f"record {index}.item")
        outcome = _tp_outcome(record)
        if outcome is True:
            accepted += 1
        elif outcome is False:
            failed += 1
        else:
            censored += 1
        initial = _tp_cost(record.get("initial_attempt"), f"record {index}.initial_attempt")
        flag = record.get("initial_attempt_reused")
        if not isinstance(flag, bool):
            raise EvalError(f"record {index}.initial_attempt_reused must be True or False: "
                            f"whether the first attempt was re-run or attributed is a fact the "
                            f"accounting states, never one it guesses")
        if flag:
            reused += 1
        add_cost(scopes["whole-task"]["totals"], initial)
        scopes["whole-task"]["priced_usd"] += priced_usd(initial)
        initial_priced += priced_usd(initial)
        for n, cost in enumerate(record.get("recovery_costs") or ()):
            attempt = _tp_cost(cost, f"record {index}.recovery_costs[{n}]")
            for name in ACCOUNTING_SCOPES:
                add_cost(scopes[name]["totals"], attempt)
                scopes[name]["priced_usd"] += priced_usd(attempt)
        for n, entry in enumerate(record.get("overhead") or ()):
            row = _tp_mapping(entry, f"record {index}.overhead[{n}]")
            kind = row.get("kind")
            if kind not in OVERHEAD_KINDS:
                raise EvalError(f"record {index}.overhead[{n}]: kind {kind!r} is not one of "
                                f"{list(OVERHEAD_KINDS)}")
            scope = row.get("scope")
            if scope not in ACCOUNTING_SCOPES:
                raise EvalError(f"record {index}.overhead[{n}]: scope {scope!r} is not one of "
                                f"{list(ACCOUNTING_SCOPES)}; every cost belongs at its actual "
                                f"scope, and an unattributed one belongs nowhere")
            cost = _tp_cost(row.get("cost"), f"record {index}.overhead[{n}].cost")
            targets = (ACCOUNTING_SCOPES if scope == "recovery-only" else ("whole-task",))
            for name in targets:
                add_cost(scopes[name]["totals"], cost)
                scopes[name]["priced_usd"] += priced_usd(cost)
    resolved = accepted + failed
    for name in ACCOUNTING_SCOPES:
        block = scopes[name]
        block["priced_usd"] = round(block["priced_usd"], 6)
        block["scope"] = name
        block["items"] = len(rows)
        if accepted:
            block["cost_per_accepted_usd"] = round(block["priced_usd"] / accepted, 6)
            block["undefined_reason"] = None
        else:
            block["cost_per_accepted_usd"] = None
            block["undefined_reason"] = ("no task was accepted, so cost per accepted task is "
                                         "undefined; it is not zero and the cohort's resources "
                                         "were still spent")
        block["label"] = FAILURES_IN_TOTALS_LABEL
    return {
        "arm": arm["arm"],
        "collapsed_from": list(arm.get("collapsed_from") or [arm["arm"]]),
        "items": len(rows),
        "accepted": accepted,
        "failed": failed,
        "censored": censored,
        "conditional_recovery": {
            "k": accepted, "n": resolved,
            "rate": round(accepted / resolved, 6) if resolved else None,
            "ci95": wilson(accepted, resolved),
            "censored": censored,
            "undefined_reason": None if resolved else "no outcome was resolved",
            "note": CONDITIONAL_RECOVERY_NOTE,
        },
        "initial_attempt": {
            "items": len(rows), "analytically_reused": reused,
            "priced_usd": round(initial_priced, 6), "label": ANALYTIC_REUSE_LABEL,
        },
        "scopes": scopes,
        "labels": [FAILURES_IN_TOTALS_LABEL, ANALYTIC_REUSE_LABEL],
    }


def compare_conditional_recovery(accountings, *, baseline_arm, threshold):
    """Differences in conditional recovery against one baseline arm -- numbers, never a verdict
    this module invented.

    `threshold` is the OPERATOR's declared practical gain, or `None` when none was declared. With
    `None` every verdict is `None` and says why: there is no universal success threshold here, and
    a difference that clears nothing is not a result. Overlapping intervals get their own note,
    because a positive point estimate inside a wide interval is the shape that most often gets
    read as a win.
    """
    rows = {a["arm"]: a for a in accountings}
    if baseline_arm not in rows:
        raise EvalError(f"baseline arm {baseline_arm!r} is not among {sorted(rows)}")
    base = rows[baseline_arm]["conditional_recovery"]
    out = []
    for name in sorted(rows):
        if name == baseline_arm:
            continue
        other = rows[name]["conditional_recovery"]
        delta = (None if base["rate"] is None or other["rate"] is None
                 else round(other["rate"] - base["rate"], 6))
        if delta is None:
            verdict, why = None, "at least one arm resolved no outcome"
        elif threshold is None:
            verdict, why = None, ("no operator-declared practical gain threshold; this module "
                                  "supplies none")
        else:
            verdict = "meets-declared-threshold" if delta >= threshold \
                else "below-declared-threshold"
            why = f"against the operator's declared threshold {threshold!r}"
        overlap = None
        if base["ci95"] and other["ci95"]:
            overlap = not (other["ci95"][0] > base["ci95"][1]
                           or base["ci95"][0] > other["ci95"][1])
        out.append({
            "arm": name, "baseline": baseline_arm,
            "collapsed_from": list(rows[name].get("collapsed_from") or [name]),
            "rate": other["rate"], "baseline_rate": base["rate"], "delta": delta,
            "ci95": other["ci95"], "baseline_ci95": base["ci95"],
            "intervals_overlap": overlap,
            "censored": {"arm": other["censored"], "baseline": base["censored"]},
            "verdict": verdict, "verdict_reason": why,
            "note": OVERLAPPING_INTERVAL_NOTE,
        })
    return out

# END OF THE THREE-ARM RECOVERY TRIAL PROTOCOL (decision-improvement D18)


class Evaluation:
    """One run: every trial through its workflow, graded by the same oracle, recorded."""

    def __init__(self, plan, tasks, adapter, *, store_dir, runner=None, git_runner=None,
                 test_runner=None, binary=None, max_usd=None, max_dispatches=None,
                 exec_mode="enforced", keep_work=False, out=None, err=None, pricing=None,
                 timeout=DEFAULT_TIMEOUT_SECONDS, verify_factory=None, partition="promotion"):
        if partition not in PARTITIONS:
            raise EvalError(f"unknown partition {partition!r}; the four are "
                            f"{', '.join(PARTITIONS)}")
        self.partition = partition
        self.plan = plan
        self.tasks = {t["task_id"]: t for t in tasks}
        self.adapter = adapter
        self.harness = adapter["name"]
        self.store_dir = Path(store_dir)
        self.runner = runner or default_runner(self.harness, timeout)
        self.git_runner = git_runner
        self.test_runner = test_runner
        self.binary = binary or adapter["binary"]
        self.max_usd = max_usd
        self.max_dispatches = max_dispatches if max_dispatches is not None else plan["caps"]["max_dispatches"]
        self.exec_mode = exec_mode
        self.keep_work = keep_work
        self.out = out or sys.stdout
        self.err = err or sys.stderr
        self.pricing = pricing if pricing is not None else adapter["load_pricing"]()
        self.verify_factory = verify_factory or (lambda ws: _ep().verify_runner(ws, mode=self.exec_mode))
        full = plan.get("_variants_full") or build_variants(
            plan["harness"], plan["candidates"], plan["workflows"], plan["policies"])
        self.variants = {v["id"]: v for v in full}
        self.spent_usd = 0.0
        self.dispatched = 0
        self.stopped = None
        self.totals = empty_totals()
        self.red_check = {}
        self.run_id = None
        self.run_dir = None

    def say(self, line):
        print(line, file=self.out)

    # -- ledger --

    def ledger(self, namespace="eval"):
        return _al().AttemptLedger(self.run_dir / "attempts", namespace)

    def _ceiling_allows(self, cost):
        rb = _rb()
        if self.dispatched >= self.max_dispatches:
            return False, f"hard cap: {self.max_dispatches} dispatch(es) already made"
        usd = priced_usd(cost)
        if self.max_usd is not None and rb.would_exceed_ceiling(self.spent_usd, usd, self.max_usd):
            return False, (f"cost ceiling: recorded ${self.spent_usd:.4f} + this dispatch's est. "
                           f"${usd:.4f} exceeds --max-usd ${self.max_usd:.4f}")
        return True, None

    def _dispatch(self, ledger, trial_id, stage, task, model, prompt, cwd, role, op,
                  requested_model, review=False, lifecycle=None, verify_cmd=None):
        """One recorded dispatch -> the stage record. Ceiling and cap checked FIRST."""
        cost_est = stage_cost(self.adapter, model, task["size_profile"], self.pricing, None)
        ok, why = self._ceiling_allows(cost_est)
        if not ok:
            self.stopped = self.stopped or why
            return {"stage": stage, "skipped": "cost-ceiling" if "ceiling" in why else "hard-cap",
                    "reason": why, "model": model, "cost": None}
        build = self.adapter["build_review_argv"] if review else self.adapter["build_argv"]
        argv = build(self.binary, model, prompt, task_id=trial_id, workspace=cwd)
        if lifecycle is not None:
            attempt = lifecycle.attempt_started(op, model, prompt, verify_cmd)
        else:
            attempt = ledger.record_started(self.run_id, trial_id, op, model, prompt=prompt,
                                            role=role, actor=self.harness,
                                            requested_model=requested_model)
        started = time.monotonic()
        try:
            raw = self.runner(argv, str(cwd))
        except OSError as exc:
            raw = (126, f"dispatch failed: {exc}", {"outcome": "start-failed"})
        wall = time.monotonic() - started
        rc, output, proc, telemetry = _unpack(raw)
        self.dispatched += 1
        observed = self.adapter["observed_model"](output) or telemetry.get("actual_model")
        usage = self.adapter["extract_usage"](output)
        cost = stage_cost(self.adapter, model, task["size_profile"], self.pricing, usage)
        add_cost(self.totals, cost)
        self.spent_usd = _rb().accrue_spend(self.spent_usd, priced_usd(cost))
        extra = {"cost_usd": cost.get("usd") if cost["basis"] in ("model-reported", "estimated") else None,
                 "cost_source": "parsed" if cost["basis"] == "model-reported" else cost["basis"]}
        if lifecycle is not None:
            cls = lifecycle.attempt_finished(attempt, rc, output, proc_outcome=proc.get("outcome"),
                                             duration_s=round(wall, 3), observed_model=observed)
        else:
            al = _al()
            if rc is None and not proc.get("outcome"):
                cls, outcome = None, "unreported"
            else:
                cls = al.classify_dispatch(rc, output, proc_outcome=proc.get("outcome"))
                outcome = proc.get("outcome") or ("ok" if rc == 0 else "failed")
            ledger.record_finished(self.run_id, trial_id, attempt, outcome, rc, output, cls=cls,
                                   duration_s=round(wall, 3), observed_model=observed, **extra)
        return {"stage": stage, "attempt": attempt, "model": model, "observed_model": observed,
                "rc": rc, "class": cls, "wall_seconds": round(wall, 3), "usage": usage,
                "cost": cost, "output_tail": " ".join((output or "").split())[-600:],
                "skipped": None, "proc_outcome": proc.get("outcome")}

    # -- grading (identical for every workflow) --

    def _grade(self, task, patch, work_dir):
        rb = _rb()
        test_cmd = self.plan.get("test_cmd")
        if task["task_id"] not in self.red_check:
            self.red_check[task["task_id"]] = rb.oracle_tests_red_check(
                task, self.plan["repo"], test_cmd, self.test_runner, work_dir,
                git_runner=self.git_runner)
        red = self.red_check[task["task_id"]]
        if red and red.get("passed_at_base"):
            tests = {"oracle": "tests", "available": False, "passed": None, "rc": None,
                     "notes": rb.TESTS_NOT_DISCRIMINATING_NOTE, "out_of_scope": None}
        else:
            tests = rb.oracle_tests(task, patch, test_cmd, self.test_runner, work_dir,
                                    target_repo=self.plan["repo"], git_runner=self.git_runner)
        structural = rb.oracle_structural(task["reference_patch"], patch)
        return {"tests": tests, "structural": structural,
                "touched_tests": rb._touched_test_paths(patch),
                "out_of_scope": tests.get("out_of_scope")}

    # -- workflows --

    def _run_trial(self, trial, work_dir, ledger):
        rb, kc = _rb(), _kc()
        task = self.tasks[trial["task_id"]]
        variant = self.variants[trial["variant"]]
        rec = {"trial": trial["trial"], "task_id": task["task_id"], "variant": variant["id"],
               "harness": self.harness, "workflow": variant["workflow"], "policy": variant["policy"],
               "repeat": trial["repeat"], "order": trial["order"], "size_profile": task["size_profile"],
               "task_class": task["mode"], "instruction_version": variant["instruction_version"],
               "stages": [], "routing": {}, "patch": None, "oracles": None, "solved": None,
               "accepted": None, "acceptance_by": None, "incorrect_acceptance": False,
               "review": None, "kit": None, "resume": None, "privacy": None, "excluded": None,
               "skipped": None, "wall_seconds": None, "adjudication": None,
               "robustness": {k: None for k in ROBUSTNESS}}
        routed = route_stage(self.adapter, self.pricing, variant, task, "implementer", task["size_profile"])
        rec["routing"]["implement"] = {"model": routed["model"], "decision": routed["decision"],
                                       "refusal": routed["refusal"]}
        if routed["refusal"] or not routed["model"] and variant["policy"] != "pinned":
            rec["skipped"] = "routing-refused"
            rec["reason"] = routed["refusal"] or "no model"
            return rec
        model = routed["model"]
        rec["model_requested"] = variant.get("model")
        rec["model_dispatched"] = model
        preamble = kc.build_id_preamble(kit=f"eval-{self.run_id}", run_id=self.run_id,
                                        task_id=trial["trial"])
        prompt, privacy = build_stage_prompt(task, variant, preamble)
        rec["privacy"] = privacy
        rec["robustness"]["privacy"] = dict(privacy["redactions"])
        sandbox_dir = work_dir / f"{trial['trial']}-sandbox"
        info, baseline = rb.prepare_cell_sandbox(task, self.plan["repo"], sandbox_dir,
                                                 git_runner=self.git_runner)
        sandbox = Path(info["path"])
        try:
            if variant["workflow"] == "kit":
                stage = self._kit_stage(trial, task, variant, model, prompt, sandbox, work_dir, rec)
            else:
                stage = self._dispatch(ledger, trial["trial"], "implement", task, model, prompt, sandbox,
                                       "implementer", "initial", variant.get("model"))
            rec["stages"].append(stage)
            if stage.get("skipped"):
                rec["skipped"] = stage["skipped"]
                rec["reason"] = stage["reason"]
                return rec
            rec["wall_seconds"] = _accrue_wall(rec["wall_seconds"], stage.get("wall_seconds"))
            observed = stage.get("observed_model")
            rec["model_observed"] = observed
            if observed is not None and observed != model:
                rec["robustness"]["policy_violation"] = f"host attested {observed}, dispatched {model}"
                rec["excluded"] = "policy-mismatch"
            patch = rb.capture_patch(sandbox, init_commit=baseline, git_runner=self.git_runner)
            rec["patch"] = patch
            if variant["workflow"] == "reviewed" and stage.get("rc") in (0, None):
                review = self._review_stage(ledger, trial, task, variant, patch, rec)
                rec["stages"].append(review)
                if not review.get("skipped"):
                    rec["wall_seconds"] = _accrue_wall(rec["wall_seconds"],
                                                       review.get("wall_seconds"))
            rec["oracles"] = self._grade(task, patch, work_dir)
            rec["solved"] = rec["oracles"]["tests"].get("passed") is True
            if rec["oracles"]["touched_tests"]:
                rec["robustness"]["evidence_tampering"] = list(rec["oracles"]["touched_tests"])
            if rec["accepted"] is True and not rec["solved"]:
                rec["incorrect_acceptance"] = True
                rec["robustness"]["incorrect_acceptance"] = rec["acceptance_by"]
        finally:
            if not self.keep_work:
                shutil.rmtree(sandbox_dir, ignore_errors=True)
        return rec

    def _review_stage(self, ledger, trial, task, variant, patch, rec):
        routed = route_stage(self.adapter, self.pricing, variant, task, "reviewer", task["size_profile"])
        rec["routing"]["review"] = {"model": routed["model"], "decision": routed["decision"],
                                    "refusal": routed["refusal"]}
        if routed["refusal"] or not routed["model"]:
            rec["review"] = {"verdict": None, "parsed": False, "skipped": "routing-refused"}
            return {"stage": "review", "skipped": "routing-refused", "reason": routed["refusal"],
                    "model": None, "cost": None}
        kc = _kc()
        preamble = kc.build_id_preamble(kit=f"eval-{self.run_id}", run_id=self.run_id, task_id=trial["trial"])
        prompt = build_review_prompt(task, patch, preamble)
        # The reviewer's cwd is a throwaway OUTSIDE the run dir: the run dir holds nothing yet,
        # and the candidate's sandbox is not the reviewer's to change.
        with tempfile.TemporaryDirectory(prefix="workflow-eval-review-") as cwd:
            stage = self._dispatch(ledger, trial["trial"], "review", task, routed["model"], prompt,
                                   Path(cwd), "reviewer", "review", variant.get("review_model"),
                                   review=True)
        if stage.get("skipped"):
            rec["review"] = {"verdict": None, "parsed": False, "skipped": stage["skipped"]}
            return stage
        parsed = parse_review(stage.get("output_tail", ""))
        rec["review"] = parsed
        if parsed["verdict"] in ("accept", "reject"):
            rec["accepted"] = parsed["verdict"] == "accept"
            rec["acceptance_by"] = "review"
        return stage

    def _kit_stage(self, trial, task, variant, model, prompt, sandbox, work_dir, rec):
        """The task as a one-task kit on the contract: claim, admission, check, projection."""
        kc = _kc()
        kit_dir = work_dir / f"{trial['trial']}-kit"
        kit_dir.mkdir(parents=True, exist_ok=True)
        statement, _priv = redacted_statement(task)
        tid = trial["trial"]
        (kit_dir / "TASKS.md").write_text(
            f"## Phase 1 {kc.EM_DASH} evaluation\n\n### {tid} {kc.EM_DASH} {task['task_id']}\n"
            f"- status: pending\n- model: {model}\n- depends: (none)\n- independent: yes\n\n"
            f"**Brief.** {statement}\n\n**Acceptance.** The repository's own test command passes.\n\n"
            f"**Verify.**\n```bash\n{self.plan['test_cmd']}\n```\n")
        # One dispatch plus one recovery: a dead attempt is closed as unknown and still counts
        # against the kit's budget (the contract's rule), so a kit that admits exactly one
        # could never resume. A third is refused and recorded as the budget outcome.
        (kit_dir / "PLAN.md").write_text("# eval kit\n\nbudget: max-dispatches=2\n")
        tasks = kc.parse_tasks((kit_dir / "TASKS.md").read_text())
        ktask = tasks[0]
        ledger = kc.open_ledger(kit_dir, store=self.run_dir / "attempts")
        lifecycle = kc.TaskRun(ledger, self.run_id, ktask, workspace=sandbox, actor=self.harness,
                               role="implementer")
        info = lifecycle.begin()
        rec["resume"] = {"closed_unknown": len(info.get("closed_unknown") or []),
                         "stale_claim": bool(info.get("stale_from")),
                         "unprojected": len(info.get("unprojected") or []), "redispatched": None}
        if rec["resume"]["closed_unknown"] or rec["resume"]["stale_claim"]:
            rec["robustness"]["resume"] = dict(rec["resume"])
        verify = self.verify_factory(sandbox)
        plan_budget = kc.parse_plan_budget(kc._plan_text(kit_dir))
        used = kc.combined_usage("", ledger)
        admission = kc.BudgetAdmission(plan_budget, used) if plan_budget else None
        kc.project_status(kit_dir / "TASKS.md", tid, "in-progress")
        recon = kc.reconcile_task(lifecycle, info, verify, ktask["verify"])
        stage = {"stage": "implement", "model": model, "skipped": None, "wall_seconds": None,
                 "cost": None, "rc": None, "observed_model": None}
        if recon["mode"] == "resolved":
            result = recon["result"]
            rec["resume"]["redispatched"] = False
            stage["resolved_without_dispatch"] = True
        else:
            kind = "retry" if recon["mode"] == "retry" else "initial"
            if recon["mode"] == "retry":
                prompt = prompt + recon["context"]
                rec["resume"]["redispatched"] = True
            ok, reason = admission.check(kind) if admission else (True, None)
            if not ok:
                result = kc._budget_stop(ktask, model, [], kind, reason)
                rec["robustness"]["budget_overshoot"] = f"kit refused: {reason}"
                stage["skipped"] = "budget-stop"
                stage["reason"] = reason
            else:
                if admission:
                    admission.admit(kind)
                started = time.monotonic()
                stage = self._dispatch(None, tid, "implement", task, model, prompt, sandbox,
                                       "implementer", kind, variant.get("model"), lifecycle=lifecycle,
                                       verify_cmd=ktask["verify"])
                if stage.get("skipped"):
                    result = kc._budget_stop(ktask, model, [], kind, stage["reason"])
                else:
                    check_started = time.monotonic()
                    try:
                        vrc, vout = verify(ktask["verify"])
                    except OSError as exc:
                        vrc, vout = 126, f"verify failed to start: {exc}"
                    lifecycle.verify_finished(stage["attempt"], vrc, vout)
                    stage["check"] = {"rc": vrc, "wall_seconds": round(time.monotonic() - check_started, 3),
                                      "mode": self.exec_mode}
                    stage["wall_seconds"] = round(time.monotonic() - started, 3)
                    rc = stage.get("rc")
                    result = {"id": tid, "status": "done" if vrc == 0 else "blocked", "model_used": model,
                              "planned_model": model, "observed_model": stage.get("observed_model"),
                              "escalations": [], "verify_rc": vrc, "dispatch_rc": rc, "usd": None,
                              "failure": None if vrc == 0 else "verification", "class": stage.get("class")}
                    if rc not in (0, None):
                        result.update(status="blocked", verify_rc=None, failure="dispatch")
        kc.finish_task_projection(lifecycle, kit_dir / "TASKS.md", ktask, result)
        kc.append_run_note(kit_dir / "NOTES.md", result, ktask, run_id=self.run_id, actor=self.harness)
        lifecycle.project(result["status"], kc.outcome_result(result["status"], [], None), outcome_line=True)
        lifecycle.end()
        rec["kit"] = {"status": result["status"], "failure": result.get("failure"),
                      "verify_rc": result.get("verify_rc"), "ledger_attempts": result.get("ledger_attempts"),
                      "kit_dir": str(kit_dir)}
        rec["accepted"] = result["status"] == "done"
        rec["acceptance_by"] = "kit-check"
        return stage

    # -- the loop --

    @property
    def manifest_root(self):
        """Where THIS evaluator files its manifests: `<run dir>/manifests/`.

        Inside the run directory rather than at the store root, because the store root holds
        exactly the run directories and readers walk it expecting that. The manifest functions
        themselves take their root as an argument, so a pool shared across runs -- a
        repository-level partitioning, which nothing mines today -- is a different root passed
        by whoever owns that pool, not a different writer.
        """
        return self.run_dir

    def _record_manifest(self, labels, notes):
        """This run's tasks -> one immutable manifest in the store, plus the exposure it caused.

        `on_leak="quarantine"`, not `"reject"`: by the time this runs the tasks have already
        been dispatched against, so a leak found now is a fact to write down, not a pool to
        refuse. Quarantined material is in the manifest, is in the exposure record, and is in
        no partition -- `require_held_out` can never cite it.

        Every failure here is degraded to a label and a note rather than raised: this runs in
        `run`'s `finally`, and a manifest problem must not cost an operator the results of a
        run that may have spent real money. An absent manifest is disclosed, never implied.
        """
        try:
            manifest = build_manifest(
                self.plan["repo"], self.plan["base_commit"],
                [self.tasks[tid] for tid in sorted(self.tasks)],
                allocation={self.partition: 1}, on_leak="quarantine",
                acceptance=self.plan.get("test_cmd"), created_by="workflow_eval",
                labels=[f"pool mined for one evaluation run: the whole pool is "
                        f"{self.partition} material"])
            write_manifest(self.manifest_root, manifest)
            record_exposure(self.manifest_root, manifest, partition=self.partition,
                            items=sorted(manifest["content"]["items"]), by="workflow_eval",
                            run=self.run_id,
                            note="every task of this run was dispatched against")
        except (EvalError, OSError, ValueError) as exc:  # noqa: BLE001 -- disclosed, not fatal
            labels.append(f"manifest unavailable: {type(exc).__name__}: {exc}")
            return None
        summary = manifest_summary(manifest)
        if summary["quarantined"]:
            labels.append(
                f"{summary['quarantined']} task(s) quarantined from the {self.partition} "
                f"partition: their problem statements screen positive for "
                f"{', '.join(f'{k}={v}' for k, v in summary['leaks'].items())} (counts by kind; "
                f"the values are never quoted). Quarantined material is never held-out evidence")
            notes.append(f"manifest {manifest['id']}: {summary['quarantined']} of "
                         f"{summary['items']} item(s) quarantined")
        return manifest

    def run(self):
        rb = _rb()
        self.run_id, self.run_dir = rb.new_run_dir(self.store_dir)
        work_dir = self.run_dir / "work"
        ledger = self.ledger()
        ledger.append("eval.started", run=self.run_id, harness=self.harness,
                      variants=[v["id"] for v in self.plan["variants"]],
                      trials=len(self.plan["trials"]), max_usd=self.max_usd,
                      max_dispatches=self.max_dispatches, registry=self.plan["registry"],
                      pricing_date=self.plan["pricing_date"], instruction_versions=sorted(
                          {v["instruction_version"] for v in self.plan["variants"]}))
        records = []
        labels = list(self.plan["labels"])
        notes = list(self.plan["notes"])
        completed = False
        try:
            for trial in self.plan["trials"]:
                if self.stopped:
                    records.append({"trial": trial["trial"], "task_id": trial["task_id"],
                                    "variant": trial["variant"], "repeat": trial["repeat"],
                                    "order": trial["order"], "skipped": "cost-ceiling"
                                    if "ceiling" in self.stopped else "hard-cap",
                                    "reason": self.stopped, "solved": None, "stages": []})
                    continue
                try:
                    records.append(self._run_trial(trial, work_dir, ledger))
                except Exception as exc:  # noqa: BLE001 -- one trial's failure is recorded, not fatal
                    records.append({"trial": trial["trial"], "task_id": trial["task_id"],
                                    "variant": trial["variant"], "repeat": trial["repeat"],
                                    "order": trial["order"], "skipped": "error",
                                    "reason": f"{type(exc).__name__}: {exc}", "solved": None, "stages": []})
                    notes.append(f"{trial['trial']}: {type(exc).__name__}: {exc}")
            completed = True
        finally:
            overspent = self.max_usd is not None and self.spent_usd > self.max_usd
            if self.stopped:
                labels.append(f"partial ({'cost-ceiling' if 'ceiling' in self.stopped else 'hard-cap'})")
                notes.append(self.stopped)
            if overspent:
                labels.append(f"overspend: ${self.spent_usd:.4f} recorded against a ${self.max_usd:.4f} ceiling")
            if not completed:
                labels.append("aborted: the trial loop raised before completing")
            manifest = self._record_manifest(labels, notes)
            envelope = {
                "v": EVAL_VERSION, "run_id": self.run_id, "repo": self.plan["repo"],
                "base_commit": self.plan["base_commit"], "harness": self.harness, "mode": self.plan["mode"],
                "registry": self.plan["registry"], "pricing_date": self.plan["pricing_date"],
                "workflows": self.plan["workflows"], "policies": self.plan["policies"],
                "candidates": self.plan["candidates"], "repeats": self.plan["repeats"],
                "variants": self.plan["variants"], "refused_variants": self.plan["refused_variants"],
                "trials": records, "totals": self.totals,
                "spend": {"ceiling_usd": self.max_usd, "spent_usd": round(self.spent_usd, 6),
                          "priced_bases": ["model-reported", "estimated"],
                          "max_dispatches": self.max_dispatches, "dispatched": self.dispatched,
                          "overspent": overspent},
                "holdout": {"tasks": sorted(self.tasks), "reserved_from": "routing tuning",
                            "partition": self.partition,
                            "manifest_ref": manifest_ref(manifest),
                            "manifest_dir": MANIFEST_DIR if manifest else None,
                            "manifest": manifest_summary(manifest) if manifest else None},
                "labels": labels, "notes": notes, "adjudications": [],
                "evidence_floor": rb.MIN_EVIDENCE_TASKS, "untested_claims": list(untested_claims()),
            }
            # Records land in the store only now: no dispatch of any kind is live.
            for tid, task in self.tasks.items():
                (self.run_dir / "tasks" / f"{tid}.json").write_text(json.dumps(task, indent=2) + "\n")
            trials_dir = self.run_dir / "trials"
            trials_dir.mkdir(exist_ok=True)
            for rec in records:
                (trials_dir / f"{rec['trial']}.json").write_text(json.dumps(rec, indent=2) + "\n")
            (self.run_dir / "plan.json").write_text(json.dumps(
                {k: v for k, v in self.plan.items() if k != "_variants_full"}, indent=2) + "\n")
            (self.run_dir / "results.json").write_text(json.dumps(envelope, indent=2) + "\n")
            if manifest is not None:
                # Only now are results over this partition KNOWN, which is what closes cohort
                # selection against it: `declare_cohort` and `select_cohort` both refuse a
                # declaration that lands after this entry.
                try:
                    record_results(self.manifest_root, manifest, partition=self.partition,
                                   run=self.run_id, by="workflow_eval",
                                   note="results.json written")
                except (EvalError, OSError, ValueError) as exc:  # noqa: BLE001 -- recorded, not fatal
                    notes.append(f"manifest results entry not recorded: {type(exc).__name__}: {exc}")
            ledger.append("eval.finished", run=self.run_id, trials=len(records),
                          dispatched=self.dispatched, spent_usd=round(self.spent_usd, 6),
                          stopped=self.stopped)
            if not self.keep_work:
                shutil.rmtree(work_dir, ignore_errors=True)
        return envelope


# ---- the card ------------------------------------------------------------------------------------------------

def _variant_summary(variant_id, recs, floor, repeats):
    live = [r for r in recs if not r.get("skipped") and not r.get("excluded")]
    n = len(live)
    solved = sum(1 for r in live if r.get("solved"))
    accepted = [r for r in live if r.get("accepted") is not None]
    incorrect = sum(1 for r in live if r.get("incorrect_acceptance"))
    review_reject_solved = sum(1 for r in live if r.get("solved") and r.get("accepted") is False)
    reviews = [r for r in live if r.get("review")]
    coverage = {"tests_oracle": (sum(1 for r in live if (r.get("oracles") or {}).get("tests", {}).get("available"))
                                 / n) if n else None,
                "review_parsed": (sum(1 for r in reviews if r["review"].get("parsed")) / len(reviews))
                if reviews else None}
    totals = empty_totals()
    wall = None
    interventions = 0
    robustness = {k: 0 for k in ROBUSTNESS}
    for r in recs:
        for st in r.get("stages") or []:
            if st.get("cost"):
                add_cost(totals, st["cost"])
        wall = _accrue_wall(wall, r.get("wall_seconds"))
        if r.get("adjudication"):
            interventions += 1
        rb_ = r.get("robustness") or {}
        for k in ROBUSTNESS:
            if rb_.get(k):
                robustness[k] += 1
        if (r.get("resume") or {}).get("closed_unknown"):
            interventions += 1
    by_task = {}
    for r in live:
        by_task.setdefault(r["task_id"], []).append(bool(r.get("solved")))
    unstable = [t for t, outs in by_task.items() if len(outs) > 1 and len(set(outs)) > 1]
    stability = (1 - len(unstable) / len(by_task)) if by_task and repeats > 1 else None
    excluded = {}
    for r in recs:
        key = r.get("skipped") or r.get("excluded")
        if key:
            excluded[key] = excluded.get(key, 0) + 1
    return {
        "variant": variant_id, "n": n, "solved": solved, "rate": (solved / n) if n else None,
        "interval_95": wilson(solved, n), "below_floor": n < floor,
        "acceptances": len(accepted), "incorrect_acceptance": incorrect,
        "escaped_defects": incorrect, "review_rejected_solved": review_reject_solved,
        "interventions": interventions,
        "wall_seconds": round(wall, 3) if wall is not None else None,
        "mean_wall_seconds": round(wall / n, 3) if (wall is not None and n) else None,
        "usage": totals,
        "coverage": coverage, "stability": stability, "unstable_tasks": unstable,
        "excluded": excluded, "robustness": robustness,
    }


def build_card(envelope):
    """What the run shows, per variant and per stratum, with its uncertainty stated."""
    floor = envelope.get("evidence_floor") or _rb().MIN_EVIDENCE_TASKS
    repeats = envelope.get("repeats") or 1
    recs = envelope.get("trials") or []
    adjudicated = {a["trial"]: a for a in envelope.get("adjudications") or []}
    for r in recs:
        if r["trial"] in adjudicated:
            r["adjudication"] = adjudicated[r["trial"]]
    variants = [v["id"] for v in envelope.get("variants") or []]
    summaries = [_variant_summary(v, [r for r in recs if r.get("variant") == v], floor, repeats)
                 for v in variants]
    strata = {}
    for key in ("task_id", "size_profile", "task_class", "workflow", "policy", "harness",
                "instruction_version"):
        buckets = {}
        for r in recs:
            if r.get("skipped") or r.get("excluded") or r.get(key) is None:
                continue
            b = buckets.setdefault(str(r[key]), {"n": 0, "solved": 0})
            b["n"] += 1
            b["solved"] += 1 if r.get("solved") else 0
        strata[key] = buckets
    strata["repository"] = {envelope.get("repo"): {"n": sum(1 for r in recs if not r.get("skipped")
                                                             and not r.get("excluded"))}}
    rankable = summaries and all(not s["below_floor"] for s in summaries) and repeats >= 2
    ranking = None
    if rankable:
        # `wall_seconds` is `None` (decision-improvement D05) when every live trial resolved
        # without a new dispatch (an already-passing resume) -- no measured time to prefer on,
        # so it sorts LAST on this tie-break rather than crashing the comparison or being read
        # as fastest;
        # the same convention `repo_bench._daily_driver` uses for an unmeasured median.
        ranking = [s["variant"] for s in sorted(summaries, key=lambda s: (
            -(s["rate"] or 0), s["incorrect_acceptance"],
            s["wall_seconds"] if s["wall_seconds"] is not None else float("inf")))]
    labels = list(envelope.get("labels") or [])
    if not rankable:
        labels.append(NOT_A_RANKING)
    for s in summaries:
        if s["below_floor"]:
            labels.append(f"{s['variant']}: BELOW EVIDENCE FLOOR (n={s['n']} < {floor})")
    disagreements = sum(s["incorrect_acceptance"] for s in summaries)
    return {
        "v": EVAL_VERSION, "run_id": envelope.get("run_id"), "repo": envelope.get("repo"),
        "harness": envelope.get("harness"), "registry": envelope.get("registry"),
        "pricing_date": envelope.get("pricing_date"), "repeats": repeats,
        "evidence_floor": floor, "variants": summaries, "strata": strata, "ranking": ranking,
        "spend": envelope.get("spend"), "totals": envelope.get("totals"),
        "adjudications": len(adjudicated), "escaped_defects_total": disagreements,
        "sample": {"tasks": len({r["task_id"] for r in recs}), "trials": len(recs),
                   "repeats": repeats, "repositories": 1},
        "labels": labels, "notes": list(envelope.get("notes") or []),
        "untested_claims": list(envelope.get("untested_claims") or untested_claims()),
    }


def _pct(rate):
    return "n/a" if rate is None else f"{rate * 100:.0f}%"


def render_card_markdown(card):
    lines = [f"# workflow-eval card — run {card['run_id']} ({card['repo']})", "",
             f"harness: {card['harness']}; pricing {card['pricing_date'] or 'none'}; registry "
             f"{card['registry']}; repeats: {card['repeats']}; evidence floor: {card['evidence_floor']}",
             ""]
    lines.append("## variants (solved = tests oracle only; never merged with acceptance or adjudication)")
    lines.append("| variant | n | solved | 95% interval | incorrect acceptance | interventions | "
                 "mean wall s | stability | usage (per basis) |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for s in card["variants"]:
        iv = s["interval_95"]
        u = s["usage"]
        usage = (f"reported n={u['model-reported']['n']} ${u['model-reported']['usd']:.4f}; "
                 f"est. n={u['estimated']['n']} ${u['estimated']['usd']:.4f}; "
                 f"proxy n={u['proxy']['n']} ${u['proxy']['api_equivalent_usd']:.4f}; "
                 f"credits {u['credits']['credits']:.2f}; unpriced n={u['unpriced']['n']}")
        lines.append(f"| {s['variant']} | {s['n']}{' (below floor)' if s['below_floor'] else ''} | "
                     f"{s['solved']}/{s['n']} = {_pct(s['rate'])} | "
                     f"{'n/a' if not iv else f'[{iv[0]:.2f}, {iv[1]:.2f}]'} | "
                     f"{s['incorrect_acceptance']}/{s['acceptances']} | {s['interventions']} | "
                     f"{'n/a' if s['mean_wall_seconds'] is None else f'{s['mean_wall_seconds']:.2f}'} | "
                     f"{'n/a' if s['stability'] is None else _pct(s['stability'])} | {usage} |")
    lines.append("")
    lines.append("## ranking")
    lines.append("  " + (" > ".join(card["ranking"]) if card["ranking"] else NOT_A_RANKING))
    lines.append("")
    lines.append("## security and robustness outcomes")
    for s in card["variants"]:
        r = s["robustness"]
        lines.append(f"  - {s['variant']}: " + ", ".join(f"{k}={r[k]}" for k in ROBUSTNESS)
                     + (f"; excluded {s['excluded']}" if s["excluded"] else ""))
    lines.append("")
    lines.append("## strata (n / solved)")
    for key, buckets in card["strata"].items():
        if not buckets:
            continue
        lines.append(f"  {key}: " + "; ".join(
            f"{b}={v['n']}/{v.get('solved', '-')}" for b, v in sorted(buckets.items())))
    lines.append("")
    sp = card.get("spend") or {}
    lines.append("## spend")
    lines.append(f"  priced bases only: ${sp.get('spent_usd', 0.0):.4f} recorded against "
                 f"{'no ceiling' if sp.get('ceiling_usd') is None else f'${sp['ceiling_usd']:.4f}'}; "
                 f"{sp.get('dispatched', 0)} dispatch(es) of a {sp.get('max_dispatches', '?')} cap"
                 + ("; OVERSPENT" if sp.get("overspent") else ""))
    lines.append(f"  sample: {card['sample']}")
    lines.append("")
    lines.append("## labels")
    for label in card["labels"]:
        lines.append(f"label: {label}")
    for note in card["notes"]:
        lines.append(f"note: {note}")
    lines.append("")
    lines.append("## untested claims")
    for claim in card["untested_claims"]:
        lines.append(f"  - {claim}")
    return "\n".join(lines)


# ---- store readers ------------------------------------------------------------------------------------------

def read_envelope(store_dir, run_id):
    path = Path(store_dir) / run_id / "results.json"
    if not path.exists():
        raise FileNotFoundError(f"no results.json for run {run_id!r} under {store_dir}")
    return json.loads(path.read_text())


def write_envelope(store_dir, run_id, envelope):
    path = Path(store_dir) / run_id / "results.json"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(envelope, indent=2) + "\n")
    tmp.replace(path)


def list_runs(store_dir):
    """Every run under the store, tolerant of absence and of entries that are not runs."""
    store_dir = Path(store_dir)
    if not store_dir.is_dir():
        return [], [f"no evals store at {store_dir}"]
    rows, notes = [], []
    for entry in sorted(store_dir.iterdir()):
        if entry.name == MANIFEST_DIR and entry.is_dir():
            continue  # this owner's own manifests, beside the runs -- not a malformed run
        results = entry / "results.json"
        if not entry.is_dir() or not results.exists():
            notes.append(f"{entry.name}: not an evaluation run")
            continue
        try:
            env = json.loads(results.read_text())
        except (OSError, ValueError):
            notes.append(f"{entry.name}: results.json unreadable")
            continue
        if env.get("v") != EVAL_VERSION:
            notes.append(f"{entry.name}: not a {EVAL_VERSION} envelope")
            continue
        rows.append({"run_id": env.get("run_id", entry.name), "repo": env.get("repo"),
                     "harness": env.get("harness"), "trials": len(env.get("trials") or []),
                     "spent_usd": (env.get("spend") or {}).get("spent_usd"),
                     "labels": env.get("labels") or []})
    return rows, notes


def history_records(store_dir, run_id):
    """Every attempt of the run through attempt_history, tiers from the registry."""
    ah, al, mr = _ah(), _al(), _mr()
    root = Path(store_dir) / run_id / "attempts"
    registry = mr.registry()
    records = []
    if root.is_dir():
        for ns in sorted(p.name for p in root.iterdir() if p.is_dir()):
            ledger = al.AttemptLedger(root, ns)
            records.extend(ah.ledger_records(f"{run_id}/{ns}", ledger, registry))
    return records, ah.summarize(records, registry=registry)


def adjudicate(store_dir, run_id, trial_id, by, verdict, note=""):
    """A person's verdict on one trial, appended with provenance; `solved` is untouched."""
    if verdict not in ADJUDICATIONS:
        raise EvalError(f"verdict must be one of {', '.join(ADJUDICATIONS)}")
    if not by:
        raise EvalError("--by is required: an adjudication without a person is not one")
    env = read_envelope(store_dir, run_id)
    if not any(r["trial"] == trial_id for r in env.get("trials") or []):
        raise EvalError(f"run {run_id} has no trial {trial_id!r}")
    entry = {"trial": trial_id, "by": by, "verdict": verdict, "note": _rd().redact(note or "")["text"],
             "at": _now()}
    env.setdefault("adjudications", []).append(entry)
    write_envelope(store_dir, run_id, env)
    return entry


# ---- policy: propose / review / apply / rollback --------------------------------------------------------------
#
# D20. This module is this repository's ONE owner of policy persistence: the proposal files, the
# applied preference file, its history and its journal. What D20 adds is not a second store and
# not a second writer -- it is two more things the records ALREADY WRITTEN HERE may say, namely
# which policy bundle and which evaluation manifest a proposal was made against.
#
# WHY THAT IS A RELAY AND NOT A COMPUTATION. `bin/decision_contract.py` owns what a policy bundle
# is; `bin/decision_policy.py` builds the reference to one; the manifest section above owns what
# an evaluation manifest is and builds the reference to one. None of those is re-implemented
# here. `_policy_ref` takes a reference its OWNER computed, hands it back through
# `attempt_ledger`'s own reader and constructor, checks it names the contract this slot points
# at, and relays exactly what came back. There is no second derivation of a digest anywhere in
# this section, so there is nothing for a second derivation to drift away from.
#
# AND WHAT IT DELIBERATELY DOES NOT CLAIM. A relayed reference is a complete pointer that names
# the right kind of object. It is NOT evidence that the bytes it names exist, that they still
# digest to that sha, or that anybody approved them: this function never sees the content, and
# vouching for what it did not read is the defect D19's review named. `read_manifest` is what
# re-derives a manifest's digest, at the one place that actually opens the file, and `cmd_propose`
# goes through it before taking a reference. Nothing equivalent exists for bundles yet -- there
# is no bundle store in this repository -- so `build_proposal(bundle_ref=...)` records a pointer
# whose target nothing here can open, and says so rather than implying otherwise.
#
# NO AUTOMATIC CONSUMPTION, AND NO VERSION BUMP. Recording these references changes what a run
# can be ASKED about; it changes nothing about what any driver reads. The preference file stays
# pull-only. `PROPOSAL_VERSION` and `POLICY_VERSION` are NOT bumped: `read_proposal` refuses any
# proposal whose `v` is not the current one, so raising either would make every stored record
# unreadable rather than migrating it. The new block carries its OWN version, on the referenced
# object rather than on the envelope around it -- D04's precedent for the ledger, D11's for
# `BUNDLE_VERSION`. A record written before this block existed has no `refs` key, reads as
# unknown, and keeps working unchanged.

#: The version of the referenced-object block a proposal and an applied policy carry. Registered
#: in `release_gate.VERSION_SOURCES`.
POLICY_REFS_VERSION = "polytropos.policy-refs/1"

#: The slots that block carries. Each names a different contract, and which one is READ from its
#: owner at call time by `_policy_ref_version` rather than copied into a literal here.
POLICY_REF_SLOTS = ("bundle", "manifest")

#: The keys the stored block itself has: its version plus one entry per slot, every entry present
#: and explicitly null when unknown, so "nobody recorded it" can never look like "nobody wrote
#: the key".
POLICY_REFS_KEYS = ("v",) + POLICY_REF_SLOTS

#: What a review entry's `authority` field says, and the WHOLE of what it means. `review_proposal`
#: checks that a non-empty string was supplied and nothing else. It does not authenticate the
#: reviewer, does not establish that the named person read the evidence, and does not bind the
#: review to the bytes it reviewed. The field exists so a reader of a stored proposal is told
#: that, instead of inferring an authority from the presence of a name.
REVIEW_AUTHORITY = "name-only"
REVIEW_AUTHORITY_LABEL = (
    "review authority: name-only -- the reviewer is a string this command was handed, checked "
    "for being non-empty and for nothing else. That is not authentication, not a controller "
    "identity, and not evidence that the named person saw what they accepted; binding an "
    "approval to the exact candidate and evaluation it approved is a later, separately gated "
    "step and has not happened here")


def _policy_ref_version(slot):
    """Which contract version this slot's reference must name, read from that slot's owner.

    `decision_contract` owns what a policy bundle is; this module owns what an evaluation
    manifest is. Both are read here rather than copied, so neither can drift from a literal.
    """
    if slot == "bundle":
        return _dc().BUNDLE_VERSION
    if slot == "manifest":
        return MANIFEST_VERSION
    raise EvalError(f"{slot!r} is not a policy reference slot; the slots are "
                    f"{', '.join(POLICY_REF_SLOTS)}")


def _policy_ref(value, slot):
    """One owner-computed reference, relayed whole -- or refused. Never trimmed, never repaired.

    THE CLOSURE CHECK IS THE POINT, and it is checked in both directions. `attempt_ledger`'s
    `read_ref` is a PROJECTION: it reads `id`, `sha` and `v` and silently ignores everything
    else. Relaying its output without first checking that the input had no other keys would
    write a record that claims to carry the reference it was given while having quietly dropped
    part of it -- completeness this function did not check. So an unknown key is refused rather
    than dropped, and a missing one is refused rather than filled in. The accepted key set is
    `attempt_ledger.REF_FIELDS` itself, read from the owner, not a list written out here.

    Whole-payload confusion falls out of that closure for free: a bundle payload, a candidate
    payload and a preference file all carry keys a reference does not, so handing one of them to
    a slot that wants a pointer is refused as the shape error it is.

    A reference with an id but no digest or no contract version is refused too. `make_ref`
    permits both to be absent because a caller may honestly not know them, and for an event's
    provenance absent is the honest record. This is the opposite case: a proposal's whole reason
    for naming a bundle or a manifest is so that a later reader can notice those bytes changing,
    and a pointer that pins neither the bytes nor the contract cannot notice either.

    WHAT SURVIVING THIS DOES NOT ESTABLISH. That the target exists, that its content still
    digests to this sha, or that anything about it was approved. This function never opens
    anything. It vouches for the shape of a pointer and for which contract it points at.
    """
    expected = _policy_ref_version(slot)
    ledger = _al()
    fields = set(ledger.REF_FIELDS)
    if not isinstance(value, dict):
        raise EvalError(f"the {slot} reference must be an object with "
                        f"{', '.join(sorted(fields))}, not {type(value).__name__}")
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown or missing:
        detail = "; ".join(
            part for part in (
                f"unknown key(s) {', '.join(repr(k) for k in unknown)}" if unknown else "",
                f"missing {', '.join(repr(k) for k in missing)}" if missing else "")
            if part)
        raise EvalError(
            f"the {slot} reference is not the shape attempt_ledger.make_ref produces "
            f"({', '.join(sorted(fields))}): {detail}. A reference is relayed whole or not at "
            f"all -- read_ref would drop the extra key(s) in silence and this record would then "
            f"claim to carry what it dropped")
    ref = ledger.read_ref(value)
    if ref is None:
        raise EvalError(f"the {slot} reference carries nothing attempt_ledger.read_ref accepts "
                        f"as an id, so it points at nothing")
    gaps = ledger.ref_gaps(ref)
    if gaps:
        raise EvalError(
            f"the {slot} reference leaves {', '.join(gaps)} unknown; a pointer that pins neither "
            f"the bytes it names nor the contract they are written under cannot notice either of "
            f"them changing underneath it, which is the whole reason this record names it")
    if ref["v"] != expected:
        if slot == "bundle" and ref["v"] == _dc().LEGACY_PREFERENCE_VERSION:
            raise EvalError(
                f"the bundle reference points at a {ref['v']} preference payload. That file is "
                f"pull-only advice about defaults that no driver consumes; recording it as this "
                f"record's bundle would promote it into the thing a run pins, which is exactly "
                f"the silent promotion the bundle contract refuses. Re-propose the change as a "
                f"{expected} bundle")
        raise EvalError(f"the {slot} reference points at a {ref['v']!r} object; this slot points "
                        f"at {expected!r}")
    try:
        # The owner's own constructor, re-run over the owner's own reader's output: the bounds
        # and types a reference must satisfy are checked where they are defined, not again here.
        return ledger.make_ref(ref["id"], sha=ref["sha"], version=ref["v"])
    except ledger.RefError as exc:
        raise EvalError(f"the {slot} reference is not one attempt_ledger would make: {exc}") \
            from None


def policy_refs(*, bundle_ref=None, manifest_ref=None):
    """The referenced-object block a proposal and an applied policy carry.

    Both keyword names deliberately shadow the module-level generators that produce their
    values (`decision_policy.bundle_ref`, and this module's own `manifest_ref`), because that is
    how they read at a call site; nothing in this function needs either generator, and nothing
    in it computes a reference. An omitted slot is written as an explicit null -- unknown, never
    absent, and never back-filled from anything else on the record.
    """
    return {"v": POLICY_REFS_VERSION,
            "bundle": None if bundle_ref is None else _policy_ref(bundle_ref, "bundle"),
            "manifest": None if manifest_ref is None else _policy_ref(manifest_ref, "manifest")}


def read_policy_refs(record):
    """What a stored proposal or applied policy says about the bundle and manifest it cites.

    A READER, so it degrades and names what it could not read instead of raising: `recorded` is
    False for a record written before this block existed, and a slot this reader refuses is left
    null with its name in `unreadable`. Both read as unknown, which is what they are -- and
    nothing here tells them apart for the caller by inventing a distinction the record does not
    make. `_relay_refs` is the write-side counterpart and REFUSES instead of degrading.
    """
    out = {"v": None, "bundle": None, "manifest": None, "recorded": False, "unreadable": []}
    block = record.get("refs") if isinstance(record, dict) else None
    if not isinstance(block, dict):
        return out
    out["recorded"] = True
    version = block.get("v")
    out["v"] = version if isinstance(version, str) and version else None
    for slot in POLICY_REF_SLOTS:
        value = block.get(slot)
        if value is None:
            continue
        try:
            out[slot] = _policy_ref(value, slot)
        except EvalError:
            out["unreadable"].append(slot)
    return out


def _relay_refs(record, where):
    """Re-validate a stored record's reference block before carrying it forward. Refuses.

    The write-side counterpart to `read_policy_refs`, and the reason apply is not a laundry: a
    block that has been edited into something this module would not have written is refused
    rather than copied into the applied policy, where a later reader would find it with the
    applied policy's authority behind it. A record with no block at all is the pre-D20
    generation and is not an error -- it becomes an all-unknown block, which is what it says.
    A block whose own version is not this one is refused too: a later generation's record is
    not silently downgraded into this one's fields.
    """
    if not isinstance(record, dict) or "refs" not in record:
        return policy_refs()
    block = record["refs"]
    if not isinstance(block, dict):
        raise EvalError(f"{where} carries a 'refs' that is not an object but a "
                        f"{type(block).__name__}; nothing can be read from it")
    unknown = sorted(set(block) - set(POLICY_REFS_KEYS))
    missing = sorted(set(POLICY_REFS_KEYS) - set(block))
    if unknown or missing:
        raise EvalError(
            f"{where} carries a 'refs' block with "
            + "; ".join(part for part in (
                f"unknown key(s) {', '.join(repr(k) for k in unknown)}" if unknown else "",
                f"missing {', '.join(repr(k) for k in missing)}" if missing else "") if part)
            + f"; the block is {', '.join(POLICY_REFS_KEYS)} and every slot is present")
    if block["v"] != POLICY_REFS_VERSION:
        raise EvalError(f"{where} carries a {block['v']!r} reference block; this writer reads "
                        f"{POLICY_REFS_VERSION} and will not guess at another shape's fields")
    try:
        return policy_refs(bundle_ref=block["bundle"], manifest_ref=block["manifest"])
    except EvalError as exc:
        # Which record was refused is the part a reader needs and the slot refusal cannot know.
        raise EvalError(f"{where} cannot be carried forward: {exc}") from None


def _ref_ids(record):
    """Which bundle and manifest a record names, by id alone -- the journal's share of it."""
    read = read_policy_refs(record)
    return {slot: (read[slot]["id"] if read[slot] else None) for slot in POLICY_REF_SLOTS}


def _prefs_paths(prefs_dir):
    prefs_dir = Path(prefs_dir)
    return {"dir": prefs_dir, "policy": prefs_dir / POLICY_FILE, "history": prefs_dir / POLICY_HISTORY,
            "proposals": prefs_dir / POLICY_PROPOSALS, "journal": prefs_dir / POLICY_JOURNAL,
            # D22's approval records, in the same store under the same caller-named directory.
            # Naming a path creates nothing: a prefs directory that has never had an approval
            # written into it still holds exactly the four files it held before.
            "approvals": prefs_dir / POLICY_APPROVALS,
            # D23's activation pointer generations, same store, same writer, same rule: naming
            # the directory creates nothing, and `runtime_data.STORES` gains no entry.
            "activation": prefs_dir / POLICY_ACTIVATION}


def _journal(paths, kind, **fields):
    paths["dir"].mkdir(parents=True, exist_ok=True)
    with open(paths["journal"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": _now(), "kind": kind, **fields}, sort_keys=True) + "\n")


def read_policy(prefs_dir):
    paths = _prefs_paths(prefs_dir)
    if not paths["policy"].exists():
        return None
    try:
        data = json.loads(paths["policy"].read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def policy_base(prefs_dir):
    """The identity of the policy file a proposal would replace: its content hash, or `none`."""
    paths = _prefs_paths(prefs_dir)
    return _sha(paths["policy"].read_text()) if paths["policy"].exists() else "none"


def build_proposal(envelope, change, by, prefs_dir, task_class=None, bundle_ref=None,
                   manifest_ref=None):
    """A proposal from one run's evidence -> dict, or EvalError when the evidence is not
    defensible: the named variant is absent, below the evidence floor, a single repeat, or the
    run's tasks already backed the policy in force (evaluation tasks stay reserved).

    `bundle_ref` and `manifest_ref` are optional references their own owners computed --
    `decision_policy.bundle_ref` and this module's `manifest_ref`. They are relayed onto the
    record, never recomputed and never dereferenced; both default to None, which is what every
    caller written before D20 passes and what the record then says. Supplying one that is not a
    complete pointer at the contract its slot names refuses the whole proposal, BEFORE any of
    the evidence work below: a malformed input is answered as a malformed input rather than as
    whatever the evidence happens to be.
    """
    refs = policy_refs(bundle_ref=bundle_ref, manifest_ref=manifest_ref)
    if not by:
        raise EvalError("--by is required: a proposal names who made it")
    if not change:
        raise EvalError("--set names nothing to change (workflow=..., policy=...)")
    for key in change:
        if key not in ("workflow", "policy"):
            raise EvalError(f"--set {key}: only workflow= and policy= are routing defaults")
    if "workflow" in change and change["workflow"] not in WORKFLOWS:
        raise EvalError(f"workflow must be one of {', '.join(WORKFLOWS)}")
    if "policy" in change and change["policy"] not in POLICIES:
        raise EvalError(f"policy must be one of {', '.join(POLICIES)}")
    card = build_card(envelope)
    matching = [s for s in card["variants"]
                if all(str(v) == str(_variant_field(envelope, s["variant"], k)) for k, v in change.items())]
    if not matching:
        raise EvalError(f"run {envelope['run_id']} measured no variant with {change}; a default is "
                        f"proposed only from a variant that was run")
    support = matching[0]
    if support["below_floor"]:
        raise EvalError(f"{support['variant']} is below the evidence floor (n={support['n']} < "
                        f"{card['evidence_floor']}); sparse observations never change a default")
    if (envelope.get("repeats") or 1) < 2:
        raise EvalError("a single repeat cannot show stability; repeat the run before proposing")
    current = read_policy(prefs_dir)
    if current:
        overlap = sorted(set(current.get("evidence_tasks") or []) & set((envelope.get("holdout") or {}).get("tasks") or []))
        if overlap:
            raise EvalError(f"{len(overlap)} task(s) in this run already backed the applied policy "
                            f"(v{current.get('version')}); evaluation tasks are reserved from the "
                            f"policy they tuned -- mine a fresh held-out set")
    comparison = [{"variant": s["variant"], "rate": s["rate"], "interval_95": s["interval_95"],
                   "incorrect_acceptance": s["incorrect_acceptance"], "n": s["n"]}
                  for s in card["variants"]]
    pid = f"prop-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{_sha(envelope['run_id'] + json.dumps(change, sort_keys=True))[:6]}"
    return {
        "v": PROPOSAL_VERSION, "id": pid, "status": "proposed", "proposed_by": by, "proposed_at": _now(),
        "source_run": envelope["run_id"], "repo": envelope.get("repo"), "harness": envelope.get("harness"),
        "change": {"scope": task_class or "defaults", "set": dict(change)},
        "evidence": {"supporting_variant": support["variant"], "n": support["n"], "rate": support["rate"],
                     "interval_95": support["interval_95"], "stability": support["stability"],
                     "incorrect_acceptance": support["incorrect_acceptance"], "comparison": comparison,
                     "ranking": card["ranking"], "labels": card["labels"],
                     "tasks": (envelope.get("holdout") or {}).get("tasks") or []},
        "refs": refs,
        "base": policy_base(prefs_dir), "reviews": [],
    }


def _variant_field(envelope, variant_id, key):
    for v in envelope.get("variants") or []:
        if v["id"] == variant_id:
            return v.get(key)
    return None


def write_proposal(prefs_dir, proposal):
    paths = _prefs_paths(prefs_dir)
    paths["proposals"].mkdir(parents=True, exist_ok=True)
    path = paths["proposals"] / f"{proposal['id']}.json"
    path.write_text(json.dumps(proposal, indent=2) + "\n")
    _journal(paths, "policy.proposed", proposal=proposal["id"], run=proposal["source_run"],
             by=proposal["proposed_by"], change=proposal["change"], refs=_ref_ids(proposal))
    return path


def read_proposal(prefs_dir, proposal_id):
    paths = _prefs_paths(prefs_dir)
    path = paths["proposals"] / f"{proposal_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"no proposal {proposal_id!r} under {paths['proposals']}")
    data = json.loads(path.read_text())
    if data.get("v") != PROPOSAL_VERSION:
        raise EvalError(f"{path} is not a {PROPOSAL_VERSION} proposal")
    return data


def review_proposal(prefs_dir, proposal_id, by, decision, note=""):
    if decision not in ("accept", "reject"):
        raise EvalError("decision must be accept or reject")
    if not by:
        raise EvalError("--by is required: a review names the reviewer")
    paths = _prefs_paths(prefs_dir)
    proposal = read_proposal(prefs_dir, proposal_id)
    if proposal["status"] == "applied":
        raise EvalError(f"proposal {proposal_id} was already applied; propose again to change it")
    # `authority` says what this review IS, so a later reader is not left to infer one from the
    # presence of a name. The check behind the field is exactly the `if not by` above.
    entry = {"by": by, "decision": decision, "note": _rd().redact(note or "")["text"],
             "at": _now(), "authority": REVIEW_AUTHORITY}
    proposal["reviews"].append(entry)
    proposal["status"] = "accepted" if decision == "accept" else "rejected"
    (paths["proposals"] / f"{proposal_id}.json").write_text(json.dumps(proposal, indent=2) + "\n")
    _journal(paths, "policy.reviewed", proposal=proposal_id, by=by, decision=decision)
    return proposal


def apply_proposal(prefs_dir, proposal_id):
    """Write the next policy version from an accepted, current proposal; keep the old one."""
    paths = _prefs_paths(prefs_dir)
    proposal = read_proposal(prefs_dir, proposal_id)
    if proposal["status"] == "applied":
        raise EvalError(f"proposal {proposal_id} was already applied")
    if not proposal["reviews"] or proposal["reviews"][-1]["decision"] != "accept":
        raise EvalError(f"proposal {proposal_id} has no accepting review; `review --decision accept` "
                        f"is the evidence review this apply requires")
    if policy_base(prefs_dir) != proposal["base"]:
        raise EvalError(f"proposal {proposal_id} was made against a different policy version than the "
                        f"one in force; re-propose from the current file")
    # Re-validated on the way through, not copied: a proposal file edited after review is not
    # laundered into the applied policy, where the block would carry the applied policy's
    # authority. A pre-D20 proposal has no block and becomes an all-unknown one. Refused here,
    # before anything is written.
    refs = _relay_refs(proposal, f"proposal {proposal_id}")
    current = read_policy(prefs_dir)
    version = (current.get("version") or 0) + 1 if current else 1
    scope = proposal["change"]["scope"]
    new = {"v": POLICY_VERSION, "version": version, "applied_at": _now(), "proposal": proposal_id,
           "source_runs": sorted(set((current or {}).get("source_runs") or []) | {proposal["source_run"]}),
           "evidence_tasks": sorted(set((current or {}).get("evidence_tasks") or [])
                                    | set(proposal["evidence"]["tasks"])),
           "defaults": dict((current or {}).get("defaults") or {}),
           "by_task_class": dict((current or {}).get("by_task_class") or {}),
           "consumption": "pull-only: no driver reads this file until wired on purpose",
           "refs": refs,
           "labels": list(proposal["evidence"]["labels"]) + [REVIEW_AUTHORITY_LABEL]}
    if scope == "defaults":
        new["defaults"].update(proposal["change"]["set"])
    else:
        new["by_task_class"].setdefault(scope, {}).update(proposal["change"]["set"])
    paths["history"].mkdir(parents=True, exist_ok=True)
    if current is not None:
        (paths["history"] / f"v{current.get('version', 0)}.json").write_text(
            paths["policy"].read_text())
    tmp = paths["policy"].with_name(paths["policy"].name + ".tmp")
    tmp.write_text(json.dumps(new, indent=2) + "\n")
    tmp.replace(paths["policy"])
    proposal["status"] = "applied"
    proposal["applied_version"] = version
    (paths["proposals"] / f"{proposal_id}.json").write_text(json.dumps(proposal, indent=2) + "\n")
    _journal(paths, "policy.applied", proposal=proposal_id, version=version,
             previous=(current or {}).get("version"), refs=_ref_ids(new))
    return new, current


def rollback_policy(prefs_dir, to_version=None):
    """Restore an earlier version's bytes; the version rolled back from is kept in history."""
    paths = _prefs_paths(prefs_dir)
    current = read_policy(prefs_dir)
    if current is None:
        raise EvalError("no routing policy is in force; nothing to roll back")
    versions = sorted(int(p.stem[1:]) for p in paths["history"].glob("v*.json")) if paths["history"].is_dir() else []
    if not versions:
        raise EvalError("no earlier version is recorded; nothing to roll back to")
    target = to_version if to_version is not None else versions[-1]
    if target not in versions:
        raise EvalError(f"version {target} is not in history ({', '.join(f'v{v}' for v in versions)})")
    restored_text = (paths["history"] / f"v{target}.json").read_text()
    (paths["history"] / f"v{current.get('version', 0)}.json").write_text(paths["policy"].read_text())
    tmp = paths["policy"].with_name(paths["policy"].name + ".tmp")
    tmp.write_text(restored_text)
    tmp.replace(paths["policy"])
    restored = json.loads(restored_text)
    # Both ends' references are recorded, because which bundle and manifest a rollback moved the
    # runtime BACK to is the part of it a later reader cannot reconstruct from the versions.
    _journal(paths, "policy.rolled-back", from_version=current.get("version"), to_version=target,
             from_refs=_ref_ids(current), to_refs=_ref_ids(restored))
    return restored, current


def policy_report(prefs_dir):
    paths = _prefs_paths(prefs_dir)
    current = read_policy(prefs_dir)
    versions = sorted(int(p.stem[1:]) for p in paths["history"].glob("v*.json")) if paths["history"].is_dir() else []
    proposals = []
    if paths["proposals"].is_dir():
        for p in sorted(paths["proposals"].glob("*.json")):
            try:
                d = json.loads(p.read_text())
                reviews = [r for r in (d.get("reviews") or []) if isinstance(r, dict)]
                # Every proposal on disk is listed whatever its status, so a REJECTED candidate
                # stays as inspectable as an applied one, with the decisions it collected. The
                # names behind those decisions stay in the file; this projection carries the
                # verdicts, which is what a reader of the report is asking about.
                proposals.append({"id": d.get("id"), "status": d.get("status"), "run": d.get("source_run"),
                                  "change": d.get("change"), "refs": read_policy_refs(d),
                                  "decisions": [r.get("decision") for r in reviews]})
            except (OSError, ValueError):
                proposals.append({"id": p.stem, "status": "unreadable"})
    return {"policy": current, "history_versions": versions, "proposals": proposals,
            "path": str(paths["policy"]), "consumption": "pull-only",
            "refs": read_policy_refs(current), "review_authority": REVIEW_AUTHORITY_LABEL}


# =================================================================================================
# BOUNDED CANDIDATE DRAFTS: WHAT THIS EVALUATOR ADMITS (decision-improvement D21)
# =================================================================================================
#
# D11 owns what a candidate proposal IS -- `decision_contract.parse_proposal` refuses an
# executable field, a key outside the data allowlist and a value of the wrong kind. It stops
# deliberately short of one thing, and says so where the allowlist is defined: "the VALUES a
# label parameter may take are the owning surface's vocabulary, not this contract's". This
# section is that surface. `routing.default_workflow` names a workflow only THIS module runs,
# and `routing.default_policy` a policy only this module routes, so whether a proposed value
# names anything at all is a question that can only be answered here.
#
# FIVE REFUSALS, EACH REACHABLE ON ITS OWN. `DRAFT_REFUSALS` is the whole vocabulary, and the
# order they are checked in is fixed so that a candidate refused for one of them has SATISFIED
# the ones before it. A guard that can only ever fire while another is already firing has never
# been shown to do anything, so the tests assert the refusal SET of a batch rather than that
# some refusal happened.
#
# WHY THIS RETURNS VERDICTS INSTEAD OF RAISING. `_policy_ref` raises, because a malformed
# reference on the way into a stored record is a write that must not happen. A draft batch is
# the opposite case: refusing by exception would abandon the other candidates and, worse, throw
# away the record of WHAT was refused and why -- and a rejected candidate staying inspectable is
# exactly what this task's acceptance asks for. So every candidate, admitted or refused,
# examined or never reached, comes back with its payload as it was given. The raising half of
# the pair is still here and is deliberately separate: `draft_budget`, `label_vocabulary`,
# `workflow_stages`, `draft_partitions` and `baseline_workflow` raise, because each of them is
# answering a question about the CALLER's setup rather than about a candidate.
#
# WHAT IS NOT HERE. No writer. Nothing in this section opens, creates or appends to anything:
# the proposal files, the preference file, its history and its journal are the D20 section's,
# and a draft is a thing a caller looks at before it ever becomes one of those. No dispatcher
# either -- there is no inference in a bounded draft, and `bin/improvement_loop.py`, the one
# caller, has no runner parameter to be handed one through.

#: Why a bounded draft is refused. Five codes, one concern each:
#:
#:   code       not a data change this surface can make -- an executable or authority field, a
#:              key outside the allowlist, a value of the wrong kind, or a label naming
#:              something this evaluator does not run
#:   assurance  the change would remove a check the run currently carries. Candidate data may
#:              not edit mandatory review; that is a person's decision, made elsewhere
#:   hidden     the candidate reaches for evaluation material or labels a proposer must be
#:              blind to -- the final audit partition, or an answer-key marker in its own text
#:   duplicate  the same change to the same parent has already been drafted; wording it
#:              differently does not make it a second proposal
#:   budget     the batch's candidate ceiling or its effort ceiling was reached
DRAFT_REFUSALS = ("code", "assurance", "hidden", "duplicate", "budget")

#: What a batch as a whole did. `no-candidate` is a SUCCESSFUL outcome and the plan says so: "no
#: applicable context is a legitimate abstention". It is kept distinct from `all-rejected`
#: because "the search found nothing to propose" and "everything proposed was refused" are
#: different facts about a run, and collapsing them would let an empty search read as a clean
#: review -- or as a failure, which it also is not.
DRAFT_OUTCOMES = ("candidates", "all-rejected", "no-candidate")

#: What one unit of proposal effort IS. Stated because the word "effort" means a model's
#: reasoning dial elsewhere in this repository and a price in others, and it means neither here.
DRAFT_EFFORT_UNIT = (
    "examined-candidate: one candidate looked at, whether it was admitted or refused. This is a "
    "COUNT of work items and never a price, a token count, a duration or a model effort level; "
    "nothing in this section reads a pricing file, a clock or a usage record")

#: How many values the bounded search may look at per data dial before the batch stops. Three is
#: a policy choice, not a measurement: it is enough for a boolean's flip, a count's two
#: neighbours, or two alternative labels, and small enough that an unbounded generator is
#: stopped rather than merely noticed.
DRAFT_EFFORT_PER_DIAL = 3

DRAFT_AUDIT_BLIND_LABEL = (
    "a proposer is audit-blind: the single-use audit partition is the final held-out evidence "
    "and any exposure at all spends it, so a candidate never nominates it for its own "
    "evaluation. Which partition the final audit reads, and when, is the controller's decision "
    "and is outside candidate authority")

DRAFT_NOT_A_PROPOSAL_LABEL = (
    "a valid draft is a candidate that this evaluator would ACCEPT FOR REVIEW; it is not an "
    "approval, not an evaluation result, and not evidence that the change is an improvement. "
    "Nothing here ran anything, compared anything or asked anybody")


def draft_partitions():
    """Which partitions a candidate may nominate for its own evaluation -- DERIVED, not listed.

    Held out, so the result means something, and not single-use, so nominating it does not spend
    the final audit. Both facts come from `PARTITION_ROLES`, this module's own table, at call
    time: a partition that changed role would move this set with it rather than leaving a
    literal here to go quietly stale.
    """
    return tuple(name for name in PARTITIONS
                 if (PARTITION_ROLES[name].get("held_out")
                     and not PARTITION_ROLES[name].get("single_use")))


def label_vocabulary(parameter):
    """The values this evaluator's surface allows for one `label` data parameter.

    Read from this module's own tuples, which are the vocabularies a run is actually routed by.
    A label dial the contract grows without a vocabulary here raises, and `validate_draft` turns
    that into a refusal rather than a pass: a value this module cannot judge is not a value this
    module has judged.

    A workflow's vocabulary is `WORKFLOWS` INTERSECTED with the workflows there is a stage list
    for. That is not belt-and-braces: `WORKFLOW_STAGES` is what the assurance check reads, so a
    name this module could route by but has no stages for is a name whose assurance consequence
    cannot be worked out, and admitting it would be admitting an unexamined one.
    """
    if parameter == "routing.default_workflow":
        return tuple(name for name in WORKFLOWS if name in WORKFLOW_STAGES)
    if parameter == "routing.default_policy":
        return POLICIES
    raise EvalError(
        f"{parameter!r} is a label parameter this evaluator owns no vocabulary for; the ones it "
        f"routes by are routing.default_workflow and routing.default_policy")


def workflow_stages(workflow):
    """The stages one workflow runs, from `WORKFLOW_STAGES`, or `EvalError` for a name that
    names nothing. `check` and `project` dispatch nothing and are stages all the same: what
    matters to the assurance question is which steps happen, not which of them cost money."""
    stages = WORKFLOW_STAGES.get(workflow)
    if stages is None:
        raise EvalError(f"{workflow!r} is not a workflow this evaluator runs; they are "
                        f"{', '.join(WORKFLOWS)}")
    return tuple(stages)


def baseline_workflow(in_force):
    """Which workflow is in force now: the parent bundle's value, else the task contract's own
    default, read from `kit_contract` at call time.

    The fallback is the part that matters. Without it a bundle that simply never set the dial
    would give the assurance check nothing to compare against, and the first candidate to set
    it could set it to the workflow that runs no review -- a reduction that looked like an
    addition because nobody had written the current value down. `kit_contract.DEFAULT_WORKFLOW`
    is where that value actually lives.

    RAISES when the task contract's default is not a workflow this evaluator runs. The two
    vocabularies overlap but are not the same, and guessing a correspondence between them would
    be inventing the very baseline this function exists to establish.
    """
    value = in_force.get("routing.default_workflow")
    if value is not None:
        workflow_stages(value)       # raises if the bundle's own value names nothing
        return value
    default = _kc().DEFAULT_WORKFLOW
    if default not in WORKFLOWS:
        raise EvalError(
            f"the task contract's default workflow is {default!r}, which is not one this "
            f"evaluator runs ({', '.join(WORKFLOWS)}); with no value in the bundle either there "
            f"is no in-force workflow to compare a proposed one against, and this refuses to "
            f"decide rather than guess which of its own workflows that name corresponds to")
    return default


def draft_ceiling():
    """The most a draft batch may admit and examine, derived from the allowlist itself.

    A bounded batch never admits more candidates than there are data dials to turn -- two
    candidates changing the same dial compete, they do not accumulate -- and never examines more
    than `DRAFT_EFFORT_PER_DIAL` values per dial. `decision_contract.DIFF_PARAMETERS` is read at
    call time, so a dial added or removed moves both ceilings and there is no number here to
    drift away from the allowlist it is supposed to bound.
    """
    dials = len(_dc().DIFF_PARAMETERS)
    return {"candidates": dials, "effort": DRAFT_EFFORT_PER_DIAL * dials,
            "effort_unit": DRAFT_EFFORT_UNIT}


def draft_budget(*, max_candidates=None, max_effort=None):
    """The bounds one batch runs under. A caller may lower them; a caller may never raise them.

    RAISES on a request above the ceiling, and that direction is the whole point: a bound a
    caller can widen on request is not a bound, and "candidate data cannot change permission or
    budget policy" is not enforced by a ceiling that asks politely. Absent means the ceiling.
    """
    ceiling = draft_ceiling()
    out = {}
    for key, requested in (("candidates", max_candidates), ("effort", max_effort)):
        limit = ceiling[key]
        if requested is None:
            out[key] = limit
            continue
        if isinstance(requested, bool) or not isinstance(requested, int):
            raise EvalError(f"the {key} bound must be a whole number, not "
                            f"{type(requested).__name__}")
        if requested < 0:
            raise EvalError(f"the {key} bound is {requested}; a negative bound bounds nothing")
        if requested > limit:
            raise EvalError(
                f"the {key} bound was asked to be {requested}, above this evaluator's ceiling of "
                f"{limit}; a batch may run under a smaller bound than the ceiling and never "
                f"under a larger one")
        out[key] = requested
    out["ceiling"] = {"candidates": ceiling["candidates"], "effort": ceiling["effort"]}
    out["effort_unit"] = DRAFT_EFFORT_UNIT
    return out


def _draft_in_force(in_force):
    """The parameters currently in force, checked against the one allowlist. Raises: this is the
    caller's own statement about its bundle, not a candidate's claim about anything."""
    if not isinstance(in_force, dict):
        raise EvalError(f"the in-force parameters must be a mapping, not "
                        f"{type(in_force).__name__}; pass {{}} to say the parent bundle sets "
                        f"none, which is a different statement from not knowing")
    dials = _dc().DIFF_PARAMETERS
    unknown = sorted(set(in_force) - set(dials))
    if unknown:
        raise EvalError(f"the in-force parameters name {', '.join(repr(u) for u in unknown)}, "
                        f"which the data allowlist does not carry")
    return dict(in_force)


def draft_key(candidate):
    """What makes two drafts the SAME draft: the parent they change and the change they make.

    Not the id, which a generator picks, and not the digest of the whole payload, which a
    reworded hypothesis moves. Two candidates proposing the identical change to the identical
    parent are one proposal however differently they argue for it, and counting them twice would
    make a batch's candidate count mean nothing.
    """
    return _sha(_canonical({"parent": candidate.parent["id"], "diff": dict(candidate.diff)}))


def _draft_vocabulary(candidate):
    """A `code`-class detail for a label value this surface does not run, else None."""
    dials = _dc().DIFF_PARAMETERS
    for key in sorted(candidate.diff):
        if dials.get(key) != "label":
            continue
        try:
            allowed = label_vocabulary(key)
        except EvalError as exc:
            return (f"{exc} -- a value this evaluator cannot judge has not been judged, so the "
                    f"draft is refused rather than admitted on the allowlist's word alone")
        value = candidate.diff[key]
        if value not in allowed:
            return (f"{key} is set to {value!r}, which names nothing this evaluator runs; its "
                    f"values are {', '.join(allowed)}")
    return None


def _draft_hidden(candidate):
    """A `hidden`-class detail, else None."""
    allowed = draft_partitions()
    partition = candidate.evaluation["partition"]
    if partition not in allowed:
        role = PARTITION_ROLES.get(partition) or {}
        return (f"the candidate nominates the {partition!r} partition for its own evaluation "
                f"({role.get('note', 'no role recorded')}); a candidate may nominate "
                f"{', '.join(allowed) or 'no partition at all, as this manifest is arranged'}. "
                f"{DRAFT_AUDIT_BLIND_LABEL}")
    for field in ("hypothesis", "falsification", "tradeoff"):
        text = (getattr(candidate, field) or "").upper()
        hits = sorted(m for m in HIDDEN_LABEL_MARKERS if m in text)
        if hits:
            return (f"the candidate's {field} carries {len(hits)} hidden-label marker(s) of "
                    f"kind {', '.join(repr(h) for h in hits)}; those appear beside an answer, "
                    f"and a proposer quoting one is reading material it is blind to by design")
    return None


def _draft_assurance(candidate, in_force):
    """An `assurance`-class detail, else None.

    The one dial with an assurance consequence is the default workflow, because a workflow IS a
    set of steps: `WORKFLOW_STAGES` says which ones each runs, and a proposal that drops one is
    a proposal to stop doing it. `routing.default_policy` chooses which model a stage runs
    under and adds or removes no step, so it is not checked here and this says so rather than
    leaving a reader to wonder which dials were considered.
    """
    proposed = candidate.diff.get("routing.default_workflow")
    if proposed is None:
        return None
    current = baseline_workflow(in_force)
    if proposed == current:
        return None
    dropped = sorted(set(workflow_stages(current)) - set(workflow_stages(proposed)))
    if not dropped:
        return None
    detail = (f"moving the default workflow from {current!r} to {proposed!r} drops the "
              f"{', '.join(repr(d) for d in dropped)} stage(s) it currently runs")
    if "review" in dropped:
        detail += (f"; the review stage is the independent review the workflow in force exists "
                   f"to run, and a mandatory review is not a dial a data candidate turns -- "
                   f"removing a check is a person's decision, made elsewhere")
    return (f"{detail}. A candidate may raise the assurance a run carries and may never lower "
            f"it.")


def _draft_verdict(payload, *, verdict, reason=None, detail="", identity=None, key=None,
                   examined=True):
    """One row of a batch report. The payload is carried back EXACTLY as it was handed in --
    including a refused one, which is what keeps a rejected candidate inspectable."""
    return {"id": identity, "key": key, "verdict": verdict, "reason": reason, "detail": detail,
            "examined": examined, "payload": payload}


def validate_draft(payload, *, in_force, known=()):
    """One bounded draft -> a verdict. Never raises over the candidate; see the section note.

    `in_force` is the parent bundle's own parameters, as the caller read them; `known` is the
    draft keys already drafted, so a search run twice does not re-propose what it proposed
    before. Budget is deliberately NOT here: a ceiling is a property of a batch, and a single
    draft cannot know how much of one has been spent.
    """
    forced = _draft_in_force(in_force)
    identity = payload.get("id") if isinstance(payload, dict) else None
    contract = _dc()
    try:
        candidate = contract.parse_proposal(payload)
    except contract.ContractError as exc:
        return _draft_verdict(
            payload, verdict="refused", reason="code", identity=identity,
            detail=f"the data allowlist refused this draft: {exc}")
    identity = candidate.id
    key = draft_key(candidate)
    # Checked IN ORDER and one at a time, so that a candidate refused by a later guard has
    # satisfied every earlier one -- and so that a guard whose input the previous guard would
    # have rejected is never run on it. Building these as a tuple would evaluate all three
    # eagerly, and `_draft_assurance` asked about a workflow `_draft_vocabulary` has just
    # refused would raise about a value that was never going to be admitted.
    for reason, check in (("code", lambda: _draft_vocabulary(candidate)),
                          ("hidden", lambda: _draft_hidden(candidate)),
                          ("assurance", lambda: _draft_assurance(candidate, forced))):
        detail = check()
        if detail:
            return _draft_verdict(payload, verdict="refused", reason=reason, detail=detail,
                                  identity=identity, key=key)
    if key in set(known):
        return _draft_verdict(
            payload, verdict="refused", reason="duplicate", identity=identity, key=key,
            detail=f"the same change to {candidate.parent['id']!r} has already been drafted; a "
                   f"second wording of one proposal is still one proposal")
    return _draft_verdict(payload, verdict="valid", identity=identity, key=key,
                          detail="accepted for review")


def validate_draft_batch(payloads, *, in_force, budget=None, known=()):
    """A whole batch under its bounds -> a report that keeps every candidate it was given.

    The effort ceiling is applied BEFORE anything is parsed, because effort is the cost of
    looking: a batch whose ceiling is spent stops looking, and the candidates it never reached
    are reported as never reached rather than as refused on their merits. The candidate ceiling
    is applied after a draft is found valid, because a refused draft was never admitted and
    admitting nothing consumes none of it.
    """
    bounds = budget if budget is not None else draft_budget()
    for field in ("candidates", "effort"):
        if field not in bounds:
            raise EvalError(f"the budget names no {field} bound; build one with draft_budget()")
    forced = _draft_in_force(in_force)
    drafts = list(payloads or ())
    seen = list(known)
    rows, admitted, examined = [], 0, 0
    for index, payload in enumerate(drafts):
        if examined >= bounds["effort"]:
            rows.append(_draft_verdict(
                payload, verdict="refused", reason="budget", examined=False,
                identity=payload.get("id") if isinstance(payload, dict) else None,
                detail=f"the batch's effort ceiling of {bounds['effort']} examined-candidate(s) "
                       f"was reached before this one (#{index + 1}) was looked at"))
            continue
        examined += 1
        row = validate_draft(payload, in_force=forced, known=seen)
        if row["verdict"] == "valid" and admitted >= bounds["candidates"]:
            row = _draft_verdict(
                payload, verdict="refused", reason="budget", identity=row["id"], key=row["key"],
                detail=f"the batch already admitted its ceiling of {bounds['candidates']} "
                       f"candidate(s); this one is valid and is refused for the ceiling alone")
        if row["verdict"] == "valid":
            admitted += 1
            seen.append(row["key"])
        rows.append(row)
    valid = [r for r in rows if r["verdict"] == "valid"]
    refused = [r for r in rows if r["verdict"] == "refused"]
    if valid:
        outcome = "candidates"
    elif refused:
        outcome = "all-rejected"
    else:
        outcome = "no-candidate"
    return {
        "outcome": outcome,
        "drafts": len(drafts), "examined": examined,
        "admitted": valid, "refused": refused, "candidates": rows,
        "refusals": sorted({r["reason"] for r in refused}),
        # The bounds this batch ran under, beside the ceiling they had to fit inside. Both, so a
        # reader of one report can see that a batch was run under a tighter bound than the
        # module allows without having to go and look the ceiling up.
        "budget": {"candidates": bounds["candidates"], "effort": bounds["effort"],
                   "effort_spent": examined, "ceiling": draft_ceiling(),
                   "effort_unit": DRAFT_EFFORT_UNIT},
        "in_force": dict(forced),
        "labels": [DRAFT_NOT_A_PROPOSAL_LABEL, DRAFT_AUDIT_BLIND_LABEL],
    }

# END OF THE BOUNDED CANDIDATE DRAFT SECTION (decision-improvement D21)


# =================================================================================================
# EXACT APPROVAL: WHAT AN APPROVAL BINDS, AND WHAT BINDING IS NOT (decision-improvement D22)
# =================================================================================================
#
# WHAT THIS SECTION ADDS. D20 gave a proposal a review entry whose `authority` field says
# `name-only`, and said in `REVIEW_AUTHORITY_LABEL` exactly what that is worth: a string the
# command was handed, checked for being non-empty. This section adds the thing that label named
# as missing -- the binding of a decision to the EXACT bytes it was taken over -- and adds
# nothing else. It does not add authority.
#
# THE DISTINCTION THE WHOLE SECTION TURNS ON, stated once here and restated in the record itself
# so a later reader is never left to infer it:
#
#   BINDING GIVES INTEGRITY.   The thing that was evaluated is the thing that was approved, and
#                              a later re-derivation notices any of it moving.
#   BINDING IS NOT AUTHORITY.  `by` is a string. Four correct digests beside it prove that the
#                              content did not move; they prove nothing whatever about who
#                              typed the name, and a record saying it was approved by "alice"
#                              with every hash matching still proves only that somebody typed
#                              "alice".
#   BINDING IS NOT ISOLATION.  `NOT_ENFORCEMENT_LABEL` has said since D06 that a content hash
#                              identifies and DETECTS change and never prevents it. Adding
#                              three more hashes does not make a confinement boundary. Whether
#                              this host enforces one at all is `bin/exec_policy.py`'s question
#                              (D07), and `gate_protected_dispatch` applies no confinement of
#                              its own (D08, D18).
#
# Those three are not prose decoration. The residual is MACHINE-READABLE: every record carries
# `unproven`, whose codes are `APPROVAL_UNPROVEN`, and every binding row carries `re_derived_by`
# naming the function that actually re-derived it -- D18's precedent, for D18's reason, because
# a row that says `satisfied` over evidence nobody consulted is a name broader than its check.
#
# THE FOUR BINDINGS, and which object each one digests. The plan names them
# "candidate/evaluation/partition/source hashes"; this says which thing each of those is, so
# nobody has to guess:
#
#   candidate    the candidate proposal payload, through D11's own parser and D11's own
#                `CandidateProposal.sha()`. Not a digest of the bytes as handed in: a candidate
#                is what the contract makes of it, so the payload is re-parsed and the owner's
#                digest is taken over the owner's normalised form. A re-serialisation that
#                changes nothing then invalidates nothing.
#   evaluation   the immutable evaluation manifest -- `MANIFEST_VERSION`, the content-addressed
#                document `build_manifest` produces, whose digest `manifest_digest` owns and
#                whose internal consistency `verify_manifest` re-derives. This is the
#                "immutable evaluation hash": the material, the grouping and the rules the
#                result was read under.
#   partition    the exact held-out item set inside that manifest that the result was read
#                over. A manifest names four partitions; which one, and which items were in it,
#                is a different fact from which manifest, and an approval that pinned only the
#                manifest would not notice the cohort moving inside it.
#   source       the source run's result envelope -- `EVAL_VERSION`, what this evaluator writes
#                as `results.json`, and what D20's proposal record calls `source_run`. The
#                numbers came from somewhere, and this is the somewhere.
#
# WHAT IS NOT HERE, deliberately. No activation: `canary`, `active`, `retired` and
# `rolled-back` are D23's states and this vocabulary does not contain them, no runtime pointer
# is written, `CONFINED_DISPATCH_WIRED` is untouched and still False, and `promotion_eligibility`
# below cannot return an eligible verdict while it is. No second reviewer vocabulary either:
# `REVIEW_AUTHORITY` is read from D20 at call time rather than copied, so there is one answer in
# this file to "what is an authority field worth here" and not two.
#
# WHY THE GATES ARE EVALUATED EAGERLY, and why that is the opposite of D21's answer. D21's draft
# guards are lazy on purpose: there, a later guard asked about a value an earlier guard had
# already refused would raise about something that was never going to be admitted. Here the
# caller is owed the WHOLE reason an approval did not happen -- stopping at the first refusal
# would let a candidate be fixed one refusal at a time without ever being told it was also out
# of scope -- and each gate is total over the case it is handed: two of them read facts the case
# already derived, and two compare strings and sets. So all four run, every time, and the tests
# assert the refusal SET rather than that some refusal happened.

#: The version of the approval RECORD. A new stored object, so it carries its own version on
#: itself rather than moving `PROPOSAL_VERSION` or `POLICY_VERSION` -- which would make every
#: proposal and preference file written before today unreadable, since `read_proposal` refuses
#: any `v` that is not current. Registered in `release_gate.VERSION_SOURCES`.
APPROVAL_VERSION = "polytropos.policy-approval/1"

#: Where approval records live under the prefs directory the caller names. Beside the proposals,
#: in the same store, written by the same module -- not a new store, and `runtime_data.STORES`
#: gains nothing.
POLICY_APPROVALS = "routing-policy.approvals"

#: The canonical lifecycle, exactly the six names the plan uses. `canary`, `active`, `retired`
#: and `rolled-back` are deliberately ABSENT: runtime activation is a separately gated
#: transition, and putting its states in this vocabulary would let something here look like a
#: step towards running.
APPROVAL_STATES = ("draft", "offline-valid", "evaluated", "approved", "rejected",
                   "insufficient-evidence")

#: Which state may follow which. Three of them are terminal FOR THE RECORD that reached them: a
#: candidate whose evidence was too thin is not forbidden from ever being evaluated again, it is
#: that THIS approval record ends there. `approved` has no successor here because its only
#: successor is an activation this module does not perform.
APPROVAL_TRANSITIONS = {
    "draft": ("offline-valid", "rejected"),
    "offline-valid": ("evaluated", "rejected"),
    "evaluated": ("approved", "rejected", "insufficient-evidence"),
    "approved": (),
    "rejected": (),
    "insufficient-evidence": (),
}

#: Why an approval asked for is not given. Four codes, one concern each, and every one of them
#: reachable with the other three satisfied:
#:
#:   stale         the evidence handed in is not the evidence the candidate pins -- the manifest
#:                 no longer hashes to the id it is filed under, its digest is not the one the
#:                 candidate's own `evaluation.manifest_ref` names, or the partition being
#:                 approved over is not the one the candidate nominated
#:   partial       the evaluation did not cover the partition it claims: some member of that
#:                 partition has no result in the run. Evidence too thin to score, which is a
#:                 STATE (`insufficient-evidence`) and not a verdict against the candidate
#:   self-approval the name approving is the name that proposed. A proposer does not approve
#:                 itself -- and see `SELF_APPROVAL_NOTE` for what that check is and is not
#:   scope         the scope the approver stated does not cover the scope the candidate claims;
#:                 an approval for one project or task class is not an approval for another
APPROVAL_REFUSALS = ("stale", "partial", "self-approval", "scope")

#: The four bound hashes, in the order a record lists them. See the section note for which
#: object each one digests and which function re-derives it.
APPROVAL_BINDINGS = ("candidate", "evaluation", "partition", "source")

#: What binding a hash DOES establish. One value, because there is only one: the content is the
#: content. Written as a code rather than a sentence so a reader can machine-check that no row
#: ever claims more than this.
BINDING_ESTABLISHES = "content-identity"

#: What no record written here establishes, whatever its state and however many of its bindings
#: re-derive. Machine-readable, closed, and UNCONDITIONAL: nothing in this section can discharge
#: any of them, so none is ever left off a record on the strength of some other check passing.
APPROVAL_UNPROVEN = ("actor-not-authenticated", "isolation-not-demonstrated",
                     "origin-not-dereferenced")

APPROVAL_UNPROVEN_NOTES = {
    "actor-not-authenticated":
        "the approving and proposing names are strings this command was handed, checked for "
        "being non-empty and for differing from each other. There is no controller identity, no "
        "signature and no session behind either of them, so an approval binds WHAT was approved "
        "exactly and WHO approved it not at all",
    "isolation-not-demonstrated":
        "binding four digests is integrity, never confinement. Nothing here ran under a "
        "boundary, observed one, or asked for one; whether this host enforces one is "
        "exec_policy's question and is answered separately",
    "origin-not-dereferenced":
        "the manifest, the envelope and the candidate are documents this function was handed. "
        "It re-derives their digests, so it can say they are internally consistent and that "
        "they have not moved since; it cannot say they came out of the store they name, because "
        "the library entry point opens nothing",
}

BINDING_NOT_AUTHORITY_LABEL = (
    "binding an approval to exact hashes gives INTEGRITY and not AUTHORITY: it establishes that "
    "the candidate, manifest, partition and run bound here are the ones the decision was taken "
    "over, and that any of them moving afterwards is detectable. It establishes nothing about "
    "who took the decision. A JSON actor string is not authentication and a content hash is not "
    "an identity; authority would have to be protected at the execution boundary, which this "
    "module does not provide and does not claim")

SELF_APPROVAL_NOTE = (
    "a proposer may not approve its own candidate. What enforces that here is a comparison of "
    "two caller-supplied names, which catches the honest case and stops nobody who types a "
    "second name -- the proposer is not authenticated either. The structural half of the rule "
    "is elsewhere and is real: a candidate payload cannot carry an authority field at all "
    "(decision_contract.BANNED_FIELDS), so the name approving can never come out of the thing "
    "being approved")

APPROVAL_NOT_ACTIVATION_LABEL = (
    "an approval is not an activation. Nothing here writes a runtime pointer, selects a bundle, "
    "starts a run or makes anything runnable; the canary/active transition is separately gated "
    "and is not in this lifecycle's vocabulary. An approved record is a precondition somebody "
    "else must still check, never a permission")


# ---- the four bindings: each digest re-derived by the owner of the thing it digests ------------

def candidate_digest(payload):
    """The exact candidate hash -> `(CandidateProposal, sha)`, through D11 and nothing else.

    The digest is `CandidateProposal.sha()` over the contract's own normalised payload, NOT a
    hash of the bytes as handed in. Two spellings of one candidate -- a reordered mapping, a
    different indentation -- are one candidate, and an approval bound to the formatting rather
    than to the proposal would be invalidated by a re-serialisation that changed nothing.

    RAISES when the contract refuses the payload, because that is the caller's setup being wrong
    rather than a candidate being refused: there is nothing to bind an approval to.
    """
    contract = _dc()
    try:
        parsed = contract.parse_proposal(payload)
    except contract.ContractError as exc:
        raise EvalError(f"the candidate is not one {contract.CANDIDATE_VERSION} describes, so "
                        f"there is nothing to bind an approval to: {exc}") from None
    return parsed, parsed.sha()


def envelope_digest(envelope):
    """The source run's hash: the digest of the whole result envelope this evaluator wrote.

    Over the WHOLE envelope and not over a summary of it: the trials, the variants, the spend
    and the labels are all part of what was evaluated, and an approval bound to a summary would
    not notice a trial's verdict being edited underneath it.
    """
    if not isinstance(envelope, dict):
        raise EvalError(f"the evaluation run must be a {EVAL_VERSION} envelope, not a "
                        f"{type(envelope).__name__}")
    if envelope.get("v") != EVAL_VERSION:
        raise EvalError(f"the evaluation run is a {envelope.get('v')!r} document; an approval "
                        f"binds a {EVAL_VERSION} result envelope")
    return _sha(_canonical(envelope))


def _manifest_content(manifest):
    """One manifest document's immutable content, or `EvalError`. Never a `{}` stand-in: an
    absent manifest digesting to the digest of nothing would give every approval taken without
    one the same `evaluation` hash, which is a collision this module would have manufactured."""
    if not isinstance(manifest, dict) or not isinstance(manifest.get("content"), dict):
        raise EvalError(f"the evaluation manifest must be a {MANIFEST_VERSION} document with a "
                        f"content block, not a {type(manifest).__name__}")
    return manifest["content"]


def partition_digest(manifest, partition):
    """The hash of the exact held-out item set the result was read over.

    Over the partition NAME and its members, and deliberately not over the manifest id: which
    manifest is the `evaluation` binding's job, and keeping the two separable is what lets a
    later check say which of the two moved. `PARTITIONS` is read from this module's own table
    rather than listed again here.
    """
    if partition not in PARTITIONS:
        raise EvalError(f"unknown partition {partition!r}; the four are {', '.join(PARTITIONS)}")
    members = sorted(_manifest_content(manifest).get("partitions", {}).get(partition) or [])
    return _sha(_canonical({"partition": partition, "items": members}))


def _binding_derivations(*, candidate, manifest, partition, envelope=None):
    """`{slot: (callable, re_derived_by, over)}` -- ONE place each binding is derived.

    `approval_bindings` calls every entry and RAISES on a bad document, because a record built
    over evidence this module could not read is a write that must not happen.
    `approval_holds` calls the same entries one at a time and DEGRADES, because a later reader
    asking "does this still hold" must be told which slot failed rather than losing all four to
    the first exception. Two jobs, deliberately not one function, over one derivation.
    """
    return {
        "candidate": (lambda: candidate_digest(candidate)[1],
                      "decision_contract.parse_proposal(...).sha()",
                      "the candidate proposal, normalised by the contract that owns its shape"),
        "evaluation": (lambda: manifest_digest(_manifest_content(manifest)),
                       "workflow_eval.manifest_digest",
                       f"the immutable {MANIFEST_VERSION} manifest's content"),
        "partition": (lambda: partition_digest(manifest, partition),
                      "workflow_eval.partition_digest",
                      f"the {partition!r} partition's exact membership inside that manifest"),
        "source": (lambda: None if envelope is None else envelope_digest(envelope),
                   "workflow_eval.envelope_digest",
                   f"the source run's {EVAL_VERSION} result envelope"),
    }


def approval_bindings(*, candidate, manifest, partition, envelope=None):
    """The four hashes an approval binds -> `{slot: row}`, every slot present.

    `establishes` carries the same code on every row on purpose. A hash establishes content
    identity and that is the whole of it; a row claiming more would be the defect this section
    exists to avoid. `does_not_establish` carries the residual codes, so the limit travels on
    the row rather than only in a paragraph somewhere.

    An absent evaluation run leaves the `source` hash null WITH its reason -- never absent, and
    never back-filled from one of the other three: "no result was supplied" and "a result was
    supplied and it hashes to this" are different facts and the record keeps them different.
    """
    out = {}
    for slot in APPROVAL_BINDINGS:
        derive, re_derived_by, over = _binding_derivations(
            candidate=candidate, manifest=manifest, partition=partition, envelope=envelope)[slot]
        digest = derive()
        out[slot] = {"slot": slot, "hash": digest, "re_derived_by": re_derived_by, "over": over,
                     "establishes": None if digest is None else BINDING_ESTABLISHES,
                     "does_not_establish": list(APPROVAL_UNPROVEN),
                     "reason": None if digest is not None else "no evaluation run was supplied"}
    return out


def approval_holds(record, *, candidate, manifest, partition, envelope=None):
    """Do the objects in hand still re-derive to what this approval bound? The central property.

    Every slot is re-derived from scratch by the same function that derived it in the first
    place and compared to the stored hash. A slot that RAISES on re-derivation -- a candidate
    the contract now refuses, an envelope of the wrong version -- counts as moved with its
    reason, never as unchanged: a binding that cannot be re-derived has not been shown to hold.
    A slot that was never bound counts as moved for the same reason.

    A reader, so it reports instead of raising. `holds` is False as soon as one slot moved, and
    `moved` names which -- "the approval no longer holds" and "the manifest was rewritten" are
    different amounts of information and a caller is owed the second.
    """
    stored = (record or {}).get("bindings") or {}
    derivations = _binding_derivations(candidate=candidate, manifest=manifest,
                                       partition=partition, envelope=envelope)
    rows, moved = [], []
    for slot in APPROVAL_BINDINGS:
        bound = (stored.get(slot) or {}).get("hash")
        derive, re_derived_by, _over = derivations[slot]
        try:
            fresh, reason = derive(), None
        except (EvalError, AttributeError, TypeError, KeyError, ValueError) as exc:
            fresh, reason = None, f"the {slot} binding could not be re-derived: {exc}"
        if reason is None and bound is None:
            reason = f"nothing was ever bound in the {slot} slot, so nothing about it holds"
        matches = reason is None and fresh == bound
        if not matches:
            moved.append(slot)
        rows.append({"slot": slot, "bound": bound, "re_derived": fresh, "matches": matches,
                     "reason": reason, "re_derived_by": re_derived_by})
    return {"holds": not moved, "moved": moved, "rows": rows,
            "unproven": list(APPROVAL_UNPROVEN),
            "labels": [BINDING_NOT_AUTHORITY_LABEL, NOT_ENFORCEMENT_LABEL]}


# ---- the facts a decision is taken over --------------------------------------------------------

def evidence_coverage(manifest, partition, envelope):
    """Did the run actually evaluate the partition it claims? Derived, never asserted.

    The members are the manifest's own, the task each item names is the manifest's own, and what
    was evaluated is the set of tasks the envelope has TRIALS for -- results, not the declared
    holdout list, because a task that was declared and never run was not evaluated. An empty
    partition is incomplete rather than vacuously complete: nothing was covered because there
    was nothing there, and reading that as full coverage is how an empty cohort becomes evidence.
    """
    content = _manifest_content(manifest)
    if partition not in PARTITIONS:
        raise EvalError(f"unknown partition {partition!r}; the four are {', '.join(PARTITIONS)}")
    members = sorted(content.get("partitions", {}).get(partition) or [])
    items = content.get("items") or {}
    wanted = {iid: (items.get(iid) or {}).get("task_id") for iid in members}
    evaluated = {trial.get("task_id") for trial in (envelope or {}).get("trials") or []}
    missing = sorted(iid for iid, task in wanted.items() if task not in evaluated)
    run = (envelope or {}).get("run_id")
    if not members:
        detail = f"the {partition} partition is empty, so nothing in it was covered"
    elif missing:
        detail = (f"{len(missing)} of {len(members)} item(s) in the {partition} partition have "
                  f"no result in run {run!r}")
    else:
        detail = ""
    return {"partition": partition, "members": len(members), "covered": len(members) - len(missing),
            "missing": missing, "complete": bool(members) and not missing, "run": run,
            "detail": detail}


def _stale_findings(parsed, manifest, partition):
    """Every way the evidence in hand is not the evidence the candidate pinned.

    Three of them, each derived: the manifest document no longer hashes to the id it is filed
    under (`verify_manifest`'s own `digest` finding, not a second implementation of it); its
    digest is not the one the candidate's `evaluation.manifest_ref` pins; and the partition being
    approved over is not the one the candidate nominated. All three are collected -- a candidate
    can be stale in more than one way and a reader is told all of them.
    """
    out = []
    for finding in verify_manifest(manifest):
        if finding.get("kind") in ("digest", "version"):
            out.append(f"the manifest is not the document it claims to be "
                       f"({finding['kind']}: {finding['detail']})")
    pinned = dict(parsed.evaluation["manifest_ref"])
    actual = manifest_digest(_manifest_content(manifest))
    if pinned.get("sha") != actual:
        out.append(f"the candidate pins manifest {pinned.get('id')!r} at "
                   f"{str(pinned.get('sha'))[:16]}..., and the manifest supplied digests to "
                   f"{actual[:16]}...; the evidence moved after the candidate was written")
    if parsed.evaluation["partition"] != partition:
        out.append(f"the candidate nominates the {parsed.evaluation['partition']!r} partition "
                   f"and this approval is being taken over {partition!r}")
    return out


def _scope_findings(approval_scope, candidate_scope):
    """Does the stated scope COVER the candidate's? The keys come from the parsed candidate.

    No list of scope field names is written here: `candidate_scope` is what
    `decision_contract.parse_proposal` produced, so the keys compared are the contract's own and
    there is nothing in this file to drift from them. The project must match exactly -- a project
    is not a set -- and each collection must be a superset: approving a candidate for more task
    classes than it claims is fine, approving it for fewer is approving something else.
    """
    keys = sorted(candidate_scope)
    if not isinstance(approval_scope, dict):
        return [f"the approval names no scope; it is an object with {', '.join(keys)}, not a "
                f"{type(approval_scope).__name__}"]
    unknown = sorted(set(approval_scope) - set(keys))
    missing = sorted(set(keys) - set(approval_scope))
    if unknown or missing:
        return ["; ".join(part for part in (
            f"the approval's scope carries unknown key(s) "
            f"{', '.join(repr(k) for k in unknown)}" if unknown else "",
            f"the approval's scope is missing {', '.join(repr(k) for k in missing)}"
            if missing else "") if part)]
    out = []
    for key in keys:
        claimed, granted = candidate_scope[key], approval_scope[key]
        if isinstance(claimed, str):
            if granted != claimed:
                out.append(f"the approval is scoped to {key} {granted!r} and the candidate "
                           f"claims {claimed!r}")
            continue
        covered = set(granted) if isinstance(granted, (list, tuple, set)) else set()
        short = sorted(set(claimed) - covered)
        if short:
            out.append(f"the candidate claims {key} {', '.join(repr(s) for s in short)}, which "
                       f"this approval's scope does not cover")
    return out


def _same_actor(left, right):
    """Two caller-supplied names, compared the way a person reads them. `SELF_APPROVAL_NOTE`
    is the whole of what this can and cannot establish."""
    return str(left or "").strip().casefold() == str(right or "").strip().casefold()


def approval_stage(*, draft_verdict, evaluated):
    """Which pre-decision lifecycle state a candidate is in, derived from two facts.

    `draft_verdict` is `validate_draft`'s own verdict -- D21's, not a second opinion about
    offline validity -- and `None` means nobody has run it, which is what `draft` means. The
    three decision states are not reachable from here: they are what a reviewer's decision
    produces, and deriving one of them from content alone would be deciding without a decider.
    """
    if draft_verdict is None:
        return "draft"
    if draft_verdict.get("verdict") != "valid":
        return "rejected"
    return "evaluated" if evaluated else "offline-valid"


def approval_case(*, candidate, manifest, partition, envelope=None, in_force=None,
                  proposed_by=""):
    """Every fact an approval decision is taken over -- and no decision, no reviewer, no write.

    Deliberately split from `decide_approval`: the facts are derived from the documents by
    functions that could not care less who is asking, and the decision is then taken over those
    facts by somebody who is named. The split is what lets the same case be re-derived later and
    compared, and what keeps a reviewer's name out of every function above.

    `in_force` is the parent bundle's parameters as the caller read them, handed straight to
    D21's `validate_draft`; `None` says nobody has validated this offline yet, which is the
    `draft` state rather than a failure. The documents are kept on the case so a later
    `approval_holds` can re-derive from the very things the bindings were derived from -- they
    are in memory only, and `decide_approval` copies the derived facts onto its record and never
    these.
    """
    parsed, _digest = candidate_digest(candidate)
    verdict = None if in_force is None else validate_draft(candidate, in_force=in_force)
    return {
        "candidate": parsed.id,
        "scope": {key: (value if isinstance(value, str) else list(value))
                  for key, value in dict(parsed.scope).items()},
        "proposed_by": proposed_by,
        "state": approval_stage(draft_verdict=verdict, evaluated=envelope is not None),
        "draft": verdict,
        "bindings": approval_bindings(candidate=candidate, manifest=manifest,
                                      partition=partition, envelope=envelope),
        "coverage": (None if envelope is None
                     else evidence_coverage(manifest, partition, envelope)),
        "stale": _stale_findings(parsed, manifest, partition),
        "manifest": manifest.get("id") if isinstance(manifest, dict) else None,
        "partition": partition,
        "run": (envelope or {}).get("run_id"),
        "documents": {"candidate": candidate, "manifest": manifest, "partition": partition,
                      "envelope": envelope},
    }


# ---- the decision ------------------------------------------------------------------------------

def decide_approval(case, *, by, scope, decision, note="", now=None):
    """One reviewer's decision over one case -> an approval record. Pure; writes nothing.

    RAISES on the caller's own setup being wrong -- an unnamed reviewer, a decision outside the
    vocabulary, or an `accept` asked for from a state the lifecycle cannot reach `approved` from.
    That last one is the transition guard, and the asymmetry in it is deliberate: a candidate may
    be REJECTED from any non-terminal state, because a person is always allowed to say no, and
    may only be APPROVED from `evaluated`, because approving something that was never evaluated
    is the defect this task exists to prevent.

    The four gates then run, all of them, and the refusal SET they produce decides the state:
    nothing refused is `approved`; `partial` alone is `insufficient-evidence`, which means the
    evidence is too thin to score and is a different fact from a verdict against the candidate;
    anything else is `rejected`. A refused record is kept exactly like a granted one -- see
    `write_approval` -- because a refusal nobody can read is a refusal nobody can review.
    """
    if decision not in ("accept", "reject"):
        raise EvalError("decision must be accept or reject")
    if not by:
        raise EvalError("--by is required: an approval names who gave it")
    state = (case or {}).get("state")
    if state not in APPROVAL_STATES:
        raise EvalError(f"{state!r} is not a lifecycle state; they are "
                        f"{', '.join(APPROVAL_STATES)}")
    target = "approved" if decision == "accept" else "rejected"
    reachable = APPROVAL_TRANSITIONS[state]
    if target not in reachable:
        onward = ", ".join(reachable) or "nothing: it is a terminal state"
        raise EvalError(f"a candidate in the {state!r} state cannot become {target!r}; from "
                        f"{state!r} this lifecycle reaches {onward}")
    refusals = []
    if decision == "accept":
        coverage = case.get("coverage") or {}
        # All four, every time -- see the section note on why this is the opposite of D21's
        # lazy guards. Each gate is total over the case it is handed: two read facts the case
        # already derived, two compare a string and a set.
        for reason, detail in (
                ("stale", "; ".join(case.get("stale") or ())),
                ("partial", "" if coverage.get("complete") else
                 (coverage.get("detail")
                  or "no evaluation run was supplied, so nothing was covered")),
                ("self-approval",
                 (f"{by!r} proposed this candidate and cannot also approve it. "
                  f"{SELF_APPROVAL_NOTE}") if _same_actor(by, case.get("proposed_by")) else ""),
                ("scope", "; ".join(_scope_findings(scope, case.get("scope") or {})))):
            if detail:
                refusals.append({"reason": reason, "detail": detail})
    codes = sorted({row["reason"] for row in refusals})
    unknown = sorted(set(codes) - set(APPROVAL_REFUSALS))
    if unknown:  # pragma: no cover -- a closed vocabulary that stopped being closed
        raise EvalError(f"refusal code(s) {unknown} are outside APPROVAL_REFUSALS")
    if decision == "reject":
        final, granted = "rejected", False
    elif not refusals:
        final, granted = "approved", True
    elif codes == ["partial"]:
        final, granted = "insufficient-evidence", False
    else:
        final, granted = "rejected", False
    bound = {slot: ((case.get("bindings") or {}).get(slot) or {}).get("hash")
             for slot in APPROVAL_BINDINGS}
    at = now or _now()
    # Everything that distinguishes two decisions is in the id, the scope included: two
    # decisions that differ only in what they were scoped to are two decisions, and an id blind
    # to that would let the second land on the first's filename.
    identity = _sha(_canonical({"candidate": case.get("candidate"), "by": by, "at": at,
                                "decision": decision, "state": final, "bindings": bound,
                                "scope": scope if isinstance(scope, dict) else None}))
    return {
        "v": APPROVAL_VERSION,
        "id": f"appr-{str(at)[:10]}-{identity[:6]}",
        "state": final,
        "granted": granted,
        "from_state": state,
        "decision": decision,
        "candidate": case.get("candidate"),
        "manifest": case.get("manifest"),
        "partition": case.get("partition"),
        "run": case.get("run"),
        "by": by,
        "proposed_by": case.get("proposed_by"),
        "at": at,
        "scope": _frozen(scope) if isinstance(scope, dict) else None,
        "candidate_scope": _frozen(case.get("scope")),
        # Read from D20 at call time, never copied: there is one answer in this file to what an
        # authority field is worth, and binding four hashes did not change it.
        "authority": REVIEW_AUTHORITY,
        # Deep copies, so a caller that goes on using the case cannot reach into a decision
        # already taken. A record of what was decided is not a live view of the decider.
        "bindings": _frozen(case.get("bindings")),
        "coverage": _frozen(case.get("coverage")),
        "refusals": refusals,
        "unproven": list(APPROVAL_UNPROVEN),
        "note": _rd().redact(note or "")["text"],
        "labels": [BINDING_NOT_AUTHORITY_LABEL, APPROVAL_NOT_ACTIVATION_LABEL,
                   REVIEW_AUTHORITY_LABEL, SELF_APPROVAL_NOTE, NOT_ENFORCEMENT_LABEL],
    }


def promotion_eligibility(record, *, case=None, sentinel_report=None):
    """What an approval does and does not establish towards a PROMOTION -- rows, not a verdict
    dressed up as one. Every row names the function that re-derived it, or `None`.

    Three requirements, and the approval is only one of them. D18 established the shape and the
    reason: a row that says `satisfied` over evidence nobody consulted is a name broader than its
    check. So the exact-approval row is re-derived only when a `case` is supplied to re-derive it
    FROM and says so when there is not; the profile row is `exec_policy.certify_profile`'s verdict
    through this module's own `_certification_evidence`, never a word the caller chose; and the
    dispatch row reads `CONFINED_DISPATCH_WIRED`, which is False.

    THIS IS NOT AN ACTIVATION AND CANNOT BECOME ONE. `eligible` is the conjunction of the rows,
    so while no dispatch path in this repository both confines and is ledgered it is False by
    construction -- and that is the correct answer rather than a gap. Making it True would take
    an edit to that constant, which is exactly where such an edit should have to be visible.
    """
    state = (record or {}).get("state")
    granted = bool((record or {}).get("granted")) and state == "approved"
    documents = (case or {}).get("documents") if case else None
    holds = None if not documents else approval_holds(
        record, candidate=documents["candidate"], manifest=documents["manifest"],
        partition=documents["partition"], envelope=documents.get("envelope"))
    approval_ok = granted and (holds is None or holds["holds"])
    if not granted:
        approval_reason = (f"the approval record is in the {state!r} state with "
                           f"granted={bool((record or {}).get('granted'))}; only a granted record "
                           f"in the 'approved' state establishes this")
    elif holds is not None and not holds["holds"]:
        approval_reason = (f"the approval was granted, and its {', '.join(holds['moved'])} "
                           f"binding(s) no longer re-derive: what was approved is not what is "
                           f"in hand")
    else:
        approval_reason = None
    certificate, cert_reason = _certification_evidence(sentinel_report)
    rows = [
        {"requirement": "exact-approval",
         "owner": "workflow_eval.decide_approval over workflow_eval.approval_case (D22)",
         "satisfied": approval_ok, "reason": approval_reason,
         "evidence": {slot: (((record or {}).get("bindings") or {}).get(slot) or {}).get("hash")
                      for slot in APPROVAL_BINDINGS},
         "blocker": None if approval_ok else "exact-approval-missing",
         "re_derived_by": "workflow_eval.approval_holds" if holds is not None else None,
         "note": (BINDING_NOT_AUTHORITY_LABEL if holds is not None else
                  f"no case was supplied, so the state on the record was READ and not "
                  f"re-derived. {BINDING_NOT_AUTHORITY_LABEL}")},
        {"requirement": "protected-profile-certified",
         "owner": "exec_policy.certify_profile over exec_policy.run_sentinels (D07)",
         "satisfied": cert_reason is None, "reason": cert_reason, "evidence": certificate,
         "blocker": None if cert_reason is None else "protected-profile-uncertified",
         "re_derived_by": "exec_policy.certify_profile",
         "note": "an unverified profile establishes no promotion eligibility, and an approval "
                 "however exactly bound never stands in for one"},
        {"requirement": "confining-and-ledgered-dispatch",
         "owner": "whichever task wires a protected runtime transition",
         "satisfied": bool(CONFINED_DISPATCH_WIRED), "evidence": None,
         "blocker": None if CONFINED_DISPATCH_WIRED else "confining-dispatch-unwired",
         "re_derived_by": "workflow_eval.CONFINED_DISPATCH_WIRED",
         "reason": (None if CONFINED_DISPATCH_WIRED else
                    "this repository has no dispatch path that both confines and is recorded in "
                    "bin/attempt_ledger.py before and after the call"),
         "note": APPROVAL_NOT_ACTIVATION_LABEL},
    ]
    return {
        "eligible": all(row["satisfied"] for row in rows),
        "requirements": rows,
        "blockers": [row["blocker"] for row in rows if not row["satisfied"]],
        "holds": holds,
        "unproven": list(APPROVAL_UNPROVEN),
        "labels": [APPROVAL_NOT_ACTIVATION_LABEL, BINDING_NOT_AUTHORITY_LABEL,
                   NOT_ENFORCEMENT_LABEL],
    }


# ---- retention: the same store, the same writer, and a refusal kept like a grant ---------------

def write_approval(prefs_dir, record):
    """Persist one approval record under the prefs directory the caller named.

    Every record, whatever its state. A rejected or insufficient-evidence record is written with
    the same care as an approved one and is listed by `approval_report` beside it, because "this
    was refused, for these reasons, by this name, over these hashes" is the part of the history
    that gets lost first and the part a later reviewer most needs.

    Writing the same record twice is a no-op; writing DIFFERENT content under an id already on
    disk is refused loudly -- `write_manifest`'s rule, for `write_manifest`'s reason. An
    approval is an immutable record of one decision, so a second decision is a second record and
    never an edit of the first. This uses the same plain write the proposal writer beside it
    uses rather than introducing a third pattern into this store.
    """
    if record.get("v") != APPROVAL_VERSION:
        raise EvalError(f"not a {APPROVAL_VERSION} approval record")
    paths = _prefs_paths(prefs_dir)
    paths["approvals"].mkdir(parents=True, exist_ok=True)
    path = paths["approvals"] / f"{record['id']}.json"
    body = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text() != body:
        raise EvalError(f"approval {record['id']} already exists with DIFFERENT content; an "
                        f"approval records one decision and is never edited into another one. "
                        f"Nothing was overwritten.")
    path.write_text(body)
    _journal(paths, "policy.approval", approval=record["id"], candidate=record.get("candidate"),
             state=record["state"], granted=record["granted"], by=record.get("by"),
             refusals=sorted({row["reason"] for row in record.get("refusals") or ()}))
    return path


def read_approval(prefs_dir, approval_id):
    paths = _prefs_paths(prefs_dir)
    path = paths["approvals"] / f"{approval_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"no approval {approval_id!r} under {paths['approvals']}")
    data = json.loads(path.read_text())
    if data.get("v") != APPROVAL_VERSION:
        raise EvalError(f"{path} is not a {APPROVAL_VERSION} approval record")
    return data


def approval_report(prefs_dir):
    """Every approval on disk, whatever its state -- a READER, so an unreadable file is named
    rather than raised over and never quietly dropped from the list."""
    paths = _prefs_paths(prefs_dir)
    rows = []
    if paths["approvals"].is_dir():
        for path in sorted(paths["approvals"].glob("*.json")):
            try:
                data = json.loads(path.read_text())
            except (OSError, ValueError):
                rows.append({"id": path.stem, "state": "unreadable"})
                continue
            rows.append({
                "id": data.get("id"), "state": data.get("state"),
                "granted": data.get("granted"), "candidate": data.get("candidate"),
                "by": data.get("by"), "proposed_by": data.get("proposed_by"),
                "authority": data.get("authority"),
                "refusals": sorted({row.get("reason") for row in data.get("refusals") or ()
                                    if isinstance(row, dict)}),
                "bindings": {slot: ((data.get("bindings") or {}).get(slot) or {}).get("hash")
                             for slot in APPROVAL_BINDINGS},
                "unproven": data.get("unproven") or []})
    return {"approvals": rows, "path": str(paths["approvals"]),
            "states": list(APPROVAL_STATES), "refusal_vocabulary": list(APPROVAL_REFUSALS),
            "authority": REVIEW_AUTHORITY_LABEL,
            "labels": [BINDING_NOT_AUTHORITY_LABEL, APPROVAL_NOT_ACTIVATION_LABEL]}


#: The keys an approval case FILE may carry. Closed, for the reason `improvement_loop._job` is
#: closed: a field nobody reads is an instruction nobody follows, and a document that decides an
#: approval is the wrong place to be permissive about one.
APPROVAL_CASE_KEYS = ("candidate", "in_force", "manifest", "run", "partition", "proposed_by")


def load_approval_case(document, store_dir):
    """An approval case from a case FILE, with the manifest and the run read from the store.

    The one function in this section that reaches the evals store at all -- the three functions
    below it open only the prefs directory they were handed -- and the difference is the point:
    here the manifest goes through `read_manifest`, which re-derives its digest and refuses a
    file rewritten since it was written, and the envelope comes out of the store under its run id.
    The library entry point above is handed documents and can only vouch for their shape.
    `origin-not-dereferenced` stays on the record either way, because the candidate itself is
    still a document somebody handed in.
    """
    if not isinstance(document, dict):
        raise EvalError(f"an approval case is an object with {', '.join(APPROVAL_CASE_KEYS)}; "
                        f"this is a {type(document).__name__}")
    unknown = sorted(set(document) - set(APPROVAL_CASE_KEYS))
    if unknown:
        raise EvalError(f"the approval case carries {', '.join(repr(u) for u in unknown)}, which "
                        f"nothing here reads; the keys are {', '.join(APPROVAL_CASE_KEYS)}")
    missing = [key for key in ("candidate", "manifest", "partition") if not document.get(key)]
    if missing:
        raise EvalError(f"the approval case names no {', '.join(missing)}")
    manifest = read_manifest(store_dir, document["manifest"])
    envelope = read_envelope(store_dir, document["run"]) if document.get("run") else None
    return approval_case(candidate=document["candidate"], manifest=manifest,
                         partition=document["partition"], envelope=envelope,
                         in_force=document.get("in_force"),
                         proposed_by=document.get("proposed_by") or "")

# END OF THE EXACT APPROVAL SECTION (decision-improvement D22)


# =================================================================================================
# PROTECTED ACTIVATION: THE POINTER, AND WHAT STILL REFUSES TO MINT ONE (decision-improvement D23)
# =================================================================================================
#
# D22 ends at `approved` and says so: "an approval is not an activation. Nothing here writes a
# runtime pointer, selects a bundle, starts a run or makes anything runnable". This section is
# that pointer -- the transition a runtime WOULD take from legacy to canary or active -- and the
# first thing to say about it is that today it refuses, by machine, on evidence, every time.
#
# WHY IT REFUSES, AND WHERE THAT IS DECIDED. `CONFINED_DISPATCH_WIRED` is False. This repository
# has no dispatch path that both confines and is recorded in `bin/attempt_ledger.py` before and
# after the call, and until one exists there is nothing a protected activation could protect.
# `promotion_eligibility` already carries that fact as one of its rows; this gate RELAYS that
# function's rows whole and adds two more, so activation is a superset of promotion eligibility
# and can never be laxer than it. Nothing here flips the flag, and nothing here can: the gate
# reads it through D22's own row, and `_unwired_dispatch` re-reads it at call time in the pointer
# WRITER and again in the pointer READER, so a canary entry is refused when it is written and
# ignored if it somehow got written anyway.
#
# THE FOUR GATES THE TASK NAMES, AND WHERE EACH ONE IS DECIDED.
#
#   D07 profile            `exec_policy.certify_profile` over a sentinel report, through D18's
#                          `_certification_evidence`, relayed from `promotion_eligibility`
#   current manifest       `verify_manifest` for the document and `require_held_out` for the
#                          STORE -- `manifest_currency`. `require_held_out` is the controller
#                          and already consults both; what this adds is D18's two-codes rule,
#                          asking the document question first so a forged manifest is reported
#                          as a forgery rather than as one entry in a list of blockers
#   D19 endpoint/margins/  `OPERATOR_DECLARATIONS` (seven, D18's) UNION
#   caps/stops             `decision_eval.RECOVERY_REPORT_DECLARATIONS` (six, D19's), plus
#                          `decision_eval.operator_plan`'s own validation of its six --
#                          `trial_plan_completeness`. Neither owner covers the other: D19's own
#                          comment names `primary_endpoint`, `sample_size` and
#                          `independent_evaluation` as "workflow_eval.live_requirements's
#                          responsibility, not this module's". That is the F4 shape D19's own
#                          comment names -- two halves, each correct about itself, each phrased
#                          as though it were the whole -- and this is where the two are composed
#   D22 approval           `promotion_eligibility`'s own exact-approval row, which re-derives
#                          all four bindings through `approval_holds` when a case is supplied
#
# EACH OF THOSE IS REACHABLE ON ITS OWN. A gate that could only ever fire while another was
# already firing has never been shown to do anything, so `activation_decision` evaluates every
# row EAGERLY and reports the blocker SET. The eager choice is deliberate and is D22's, not
# D21's: D21 needed lazy guards because one of them raised about a value another had already
# refused, and every gate here is TOTAL over what it is handed -- `manifest_currency` answers
# for a missing store and a missing manifest rather than raising about them,
# `trial_plan_completeness` catches the contract's refusal and reports it, and the relay works
# over a verdict that has already been computed. A caller who is told only the first thing wrong
# fixes it and comes back for the next one.
#
# THE FIFTH ROW IS UNCONDITIONAL AND IS THE POINT. With all four gates satisfied over synthetic
# fixtures, `permitted` is still False and `blockers` is exactly `['confining-dispatch-unwired']`.
# That is this section's positive control: it proves the four gates are individually satisfiable
# -- so each single-gate refusal below is a real refusal and not an artefact of everything being
# broken -- and it proves the transition still refuses. A fixture that makes a gate pass proves
# the gate READS what it claims to read. It certifies no host, no isolation and no model.
#
# THE POINTER, AND WHY IT IS COMPARE-AND-SWAP. A lost update here is a silent wrong-policy
# activation, so there is no read-modify-write anywhere in this section. Each generation is its
# own immutable file, `gen-000001.json` upward, created with `safe_paths.confined_create_bytes`
# -- `O_EXCL`, where "is this name free" and "write these bytes" are one kernel operation.
# `swap_activation(expected=N)` writes `gen-(N+1)` and does NOT re-read the directory first:
# the only check is the create, so a stale expectation fails on the kernel's answer rather than
# on a comparison with its own window. Two writers that both read generation 4 both try
# `gen-000005`; exactly one gets it and the other raises `ActivationConflict`. Nothing is ever
# rewritten and nothing is ever deleted, which is also why a rollback destroys no evidence.
#
# WHAT A POINTER IS NOT. It is not authority. A process that can write the prefs directory can
# write a file in it, and no hash, digest or gate block stored inside that file changes that --
# the same thing D22 said about binding four digests, one layer out. What the writer and the
# reader BOTH do is re-derive the one row that can be re-derived here and now, so the state this
# repository is actually in beats whatever a stored block claims about it. The residual is
# carried as unconditional machine-readable codes in `ACTIVATION_UNPROVEN`, never as prose a
# reader has to notice.
#
# WHAT RUNS TODAY, AND WHAT THE ABSENCE OF A POINTER MEANS. No pointer -> legacy. Not an error,
# not a default activation, not a degraded mode: the behaviour that was there before any of this
# existed, which is the default everywhere. An unreadable pointer, a retired one, a rolled-back
# one, one whose eligibility a run falls outside of, and one whose gate block claims the unwired
# row: all legacy too. Every path out of `runtime_activation` that is not a live running state
# is legacy, and `RUNTIME_REASONS` says which one it was.
#
# OLD PREFERENCES STILL DO NOTHING. `routing-policy.json` is untouched by this section and stays
# pull-only. Nothing here opens it: `read_policy` and `policy_report` in the D20 section above
# are what read one, and `decision_policy.describe_legacy_preferences` is what reads one for
# what it IS. No function anywhere turns a preference file into a policy bundle, and a pointer
# store existing beside it changes none of that.

#: The version of a pointer entry. Registered in `release_gate.VERSION_SOURCES`. On the
#: REFERENCED OBJECT, like `POLICY_REFS_VERSION` and `APPROVAL_VERSION` before it: no existing
#: version is bumped, because raising one would make every stored record unreadable rather than
#: migrating it.
ACTIVATION_VERSION = "polytropos.policy-activation/1"

#: Where pointer generations live under the prefs directory the caller names. Beside the
#: proposals and the approvals, in the same store, written by the same module. `runtime_data`
#: gains nothing and `.gitignore` gains nothing -- a new store would be an architect's decision
#: and this is not one.
POLICY_ACTIVATION = "routing-policy.activation"

#: The four runtime states D22's lifecycle deliberately stops short of. `canary` and `active`
#: change what a run does; `retired` and `rolled-back` are how a scope leaves them, and both
#: read as legacy for every run that starts afterwards.
ACTIVATION_STATES = ("canary", "active", "retired", "rolled-back")

#: The states that change what a run does. Only these need a gate, and only these may carry a
#: bundle a run pins. The other two move a runtime AWAY from a bundle, which never needs
#: permission -- refusing a rollback because some evidence went stale is how a bad activation
#: gets stuck in place.
RUNNING_STATES = ("canary", "active")

#: The requirements this section decides for itself. Everything else on an activation verdict is
#: `promotion_eligibility`'s, relayed whole and never renamed; a relayed row that arrived
#: carrying one of these names would mean two owners for one requirement and is refused.
ACTIVATION_OWN_REQUIREMENTS = ("current-evaluation-manifest", "predeclared-trial-plan")

#: The blocker codes those two rows emit. The relayed rows keep the codes their own owner gave
#: them -- `protected-profile-uncertified`, `confining-dispatch-unwired` and
#: `exact-approval-missing` are `PROTOCOL_BLOCKERS`' and `promotion_eligibility`'s, not copies
#: here -- so there is nothing in this tuple to drift away from another owner's vocabulary.
ACTIVATION_BLOCKERS = ("evaluation-manifest-not-current", "trial-plan-incomplete")

#: The keys this section reads off every relayed requirement row. A row missing one of them is
#: REFUSED rather than relayed with a hole in it: `read_ref` drops an unknown key and D20's
#: relay refuses one, for the reason that applies here too -- a verdict that claims to carry
#: what it dropped is worse than no verdict.
RELAYED_ROW_KEYS = ("requirement", "satisfied", "reason", "blocker", "re_derived_by")

#: What no pointer written or read here establishes, however many gates passed. Machine-readable,
#: closed and UNCONDITIONAL: nothing in this section can discharge any of them, so none is ever
#: left off a record on the strength of some other check passing.
ACTIVATION_UNPROVEN = ("pointer-store-not-authenticated", "gate-block-not-re-derived-in-full",
                       "fixture-proves-mechanics-not-safety")

ACTIVATION_UNPROVEN_NOTES = {
    "pointer-store-not-authenticated":
        "a process that can write the prefs directory can write a file in it. The generation "
        "files are create-once and 0600, which stops a lost update and a careless overwrite; "
        "neither is authentication, and nothing here asks who wrote a byte",
    "gate-block-not-re-derived-in-full":
        "a stored entry carries the gate verdict it was minted with. The writer and the reader "
        "both re-derive the ONE row that can be answered here and now -- whether this "
        "repository has a confining, ledgered dispatch path -- and refuse an entry that "
        "disagrees with it. The other rows are read, not re-run: re-deriving them would need "
        "the manifest, the store, the sentinel report and the approval case the decision was "
        "taken over, none of which a pointer holds",
    "fixture-proves-mechanics-not-safety":
        "every gate in this section can be made to pass by a synthetic fixture, and the tests "
        "do exactly that to prove each gate is individually reachable. A passing fixture shows "
        "that a gate READS what it claims to read. It certifies no host's isolation, no live "
        "deployment and no model's quality, and a fixture that made every gate pass would still "
        "leave this transition refused",
}

#: What a canary must be watched for while it is in force. Inputs a monitor observes, declared
#: on the entry so a reader can see what was promised; nothing in this section monitors
#: anything, samples anything or triggers anything. The list is the shared plan's own sentence
#: about canaries, in codes rather than prose.
ACTIVATION_MONITORS = ("accepted-completion", "delayed-defects", "censoring",
                       "operator-interventions", "resource-basis", "invalid-rate",
                       "abstain-rate", "provider-version-drift")

#: The bounds a running entry must declare. `cohort` may be empty, which means "the whole of the
#: eligible task classes"; `task_classes` may not, and `max_runs` must be a positive count --
#: an unbounded canary is not a canary.
ELIGIBILITY_KEYS = ("task_classes", "cohort", "max_runs")

#: What a run STARTING NOW must be able to say about itself before an eligibility limit can be
#: checked against it. `None` refuses, for `COORDINATOR_CHECKS`' reason: an unmade check is not
#: a passed one.
RUNTIME_FACT_KEYS = ("task_class", "item", "runs_so_far")

#: Every reason `runtime_activation` gives for the mode it resolved. Closed, so a report counts
#: them and a caller branches on them. All but `pinned` end at legacy.
RUNTIME_REASONS = ("no-pointer", "pointer-unreadable", "pointer-retired", "pointer-rolled-back",
                   "confining-dispatch-unwired", "eligibility-unestablished",
                   "outside-eligible-cohort", "eligibility-limit-reached", "pinned")

#: The keys a stored entry carries. Closed in both directions, like every other stored shape
#: here: an unknown key is refused rather than ignored, and a missing one refused rather than
#: filled in.
ACTIVATION_ENTRY_KEYS = ("v", "id", "state", "scope", "scope_key", "bundle_ref", "approval",
                         "candidate", "manifest", "partition", "eligibility", "monitors",
                         "gate", "fallback", "previous", "by", "at", "reason", "unproven",
                         "labels")

POINTER_NOT_AUTHORITY_LABEL = (
    "a runtime pointer is INTEGRITY and not AUTHORITY. Create-once generation files stop a lost "
    "update, a silent overwrite and a rewritten history; they establish nothing about who wrote "
    "one. Anyone who can write the prefs directory can write a pointer, exactly as anyone who "
    "can type a second name can defeat the self-approval check one layer up -- authority would "
    "have to be protected at the execution boundary, which this module does not provide and "
    "does not claim")

ACTIVATION_REFUSED_TODAY_LABEL = (
    "this transition refuses today and the refusal is machine-derived, not a policy somebody "
    "remembered: workflow_eval.CONFINED_DISPATCH_WIRED is False, so promotion_eligibility's own "
    "dispatch row is unsatisfied, so the activation gate -- which relays that row whole and adds "
    "two of its own -- can never be permitted. Making it permitted would take an edit to that "
    "constant, in the same change that wires a dispatch path which both confines and is "
    "ledgered, which is exactly where such an edit should have to be visible")

ABSENT_POINTER_IS_LEGACY_LABEL = (
    "no pointer means LEGACY: the behaviour that was there before any of this existed. It is "
    "not an error, not a default activation and not a degraded mode. An unreadable pointer, a "
    "retired one, a rolled-back one and one whose eligibility this run falls outside of all "
    "read the same way, and the reason code says which")

ROLLBACK_SCOPE_LABEL = (
    "a rollback moves FUTURE runs off a bundle. It contacts no provider, resets no user "
    "workspace, deletes no generation, erases no evidence, reverses no external effect and "
    "refunds no call -- every generation ever written stays on disk and stays readable. Runs "
    "already in flight keep the pin they started with; there is no path by which one picks this "
    "up mid-run")

ROLLBACK_TARGET_NOT_ACTIVATED_LABEL = (
    "the fallback a rollback names is the one decision_policy.resolve_bundle chose over the "
    "runtime's own facts, and recording it is not activating it: a rolled-back pointer resolves "
    "every future run to legacy, and promoting that fallback into a running state would need "
    "its own pass through this gate. Naming a target is not taking it")

OLD_PREFERENCES_UNCHANGED_LABEL = (
    "routing-policy.json remains pull-only and this section never opens it. There is no "
    "function here that reads an applied preference file, and none that turns one into a policy "
    "bundle; an existing preference file does not become executable policy because an "
    "activation pointer now exists beside it")


class ActivationConflict(EvalError):
    """A compare-and-swap that lost: the generation this caller expected to extend already has a
    successor. The loser is told which generation took the name and writes nothing."""


# ---- the two gates this section decides for itself ---------------------------------------------

def manifest_currency(store_dir, manifest, partition, *, tasks=None, acceptance=None):
    """Is the grouped/exposure manifest still the one an approval could be acted on? -> a row.

    TWO OWNERS, BOTH CONSULTED, NEITHER RE-IMPLEMENTED.

      * `verify_manifest` answers for the DOCUMENT: the digest it is filed under, membership,
        orphans, leaking items sitting in a real partition, and grouping -- a defect's variants
        split across partitions means a held-out result over any of them was already seen
        through the others.
      * `require_held_out` answers for the STORE: exposure, retirement, single-use and
        calibration fits. `MANIFEST_VERIFICATION_NOTE` has said since D18 that "verifying a
        manifest is not the same as a partition still being unspent".

    WHY `verify_manifest` IS CALLED HERE WHEN `require_held_out` ALREADY CALLS IT. It does --
    that function is the controller and it consults both -- but it MERGES what it found into one
    blocker sentence. D18's own rule is that `manifest-unverified` and `no-held-out-evidence`
    are "deliberately TWO codes and never one": a document that does not match its own digest is
    a forgery finding and nothing may be read out of it, while a partition that has simply been
    looked at is an honest document that is spent. This asks the document question FIRST so the
    reason a reader gets says which of the two it was, and returns before the store is consulted
    at all when the answer is the first one. Neither check is re-implemented here.

    TOTAL, by construction. A missing manifest, a missing store directory and a partition name
    that is not one all come back as an unsatisfied row rather than an exception, which is what
    lets `activation_decision` evaluate every gate eagerly and hand the caller the whole reason.
    A store directory of None does NOT skip the second half: it fails it, because an unmade
    check is not a passed one and half of this gate passing is the exact shape this kit keeps
    finding.
    """
    evidence = {"manifest": None, "partition": partition, "findings": [], "held_out": None,
                "store": None if store_dir is None else str(store_dir)}
    if not isinstance(manifest, dict):
        return _activation_row(
            "current-evaluation-manifest", False,
            f"no evaluation manifest was supplied (got {type(manifest).__name__}), so neither "
            f"its structure nor the store's record of it could be consulted",
            evidence)
    evidence["manifest"] = manifest.get("id")
    findings = verify_manifest(manifest, tasks=tasks, acceptance=acceptance)
    evidence["findings"] = [{"kind": f.get("kind"), "detail": f.get("detail")} for f in findings]
    if findings:
        kinds = ", ".join(sorted({str(f.get("kind")) for f in findings}))
        return _activation_row(
            "current-evaluation-manifest", False,
            f"workflow_eval.verify_manifest returned {len(findings)} finding(s) over this "
            f"manifest ({kinds}), so nothing may be read out of it as a cohort: the document is "
            f"not the one it claims to be",
            evidence)
    if store_dir is None:
        return _activation_row(
            "current-evaluation-manifest", False,
            "the manifest verifies as a document and NO store was supplied, so exposure, "
            "retirement, single-use and calibration fits were never consulted. Verifying a "
            "manifest is not the same as its partition still being unspent, and an unmade check "
            "is not a passed one",
            evidence)
    try:
        usable = require_held_out(store_dir, manifest, partition, tasks=tasks,
                                  acceptance=acceptance)
    except EvalError as exc:
        return _activation_row(
            "current-evaluation-manifest", False,
            f"workflow_eval.require_held_out refused the {partition!r} partition against the "
            f"store: {exc}", evidence)
    evidence["held_out"] = len(usable)
    if not usable:
        return _activation_row(
            "current-evaluation-manifest", False,
            f"the {partition!r} partition has no usable held-out item left in the store; an "
            f"empty cohort is not evidence", evidence)
    return _activation_row("current-evaluation-manifest", True, None, evidence)


def trial_plan_completeness(declarations):
    """Every predeclared endpoint, margin, cap and stop a live transition needs -> a row.

    THE UNION OF TWO OWNERS, READ FROM BOTH AT CALL TIME. `OPERATOR_DECLARATIONS` is D18's seven
    per-arm predeclarations; `decision_eval.RECOVERY_REPORT_DECLARATIONS` is D19's six
    per-evaluation ones. They share four names by design, and D19's own comment names the other
    three -- `primary_endpoint`, `sample_size`, `independent_evaluation` -- as
    "workflow_eval.live_requirements's responsibility, not this module's". Two halves, each
    correct about itself, each phrased as though it were the whole, and nothing composing them
    -- the F4 shape D19's own comment names and leaves open. The required set here is the
    UNION, and there is no list of field names in this function to drift from either owner.

    `decision_eval.operator_plan` is then run over the declarations, because the owner of a
    field owns what a valid value for it is: an `independent_label_source` outside its own
    `LABEL_SOURCES`, or an `observation_window` that names no instant, are refusals this
    function would not otherwise catch and does not re-implement.

    TOTAL: the contract's refusal is caught and reported as an unsatisfied row, never raised.
    """
    de = _de()
    required = tuple(sorted(set(OPERATOR_DECLARATIONS) | set(de.RECOVERY_REPORT_DECLARATIONS)))
    evidence = {"required": list(required),
                "from_trial_protocol": list(OPERATOR_DECLARATIONS),
                "from_recovery_report": list(de.RECOVERY_REPORT_DECLARATIONS),
                "missing": [], "plan": None}
    if not isinstance(declarations, dict):
        evidence["missing"] = list(required)
        return _activation_row(
            "predeclared-trial-plan", False,
            f"no operator declarations were supplied (got {type(declarations).__name__}); all "
            f"{len(required)} predeclared field(s) are undeclared", evidence)
    missing = [name for name in required if declarations.get(name) in (None, "", [], {})]
    evidence["missing"] = missing
    if missing:
        return _activation_row(
            "predeclared-trial-plan", False,
            f"undeclared: {', '.join(missing)}. {NO_INVENTED_NUMBER_LABEL}", evidence)
    try:
        plan = de.operator_plan(declarations)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        # `ContractError` is a `ValueError`, and naming its class here by identity would not
        # work anyway: `bin/` is not a package, so decision_eval's contract instance is a
        # different class object from this module's -- the loader defect this kit has already
        # been bitten by. Caught by BASE class rather than re-raised, because a gate that
        # raised here would abandon the other rows the caller is owed.
        return _activation_row(
            "predeclared-trial-plan", False,
            f"decision_eval.operator_plan refused these declarations: {exc}", evidence)
    evidence["plan"] = {"status": plan.get("status"),
                        "own_declarations_complete": plan.get("own_declarations_complete"),
                        "not_covered": list((plan.get("not_covered") or {}).get("fields") or ())}
    if not plan.get("own_declarations_complete"):
        return _activation_row(
            "predeclared-trial-plan", False,
            f"decision_eval.operator_plan reports {plan.get('status')!r} over its own six "
            f"fields: {', '.join(plan.get('missing') or ())}", evidence)
    return _activation_row("predeclared-trial-plan", True, None, evidence)


def _activation_row(requirement, satisfied, reason, evidence):
    """One row this section decided, in the same shape `promotion_eligibility` produces so a
    caller cannot tell a relayed row from a local one by its shape -- only by `owner`."""
    blocker = None
    if not satisfied:
        blocker = ("evaluation-manifest-not-current"
                   if requirement == "current-evaluation-manifest" else "trial-plan-incomplete")
    if blocker is not None and blocker not in ACTIVATION_BLOCKERS:  # pragma: no cover
        raise EvalError(f"blocker {blocker!r} is outside ACTIVATION_BLOCKERS")
    owners = {
        "current-evaluation-manifest":
            ("workflow_eval.verify_manifest for the document; workflow_eval.require_held_out "
             "against the store (D06)"),
        "predeclared-trial-plan":
            ("the operator, never this module -- checked against workflow_eval."
             "OPERATOR_DECLARATIONS and decision_eval.RECOVERY_REPORT_DECLARATIONS together, "
             "and validated by decision_eval.operator_plan (D18/D19)"),
    }
    derived = {
        "current-evaluation-manifest": "workflow_eval.manifest_currency",
        "predeclared-trial-plan": "workflow_eval.trial_plan_completeness",
    }
    return {"requirement": requirement, "owner": owners[requirement], "satisfied": bool(satisfied),
            "reason": reason, "evidence": evidence, "blocker": blocker,
            "re_derived_by": derived[requirement], "relayed_from": None,
            "note": (MANIFEST_VERIFICATION_NOTE if requirement == "current-evaluation-manifest"
                     else ACTIVATION_UNPROVEN_NOTES["fixture-proves-mechanics-not-safety"])}


# ---- the relay: promotion eligibility's rows, whole, or not at all ------------------------------

def _relayed_rows(verdict, where):
    """`promotion_eligibility`'s requirement rows, relayed whole -> a list. Refuses.

    CLOSURE IN BOTH DIRECTIONS, which is the whole reason this is a function.

      * A row missing any of `RELAYED_ROW_KEYS` is refused, not padded: a verdict that claimed
        to carry a requirement whose `satisfied` it never read would be strictly worse than no
        verdict at all.
      * A row whose `requirement` is one of `ACTIVATION_OWN_REQUIREMENTS` is refused: two
        owners for one requirement name is a collision a reader cannot untangle.
      * An empty row list is refused. A gate assembled out of nothing is not a gate, and an
        upstream function that stopped returning rows must fail loudly here rather than make
        this one vacuously permissive.

    And -- the direction that matters for a gate -- a requirement ADDED upstream arrives here
    automatically and is conjoined automatically. That fails closed, which is the same reason
    `decision_policy.denial_reasons` derives its hard filters by subtraction.
    """
    rows = (verdict or {}).get("requirements")
    if not isinstance(rows, list) or not rows:
        raise EvalError(
            f"{where} produced no requirement rows; an activation gate assembled out of nothing "
            f"would be permitted by default, which is the opposite of what it is for")
    out = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise EvalError(f"{where} row {index} is a {type(row).__name__}, not a requirement")
        missing = sorted(set(RELAYED_ROW_KEYS) - set(row))
        if missing:
            raise EvalError(
                f"{where} row {index} ({row.get('requirement')!r}) is missing "
                f"{', '.join(repr(m) for m in missing)}; a requirement row is relayed whole or "
                f"not at all, and one relayed without its verdict would claim to carry what it "
                f"dropped")
        name = row["requirement"]
        if name in ACTIVATION_OWN_REQUIREMENTS:
            raise EvalError(
                f"{where} carries a {name!r} row, which is also a requirement this section "
                f"decides; one requirement has one owner, and two rows under one name is a "
                f"collision a reader cannot untangle")
        relayed = dict(row)
        relayed["relayed_from"] = where
        out.append(relayed)
    return out


def _unwired_dispatch(gate, where):
    """The one row of a STORED gate block that is re-derivable here and now -> reason or None.

    `CONFINED_DISPATCH_WIRED` is read at call time, never copied into a literal, and this is
    called by the pointer WRITER before anything is created and by the pointer READER before a
    stored entry resolves a run to anything. So a gate block claiming a satisfied dispatch row
    while this repository has no confining, ledgered dispatch path is refused at the write and
    ignored at the read -- the state the repository is actually in beats what a stored document
    says about it.

    The other rows are NOT re-derived: doing that would need the manifest, the store, the
    sentinel report and the approval case the decision was taken over, none of which a pointer
    holds. `gate-block-not-re-derived-in-full` is that limit, carried on every record.
    """
    if CONFINED_DISPATCH_WIRED:
        return None
    if not isinstance(gate, dict):
        return (f"{where} carries no gate verdict at all, and a running state needs one that "
                f"was permitted")
    if gate.get("permitted") is not True:
        return (f"{where} carries a gate verdict with permitted={gate.get('permitted')!r}; only "
                f"a permitted gate mints a running pointer")
    return (f"{where} claims a permitted gate while workflow_eval.CONFINED_DISPATCH_WIRED is "
            f"False: this repository has no dispatch path that both confines and is recorded in "
            f"bin/attempt_ledger.py before and after the call, so no verdict stored in a file "
            f"can make this transition permitted. {ACTIVATION_REFUSED_TODAY_LABEL}")


def activation_decision(approval, *, case=None, target_state="canary", sentinel_report=None,
                        store_dir=None, manifest=None, partition=None, declarations=None,
                        tasks=None, acceptance=None):
    """Would this runtime be permitted to move to `target_state`? -> rows, blockers, a verdict.

    It READS -- `require_held_out` opens the evals store's exposure log, which is the whole
    point of the manifest gate -- and it writes nothing, creates nothing, starts nothing,
    dispatches nothing and mints nothing. `activation_entry` is the only function that turns a
    permitted verdict into a pointer entry, and it refuses an unpermitted one.

    EVERY ROW IS EVALUATED. See the section note: the four gates the task names must each be
    reachable with the other three satisfied, so the caller gets the blocker SET rather than the
    first thing that happened to be wrong. Every gate here is total over what it is handed.

    `permitted` is the conjunction of every row, relayed and local alike. While
    `CONFINED_DISPATCH_WIRED` is False, `promotion_eligibility`'s own dispatch row is
    unsatisfied, so this is False by construction -- and that is the correct answer, not a gap.
    """
    if target_state not in RUNNING_STATES:
        raise EvalError(
            f"{target_state!r} is not a state a runtime is ACTIVATED into; the two are "
            f"{', '.join(RUNNING_STATES)}. Retiring or rolling back is a different transition "
            f"with a different function, and it needs no gate: moving away from a bundle is "
            f"never the thing permission protects")
    verdict = promotion_eligibility(approval, case=case, sentinel_report=sentinel_report)
    rows = _relayed_rows(verdict, "workflow_eval.promotion_eligibility")
    rows.append(manifest_currency(store_dir, manifest, partition, tasks=tasks,
                                 acceptance=acceptance))
    rows.append(trial_plan_completeness(declarations))
    blockers = sorted({row["blocker"] for row in rows
                       if not row["satisfied"] and row["blocker"]})
    permitted = all(row["satisfied"] for row in rows)
    at = _now()
    decision = {
        "v": ACTIVATION_VERSION,
        "target_state": target_state,
        "permitted": permitted,
        "requirements": rows,
        "blockers": blockers,
        "approval": (approval or {}).get("id"),
        "candidate": (approval or {}).get("candidate"),
        "manifest": manifest.get("id") if isinstance(manifest, dict) else None,
        "partition": partition,
        "at": at,
        "promotion_eligible": bool(verdict.get("eligible")),
        "unproven": list(ACTIVATION_UNPROVEN),
        "labels": [ACTIVATION_REFUSED_TODAY_LABEL, POINTER_NOT_AUTHORITY_LABEL,
                   APPROVAL_NOT_ACTIVATION_LABEL, NOT_ENFORCEMENT_LABEL,
                   OLD_PREFERENCES_UNCHANGED_LABEL],
    }
    # The gate's own content identity, so a stored entry names the verdict it was minted with
    # and a reader can tell two verdicts apart. Provenance (`at`) stays outside it, D06's rule.
    decision["sha"] = _sha(_canonical({
        "target_state": target_state, "permitted": permitted, "blockers": blockers,
        "rows": [{k: row.get(k) for k in ("requirement", "satisfied", "blocker")}
                 for row in rows]}))
    return decision


# ---- the entries a pointer generation may hold --------------------------------------------------

def scope_key(scope):
    """One activation scope -> the safe filename component its generations live under.

    A DIGEST of the canonical scope rather than a rendering of it. A project path and a task
    class are user text, and text that becomes a filename is text that can name a path;
    `safe_paths.validate_id` then checks the result anyway, which is the belt this braces.
    """
    if not isinstance(scope, dict) or not scope:
        raise EvalError("an activation scope is a non-empty object -- the candidate's own "
                        "scope, as decision_contract parsed it")
    return _sp().validate_id(f"scope-{_sha(_canonical(scope))[:16]}", "activation scope")


def _eligibility(value):
    """The bounds a running entry declares, or `EvalError`. A canary is a BOUNDED cohort, so an
    absent bound is refused rather than read as `no limit`."""
    if not isinstance(value, dict):
        raise EvalError(f"eligibility is an object with {', '.join(ELIGIBILITY_KEYS)}, not a "
                        f"{type(value).__name__}")
    unknown = sorted(set(value) - set(ELIGIBILITY_KEYS))
    missing = sorted(set(ELIGIBILITY_KEYS) - set(value))
    if unknown or missing:
        raise EvalError(
            "eligibility carries " + "; ".join(part for part in (
                f"unknown key(s) {', '.join(repr(k) for k in unknown)}" if unknown else "",
                f"no {', '.join(repr(k) for k in missing)}" if missing else "") if part)
            + f"; the keys are {', '.join(ELIGIBILITY_KEYS)}")
    classes = value["task_classes"]
    if not isinstance(classes, (list, tuple)) or not classes or \
            not all(isinstance(c, str) and c for c in classes):
        raise EvalError("eligibility.task_classes is a non-empty list of task class names; a "
                        "canary with no declared cohort is not a bounded one")
    cohort = value["cohort"]
    if not isinstance(cohort, (list, tuple)) or not all(isinstance(c, str) and c for c in cohort):
        raise EvalError("eligibility.cohort is a list of item ids, empty for `every item of the "
                        "declared task classes`")
    runs = value["max_runs"]
    if not isinstance(runs, int) or isinstance(runs, bool) or runs < 1:
        raise EvalError("eligibility.max_runs is a positive count; an unbounded canary is not a "
                        "canary")
    return {"task_classes": sorted(set(classes)), "cohort": sorted(set(cohort)),
            "max_runs": runs}


def _monitors(value):
    """The monitoring inputs a running entry declares, checked against `ACTIVATION_MONITORS`."""
    if not isinstance(value, (list, tuple)) or not value:
        raise EvalError(f"monitors is a non-empty list drawn from "
                        f"{', '.join(ACTIVATION_MONITORS)}; a canary nobody watches is not one")
    unknown = sorted(set(value) - set(ACTIVATION_MONITORS))
    if unknown:
        raise EvalError(f"monitor input(s) {', '.join(repr(u) for u in unknown)} are outside "
                        f"ACTIVATION_MONITORS ({', '.join(ACTIVATION_MONITORS)})")
    return sorted(set(value))


def _entry(state, *, scope, by, reason, bundle_ref=None, gate=None, fallback=None,
           eligibility=None, monitors=None, approval=None, candidate=None, manifest=None,
           partition=None, now=None):
    at = now or _now()
    key = scope_key(scope)
    entry = {
        "v": ACTIVATION_VERSION, "id": "", "state": state, "scope": _frozen(scope),
        "scope_key": key, "bundle_ref": bundle_ref, "approval": approval,
        "candidate": candidate, "manifest": manifest, "partition": partition,
        "eligibility": eligibility, "monitors": monitors, "gate": gate, "fallback": fallback,
        "previous": None, "by": by, "at": at,
        "reason": _rd().redact(reason or "")["text"],
        "unproven": list(ACTIVATION_UNPROVEN),
        "labels": [POINTER_NOT_AUTHORITY_LABEL, ABSENT_POINTER_IS_LEGACY_LABEL,
                   OLD_PREFERENCES_UNCHANGED_LABEL],
    }
    entry["id"] = f"act-{str(at)[:10]}-{_sha(_canonical(dict(entry, id='')))[:6]}"
    return entry


def activation_entry(decision, *, scope, bundle_ref, eligibility, monitors, by, now=None):
    """Mint the pointer entry a permitted gate would produce -> an entry. RAISES otherwise.

    THE ONE PLACE A RUNNING POINTER IS MADE, and it refuses an unpermitted verdict before it
    looks at anything else. There is no keyword here through which a caller could assert
    permission: `decision` is `activation_decision`'s own output, and `_unwired_dispatch` then
    re-derives the one row that can be re-derived, so a hand-built verdict with
    `permitted: True` is refused too while `CONFINED_DISPATCH_WIRED` is False.

    Today this function cannot return. That is the task's whole point, and it is enforced here
    rather than merely documented: there is no argument anybody can pass that gets past it.
    """
    if not isinstance(decision, dict) or decision.get("v") != ACTIVATION_VERSION:
        raise EvalError(f"an activation entry is minted from an {ACTIVATION_VERSION} gate "
                        f"verdict (workflow_eval.activation_decision), not a "
                        f"{type(decision).__name__}")
    state = decision.get("target_state")
    if state not in RUNNING_STATES:
        raise EvalError(f"the gate verdict names target_state {state!r}; the states a runtime "
                        f"is activated into are {', '.join(RUNNING_STATES)}")
    if decision.get("permitted") is not True:
        raise EvalError(
            f"the activation gate refused this transition, so there is no pointer to mint. "
            f"Blocker(s): {', '.join(decision.get('blockers') or ()) or 'unreported'}. "
            f"{ACTIVATION_REFUSED_TODAY_LABEL}")
    unwired = _unwired_dispatch(decision, "this gate verdict")
    if unwired:
        raise EvalError(unwired)
    if not by:
        raise EvalError("--by is required: an activation names who took it")
    return _entry(state, scope=scope, by=by,
                  reason=f"gate {decision.get('sha')} permitted {state}",
                  bundle_ref=_policy_ref(bundle_ref, "bundle"),
                  gate=_frozen({k: decision[k] for k in
                                ("v", "target_state", "permitted", "blockers", "requirements",
                                 "sha", "unproven")}),
                  eligibility=_eligibility(eligibility), monitors=_monitors(monitors),
                  approval=decision.get("approval"), candidate=decision.get("candidate"),
                  manifest=decision.get("manifest"), partition=decision.get("partition"),
                  now=now)


def rollback_entry(*, scope, resolution, by, reason, current=None, now=None):
    """Move FUTURE runs off whatever is in force -> a `rolled-back` entry. No gate, no provider.

    NO GATE, DELIBERATELY. Moving a runtime away from a bundle is not the thing permission
    protects; refusing a rollback because some evidence went stale is how a bad activation gets
    stuck in place. What this needs instead is a fallback somebody else chose:
    `decision_policy.resolve_bundle`, whose `_unmet` refuses any bundle with no approval
    reference and whose chain always terminates at legacy. This function takes that RESOLUTION
    as a value and relays which bundle it named -- it resolves nothing itself, opens no catalog
    and contacts nothing. `rollback selects an approved compatible fallback` is therefore that
    function's rule, enforced where it is defined.

    AND RECORDING A TARGET IS NOT TAKING IT. A `rolled-back` pointer resolves every future run
    to legacy, whatever the fallback named; promoting that fallback into a running state would
    need its own pass through `activation_decision`, which is why `bundle_ref` stays null here
    and the target lives under `fallback`.

    NOTHING IS DESTROYED. Every generation ever written stays on disk: this appends a new one.
    No workspace, no evidence, no external effect and no call is touched -- see
    `ROLLBACK_SCOPE_LABEL`, which travels on the entry.
    """
    if not by:
        raise EvalError("--by is required: a rollback names who took it")
    source = getattr(resolution, "source", None)
    if source not in _dp().RESOLUTION_SOURCES:
        raise EvalError(
            f"a rollback names the fallback decision_policy.resolve_bundle chose; this is a "
            f"{type(resolution).__name__} whose source is {source!r}, not one of "
            f"{', '.join(_dp().RESOLUTION_SOURCES)}")
    bundle = getattr(resolution, "bundle", None)
    target = None if bundle is None else _dp().bundle_ref(bundle)
    fallback = {
        "source": source,
        "bundle_ref": None if target is None else _policy_ref(dict(target), "bundle"),
        "reasons": sorted(getattr(resolution, "reasons", ()) or ()),
        "chain": list(getattr(resolution, "chain", ()) or ()),
        "in_force_for_future_runs": "legacy",
        "requires": "its own pass through workflow_eval.activation_decision",
        "note": ROLLBACK_TARGET_NOT_ACTIVATED_LABEL,
    }
    entry = _entry("rolled-back", scope=scope, by=by, reason=reason, fallback=fallback,
                   approval=(current or {}).get("approval"),
                   candidate=(current or {}).get("candidate"),
                   manifest=(current or {}).get("manifest"),
                   partition=(current or {}).get("partition"), now=now)
    entry["labels"] = entry["labels"] + [ROLLBACK_SCOPE_LABEL, ROLLBACK_TARGET_NOT_ACTIVATED_LABEL]
    return entry


def retirement_entry(*, scope, by, reason, current=None, now=None):
    """End a scope's activation without naming a successor -> a `retired` entry. No gate.

    The difference from a rollback is what it says, not what it does: a rollback names the
    fallback a resolution chose, a retirement names none. Both resolve every future run to
    legacy and both destroy nothing.
    """
    if not by:
        raise EvalError("--by is required: a retirement names who took it")
    entry = _entry("retired", scope=scope, by=by, reason=reason,
                   approval=(current or {}).get("approval"),
                   candidate=(current or {}).get("candidate"),
                   manifest=(current or {}).get("manifest"),
                   partition=(current or {}).get("partition"), now=now)
    entry["labels"] = entry["labels"] + [ROLLBACK_SCOPE_LABEL]
    return entry


def validate_entry(entry, *, where="this pointer entry", key=None, re_derive=True):
    """Everything a stored generation must be, or `EvalError`. The WRITER's half; refuses.

    Closed in both directions on its keys, versioned, state-checked, and -- the half that is not
    shape -- `_unwired_dispatch` over a running state's gate block, read from
    `CONFINED_DISPATCH_WIRED` at call time. A `retired` or `rolled-back` entry carries no gate
    and needs none; a `canary` or `active` one needs a permitted gate AND a bundle reference
    that is a complete pointer at a policy bundle, through D20's own `_policy_ref`.

    `re_derive=False` is the READER's half and checks SHAPE only. The two are deliberately
    separable: "these bytes are not a pointer entry" and "this entry claims a permitted gate
    while this repository has no confining, ledgered dispatch path" are different facts about a
    store, and folding the second into the first would leave `runtime_activation` reporting
    `pointer-unreadable` for an entry it read perfectly well. The reader still refuses to
    RESOLVE such an entry -- `runtime_activation` runs the same `_unwired_dispatch` and answers
    legacy with `confining-dispatch-unwired`, which is the code that says why.
    """
    if not isinstance(entry, dict):
        raise EvalError(f"{where} is a {type(entry).__name__}, not a pointer entry")
    if entry.get("v") != ACTIVATION_VERSION:
        raise EvalError(f"{where} is a {entry.get('v')!r} document; this store holds "
                        f"{ACTIVATION_VERSION} entries and will not guess at another shape")
    unknown = sorted(set(entry) - set(ACTIVATION_ENTRY_KEYS))
    missing = sorted(set(ACTIVATION_ENTRY_KEYS) - set(entry))
    if unknown or missing:
        raise EvalError(
            f"{where} carries " + "; ".join(part for part in (
                f"unknown key(s) {', '.join(repr(k) for k in unknown)}" if unknown else "",
                f"no {', '.join(repr(k) for k in missing)}" if missing else "") if part)
            + f"; the keys are {', '.join(ACTIVATION_ENTRY_KEYS)}")
    state = entry["state"]
    if state not in ACTIVATION_STATES:
        raise EvalError(f"{where} is in state {state!r}; the states are "
                        f"{', '.join(ACTIVATION_STATES)}")
    if not entry.get("by"):
        raise EvalError(f"{where} names nobody who took it")
    derived = scope_key(entry["scope"])
    if entry["scope_key"] != derived:
        raise EvalError(f"{where} is filed under scope key {entry['scope_key']!r} and its own "
                        f"scope digests to {derived!r}; an entry cannot be filed under a scope "
                        f"it does not name")
    if key is not None and key != derived:
        raise EvalError(f"{where} names scope {derived!r} and is being written under {key!r}")
    if state in RUNNING_STATES:
        if re_derive:
            unwired = _unwired_dispatch(entry.get("gate"), where)
            if unwired:
                raise EvalError(unwired)
        elif not isinstance(entry.get("gate"), dict):
            raise EvalError(f"{where} is {state!r} and carries no gate verdict at all")
        _policy_ref(entry.get("bundle_ref"), "bundle")
        _eligibility(entry.get("eligibility"))
        _monitors(entry.get("monitors"))
    else:
        for field in ("gate", "bundle_ref", "eligibility", "monitors"):
            if entry.get(field) is not None:
                raise EvalError(
                    f"{where} is {state!r} and carries a {field}; a state that resolves every "
                    f"future run to legacy names no bundle, no gate and no cohort -- recording "
                    f"a fallback is what the `fallback` block is for")
    return entry


# ---- the pointer store: one generation per file, created once, never rewritten ------------------

_GENERATION_RE = re.compile(r"\Agen-(\d{6})\.json\Z")


def _generation_name(number):
    if not isinstance(number, int) or isinstance(number, bool) or number < 1 or number > 999999:
        raise EvalError(f"a pointer generation is a counting number below 1000000, not "
                        f"{number!r}")
    return f"gen-{number:06d}.json"


def _activation_rel(key, number):
    return f"{POLICY_ACTIVATION}/{key}/{_generation_name(number)}"


def activation_generations(prefs_dir, scope):
    """Every generation on disk for this scope -> `(sorted numbers, stray filenames)`.

    A name that is not a generation is REPORTED rather than ignored: a `.tmp` or a hand-made
    file in this directory is a fact about the store somebody should see, and a reader that
    silently skipped it would make the store look tidier than it is.
    """
    key = scope if isinstance(scope, str) else scope_key(scope)
    root = Path(prefs_dir) / POLICY_ACTIVATION / key
    if not root.is_dir():
        return [], []
    numbers, strays = [], []
    for path in sorted(root.iterdir()):
        match = _GENERATION_RE.match(path.name)
        if match and path.is_file():
            numbers.append(int(match.group(1)))
        else:
            strays.append(path.name)
    return sorted(numbers), strays


def read_activation(prefs_dir, scope):
    """The pointer in force for this scope -> a reading. A READER, and it fails CLOSED.

    Absent directory, absent file, unparseable bytes, a shape `validate_entry` refuses and a
    running state whose gate block `_unwired_dispatch` contradicts all come back with `entry`
    None and the reason named. None of them raises and none of them is an activation: whatever
    could not be read is legacy, which is the safe direction and also the true one.
    """
    key = scope if isinstance(scope, str) else scope_key(scope)
    numbers, strays = activation_generations(prefs_dir, key)
    out = {"scope_key": key, "generation": None, "entry": None, "unreadable": None,
           "generations": numbers, "strays": strays,
           "path": str(Path(prefs_dir) / POLICY_ACTIVATION / key)}
    if not numbers:
        return out
    latest = numbers[-1]
    out["generation"] = latest
    try:
        raw = _sp().confined_read_bytes(Path(prefs_dir), _activation_rel(key, latest),
                                        what="activation read")
        entry = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, EvalError) as exc:
        out["unreadable"] = f"generation {latest} could not be read: {exc}"
        return out
    try:
        out["entry"] = validate_entry(entry, where=f"generation {latest}", key=key,
                                      re_derive=False)
    except EvalError as exc:
        out["unreadable"] = str(exc)
    return out


def swap_activation(prefs_dir, scope, *, entry, expected):
    """Compare-and-swap one pointer generation into place -> the written entry.

    THE ONLY WRITER, and it is unlosable. `expected` is the generation the caller READ; this
    writes `expected + 1` (or generation 1 when `expected` is None, meaning "there was nothing"),
    with `safe_paths.confined_create_bytes`, whose `O_EXCL` makes "is this name free" and "write
    these bytes" one kernel operation. There is deliberately NO re-read of the directory before
    the create: a check followed by a write has a window, and this has none. A stale expectation
    therefore fails on the kernel's own answer -- the name it would write is already taken --
    and the loser writes nothing at all.

    It DECIDES nothing. `validate_entry` is what refuses a running entry the gate never
    permitted, and it re-derives `CONFINED_DISPATCH_WIRED` to do it.
    """
    key = scope if isinstance(scope, str) else scope_key(scope)
    if expected is not None and (not isinstance(expected, int) or isinstance(expected, bool)
                                 or expected < 1):
        raise EvalError(f"expected is the generation you read, or None when there was none; "
                        f"{expected!r} is neither")
    number = 1 if expected is None else expected + 1
    record = dict(entry, previous=expected)
    validate_entry(record, where=f"the entry offered for generation {number}", key=key)
    body = json.dumps(record, indent=2, sort_keys=True) + "\n"
    paths = _prefs_paths(prefs_dir)
    paths["dir"].mkdir(parents=True, exist_ok=True)
    sp = _sp()
    try:
        sp.confined_create_bytes(paths["dir"], _activation_rel(key, number), body.encode("utf-8"),
                                 what="activation swap")
    except sp.SafePathExists:
        raise ActivationConflict(
            f"generation {number} of activation scope {key} already exists: this swap expected "
            f"{expected!r} to still be the latest and it is not. Nothing was written. Re-read "
            f"the pointer and decide again over what is actually in force -- a lost update here "
            f"is a silent wrong-policy activation, which is why the create is O_EXCL and why "
            f"this refuses instead of retrying for you") from None
    except sp.SafePathError as exc:
        raise EvalError(f"the activation pointer could not be written: {exc}") from None
    _journal(paths, "policy.activation", scope=key, generation=number, previous=expected,
             state=record["state"], entry=record["id"], by=record["by"],
             bundle=(record.get("bundle_ref") or {}).get("id"))
    return record


def activation_history(prefs_dir, scope):
    """Every generation ever written for this scope, oldest first -> rows. A READER.

    The whole of it, whatever each one decided and whatever this reader can make of it: a
    generation that no longer parses is listed as unreadable rather than dropped, because a
    history with a hole in it is how a rollback comes to look like it never happened.
    """
    key = scope if isinstance(scope, str) else scope_key(scope)
    numbers, strays = activation_generations(prefs_dir, key)
    rows = []
    for number in numbers:
        try:
            raw = _sp().confined_read_bytes(Path(prefs_dir), _activation_rel(key, number),
                                            what="activation read")
            entry = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError, EvalError) as exc:
            rows.append({"generation": number, "state": "unreadable", "detail": str(exc)})
            continue
        rows.append({"generation": number, "state": entry.get("state"), "id": entry.get("id"),
                     "by": entry.get("by"), "at": entry.get("at"),
                     "previous": entry.get("previous"),
                     "bundle": (entry.get("bundle_ref") or {}).get("id"),
                     "approval": entry.get("approval"),
                     "fallback": ((entry.get("fallback") or {}).get("bundle_ref") or {}).get("id"),
                     "reason": entry.get("reason")})
    return {"scope_key": key, "generations": rows, "strays": strays,
            "labels": [ROLLBACK_SCOPE_LABEL, POINTER_NOT_AUTHORITY_LABEL]}


# ---- the read seam a run uses, once, at its start ------------------------------------------------

def _facts(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise EvalError(f"runtime facts are an object with {', '.join(RUNTIME_FACT_KEYS)}, not a "
                        f"{type(value).__name__}")
    missing = sorted(set(RUNTIME_FACT_KEYS) - set(value))
    unknown = sorted(set(value) - set(RUNTIME_FACT_KEYS))
    if missing or unknown:
        raise EvalError(f"runtime facts are exactly {', '.join(RUNTIME_FACT_KEYS)}; this carries "
                        + "; ".join(part for part in (
                            f"unknown {', '.join(repr(u) for u in unknown)}" if unknown else "",
                            f"no {', '.join(repr(m) for m in missing)}" if missing else "")
                            if part))
    runs = value["runs_so_far"]
    if not isinstance(runs, int) or isinstance(runs, bool) or runs < 0:
        raise EvalError(f"runs_so_far is a count of runs already started under this pointer, not "
                        f"{runs!r}")
    return dict(value)


def runtime_activation(prefs_dir, scope, *, facts=None):
    """What mode a run STARTING NOW takes for this scope, and the complete reason.

    ABSENT POINTER IS LEGACY. No directory, no generation, no store at all: legacy, with
    `no-pointer`, and it is not an error. So is an unreadable pointer, a retired one, a
    rolled-back one, one whose gate block contradicts `CONFINED_DISPATCH_WIRED`, and one whose
    declared eligibility this run falls outside. Every exit that is not a live running state is
    legacy and `reasons` says which.

    READ ONCE, BY THE RUN THAT IS STARTING. The value this returns is what a run carries for its
    whole life -- see `pin_for_run` and `bin/kit_contract.py`'s `start_task_lifecycle`. Nothing
    in this repository re-reads a pointer during a run, which is what "a run pins" means: a run
    that began under generation 4 keeps generation 4's bundle after generation 5 lands.

    `implemented_by_selection` is read from `decision_policy.SELECTION_MODES` at call time, and
    is False for every running state today: that module implements `legacy` and `shadow` and
    refuses `canary` and `active` by name. A pointer saying `canary` and a selection acting on
    one are two different facts and this keeps them apart.
    """
    reading = read_activation(prefs_dir, scope)
    dp = _dp()
    out = {"v": ACTIVATION_VERSION, "scope_key": reading["scope_key"], "mode": "legacy",
           "pin": None, "generation": reading["generation"], "entry": None, "reasons": [],
           "eligibility": None, "implemented_by_selection": True,
           "selection_modes": list(dp.SELECTION_MODES),
           "deferred_modes": list(dp.DEFERRED_MODES),
           "labels": [ABSENT_POINTER_IS_LEGACY_LABEL, POINTER_NOT_AUTHORITY_LABEL,
                      OLD_PREFERENCES_UNCHANGED_LABEL]}

    def legacy(reason):
        if reason not in RUNTIME_REASONS:  # pragma: no cover -- a closed vocabulary that is not
            raise EvalError(f"runtime reason {reason!r} is outside RUNTIME_REASONS")
        out["reasons"].append(reason)
        return out

    if reading["unreadable"]:
        out["detail"] = reading["unreadable"]
        return legacy("pointer-unreadable")
    entry = reading["entry"]
    if entry is None:
        return legacy("no-pointer")
    out["entry"] = entry
    if entry["state"] == "retired":
        return legacy("pointer-retired")
    if entry["state"] == "rolled-back":
        out["fallback"] = entry.get("fallback")
        return legacy("pointer-rolled-back")
    unwired = _unwired_dispatch(entry.get("gate"), f"generation {reading['generation']}")
    if unwired:
        out["detail"] = unwired
        return legacy("confining-dispatch-unwired")
    bounds = entry["eligibility"]
    out["eligibility"] = bounds
    checked = _facts(facts)
    if checked is None:
        return legacy("eligibility-unestablished")
    if checked["task_class"] not in bounds["task_classes"] or (
            bounds["cohort"] and checked["item"] not in bounds["cohort"]):
        return legacy("outside-eligible-cohort")
    if checked["runs_so_far"] >= bounds["max_runs"]:
        return legacy("eligibility-limit-reached")
    out["mode"] = entry["state"]
    out["pin"] = entry["bundle_ref"]
    out["implemented_by_selection"] = entry["state"] in dp.SELECTION_MODES
    out["reasons"].append("pinned")
    return out


def pin_for_run(activation):
    """The bundle reference a run carries for its whole life -> a reference or None.

    Taken ONCE, at the start, from `runtime_activation`'s answer, and then handed to
    `kit_contract.start_task_lifecycle(policy_ref=...)`, which gives it to `TaskRun`, which
    records it on every attempt through `attempt_ledger`'s existing provenance fields. There is
    no seam anywhere by which a run re-reads the pointer afterwards: `runtime_activation` is the
    only reader in this module and a run calls it once.

    None is the answer today and every day until something mints a pointer, and None is exactly
    what `TaskRun` already expects: a run that pins nothing records the field as unknown, which
    is what it is.
    """
    return None if activation is None else activation.get("pin")


def run_pin(activation):
    """The same pin in the shape `decision_policy.pinned_bundle` reads -> a pin or None.

    Two shapes because two consumers want different things and neither should have to reshape
    the other's: the ledger wants a REFERENCE, because that is what an attempt's provenance
    field holds; bundle resolution wants the reference plus which pointer generation and mode it
    came out of, because a resolution that could not say which generation it resolved would
    leave a later reader unable to tell a run that predates a swap from one that ignored it.

    None when nothing is in force, which resolves exactly as an unpinned run always has.
    """
    if activation is None or activation.get("pin") is None:
        return None
    return {"mode": activation["mode"], "generation": activation["generation"],
            "activation": (activation.get("entry") or {}).get("id"),
            "bundle_ref": activation["pin"]}


def activation_report(prefs_dir):
    """Every activation scope this prefs directory holds -> a report. A READER.

    Listed whatever each one says, unreadable generations included, for the reason
    `approval_report` lists a refusal beside a grant: the history that gets lost first is the
    part a later reviewer most needs.
    """
    root = Path(prefs_dir) / POLICY_ACTIVATION
    scopes = []
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            reading = read_activation(prefs_dir, child.name)
            entry = reading["entry"] or {}
            contradiction = (_unwired_dispatch(entry.get("gate"), f"generation "
                                               f"{reading['generation']}")
                             if entry.get("state") in RUNNING_STATES else None)
            scopes.append({"scope_key": child.name, "generation": reading["generation"],
                           "state": entry.get("state") or None,
                           "unreadable": reading["unreadable"],
                           "dispatch_contradiction": contradiction,
                           "strays": reading["strays"],
                           "generations": reading["generations"]})
    return {"v": ACTIVATION_VERSION, "path": str(root), "scopes": scopes,
            "states": list(ACTIVATION_STATES), "running_states": list(RUNNING_STATES),
            "blocker_vocabulary": list(ACTIVATION_BLOCKERS),
            "runtime_reasons": list(RUNTIME_REASONS),
            "confined_dispatch_wired": bool(CONFINED_DISPATCH_WIRED),
            "unproven": list(ACTIVATION_UNPROVEN),
            "labels": [ACTIVATION_REFUSED_TODAY_LABEL, ABSENT_POINTER_IS_LEGACY_LABEL,
                       POINTER_NOT_AUTHORITY_LABEL, ROLLBACK_SCOPE_LABEL,
                       OLD_PREFERENCES_UNCHANGED_LABEL]}

# END OF THE PROTECTED ACTIVATION SECTION (decision-improvement D23)




# ---- CLI --------------------------------------------------------------------------------------------------------

def _split(raw):
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


def _read_instructions(paths):
    out = []
    for p in paths or ():
        text = Path(p).read_text()
        out.append((Path(p).stem, text))
    return out or None


def _plan_from_args(args, scratch_dir, tasks_out=None, adapter=None):
    return build_plan(
        args.repo, args.harness, _split(args.models), workflows=_split(args.workflows) or ("direct",),
        policies=_split(args.policies) or ("pinned",), repeats=args.repeats, mode=args.mode,
        limit=args.limit, test_cmd=args.test_cmd, commit=args.commit, scratch_dir=scratch_dir,
        exclude_subject=tuple(args.exclude_subject or ()), adapter=adapter, tasks_out=tasks_out,
        instructions=_read_instructions(getattr(args, "instructions", None)),
        review_model=getattr(args, "review_model", None), timeout=args.timeout,
    )


def cmd_plan(args):
    with tempfile.TemporaryDirectory(prefix="workflow-eval-plan-") as tmp:
        card = _plan_from_args(args, Path(tmp) / "work")
    print(json.dumps(card, indent=2) if args.json else render_plan_markdown(card))
    return 0


def cmd_run(args, runner=None, adapter=None, git_runner=None, test_runner=None):
    rb = _rb()
    store_dir = Path(args.store_dir) if args.store_dir else DEFAULT_STORE_DIR
    try:
        max_usd = rb.validate_ceiling(args.max_usd)
    except ValueError as exc:
        print(f"refusing to dispatch: {exc}", file=sys.stderr)
        return 2
    adapter = adapter or make_adapter(args.harness)
    tasks = []
    with tempfile.TemporaryDirectory(prefix="workflow-eval-mine-") as tmp:
        plan = _plan_from_args(args, Path(tmp) / "work", tasks_out=tasks, adapter=adapter)
        instructions = _read_instructions(getattr(args, "instructions", None))
        plan["_variants_full"] = build_variants(args.harness, plan["candidates"], plan["workflows"],
                                                plan["policies"], instructions=instructions,
                                                review_model=getattr(args, "review_model", None))
        if not (args.live and max_usd is not None):
            print(render_plan_markdown(plan))
            print("refusing to dispatch: run requires --live AND --max-usd <ceiling>", file=sys.stderr)
            return 2
        est = plan["totals"]["estimated"]["usd"] + plan["totals"]["model-reported"]["usd"]
        if est > max_usd:
            print(render_plan_markdown(plan))
            print(f"planned priced estimate ${est:.4f} exceeds --max-usd ${max_usd:.4f} -- raise the "
                  f"ceiling or shrink the matrix", file=sys.stderr)
            return 2
        cap = args.max_dispatches if args.max_dispatches is not None else plan["caps"]["max_dispatches"]
        if cap < 1:
            print("refusing to dispatch: --max-dispatches must be at least 1", file=sys.stderr)
            return 2
        print(render_plan_markdown(plan))
        print("")
        ev = Evaluation(plan, tasks, adapter, store_dir=store_dir, runner=runner, git_runner=git_runner,
                        test_runner=test_runner, binary=args.bin, max_usd=max_usd, max_dispatches=cap,
                        exec_mode=args.exec_mode, keep_work=args.keep_work, timeout=args.timeout)
        envelope = ev.run()
    card = build_card(envelope)
    print(render_card_markdown(card))
    print(f"results.json: {ev.run_dir / 'results.json'}")
    return 0


def cmd_card(args):
    store_dir = Path(args.store_dir) if args.store_dir else DEFAULT_STORE_DIR
    env = read_envelope(store_dir, args.run)
    card = build_card(env)
    if args.history:
        records, summary = history_records(store_dir, args.run)
        card["history"] = {"records": len(records), "by_harness": summary["by_harness"],
                           "unknown": summary["unknown"], "cost": summary["cost"]}
    if args.json:
        print(json.dumps(card, indent=2))
    else:
        print(render_card_markdown(card))
        if args.history:
            print("")
            print(f"## attempt history ({card['history']['records']} record(s), joined through "
                  f"attempt_history with tiers from model_registry)")
            print(f"  by harness: {card['history']['by_harness']}")
            print(f"  unknown: {card['history']['unknown']}")
            print(f"  cost: {card['history']['cost']['by_basis']}")
    return 0


def cmd_adjudicate(args):
    store_dir = Path(args.store_dir) if args.store_dir else DEFAULT_STORE_DIR
    entry = adjudicate(store_dir, args.run, args.trial, args.by, args.verdict, note=args.note or "")
    print(f"recorded adjudication on {args.run}/{args.trial}: {entry['verdict']} by {entry['by']} "
          f"(solved is unchanged; the card counts this as an intervention)")
    return 0


def cmd_list(args):
    store_dir = Path(args.store_dir) if args.store_dir else DEFAULT_STORE_DIR
    rows, notes = list_runs(store_dir)
    if args.json:
        print(json.dumps({"runs": rows, "notes": notes}, indent=2))
        return 0
    print(f"evals store: {store_dir}")
    for r in rows:
        spend = "-" if r["spent_usd"] is None else f"${r['spent_usd']:.4f}"
        print(f"  {r['run_id']}  {r['harness']}  {r['trials']} trial(s)  {spend}  {r['repo']}")
    for n in notes:
        print(f"  note: {n}")
    return 0


def cmd_propose(args):
    store_dir = Path(args.store_dir) if args.store_dir else DEFAULT_STORE_DIR
    prefs_dir = Path(args.prefs_dir) if args.prefs_dir else DEFAULT_PREFS_DIR
    env = read_envelope(store_dir, args.run)
    change = {}
    for item in args.set or ():
        if "=" not in item:
            raise EvalError(f"--set expects key=value, got {item!r}")
        k, v = item.split("=", 1)
        change[k.strip()] = v.strip()
    # `read_manifest` re-derives the manifest's digest and refuses a rewritten file, so the
    # reference recorded below is taken from a manifest this command actually opened and
    # checked. It is still only a pointer once it is on the record.
    cited = manifest_ref(read_manifest(store_dir, args.manifest)) if args.manifest else None
    proposal = build_proposal(env, change, args.by, prefs_dir, task_class=args.task_class,
                              manifest_ref=cited)
    path = write_proposal(prefs_dir, proposal)
    print(f"proposal {proposal['id']} written to {path}")
    print(f"  change: {proposal['change']}")
    print(f"  refs: bundle={_ref_ids(proposal)['bundle']} manifest={_ref_ids(proposal)['manifest']}")
    print(f"  evidence: {proposal['evidence']['supporting_variant']} n={proposal['evidence']['n']} "
          f"rate={proposal['evidence']['rate']} interval={proposal['evidence']['interval_95']} "
          f"stability={proposal['evidence']['stability']}")
    print(f"  base: {proposal['base']}; next: review --proposal {proposal['id']} --by <name> "
          f"--decision accept|reject, then apply")
    return 0


def cmd_review(args):
    prefs_dir = Path(args.prefs_dir) if args.prefs_dir else DEFAULT_PREFS_DIR
    proposal = review_proposal(prefs_dir, args.proposal, args.by, args.decision, note=args.note or "")
    print(f"proposal {args.proposal}: {proposal['status']} (reviewed by {args.by})")
    return 0


def cmd_apply(args):
    prefs_dir = Path(args.prefs_dir) if args.prefs_dir else DEFAULT_PREFS_DIR
    new, old = apply_proposal(prefs_dir, args.proposal)
    print(f"applied proposal {args.proposal}: routing policy v{new['version']} "
          f"(previous: {'none' if old is None else 'v' + str(old.get('version'))}, kept in history)")
    print(f"  defaults: {new['defaults']}; by_task_class: {new['by_task_class']}")
    print(f"  {new['consumption']}")
    return 0


def cmd_rollback(args):
    prefs_dir = Path(args.prefs_dir) if args.prefs_dir else DEFAULT_PREFS_DIR
    restored, previous = rollback_policy(prefs_dir, to_version=args.to)
    print(f"rolled back: v{previous.get('version')} -> v{restored.get('version')} "
          f"(v{previous.get('version')} kept in history)")
    return 0


def cmd_approve(args):
    """Decide one approval over a case file, and write the record whatever it decides.

    The manifest and the run are read from the store HERE, so this path re-derives the
    manifest's digest off disk before anything is bound to it. It still writes no pointer and
    activates nothing: `write_approval` appends to the prefs store and that is the end of it.
    """
    store_dir = Path(args.store_dir) if args.store_dir else DEFAULT_STORE_DIR
    prefs_dir = Path(args.prefs_dir) if args.prefs_dir else DEFAULT_PREFS_DIR
    document = json.loads(Path(args.case).read_text(encoding="utf-8"))
    case = load_approval_case(document, store_dir)
    scope = json.loads(Path(args.scope).read_text(encoding="utf-8")) if args.scope else None
    record = decide_approval(case, by=args.by, scope=scope, decision=args.decision,
                             note=args.note or "")
    path = write_approval(prefs_dir, record)
    print(f"approval {record['id']}: {record['state']} (from {record['from_state']}, "
          f"granted={record['granted']}) -> {path}")
    for slot in APPROVAL_BINDINGS:
        row = record["bindings"][slot]
        print(f"  bound {slot}: {str(row['hash'])[:16] if row['hash'] else '(unbound)'} "
              f"re-derived by {row['re_derived_by']}")
    for row in record["refusals"]:
        print(f"  refused {row['reason']}: {row['detail']}")
    print(f"  authority: {record['authority']}; unproven: {', '.join(record['unproven'])}")
    print(f"  {APPROVAL_NOT_ACTIVATION_LABEL}")
    return 0 if record["granted"] else 3


def cmd_approvals(args):
    prefs_dir = Path(args.prefs_dir) if args.prefs_dir else DEFAULT_PREFS_DIR
    report = approval_report(prefs_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    print(f"approvals: {report['path']}")
    for row in report["approvals"]:
        print(f"  {row['id']}: {row['state']} granted={row.get('granted')} "
              f"candidate={row.get('candidate')} by={row.get('by')} "
              f"refused={','.join(row.get('refusals') or ()) or '-'}")
    print(f"  {report['authority']}")
    for label in report["labels"]:
        print(f"  -- {label}")
    return 0


def cmd_activation(args):
    """READ-ONLY. There is deliberately no command that activates anything.

    `activation_decision` refuses today whatever it is handed, so a command that offered to take
    the transition would offer something that cannot happen; and if one day it can happen, the
    edit that wires it should have to add the command in the same change. What this prints is
    what a run starting now would resolve to, and the history of how a scope got there.
    """
    prefs_dir = Path(args.prefs_dir) if args.prefs_dir else DEFAULT_PREFS_DIR
    report = activation_report(prefs_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    print(f"activation pointers: {report['path']}")
    print(f"  confining, ledgered dispatch wired: {report['confined_dispatch_wired']}")
    if not report["scopes"]:
        print("  (no pointer for any scope -- every run resolves to legacy)")
    for row in report["scopes"]:
        print(f"  {row['scope_key']}: generation={row['generation']} state={row['state']}"
              f"{' UNREADABLE: ' + row['unreadable'] if row['unreadable'] else ''}")
        if row["strays"]:
            print(f"    strays: {', '.join(row['strays'])}")
    for code in report["unproven"]:
        print(f"  unproven -- {code}: {ACTIVATION_UNPROVEN_NOTES[code]}")
    for label in report["labels"]:
        print(f"  -- {label}")
    return 0


def cmd_policy(args):
    prefs_dir = Path(args.prefs_dir) if args.prefs_dir else DEFAULT_PREFS_DIR
    report = policy_report(prefs_dir)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"routing policy: {report['path']} ({report['consumption']})")
    pol = report["policy"]
    print(f"  in force: {'none' if not pol else 'v%s %s by_task_class=%s' % (pol.get('version'), pol.get('defaults'), pol.get('by_task_class'))}")
    print(f"  history: {', '.join('v%d' % v for v in report['history_versions']) or '(none)'}")
    refs = report["refs"]
    print(f"  refs: bundle={(refs['bundle'] or {}).get('id')} "
          f"manifest={(refs['manifest'] or {}).get('id')}"
          f"{'' if refs['recorded'] else ' (this policy predates the reference block)'}"
          f"{' unreadable=' + ','.join(refs['unreadable']) if refs['unreadable'] else ''}")
    print(f"  {report['review_authority']}")
    for p in report["proposals"]:
        print(f"  proposal {p['id']}: {p['status']} run={p.get('run')} change={p.get('change')}"
              f" decisions={p.get('decisions')}")
    return 0


# ---- demo ---------------------------------------------------------------------------------------------------

_DEMO_STUB = """#!/bin/sh
# argv: --task ID --model M --workspace DIR [--mode ask] PROMPT
mode=write
for a in "$@"; do [ "$a" = "ask" ] && mode=ask; done
prompt=$(eval "echo \\"\\$$#\\"")
if [ "$mode" = "ask" ]; then
  case "$prompt" in *"+    return 2"*) echo "REVIEW VERDICT=accept";; *) echo "REVIEW VERDICT=reject";; esac
  exit 0
fi
case "$4" in
  fixer)  printf 'def f():\\n    return 2\\n' > m.py ;;
  idler)  : ;;
esac
echo '{"type":"result","subtype":"success"}'
exit 0
"""


def _demo_repo(root, git):
    root.mkdir(parents=True)
    git(root, "init", "-q")
    (root / "m.py").write_text("def f():\n    return 1\n")
    (root / "run_tests.py").write_text(
        "import os, runpy\nif os.path.exists('tests/test_m.py'):\n    runpy.run_path('tests/test_m.py')\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "start")
    (root / "m.py").write_text("def f():\n    return 2\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_m.py").write_text("import m\nassert m.f() == 2\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixes #1: f() should return 2")


def _demo(out=None):
    pr = _pr()

    def git(repo, *args):
        r = pr.run(["git", "-C", str(repo), "-c", "user.name=demo", "-c", "user.email=demo@example.com",
                    "-c", "init.defaultBranch=demo", "-c", "commit.gpgsign=false", *args],
                   cwd=str(repo), timeout=60, name="demo git")
        if r.get("rc") != 0:
            raise EvalError(f"demo fixture git {args} failed: {r.get('output', '')[-300:]}")

    def test_runner(cmd, cwd):
        r = pr.run([sys.executable, "run_tests.py"], cwd=str(cwd), timeout=60, name="demo tests")
        return r.get("rc"), (r.get("stdout") or "") + (r.get("stderr") or "")

    out = out or sys.stdout
    with tempfile.TemporaryDirectory(prefix="workflow-eval-demo-") as tmp:
        tmp = Path(tmp)
        repo = tmp / "target"
        _demo_repo(repo, git)
        stub = tmp / "stub"
        stub.write_text(_DEMO_STUB)
        stub.chmod(0o755)
        adapter = stub_adapter()
        tasks = []
        plan = build_plan(repo, "stub", ["fixer", "idler"], workflows=("direct", "reviewed", "kit"),
                          policies=("pinned",), repeats=2, mode="issue-replay",
                          test_cmd=f"{sys.executable} run_tests.py", scratch_dir=tmp / "work",
                          adapter=adapter, tasks_out=tasks, test_runner=test_runner)
        plan["_variants_full"] = build_variants("stub", plan["candidates"], plan["workflows"], plan["policies"])
        print("== the plan (nothing dispatched) ==", file=out)
        print(render_plan_markdown(plan), file=out)
        print("", file=out)
        def runner(argv, cwd):
            r = pr.run(argv, cwd=cwd, timeout=60, name="demo stub")
            return r.get("rc"), (r.get("stdout") or "") + (r.get("stderr") or ""), r

        ev = Evaluation(plan, tasks, adapter, store_dir=tmp / "store", runner=runner, test_runner=test_runner,
                        binary=str(stub), max_usd=1.0, exec_mode="trusted-host", out=out)
        env = ev.run()
        card = build_card(env)
        print("== the card ==", file=out)
        print(render_card_markdown(card), file=out)
        print("", file=out)
        by = {s["variant"]: s for s in card["variants"]}
        print("== what it shows ==", file=out)
        print(f"  fixer solves through every workflow: "
              + ", ".join(f"{v}={by[v]['solved']}/{by[v]['n']}" for v in by if ':fixer' in v), file=out)
        print(f"  idler changes nothing: the kit workflow ACCEPTS it (the repository's own tests still pass) "
              f"while the oracle fails it -- incorrect acceptance "
              f"{by['stub/kit/pinned:idler']['incorrect_acceptance']}/{by['stub/kit/pinned:idler']['acceptances']}; "
              f"the reviewer's incorrect acceptances: {by['stub/reviewed/pinned:idler']['incorrect_acceptance']}", file=out)
        print(f"  every variant is below the evidence floor ({card['evidence_floor']}), so: {card['ranking'] or NOT_A_RANKING}", file=out)
        records, summary = history_records(tmp / "store", env["run_id"])
        print(f"  attempt history: {len(records)} dispatch record(s) across "
              f"{list(summary['by_harness'])}; cost bases {summary['cost']['by_basis']['estimated']['n']} est., "
              f"{summary['unknown']['cost']} unknown (the stub is unpriced)", file=out)
        ref = (env["holdout"] or {}).get("manifest_ref") or {}
        summary = (env["holdout"] or {}).get("manifest") or {}
        manifest = read_manifest(ev.run_dir, ref["id"])
        state = exposure_state(ev.run_dir, manifest)
        print(f"  manifest {ref['id']}: {summary['items']} item(s) in {summary['groups']} defect "
              f"group(s); partitions "
              f"{', '.join(f'{k}={v}' for k, v in summary['partitions'].items() if v)}; "
              f"exposure entries {state['entries']}", file=out)
        for kind, count in (summary.get("leaks") or {}).items():
            print(f"  quarantined by kind: {kind}={count} (this fixture's statement IS its fix "
                  f"commit message, which is a future fix message by construction)", file=out)
        try:
            declare_cohort(ev.run_dir, manifest, partition="promotion", cohort="after-the-fact",
                           items=sorted(manifest["content"]["partitions"]["promotion"]) or
                           sorted(manifest["content"]["items"]), by="demo")
        except EvalError as exc:
            print(f"  cohort refused: {exc}", file=out)
        print(f"  hashes are identity, not enforcement: {NOT_ENFORCEMENT_LABEL}", file=out)
        prefs = tmp / "prefs"
        try:
            build_proposal(env, {"workflow": "kit"}, "demo", prefs)
        except EvalError as exc:
            print(f"  propose refused: {exc}", file=out)
        print(f"  nothing dispatched a model, nothing left the temp dir {tmp}", file=out)
    return 0


def cmd_demo(args):
    return _demo()


def build_parser():
    ap = argparse.ArgumentParser(prog="workflow_eval.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command")

    def matrix_args(p):
        p.add_argument("--repo", required=True)
        p.add_argument("--harness", required=True, choices=HARNESSES)
        p.add_argument("--models", default="", help="comma-separated ids or tier words (pinned policy)")
        p.add_argument("--workflows", default="direct", help=f"comma-separated: {', '.join(WORKFLOWS)}")
        p.add_argument("--policies", default="pinned", help=f"comma-separated: {', '.join(POLICIES)}")
        p.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
        p.add_argument("--mode", default="auto", choices=("auto", "issue-replay", "general"))
        p.add_argument("--limit", type=int, default=8)
        p.add_argument("--test-cmd", default=None)
        p.add_argument("--commit", default=None)
        p.add_argument("--exclude-subject", action="append", default=None)
        p.add_argument("--instructions", action="append", default=None,
                       help="an instruction file; repeat to compare instruction versions")
        p.add_argument("--review-model", default=None)
        p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)

    p = sub.add_parser("plan", help="mine, enumerate, price; dispatch nothing")
    matrix_args(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("run", help="dispatch the plan (requires --live AND --max-usd)")
    matrix_args(p)
    p.add_argument("--store-dir", default=None)
    p.add_argument("--live", action="store_true")
    p.add_argument("--max-usd", type=float, default=None)
    p.add_argument("--max-dispatches", type=int, default=None, help="hard cap (default: the plan's count)")
    p.add_argument("--bin", default=None, help="the harness binary (a stub in any test)")
    p.add_argument("--exec-mode", default="enforced", choices=("enforced", "trusted-host"))
    p.add_argument("--keep-work", action="store_true")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("card", help="render a run's card")
    p.add_argument("--run", required=True)
    p.add_argument("--store-dir", default=None)
    p.add_argument("--history", action="store_true", help="join the attempt history")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_card)

    p = sub.add_parser("adjudicate", help="record a person's verdict on one trial")
    p.add_argument("--run", required=True)
    p.add_argument("--trial", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--verdict", required=True, choices=ADJUDICATIONS)
    p.add_argument("--note", default="")
    p.add_argument("--store-dir", default=None)
    p.set_defaults(func=cmd_adjudicate)

    p = sub.add_parser("list", help="runs in the evals store")
    p.add_argument("--store-dir", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("propose", help="a routing-default proposal from one run's evidence")
    p.add_argument("--run", required=True)
    p.add_argument("--set", action="append", default=None, help="workflow=W or policy=P; repeatable")
    p.add_argument("--task-class", default=None, help="scope the change to one task class")
    p.add_argument("--manifest", default=None,
                   help="an evaluation manifest id in the store; records a reference to it on "
                        "the proposal (the manifest is read and re-digested first)")
    p.add_argument("--by", required=True)
    p.add_argument("--store-dir", default=None)
    p.add_argument("--prefs-dir", default=None)
    p.set_defaults(func=cmd_propose)

    p = sub.add_parser("review", help="a person's decision on a proposal")
    p.add_argument("--proposal", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--decision", required=True, choices=("accept", "reject"))
    p.add_argument("--note", default="")
    p.add_argument("--prefs-dir", default=None)
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("apply", help="write the next policy version from an accepted proposal")
    p.add_argument("--proposal", required=True)
    p.add_argument("--prefs-dir", default=None)
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("rollback", help="restore an earlier policy version")
    p.add_argument("--to", type=int, default=None)
    p.add_argument("--prefs-dir", default=None)
    p.set_defaults(func=cmd_rollback)

    p = sub.add_parser("approve", help="bind a decision to the exact candidate, manifest, "
                                       "partition and run it was taken over")
    p.add_argument("--case", required=True,
                   help=f"a JSON case file; the keys are {', '.join(APPROVAL_CASE_KEYS)}")
    p.add_argument("--by", required=True)
    p.add_argument("--decision", required=True, choices=("accept", "reject"))
    p.add_argument("--scope", default=None,
                   help="a JSON file with the scope this approval covers; required to accept")
    p.add_argument("--note", default="")
    p.add_argument("--store-dir", default=None)
    p.add_argument("--prefs-dir", default=None)
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("approvals", help="every approval record, granted or refused")
    p.add_argument("--prefs-dir", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_approvals)

    p = sub.add_parser("activation",
                       help="read-only: what mode a run starting now resolves to, per scope")
    p.add_argument("--prefs-dir", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_activation)

    p = sub.add_parser("policy", help="the policy in force, its history, and proposals")
    p.add_argument("--prefs-dir", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_policy)

    p = sub.add_parser("demo", help="offline: a stub harness, three workflows, two repeats; spends nothing")
    p.set_defaults(func=cmd_demo)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 2
    try:
        return args.func(args) or 0
    except (EvalError, FileNotFoundError, KeyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
