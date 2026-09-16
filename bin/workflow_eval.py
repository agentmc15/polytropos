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


class Evaluation:
    """One run: every trial through its workflow, graded by the same oracle, recorded."""

    def __init__(self, plan, tasks, adapter, *, store_dir, runner=None, git_runner=None,
                 test_runner=None, binary=None, max_usd=None, max_dispatches=None,
                 exec_mode="enforced", keep_work=False, out=None, err=None, pricing=None,
                 timeout=DEFAULT_TIMEOUT_SECONDS, verify_factory=None):
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
               "skipped": None, "wall_seconds": 0.0, "adjudication": None,
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
            rec["wall_seconds"] += stage.get("wall_seconds") or 0.0
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
                    rec["wall_seconds"] += review.get("wall_seconds") or 0.0
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
        stage = {"stage": "implement", "model": model, "skipped": None, "wall_seconds": 0.0,
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
                "holdout": {"tasks": sorted(self.tasks), "reserved_from": "routing tuning"},
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
    wall = 0.0
    interventions = 0
    robustness = {k: 0 for k in ROBUSTNESS}
    for r in recs:
        for st in r.get("stages") or []:
            if st.get("cost"):
                add_cost(totals, st["cost"])
        wall += r.get("wall_seconds") or 0.0
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
        "interventions": interventions, "wall_seconds": round(wall, 3),
        "mean_wall_seconds": round(wall / n, 3) if n else None, "usage": totals,
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
        ranking = [s["variant"] for s in sorted(summaries, key=lambda s: (-(s["rate"] or 0),
                                                                          s["incorrect_acceptance"],
                                                                          s["wall_seconds"]))]
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

def _prefs_paths(prefs_dir):
    prefs_dir = Path(prefs_dir)
    return {"dir": prefs_dir, "policy": prefs_dir / POLICY_FILE, "history": prefs_dir / POLICY_HISTORY,
            "proposals": prefs_dir / POLICY_PROPOSALS, "journal": prefs_dir / POLICY_JOURNAL}


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


def build_proposal(envelope, change, by, prefs_dir, task_class=None):
    """A proposal from one run's evidence -> dict, or EvalError when the evidence is not
    defensible: the named variant is absent, below the evidence floor, a single repeat, or the
    run's tasks already backed the policy in force (evaluation tasks stay reserved)."""
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
             by=proposal["proposed_by"], change=proposal["change"])
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
    entry = {"by": by, "decision": decision, "note": _rd().redact(note or "")["text"], "at": _now()}
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
           "labels": list(proposal["evidence"]["labels"])}
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
             previous=(current or {}).get("version"))
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
    _journal(paths, "policy.rolled-back", from_version=current.get("version"), to_version=target)
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
                proposals.append({"id": d.get("id"), "status": d.get("status"), "run": d.get("source_run"),
                                  "change": d.get("change")})
            except (OSError, ValueError):
                proposals.append({"id": p.stem, "status": "unreadable"})
    return {"policy": current, "history_versions": versions, "proposals": proposals,
            "path": str(paths["policy"]), "consumption": "pull-only"}


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
    proposal = build_proposal(env, change, args.by, prefs_dir, task_class=args.task_class)
    path = write_proposal(prefs_dir, proposal)
    print(f"proposal {proposal['id']} written to {path}")
    print(f"  change: {proposal['change']}")
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
    for p in report["proposals"]:
        print(f"  proposal {p['id']}: {p['status']} run={p.get('run')} change={p.get('change')}")
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
