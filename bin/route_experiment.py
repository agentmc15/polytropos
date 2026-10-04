#!/usr/bin/env python3
"""Which Copilot route is best? A preregistered, paired experiment over whole routes.

    route_experiment.py validate [--exec-mode M]                  oracles red on base, green on reference
    route_experiment.py plan     [--repeats N] [--json]           trial matrix + AIC estimate; spends nothing
    route_experiment.py run      --dry-run                        print every dispatch argv; spawns nothing
    route_experiment.py run      --live --max-aic N [--run-id ID] [--only T1-A1-r1,..] [--bin PATH]
    route_experiment.py grade    --run ID [--only ..] [--full-regression]      offline re-grade
    route_experiment.py judge    --run ID (--dry-run | --live --max-aic N)     blind cross-vendor judges
    route_experiment.py rescan   --run ID [--only ..]             re-classify contamination from session logs
    route_experiment.py report   --run ID [--json]                scorecard + the preregistered decision
    route_experiment.py list
    route_experiment.py demo                                      stub CLI, fixture repo, whole pipeline

WHAT IS COMPARED. Routes, not models: each arm in `experiments/route-arms/experiment.json` is a
complete way of getting one task done -- a planner -> test-author -> implementer -> verifier ->
reviewer PIPELINE with bounded rework, or a single ONE-SHOT dispatch. Every trial starts from the
same pinned `base_commit`, extracted history-free by `repo_bench.make_sandbox`, so a trial can
neither see nor disturb the user's working tree (rollback = the sandbox is discarded). Repeats
are counterbalanced: the arm order rotates per task and repeat.

WHAT IS MEASURED, per trial. COST: every dispatch's AIC, token-priced from that session's own
`session.shutdown` `modelMetrics` (the session id is set by us, so attribution is exact), with
Copilot's reported AIU beside it as a cross-check and never summed with it; tokens by kind,
premium requests, wall-clock, dispatch count. CORRECTNESS: a HIDDEN oracle test file per task
(never in the candidate's tree; copied into a separate grading sandbox afterwards), plus the
task's regression modules (or the full suite with `--full-regression`). TEST STRENGTH: the
candidate's own tests run against AST mutants of the functions it changed; only mutants the
oracle also kills count, so an equivalent mutant cannot depress the score. COMPLEXITY: McCabe
and cognitive complexity, nesting, SLOC, Halstead volume and maintainability index, before and
after, and against the task's reference solution. DISCIPLINE: out-of-scope files, task
guardrails (`subprocess`, hardcoded model ids ...), writes by read-only stages, new unused
imports. QUALITY: two blind judges from different vendors score all arms' diffs for one task and
repeat side by side under shuffled labels. PIPELINE-ONLY: verifier/reviewer verdict accuracy
against the oracle (an INCORRECT ACCEPTANCE is a verdict of pass/accept on a failing oracle).

THE DECISION RULE is data (`scoring` in experiment.json) and is fixed before a live trial
exists; `run` pins its digest and refuses to resume under a changed definition. An arm added
afterwards lives in `extensions/`, joins a run only on `--extend-arms` (recorded in run.json),
is never judged, and is ranked in a separate post-hoc view, never in the preregistered one. See
docs/ROUTE-EXPERIMENT.md for every weight and threat to validity.

MONEY. Nothing spends by default. `run` and `judge` dispatch only behind BOTH `--live` and an
explicit `--max-aic`; the ceiling is re-checked before every dispatch against the MEASURED
spend so far plus a profile estimate of the next one. A dispatch whose session log cannot be
read is charged at its estimate and labelled unmeasured -- never as zero. A ceiling stops the
NEXT dispatch; it is not a provider-side guarantee. Model ids, efforts and prices are data:
arms are validated against `data/pricing.copilot.json` and every figure is derived from it.

HERMETIC DISPATCH. Each dispatch sets its own `--session-id`, excludes subagent/skill delegation,
cross-session history, memory writes and web tools, and read-only stages deny the write tool.
After each dispatch its session log is scanned (read-only, JSONL only) for the experiment's
own paths and for nested CLI launches; a hit marks the trial CONTAMINATED and excludes it.
"""

import argparse
import ast
import hashlib
import importlib.util
import io
import json
import keyword
import math
import os
import random
import re
import shlex
import shutil
import statistics
import sys
import tempfile
import time
import tokenize
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT_DIR = REPO_ROOT / "experiments" / "route-arms"
PRICING_PATH = REPO_ROOT / "data" / "pricing.copilot.json"
EXPERIMENT_VERSION = "polytropos.route-experiment/1"
RESULT_VERSION = "polytropos.route-experiment.result/1"
EXTENSION_VERSION = "polytropos.route-experiment.extension/1"
STORE_NAME = "routeruns"

PIPELINE_ROLES = ("planner", "test_author", "implementer", "verifier", "reviewer")
ONE_SHOT_ROLES = ("solo",)
# A pipeline may omit its reviewer gate; a `reviewed` arm is a one-shot followed by a reviewer
# gate whose findings get the solo model's rework rounds.
SHAPE_ROLES = {"pipeline": (PIPELINE_ROLES, ("reviewer",)),
               "one-shot": (ONE_SHOT_ROLES, ()),
               "reviewed": (("solo", "reviewer"), ())}
READ_ONLY_ROLES = frozenset({"planner", "verifier", "reviewer", "judge"})
LEDGER_OPS = {"planner": "consult", "test_author": "initial", "implementer": "initial",
              "rework": "retry", "verifier": "review", "reviewer": "review", "solo": "initial",
              "judge": "review"}
WEIGHT_KEYS = ("correctness", "quality", "test_strength", "simplicity", "discipline")

ORACLE_TEST_NAME = "test_route_oracle.py"
VERIFY_RE = re.compile(r"VERIFY\s+VERDICT\s*=\s*(pass|fail)", re.IGNORECASE)
REVIEW_RE = re.compile(r"REVIEW\s+VERDICT\s*=\s*(accept|reject)", re.IGNORECASE)
NESTED_DISPATCHERS = ("copilot_execute.py", "copilot_ralph.py")
SHELL_WRAPPERS = ("env", "exec", "nohup", "time", "command", "sudo", "timeout", "gtimeout")
SHELL_SPLIT_RE = re.compile(r"&&|\|\||[;|&\n]|\$\(|`")
RAN_RE = re.compile(r"^Ran (\d+) tests? in", re.MULTILINE)
FAILED_RE = re.compile(r"^FAILED \(([^)]*)\)", re.MULTILINE)

PROMPT_PATCH_CHARS = 20000
JUDGE_PATCH_CHARS = 12000
FINDINGS_CHARS = 6000
PLAN_CHARS = 12000
OUTPUT_KEEP_CHARS = 16000
TEST_TIMEOUT_SECONDS = 300
LABELS = "WXYZVUTS"
SIMPLICITY_BASES = ("reference", "median")
QUALITY_MODES = ("overall", "rubric_rank")

_SIBLINGS = {}


class ConfigError(ValueError):
    """The experiment definition is not runnable as written."""


def _sibling(name):
    if name not in _SIBLINGS:
        path = Path(__file__).resolve().with_name(f"{name}.py")
        spec = importlib.util.spec_from_file_location(f"polytropos_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLINGS[name] = module
    return _SIBLINGS[name]


def _pr():
    return _sibling("proc_runner")


def _al():
    return _sibling("attempt_ledger")


def _sp():
    return _sibling("safe_paths")


def _rd():
    return _sibling("runtime_data")


def _rb():
    return _sibling("repo_bench")


def _ep():
    return _sibling("exec_policy")


def _cu():
    return _sibling("copilot_usage")


def _cp():
    return _sibling("copilot_pricing")


def _kc():
    return _sibling("kit_contract")


def _redact():
    return _sibling("redact")


def sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------------------------
# The experiment definition (data, validated against the pricing file)


def load_pricing(path=PRICING_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def effort_values(pricing):
    """The CLI's effort tokens, derived from the pricing file's display ladder."""
    ladder = (pricing.get("knobs") or {}).get("reasoning_efforts") or []
    return [re.sub(r"^extra\s+", "x", str(level).strip().lower()) for level in ladder]


def _require(cond, message):
    if not cond:
        raise ConfigError(message)


def validate_definition(exp, pricing):
    """Raise ConfigError unless every arm and judge names an active model and a known effort."""
    _require(exp.get("version") == EXPERIMENT_VERSION,
             f"experiment version must be {EXPERIMENT_VERSION!r}, got {exp.get('version')!r}")
    _require(re.fullmatch(r"[0-9a-f]{40}", str(exp.get("base_commit", ""))),
             "base_commit must be a full 40-hex commit sha")
    models = pricing.get("models") or {}
    efforts = effort_values(pricing)
    profiles = pricing.get("task_profiles") or {}

    def check_stage(where, stage):
        _require(stage.get("model") in models,
                 f"{where}: model {stage.get('model')!r} is not an active model in "
                 f"data/pricing.copilot.json")
        _require(stage.get("effort") in efforts,
                 f"{where}: effort {stage.get('effort')!r} is not one of {efforts}")

    arms = exp.get("arms") or {}
    _require(arms, "no arms defined")
    for arm_id, arm in sorted(arms.items()):
        _sp().validate_id(arm_id, "arm id")
        shape = arm.get("shape")
        stages = arm.get("stages") or {}
        _require(shape in SHAPE_ROLES,
                 f"arm {arm_id}: shape must be one of {sorted(SHAPE_ROLES)}")
        roles, optional = SHAPE_ROLES[shape]
        required = [r for r in roles if r not in optional]
        _require(set(required) <= set(stages) <= set(roles),
                 f"arm {arm_id}: a {shape} arm needs the stages {required}"
                 + (f" (optional: {list(optional)})" if optional else ""))
        for role in roles:
            if role in stages:
                check_stage(f"arm {arm_id} {role}", stages[role])
    for index, judge in enumerate(exp.get("judges") or []):
        check_stage(f"judge {index}", judge)
    for role, profile in (exp.get("role_profiles") or {}).items():
        if role != "note":
            _require(profile in profiles, f"role_profiles.{role}: unknown task profile {profile!r}")
    weights = (exp.get("scoring") or {}).get("weights") or {}
    _require(set(weights) == set(WEIGHT_KEYS), f"scoring.weights must name exactly {WEIGHT_KEYS}")
    _require(abs(sum(weights.values()) - 1.0) < 1e-9, "scoring.weights must sum to 1")
    scoring = exp["scoring"]
    for key, allowed in (("mutation_operators", MUTATION_OPERATORS),
                         ("simplicity_basis", SIMPLICITY_BASES),
                         ("quality_mode", QUALITY_MODES)):
        _require(scoring.get(key, allowed[0]) in allowed,
                 f"scoring.{key} must be one of {list(allowed)}")
    for key, hi in (("judge_min_agreement", 1.0), ("max_estimate_share", 1.0),
                    ("cost_tie_pct", 1000.0)):
        value = scoring.get(key)
        _require(value is None or (isinstance(value, (int, float)) and 0 <= value <= hi),
                 f"scoring.{key} must be a number in 0..{hi:g}")
    fraction = (exp.get("judging") or {}).get("consistency_fraction", 0)
    _require(isinstance(fraction, (int, float)) and 0 <= fraction <= 1,
             "judging.consistency_fraction must be in 0..1")
    rework = exp.get("rework") or {}
    for key in ("after_verifier_fail", "after_reviewer_reject"):
        _require(isinstance(rework.get(key), int) and rework[key] >= 0,
                 f"rework.{key} must be a non-negative integer")
    _require(exp.get("tasks"), "no tasks listed")
    return exp


def load_task(exp_dir, task_id):
    _sp().validate_id(task_id, "task id")
    root = Path(exp_dir) / "tasks" / task_id
    task = json.loads((root / "task.json").read_text(encoding="utf-8"))
    _require(task.get("id") == task_id, f"{root}/task.json: id must be {task_id!r}")
    for key in ("source_files", "allowed_paths", "regression", "guardrails"):
        _require(isinstance(task.get(key), list), f"task {task_id}: {key} must be a list")
    task["prompt_text"] = (root / task["prompt"]).read_text(encoding="utf-8")
    task["oracle_text"] = (root / task["oracle"]).read_text(encoding="utf-8")
    task["reference_text"] = (root / task["reference"]).read_text(encoding="utf-8")
    task["digests"] = {key: sha256_text(task[f"{key}_text"])
                       for key in ("prompt", "oracle", "reference")}
    if task.get("naive"):
        task["naive_text"] = (root / task["naive"]).read_text(encoding="utf-8")
        task["digests"]["naive"] = sha256_text(task["naive_text"])
    for key in ("allowed_generated", "rubric"):
        _require(isinstance(task.get(key, []), list), f"task {task_id}: {key} must be a list")
    task["task_json_digest"] = sha256_text((root / "task.json").read_text(encoding="utf-8"))
    task["short"] = task_id.split("-")[0]
    return task


def load_experiment(exp_dir=EXPERIMENT_DIR, pricing=None):
    """-> (experiment dict with `task_defs`, preregistration digest)."""
    exp_dir = Path(exp_dir)
    raw = (exp_dir / "experiment.json").read_text(encoding="utf-8")
    exp = json.loads(raw)
    validate_definition(exp, pricing if pricing is not None else load_pricing())
    exp["task_defs"] = {tid: load_task(exp_dir, tid) for tid in exp["tasks"]}
    shorts = [t["short"] for t in exp["task_defs"].values()]
    _require(len(set(shorts)) == len(shorts), "task ids must have distinct leading segments")
    exp["dir"] = str(exp_dir)
    manifest = {"experiment": sha256_text(raw),
                "tasks": {tid: t["digests"] for tid, t in sorted(exp["task_defs"].items())}}
    if exp.get("digest_task_json"):
        manifest["task_json"] = {tid: t["task_json_digest"]
                                 for tid, t in sorted(exp["task_defs"].items())}
    digest = sha256_text(json.dumps(manifest, sort_keys=True))
    exp["extensions"] = load_extensions(exp_dir, exp, pricing if pricing is not None
                                        else load_pricing())
    return exp, digest


def load_extensions(exp_dir, exp, pricing):
    """{arm id: {definition, digest, file, reason, added}} from `extensions/*.json` -- arms
    added AFTER the preregistration. They live outside experiment.json so the preregistered
    digest never moves; a run takes one only on an explicit `--extend-arms`, which records the
    extension's own digest in run.json."""
    found = {}
    for path in sorted((Path(exp_dir) / "extensions").glob("*.json")):
        raw = path.read_text(encoding="utf-8")
        ext = json.loads(raw)
        _require(ext.get("version") == EXTENSION_VERSION,
                 f"{path.name}: version must be {EXTENSION_VERSION!r}")
        arm_id = ext.get("arm")
        _require(arm_id not in (exp.get("arms") or {}) and arm_id not in found,
                 f"{path.name}: arm {arm_id!r} already exists")
        _require(ext.get("reason"), f"{path.name}: an extension must state its reason")
        definition = ext.get("definition") or {}
        probe = {k: v for k, v in exp.items() if k not in ("task_defs", "dir")}
        validate_definition({**probe, "arms": {arm_id: definition}}, pricing)
        found[arm_id] = {"definition": definition, "digest": sha256_text(raw),
                         "file": f"extensions/{path.name}", "reason": ext["reason"],
                         "added": ext.get("added")}
    return found


def merge_extensions(exp, arm_ids):
    """Merge the named extension arms into `exp["arms"]` (in memory only)."""
    for arm_id in arm_ids:
        _require(arm_id in (exp.get("extensions") or {}),
                 f"no extension arm {arm_id!r} under {exp.get('dir', '?')}/extensions/")
        exp["arms"][arm_id] = exp["extensions"][arm_id]["definition"]
    return exp


# ---------------------------------------------------------------------------------------------
# The trial matrix, and what it should cost


def trial_plan(exp, repeats):
    """Every (task, arm, repeat) in counterbalanced dispatch order."""
    arms = sorted(exp["arms"])
    trials = []
    for rep in range(1, repeats + 1):
        for t_index, task_id in enumerate(exp["tasks"]):
            shift = (rep - 1 + t_index) % len(arms)
            order = arms[shift:] + arms[:shift]
            short = exp["task_defs"][task_id]["short"] if "task_defs" in exp else task_id
            for position, arm in enumerate(order):
                trials.append({"trial_id": f"{short}-{arm}-r{rep}", "task": task_id, "arm": arm,
                               "repeat": rep, "position": position})
    return trials


def stage_estimate(exp, pricing, role, model):
    """Profile-based AIC estimate for one dispatch (est.; excludes cache writes)."""
    profile = (exp.get("role_profiles") or {}).get(role, "M")
    return _cp().est_cost(pricing, profile, model)["aic"]


def arm_estimate(exp, pricing, arm_id):
    """-> {min, max, dispatches_min, dispatches_max} AIC for one trial of `arm_id`."""
    arm = exp["arms"][arm_id]
    st = arm["stages"]
    if arm["shape"] == "one-shot":
        aic = stage_estimate(exp, pricing, "solo", st["solo"]["model"])
        return {"min": aic, "max": aic, "dispatches_min": 1, "dispatches_max": 1}
    if arm["shape"] == "reviewed":
        base = sum(stage_estimate(exp, pricing, role, st[role]["model"])
                   for role in ("solo", "reviewer"))
        rounds = exp["rework"]["after_reviewer_reject"]
        per_round = (stage_estimate(exp, pricing, "solo", st["solo"]["model"])
                     + stage_estimate(exp, pricing, "reviewer", st["reviewer"]["model"]))
        return {"min": base, "max": base + rounds * per_round,
                "dispatches_min": 2, "dispatches_max": 2 + 2 * rounds}
    roles = [r for r in PIPELINE_ROLES if r in st]
    base = sum(stage_estimate(exp, pricing, role, st[role]["model"]) for role in roles)
    rework_rounds = exp["rework"]["after_verifier_fail"] + (
        exp["rework"]["after_reviewer_reject"] if "reviewer" in st else 0)
    one_round = (stage_estimate(exp, pricing, "implementer", st["implementer"]["model"])
                 + stage_estimate(exp, pricing, "verifier", st["verifier"]["model"]))
    return {"min": base, "max": base + rework_rounds * one_round,
            "dispatches_min": len(roles),
            "dispatches_max": len(roles) + 2 * rework_rounds}


def judge_estimate(exp, pricing):
    return sum(stage_estimate(exp, pricing, "judge", j["model"]) for j in exp.get("judges") or [])


def gate_stages(exp):
    """{(role, model, effort): [arms]} for every distinct verifier/reviewer stage."""
    gates = {}
    for arm_id, arm in sorted(exp["arms"].items()):
        for role in ("verifier", "reviewer"):
            st = arm["stages"].get(role)
            if st:
                gates.setdefault((role, st["model"], st["effort"]), []).append(arm_id)
    return gates


def probe_plan(exp):
    """-> [(key, gate, task_id, kind, n)] over every gate x task with a naive patch x
    {naive, reference} x probe.repeats."""
    repeats = int((exp.get("probe") or {}).get("repeats") or 1)
    out = []
    for g_index, gate in enumerate(sorted(gate_stages(exp))):
        for task_id in exp["tasks"]:
            task = exp["task_defs"][task_id]
            if not task.get("naive_text"):
                continue
            for kind in ("naive", "reference"):
                for n in range(1, repeats + 1):
                    out.append((f"probe-g{g_index}-{task['short']}-{kind}-r{n}", gate,
                                task_id, kind, n))
    return out


def probe_estimate(exp, pricing):
    plan = probe_plan(exp)
    return {"dispatches": len(plan),
            "aic": sum(stage_estimate(exp, pricing, role, model)
                       for _, (role, model, _e), _, _, _ in plan)}


def build_plan(exp, digest, pricing, repeats):
    trials = trial_plan(exp, repeats)
    per_arm = {arm: arm_estimate(exp, pricing, arm) for arm in sorted(exp["arms"])}
    n_groups = len(exp["tasks"]) * repeats
    per_group_judge = judge_estimate(exp, pricing)
    lo = sum(per_arm[t["arm"]]["min"] for t in trials)
    hi = sum(per_arm[t["arm"]]["max"] for t in trials)
    plan = {
        "version": EXPERIMENT_VERSION, "preregistration": digest, "base_commit": exp["base_commit"],
        "repeats": repeats, "trials": trials, "per_arm": per_arm,
        "dispatches": {"min": sum(per_arm[t["arm"]]["dispatches_min"] for t in trials),
                       "max": sum(per_arm[t["arm"]]["dispatches_max"] for t in trials),
                       "judge": n_groups * len(exp.get("judges") or [])},
        "aic": {"trials_min": lo, "trials_max": hi, "judges": n_groups * per_group_judge,
                "total_min": lo + n_groups * per_group_judge,
                "total_max": hi + n_groups * per_group_judge},
        "ceiling": exp.get("max_aic"),
        "basis": "est. -- task_profiles token counts x per-MTok rates; cache writes excluded, "
                 "so real spend runs higher; measured AIC replaces each estimate as it lands",
    }
    if exp.get("probe"):
        plan["probe"] = probe_estimate(exp, pricing)
    return plan


# ---------------------------------------------------------------------------------------------
# Dispatch argv and prompts


def build_argv(exp, binary, model, effort, prompt, session_id, role):
    flags = exp.get("dispatch_flags") or {}
    argv = [binary, "--model", model, f"--reasoning-effort={effort}", "--session-id", session_id]
    argv += list(flags.get("common") or [])
    if role in READ_ONLY_ROLES:
        argv += list(flags.get("read_only") or [])
    if role == "judge":
        argv += list(flags.get("judge") or [])
    argv += ["-p", prompt]
    return argv


def _bounded(text, limit):
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[... {len(text) - limit} more chars cut]"


def prompt_for(role, task, plan=None, test_files=None, patch=None, findings=None, source=None):
    spec = task["prompt_text"].strip()
    head = ("You are working in a git repository in the current directory. Work autonomously; "
            "do not ask questions. Do not push.\n\n# TASK\n\n" + spec)
    if role == "solo":
        return (head + "\n\n# YOUR JOB\n\nComplete the task end to end: implement the change, add "
                "or update unit tests, and run the tests named in the task until they pass.")
    if role == "planner":
        return (head + "\n\n# YOUR JOB: PLANNER\n\nDo NOT modify any file. Read the relevant code "
                "and write an implementation plan an engineer will follow literally: the files "
                "and functions to change, the exact behaviour for each requirement, edge cases, "
                "and the unit tests to write (names and what each asserts). Your final response "
                "must be the plan itself, in Markdown.")
    plan_block = f"\n\n# PLAN\n\n{_bounded(plan, PLAN_CHARS)}" if plan else ""
    if role == "test_author":
        return (head + plan_block + "\n\n# YOUR JOB: TEST AUTHOR\n\nWrite stdlib `unittest` tests "
                "under tests/ that encode the task's acceptance criteria, following the plan. "
                "Modify nothing outside tests/. The implementation does not exist yet, so new "
                "tests are expected to fail now. Final response: the test files and test names.")
    if role == "implementer" and not plan:
        # rework inside a `reviewed` arm: no plan, no test author -- only the findings
        return (head + "\n\n# YOUR JOB\n\nYou already worked on this task; your change so far is "
                "in the working tree. A reviewer found problems. Address every finding that is "
                "correct, keep the unit tests up to date, and run the tests named in the task "
                f"until they pass.\n\n# FINDINGS TO ADDRESS (from the {source or 'reviewer'})"
                f"\n\n{_bounded(findings, FINDINGS_CHARS)}")
    if role == "implementer":
        tests = ", ".join(test_files) if test_files else "(none were written)"
        body = (head + plan_block + f"\n\n# TESTS WRITTEN FROM THE PLAN\n\n{tests}\n\n# YOUR JOB: "
                "IMPLEMENTER\n\nImplement the change so these tests and the existing tests named "
                "in the task pass. Do not weaken or delete the provided tests; if one is wrong, "
                "fix it minimally and say why. Run the tests before finishing.")
        if findings:
            body += (f"\n\n# FINDINGS TO ADDRESS (from the {source})\n\n"
                     f"{_bounded(findings, FINDINGS_CHARS)}\n\nAddress every finding that is "
                     "correct; the change so far is already in the working tree.")
        return body
    diff = f"\n\n# CURRENT CHANGE (unified diff against the starting state)\n\n```diff\n" \
           f"{_bounded(patch, PROMPT_PATCH_CHARS)}\n```"
    if role == "verifier":
        return (head + diff + "\n\n# YOUR JOB: VERIFIER\n\nDo NOT modify any file. Run the "
                "relevant tests, check every requirement in the task against the code, and list "
                "concrete defects. End your response with exactly one line: "
                "`VERIFY VERDICT=pass` or `VERIFY VERDICT=fail`.")
    if role == "reviewer":
        return (head + diff + "\n\n# YOUR JOB: REVIEWER (final quality gate)\n\nDo NOT modify "
                "any file. Review for correctness against every requirement, edge cases, "
                "readability, design, test quality and scope. List findings by severity. End "
                "your response with exactly one line: `REVIEW VERDICT=accept` or "
                "`REVIEW VERDICT=reject`.")
    raise ValueError(f"no prompt for role {role!r}")


def judge_prompt(task, candidates):
    """`candidates` is [(label, patch)] already shuffled; nothing names an arm or a model."""
    parts = ["You are grading anonymous candidate solutions to ONE programming task. Judge only "
             "from the text below; do not run tools. Candidates are in no particular order.\n\n"
             "# TASK\n\n" + task["prompt_text"].strip()]
    for label, patch in candidates:
        body = _bounded(patch, JUDGE_PATCH_CHARS) if patch.strip() else "(empty diff: no change)"
        parts.append(f"# CANDIDATE {label}\n\n```diff\n{body}\n```")
    keys = ", ".join(f'"{label}": {{...}}' for label, _ in candidates)
    parts.append(
        "# SCORING\n\nScore EVERY candidate from 1 (worst) to 10 (best) on: correctness (meets "
        "every requirement, handles edge cases), readability, design (simplicity, "
        "maintainability, fit with the surrounding code), tests (do the tests pin the "
        "behaviour?), scope (changes only what the task needs), and overall. Respond with ONE "
        "JSON object and nothing else, shaped: {\"candidates\": {" + keys + "}} where each value "
        "is {\"correctness\": n, \"readability\": n, \"design\": n, \"tests\": n, \"scope\": n, "
        "\"overall\": n, \"rationale\": \"<= 40 words\"}.")
    return "\n\n".join(parts)


def judge_prompt_rubric_rank(task, candidates):
    """v2 judge prompt: a per-task checklist answered for every candidate, then one full
    ranking. Checklist items are the task's own `rubric`; nothing names an arm or a model."""
    rubric = task.get("rubric") or ["The change meets every requirement in the task."]
    parts = ["You are grading anonymous candidate solutions to ONE programming task. Judge only "
             "from the text below; do not run tools. Candidates are in no particular order.\n\n"
             "# TASK\n\n" + task["prompt_text"].strip()]
    for label, patch in candidates:
        body = _bounded(patch, JUDGE_PATCH_CHARS) if patch.strip() else "(empty diff: no change)"
        parts.append(f"# CANDIDATE {label}\n\n```diff\n{body}\n```")
    items = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(rubric))
    keys = ", ".join(f'"{label}": {{...}}' for label, _ in candidates)
    labels = ", ".join(f'"{label}"' for label, _ in candidates)
    parts.append(
        "# CHECKLIST\n\n" + items + "\n\n# SCORING\n\nFor EVERY candidate answer each "
        "checklist item true (the diff clearly satisfies it) or false, in order, and give an "
        "overall score from 1 (worst) to 10 (best) weighing correctness, design, readability, "
        "test quality and scope. Then rank ALL candidates from best to worst; ties are not "
        "allowed. Respond with ONE JSON object and nothing else, shaped: {\"candidates\": {"
        + keys + "}, \"ranking\": [" + labels + " in your order]} where each candidate value "
        f"is {{\"checklist\": [{len(rubric)} booleans], \"overall\": n, "
        "\"rationale\": \"<= 40 words\"}.")
    return "\n\n".join(parts)


def parse_judge_rubric_rank(text, labels, items):
    """-> {"scores": {arm: {checklist, rubric_share, overall, rationale}}, "ranking": [arms]}
    from a rubric_rank response, or None if it is not usable (any malformed candidate, a
    checklist of the wrong length, or a ranking that is not a permutation of the labels)."""
    decoder = json.JSONDecoder()
    for start in [m.start() for m in re.finditer(r"\{", text or "")]:
        try:
            obj, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or not isinstance(obj.get("candidates"), dict):
            continue
        ranking = obj.get("ranking")
        if not isinstance(ranking, list) or sorted(map(str, ranking)) != sorted(labels):
            return None
        scores = {}
        for label, arm in labels.items():
            entry = obj["candidates"].get(label)
            if not isinstance(entry, dict):
                return None
            checks, overall = entry.get("checklist"), entry.get("overall")
            if (not isinstance(checks, list) or len(checks) != items
                    or not all(isinstance(c, bool) for c in checks)):
                return None
            if not isinstance(overall, (int, float)) or isinstance(overall, bool) \
                    or not 1 <= overall <= 10:
                return None
            scores[arm] = {"checklist": checks, "rubric_share": sum(checks) / items,
                           "overall": float(overall),
                           "rationale": str(entry.get("rationale") or "")[:400]}
        return {"scores": scores, "ranking": [labels[str(x)] for x in ranking]}
    return None


# ---------------------------------------------------------------------------------------------
# Diffs: which files changed, how much, and whether the change stayed in scope

_DIFF_HEADER_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$")


def diff_files(patch):
    """Unified diff -> [{path, added, removed, added_lines, new, deleted}] in diff order."""
    files, current = [], None
    for line in (patch or "").splitlines():
        match = _DIFF_HEADER_RE.match(line)
        if match:
            current = {"path": match.group(2), "added": 0, "removed": 0, "added_lines": [],
                       "new": False, "deleted": False}
            files.append(current)
            continue
        if current is None:
            continue
        if line.startswith("new file mode"):
            current["new"] = True
        elif line.startswith("deleted file mode"):
            current["deleted"] = True
        elif line.startswith("+++ ") or line.startswith("--- "):
            continue
        elif line.startswith("+"):
            current["added"] += 1
            current["added_lines"].append(line[1:])
        elif line.startswith("-"):
            current["removed"] += 1
    return files


def is_test_path(path):
    return path.startswith("tests/")


def in_scope(path, allowed):
    return any(path.startswith(entry) if entry.endswith("/") else path == entry
               for entry in allowed)


def guardrail_hits(files, guardrails):
    """{kind: count} of guardrail regexes matching ADDED lines in non-test files."""
    hits = {}
    for entry in files:
        if is_test_path(entry["path"]) or not entry["path"].endswith(".py"):
            continue
        for rule in guardrails:
            pattern = re.compile(rule["regex"], re.MULTILINE)
            count = sum(1 for line in entry["added_lines"] if pattern.search(line))
            if count:
                hits[rule["kind"]] = hits.get(rule["kind"], 0) + count
    return hits


def diff_stats(patch, task):
    """Size and scope of a diff. Paths in the task's `allowed_generated` (regenerated mirrors
    the task legitimately rebuilds) are in scope and outside every size measure."""
    every = diff_files(patch)
    generated = task.get("allowed_generated") or []
    files = [f for f in every if not in_scope(f["path"], generated)]
    src = [f for f in files if not is_test_path(f["path"])]
    tests = [f for f in files if is_test_path(f["path"])]
    todo_re = re.compile(r"\b(TODO|FIXME|XXX)\b")
    return {
        "files_changed": len(files),
        "src_files": sorted(f["path"] for f in src),
        "test_files": sorted(f["path"] for f in tests),
        "src_added": sum(f["added"] for f in src), "src_removed": sum(f["removed"] for f in src),
        "test_added": sum(f["added"] for f in tests),
        "test_removed": sum(f["removed"] for f in tests),
        "out_of_scope": sorted(f["path"] for f in files
                               if not in_scope(f["path"], task["allowed_paths"])),
        "guardrails": guardrail_hits(files, task["guardrails"]),
        "todos_added": sum(1 for f in files for line in f["added_lines"] if todo_re.search(line)),
        "empty": not every,
        **({"generated_files": sorted(f["path"] for f in every
                                      if in_scope(f["path"], generated))}
           if generated else {}),
    }


# ---------------------------------------------------------------------------------------------
# Static complexity (stdlib ast/tokenize; cognitive complexity is an approximation, labelled so)

_BRANCH_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp)
_NEST_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)
if hasattr(ast, "Match"):
    _NEST_NODES = _NEST_NODES + (ast.Match,)
if hasattr(ast, "TryStar"):
    _NEST_NODES = _NEST_NODES + (ast.TryStar,)
_FUNC_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPE_NODES = _FUNC_NODES + (ast.ClassDef,)


def _own_nodes(node):
    """Descendants of `node` that are not inside a nested function or class."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        child = stack.pop()
        yield child
        if not isinstance(child, _SCOPE_NODES):
            stack.extend(ast.iter_child_nodes(child))


def mccabe(node):
    score = 1
    for child in _own_nodes(node):
        if isinstance(child, _BRANCH_NODES):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            score += 1 + len(child.ifs)
        elif hasattr(ast, "match_case") and isinstance(child, ast.match_case):
            score += 1
    return score


def cognitive(node):
    """Approximate SonarSource cognitive complexity: +1 per break in linear flow, plus the
    nesting depth for structures that nest; `elif`/`else` +1 flat; a boolean-operator run +1."""
    total = 0

    def visit(n, depth):
        nonlocal total
        for child in ast.iter_child_nodes(n):
            if isinstance(child, _SCOPE_NODES) or isinstance(child, ast.Lambda):
                continue
            if isinstance(child, ast.If):
                total += 1 + depth
                visit_test_and_body(child, depth)
                orelse = child.orelse
                while len(orelse) == 1 and isinstance(orelse[0], ast.If):
                    total += 1
                    visit_test_and_body(orelse[0], depth)
                    orelse = orelse[0].orelse
                if orelse:
                    total += 1
                    for stmt in orelse:
                        visit_stmt(stmt, depth + 1)
                continue
            if isinstance(child, (ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
                                  ast.IfExp)):
                total += 1 + depth
                visit(child, depth + 1)
                continue
            if isinstance(child, ast.BoolOp):
                total += 1
            visit(child, depth)

    def visit_test_and_body(node_if, depth):
        visit(node_if.test, depth)
        for stmt in node_if.body:
            visit_stmt(stmt, depth + 1)

    def visit_stmt(stmt, depth):
        wrapper = ast.Module(body=[stmt], type_ignores=[])
        visit(wrapper, depth)

    visit(node, 0)
    return total


def max_nesting(node):
    best = 0

    def visit(n, depth):
        nonlocal best
        for child in ast.iter_child_nodes(n):
            if isinstance(child, _SCOPE_NODES):
                continue
            if isinstance(child, _NEST_NODES):
                best = max(best, depth + 1)
                visit(child, depth + 1)
            else:
                visit(child, depth)

    visit(node, 0)
    return best


def functions(tree):
    """{qualname: node} for every function, including methods and nested functions."""
    found = {}

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _SCOPE_NODES):
                name = f"{prefix}{child.name}"
                if isinstance(child, _FUNC_NODES):
                    found[name] = child
                visit(child, name + ".")
            else:
                visit(child, prefix)

    visit(tree, "")
    return found


def _docstring_lines(tree):
    lines = set()
    for node in [tree] + [n for n in ast.walk(tree) if isinstance(n, _SCOPE_NODES)]:
        body = getattr(node, "body", None) or []
        if body and isinstance(body[0], ast.Expr) and isinstance(
                getattr(body[0], "value", None), ast.Constant) and isinstance(
                body[0].value.value, str):
            lines.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    return lines


_SKIP_TOKENS = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER}


def _tokens(source):
    try:
        return list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []


def sloc(source, tree):
    doc = _docstring_lines(tree)
    lines = set()
    for tok in _tokens(source):
        if tok.type in _SKIP_TOKENS:
            continue
        for line in range(tok.start[0], tok.end[0] + 1):
            if line not in doc:
                lines.add(line)
    return len(lines)


def halstead_volume(source):
    operators, operands = [], []
    for tok in _tokens(source):
        if tok.type == tokenize.OP:
            operators.append(tok.string)
        elif tok.type == tokenize.NAME:
            (operators if keyword.iskeyword(tok.string) else operands).append(tok.string)
        elif tok.type in (tokenize.NUMBER, tokenize.STRING):
            operands.append(tok.string)
    vocabulary = len(set(operators)) + len(set(operands))
    length = len(operators) + len(operands)
    return length * math.log2(vocabulary) if vocabulary > 1 else 0.0


def maintainability_index(volume, cc_total, lines):
    """The SEI/Visual Studio MI, rescaled to 0..100 (higher is more maintainable)."""
    raw = 171 - 5.2 * math.log(max(volume, 1.0)) - 0.23 * cc_total - 16.2 * math.log(max(lines, 1))
    return max(0.0, raw * 100 / 171)


def source_metrics(source):
    """Module-level complexity metrics for one Python source text (None -> parse error)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    funcs = functions(tree)
    per_func = {}
    for name, node in funcs.items():
        per_func[name] = {"cc": mccabe(node), "cognitive": cognitive(node),
                          "nesting": max_nesting(node),
                          "length": (node.end_lineno or node.lineno) - node.lineno + 1,
                          "lineno": node.lineno, "end_lineno": node.end_lineno or node.lineno}
    module_cc = mccabe(tree)
    cc_total = module_cc - 1 + sum(f["cc"] for f in per_func.values())
    lines = sloc(source, tree)
    volume = halstead_volume(source)
    return {"sloc": lines, "functions": len(per_func), "cc_total": cc_total,
            "cc_max": max((f["cc"] for f in per_func.values()), default=0),
            "cognitive_total": sum(f["cognitive"] for f in per_func.values()),
            "nesting_max": max((f["nesting"] for f in per_func.values()), default=0),
            "halstead_volume": round(volume, 1),
            "mi": round(maintainability_index(volume, cc_total, lines), 2),
            "per_function": per_func}


def changed_functions(before_src, after_src):
    """Qualnames of functions in `after_src` that are new or whose source text changed."""
    try:
        before_tree = ast.parse(before_src) if before_src else ast.parse("")
        after_tree = ast.parse(after_src)
    except SyntaxError:
        return []
    before = {name: ast.get_source_segment(before_src or "", node)
              for name, node in functions(before_tree).items()}
    changed = []
    for name, node in functions(after_tree).items():
        if before.get(name) != ast.get_source_segment(after_src, node):
            changed.append(name)
    return sorted(changed)


def unused_imports(source):
    """Top-level imported names never referenced elsewhere in the module."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    imported = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported[(alias.asname or alias.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    imported[alias.asname or alias.name] = node.lineno
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {n.value.id for n in ast.walk(tree)
             if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    exported = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            if isinstance(node.value, (ast.List, ast.Tuple)):
                exported |= {e.value for e in node.value.elts if isinstance(e, ast.Constant)}
    return {name for name in imported if name not in used and name not in exported}


def undocumented_new_public(before_src, after_src):
    """New public top-level functions/classes without a docstring."""
    try:
        before = {n.name for n in ast.parse(before_src or "").body if isinstance(n, _SCOPE_NODES)}
        after = [n for n in ast.parse(after_src).body if isinstance(n, _SCOPE_NODES)]
    except SyntaxError:
        return []
    return sorted(n.name for n in after if n.name not in before and not n.name.startswith("_")
                  and ast.get_docstring(n) is None)


def complexity_delta(before_src, after_src):
    """Before/after metrics for one source file, focused on the functions the change touched."""
    before = source_metrics(before_src or "") if before_src is not None else source_metrics("")
    after = source_metrics(after_src)
    if after is None:
        return {"parse_error": True}
    touched = changed_functions(before_src, after_src)
    tf = [after["per_function"][name] for name in touched]
    return {
        "parse_error": False,
        "before": {k: v for k, v in (before or {}).items() if k != "per_function"},
        "after": {k: v for k, v in after.items() if k != "per_function"},
        "delta": {key: round(after[key] - (before or {}).get(key, 0), 2)
                  for key in ("sloc", "cc_total", "cognitive_total", "halstead_volume", "mi")},
        "touched_functions": touched,
        "touched_cc_max": max((f["cc"] for f in tf), default=0),
        "touched_cognitive_max": max((f["cognitive"] for f in tf), default=0),
        "touched_nesting_max": max((f["nesting"] for f in tf), default=0),
        "touched_length_max": max((f["length"] for f in tf), default=0),
        "new_unused_imports": sorted(unused_imports(after_src) - unused_imports(before_src or "")),
        "undocumented_new_public": undocumented_new_public(before_src, after_src),
    }


# ---------------------------------------------------------------------------------------------
# Mutation testing: does the candidate's own test suite pin the behaviour it changed?

_CMP_SWAP = {ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE, ast.LtE: ast.Gt,
             ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Is: ast.IsNot, ast.IsNot: ast.Is,
             ast.In: ast.NotIn, ast.NotIn: ast.In}
_BIN_SWAP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult,
             ast.FloorDiv: ast.Mult}
_CALL_SWAP = {"min": "max", "max": "min", "any": "all", "all": "any"}
MUTATION_OPERATORS = ("v1", "v2")


def _mutation_points(tree, ranges, operators="v1"):
    """v1: compare/bool-op/arith/int/not/return. v2 adds bool and non-docstring str constants,
    min/max and any/all swaps, augmented-assignment arithmetic, negated `if`/`while` tests and
    a dropped unary minus -- the operators that reach branchy, string-handling code."""
    v2 = operators == "v2"
    docstrings = {id(n.value) for n in ast.walk(tree)
                  if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}

    def inside(node):
        line = getattr(node, "lineno", None)
        return line is not None and any(lo <= line <= hi for lo, hi in ranges)

    points = []
    for node in ast.walk(tree):
        if not inside(node):
            continue
        if isinstance(node, ast.Compare):
            for index, op in enumerate(node.ops):
                if type(op) in _CMP_SWAP:
                    points.append(("compare", node, index))
        elif isinstance(node, ast.BoolOp):
            points.append(("boolop", node, None))
        elif isinstance(node, ast.BinOp) and type(node.op) in _BIN_SWAP:
            points.append(("binop", node, None))
        elif isinstance(node, ast.Constant) and type(node.value) is int:
            points.append(("int", node, None))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            points.append(("not", node, None))
        elif v2 and isinstance(node, ast.Constant) and type(node.value) is bool:
            points.append(("bool", node, None))
        elif (v2 and isinstance(node, ast.Constant) and isinstance(node.value, str)
              and node.value and id(node) not in docstrings):
            points.append(("str", node, None))
        elif (v2 and isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id in _CALL_SWAP):
            points.append(("call-swap", node, None))
        elif v2 and isinstance(node, ast.AugAssign) and type(node.op) in _BIN_SWAP:
            points.append(("augassign", node, None))
        elif v2 and isinstance(node, (ast.If, ast.While)):
            points.append(("negate-test", node, None))
        elif v2 and isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            points.append(("neg", node, None))
        elif isinstance(node, ast.Return) and node.value is not None and not (
                isinstance(node.value, ast.Constant) and node.value.value is None):
            points.append(("return", node, None))
    return points


def _apply_point(kind, node, index):
    if kind == "compare":
        node.ops[index] = _CMP_SWAP[type(node.ops[index])]()
    elif kind == "boolop":
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    elif kind in ("binop", "augassign"):
        node.op = _BIN_SWAP[type(node.op)]()
    elif kind == "bool":
        node.value = not node.value
    elif kind == "str":
        node.value = ""
    elif kind == "call-swap":
        node.func.id = _CALL_SWAP[node.func.id]
    elif kind == "negate-test":
        node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
    elif kind == "int":
        node.value = node.value + 1
    elif kind == "return":
        node.value = ast.Constant(value=None)


class _DropNot(ast.NodeTransformer):
    def __init__(self, target):
        self.target = target

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        return node.operand if node is self.target else node


def mutants(source, function_names, limit, seed, operators="v1"):
    """Deterministic sample of at most `limit` single-point mutants of the named functions.

    -> [{"id", "kind", "line", "source"}]. Each mutant re-parses the original so mutations
    never compound; `ast.unparse` drops comments, which a test run does not care about.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    funcs = functions(tree)
    ranges = [(funcs[n].lineno, funcs[n].end_lineno or funcs[n].lineno)
              for n in function_names if n in funcs]
    if not ranges:
        return []
    count = len(_mutation_points(tree, ranges, operators))
    order = list(range(count))
    random.Random(seed).shuffle(order)
    out = []
    for point_index in sorted(order[:limit]):
        fresh = ast.parse(source)
        kind, node, index = _mutation_points(fresh, ranges, operators)[point_index]
        line = node.lineno
        if kind in ("not", "neg"):
            fresh = _DropNot(node).visit(fresh)
        else:
            _apply_point(kind, node, index)
        ast.fix_missing_locations(fresh)
        try:
            text = ast.unparse(fresh) + "\n"
        except Exception:  # noqa: BLE001 -- an unparseable mutant is simply not generated
            continue
        out.append({"id": f"m{point_index:03d}", "kind": kind, "line": line, "source": text})
    return out


# ---------------------------------------------------------------------------------------------
# unittest output


def parse_unittest(output):
    """-> {ran, failures, errors, skipped, ok} from a `python -m unittest` transcript."""
    text = output or ""
    ran_all = RAN_RE.findall(text)
    ran = int(ran_all[-1]) if ran_all else 0
    failures = errors = skipped = 0
    failed = FAILED_RE.findall(text)
    if failed:
        for part in failed[-1].split(","):
            key, _, value = part.strip().partition("=")
            if value.isdigit():
                if key == "failures":
                    failures = int(value)
                elif key == "errors":
                    errors = int(value)
                elif key == "skipped":
                    skipped = int(value)
    ok = bool(ran_all) and not failed and re.search(r"^OK\b", text, re.MULTILINE) is not None
    return {"ran": ran, "failures": failures, "errors": errors, "skipped": skipped, "ok": ok}


def oracle_test_count(oracle_text):
    tree = ast.parse(oracle_text)
    return sum(1 for cls in tree.body if isinstance(cls, ast.ClassDef)
               for node in cls.body if isinstance(node, _FUNC_NODES)
               and node.name.startswith("test"))


# ---------------------------------------------------------------------------------------------
# What a dispatch cost, read from its own session log (read-only, JSONL only)


def _event_lines(text):
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


def _token_details(td):
    td = td if isinstance(td, dict) else {}
    return {kind: int(((td.get(kind) or {}).get("tokenCount")) or 0)
            for kind in ("input", "cache_read", "cache_write", "output")}


def session_usage(events_text, pricing):
    """One session's cost from its LAST `session.shutdown` -> dict, or None when there is none.

    Primary figure: `aic`, every model's `tokenDetails` priced from the pricing file (est. --
    the rates are a dated snapshot). Beside it, never summed with it: `reported_aiu`, Copilot's
    own `totalNanoAiu`, and their agreement. A model the pricing file cannot price falls back to
    its reported AIU and is named in `unpriced`.
    """
    cu = _cu()
    shutdown = None
    models_seen, efforts_seen, tool_calls = [], [], {}
    for obj in _event_lines(events_text):
        etype, data = obj.get("type"), obj.get("data") or {}
        if etype == "session.shutdown":
            shutdown = data
        elif etype == "session.model_change":
            for key, bucket in (("newModel", models_seen), ("reasoningEffort", efforts_seen)):
                if data.get(key) and data[key] not in bucket:
                    bucket.append(data[key])
        elif etype == "tool.execution_start":
            name = str(data.get("toolName") or "?")
            tool_calls[name] = tool_calls.get(name, 0) + 1
    if shutdown is None:
        return None
    metrics = shutdown.get("modelMetrics") or {}
    if not metrics and shutdown.get("currentModel"):
        metrics = {shutdown["currentModel"]: {"tokenDetails": shutdown.get("tokenDetails"),
                                              "totalNanoAiu": shutdown.get("totalNanoAiu")}}
    per_model, unpriced, aic = {}, [], 0.0
    totals = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0}
    reasoning = 0
    for raw_model, mm in sorted(metrics.items()):
        mm = mm if isinstance(mm, dict) else {}
        tokens = _token_details(mm.get("tokenDetails"))
        for kind in totals:
            totals[kind] += tokens[kind]
        reasoning += int(((mm.get("usage") or {}).get("reasoningTokens")) or 0)
        reported = (mm.get("totalNanoAiu") or 0) / 1e9
        key = cu.match_model(raw_model, pricing)
        if key is not None:
            model_aic = cu.usd_to_aic(cu.price_tokens(tokens, key, pricing), pricing)
        else:
            model_aic = reported
            unpriced.append(raw_model)
        aic += model_aic
        per_model[raw_model] = {"model_key": key, "tokens": tokens, "aic": round(model_aic, 4),
                                "reported_aiu": round(reported, 4),
                                "requests": ((mm.get("requests") or {}).get("count"))}
    reported_total = (shutdown.get("totalNanoAiu") or 0) / 1e9
    return {
        "aic": round(aic, 4), "reported_aiu": round(reported_total, 4),
        "agreement_pct": round(100 * aic / reported_total, 1) if reported_total else None,
        "tokens": totals, "reasoning_tokens": reasoning,
        "premium_requests": shutdown.get("totalPremiumRequests"),
        "api_ms": shutdown.get("totalApiDurationMs"),
        "per_model": per_model, "unpriced": unpriced,
        "observed_models": models_seen, "observed_efforts": efforts_seen,
        "tool_calls": tool_calls,
    }


def nested_cli_launch(command):
    """True when a shell command LAUNCHES a nested model CLI: `copilot -p/--prompt ...`, or a
    polytropos dispatcher run as a program (`python3 bin/copilot_execute.py`, `./bin/...`).
    Naming one as data -- `grep x bin/copilot_execute.py`, `sed -n 1,9p ...` -- is not."""
    for segment in SHELL_SPLIT_RE.split(command or ""):
        try:
            words = shlex.split(segment)
        except ValueError:
            words = segment.split()
        while words and ("=" in words[0] and not words[0].startswith("-")
                         or os.path.basename(words[0]) in SHELL_WRAPPERS
                         or re.fullmatch(r"-\S*|\d+[smh]?", words[0])):
            words = words[1:]
        if not words:
            continue
        head = os.path.basename(words[0])
        if head == "copilot" and any(w in ("-p", "--prompt") or w.startswith("--prompt=")
                                     for w in words[1:]):
            return True
        if head in NESTED_DISPATCHERS:
            return True
        if re.fullmatch(r"python(?:3(?:\.\d+)?)?", head):
            script = next((w for w in words[1:] if not w.startswith("-")), "")
            if os.path.basename(script) in NESTED_DISPATCHERS:
                return True
    return False


def _commands(arguments):
    """Every string under a `command` key of a tool call's arguments."""
    if isinstance(arguments, dict):
        for key, value in arguments.items():
            if key == "command" and isinstance(value, str):
                yield value
            else:
                yield from _commands(value)
    elif isinstance(arguments, list):
        for value in arguments:
            yield from _commands(value)


def contamination(events_text, markers):
    """Markers found in the session's TOOL-CALL ARGUMENTS (what the agent asked to do).

    Tool RESULTS are not scanned: a `grep` that happens to list `copilot_execute.py` is the
    repository answering, not the agent launching a nested CLI. Nor is a dispatcher named as
    an argument (a file to grep or view): nested-cli means a shell command that RUNS one.
    """
    hits = []
    for obj in _event_lines(events_text):
        if obj.get("type") != "tool.execution_start":
            continue
        data = obj.get("data") or {}
        args = json.dumps(data.get("arguments"), sort_keys=True)
        for marker in markers:
            if marker and marker in args and marker not in hits:
                hits.append(marker)
        if "nested-cli" not in hits and any(
                nested_cli_launch(c) for c in _commands(data.get("arguments"))):
            hits.append("nested-cli")
        if data.get("toolName") in ("task", "skill") and "delegation" not in hits:
            hits.append("delegation")
    return hits


# ---------------------------------------------------------------------------------------------
# The run store and the experiment driver


class CeilingReached(RuntimeError):
    """The next dispatch would take measured spend past `--max-aic`."""


def default_store_dir():
    return _rd().store_path(STORE_NAME, REPO_ROOT)


def default_dispatch_runner(argv, cwd, timeout):
    pr = _pr()
    return pr.run(argv, cwd=cwd, env=pr.dispatch_env("copilot"), timeout=timeout,
                  output_limit=4 * 1024 * 1024, name="copilot")


def _unittest_cmd(pattern=None):
    """A test line for the verify boundary. Runtime stores point at the run-scoped scratch
    `$TMPDIR` (the boundary refuses writes to the real data home, correctly). `-B` keeps
    bytecode out of the grade box: a same-size mutant written within the same second as
    its source would otherwise run from the source's stale .pyc and "survive"."""
    line = (f'POLYTROPOS_DATA_HOME="$TMPDIR/polytropos-data" {shlex.quote(sys.executable)} '
            f"-B -m unittest discover -s tests")
    return f"{line} -p {shlex.quote(pattern)}" if pattern else line


# Consecutive dispatch-failed trials that stop a run: an outage fails every dispatch in
# seconds, and each unlogged failure is charged its estimate against the ceiling.
FAILURE_STREAK_LIMIT = 3


class Experiment:
    """One run: dispatch trials, record everything, grade, judge. The run store's only writer."""

    def __init__(self, exp, digest, pricing, store_dir, run_id, *, binary="copilot",
                 copilot_home=None, repo=REPO_ROOT, exec_mode="enforced", live=False,
                 max_aic=None, dispatch_runner=None, git_runner=None, out=None,
                 keep_work=False, full_regression=False):
        self.exp, self.digest, self.pricing = exp, digest, pricing
        self.store_dir = Path(store_dir)
        self.run_id = _sp().validate_id(run_id, "run id")
        self.run_dir = self.store_dir / self.run_id
        self.binary = binary
        self.copilot_home = Path(copilot_home) if copilot_home else Path(
            os.environ.get("COPILOT_HOME") or Path(os.environ.get("HOME", "/")) / ".copilot")
        self.repo = Path(repo)
        self.exec_mode = exec_mode
        self.live = live
        self.max_aic = max_aic
        self.dispatch_runner = dispatch_runner or default_dispatch_runner
        self.git_runner = git_runner
        self.out = out or sys.stdout
        self.keep_work = keep_work
        self.full_regression = full_regression
        self.timeout = int(exp.get("stage_timeout_seconds") or 1800)
        self.markers = [str(Path(exp["dir"]).resolve()), "route-arms", ORACLE_TEST_NAME,
                        "reference.patch", str(REPO_ROOT)]
        self._ledger = None
        self._reference = {}

    # -- records ----------------------------------------------------------------------------

    def say(self, text):
        print(text, file=self.out, flush=True)

    def write(self, rel, payload):
        data = payload if isinstance(payload, (bytes, str)) else json.dumps(
            payload, indent=2, sort_keys=True, default=str) + "\n"
        if isinstance(data, str):
            data = data.encode("utf-8")
        _rd().ensure_private(self.run_dir)
        _sp().confined_write_bytes(self.run_dir, rel, data, what="route-experiment record")

    def read_json(self, rel):
        if not self.run_dir.is_dir():
            return None
        raw = _sp().confined_read_bytes(self.run_dir, rel, what="route-experiment record",
                                        missing_ok=True)
        return None if raw is None else json.loads(raw.decode("utf-8"))

    def read_text(self, rel):
        if not self.run_dir.is_dir():
            return None
        raw = _sp().confined_read_bytes(self.run_dir, rel, what="route-experiment record",
                                        missing_ok=True)
        return None if raw is None else raw.decode("utf-8")

    def records(self, sub):
        root = self.run_dir / sub
        if not root.is_dir():
            return []
        found = []
        for path in sorted(root.glob("*.json")):
            record = self.read_json(f"{sub}/{path.name}")
            if record is not None:
                found.append(record)
        return found

    @property
    def ledger(self):
        if self._ledger is None:
            _rd().ensure_private(self.run_dir / "attempts")
            self._ledger = _al().AttemptLedger(self.run_dir / "attempts", self.run_id)
        return self._ledger

    def open_run(self, repeats, extend=()):
        manifest = self.read_json("run.json")
        if manifest is not None:
            if manifest.get("preregistration") != self.digest:
                raise ConfigError(
                    f"run {self.run_id} was started under preregistration "
                    f"{manifest.get('preregistration', '?')[:12]}; the experiment definition "
                    f"now digests to {self.digest[:12]}. Start a new run instead of mixing them.")
        else:
            manifest = {"version": RESULT_VERSION, "run_id": self.run_id, "created": utc_now(),
                        "preregistration": self.digest, "base_commit": self.exp["base_commit"],
                        "repeats": repeats, "exec_mode": self.exec_mode,
                        "pricing_cached_date": self.pricing.get("cached_date"),
                        "cli_binary": Path(self.binary).name, "arms": dict(self.exp["arms"]),
                        "judges": self.exp.get("judges"), "scoring": self.exp["scoring"]}
            self.write("run.json", manifest)
        self.activate(manifest)
        recorded = {e["arm"] for e in manifest.get("extensions") or []}
        added = [a for a in extend if a not in recorded]
        if added:
            merge_extensions(self.exp, added)
            for arm_id in added:
                ext = self.exp["extensions"][arm_id]
                manifest.setdefault("extensions", []).append({
                    "arm": arm_id, "digest": ext["digest"], "file": ext["file"],
                    "reason": ext["reason"], "definition": ext["definition"],
                    "added_to_run": utc_now(),
                    "trials_before": len(self.records("trials"))})
            self.write("run.json", manifest)
            self.say(f"run {self.run_id}: extended with post-hoc arm(s) {', '.join(added)} "
                     "(recorded in run.json; reported apart from the preregistered decision)")
        return manifest

    def activate(self, manifest):
        """Merge the extension arms this run already recorded, refusing a changed extension."""
        for entry in manifest.get("extensions") or []:
            ext = (self.exp.get("extensions") or {}).get(entry["arm"])
            if ext is None or ext["digest"] != entry["digest"]:
                raise ConfigError(
                    f"run {self.run_id} recorded extension arm {entry['arm']} at digest "
                    f"{entry['digest'][:12]}; {entry.get('file', 'its file')} is now "
                    f"{'missing' if ext is None else ext['digest'][:12]}. Restore it or start "
                    "a new run.")
            merge_extensions(self.exp, [entry["arm"]])
        return manifest

    def preregistered_arms(self):
        manifest = self.read_json("run.json") or {}
        extensions = {e["arm"] for e in manifest.get("extensions") or []}
        return sorted(a for a in (manifest.get("arms") or self.exp["arms"])
                      if a not in extensions)

    # -- money ------------------------------------------------------------------------------

    def spent(self):
        """Every dispatch recorded so far in this run: measured AIC, or the estimate when the
        session log could not be read (never zero)."""
        total = 0.0
        for record in self.records("trials") + self.records("judges") + self.records("probes"):
            for dispatch in record.get("dispatches") or []:
                total += dispatch.get("aic_charged") or 0.0
            for prior in record.get("prior_attempts") or []:
                total += sum(d.get("aic_charged") or 0.0 for d in prior.get("dispatches") or [])
        return total + sum(d.get("aic_charged") or 0.0 for d in getattr(self, "_open", []))

    def check_ceiling(self, estimate):
        if not self.live:
            return
        spent = self.spent()
        if spent + estimate > self.max_aic:
            raise CeilingReached(
                f"next dispatch est. {estimate:.1f} AIC + {spent:.1f} AIC already spent would "
                f"pass --max-aic {self.max_aic:g}; stopping before it")

    # -- one dispatch -----------------------------------------------------------------------

    def dispatch(self, trial_id, role, stage, prompt, cwd, round_no=0, ledger_op=None):
        """Run one `copilot -p` and return its record (usage, verdict, output text)."""
        model, effort = stage["model"], stage["effort"]
        estimate = stage_estimate(self.exp, self.pricing, role, model)
        self.check_ceiling(estimate)
        session_id = str(uuid.uuid4())
        argv = build_argv(self.exp, self.binary, model, effort, prompt, session_id, role)
        op = ledger_op or LEDGER_OPS[role]
        attempt = self.ledger.record_started(self.run_id, trial_id, op, model, prompt=prompt,
                                             role=role, effort=effort, session_id=session_id)
        started = utc_now()
        result = self.dispatch_runner(argv, str(cwd), self.timeout)
        output = result.get("stdout") if result.get("stdout") is not None else result.get("output")
        output = output or ""
        cls = _al().classify_dispatch(result.get("rc"), result.get("output") or "",
                                      result.get("outcome"))
        self.ledger.record_finished(self.run_id, trial_id, attempt, result.get("outcome"),
                                    result.get("rc"), result.get("output") or "", cls=cls,
                                    duration_s=result.get("duration_s"))
        usage, events_text = None, ""
        for wait in (0, 1, 2, 3):
            time.sleep(wait if self.live and wait else 0)
            events = _sp().confined_read_bytes(
                self.copilot_home, f"session-state/{session_id}/events.jsonl",
                what="copilot session log", missing_ok=True)
            events_text = events.decode("utf-8", "replace") if events is not None else ""
            usage = session_usage(events_text, self.pricing) if events is not None else None
            if usage is not None:
                break
        measured = usage is not None
        record = {
            "role": role, "round": round_no, "model": model, "effort": effort,
            "session_id": session_id, "attempt": attempt, "started": started,
            "duration_s": result.get("duration_s"), "outcome": result.get("outcome"),
            "rc": result.get("rc"), "class": cls, "timed_out": bool(result.get("timed_out")),
            "usage": usage, "aic_charged": round(usage["aic"] if measured else estimate, 4),
            "aic_basis": "measured (est. rates)" if measured else "unmeasured -- estimate charged",
            "contamination": contamination(events_text, self.markers),
            "output_chars": len(output),
        }
        if role == "verifier":
            found = VERIFY_RE.findall(output)
            record["verdict"] = found[-1].lower() if found else None
        elif role == "reviewer":
            found = REVIEW_RE.findall(output)
            record["verdict"] = found[-1].lower() if found else None
        kept = _redact().redact(output, limit=OUTPUT_KEEP_CHARS)
        record["output_redactions"] = kept["redactions"]
        record["_text"] = output
        record["_kept"] = kept["text"]
        return record

    # -- sandboxes --------------------------------------------------------------------------

    def sandbox(self, dest):
        if Path(dest).exists():
            shutil.rmtree(dest)
        return _rb().make_sandbox(self.repo, self.exp["base_commit"], dest,
                                  git_runner=self.git_runner)

    def snapshot(self, sandbox):
        """{path: sha256 | None} for every path that differs from the sandbox's first commit."""
        rb = _rb()
        rc, out = rb.git_sandbox(sandbox, "add", "-A", git_runner=self.git_runner)
        rb._require_ok(rc, out, "git add")
        rc, out = rb.git_sandbox(sandbox, "diff", "--cached", "--name-only", "--no-renames",
                                 sandbox["init"] if isinstance(sandbox, dict) else
                                 rb.sandbox_init_commit(sandbox, git_runner=self.git_runner),
                                 git_runner=self.git_runner)
        rb._require_ok(rc, out, "git diff --name-only")
        snap = {}
        for rel in (line.strip() for line in out.splitlines()):
            if rel:
                path = Path(sandbox) / rel
                snap[rel] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        return snap

    @staticmethod
    def touched(before, after):
        return sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))

    def patch(self, sandbox):
        return _rb().capture_patch(sandbox, git_runner=self.git_runner)

    # -- one trial --------------------------------------------------------------------------

    def run_trial(self, trial):
        task = self.exp["task_defs"][trial["task"]]
        arm = self.exp["arms"][trial["arm"]]
        tid = trial["trial_id"]
        work = self.run_dir / "work" / tid
        box = self.sandbox(work)["path"]
        self._open = []
        # A re-run of a failed trial keeps what the failed attempts cost: their dispatches
        # stay in the record (and in `spent`), never overwritten out of the books.
        previous = self.read_json(f"trials/{tid}.json")
        prior = list((previous or {}).get("prior_attempts") or [])
        if previous and previous.get("dispatches"):
            prior.append({k: previous.get(k) for k in (
                "attempt", "status", "started", "ended", "dispatches")})
        attempt_no = len(prior) + 1
        record = {"trial_id": tid, "task": trial["task"], "arm": trial["arm"],
                  "repeat": trial["repeat"], "position": trial["position"],
                  "shape": arm["shape"], "started": utc_now(), "dispatches": self._open,
                  "fence": [], "verdicts": [], "reworks": 0, "status": "running",
                  "attempt": attempt_no, "prior_attempts": prior}
        out_prefix = f"a{attempt_no}-" if attempt_no > 1 else ""
        stage_no = [0]

        def step(role, prompt, round_no=0, op=None):
            before = self.snapshot(box)
            model_role = role
            if role == "rework":
                model_role = "implementer" if "implementer" in arm["stages"] else "solo"
            d = self.dispatch(tid, model_role, arm["stages"][model_role], prompt, box,
                              round_no=round_no, ledger_op=op)
            after = self.snapshot(box)
            d["touched"] = self.touched(before, after)
            stage_no[0] += 1
            d["output_file"] = f"outputs/{tid}/{out_prefix}{stage_no[0]:02d}-{role}.txt"
            self.write(d["output_file"], d.pop("_kept"))
            text = d.pop("_text")
            self._open.append(d)
            if model_role in READ_ONLY_ROLES and d["touched"]:
                record["fence"].append({"stage": role, "kind": "read-only-stage-wrote",
                                        "paths": d["touched"]})
            if role == "test_author":
                src = [p for p in d["touched"] if not is_test_path(p)]
                if src:
                    record["fence"].append({"stage": role, "kind": "test-author-wrote-source",
                                            "paths": src})
            if model_role == "implementer":
                tests = [p for p in d["touched"] if is_test_path(p)]
                if tests and arm["shape"] == "pipeline":
                    record.setdefault("implementer_edited_tests", []).extend(tests)
            self.say(f"  {tid} {role:<11} {d['model']}/{d['effort']} "
                     f"{d['aic_charged']:.2f} AIC {d.get('duration_s') or 0:.0f}s "
                     f"{d.get('verdict') or d.get('outcome')}")
            return d, text

        def failed(d):
            return d["class"] is not None or d["timed_out"]

        def verdict_point(d, stage):
            patch = self.patch(box)
            name = f"patches/{tid}.{len(record['verdicts'])}-{stage}.diff"
            self.write(name, patch)
            record["verdicts"].append({"stage": stage, "verdict": d.get("verdict"),
                                       "patch_file": name, "patch_sha": sha256_text(patch)})

        status = "complete"
        try:
            if arm["shape"] == "one-shot":
                d, _ = step("solo", prompt_for("solo", task))
                if failed(d):
                    status = "timeout" if d["timed_out"] else "dispatch-failed"
            elif arm["shape"] == "reviewed":
                status = self._reviewed(task, box, step, failed, verdict_point, record)
            else:
                status = self._pipeline(task, box, step, failed, verdict_point, record)
        except CeilingReached as exc:
            status = "stopped"
            record["stop_reason"] = str(exc)
            self.say(f"  {tid} STOPPED: {exc}")
        patch = self.patch(box)
        self.write(f"patches/{tid}.diff", patch)
        contaminated = sorted({m for d in self._open for m in d["contamination"]})
        if contaminated and status in ("complete", "timeout"):
            record["pre_contamination_status"] = status
            status = "contaminated"
        record.update({"status": status, "finished": utc_now(), "patch_file": f"patches/{tid}.diff",
                       "patch_sha": sha256_text(patch), "contamination": contaminated,
                       "aic": round(sum(d["aic_charged"] for d in self._open), 4),
                       "unmeasured_dispatches": sum(1 for d in self._open
                                                    if d["usage"] is None),
                       "wall_s": round(sum(d.get("duration_s") or 0 for d in self._open), 1)})
        record["dispatches"] = list(self._open)
        self._open = []
        self.write(f"trials/{tid}.json", record)
        if not self.keep_work:
            shutil.rmtree(work, ignore_errors=True)
        return record

    def _pipeline(self, task, box, step, failed, verdict_point, record):
        rework = self.exp["rework"]
        d, plan = step("planner", prompt_for("planner", task))
        if failed(d) or not plan.strip():
            return "timeout" if d["timed_out"] else "dispatch-failed"
        d, _ = step("test_author", prompt_for("test_author", task, plan=plan))
        if failed(d):
            return "timeout" if d["timed_out"] else "dispatch-failed"
        test_files = [p for p in d["touched"] if is_test_path(p)]
        d, _ = step("implementer", prompt_for("implementer", task, plan=plan,
                                              test_files=test_files))
        if failed(d):
            return "timeout" if d["timed_out"] else "dispatch-failed"

        def verify(round_no):
            v, text = step("verifier", prompt_for("verifier", task, patch=self.patch(box)),
                           round_no=round_no)
            verdict_point(v, "verifier")
            return v, text

        def redo(findings, source, round_no):
            record["reworks"] += 1
            r, _ = step("rework", prompt_for("implementer", task, plan=plan,
                                             test_files=test_files, findings=findings,
                                             source=source), round_no=round_no, op="retry")
            return r

        v, findings = verify(0)
        if failed(v):
            return "timeout" if v["timed_out"] else "dispatch-failed"
        for n in range(rework["after_verifier_fail"]):
            if v.get("verdict") == "pass":
                break
            r = redo(findings, "verifier", n + 1)
            if failed(r):
                return "timeout" if r["timed_out"] else "dispatch-failed"
            v, findings = verify(n + 1)
            if failed(v):
                return "timeout" if v["timed_out"] else "dispatch-failed"
        if "reviewer" not in self.exp["arms"][record["arm"]]["stages"]:
            return "complete"
        rv, review = step("reviewer", prompt_for("reviewer", task, patch=self.patch(box)))
        verdict_point(rv, "reviewer")
        if failed(rv):
            return "timeout" if rv["timed_out"] else "dispatch-failed"
        for n in range(rework["after_reviewer_reject"]):
            if rv.get("verdict") == "accept":
                break
            r = redo(review, "reviewer", 10 + n)
            if failed(r):
                return "timeout" if r["timed_out"] else "dispatch-failed"
            v, _ = verify(10 + n)
            if failed(v):
                return "timeout" if v["timed_out"] else "dispatch-failed"
        return "complete"

    def _reviewed(self, task, box, step, failed, verdict_point, record):
        """One-shot, then a reviewer gate; each reject buys one solo rework and a re-review."""
        d, _ = step("solo", prompt_for("solo", task))
        if failed(d):
            return "timeout" if d["timed_out"] else "dispatch-failed"
        for n in range(self.exp["rework"]["after_reviewer_reject"] + 1):
            rv, review = step("reviewer", prompt_for("reviewer", task, patch=self.patch(box)),
                              round_no=n)
            verdict_point(rv, "reviewer")
            if failed(rv):
                return "timeout" if rv["timed_out"] else "dispatch-failed"
            if rv.get("verdict") == "accept" or n == self.exp["rework"]["after_reviewer_reject"]:
                break
            record["reworks"] += 1
            r, _ = step("rework", prompt_for("implementer", task, findings=review,
                                             source="reviewer"), round_no=10 + n, op="retry")
            if failed(r):
                return "timeout" if r["timed_out"] else "dispatch-failed"
        return "complete"

    # -- the whole run ----------------------------------------------------------------------

    def run(self, repeats, only=None, grade=True, extend=()):
        self.open_run(repeats, extend=extend)
        done = {r["trial_id"]: r for r in self.records("trials")}
        plan = [t for t in trial_plan(self.exp, repeats)
                if not only or t["trial_id"] in only]
        streak = 0
        for trial in plan:
            previous = done.get(trial["trial_id"])
            if previous and previous["status"] in ("complete", "timeout", "contaminated"):
                continue
            self.say(f"{trial['trial_id']}: arm {trial['arm']} on {trial['task']}")
            record = self.run_trial(trial)
            if record["status"] in ("complete", "timeout") and grade:
                self.grade_trial(record)
            if record["status"] == "stopped":
                self.say("ceiling reached; resume later with --run-id "
                         f"{self.run_id} and a higher --max-aic")
                return 4
            streak = streak + 1 if record["status"] == "dispatch-failed" else 0
            if streak >= FAILURE_STREAK_LIMIT:
                self.say(f"{streak} trials in a row failed to dispatch (network or auth?); "
                         f"stopping. Resume with --run-id {self.run_id}: failed trials re-run "
                         "and keep what their failed attempts cost")
                return 5
        return 0

    def rescan(self, only=None):
        """Re-classify contamination from each dispatch's own session log (read-only) under
        the CURRENT classifier, and re-measure any dispatch that was charged at estimate when
        its log now carries usage (a still-existing source captured late, audited under
        `remeasures`). A changed verdict is written back with an audit entry; a log
        that is gone leaves that dispatch's recorded verdict untouched. Spends nothing.
        -> [(trial_id, before, after, status)] for every trial that changed."""
        changed = []
        for record in self.records("trials"):
            tid = record["trial_id"]
            if only and tid not in only:
                continue
            missing = 0
            remeasured = []
            for d in record.get("dispatches") or []:
                events = _sp().confined_read_bytes(
                    self.copilot_home, f"session-state/{d['session_id']}/events.jsonl",
                    what="copilot session log", missing_ok=True)
                if events is None:
                    missing += 1
                    continue
                text = events.decode("utf-8", "replace")
                d["contamination"] = contamination(text, self.markers)
                if d.get("usage") is None:
                    usage = session_usage(text, self.pricing)
                    if usage is not None:
                        remeasured.append({"session_id": d["session_id"],
                                           "estimate_aic": d["aic_charged"],
                                           "measured_aic": round(usage["aic"], 4)})
                        d.update({"usage": usage, "aic_charged": round(usage["aic"], 4),
                                  "aic_basis": "measured late (rescan; est. rates)"})
            if remeasured:
                record["aic"] = round(sum(d["aic_charged"] for d in record["dispatches"]), 4)
                record["unmeasured_dispatches"] = sum(1 for d in record["dispatches"]
                                                      if d.get("usage") is None)
                record.setdefault("remeasures", []).append({"at": utc_now(),
                                                            "dispatches": remeasured})
            before = record.get("contamination") or []
            after = sorted({m for d in record.get("dispatches") or []
                            for m in d.get("contamination") or []})
            if after == before:
                if remeasured:
                    self.write(f"trials/{tid}.json", record)
                    changed.append((tid, before, after, record["status"]))
                continue
            status = record["status"]
            if status == "contaminated" and not after:
                timed_out = any(d.get("timed_out") for d in record.get("dispatches") or [])
                status = record.get("pre_contamination_status") or (
                    "timeout" if timed_out else "complete")
            elif after and status in ("complete", "timeout"):
                record["pre_contamination_status"] = status
                status = "contaminated"
            record.setdefault("rescans", []).append(
                {"at": utc_now(), "before": before, "after": after,
                 "status_before": record["status"], "status_after": status,
                 "logs_missing": missing})
            record.update({"contamination": after, "status": status})
            self.write(f"trials/{tid}.json", record)
            changed.append((tid, before, after, status))
        return changed

    # -- grading (offline; spends nothing) --------------------------------------------------

    def tester(self, workspace):
        return _ep().verify_runner(workspace, mode=self.exec_mode, timeout=TEST_TIMEOUT_SECONDS)

    def grade_box(self, patch, dest):
        """Fresh base sandbox with `patch` applied -> (path, applied, detail)."""
        box = self.sandbox(dest)["path"]
        if not patch.strip():
            return box, True, "empty patch"
        with tempfile.TemporaryDirectory(prefix="route-exp-patch-") as tmp:
            patch_file = Path(tmp) / "candidate.diff"
            patch_file.write_text(patch, encoding="utf-8")
            rc, out = _rb().git_sandbox(box, "apply", "--whitespace=nowarn", str(patch_file),
                                        git_runner=self.git_runner)
        return box, rc == 0, (out or "").strip()[-2000:]

    def run_oracle(self, task, box, run_tests):
        _sp().confined_write_bytes(box, f"tests/{ORACLE_TEST_NAME}",
                                   task["oracle_text"].encode("utf-8"), what="oracle copy")
        rc, out = run_tests(_unittest_cmd(ORACLE_TEST_NAME))
        parsed = parse_unittest(out)
        expected = oracle_test_count(task["oracle_text"])
        passed = max(0, parsed["ran"] - parsed["failures"] - parsed["errors"] - parsed["skipped"])
        parsed.update({"rc": rc, "expected": expected,
                       "passed": min(passed, expected),
                       "score": (min(passed, expected) / expected) if expected else 0.0})
        return parsed

    @staticmethod
    def _without_oracle(box):
        oracle = Path(box) / "tests" / ORACLE_TEST_NAME
        if oracle.exists():
            oracle.unlink()

    def file_text(self, box, rel, at_init=False):
        if at_init:
            rb = _rb()
            init = rb.sandbox_init_commit(box, git_runner=self.git_runner)
            rc, out = rb.git_sandbox(box, "show", f"{init}:{rel}", git_runner=self.git_runner)
            return out if rc == 0 else None
        path = Path(box) / rel
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None

    def code_metrics(self, box, stats):
        """Complexity before/after for every changed non-test .py file."""
        per_file = {}
        for rel in stats["src_files"]:
            if not rel.endswith(".py"):
                continue
            after = self.file_text(box, rel)
            if after is None:
                per_file[rel] = {"deleted": True}
                continue
            per_file[rel] = complexity_delta(self.file_text(box, rel, at_init=True), after)
        agg = {"parse_errors": sum(1 for m in per_file.values() if m.get("parse_error")),
               "delta_sloc": 0, "delta_cc": 0, "delta_cognitive": 0, "delta_halstead": 0.0,
               "delta_mi": 0.0, "touched_cc_max": 0, "touched_cognitive_max": 0,
               "touched_nesting_max": 0, "touched_length_max": 0, "new_unused_imports": 0,
               "undocumented_new_public": 0, "touched_functions": 0}
        for m in per_file.values():
            if m.get("parse_error") or m.get("deleted"):
                continue
            agg["delta_sloc"] += m["delta"]["sloc"]
            agg["delta_cc"] += m["delta"]["cc_total"]
            agg["delta_cognitive"] += m["delta"]["cognitive_total"]
            agg["delta_halstead"] = round(agg["delta_halstead"] + m["delta"]["halstead_volume"], 1)
            agg["delta_mi"] = round(agg["delta_mi"] + m["delta"]["mi"], 2)
            for key in ("touched_cc_max", "touched_cognitive_max", "touched_nesting_max",
                        "touched_length_max"):
                agg[key] = max(agg[key], m[key])
            agg["new_unused_imports"] += len(m["new_unused_imports"])
            agg["undocumented_new_public"] += len(m["undocumented_new_public"])
            agg["touched_functions"] += len(m["touched_functions"])
        return {"files": per_file, "aggregate": agg}

    def reference(self, task_id):
        """The task's reference solution measured exactly like a candidate (cached per run)."""
        if task_id in self._reference:
            return self._reference[task_id]
        cached = self.read_json(f"reference/{task_id}.json")
        if cached is None:
            task = self.exp["task_defs"][task_id]
            with tempfile.TemporaryDirectory(prefix="route-exp-ref-") as tmp:
                box, applied, detail = self.grade_box(task["reference_text"], Path(tmp) / "g")
                if not applied:
                    raise ConfigError(f"{task_id}: reference.patch does not apply: {detail}")
                stats = diff_stats(task["reference_text"], task)
                cached = {"task": task_id, "diff": stats, "metrics": self.code_metrics(box, stats)}
            self.write(f"reference/{task_id}.json", cached)
        self._reference[task_id] = cached
        return cached

    def arm_tests(self, box, stats):
        """The candidate's own changed test modules that still exist."""
        return [Path(p).name for p in stats["test_files"]
                if Path(p).name.startswith("test") and p.endswith(".py")
                and Path(p).name != ORACLE_TEST_NAME and (Path(box) / p).is_file()]

    def mutation(self, task, box, stats, metrics, oracle, tests, run_tests, seed):
        """-> {considered, killed, score, generated}. A mutant counts only if the ORACLE
        catches it (so it provably changes specified behaviour); the score is the share of
        those the candidate's own tests also catch."""
        limit = int(self.exp["scoring"].get("mutants_per_trial") or 20)
        operators = self.exp["scoring"].get("mutation_operators", "v1")
        pool = []
        for rel, m in sorted(metrics["files"].items()):
            if m.get("parse_error") or m.get("deleted") or not m["touched_functions"]:
                continue
            source = self.file_text(box, rel)
            for mutant in mutants(source, m["touched_functions"], limit, seed, operators):
                pool.append((rel, source, mutant))
        random.Random(seed).shuffle(pool)
        pool = pool[:limit]
        base_bad = oracle["failures"] + oracle["errors"]
        considered = killed = 0
        for rel, source, mutant in pool:
            target = Path(box) / rel
            try:
                target.write_text(mutant["source"], encoding="utf-8")
                parsed = parse_unittest(run_tests(_unittest_cmd(ORACLE_TEST_NAME))[1])
                if parsed["failures"] + parsed["errors"] <= base_bad and parsed["ok"] is oracle["ok"]:
                    continue
                considered += 1
                self._without_oracle(box)
                if any(not parse_unittest(run_tests(_unittest_cmd(name))[1])["ok"]
                       for name in tests):
                    killed += 1
                _sp().confined_write_bytes(box, f"tests/{ORACLE_TEST_NAME}",
                                           task["oracle_text"].encode("utf-8"), what="oracle copy")
            finally:
                target.write_text(source, encoding="utf-8")
        return {"generated": len(pool), "considered": considered, "killed": killed,
                "score": (killed / considered) if considered else None}

    def grade_trial(self, record):
        task = self.exp["task_defs"][record["task"]]
        tid = record["trial_id"]
        patch = self.read_text(record["patch_file"]) or ""
        stats = diff_stats(patch, task)
        grade = {"trial_id": tid, "task": record["task"], "arm": record["arm"],
                 "repeat": record["repeat"], "graded": utc_now(), "diff": stats,
                 "patch_sha": sha256_text(patch)}
        with tempfile.TemporaryDirectory(prefix="route-exp-grade-") as tmp:
            box, applied, detail = self.grade_box(patch, Path(tmp) / "g")
            grade["applied"] = applied
            if not applied:
                grade.update({"apply_error": detail, "oracle": {"score": 0.0, "ok": False},
                              "regression": {"green": False}, "own_tests": {},
                              "metrics": None, "mutation": None})
            else:
                run_tests = self.tester(box)
                grade["metrics"] = self.code_metrics(box, stats)
                tests = self.arm_tests(box, stats)
                own = {}
                for name in tests:
                    rc, out = run_tests(_unittest_cmd(name))
                    own[name] = parse_unittest(out)
                grade["own_tests"] = {
                    "modules": own, "count": sum(p["ran"] for p in own.values()),
                    "green": bool(own) and all(p["ok"] for p in own.values())}
                if self.full_regression:
                    rc, out = run_tests(_unittest_cmd())
                    reg = {"full": parse_unittest(out)}
                else:
                    reg = {m: parse_unittest(run_tests(_unittest_cmd(m))[1])
                           for m in task["regression"]}
                grade["regression"] = {"modules": reg,
                                       "green": all(p["ok"] for p in reg.values())}
                grade["oracle"] = self.run_oracle(task, box, run_tests)
                seed = int(self.exp.get("seed") or 0) + int(grade["patch_sha"][:8], 16)
                if not tests or not grade["own_tests"]["green"]:
                    grade["mutation"] = {"generated": 0, "considered": 0, "killed": 0,
                                         "score": 0.0,
                                         "note": "no own tests" if not tests else
                                                 "own tests red on the candidate"}
                else:
                    grade["mutation"] = self.mutation(task, box, stats, grade["metrics"],
                                                      grade["oracle"], tests, run_tests, seed)
        grade["verdicts"] = self.grade_verdicts(task, record)
        grade["reference"] = self.reference(record["task"])
        self.write(f"grades/{tid}.json", grade)
        o = grade["oracle"]
        self.say(f"  graded {tid}: oracle {o.get('passed', 0)}/{o.get('expected', '?')} "
                 f"regression {'green' if grade['regression']['green'] else 'RED'}")
        return grade

    def grade_verdicts(self, task, record):
        """Each verifier/reviewer verdict scored against the oracle ON THE PATCH IT SAW."""
        cache, out = {}, []
        for point in record.get("verdicts") or []:
            if point["patch_sha"] not in cache:
                patch = self.read_text(point["patch_file"]) or ""
                with tempfile.TemporaryDirectory(prefix="route-exp-verdict-") as tmp:
                    box, applied, _ = self.grade_box(patch, Path(tmp) / "g")
                    cache[point["patch_sha"]] = (
                        self.run_oracle(task, box, self.tester(box))["score"] == 1.0
                        if applied else False)
            truth = cache[point["patch_sha"]]
            said_ok = point["verdict"] in ("pass", "accept")
            out.append({**point, "oracle_green": truth,
                        "correct": None if point["verdict"] is None else said_ok == truth,
                        "incorrect_acceptance": bool(said_ok and not truth),
                        "incorrect_rejection": bool(point["verdict"] is not None
                                                    and not said_ok and truth)})
        return out

    # -- gate probe -------------------------------------------------------------------------

    def gate_stages(self):
        return gate_stages(self.exp)

    def probe_plan(self):
        return probe_plan(self.exp)

    def probe(self, only=None):
        """Show each gate stage a known-bad (naive) and known-good (reference) patch in a
        fresh base sandbox -- the oracle is never present -- and record its verdict. The
        result measures each gate's sensitivity and specificity; it never enters QS."""
        if self.read_json("run.json") is None:
            raise ConfigError(f"no run {self.run_id} under {self.store_dir}")
        gates = self.gate_stages()
        for key, (role, model, effort), task_id, kind, n in self.probe_plan():
            if only and key not in only:
                continue
            existing = self.read_json(f"probes/{key}.json")
            if existing and existing.get("verdict") is not None:
                continue
            task = self.exp["task_defs"][task_id]
            patch = task[f"{kind}_text"]
            with tempfile.TemporaryDirectory(prefix="route-exp-probe-") as tmp:
                box, applied, detail = self.grade_box(patch, Path(tmp) / "g")
                if not applied:
                    raise ConfigError(f"{task_id}: {kind} patch does not apply: {detail}")
                before = self.snapshot(box)
                try:
                    d = self.dispatch(key, role, {"model": model, "effort": effort},
                                      prompt_for(role, task, patch=patch), box)
                except CeilingReached as exc:
                    self.say(f"  probe {key} STOPPED: {exc}")
                    return 4
                wrote = self.touched(before, self.snapshot(box))
            d.pop("_text")
            d.pop("_kept")
            verdict = d.get("verdict")
            record = {"key": key, "role": role, "model": model, "effort": effort,
                      "arms": gates[(role, model, effort)], "task": task_id, "kind": kind,
                      "repeat": n, "verdict": verdict,
                      "correct": None if verdict is None else
                      (verdict in ("pass", "accept")) == (kind == "reference"),
                      "wrote": wrote, "dispatches": [d]}
            self.write(f"probes/{key}.json", record)
            self.say(f"  probe {key} {role} {model}: {kind} -> {verdict or 'UNPARSED'} "
                     f"{d['aic_charged']:.2f} AIC")
        return 0

    # -- blind judges -----------------------------------------------------------------------

    def judge_groups(self):
        """{(task, repeat): {arm: trial}} over graded, uncontaminated trials of the
        PREREGISTERED arms. A post-hoc extension arm is never judged: re-judging a group with
        an extra candidate would replace the preregistered judgments it was decided on."""
        groups = {}
        arms = set(self.preregistered_arms())
        for record in self.records("trials"):
            if record["status"] in ("complete", "timeout") and record["arm"] in arms:
                groups.setdefault((record["task"], record["repeat"]), {})[record["arm"]] = record
        return groups

    def consistency_groups(self, groups):
        """The deterministic share of (task, repeat) groups every judge sees a second time."""
        fraction = float((self.exp.get("judging") or {}).get("consistency_fraction") or 0)
        keys = sorted(groups)
        count = round(fraction * len(keys))
        return set(random.Random(f"{self.exp.get('seed')}:consistency").sample(keys, count))

    def judge(self, only=None):
        manifest = self.read_json("run.json")
        if manifest is None:
            raise ConfigError(f"no run {self.run_id} under {self.store_dir}")
        groups = {k: v for k, v in self.judge_groups().items() if len(v) >= 2}
        retest = self.consistency_groups(groups)
        passes = [(k, "") for k in sorted(groups)] + [(k, "-c") for k in sorted(retest)]
        for (task_id, rep), suffix in passes:
            trials = groups[(task_id, rep)]
            task = self.exp["task_defs"][task_id]
            for j_index, judge in enumerate(self.exp.get("judges") or []):
                key = f"{task['short']}-r{rep}-j{j_index}{suffix}"
                if only and key not in only:
                    continue
                if self._judge_one(task, rep, trials, j_index, judge, key, bool(suffix)) == 4:
                    return 4
        return 0

    def _judge_one(self, task, rep, trials, j_index, judge, key, retest):
        existing = self.read_json(f"judges/{key}.json")
        arms = sorted(trials)
        if existing and existing.get("parsed") and sorted(existing["arms"]) == arms:
            return 0
        rng = random.Random(f"{self.exp.get('seed')}:{key}")
        shuffled = arms[:]
        rng.shuffle(shuffled)
        labels = {LABELS[i]: arm for i, arm in enumerate(shuffled)}
        candidates = [(label, self.read_text(trials[arm]["patch_file"]) or "")
                      for label, arm in labels.items()]
        mode = self.exp["scoring"].get("quality_mode", "overall")
        prompt = (judge_prompt_rubric_rank(task, candidates) if mode == "rubric_rank"
                  else judge_prompt(task, candidates))
        try:
            with tempfile.TemporaryDirectory(prefix="route-exp-judge-") as cwd:
                d = self.dispatch(key, "judge", judge, prompt, cwd)
        except CeilingReached as exc:
            self.say(f"  judge {key} STOPPED: {exc}")
            return 4
        text = d.pop("_text")
        d.pop("_kept")
        ranking = None
        if mode == "rubric_rank":
            parsed = parse_judge_rubric_rank(text, labels, len(task.get("rubric") or [1]))
            scores, ranking = (parsed["scores"], parsed["ranking"]) if parsed else (None, None)
        else:
            scores = parse_judge(text, labels)
        record = {"key": key, "task": task["id"], "repeat": rep, "judge_index": j_index,
                  "model": judge["model"], "labels": labels, "arms": arms,
                  "parsed": scores is not None, "scores": scores or {},
                  "dispatches": [d]}
        if mode == "rubric_rank":
            record.update({"mode": mode, "ranking": ranking})
        if retest:
            record["consistency"] = True
        self.write(f"judges/{key}.json", record)
        self.write(f"outputs/judges/{key}.txt",
                   _redact().redact(text, limit=OUTPUT_KEEP_CHARS)["text"])
        self.say(f"  judge {key} {judge['model']}: "
                 f"{'parsed' if scores else 'UNPARSED -- excluded'} "
                 f"{d['aic_charged']:.2f} AIC")
        return 0


JUDGE_KEYS = ("correctness", "readability", "design", "tests", "scope", "overall")


def parse_judge(text, labels):
    """{arm: {criterion: 1..10}} from a judge response, or None if it is not usable."""
    decoder = json.JSONDecoder()
    for start in [m.start() for m in re.finditer(r"\{", text or "")]:
        try:
            obj, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        cands = obj.get("candidates") if isinstance(obj, dict) else None
        if not isinstance(cands, dict):
            continue
        out = {}
        for label, arm in labels.items():
            entry = cands.get(label)
            if not isinstance(entry, dict):
                return None
            row = {}
            for key in JUDGE_KEYS:
                value = entry.get(key)
                if not isinstance(value, (int, float)) or not 1 <= value <= 10:
                    return None
                row[key] = float(value)
            row["rationale"] = str(entry.get("rationale") or "")[:400]
            out[arm] = row
        return out
    return None


# ---------------------------------------------------------------------------------------------
# Scoring, statistics and the preregistered decision


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def violations(trial, grade):
    """Discipline violations, each counted once per occurrence -> (count, [descriptions])."""
    found = []
    diff = grade.get("diff") or {}
    found += [f"out-of-scope: {p}" for p in diff.get("out_of_scope", [])]
    found += [f"guardrail {k} x{n}" for k, n in sorted((diff.get("guardrails") or {}).items())]
    found += [f"{f['kind']} ({f['stage']})" for f in trial.get("fence", [])]
    agg = ((grade.get("metrics") or {}).get("aggregate")) or {}
    if agg.get("parse_errors"):
        found.append(f"parse errors x{agg['parse_errors']}")
    if agg.get("new_unused_imports"):
        found.append(f"new unused imports x{agg['new_unused_imports']}")
    if diff.get("todos_added"):
        found.append(f"TODO/FIXME added x{diff['todos_added']}")
    if not grade.get("applied", True):
        found.append("patch does not apply to base")
    return len(found), found


def simplicity(grade):
    ref = grade.get("reference") or {}
    rd, rm = ref.get("diff") or {}, ((ref.get("metrics") or {}).get("aggregate")) or {}
    d, m = grade.get("diff") or {}, ((grade.get("metrics") or {}).get("aggregate")) or {}
    if not m:
        return 0.0
    ref_loc = rd.get("src_added", 0) + rd.get("src_removed", 0)
    arm_loc = d.get("src_added", 0) + d.get("src_removed", 0)
    excess_loc = max(0, arm_loc - ref_loc)
    excess_cc = max(0, m.get("delta_cc", 0) - rm.get("delta_cc", 0))
    return clamp(1 - 0.5 * excess_loc / max(10, ref_loc)
                 - 0.5 * excess_cc / max(3, abs(rm.get("delta_cc", 0))))


def probe_summary(records):
    """Per gate stage: sensitivity (share of naive patches rejected) and specificity (share of
    reference patches accepted) over parsed verdicts."""
    out = {}
    for r in records:
        g = out.setdefault((r["role"], r["model"], r["effort"]), {
            "role": r["role"], "model": r["model"], "effort": r["effort"], "arms": r["arms"],
            "naive": 0, "rejected_naive": 0, "reference": 0, "accepted_reference": 0,
            "unparsed": 0, "wrote": 0, "aic": 0.0})
        g["aic"] = round(g["aic"] + sum(d["aic_charged"] for d in r["dispatches"]), 4)
        g["wrote"] += 1 if r.get("wrote") else 0
        if r["verdict"] is None:
            g["unparsed"] += 1
            continue
        ok = r["verdict"] in ("pass", "accept")
        if r["kind"] == "naive":
            g["naive"] += 1
            g["rejected_naive"] += 0 if ok else 1
        else:
            g["reference"] += 1
            g["accepted_reference"] += 1 if ok else 0
    for g in out.values():
        g["sensitivity"] = g["rejected_naive"] / g["naive"] if g["naive"] else None
        g["specificity"] = (g["accepted_reference"] / g["reference"]
                            if g["reference"] else None)
    return [out[k] for k in sorted(out)]


def simplicity_basis(ex, grades):
    """{task: pseudo-reference} for the `median` simplicity basis: the median source-line
    change and median ΔCC over every SOLVED candidate of that task (all arms) plus the
    reference itself, so one unusually lean or verbose reference does not set the bar."""
    out = {}
    for task_id in ex.exp["tasks"]:
        ref = ex.reference(task_id) or {}
        sizes = [((ref.get("diff") or {}).get("src_added", 0)
                  + (ref.get("diff") or {}).get("src_removed", 0),
                  (((ref.get("metrics") or {}).get("aggregate")) or {}).get("delta_cc", 0))]
        for g in grades.values():
            agg = ((g.get("metrics") or {}).get("aggregate")) or {}
            if g.get("task") == task_id and (g.get("oracle") or {}).get("score") == 1.0 and agg:
                sizes.append((g["diff"]["src_added"] + g["diff"]["src_removed"],
                              agg.get("delta_cc", 0)))
        out[task_id] = {"diff": {"src_added": statistics.median(s for s, _ in sizes),
                                 "src_removed": 0},
                        "metrics": {"aggregate": {"delta_cc": statistics.median(
                            c for _, c in sizes)}},
                        "basis": "median", "candidates": len(sizes)}
    return out


def judge_quality(judge_records):
    """{(task, repeat, arm): mean 0..1 across parsed judges}. An `overall` judgment counts as
    its normalised overall score; a rubric_rank judgment as half its checklist pass share and
    half its normalised rank (best = 1, worst = 0). Consistency re-judgments never count."""
    acc = {}
    for record in judge_records:
        if not record.get("parsed") or record.get("consistency"):
            continue
        ranking = record.get("ranking")
        for arm, row in record["scores"].items():
            if ranking:
                k = len(ranking)
                rank = (k - 1 - ranking.index(arm)) / (k - 1) if k > 1 else 1.0
                value = 0.5 * row["rubric_share"] + 0.5 * rank
            else:
                value = (row["overall"] - 1) / 9
            acc.setdefault((record["task"], record["repeat"], arm), []).append(value)
    return {key: sum(v) / len(v) for key, v in acc.items()}


def kendall_w(rankings):
    """Kendall's coefficient of concordance for m complete rankings of the same n items
    (0 = no agreement, 1 = identical), or None when m < 2 or n < 2."""
    m = len(rankings)
    n = len(rankings[0]) if rankings else 0
    if m < 2 or n < 2:
        return None
    totals = {item: 0 for item in rankings[0]}
    for ranking in rankings:
        for position, item in enumerate(ranking):
            totals[item] += position + 1
    mean = m * (n + 1) / 2
    spread = sum((t - mean) ** 2 for t in totals.values())
    return 12 * spread / (m * m * (n ** 3 - n))


def judge_agreement(judge_records):
    """Rank agreement among rubric_rank judges, and test-retest reliability of each judge
    against its own consistency re-judgment. -> dict, all None when nothing is ranked."""
    ranked = [r for r in judge_records if r.get("parsed") and r.get("ranking")]
    first = {r["key"]: r for r in ranked if not r.get("consistency")}
    groups = {}
    for r in first.values():
        groups.setdefault((r["task"], r["repeat"]), []).append(r["ranking"])
    ws = [w for w in (kendall_w(v) for v in groups.values()
                      if len({tuple(sorted(x)) for x in v}) == 1) if w is not None]
    retest, top = [], []
    for r in ranked:
        if not r.get("consistency"):
            continue
        orig = first.get(r["key"][:-2])
        if not orig or sorted(orig["ranking"]) != sorted(r["ranking"]):
            continue
        items = orig["ranking"]
        rho = spearman([items.index(a) for a in items], [r["ranking"].index(a) for a in items])
        if rho is not None:
            retest.append(rho)
        top.append(1.0 if orig["ranking"][0] == r["ranking"][0] else 0.0)
    return {"kendall_w_mean": _mean(ws), "groups": len(ws),
            "retest_pairs": len(retest) or len(top), "retest_spearman_mean": _mean(retest),
            "retest_top_pick_agreement": _mean(top)}


def score_trial(trial, grade, quality, scoring, drop=()):
    """-> the per-trial scorecard row, including the composite QS (0..100). A component in
    `drop` is left out and the remaining weights renormalise, exactly as for a missing one."""
    weights = scoring["weights"]
    oracle = grade.get("oracle") or {}
    reg_green = bool((grade.get("regression") or {}).get("green"))
    n_viol, viol = violations(trial, grade)
    components = {
        "correctness": float(oracle.get("score") or 0.0),
        "quality": quality,
        "test_strength": (grade.get("mutation") or {}).get("score"),
        "simplicity": simplicity(grade),
        "discipline": max(0.0, 1 - float(scoring.get("discipline_penalty", 0.25)) * n_viol),
    }
    for key in drop:
        components[key] = None
    present = {k: v for k, v in components.items() if v is not None}
    total_w = sum(weights[k] for k in present)
    weighted = sum(weights[k] * v for k, v in present.items()) / total_w if total_w else 0.0
    gate = 1.0 if reg_green else float(scoring.get("regression_gate", 0.5))
    qs = 100 * gate * weighted
    aic = trial.get("aic") or 0.0
    return {"trial_id": trial["trial_id"], "task": trial["task"], "arm": trial["arm"],
            "repeat": trial["repeat"], "status": trial["status"],
            "solved": components["correctness"] == 1.0 and reg_green,
            "components": components, "missing": sorted(set(components) - set(present)),
            "regression_green": reg_green, "violations": viol, "qs": round(qs, 2),
            "aic": aic, "value": round(qs / aic, 3) if aic else None,
            "wall_s": trial.get("wall_s"), "dispatches": len(trial.get("dispatches") or []),
            "reworks": trial.get("reworks", 0)}


def wilson(successes, n, z=1.959964):
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _percentile(sorted_values, q):
    if not sorted_values:
        return None
    pos = q * (len(sorted_values) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def bootstrap_mean(rows, iterations, confidence, seed):
    """Task-stratified bootstrap CI of the mean QS: resample within each task."""
    by_task = {}
    for row in rows:
        by_task.setdefault(row["task"], []).append(row["qs"])
    if not by_task:
        return (None, None)
    rng = random.Random(seed)
    means = []
    for _ in range(iterations):
        sample = []
        for values in by_task.values():
            sample += [rng.choice(values) for _ in values]
        means.append(sum(sample) / len(sample))
    means.sort()
    alpha = (1 - confidence) / 2
    return (_percentile(means, alpha), _percentile(means, 1 - alpha))


def paired_gap(rows_a, rows_b, iterations, confidence, seed):
    """Mean QS gap a - b over (task, repeat) pairs both arms completed, with a bootstrap CI."""
    b = {(r["task"], r["repeat"]): r["qs"] for r in rows_b}
    diffs = [r["qs"] - b[(r["task"], r["repeat"])] for r in rows_a
             if (r["task"], r["repeat"]) in b]
    if not diffs:
        return {"pairs": 0, "mean": None, "ci": (None, None)}
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs)
                   for _ in range(iterations))
    alpha = (1 - confidence) / 2
    mean = sum(diffs) / len(diffs)
    sd = (math.sqrt(sum((x - mean) ** 2 for x in diffs) / (len(diffs) - 1))
          if len(diffs) > 1 else None)
    return {"pairs": len(diffs), "mean": mean, "sd": sd,
            "ci": (_percentile(means, alpha), _percentile(means, 1 - alpha))}


def spearman(xs, ys):
    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            for k in range(i, j + 1):
                out[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return out

    if len(xs) < 3:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return round(cov / (sx * sy), 3) if sx and sy else None


POWER_Z = 1.959964 + 0.841621  # two-sided 95% + 80% power


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _pct(values, q):
    """Nearest-rank percentile (q in 0..1) of the non-null values, or None."""
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    return values[max(0, min(len(values) - 1, math.ceil(q * len(values)) - 1))]


def decide(arm_rows, per_arm, scoring):
    """The preregistered rule: eligible arms (solve rate >= min_solve_rate); the QS leader;
    every eligible arm statistically tied with it (gap <= equivalence_margin OR the paired
    bootstrap CI of the gap contains 0); the winner is the cheapest tied arm."""
    it = int(scoring.get("bootstrap_iterations", 2000))
    conf = float(scoring.get("confidence", 0.95))
    margin = float(scoring.get("equivalence_margin", 5.0))
    eligible = [a for a, s in per_arm.items()
                if s["n"] and s["solve_rate"] >= float(scoring.get("min_solve_rate", 0.0)) - 1e-9]
    if not eligible:
        return {"winner": None, "reason": "no arm met the minimum solve rate",
                "eligible": [], "tied": [], "leader": None, "gaps": {}}
    leader = max(eligible, key=lambda a: (per_arm[a]["qs_mean"], -per_arm[a]["aic_mean"]))
    gaps, tied = {}, [leader]
    for arm in eligible:
        if arm == leader:
            continue
        gap = paired_gap(arm_rows[leader], arm_rows[arm], it, conf, seed=hash_seed(leader, arm))
        gaps[arm] = gap
        lo, hi = gap["ci"]
        if (gap["mean"] is not None and gap["mean"] <= margin) or (
                lo is not None and lo <= 0 <= hi):
            tied.append(arm)
    winner = min(tied, key=lambda a: (per_arm[a]["aic_mean"], -per_arm[a]["qs_mean"]))
    cheapest = winner
    band = scoring.get("cost_tie_pct")
    if band is not None:
        # preregistered time tie-break: among tied arms whose mean AIC is within `band` % of
        # the cheapest, the fastest by median wall time wins
        near = [a for a in tied
                if per_arm[a]["aic_mean"] <= per_arm[cheapest]["aic_mean"] * (1 + band / 100)]
        winner = min(near, key=lambda a: (per_arm[a].get("wall_s_median") or math.inf,
                                          per_arm[a]["aic_mean"]))
    reason = (f"{leader} leads on quality score; " +
              (f"{', '.join(a for a in tied if a != leader)} statistically tied with it; "
               if len(tied) > 1 else "no arm is tied with it; ") +
              f"{cheapest} is the cheapest of the tied set")
    if winner != cheapest:
        reason += (f"; {winner} costs within {band:g}% of it and is faster (median wall time), "
                   "so it wins the time tie-break")
    elif band is not None:
        reason += f" (no tied arm within {band:g}% of its cost is faster)"
    return {"winner": winner, "leader": leader, "eligible": sorted(eligible),
            "tied": sorted(tied), "gaps": gaps, "reason": reason}


def hash_seed(*parts):
    return int(sha256_text(":".join(parts))[:8], 16)


def pareto(per_arm):
    arms = [a for a, s in per_arm.items() if s["n"]]
    front = []
    for a in arms:
        dominated = any(per_arm[b]["qs_mean"] >= per_arm[a]["qs_mean"]
                        and per_arm[b]["aic_mean"] <= per_arm[a]["aic_mean"]
                        and (per_arm[b]["qs_mean"] > per_arm[a]["qs_mean"]
                             or per_arm[b]["aic_mean"] < per_arm[a]["aic_mean"])
                        for b in arms if b != a)
        if not dominated:
            front.append(a)
    return sorted(front)


def build_report(ex, arms=None, drop=(), view="preregistered"):
    """The scorecard for one run: per-arm metrics, statistics and the decision.

    The default view scores the PREREGISTERED arms exactly as preregistered. When the run was
    extended with post-hoc arms, `extended` carries a second view over every arm; if judge
    quality covers some of those arms and not others it is dropped for ALL of them there, so
    no arm is ranked on a component another arm was never scored on."""
    scoring = ex.exp["scoring"]
    manifest = ex.read_json("run.json") or {}
    prereg = ex.preregistered_arms()
    extensions = [e["arm"] for e in manifest.get("extensions") or []
                  if e["arm"] in ex.exp["arms"]]
    arms = sorted(arms if arms is not None else prereg)
    trials = [t for t in ex.records("trials") if t["arm"] in arms]
    grades = {g["trial_id"]: g for g in ex.records("grades")}
    all_judges = ex.records("judges")
    judges = [j for j in all_judges if not j.get("consistency")]
    quality = judge_quality(judges)
    drop_reason = None
    agreement_gate = scoring.get("judge_min_agreement")
    ranked = judge_agreement(all_judges)
    if (scoring.get("quality_mode") == "rubric_rank" and agreement_gate is not None
            and "quality" not in drop and ranked["kendall_w_mean"] is not None
            and ranked["kendall_w_mean"] < agreement_gate):
        drop = tuple(drop) + ("quality",)
        drop_reason = (f"judges agree too little to score on (mean Kendall's W "
                       f"{ranked['kendall_w_mean']:.2f} < the preregistered "
                       f"{agreement_gate:g}), so judge quality is left out for every arm")
    if view == "extended" and "quality" not in drop:
        covered = {quality.get((t["task"], t["repeat"], t["arm"])) is not None
                   for t in trials if t["status"] in ("complete", "timeout")}
        if covered == {True, False}:
            drop = tuple(drop) + ("quality",)
            drop_reason = ("judge quality covers only some arms in this view (extension arms "
                           "are never judged), so it is left out for every arm")
    basis = simplicity_basis(ex, grades) if scoring.get("simplicity_basis") == "median" else {}
    rows, excluded = [], []
    for trial in trials:
        grade = grades.get(trial["trial_id"])
        if trial["status"] not in ("complete", "timeout") or grade is None:
            excluded.append({"trial_id": trial["trial_id"], "status": trial["status"],
                             "reason": "ungraded" if grade is None and trial["status"] in
                             ("complete", "timeout") else trial["status"],
                             "contamination": trial.get("contamination") or []})
            continue
        q = quality.get((trial["task"], trial["repeat"], trial["arm"]))
        scored = dict(grade, reference=basis[trial["task"]]) if trial["task"] in basis else grade
        row = score_trial(trial, scored, q, scoring, drop=drop)
        row["_trial"], row["_grade"] = trial, grade
        rows.append(row)

    arm_rows = {arm: [r for r in rows if r["arm"] == arm] for arm in arms}
    it = int(scoring.get("bootstrap_iterations", 2000))
    conf = float(scoring.get("confidence", 0.95))
    per_arm = {}
    for arm, rs in arm_rows.items():
        n = len(rs)
        solved = sum(1 for r in rs if r["solved"])
        dispatches = [d for r in rs for d in r["_trial"]["dispatches"]]
        by_role = {}
        for d in dispatches:
            role = "rework" if d["role"] == "implementer" and d["round"] else d["role"]
            by_role[role] = round(by_role.get(role, 0.0) + d["aic_charged"], 4)
        tokens = {k: sum(((d.get("usage") or {}).get("tokens") or {}).get(k, 0) for d in dispatches)
                  for k in ("input", "cache_read", "cache_write", "output")}
        verdicts = [v for r in rs for v in r["_grade"].get("verdicts") or []]
        aggs = [((r["_grade"].get("metrics") or {}).get("aggregate")) or {} for r in rs]
        aic_total = sum(r["aic"] for r in rs)
        per_arm[arm] = {
            "arm": arm, "label": ex.exp["arms"][arm].get("label", arm),
            "shape": ex.exp["arms"][arm]["shape"], "n": n, "solved": solved,
            "solve_rate": solved / n if n else 0.0, "solve_ci": wilson(solved, n),
            "qs_mean": _mean([r["qs"] for r in rs]) or 0.0,
            "qs_ci": bootstrap_mean(rs, it, conf, hash_seed(arm)),
            "qs_by_task": {t: _mean([r["qs"] for r in rs if r["task"] == t])
                           for t in ex.exp["tasks"]},
            "components": {k: _mean([r["components"][k] for r in rs])
                           for k in WEIGHT_KEYS},
            "aic_mean": aic_total / n if n else 0.0, "aic_total": round(aic_total, 3),
            "aic_per_solve": round(aic_total / solved, 3) if solved else None,
            "aic_by_role": {k: round(v / n, 3) for k, v in by_role.items()} if n else {},
            "value": round((_mean([r["qs"] for r in rs]) or 0.0) / (aic_total / n), 3)
                     if n and aic_total else None,
            "reported_aiu_total": round(sum((d.get("usage") or {}).get("reported_aiu") or 0
                                            for d in dispatches), 3),
            "unmeasured_dispatches": sum(1 for d in dispatches if d.get("usage") is None),
            "tokens": tokens,
            "reasoning_tokens": sum((d.get("usage") or {}).get("reasoning_tokens") or 0
                                    for d in dispatches),
            "premium_requests": sum((d.get("usage") or {}).get("premium_requests") or 0
                                    for d in dispatches),
            "dispatches_mean": _mean([r["dispatches"] for r in rs]),
            "wall_s_mean": _mean([r["wall_s"] for r in rs]),
            "wall_s_median": _pct([r["wall_s"] for r in rs], 0.5),
            "wall_s_p90": _pct([r["wall_s"] for r in rs], 0.9),
            "aic_median": _pct([r["aic"] for r in rs], 0.5),
            "aic_p90": _pct([r["aic"] for r in rs], 0.9),
            "estimate_charged": {
                "dispatches": sum(1 for d in dispatches if d.get("usage") is None),
                "aic": round(sum(d["aic_charged"] for d in dispatches
                                 if d.get("usage") is None), 3),
                "share": round(sum(d["aic_charged"] for d in dispatches
                                   if d.get("usage") is None) / aic_total, 3)
                         if aic_total else 0.0},
            "efforts": {role: f"{s['model']}/{s['effort']}"
                        for role, s in ex.exp["arms"][arm]["stages"].items()},
            "reworks_mean": _mean([r["reworks"] for r in rs]),
            "regression_green_rate": _mean([1.0 if r["regression_green"] else 0.0 for r in rs]),
            "violations_mean": _mean([len(r["violations"]) for r in rs]),
            "own_tests_mean": _mean([(r["_grade"].get("own_tests") or {}).get("count", 0)
                                     for r in rs]),
            "mutation_mean": _mean([(r["_grade"].get("mutation") or {}).get("score")
                                    for r in rs]),
            "complexity": {k: _mean([a.get(k) for a in aggs]) for k in (
                "delta_sloc", "delta_cc", "delta_cognitive", "delta_halstead", "delta_mi",
                "touched_cc_max", "touched_cognitive_max", "touched_nesting_max",
                "touched_length_max")},
            "diff_lines_mean": _mean([(r["_grade"]["diff"]["src_added"]
                                       + r["_grade"]["diff"]["src_removed"]) for r in rs]),
            "test_lines_mean": _mean([r["_grade"]["diff"]["test_added"] for r in rs]),
            "verdicts": {
                "count": len(verdicts),
                "accuracy": _mean([1.0 if v["correct"] else 0.0 for v in verdicts
                                   if v["correct"] is not None]),
                "incorrect_acceptances": sum(1 for v in verdicts if v["incorrect_acceptance"]),
                "incorrect_rejections": sum(1 for v in verdicts if v["incorrect_rejection"]),
                "unparsed": sum(1 for v in verdicts if v["verdict"] is None)},
        }
    ref = {t: ex.read_json(f"reference/{t}.json") for t in ex.exp["tasks"]}
    agreement = []
    by_item = {}
    for record in judges:
        if record.get("parsed"):
            for arm, row in record["scores"].items():
                by_item.setdefault((record["task"], record["repeat"], arm), {})[
                    record["judge_index"]] = row["overall"]
    pairs = [v for v in by_item.values() if 0 in v and 1 in v]
    agreement = spearman([p[0] for p in pairs], [p[1] for p in pairs])
    decision = decide(arm_rows, per_arm, scoring)
    measured = [a for a in per_arm.values() if a["n"]]
    scored_ids = {r["trial_id"] for r in rows}
    lost = []
    for trial in trials:
        lost += [d for p in trial.get("prior_attempts") or [] for d in p.get("dispatches") or []]
        if trial["trial_id"] not in scored_ids:
            lost += trial.get("dispatches") or []
    failed_spend = {
        "dispatches": len(lost),
        "measured_aic": round(sum(d["aic_charged"] for d in lost if d.get("usage")), 3),
        "estimate_charged_aic": round(sum(d["aic_charged"] for d in lost
                                          if not d.get("usage")), 3)}
    report = {
        "version": RESULT_VERSION, "run_id": ex.run_id, "preregistration": ex.digest,
        "manifest_preregistration": manifest.get("preregistration"),
        "view": view, "arms": arms, "extension_arms": [a for a in extensions if a in arms],
        "dropped_components": sorted(set(drop)), "drop_reason": drop_reason,
        "pricing_cached_date": ex.pricing.get("cached_date"),
        "trials": len(trials), "scored": len(rows), "excluded": excluded,
        "failed_spend": failed_spend,
        "judges": {"records": len(judges), "parsed": sum(1 for j in judges if j.get("parsed")),
                   "spearman_overall": agreement, "pairs": len(pairs),
                   **({"ranked": ranked, "min_agreement": agreement_gate,
                       "consistency_records": len(all_judges) - len(judges)}
                      if ranked["groups"] or ranked["retest_pairs"] else {}),
                   "aic": round(sum(d["aic_charged"] for j in judges
                                    for d in j.get("dispatches") or []), 3)},
        "per_arm": per_arm, "decision": decision, "pareto": pareto(per_arm),
        "quality_leader": max(measured, key=lambda a: (a["qs_mean"], -a["aic_mean"]))["arm"]
        if measured else None,
        "value_leader": max((a for a in measured if a["value"]), key=lambda a: a["value"],
                            default={"arm": None})["arm"],
        "reference": {t: (r or {}).get("metrics", {}).get("aggregate") for t, r in ref.items()},
        "rows": [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows],
        "small_sample": any(a["n"] < 20 for a in measured),
        "max_estimate_share": float(scoring.get("max_estimate_share", 0.10)),
        "extended_sections": bool(scoring.get("extended_report")),
    }
    probes = ex.records("probes")
    if probes and view == "preregistered":
        report["probe"] = probe_summary(probes)
    if view == "preregistered" and extensions:
        report["extended"] = build_report(ex, arms=prereg + extensions, view="extended")
        report["extended"]["extensions"] = [
            {k: e.get(k) for k in ("arm", "file", "digest", "reason", "added_to_run",
                                   "trials_before")}
            for e in manifest.get("extensions") or []]
    return report


def _f(value, digits=1, suffix=""):
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}{suffix}"
    return f"{value}{suffix}"


def _spread_lines(report, arms):
    """Cost/time spread, estimate-charged share and detection sensitivity (v2 reports)."""
    lines = ["## Cost and time spread (per trial)", "",
              "| Arm | Models/effort | AIC median | AIC p90 | Wall s median | Wall s p90 | "
              "Charged at estimate |", "|---|---|---|---|---|---|---|"]
    for a in arms:
        est = a.get("estimate_charged") or {}
        flag = (f"{est.get('dispatches', 0)} dispatches, {_f(est.get('aic'), 2)} AIC "
                f"({_f(100 * (est.get('share') or 0), 0)}%)") if est.get("dispatches") else "none"
        if (est.get("share") or 0) > report.get("max_estimate_share", 0.10):
            flag += " **⚠ cost partly estimated**"
        efforts = ", ".join(f"{k} {v}" for k, v in (a.get("efforts") or {}).items())
        lines.append(f"| {a['arm']} | {efforts} | {_f(a.get('aic_median'), 2)} | "
                     f"{_f(a.get('aic_p90'), 2)} | {_f(a.get('wall_s_median'), 0)} | "
                     f"{_f(a.get('wall_s_p90'), 0)} | {flag} |")
    lines.append("")
    gaps = (report.get("decision") or {}).get("gaps") or {}
    sds = [g["sd"] for g in gaps.values() if g.get("sd") is not None and g.get("pairs")]
    if sds:
        pairs = min(g["pairs"] for g in gaps.values() if g.get("pairs"))
        sd = statistics.median(sds)
        mde = POWER_Z * sd / math.sqrt(pairs)
        lines += ["## Sensitivity", "",
                  f"Median paired QS-gap SD {_f(sd, 2)} over {pairs} paired attempts: the "
                  f"smallest QS gap this run detects with 80% power at 95% confidence is "
                  f"about **{_f(mde, 1)} points**. Gaps smaller than that are ties by "
                  "construction, not evidence of equality.",
                  "", "| Gap to detect | Paired attempts needed |", "|---|---|"]
        for target in (2, 3, 5):
            lines.append(f"| {target} QS | {math.ceil((POWER_Z * sd / target) ** 2)} |")
        lines.append("")
    return lines



def render_report(report, nested=False):
    arms = [a for a in report["per_arm"].values()]
    if nested:
        lines = ["## Post-hoc extension view -- all arms", "",
                 "NOT part of the preregistered decision. Extension arm(s) "
                 f"{', '.join(report['extension_arms'])} were added after the preregistered "
                 "trials ran, so they also differ in dispatch time (model and service drift "
                 "are uncontrolled)."]
        for e in report.get("extensions") or []:
            lines.append(f"- {e['arm']} ({e['file']}, {e['digest'][:12]}), added "
                         f"{e['added_to_run']} after {e['trials_before']} trials: {e['reason']}")
        if report["dropped_components"]:
            lines += ["", f"Left out for every arm: {', '.join(report['dropped_components'])} "
                      f"-- {report['drop_reason'] or 'requested'}; the remaining weights "
                      "renormalise."]
        lines.append("")
    else:
        lines = [f"# Route experiment -- run {report['run_id']}", ""]
        if report.get("extended"):
            lines += [f"Preregistered arms only ({', '.join(report['arms'])}); post-hoc "
                      "extension arms are scored separately at the end.", ""]
    lines += [
             f"{report['scored']} of {report['trials']} trials scored; "
             f"{len(report['excluded'])} excluded. AIC is token-priced from each session's "
             f"own log at the {report['pricing_cached_date']} rates (est.).", ""]
    fs = report.get("failed_spend") or {}
    if fs.get("dispatches"):
        lines += [f"Failed or excluded attempts: {fs['dispatches']} dispatches, "
                  f"{_f(fs['measured_aic'], 2)} AIC measured + "
                  f"{_f(fs['estimate_charged_aic'], 2)} AIC charged at estimate (no session log). "
                  "Counted against the ceiling; outside every arm's per-trial AIC.", ""]
    d = report["decision"]
    lines += ["## Decision (preregistered rule)" + (", applied post hoc" if nested else ""), "",
              f"**Winner: {d['winner'] or 'none'}** -- {d['reason']}.",
              f"Quality leader {report['quality_leader']}; value leader (QS per AIC) "
              f"{report['value_leader']}; Pareto set (QS vs AIC): "
              f"{', '.join(report['pareto']) or '—'}.", ""]
    if not nested and report["dropped_components"]:
        lines += [f"Left out for every arm: {', '.join(report['dropped_components'])} -- "
                  f"{report['drop_reason'] or 'requested'}; the remaining weights renormalise.",
                  ""]
    if report["small_sample"]:
        lines += ["> Small sample: fewer than 20 scored trials per arm. Intervals are wide; "
                  "treat the ranking as directional.", ""]
    lines += ["## Outcome and cost", "",
              "| Arm | Route | n | Solved (95% CI) | QS mean (95% CI) | AIC/trial | AIC/solve | "
              "QS per AIC | Dispatches | Wall s |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for a in arms:
        lo, hi = a["solve_ci"]
        qlo, qhi = a["qs_ci"]
        lines.append(
            f"| {a['arm']} | {a['label']} | {a['n']} | {a['solved']}/{a['n']} "
            f"({_f(lo * 100, 0)}–{_f(hi * 100, 0)}%) | {_f(a['qs_mean'])} "
            f"({_f(qlo)}–{_f(qhi)}) | {_f(a['aic_mean'], 2)} | {_f(a['aic_per_solve'], 2)} | "
            f"{_f(a['value'], 2)} | {_f(a['dispatches_mean'])} | {_f(a['wall_s_mean'], 0)} |")
    lines += ["", "## Score components (means, 0..1)", "",
              "| Arm | Correctness | Judge quality | Test strength | Simplicity | Discipline | "
              "Regression green | Violations/trial |", "|---|---|---|---|---|---|---|---|"]
    for a in arms:
        c = a["components"]
        lines.append(f"| {a['arm']} | {_f(c['correctness'], 2)} | {_f(c['quality'], 2)} | "
                     f"{_f(c['test_strength'], 2)} | {_f(c['simplicity'], 2)} | "
                     f"{_f(c['discipline'], 2)} | {_f(a['regression_green_rate'], 2)} | "
                     f"{_f(a['violations_mean'], 2)} |")
    lines += ["", "## Code metrics (means per trial; deltas vs base)", "",
              "| Arm | Src lines ± | Test lines + | Own tests | ΔSLOC | ΔCC | ΔCognitive | "
              "Max CC touched | Max nesting | ΔHalstead V | ΔMI |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for a in arms:
        c = a["complexity"]
        lines.append(f"| {a['arm']} | {_f(a['diff_lines_mean'])} | {_f(a['test_lines_mean'])} | "
                     f"{_f(a['own_tests_mean'])} | {_f(c['delta_sloc'])} | {_f(c['delta_cc'])} | "
                     f"{_f(c['delta_cognitive'])} | {_f(c['touched_cc_max'])} | "
                     f"{_f(c['touched_nesting_max'])} | {_f(c['delta_halstead'], 0)} | "
                     f"{_f(c['delta_mi'], 2)} |")
    lines += ["", "Reference solutions: " + "; ".join(
        f"{t}: ΔSLOC {_f((m or {}).get('delta_sloc'))}, ΔCC {_f((m or {}).get('delta_cc'))}"
        for t, m in report["reference"].items()), ""]
    if report.get("extended_sections"):
        lines += _spread_lines(report, arms)

    lines += ["## Spend detail", "",
              "| Arm | AIC total | Reported AIU | Unmeasured | Input tok | Cache-read tok | "
              "Output tok | Reasoning tok | Premium req | AIC by stage (per trial) |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for a in arms:
        t = a["tokens"]
        stages = ", ".join(f"{k} {v:.2f}" for k, v in sorted(a["aic_by_role"].items()))
        lines.append(f"| {a['arm']} | {_f(a['aic_total'], 2)} | {_f(a['reported_aiu_total'], 2)} | "
                     f"{a['unmeasured_dispatches']} | {t['input']:,} | {t['cache_read']:,} | "
                     f"{t['output']:,} | {a['reasoning_tokens']:,} | {a['premium_requests']} | "
                     f"{stages} |")
    pipes = [a for a in arms if a["shape"] != "one-shot" and a["verdicts"]["count"]]
    if pipes:
        lines += ["", "## Pipeline gates vs the hidden oracle", "",
                  "| Arm | Verdicts | Accuracy | Incorrect accepts | Incorrect rejects | "
                  "Unparsed | Reworks/trial |", "|---|---|---|---|---|---|---|"]
        for a in pipes:
            v = a["verdicts"]
            lines.append(f"| {a['arm']} | {v['count']} | {_f(v['accuracy'], 2)} | "
                         f"{v['incorrect_acceptances']} | {v['incorrect_rejections']} | "
                         f"{v['unparsed']} | {_f(a['reworks_mean'], 2)} |")
    j = report["judges"]
    lines += ["", f"Judges: {j['parsed']}/{j['records']} parsed, {_f(j['aic'], 2)} AIC; "
              f"inter-judge Spearman on overall = {_f(j['spearman_overall'], 2)} "
              f"over {j['pairs']} items."]
    rk = j.get("ranked")
    if rk:
        gate = j.get("min_agreement")
        lines += ["", f"Rank agreement: mean Kendall's W {_f(rk['kendall_w_mean'], 2)} over "
                  f"{rk['groups']} groups" + (f" (preregistered floor {gate:g}: "
                  f"{'met' if (rk['kendall_w_mean'] or 0) >= gate else 'NOT met -- judge quality left out'})"
                  if gate is not None and rk["kendall_w_mean"] is not None else "") +
                  f". Test-retest on {j.get('consistency_records', 0)} re-judgments: rank "
                  f"Spearman {_f(rk['retest_spearman_mean'], 2)}, same top pick "
                  f"{_f(100 * rk['retest_top_pick_agreement'] if rk['retest_top_pick_agreement'] is not None else None, 0, '%')}."]
    probe = report.get("probe")
    if probe:
        lines += ["", "## Gate probe (known-bad naive vs known-good reference patches)", "",
                  "| Gate | Model/effort | Arms | Sensitivity (rejects naive) | "
                  "Specificity (accepts reference) | Unparsed | AIC |",
                  "|---|---|---|---|---|---|---|"]
        for g in probe:
            lines.append(f"| {g['role']} | {g['model']}/{g['effort']} | {', '.join(g['arms'])} | "
                         f"{g['rejected_naive']}/{g['naive']} ({_f(g['sensitivity'], 2)}) | "
                         f"{g['accepted_reference']}/{g['reference']} "
                         f"({_f(g['specificity'], 2)}) | {g['unparsed']} | {_f(g['aic'], 2)} |")
    if d["gaps"]:
        lines += ["", "Paired QS gaps vs the leader: " + "; ".join(
            f"{arm}: {_f(g['mean'])} (CI {_f(g['ci'][0])}–{_f(g['ci'][1])}, {g['pairs']} pairs)"
            for arm, g in sorted(d["gaps"].items()))]
    if report["excluded"]:
        lines += ["", "Excluded: " + ", ".join(
            f"{e['trial_id']} ({e['reason']}{': ' + ','.join(e['contamination']) if e['contamination'] else ''})"
            for e in report["excluded"])]
    if nested:
        lines = [("#" + line) if line.startswith("## ") and i else line
                 for i, line in enumerate(lines)]
    elif report.get("extended"):
        lines += ["", render_report(report["extended"], nested=True).rstrip("\n")]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------------------------
# validate: every task's oracle is red on base and green on its reference (spends nothing)


def validate_tasks(ex, only=None):
    """-> [{task, base_oracle, ref_oracle, base_regression, ref_regression, valid}].

    `task_requirements` in the definition can also demand a minimum oracle size and a
    `naive.patch` -- a plausible wrong solution that must apply and score strictly between 0
    and 1 on the oracle, which proves the oracle discriminates partial work."""
    req = ex.exp.get("task_requirements") or {}
    rows = []
    for task_id in ex.exp["tasks"]:
        if only and task_id not in only:
            continue
        task = ex.exp["task_defs"][task_id]
        row = {"task": task_id, "problems": []}
        expected = oracle_test_count(task["oracle_text"])
        row["oracle_tests"] = expected
        if expected < int(req.get("min_oracle_tests") or 0):
            row["problems"].append(f"oracle has {expected} tests, needs "
                                   f"{req['min_oracle_tests']}")
        if req.get("naive_patch") and not task.get("naive_text"):
            row["problems"].append("no naive.patch")
        cases = [("base", ""), ("ref", task["reference_text"])]
        if task.get("naive_text"):
            cases.append(("naive", task["naive_text"]))
        for label, patch in cases:
            with tempfile.TemporaryDirectory(prefix="route-exp-validate-") as tmp:
                box, applied, detail = ex.grade_box(patch, Path(tmp) / "g")
                if not applied:
                    row[f"{label}_error"] = detail
                    continue
                run_tests = ex.tester(box)
                row[f"{label}_regression"] = all(
                    parse_unittest(run_tests(_unittest_cmd(m))[1])["ok"] for m in task["regression"])
                oracle = ex.run_oracle(task, box, run_tests)
                row[f"{label}_oracle"] = f"{oracle['passed']}/{oracle['expected']}"
                row[f"{label}_oracle_green"] = oracle["score"] == 1.0
                row[f"{label}_score"] = oracle["score"]
        if "naive" in dict(cases):
            if row.get("naive_error"):
                row["problems"].append("naive.patch does not apply")
            elif not 0 < row.get("naive_score", 0) < 1:
                row["problems"].append(f"naive.patch scores {row.get('naive_oracle')} on the "
                                       "oracle; it must pass some tests and fail others")
        row["valid"] = (not row["problems"]
                        and not row.get("base_error") and not row.get("ref_error")
                        and row.get("base_oracle_green") is False
                        and row.get("ref_oracle_green") is True
                        and row.get("base_regression") is True
                        and row.get("ref_regression") is True)
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------------------------
# demo: the whole pipeline against a fixture repo and a stub CLI (offline, spends nothing)

DEMO_BASE = '''"""Tiny fixture module for the route-experiment demo."""


def pct(part, whole):
    """`part` as a whole-number percentage of `whole`."""
    return round(100 * part / whole)
'''

DEMO_FIXED = DEMO_BASE.replace(
    "    return round(100 * part / whole)",
    "    if not whole:\n        return 0\n    return round(100 * part / whole)")

DEMO_VERBOSE = DEMO_BASE.replace(
    "    return round(100 * part / whole)",
    "    result = 0\n    if whole is not None:\n        if whole != 0:\n            result = "
    "round(100 * part / whole)\n        else:\n            result = 0\n    return result")

DEMO_REGRESSION = '''import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))
import calc  # noqa: E402


class PctTests(unittest.TestCase):
    def test_quarter(self):
        self.assertEqual(calc.pct(1, 4), 25)


if __name__ == "__main__":
    unittest.main()
'''

DEMO_ORACLE = DEMO_REGRESSION.replace("class PctTests", "class OracleTests").replace(
    "    def test_quarter(self):\n        self.assertEqual(calc.pct(1, 4), 25)",
    "    def test_zero_whole(self):\n        self.assertEqual(calc.pct(3, 0), 0)\n\n"
    "    def test_half(self):\n        self.assertEqual(calc.pct(1, 2), 50)\n\n"
    "    def test_zero_part(self):\n        self.assertEqual(calc.pct(0, 5), 0)")

DEMO_STRONG_TESTS = DEMO_REGRESSION.replace("class PctTests", "class ZeroTests").replace(
    "    def test_quarter(self):\n        self.assertEqual(calc.pct(1, 4), 25)",
    "    def test_zero_whole(self):\n        self.assertEqual(calc.pct(7, 0), 0)\n\n"
    "    def test_third(self):\n        self.assertEqual(calc.pct(1, 3), 33)")

DEMO_WEAK_TESTS = DEMO_REGRESSION.replace("class PctTests", "class ZeroTests").replace(
    "    def test_quarter(self):\n        self.assertEqual(calc.pct(1, 4), 25)",
    "    def test_runs(self):\n        calc.pct(1, 3)")

DEMO_PROMPT = """Fix `pct` in `bin/calc.py`: `pct(part, 0)` raises ZeroDivisionError; it must return 0.
Add a unit test. Run: `python3 -m unittest discover -s tests -p "test_calc*.py"`.
"""

DEMO_STUB = r'''#!__PYTHON__
"""Stub `copilot` for the route-experiment demo: acts by role, writes a fake session log."""
import json, sys
from pathlib import Path

HOME = Path(__HOME__)
FILES = json.loads(__FILES__)
argv = sys.argv[1:]
model = argv[argv.index("--model") + 1]
session = argv[argv.index("--session-id") + 1]
prompt = argv[argv.index("-p") + 1]

def put(rel, text):
    path = Path.cwd() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)

fix = FILES["verbose"] if "sol" in model else FILES["fixed"]
tests = FILES["weak"] if "sol" in model else FILES["strong"]
if "# CANDIDATE" in prompt:
    labels = [line.split()[-1] for line in prompt.splitlines() if line.startswith("# CANDIDATE ")]
    out = {"candidates": {l: {"correctness": 8, "readability": 7 + i % 2, "design": 7,
                              "tests": 6 + i % 3, "scope": 9, "overall": 6 + (i * 3 + len(model)) % 4,
                              "rationale": "stub"} for i, l in enumerate(labels)}}
    reply, tokens = json.dumps(out), (60000, 1500)
elif "YOUR JOB: PLANNER" in prompt:
    reply, tokens = "## Plan\n1. Guard `whole == 0` in pct.\n2. Test pct(x, 0) == 0.", (40000, 2000)
elif "YOUR JOB: TEST AUTHOR" in prompt:
    put("tests/test_calc_zero.py", tests); reply, tokens = "tests/test_calc_zero.py", (30000, 800)
elif "YOUR JOB: IMPLEMENTER" in prompt:
    put("bin/calc.py", fix); reply, tokens = "done", (50000, 1200)
elif "YOUR JOB: VERIFIER" in prompt:
    reply, tokens = "All requirements met.\nVERIFY VERDICT=pass", (30000, 600)
elif "YOUR JOB: REVIEWER" in prompt:
    reply, tokens = "Looks right.\nREVIEW VERDICT=accept", (35000, 900)
else:
    put("bin/calc.py", fix); put("tests/test_calc_zero.py", tests)
    reply, tokens = "Fixed and tested.", (90000, 3000)
detail = {"input": {"tokenCount": tokens[0] // 5}, "cache_read": {"tokenCount": tokens[0] - tokens[0] // 5},
          "cache_write": {"tokenCount": 0}, "output": {"tokenCount": tokens[1]}}
events = [
    {"type": "session.model_change", "data": {"newModel": model, "reasoningEffort": "high"}},
    {"type": "session.shutdown", "data": {"totalNanoAiu": 0, "totalPremiumRequests": 1,
        "tokenDetails": detail, "modelMetrics": {model: {"requests": {"count": 1},
        "usage": {"reasoningTokens": 100}, "totalNanoAiu": 0, "tokenDetails": detail}}}},
]
log = HOME / "session-state" / session
log.mkdir(parents=True, exist_ok=True)
(log / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
print(reply)
'''


def build_demo(root, pricing):
    """Fixture repo + one-task experiment dir + stub CLI under `root` -> (exp_dir, stub, home)."""
    rb = _rb()
    repo = Path(root) / "repo"
    (repo / "bin").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "bin" / "calc.py").write_text(DEMO_BASE, encoding="utf-8")
    (repo / "tests" / "test_calc.py").write_text(DEMO_REGRESSION, encoding="utf-8")
    for args in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "fixture base")):
        rb._require_ok(*rb.git_sandbox(repo, *args), f"demo git {args[0]}")
    base = rb.git_sandbox(repo, "rev-parse", "HEAD")[1].strip()
    (repo / "bin" / "calc.py").write_text(DEMO_FIXED, encoding="utf-8")
    reference = rb.git_sandbox(repo, "diff", "--no-color")[1]
    rb._require_ok(*rb.git_sandbox(repo, "checkout", "--", "bin/calc.py"), "demo git checkout")

    real = json.loads((EXPERIMENT_DIR / "experiment.json").read_text(encoding="utf-8"))
    exp_dir = Path(root) / "experiment"
    task_dir = exp_dir / "tasks" / "D1-pct-zero"
    task_dir.mkdir(parents=True)
    (task_dir / "prompt.md").write_text(DEMO_PROMPT, encoding="utf-8")
    (task_dir / "oracle.py").write_text(DEMO_ORACLE, encoding="utf-8")
    (task_dir / "reference.patch").write_text(reference, encoding="utf-8")
    (task_dir / "task.json").write_text(json.dumps({
        "id": "D1-pct-zero", "title": "Guard pct against a zero whole", "kind": "bugfix",
        "source_files": ["bin/calc.py"], "allowed_paths": ["bin/calc.py", "tests/"],
        "regression": ["test_calc.py"],
        "guardrails": [{"kind": "subprocess", "regex": r"\bimport subprocess\b"}],
        "prompt": "prompt.md", "oracle": "oracle.py", "reference": "reference.patch"}, indent=2))
    demo = dict(real, base_commit=base, repeats=1, tasks=["D1-pct-zero"], max_aic=10000)
    demo["scoring"] = dict(real["scoring"], bootstrap_iterations=200, mutants_per_trial=6)
    (exp_dir / "experiment.json").write_text(json.dumps(demo, indent=2), encoding="utf-8")

    home = Path(root) / "copilot-home"
    home.mkdir()
    files = {"fixed": DEMO_FIXED, "verbose": DEMO_VERBOSE,
             "strong": DEMO_STRONG_TESTS, "weak": DEMO_WEAK_TESTS}
    stub = Path(root) / "copilot-stub"
    stub.write_text(DEMO_STUB.replace("__PYTHON__", sys.executable)
                    .replace("__HOME__", repr(str(home)))
                    .replace("__FILES__", repr(json.dumps(files))), encoding="utf-8")
    stub.chmod(0o755)
    return exp_dir, repo, stub, home


def run_demo(out=sys.stdout, keep=None):
    pricing = load_pricing()
    with tempfile.TemporaryDirectory(prefix="route-exp-demo-") as tmp:
        root = Path(keep) if keep else Path(tmp)
        exp_dir, repo, stub, home = build_demo(root, pricing)
        exp, digest = load_experiment(exp_dir, pricing)
        ex = Experiment(exp, digest, pricing, root / "store", "demo-run", binary=str(stub),
                        copilot_home=home, repo=repo, exec_mode="trusted-host", live=True,
                        max_aic=exp["max_aic"], out=out)
        print("DEMO -- fixture repo, stub CLI (spends nothing), trusted-host test runs.\n",
              file=out)
        for row in validate_tasks(ex):
            print(f"validate {row['task']}: base oracle {row.get('base_oracle')} -> reference "
                  f"{row.get('ref_oracle')}  {'VALID' if row['valid'] else 'INVALID'}", file=out)
        ex.run(repeats=1)
        ex.judge()
        print("", file=out)
        print(render_report(build_report(ex)), file=out)
    return 0


# ---------------------------------------------------------------------------------------------
# CLI


def render_plan(plan, exp):
    lines = [f"Route experiment plan -- {len(plan['trials'])} trials "
             f"({len(exp['tasks'])} tasks x {len(exp['arms'])} arms x {plan['repeats']} repeats), "
             f"preregistration {plan['preregistration'][:12]}", ""]
    for arm, est in plan["per_arm"].items():
        a = exp["arms"][arm]
        stages = ", ".join(f"{r}={s['model']}/{s['effort']}" for r, s in a["stages"].items())
        lines.append(f"  {arm} {a['shape']:<9} est. {est['min']:.1f}-{est['max']:.1f} AIC/trial, "
                     f"{est['dispatches_min']}-{est['dispatches_max']} dispatches  [{stages}]")
    a = plan["aic"]
    lines += ["", f"Trials: est. {a['trials_min']:.0f}-{a['trials_max']:.0f} AIC; judges est. "
              f"{a['judges']:.0f} AIC ({plan['dispatches']['judge']} dispatches); total est. "
              f"{a['total_min']:.0f}-{a['total_max']:.0f} AIC against the preregistered "
              f"ceiling {plan['ceiling']}."]
    if plan.get("probe"):
        p = plan["probe"]
        lines.append(f"Gate probe (separate command): est. {p['aic']:.0f} AIC "
                     f"({p['dispatches']} dispatches); with it, est. "
                     f"{a['total_min'] + p['aic']:.0f}-{a['total_max'] + p['aic']:.0f} AIC.")
    lines += [f"Basis: {plan['basis']}.", "", "Dispatch order (counterbalanced):"]
    for t in plan["trials"]:
        lines.append(f"  {t['trial_id']}")
    return "\n".join(lines)


def _session(args, pricing, live=False):
    exp, digest = load_experiment(Path(args.experiment_dir), pricing)
    store = Path(args.store_dir) if args.store_dir else default_store_dir()
    run_id = getattr(args, "run", None) or getattr(args, "run_id", None) or \
        _kc().generate_run_id()
    ex = Experiment(exp, digest, pricing, store, run_id,
                    binary=getattr(args, "bin", None) or "copilot",
                    copilot_home=getattr(args, "copilot_home", None),
                    exec_mode=args.exec_mode, live=live,
                    max_aic=getattr(args, "max_aic", None),
                    keep_work=getattr(args, "keep_work", False),
                    full_regression=getattr(args, "full_regression", False))
    manifest = ex.read_json("run.json")
    if manifest is not None:
        ex.activate(manifest)
    return ex


def _only(raw):
    return {x.strip() for x in raw.split(",") if x.strip()} if raw else None


def _require_spend_gate(args, parser):
    if args.live == args.dry_run:
        parser.error("choose exactly one of --live (spends AIC) or --dry-run (spawns nothing)")
    if args.live:
        if args.max_aic is None or args.max_aic <= 0:
            parser.error("--live requires an explicit positive --max-aic ceiling")
        if shutil.which(args.bin or "copilot") is None:
            parser.error(f"copilot CLI not found: {args.bin or 'copilot'}")


def cmd_run(args, parser, pricing):
    _require_spend_gate(args, parser)
    if args.full_regression and args.exec_mode == "enforced":
        parser.error("--full-regression needs --exec-mode trusted-host: suite modules that "
                     "drive the kit drivers re-enter the verify boundary, which refuses nesting")
    ex = _session(args, pricing, live=args.live)
    repeats = args.repeats or int(ex.exp["repeats"])
    extend = sorted(_only(args.extend_arms) or ())
    for arm_id in extend:
        if arm_id not in (ex.exp.get("extensions") or {}):
            raise ConfigError(f"no extension arm {arm_id!r} under "
                              f"{ex.exp['dir']}/extensions/")
    only = _only(args.only)
    if args.dry_run:
        merge_extensions(ex.exp, [a for a in extend if a not in ex.exp["arms"]])
        plan = build_plan(ex.exp, ex.digest, pricing, repeats)
        print(render_plan(plan, ex.exp).split("\nDispatch order")[0])
        print("\nDRY RUN -- nothing spawned, nothing written. First dispatch of each arm:")
        seen = set()
        for t in plan["trials"]:
            if t["arm"] in seen or (only and t["trial_id"] not in only):
                continue
            seen.add(t["arm"])
            arm = ex.exp["arms"][t["arm"]]
            role = "planner" if arm["shape"] == "pipeline" else "solo"
            task = ex.exp["task_defs"][t["task"]]
            argv = build_argv(ex.exp, args.bin or "copilot", arm["stages"][role]["model"],
                              arm["stages"][role]["effort"], "<PROMPT>", "<uuid>", role)
            print(f"\n{t['trial_id']} ({role}, cwd = fresh sandbox of {ex.exp['base_commit'][:12]}):")
            print("  " + " ".join(shlex.quote(a) for a in argv))
            print(f"  prompt: {len(prompt_for(role, task))} chars, sha "
                  f"{sha256_text(prompt_for(role, task))[:12]}")
        return 0
    if args.max_aic > float(ex.exp.get("max_aic") or args.max_aic):
        print(f"note: --max-aic {args.max_aic:g} is above the preregistered "
              f"{ex.exp['max_aic']} AIC", file=sys.stderr)
    print(f"run {ex.run_id} -> {ex.run_dir}")
    rc = ex.run(repeats, only=only, grade=not args.no_grade, extend=extend)
    print(f"spent so far: {ex.spent():.2f} AIC (token-priced, est. rates)")
    return rc


def cmd_judge(args, parser, pricing):
    _require_spend_gate(args, parser)
    ex = _session(args, pricing, live=args.live)
    if args.dry_run:
        groups = ex.judge_groups()
        print(f"DRY RUN -- {len(groups)} (task, repeat) groups x "
              f"{len(ex.exp.get('judges') or [])} judges; nothing spawned.")
        for (task, rep), trials in sorted(groups.items()):
            print(f"  {task} r{rep}: arms {', '.join(sorted(trials))}")
        return 0
    rc = ex.judge(only=_only(args.only))
    print(f"spent so far: {ex.spent():.2f} AIC")
    return rc


def cmd_probe(args, parser, pricing):
    _require_spend_gate(args, parser)
    ex = _session(args, pricing, live=args.live)
    plan = ex.probe_plan()
    if args.dry_run:
        est = probe_estimate(ex.exp, ex.pricing)["aic"]
        print(f"DRY RUN -- {len(plan)} gate probes over {len(ex.gate_stages())} gate stages, "
              f"est. {est:.1f} AIC; nothing spawned.")
        for key, (role, model, effort), *_ in plan:
            print(f"  {key}: {role} {model}/{effort}")
        return 0
    rc = ex.probe(only=_only(args.only))
    print(f"spent so far: {ex.spent():.2f} AIC")
    return rc


def cmd_grade(args, parser, pricing):
    if args.full_regression and args.exec_mode == "enforced":
        parser.error("--full-regression needs --exec-mode trusted-host (the boundary refuses "
                     "nesting)")
    ex = _session(args, pricing)
    only = _only(args.only)
    for record in ex.records("trials"):
        if record["status"] in ("complete", "timeout") and (not only or record["trial_id"] in only):
            ex.grade_trial(record)
    return 0


def cmd_rescan(args, parser, pricing):
    ex = _session(args, pricing)
    if ex.read_json("run.json") is None:
        parser.error(f"no run {args.run} under {ex.store_dir}")
    changed = ex.rescan(only=_only(args.only))
    for tid, before, after, status in changed:
        print(f"{tid}: contamination {before or '[]'} -> {after or '[]'}; status {status}")
    regrade = [tid for tid, _, _, status in changed if status in ("complete", "timeout")]
    if regrade:
        print(f"grade the trials now in scope: grade --run {ex.run_id} --only {','.join(regrade)}")
    if not changed:
        print("no contamination verdict changed")
    return 0


def cmd_report(args, parser, pricing):
    ex = _session(args, pricing)
    if ex.read_json("run.json") is None:
        parser.error(f"no run {args.run} under {ex.store_dir}")
    report = build_report(ex)
    if report["manifest_preregistration"] != report["preregistration"]:
        print("WARNING: the experiment definition changed since this run started; the "
              "report re-scores recorded trials under the CURRENT scoring block.", file=sys.stderr)
    print(json.dumps(report, indent=2, default=str) if args.json else render_report(report))
    return 0


def cmd_list(args, parser, pricing):
    store = Path(args.store_dir) if args.store_dir else default_store_dir()
    if not store.is_dir():
        print(f"no runs under {store}")
        return 0
    for run in sorted(p for p in store.iterdir() if (p / "run.json").is_file()):
        trials = len(list((run / "trials").glob("*.json"))) if (run / "trials").is_dir() else 0
        print(f"{run.name}  {trials} trials")
    return 0


def cmd_validate(args, parser, pricing):
    ex = _session(args, pricing)
    ex.run_dir = Path(tempfile.mkdtemp(prefix="route-exp-validate-"))
    try:
        rows = validate_tasks(ex, only=_only(args.only))
    finally:
        shutil.rmtree(ex.run_dir, ignore_errors=True)
    for row in rows:
        print(f"{row['task']}: base oracle {row.get('base_oracle', row.get('base_error'))} "
              f"(regression {'green' if row.get('base_regression') else 'RED'}) -> reference "
              f"{row.get('ref_oracle', row.get('ref_error'))} (regression "
              f"{'green' if row.get('ref_regression') else 'RED'})"
              + (f"; naive {row.get('naive_oracle', row.get('naive_error'))}"
                 if "naive_oracle" in row or "naive_error" in row else "")
              + f"; {row['oracle_tests']} oracle tests  "
              f"{'VALID' if row['valid'] else 'INVALID'}"
              + "".join(f"\n  - {p}" for p in row["problems"]))
    return 0 if all(r["valid"] for r in rows) else 3


def build_parser():
    parser = argparse.ArgumentParser(
        prog="route_experiment.py", description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--experiment-dir", default=str(EXPERIMENT_DIR))
    parser.add_argument("--store-dir", help="run store (default: the `routeruns` runtime store)")
    parser.add_argument("--exec-mode", choices=("enforced", "trusted-host"), default="enforced",
                        help="test runs inside the OS boundary (default) or, explicitly, not")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("validate", help="oracles red on base, green on reference")
    p.add_argument("--only", help="comma-separated task ids")
    p = sub.add_parser("plan", help="trial matrix and AIC estimate; spends nothing")
    p.add_argument("--repeats", type=int)
    p.add_argument("--json", action="store_true")
    p.add_argument("--extend-arms", help="include these post-hoc extension arms")
    for name in ("run", "judge", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--live", action="store_true")
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--max-aic", type=float)
        p.add_argument("--bin", help="copilot executable (default: `copilot` on PATH)")
        p.add_argument("--copilot-home", help="where session logs land (default ~/.copilot)")
        p.add_argument("--only", help="comma-separated trial ids (run) or judge keys (judge)")
        if name == "run":
            p.add_argument("--run-id", help="resume this run")
            p.add_argument("--repeats", type=int)
            p.add_argument("--keep-work", action="store_true")
            p.add_argument("--extend-arms", help="comma-separated POST-HOC arms from "
                           "extensions/ to add to this run (recorded in run.json, reported "
                           "apart from the preregistered decision)")
            p.add_argument("--no-grade", action="store_true")
            p.add_argument("--full-regression", action="store_true")
        else:
            p.add_argument("--run", required=True)
    p = sub.add_parser("grade")
    p.add_argument("--run", required=True)
    p.add_argument("--only")
    p.add_argument("--full-regression", action="store_true")
    p = sub.add_parser("rescan", help="re-classify contamination from the session logs")
    p.add_argument("--run", required=True)
    p.add_argument("--only")
    p = sub.add_parser("report")
    p.add_argument("--run", required=True)
    p.add_argument("--json", action="store_true")
    sub.add_parser("list")
    p = sub.add_parser("demo", help="whole pipeline offline: fixture repo, stub CLI")
    p.add_argument("--keep", help="build the demo under this empty directory and keep it")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "demo":
        return run_demo(keep=args.keep)
    pricing = load_pricing()
    try:
        if args.cmd == "plan":
            exp, digest = load_experiment(Path(args.experiment_dir), pricing)
            merge_extensions(exp, sorted(_only(args.extend_arms) or ()))
            plan = build_plan(exp, digest, pricing, args.repeats or int(exp["repeats"]))
            print(json.dumps(plan, indent=2) if args.json else render_plan(plan, exp))
            return 0
        handler = {"run": cmd_run, "judge": cmd_judge, "probe": cmd_probe,
                   "grade": cmd_grade, "report": cmd_report,
                   "list": cmd_list, "validate": cmd_validate,
                   "rescan": cmd_rescan}[args.cmd]
        return handler(args, parser, pricing)
    except ConfigError as exc:
        print(f"route_experiment: {exc}", file=sys.stderr)
        return 2
    except _ep().SandboxUnavailable as exc:
        print(f"route_experiment: no OS execution boundary on this host ({exc}); pass "
              f"--exec-mode trusted-host to run tests unconfined, knowingly", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
