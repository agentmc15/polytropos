#!/usr/bin/env python3
"""Copilot-side cost math for the polytropos monorepo.

`data/pricing.copilot.json` is the single Copilot-side numeric source of truth (the
sibling of this plugin's `data/pricing.json` — the two never merge and neither harness
reads the other's file). Nothing in this script hardcodes a price, a credit value, a plan
allowance, or a model id: every number below is computed from the pricing dict passed in
or loaded at run time, and the USD<->AIC conversion always goes through
`pricing["billing_unit"]["usd_per_credit"]`.

Long-context rule (PLAN.md Risks — a deliberate conservative simplification): when a
model carries a `long_context` sub-object and a task profile's input token count exceeds
its `threshold_tokens`, the step-up rates apply to the WHOLE estimate (not just the
tokens over the threshold). GitHub actually bills the step-up only on the over-threshold
portion of a request, and task profiles are coarse conventions anyway, so this trades a
little precision for a much simpler, auditable formula.

Cache-write exclusion: `cache_write_per_mtok` (present on some Anthropic rows) is never
included in an estimate. Cache writes are a small fraction of an agentic loop's traffic,
and this keeps the formula at parity with the Claude-side estimator in
`bin/aesop_bridge.py`.

Usage:
    copilot_pricing.py models [--profile P] [--cache-hit 0.8] [--json]
    copilot_pricing.py est PROFILE MODEL_ID [--cache-hit 0.8] [--json]
    copilot_pricing.py runway PLAN PROFILE MODEL_ID [--cache-hit 0.8] [--pool-aic N] [--json]
    copilot_pricing.py prefs [--pin TIER=MODEL_ID ...] [--exclude MODEL_ID ...]
                        [--prefs FILE] [--no-prefs] [--json]
"""

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path

PRICING_PATH = Path(__file__).resolve().parent.parent / "data" / "pricing.copilot.json"


def load_pricing():
    with open(PRICING_PATH) as f:
        return json.load(f)


_prefs_mod = None


def _load_prefs_module():
    """Lazy-load bin/copilot_prefs.py (the single home for prefs logic) via importlib."""
    global _prefs_mod
    if _prefs_mod is None:
        import importlib.util
        path = Path(__file__).resolve().parent / "copilot_prefs.py"
        spec = importlib.util.spec_from_file_location("copilot_prefs", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _prefs_mod = mod
    return _prefs_mod


# ---- pure functions (no I/O besides the pricing dict passed in) ------------------------------

def effective_rates(model, input_tokens):
    """Return (rates_dict, which) for `model` at `input_tokens` of input.

    If `model` has a `long_context` sub-object and `input_tokens` exceeds its
    `threshold_tokens`, the step-up rates apply to the WHOLE estimate and `which` is
    `"long_context"` (see module docstring for why this is a deliberate simplification).
    Otherwise the base model rates apply and `which` is `"base"`. Either returned dict
    carries at least `input_per_mtok`, `cached_input_per_mtok`, and `output_per_mtok`.
    """
    long_context = model.get("long_context")
    if long_context and input_tokens > long_context["threshold_tokens"]:
        return long_context, "long_context"
    return model, "base"


def est_cost(pricing, profile, model_id, cache_hit=0.8, today=None):
    """Estimate USD + AIC cost of one task under `profile` on `model_id`.

    usd = input_tokens * ((1 - cache_hit) * input_per_mtok + cache_hit *
    cached_input_per_mtok) / 1e6 + output_tokens / 1e6 * output_per_mtok, using whichever
    rates `effective_rates` selects. Cache WRITE rates are never included (see module
    docstring). aic = usd / pricing["billing_unit"]["usd_per_credit"] — the AIC unit is
    always read from the data, never hardcoded.

    `today` is a `datetime.date` (defaults to `date.today()`); if the model carries a
    `promo` block and `today` is after `promo["until"]`, a warning is appended noting the
    promo has ended and rates may be stale.

    Raises `KeyError` (message lists valid choices) for an unknown `profile` or
    `model_id`.
    """
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
    model = models[model_id]
    rates, which = effective_rates(model, p["input_tokens"])

    usd = (
        p["input_tokens"]
        * ((1 - cache_hit) * rates["input_per_mtok"] + cache_hit * rates["cached_input_per_mtok"])
        / 1e6
        + p["output_tokens"] / 1e6 * rates["output_per_mtok"]
    )
    aic = usd / pricing["billing_unit"]["usd_per_credit"]

    warnings = []
    promo = model.get("promo")
    if promo:
        effective_today = today if today is not None else date.today()
        until = date.fromisoformat(promo["until"])
        if effective_today > until:
            warnings.append(
                f"promo pricing ended {promo['until']} — rates may be stale; "
                "re-check update_from"
            )

    return {"usd": usd, "aic": aic, "rates_used": which, "warnings": warnings}


def plan_runway(pricing, plan_id, profile, model_id, cache_hit=0.8, today=None, pool_aic=None):
    """How far a plan's monthly AIC allowance stretches for one task type.

    Raises `KeyError` (message lists valid choices) for an unknown `plan_id` — with or
    without a `pool_aic` (a pool never legitimizes a bad plan id). For a plan whose
    `included_aic_per_month` is null (no fixed allowance — see the plan's own `note` in
    pricing.copilot.json, e.g. `business`/`enterprise`, whose AIC is pooled at the org
    level), a `KeyError` is raised UNLESS `pool_aic` is given, in which case that pool
    supplies the allowance.

    `pool_aic`, when given, must be a number > 0 (else `ValueError`) and is used as the
    allowance REGARDLESS of the plan's own `included_aic_per_month` — it deliberately
    OVERRIDES a fixed plan's allowance too, since an org admin may know the real pooled
    size for a seat that otherwise reports a fixed number. Profile/model errors propagate
    from `est_cost`.

    Returns a dict with the three original keys (`est_aic_per_task`, `tasks_per_month`,
    `pct_of_allowance`, computed against whichever allowance was used) plus
    `allowance_aic` (the number used) and `allowance_source` (`"plan"` when the plan's own
    `included_aic_per_month` was used, `"pool"` when `pool_aic` was used).
    """
    if pool_aic is not None and not (pool_aic > 0):
        raise ValueError(
            f"pool_aic must be a positive AIC count, got {pool_aic!r}"
        )

    plans = pricing["plans"]
    if plan_id not in plans:
        raise KeyError(f"unknown plan {plan_id!r}; valid choices: {sorted(plans)}")
    plan = plans[plan_id]
    included = plan.get("included_aic_per_month")

    if pool_aic is not None:
        allowance = pool_aic
        allowance_source = "pool"
    elif included is None:
        raise KeyError(
            f"plan '{plan_id}' has no fixed AIC allowance — see its note in "
            "pricing.copilot.json; supply the org pool via --pool-aic / pool_aic"
        )
    else:
        allowance = included
        allowance_source = "plan"

    cost = est_cost(pricing, profile, model_id, cache_hit=cache_hit, today=today)
    est_aic = cost["aic"]
    return {
        "est_aic_per_task": est_aic,
        "tasks_per_month": math.floor(allowance / est_aic),
        "pct_of_allowance": est_aic / allowance * 100,
        "allowance_aic": allowance,
        "allowance_source": allowance_source,
    }


def models_table(pricing, profile=None, cache_hit=0.8, today=None):
    """One dict per model, in file order: id, display, vendor, tier, base rates, and —
    when `profile` is given — `est_usd`/`est_aic` via `est_cost`.
    """
    rows = []
    for model_id, info in pricing["models"].items():
        row = {
            "id": model_id,
            "display": info["display"],
            "vendor": info["vendor"],
            "tier": info["tier"],
            "input_per_mtok": info["input_per_mtok"],
            "cached_input_per_mtok": info["cached_input_per_mtok"],
            "output_per_mtok": info["output_per_mtok"],
        }
        if profile is not None:
            cost = est_cost(pricing, profile, model_id, cache_hit=cache_hit, today=today)
            row["est_usd"] = cost["usd"]
            row["est_aic"] = cost["aic"]
        rows.append(row)
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
            if "est_usd" in jr:
                jr["est_usd"] = round(jr["est_usd"], 4)
            if "est_aic" in jr:
                jr["est_aic"] = round(jr["est_aic"], 4)
            json_rows.append(jr)
        print(json.dumps(json_rows, indent=2))
        return

    tier_width = max((len(r["tier"]) for r in rows), default=0)
    id_width = max((len(r["id"]) for r in rows), default=0)
    display_width = max((len(r["display"]) for r in rows), default=0)
    for r in rows:
        line = (
            f"{r['tier']:<{tier_width}}  {r['id']:<{id_width}}  {r['display']:<{display_width}}  "
            f"${r['input_per_mtok']:.3f} in / ${r['output_per_mtok']:.3f} out per MTok"
        )
        if "est_usd" in r:
            line += f"  est ${r['est_usd']:.4f} / {r['est_aic']:.1f} AIC"
        print(line)


def cmd_est(args, pricing):
    try:
        result = est_cost(pricing, args.profile, args.model_id, cache_hit=args.cache_hit)
    except KeyError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)

    if args.json:
        out = {
            "profile": args.profile,
            "model_id": args.model_id,
            "cache_hit": args.cache_hit,
            "usd": round(result["usd"], 4),
            "aic": round(result["aic"], 4),
            "rates_used": result["rates_used"],
            "warnings": result["warnings"],
        }
        print(json.dumps(out, indent=2))
        return

    print(f"profile {args.profile} on {args.model_id}, cache_hit={args.cache_hit}")
    print(f"  usd:   ${result['usd']:.4f}")
    print(f"  aic:   {result['aic']:.1f}")
    print(f"  rates: {result['rates_used']}")
    for w in result["warnings"]:
        print(f"  warning: {w}")


def cmd_runway(args, pricing):
    try:
        result = plan_runway(
            pricing, args.plan, args.profile, args.model_id, cache_hit=args.cache_hit,
            pool_aic=args.pool_aic,
        )
    except (KeyError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)

    if args.json:
        out = {
            "plan": args.plan,
            "profile": args.profile,
            "model_id": args.model_id,
            "cache_hit": args.cache_hit,
            "est_aic_per_task": round(result["est_aic_per_task"], 4),
            "tasks_per_month": result["tasks_per_month"],
            "pct_of_allowance": round(result["pct_of_allowance"], 4),
            "allowance_aic": result["allowance_aic"],
            "allowance_source": result["allowance_source"],
        }
        print(json.dumps(out, indent=2))
        return

    print(
        f"plan {args.plan} profile {args.profile} model {args.model_id} "
        f"cache_hit={args.cache_hit}"
    )
    allowance_label = "plan" if result["allowance_source"] == "plan" else "user-supplied pool"
    print(f"  allowance:        {result['allowance_aic']:,.0f} AIC ({allowance_label})")
    print(f"  est_aic_per_task: {result['est_aic_per_task']:.1f}")
    print(f"  tasks_per_month:  {result['tasks_per_month']}")
    print(f"  pct_of_allowance: {result['pct_of_allowance']:.2f}%")


def cmd_knobs(args, pricing):
    """Print the reasoning-effort facts from the pricing dict's `knobs` block.

    The level vocabulary is DATA, never hardcoded here: `reasoning_efforts` prints in
    file order joined by " | ", followed by one line per `*_note` string key found in
    the knobs block (also file order). If `knobs` is absent or empty, prints one honest
    line and returns (exit 0) -- never an invented list. With `--json`, prints the raw
    knobs object verbatim (or `{}` when absent/empty).
    """
    knobs = pricing.get("knobs")
    if not knobs:
        if args.json:
            print("{}")
        else:
            print("no knobs recorded in data/pricing.copilot.json")
        return

    if args.json:
        print(json.dumps(knobs, indent=2))
        return

    efforts = knobs.get("reasoning_efforts", [])
    print(f"reasoning_efforts: {' | '.join(efforts)}")
    for key, value in knobs.items():
        if key.endswith("_note") and isinstance(value, str):
            print(f"{key}: {value}")


def cmd_prefs(args, pricing):
    """Show the active model pins/excludes and what each tier now resolves to.

    Prefs come from `bin/copilot_prefs.py` (the single home for prefs logic, loaded lazily
    via importlib) — the gitignored USER DATA file `prefs/copilot.json` by default, merged
    with any `--pin`/`--exclude` flags per `copilot_prefs.effective_prefs`'s precedence
    rules (flag pins replace only their own tier's file pin; excludes union). Errors — bad
    `--pin` grammar, an unknown tier or model id, or a pin-vs-exclude conflict — print to
    stderr and exit 2. With `--json`, prints exactly `source`, `pins`, `excludes`,
    `resolved` (tier -> id or null), `resolved_via` (tier -> "pin"/"default"/null), `notes`.
    """
    prefs_mod = _load_prefs_module()
    try:
        prefs = prefs_mod.effective_prefs(
            pricing, prefs_path=args.prefs, no_prefs=args.no_prefs,
            pin_flags=tuple(args.pin or ()), exclude_flags=tuple(args.exclude or ()),
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)

    resolved = {
        tier: prefs_mod.resolve_tier(pricing, tier, prefs) for tier in prefs_mod.TIER_ORDER
    }
    resolved_via = {
        tier: ("pin" if tier in prefs["pins"] else ("default" if resolved[tier] else None))
        for tier in prefs_mod.TIER_ORDER
    }

    if args.json:
        out = {
            "source": prefs["source"],
            "pins": prefs["pins"],
            "excludes": prefs["excludes"],
            "resolved": resolved,
            "resolved_via": resolved_via,
            "notes": prefs["notes"],
        }
        print(json.dumps(out, indent=2))
        return

    if prefs["source"] is not None:
        print(f"source: {prefs['source']}")
    elif args.no_prefs:
        print("source: (prefs file ignored: --no-prefs)")
    else:
        print("source: (no prefs file)")

    pins_line = ", ".join(f"{tier}={model_id}" for tier, model_id in prefs["pins"].items())
    print(f"pins: {pins_line or '(none)'}")

    excludes_line = ", ".join(prefs["excludes"])
    print(f"excludes: {excludes_line or '(none)'}")

    print("tier resolution:")
    tier_width = max(len(t) for t in prefs_mod.TIER_ORDER)
    for tier in prefs_mod.TIER_ORDER:
        model_id = resolved[tier]
        if model_id is None:
            print(f"  {tier:<{tier_width}}  -> (none — no non-excluded model carries this tier)")
            continue
        suffix = ""
        if resolved_via[tier] == "pin":
            suffix = " (pinned)"
            own_tier = pricing["models"].get(model_id, {}).get("tier")
            if own_tier is not None and own_tier != tier:
                suffix += f" (model's own tier: {own_tier})"
        print(f"  {tier:<{tier_width}}  -> {model_id}{suffix}")

    for note in prefs["notes"]:
        print(f"note: {note}")


def build_parser():
    ap = argparse.ArgumentParser(
        prog="copilot_pricing.py",
        description=(
            "Copilot-side cost math (USD + AI Credits) from data/pricing.copilot.json: "
            "the cross-vendor model roster, per-task cost estimates, and plan runway."
        ),
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_models = sub.add_parser("models", help="cross-vendor model roster")
    p_models.add_argument("--profile", help="task profile key to add est_usd/est_aic columns")
    p_models.add_argument("--cache-hit", type=float, default=0.8)
    p_models.add_argument("--json", action="store_true", help="machine-readable output")
    p_models.set_defaults(func=cmd_models)

    p_est = sub.add_parser("est", help="estimated USD + AIC cost of one task")
    p_est.add_argument("profile", help="task profile key, e.g. XS, S, M, L, XL")
    p_est.add_argument("model_id", help="model id from pricing.copilot.json")
    p_est.add_argument("--cache-hit", type=float, default=0.8)
    p_est.add_argument("--json", action="store_true", help="machine-readable output")
    p_est.set_defaults(func=cmd_est)

    p_runway = sub.add_parser("runway", help="how far a plan's monthly AIC allowance stretches")
    p_runway.add_argument("plan", help="plan id from pricing.copilot.json, e.g. pro")
    p_runway.add_argument("profile", help="task profile key, e.g. XS, S, M, L, XL")
    p_runway.add_argument("model_id", help="model id from pricing.copilot.json")
    p_runway.add_argument("--cache-hit", type=float, default=0.8)
    p_runway.add_argument(
        "--pool-aic", type=float, default=None,
        help=(
            "user-supplied AIC pool size, required for org/Business plans whose "
            "included_aic_per_month is null; also overrides a fixed plan's own allowance "
            "when an admin knows the real pooled size"
        ),
    )
    p_runway.add_argument("--json", action="store_true", help="machine-readable output")
    p_runway.set_defaults(func=cmd_runway)

    p_knobs = sub.add_parser(
        "knobs", help="reasoning-effort facts from the pricing data (the level vocabulary is data, not code)"
    )
    p_knobs.add_argument("--json", action="store_true", help="machine-readable output")
    p_knobs.set_defaults(func=cmd_knobs)

    p_prefs = sub.add_parser(
        "prefs", help="active model pins/excludes and what each tier now resolves to"
    )
    p_prefs.add_argument("--pin", action="append", metavar="TIER=MODEL_ID",
                         help="resolve TIER to MODEL_ID (repeatable; overrides the prefs file's pin for that tier)")
    p_prefs.add_argument("--exclude", action="append", metavar="MODEL_ID",
                         help="never recommend this model (repeatable; unions with the prefs file's excludes)")
    p_prefs.add_argument("--prefs", default=None, metavar="FILE",
                         help="prefs file to read (default: <repo>/prefs/copilot.json)")
    p_prefs.add_argument("--no-prefs", action="store_true",
                         help="ignore the prefs file entirely (--pin/--exclude flags still apply)")
    p_prefs.add_argument("--json", action="store_true", help="machine-readable output")
    p_prefs.set_defaults(func=cmd_prefs)

    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    pricing = load_pricing()
    args.func(args, pricing)


if __name__ == "__main__":
    main()
