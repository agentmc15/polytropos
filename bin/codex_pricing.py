#!/usr/bin/env python3
"""Codex-side cost math for the polytropos monorepo.

`data/pricing.codex.json` is the Codex-side single numeric source of truth (the sibling
of this plugin's `data/pricing.json` and `data/pricing.copilot.json` — the three pricing
files never merge, and no harness reads another harness's file). Nothing in this script
hardcodes a price, a cache multiplier, a plan fact, or a model id: every number below is
computed from the pricing dict passed in or loaded at run time. The four-value tier
vocabulary `("cheap", "mid", "strong", "frontier")` is the one sanctioned literal, held in
the module constant `TIER_ORDER`.

Dual framing (PLAN.md D3 — the central decision): Codex under a ChatGPT plan draws down
opaque usage limits, not dollars, while API-key auth is metered in real dollars at the
rates in this file. There is no published token-to-quota conversion, so `est_cost` always
returns BOTH framings and there is no `--mode` flag: `usd_api` is the real, authoritative
API-dollar estimate; `subscription.billed_usd` is always `None` (a subscription run is not
token-billed) alongside the SAME dollar figure re-labeled as an API-equivalent
relative-burn proxy, plus a burn index (this estimate divided by the cheapest same-profile
estimate on the roster, computed here from the data — never a hardcoded divisor id). A
dollar figure must never be presented as a subscription bill.

Cache-write exclusion: `cache_write_multiplier` (the 1.25x write rate in the data) is never
included in an estimate here. Cache writes are a small fraction of an agentic loop's
traffic, and this keeps the formula at parity with the sibling Claude- and Copilot-side
estimators. The write multiplier still lives in the data for `codex_usage.py`, which prices
OBSERVED usage (including any real cache writes it finds) rather than estimating one.

Tier skip-up rule (PLAN.md D4, shared verbatim with `codex_execute.py`'s escalation
ladder): resolving a tier word to a model takes the first model in pricing-file order
carrying that tier; if the tier is unpopulated on the roster, retry the next tier UP in
`TIER_ORDER` (repeating as needed) until a populated tier is found or the vocabulary is
exhausted.

This script NEVER invokes the real `codex` CLI — it only reads `data/pricing.codex.json`
and does arithmetic.

Usage:
    codex_pricing.py models [--profile P] [--cache-hit 0.8] [--json]
    codex_pricing.py est PROFILE MODEL_OR_TIER [--cache-hit 0.8] [--json]
    codex_pricing.py plans [--json]
    codex_pricing.py knobs [--json]
"""

import argparse
import json
import sys
from pathlib import Path

PRICING_PATH = Path(__file__).resolve().parent.parent / "data" / "pricing.codex.json"

TIER_ORDER = ("cheap", "mid", "strong", "frontier")


def load_pricing():
    with open(PRICING_PATH) as f:
        return json.load(f)


# ---- pure functions (no I/O besides the pricing dict passed in) ------------------------------

def resolve_tier(pricing, tier):
    """Return the model id for `tier`, applying the D4 skip-up rule (shared with
    `codex_execute.py`).

    Raises `KeyError` for an unknown tier word (message lists `TIER_ORDER`). Otherwise
    returns the id of the FIRST model in pricing-file order whose `tier` equals `tier`. If
    that tier is unpopulated on the roster, retries with the next tier UP in `TIER_ORDER`
    (repeating as needed); if no populated tier at or above the request exists, raises
    `KeyError`.
    """
    if tier not in TIER_ORDER:
        raise KeyError(
            f"unknown tier {tier!r}; valid tiers: {list(TIER_ORDER)}"
        )
    models = pricing["models"]
    start = TIER_ORDER.index(tier)
    for candidate_tier in TIER_ORDER[start:]:
        for model_id, info in models.items():
            if info["tier"] == candidate_tier:
                return model_id
    raise KeyError(
        f"no model at or above tier {tier!r} on this roster; tiers present: "
        f"{sorted({info['tier'] for info in models.values()})}"
    )


def resolve_model(pricing, model_or_tier):
    """Resolve `model_or_tier` to a model id.

    If it is a key of `pricing["models"]`, return it verbatim. Elif it is one of
    `TIER_ORDER`, return `resolve_tier(pricing, model_or_tier)`. Else raise `KeyError`
    listing both valid model ids and tier words.
    """
    models = pricing["models"]
    if model_or_tier in models:
        return model_or_tier
    if model_or_tier in TIER_ORDER:
        return resolve_tier(pricing, model_or_tier)
    raise KeyError(
        f"unknown model or tier {model_or_tier!r}; valid model ids: {sorted(models)}; "
        f"valid tiers: {list(TIER_ORDER)}"
    )


def est_cost(pricing, profile, model_or_tier, cache_hit=0.8):
    """Estimate the dual-framed cost of one task under `profile` on `model_or_tier`.

    `usd_api = input_tokens * ((1 - cache_hit) * input_per_mtok + cache_hit *
    input_per_mtok * cache_read_multiplier) / 1e6 + output_tokens / 1e6 * output_per_mtok`
    — cache WRITE costs are never included (see module docstring). Raises `KeyError`
    (message lists valid choices) for an unknown `profile`; model/tier resolution errors
    propagate from `resolve_model`.

    Returns `{"model_id": <resolved id>, "usd_api": float, "subscription":
    {"billed_usd": None, "api_equivalent_usd": <same float>, "burn_index_vs_cheapest":
    float, "cheapest_model_id": str}}`. The burn index divides `usd_api` by the minimum
    same-profile `usd_api` across the WHOLE roster (computed here from the data at run
    time — never a hardcoded id; with today's data the divisor happens to be the cheap-tier
    model, but nothing in this function assumes that).
    """
    profiles = pricing["task_profiles"]
    if profile not in profiles:
        raise KeyError(
            f"unknown task profile {profile!r}; valid choices: {sorted(profiles)}"
        )

    model_id = resolve_model(pricing, model_or_tier)
    models = pricing["models"]
    p = profiles[profile]
    cache_read_multiplier = pricing["cache_read_multiplier"]

    def usd_api_for(mid):
        m = models[mid]
        return (
            p["input_tokens"]
            * (
                (1 - cache_hit) * m["input_per_mtok"]
                + cache_hit * m["input_per_mtok"] * cache_read_multiplier
            )
            / 1e6
            + p["output_tokens"] / 1e6 * m["output_per_mtok"]
        )

    usd_api = usd_api_for(model_id)

    cheapest_model_id = min(models, key=usd_api_for)
    cheapest_usd_api = usd_api_for(cheapest_model_id)
    burn_index = usd_api / cheapest_usd_api

    return {
        "model_id": model_id,
        "usd_api": usd_api,
        "subscription": {
            "billed_usd": None,
            "api_equivalent_usd": usd_api,
            "burn_index_vs_cheapest": burn_index,
            "cheapest_model_id": cheapest_model_id,
        },
    }


def models_table(pricing, profile=None, cache_hit=0.8):
    """One dict per model, in file order: id, display, vendor, tier, base rates,
    `cached_input_per_mtok` (COMPUTED: `input_per_mtok * cache_read_multiplier`), and —
    when `profile` is given — `est_usd_api`/`burn_index` via `est_cost`.
    """
    cache_read_multiplier = pricing["cache_read_multiplier"]
    rows = []
    for model_id, info in pricing["models"].items():
        row = {
            "id": model_id,
            "display": info["display"],
            "vendor": info["vendor"],
            "tier": info["tier"],
            "input_per_mtok": info["input_per_mtok"],
            "cached_input_per_mtok": info["input_per_mtok"] * cache_read_multiplier,
            "output_per_mtok": info["output_per_mtok"],
        }
        if profile is not None:
            cost = est_cost(pricing, profile, model_id, cache_hit=cache_hit)
            row["est_usd_api"] = cost["usd_api"]
            row["burn_index"] = cost["subscription"]["burn_index_vs_cheapest"]
        rows.append(row)
    return rows


def plans_table(pricing):
    """One dict per plan, in file order: `id`, `usd_per_month`, `included_usage`, `note`
    (absent on the plan -> `None`). Never invents an allowance: a null `included_usage`
    stays `None` all the way to output.
    """
    rows = []
    for plan_id, info in pricing["plans"].items():
        rows.append({
            "id": plan_id,
            "usd_per_month": info.get("usd_per_month"),
            "included_usage": info.get("included_usage"),
            "note": info.get("note"),
        })
    return rows


# ---- CLI ---------------------------------------------------------------------------------------

def cmd_models(args, pricing):
    try:
        rows = models_table(pricing, profile=args.profile, cache_hit=args.cache_hit)
    except KeyError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)

    if args.json:
        json_rows = []
        for r in rows:
            jr = dict(r)
            jr["cached_input_per_mtok"] = round(jr["cached_input_per_mtok"], 4)
            if "est_usd_api" in jr:
                jr["est_usd_api"] = round(jr["est_usd_api"], 4)
            if "burn_index" in jr:
                jr["burn_index"] = round(jr["burn_index"], 4)
            json_rows.append(jr)
        print(json.dumps(json_rows, indent=2))
        return

    tier_width = max((len(r["tier"]) for r in rows), default=0)
    id_width = max((len(r["id"]) for r in rows), default=0)
    display_width = max((len(r["display"]) for r in rows), default=0)
    for r in rows:
        line = (
            f"{r['tier']:<{tier_width}}  {r['id']:<{id_width}}  {r['display']:<{display_width}}  "
            f"${r['input_per_mtok']:.3f} in / ${r['output_per_mtok']:.3f} out per MTok "
            f"(${r['cached_input_per_mtok']:.4f} cached-in)"
        )
        if "est_usd_api" in r:
            line += f"  est ${r['est_usd_api']:.4f} api / {r['burn_index']:.1f}x cheapest"
        print(line)


def cmd_est(args, pricing):
    try:
        result = est_cost(pricing, args.profile, args.model_or_tier, cache_hit=args.cache_hit)
    except KeyError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)

    if args.json:
        sub = result["subscription"]
        out = {
            "profile": args.profile,
            "cache_hit": args.cache_hit,
            "model_id": result["model_id"],
            "usd_api": round(result["usd_api"], 4),
            "subscription": {
                "billed_usd": sub["billed_usd"],
                "api_equivalent_usd": round(sub["api_equivalent_usd"], 4),
                "burn_index_vs_cheapest": round(sub["burn_index_vs_cheapest"], 4),
                "cheapest_model_id": sub["cheapest_model_id"],
            },
        }
        print(json.dumps(out, indent=2))
        return

    sub = result["subscription"]
    tier = pricing["models"][result["model_id"]]["tier"]
    print(
        f"profile {args.profile} on {result['model_id']} (tier {tier}), "
        f"cache_hit={args.cache_hit}"
    )
    print(f"  api:          ${result['usd_api']:.4f} (token-metered API billing)")
    print(
        "  subscription: not token-billed (usage-limited) — API-equivalent "
        f"${sub['api_equivalent_usd']:.4f} is a relative-burn proxy, not a bill; "
        f"{sub['burn_index_vs_cheapest']:.1f}x cheapest ({sub['cheapest_model_id']})"
    )


def cmd_plans(args, pricing):
    rows = plans_table(pricing)

    if args.json:
        print(json.dumps(rows, indent=2))
        return

    for r in rows:
        usage = (
            "usage-limited (no published allowance)"
            if r["included_usage"] is None
            else str(r["included_usage"])
        )
        price = "custom / org-managed" if r["usd_per_month"] is None else f"${r['usd_per_month']}/mo"
        line = f"{r['id']:<10}  {price:<20}  {usage}"
        if r["note"]:
            line += f"  — {r['note']}"
        print(line)


def cmd_knobs(args, pricing):
    """Print the reasoning-effort ladder plus every knobs note, honestly (PLAN.md D6).

    Absent or empty `knobs` -> one honest line (`no knobs recorded in
    data/pricing.codex.json`), exit 0; `--json` -> `{}`. Otherwise text mode prints
    `reasoning_efforts: <v1> | <v2> | ...` in file order, then every `*_note` string key
    in the knobs block as `<key>: <value>`, then -- if a `modes` object exists -- one line
    per mode as `mode <name>: <its note>` (never a flag; modes' CLI surfaces are
    unpublished, so their notes are relayed verbatim, never invented). `--json` prints the
    raw knobs object, indent 2.
    """
    knobs = pricing.get("knobs")

    if not knobs:
        if args.json:
            print(json.dumps({}, indent=2))
        else:
            print("no knobs recorded in data/pricing.codex.json")
        return

    if args.json:
        print(json.dumps(knobs, indent=2))
        return

    efforts = knobs.get("reasoning_efforts")
    if efforts:
        print(f"reasoning_efforts: {' | '.join(efforts)}")

    for key, value in knobs.items():
        if key.endswith("_note") and isinstance(value, str):
            print(f"{key}: {value}")

    modes = knobs.get("modes")
    if isinstance(modes, dict):
        for mode_name, mode_info in modes.items():
            note = mode_info.get("note", "") if isinstance(mode_info, dict) else ""
            print(f"mode {mode_name}: {note}")


def build_parser():
    ap = argparse.ArgumentParser(
        prog="codex_pricing.py",
        description=(
            "Codex-side cost math (dual API/subscription framing) from "
            "data/pricing.codex.json: the GPT-5.6 model roster, per-task cost estimates, "
            "and ChatGPT plan facts. Never invokes the real codex CLI."
        ),
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_models = sub.add_parser("models", help="GPT-5.6 model roster")
    p_models.add_argument("--profile", help="task profile key to add est/burn columns")
    p_models.add_argument("--cache-hit", type=float, default=0.8)
    p_models.add_argument("--json", action="store_true", help="machine-readable output")
    p_models.set_defaults(func=cmd_models)

    p_est = sub.add_parser("est", help="dual-framed (API + subscription) cost of one task")
    p_est.add_argument("profile", help="task profile key, e.g. XS, S, M, L, XL")
    p_est.add_argument("model_or_tier", help="model id or tier word from pricing.codex.json")
    p_est.add_argument("--cache-hit", type=float, default=0.8)
    p_est.add_argument("--json", action="store_true", help="machine-readable output")
    p_est.set_defaults(func=cmd_est)

    p_plans = sub.add_parser("plans", help="ChatGPT plan facts (no invented allowances)")
    p_plans.add_argument("--json", action="store_true", help="machine-readable output")
    p_plans.set_defaults(func=cmd_plans)

    p_knobs = sub.add_parser("knobs", help="reasoning-effort ladder and mode notes")
    p_knobs.add_argument("--json", action="store_true", help="machine-readable output")
    p_knobs.set_defaults(func=cmd_knobs)

    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    pricing = load_pricing()
    args.func(args, pricing)


if __name__ == "__main__":
    main()
