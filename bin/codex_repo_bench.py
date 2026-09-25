#!/usr/bin/env python3
"""Plan repo-native Codex benchmarks without misrepresenting subscription spend.

Task acquisition is shared with ``repo_bench.py``.  Execution is deliberately not yet
enabled: that engine's live ledger and ceiling are denominated in actual Claude API dollars,
which cannot safely cap an opaque ChatGPT-plan quota.  This module provides an honest,
useful planning surface while the live engine gains a dispatch-count ceiling and a Codex
result ledger.
"""

import argparse
import json
import tempfile
from pathlib import Path

try:  # direct script execution
    import codex_pricing as cp
    import repo_bench as rb
except ModuleNotFoundError:  # package import from tests
    from . import codex_pricing as cp
    from . import repo_bench as rb


def _resolve_candidates(pricing, raw):
    values = rb._split_models(raw)
    if not values:
        raise ValueError("at least one candidate model or tier is required")
    result = []
    for value in values:
        model_id = cp.resolve_model(pricing, value)
        if not pricing["models"][model_id].get("available", True):
            raise ValueError(f"candidate model {model_id!r} is unavailable on this roster")
        if model_id not in result:
            result.append(model_id)
    return result


def _default_judge(pricing, candidates):
    for tier in reversed(cp.TIER_ORDER):
        for model_id, info in pricing["models"].items():
            if info.get("available", True) and info.get("tier") == tier and model_id not in candidates:
                return model_id
    raise ValueError("no independent Codex judge remains; pass fewer candidate models")


def build_plan(args, *, miner=rb.mine_tasks, pricing=None):
    pricing = pricing or cp.load_pricing()
    if args.limit < 1:
        raise ValueError("--limit must be at least 1")
    candidates = _resolve_candidates(pricing, args.models)
    judge = cp.resolve_model(pricing, args.judge) if args.judge else _default_judge(pricing, candidates)
    if not pricing["models"][judge].get("available", True):
        raise ValueError(f"judge model {judge!r} is unavailable on this roster")
    if judge in candidates:
        raise ValueError(f"Codex repo-bench refuses judge {judge!r}: it is also a candidate")

    with tempfile.TemporaryDirectory(prefix="codex-repo-bench-plan-") as tmp:
        mined = miner(
            Path(args.repo), mode=args.mode, limit=args.limit, test_cmd=args.test_cmd,
            commit=args.commit, scratch_dir=Path(tmp) / "work",
            exclude_subject=tuple(args.exclude_subject or ()), use_gh=False,
            setup_cmd=args.setup_cmd,
        )

    tasks = [{
        "task_id": task["task_id"], "size_profile": task["size_profile"],
        "oracle_tests_available": task["oracle_tests_available"],
    } for task in mined["tasks"]]
    rows = []
    for task in tasks:
        for model_id in candidates:
            est = cp.est_cost(pricing, task["size_profile"], model_id)
            rows.append({"kind": "candidate", "task_id": task["task_id"], "model": model_id,
                         "profile": task["size_profile"],
                         "burn_index_vs_cheapest": est["subscription"]["burn_index_vs_cheapest"],
                         "api_equivalent_usd": est["usd_api"]})
            judge_est = cp.est_cost(pricing, rb.JUDGE_GRADE_PROFILE, judge)
            rows.append({"kind": "judge", "task_id": task["task_id"], "model": judge,
                         "candidate": model_id, "profile": rb.JUDGE_GRADE_PROFILE,
                         "burn_index_vs_cheapest": judge_est["subscription"]["burn_index_vs_cheapest"],
                         "api_equivalent_usd": judge_est["usd_api"]})
    return {
        "schema_version": 1, "harness": "codex", "billing_mode": "chatgpt-plan",
        "repo": str(Path(args.repo)), "base_commit": mined["base_commit"],
        "mode": mined["mode"], "mode_reason": mined["mode_reason"], "tasks": tasks,
        "candidates": candidates, "judge": judge, "dispatch_count": len(rows),
        "rows": rows, "labels": list(mined["labels"]), "notes": list(mined["notes"]),
        "limitation": "planning only: live Codex dispatch is not implemented",
    }


def render_plan(card):
    lines = [f"# Codex repo-bench plan — {card['repo']}", "",
             "billing: ChatGPT plan (usage-limited; not token-billed)",
             f"mode: {card['mode']} — {card['mode_reason']}",
             f"tasks mined: {len(card['tasks'])}",
             f"dispatches: {card['dispatch_count']}",
             f"candidates: {', '.join(card['candidates']) or '(none)'}", f"judge: {card['judge']}", "",
             "## dispatch estimates (burn first)"]
    if not card["tasks"]:
        lines.append("No benchmark tasks were mined; this plan cannot support a model comparison.")
    for row in card["rows"]:
        subject = row.get("candidate") or row["model"]
        lines.append(f"- {row['kind']} {row['task_id']} / {subject}: "
                     f"burn index {row['burn_index_vs_cheapest']:.1f}×; "
                     f"API-equivalent proxy ${row['api_equivalent_usd']:.4f}")
    total = sum(row["api_equivalent_usd"] for row in card["rows"])
    lines += ["", f"API-equivalent proxy total: ${total:.4f} (not a bill or quota ceiling)",
              f"limitation: {card['limitation']}"]
    if card["labels"]:
        lines += ["", "labels:"] + [f"- {label}" for label in card["labels"]]
    if card["notes"]:
        lines += ["", "mining notes:"] + [f"- {note}" for note in card["notes"]]
    return "\n".join(lines)


def cmd_plan(args):
    card = build_plan(args)
    print(json.dumps(card, indent=2) if args.json else render_plan(card))
    return 0


def cmd_run(args):
    card = build_plan(args)
    print(json.dumps(card, indent=2) if args.json else render_plan(card))
    print("refusing to dispatch: live Codex repo-bench needs a dispatch-count ceiling and "
          "Codex-native result ledger; an API-equivalent proxy is not a spending ceiling")
    return 2


def build_parser():
    parser = argparse.ArgumentParser(prog="codex_repo_bench.py")
    subs = parser.add_subparsers(dest="command", required=True)
    for name, handler in (("plan", cmd_plan), ("run", cmd_run)):
        sub = subs.add_parser(name)
        sub.add_argument("--repo", required=True)
        sub.add_argument("--models", required=True)
        sub.add_argument("--judge")
        sub.add_argument("--mode", choices=("auto", "issue-replay", "general"), default="auto")
        sub.add_argument("--limit", type=int, default=8)
        sub.add_argument("--test-cmd")
        sub.add_argument("--setup-cmd")
        sub.add_argument("--commit")
        sub.add_argument("--exclude-subject", action="append", default=[])
        sub.add_argument("--json", action="store_true")
        sub.set_defaults(func=handler)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (KeyError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
