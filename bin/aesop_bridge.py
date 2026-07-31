#!/usr/bin/env python3
"""Bridge from data/pricing.json to aesop's abstract dials.

aesop (https://github.com/agentmc15/aesop) deliberately keeps its dials abstract and
price-agnostic: model tiers are named strong|mid|cheap, budget stops are a flat
budget_usd, and its Ralph-style loop runner falls back to a flat per-tick cost estimate
when the agent CLI it drives emits no cost JSON. This script computes the concrete
numbers those dials need from this plugin's data/pricing.json, at run time, so a user can
paste them into an aesop.yaml manifest or a goal recipe. It is copy-paste output, not a
runtime dependency — nothing here imports or calls aesop.

Convention (PLAN.md D5): "current model per tier" = the first model in pricing.json's
`models` object, in file order, whose `tier` field matches (json.load preserves
insertion order, and this repo lists the newest model first within each tier). Nothing in
this script hardcodes a price, a price ratio, or a model id — every number below is
computed from the pricing dict passed in or loaded at run time.

Usage:
    aesop_bridge.py tiers [--json]
    aesop_bridge.py est-tick PROFILE MODEL_ID [--cache-hit 0.8] [--json]
    aesop_bridge.py check-budget USD PROFILE MODEL_ID [--cache-hit 0.8] [--json]
"""

import argparse
import json
import math
import os
import sys
from datetime import date

PRICING_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "pricing.json"
)

# aesop tier name -> pricing.json `tier` value it maps from, in the order aesop defines
# its dial (frontier is polytropos's own addition for Fable-class models).
_TIER_SOURCE = (
    ("frontier", "frontier"),
    ("strong", "opus"),
    ("mid", "sonnet"),
    ("cheap", "haiku"),
)


def load_pricing():
    with open(PRICING_PATH) as f:
        return json.load(f)


# ---- pure functions (no I/O besides the pricing dict passed in) ------------------------------

def tier_map(pricing):
    """Map aesop tier names to the current model id for that tier.

    "Current" = first model in `pricing["models"]` file order whose `tier` field matches
    (see module docstring). A tier is omitted if no model in pricing.json carries it.
    """
    models = pricing["models"]
    result = {}
    for aesop_tier, pricing_tier in _TIER_SOURCE:
        for model_id, info in models.items():
            if info.get("tier") == pricing_tier:
                result[aesop_tier] = model_id
                break
    return result


def _rates(model, today):
    """Return (input_per_mtok, output_per_mtok) for a model, honoring intro_pricing."""
    intro = model.get("intro_pricing")
    if intro:
        effective_today = today if today is not None else date.today()
        if effective_today <= date.fromisoformat(intro["until"]):
            return intro["input_per_mtok"], intro["output_per_mtok"]
    return model["input_per_mtok"], model["output_per_mtok"]


def est_tick(pricing, profile, model_id, cache_hit=0.8, today=None):
    """Estimated USD for one agent-loop tick under `profile` on `model_id`."""
    profiles = pricing["task_profiles"]
    if profile not in profiles:
        raise KeyError(
            f"unknown task profile {profile!r}; valid choices: {sorted(profiles)}"
        )
    models = pricing["models"]
    if model_id not in models:
        raise KeyError(
            f"unknown model id {model_id!r}; valid choices: {sorted(models)}"
        )
    p = profiles[profile]
    input_per_mtok, output_per_mtok = _rates(models[model_id], today)
    effective_input_mult = (1 - cache_hit) + cache_hit * pricing["cache_read_multiplier"]
    return (
        p["input_tokens"] * effective_input_mult / 1e6 * input_per_mtok
        + p["output_tokens"] / 1e6 * output_per_mtok
    )


def check_budget(pricing, usd, profile, model_id, cache_hit=0.8, today=None):
    """How many loop ticks a flat budget_usd buys under `profile` on `model_id`."""
    tick = est_tick(pricing, profile, model_id, cache_hit=cache_hit, today=today)
    iterations = math.floor(usd / tick)
    warning = None
    if iterations < 10:
        warning = (
            "fewer than 10 iterations of runway — raise budget_usd or shrink "
            "the task profile"
        )
    return {"est_tick_usd": tick, "iterations": iterations, "warning": warning}


# ---- CLI ---------------------------------------------------------------------------------------

def cmd_tiers(args, pricing):
    tm = tier_map(pricing)
    if args.json:
        print(json.dumps(tm, indent=2))
        return
    models = pricing["models"]
    order = [t for t, _ in _TIER_SOURCE if t in tm]
    width = max((len(t) for t in order), default=0)
    for tier in order:
        model_id = tm[tier]
        m = models[model_id]
        print(
            f"{tier:<{width}} → {model_id} ({m['display']}, "
            f"${m['input_per_mtok']:.2f} in / ${m['output_per_mtok']:.2f} out per MTok)"
        )


def _subscription_note(pricing):
    if pricing.get("billing_mode") == "subscription":
        return "billing_mode is subscription — read this as API-equivalent burn, not dollars."
    return None


def cmd_est_tick(args, pricing):
    try:
        cost = est_tick(pricing, args.profile, args.model_id, cache_hit=args.cache_hit)
    except KeyError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
    note = _subscription_note(pricing)
    if args.json:
        out = {
            "profile": args.profile,
            "model_id": args.model_id,
            "cache_hit": args.cache_hit,
            "est_tick_usd": round(cost, 4),
        }
        if note:
            out["note"] = note
        print(json.dumps(out, indent=2))
        return
    profile_info = pricing["task_profiles"][args.profile]
    print(
        f"profile {args.profile} ({profile_info['label']}) on {args.model_id}, "
        f"cache_hit={args.cache_hit}"
    )
    print(
        f"  input_tokens={profile_info['input_tokens']:,} "
        f"output_tokens={profile_info['output_tokens']:,}"
    )
    print(f"  est_tick_usd = ${cost:.2f}")
    if note:
        print(note)


def cmd_check_budget(args, pricing):
    try:
        result = check_budget(
            pricing, args.usd, args.profile, args.model_id, cache_hit=args.cache_hit
        )
    except KeyError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
    if args.json:
        out = {
            "budget_usd": args.usd,
            "profile": args.profile,
            "model_id": args.model_id,
            "cache_hit": args.cache_hit,
            "est_tick_usd": round(result["est_tick_usd"], 4),
            "iterations": result["iterations"],
            "warning": result["warning"],
        }
        print(json.dumps(out, indent=2))
        return
    print(
        f"budget_usd=${args.usd:.2f} profile={args.profile} model={args.model_id} "
        f"cache_hit={args.cache_hit}"
    )
    print(f"  est_tick_usd = ${result['est_tick_usd']:.2f}")
    print(f"  iterations   = {result['iterations']}")
    if result["warning"]:
        print(f"  warning: {result['warning']}")


def build_parser():
    ap = argparse.ArgumentParser(
        prog="aesop_bridge.py",
        description=(
            "Compute concrete numbers for aesop's abstract dials (tiers, per-tick cost, "
            "budget runway) from this plugin's data/pricing.json."
        ),
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_tiers = sub.add_parser("tiers", help="current model mapped to each aesop tier")
    p_tiers.add_argument("--json", action="store_true", help="machine-readable output")
    p_tiers.set_defaults(func=cmd_tiers)

    p_est = sub.add_parser("est-tick", help="estimated USD for one agent-loop tick")
    p_est.add_argument("profile", help="task profile key, e.g. S, M, L")
    p_est.add_argument("model_id", help="model id from pricing.json")
    p_est.add_argument("--cache-hit", type=float, default=0.8)
    p_est.add_argument("--json", action="store_true", help="machine-readable output")
    p_est.set_defaults(func=cmd_est_tick)

    p_budget = sub.add_parser("check-budget", help="how many loop ticks a budget_usd buys")
    p_budget.add_argument("usd", type=float)
    p_budget.add_argument("profile", help="task profile key, e.g. S, M, L")
    p_budget.add_argument("model_id", help="model id from pricing.json")
    p_budget.add_argument("--cache-hit", type=float, default=0.8)
    p_budget.add_argument("--json", action="store_true", help="machine-readable output")
    p_budget.set_defaults(func=cmd_check_budget)

    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    pricing = load_pricing()
    args.func(args, pricing)


if __name__ == "__main__":
    main()
