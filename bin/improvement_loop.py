#!/usr/bin/env python3
"""Draft bounded, falsifiable, data-only policy candidates -- and nothing else (step D21).

    improvement_loop.py evidence --store-dir DIR --manifest ID [--partition P] [--json]
    improvement_loop.py draft    --job FILE [--json]
    improvement_loop.py demo

WHAT THIS IS. An ORCHESTRATOR. It reads evidence that is allowed to be cited, turns a parent
bundle plus that evidence into candidate drafts, and hands every one of them to
`bin/workflow_eval.py` to be admitted or refused. That evaluator is this repository's one owner
of policy persistence, of the manifest store, and of what a draft may say; this module owns the
walk between them and owns no record at all.

WHAT IT IS NOT, and the distinction the whole file turns on: it is NOT a persistence owner. It
writes no envelope, no proposal file, no preference file, no policy, no manifest, no store and
no second ledger. A draft that comes out of here is a payload in memory and on stdout. Making
one into a stored proposal is a separate, reviewed step somebody takes on purpose through the
workbench's own commands, and there is no code path here that shortcuts it. `python3
bin/improvement_loop.py draft --job ...` run a thousand times changes nothing on disk.

NO INFERENCE. Neither drafting mode asks a model anything. `manual` validates drafts a person
wrote; `deterministic` enumerates the neighbouring values of the data dials the allowlist
already carries and words each one from the dial it turns. `proposer` -- the optional model
proposer the plan leaves room for -- is DECLARED so that a reader learns what it would have to
be, and is not wired: `PROPOSER_WIRED` is False, there is no runner parameter anywhere in this
module to hand a dispatcher through, and asking for it refuses. When it is ever built it is a
separately admitted job with its own budget, and it is audit-blind like every other proposer
here -- see `workflow_eval.DRAFT_AUDIT_BLIND_LABEL`.

BOUNDS. Every batch runs under `workflow_eval.draft_budget`, which caps how many candidates may
be admitted and how many may be examined at all, and which refuses a caller asking for a bound
larger than the evaluator's own ceiling. A refused candidate keeps its payload and its reason in
the report: a rejection that vanishes is a rejection nobody can review.

AUTHORITY. A candidate is data. It may set the data dials
`decision_contract.DIFF_PARAMETERS` enumerates and nothing else -- not this module's code, not
the evaluator's rules, not an acceptance criterion, not a permission, not a price, not a skill,
not a lesson, not a benchmark record, and not the audit that judges it. Proposer code and the
final audit are outside candidate authority by construction: neither is reachable from a
payload, because a payload sets dials and every one of those dials is a scalar on an allowlist.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

#: The ways a draft can come to exist. `proposer` is declared and not wired -- see the module
#: docstring and `PROPOSER_WIRED`.
SOURCES = ("manual", "deterministic", "proposer")

#: Whether an optional model proposer exists. It does not. This constant is what the refusal
#: reads, so wiring one would be a visible edit here rather than an accident somewhere else --
#: the precedent `workflow_eval.CONFINED_DISPATCH_WIRED` set.
PROPOSER_WIRED = False

PROPOSER_LABEL = (
    "the optional model proposer is not wired. When it exists it is a separately admitted job "
    "with its own budget, counted at its own scope and never inside a candidate's -- and it is "
    "audit-blind: it never reads the final audit partition, and it never judges its own output. "
    "Nothing in this module calls a model, and it has no seam through which one could be passed")

NOT_A_DECISION_LABEL = (
    "a drafted candidate is a question, not an answer: it has not been evaluated, reviewed, "
    "approved or applied, and this module cannot do any of those. It writes nothing")

#: The keys a job file may carry. Closed, so a field nobody reads is a refusal rather than a
#: silently ignored instruction.
JOB_KEYS = ("source", "bundle", "evaluation", "evidence", "counterevidence", "scope",
            "rollback", "dials", "drafts", "known", "budget")

#: The keys a job's `budget` may carry. Both are LOWER bounds on the evaluator's ceiling; see
#: `workflow_eval.draft_budget`, which refuses anything above it.
BUDGET_KEYS = ("max_candidates", "max_effort")

_MODS = {}


class LoopError(ValueError):
    """The caller's setup is wrong. A CANDIDATE being wrong is a verdict, never this."""


def _sibling(name):
    if name not in _MODS:
        path = Path(__file__).resolve().with_name(f"{name}.py")
        spec = importlib.util.spec_from_file_location(f"polytropos_loop_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODS[name] = module
    return _MODS[name]


def _we():
    return _sibling("workflow_eval")


def _dc():
    """The decision contract instance the EVALUATOR reads.

    `bin/` is not a package, so two loaders of one file produce two sets of classes and two
    `ContractError`s. Reading the contract through `workflow_eval` means this module and the
    module that judges its output are looking at exactly one set.
    """
    return _we()._dc()


def _dp():
    return _sibling("decision_policy")


# ---- the evidence side: read-only, and blind to the audit --------------------------------------

def prepare_evaluation(store_dir, manifest_id, *, partition="promotion"):
    """What a draft may cite, and what stops it -- through the evaluator's own seam.

    Three things happen, all of them in `bin/workflow_eval.py`: `read_manifest` re-derives the
    digest and refuses a file that was rewritten after it was written; `require_held_out` is the
    controller that decides whether a partition may be cited at all; `manifest_ref` builds the
    pointer a candidate carries. None of the three is re-implemented here and none of them is a
    write.

    A READER, so it reports blockers instead of raising over them: "this material cannot be
    cited, and here is every reason" is the answer a drafter needs, and an exception would lose
    all but the first. The caller's own mistakes -- a partition a proposer may not read, a
    manifest that is not there or no longer digests to what it says -- still raise, because
    those are not facts about the evidence.
    """
    we = _we()
    allowed = we.draft_partitions()
    if partition not in allowed:
        role = we.PARTITION_ROLES.get(partition)
        if role is None:
            raise LoopError(f"unknown partition {partition!r}; the four are "
                            f"{', '.join(we.PARTITIONS)}")
        raise LoopError(
            f"a proposer does not read the {partition!r} partition ({role.get('note', '')}); it "
            f"may read {', '.join(allowed)}. {we.DRAFT_AUDIT_BLIND_LABEL}")
    manifest = we.read_manifest(store_dir, manifest_id)
    blockers = None
    items = []
    try:
        items = we.require_held_out(store_dir, manifest, partition)
    except we.EvalError as exc:
        blockers = str(exc)
    return {
        "manifest": manifest["id"], "manifest_ref": we.manifest_ref(manifest),
        "partition": partition, "ready": blockers is None, "items": items,
        "blockers": blockers,
        "labels": [we.NOT_ENFORCEMENT_LABEL, we.DRAFT_AUDIT_BLIND_LABEL],
    }


# ---- the drafting side: manual, or a small deterministic search ---------------------------------

def _slug(value):
    """A dial or a value as an identifier fragment. `_ID_RE` allows letters, digits, '.', '_'
    and '-', so a dial's own name passes through and a value is spelled the way JSON spells
    it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = "".join(ch if (ch.isalnum() or ch in "._-") else "-" for ch in str(value))
    return text.strip("-") or "x"


def _neighbours(kind, current, dial):
    """The values a bounded search will try for one dial, in a fixed order.

    Neighbours, never a sweep: a boolean has one other value, a count has the two either side of
    where it is, and a label has the other values the evaluator's own vocabulary carries. An
    unset dial is proposed ON rather than in both directions, because a candidate proposing a
    dial's current effective behaviour is proposing nothing.
    """
    contract = _dc()
    if kind == "boolean":
        return [True] if current is None else [not current]
    if kind == "count":
        if current is None:
            return [1]
        return [v for v in (current + 1, current - 1)
                if 0 <= v <= contract.MAX_PARAMETER_VALUE]
    values = _we().label_vocabulary(dial)
    return [v for v in values if v != current]


def _statements(dial, current, proposed, endpoint, partition):
    """One candidate's hypothesis, falsification and tradeoff, worded from the dial it turns.

    Deterministic and precise: each names the parameter, the value it is moving from and the
    value it is moving to, so two candidates are never two wordings of one claim. The contract
    refuses any two of the three that reduce to the same text, which is the check that keeps a
    falsification from being a restatement -- these are written to satisfy it on their meaning,
    not to slip past it.
    """
    was = "unset" if current is None else json.dumps(current)
    now = json.dumps(proposed)
    return {
        "hypothesis": (
            f"Setting {dial} to {now} where it is now {was} raises the {endpoint} endpoint for "
            f"the scope named below, without raising total resources per accepted task."),
        "falsification": (
            f"Measured on the frozen {partition} cohort, {endpoint} under {dial}={now} fails to "
            f"beat the current {dial}={was} arm by the declared margin, or total resources per "
            f"accepted task rise."),
        "tradeoff": (
            f"Every run in scope pays for {dial}={now}, including the runs where the setting "
            f"changes nothing at all, so whatever it costs is spent on all of them and not only "
            f"on the ones it turns out to help."),
    }


def deterministic_drafts(bundle, *, evaluation, evidence, counterevidence=(), scope=None,
                         rollback=None, dials=None):
    """A small search over the data dials the allowlist carries -> candidate payloads.

    No inference, no ranking and no scoring: it enumerates, words each enumeration from the dial
    it turns, and stops. Whether any of them is admitted is the evaluator's question, asked
    afterwards, and several of these are expected to be refused -- a search that only ever emits
    admissible candidates is a search that has already made the decision.
    """
    contract = _dc()
    parsed = contract.parse_bundle(bundle)
    parent = _dp().bundle_ref(bundle)
    in_force = dict(parsed.parameters)
    allow = contract.DIFF_PARAMETERS
    wanted = sorted(allow) if dials is None else list(dials)
    unknown = sorted(set(wanted) - set(allow))
    if unknown:
        raise LoopError(f"no such data dial(s): {', '.join(repr(u) for u in unknown)}; the "
                        f"allowlist carries {', '.join(sorted(allow))}")
    endpoint = (evaluation or {}).get("endpoint")
    partition = (evaluation or {}).get("partition")
    out = []
    for dial in wanted:
        current = in_force.get(dial)
        for value in _neighbours(allow[dial], current, dial):
            payload = {
                "v": contract.CANDIDATE_VERSION,
                "id": f"draft-{_slug(dial)}-{_slug(value)}",
                "parent": parent,
                "scope": dict(scope) if scope else {
                    "project": parsed.scope["project"],
                    "task_classes": list(parsed.scope["task_classes"]),
                    "intended_uses": list(parsed.scope["intended_uses"])},
                "diff": {dial: value},
                "evaluation": dict(evaluation or {}),
                "evidence": [dict(r) for r in evidence or ()],
                "counterevidence": [dict(r) for r in counterevidence or ()],
                "rollback": dict(rollback) if rollback else {"kind": "legacy",
                                                             "bundle_ref": None},
            }
            payload.update(_statements(dial, current, value, endpoint, partition))
            out.append(payload)
    return out


def _job(value):
    """A drafting job, with a closed key set. Raises: a job is the caller's, not a candidate's."""
    if not isinstance(value, dict):
        raise LoopError(f"a job is an object with {', '.join(JOB_KEYS)}; this is a "
                        f"{type(value).__name__}")
    unknown = sorted(set(value) - set(JOB_KEYS))
    if unknown:
        raise LoopError(f"the job carries {', '.join(repr(u) for u in unknown)}, which nothing "
                        f"here reads; a field nobody reads is an instruction nobody follows")
    source = value.get("source") or "manual"
    if source not in SOURCES:
        raise LoopError(f"source must be one of {', '.join(SOURCES)}, not {source!r}")
    if source == "proposer" or PROPOSER_WIRED:
        raise LoopError(f"source {source!r} would need a model. {PROPOSER_LABEL}")
    budget = value.get("budget") or {}
    if not isinstance(budget, dict):
        raise LoopError(f"the job's budget must be an object with "
                        f"{', '.join(BUDGET_KEYS)}, not {type(budget).__name__}")
    unknown = sorted(set(budget) - set(BUDGET_KEYS))
    if unknown:
        raise LoopError(f"the job's budget carries {', '.join(repr(u) for u in unknown)}; the "
                        f"bounds are {', '.join(BUDGET_KEYS)}")
    return dict(value, source=source, budget=budget)


def run_draft(job):
    """One drafting job -> the evaluator's batch report, plus what this module contributed.

    The report is `workflow_eval.validate_draft_batch`'s, unchanged: which candidates were
    admitted, which were refused and why, every payload kept either way, and the bounds the
    batch ran under. What this adds is the provenance of the batch -- where the drafts came
    from and which parent they were written against -- and the two things a reader of the
    report alone could otherwise assume: that nothing was inferred and that nothing was stored.
    """
    we = _we()
    job = _job(job)
    bundle = job.get("bundle")
    if not isinstance(bundle, dict):
        raise LoopError("the job names no parent bundle; a candidate is always a change TO "
                        "something, and the bundle is what says what is in force now")
    parsed = _dc().parse_bundle(bundle)
    in_force = dict(parsed.parameters)
    if job["source"] == "deterministic":
        drafts = deterministic_drafts(
            bundle, evaluation=job.get("evaluation"), evidence=job.get("evidence"),
            counterevidence=job.get("counterevidence"), scope=job.get("scope"),
            rollback=job.get("rollback"), dials=job.get("dials"))
    else:
        drafts = list(job.get("drafts") or ())
        if job.get("dials"):
            raise LoopError("a manual job lists its drafts; `dials` is what the deterministic "
                            "search enumerates and is not read here")
    budget = we.draft_budget(max_candidates=job["budget"].get("max_candidates"),
                             max_effort=job["budget"].get("max_effort"))
    report = we.validate_draft_batch(drafts, in_force=in_force, budget=budget,
                                     known=job.get("known") or ())
    report["source"] = job["source"]
    report["parent"] = _dp().bundle_ref(bundle)
    report["labels"] = list(report["labels"]) + [NOT_A_DECISION_LABEL, PROPOSER_LABEL]
    return report


# ---- rendering ---------------------------------------------------------------------------------

def render_report(report):
    lines = [f"drafts {report['drafts']} | examined {report['examined']} "
             f"(effort {report['budget']['effort_spent']}/{report['budget']['effort']}) | "
             f"admitted {len(report['admitted'])}/{report['budget']['candidates']} | "
             f"outcome {report['outcome']}"]
    if report["refusals"]:
        lines.append(f"refused for: {', '.join(report['refusals'])}")
    for row in report["candidates"]:
        mark = "ok  " if row["verdict"] == "valid" else f"{row['reason']:<9}"
        lines.append(f"  {mark} {row['id'] or '<unreadable>'}: {row['detail']}")
    for label in report["labels"]:
        lines.append(f"  -- {label}")
    return "\n".join(lines)


def render_evidence(state):
    lines = [f"manifest {state['manifest']} | partition {state['partition']} | "
             f"{'citable' if state['ready'] else 'NOT citable'} | {len(state['items'])} item(s)"]
    if state["blockers"]:
        lines.append(f"  blocked: {state['blockers']}")
    for label in state["labels"]:
        lines.append(f"  -- {label}")
    return "\n".join(lines)


# ---- demo: synthetic, offline, and it spends nothing ---------------------------------------------

def demo_job():
    """A synthetic drafting job. Every version string is read from the contract that owns it;
    no repository, no store, no harness and no model is named or reached."""
    contract = _dc()
    we = _we()
    ledger = we._al()
    kit = we._kc()

    def ref(identity, version):
        return ledger.make_ref(identity, sha=we._sha(identity), version=version)

    bundle = {
        "v": contract.BUNDLE_VERSION,
        "id": "demo-bundle-0",
        "parent": None,
        "scope": {"project": "demo-project", "task_classes": ["demo-class"],
                  "intended_uses": ["proposal-evidence"]},
        "components": {"decision_contract": contract.CONTRACT_VERSION,
                       "task_contract": kit.CONTRACT_VERSION, "provider_contract": None},
        "parameters": {"routing.default_workflow": "reviewed",
                       "recovery.contract_context_files": 2},
        "requirements": {"capabilities": [], "providers": [], "calibration": None},
        "fallback": {"kind": "legacy", "bundle_ref": None},
        "provenance": {"approval_ref": None, "evaluation_ref": None, "rolled_back_from": None},
    }
    return {
        "source": "deterministic",
        "bundle": bundle,
        "evaluation": {"endpoint": "accepted-completion", "partition": "promotion",
                       "manifest_ref": ref("demo-manifest", we.MANIFEST_VERSION)},
        "evidence": [ref("demo-attempt-a", kit.CONTRACT_VERSION),
                     ref("demo-attempt-b", kit.CONTRACT_VERSION)],
        "counterevidence": [ref("demo-attempt-c", kit.CONTRACT_VERSION)],
        "dials": ["routing.default_workflow", "recovery.contract_context_files"],
    }


def cmd_demo(args):
    report = run_draft(demo_job())
    if getattr(args, "json", False):
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_report(report))
        print("\nnothing was dispatched, nothing was written, nothing was spent.")
    return 0


def cmd_draft(args):
    job = json.loads(Path(args.job).read_text(encoding="utf-8"))
    report = run_draft(job)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_report(report))
    return 0 if report["outcome"] != "all-rejected" else 3


def cmd_evidence(args):
    state = prepare_evaluation(args.store_dir, args.manifest, partition=args.partition)
    if args.json:
        print(json.dumps(state, indent=2, sort_keys=True))
    else:
        print(render_evidence(state))
    return 0 if state["ready"] else 3


def build_parser():
    parser = argparse.ArgumentParser(
        description="Draft bounded, falsifiable, data-only policy candidates. It validates "
                    "them through bin/workflow_eval.py, stores nothing, and calls no model.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ev = sub.add_parser("evidence", help="what a draft may cite from one manifest partition")
    p_ev.add_argument("--store-dir", required=True)
    p_ev.add_argument("--manifest", required=True)
    p_ev.add_argument("--partition", default="promotion")
    p_ev.add_argument("--json", action="store_true")
    p_ev.set_defaults(func=cmd_evidence)

    p_dr = sub.add_parser("draft", help="validate a job's drafts against the evaluator's bounds")
    p_dr.add_argument("--job", required=True, help="a JSON job file; see JOB_KEYS")
    p_dr.add_argument("--json", action="store_true")
    p_dr.set_defaults(func=cmd_draft)

    p_demo = sub.add_parser("demo", help="a synthetic offline batch; spends nothing")
    p_demo.add_argument("--json", action="store_true")
    p_demo.set_defaults(func=cmd_demo)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (LoopError, _we().EvalError, _dc().ContractError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
