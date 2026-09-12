#!/usr/bin/env python3
"""Route workflow shape, model, initial effort, and assurance as four separate decisions.

WHAT WAS COUPLED, MEASURED. Before this module, a Codex task's routing was one function
(`codex_policy.resolve_assignment`) answering one question -- which worker -- and three other
questions were answered by its side effects: the workflow shape was always "workers, then a
strong review, then a reserved-frontier acceptance"; the initial effort was whatever the
command line said or the model's own default; assurance was whatever the driver happened to
run. And the one question it did answer was coupled to the reserved orchestrator: with Astra
marked unavailable, `resolve_assignment(pricing, "mid")` raised "execution is disabled", so a
worker-only path that never needed Astra could not run. A frontier pin was migrated down to
the strongest worker; a task could reach the frontier only after a cheaper attempt had failed.

Those are policy choices, and good ones for the default. They were not stated as a policy, so
they could not be selected against. This module states them: `reserved` is the existing
behaviour under its own name and stays the default; `adaptive` is the opt-in alternative that
may send a hard task straight to an eligible capable model, frontier included, without a
failed cheaper attempt first. Nothing changes for a caller that selects nothing.

FOUR DECISIONS, ONE ORDER. Hard filters come before any preference: a model that is
unavailable, not routable, pinned away, excluded, unsupported for the requested effort, or
over budget is out before quality or cost is weighed. Explicit pins win over the policy. A
preference (`cost`, `quality`, `balanced`, `latency`) only chooses among what survived. Every
alternative is listed with the filter that removed it or the preference that ranked it lower,
so the decision is explainable from its own record. No success probability is estimated from
a benchmark ranking; the estimate is the harness's own price engine's figure, labelled est.
and API-equivalent, never a bill.

HARNESS-NEUTRAL BY CONSTRUCTION. This module never reads a pricing file. Each harness builds
a `catalog` from its own file -- ids, tiers as ranks in that harness's own tier order,
availability, supported efforts, an estimate -- and the decision compares ranks, never tier
names, so a Claude roster (haiku|sonnet|opus|frontier) and a Codex roster
(cheap|mid|strong|frontier) route through the same rule without either being assumed to look
like the other. Catalog facts (what exists, what it costs) and strategy (which policy, which
preference) stay separate: the former is data in the pricing files, the latter is a selected
name.

NOT LEARNING. Which policy is active is a deterministic, explicit selection: a command-line
flag or a PLAN.md `routing:` line. Nothing here promotes a new default from observations; that
is step 25's evaluation loop, and it will consume these decisions rather than replace them.
"""

import json
import sys

#: The decision contract. A consumer checks this before trusting the field names.
CONTRACT_VERSION = "polytropos.routing/1"

POLICIES = ("reserved", "adaptive")
DEFAULT_POLICY = "reserved"

PREFERENCES = ("balanced", "cost", "quality", "latency")
DEFAULT_PREFERENCE = "balanced"

#: Workflow shapes, simplest first. `direct` is one dispatch and its check; `reviewed` adds an
#: independent review; `graph` is a kit: tasks with dependencies, phase review, acceptance.
SHAPES = ("direct", "reviewed", "graph")

#: What each shape needs from the host, by capability name in the harness registry. A shape
#: whose capability is `unsupported` is not offered; `unknown` is offered and named as
#: unverified, because every row in the registry is unverified today (nothing is run live
#: from this repository) and treating unknown as unsupported would exclude the default path.
SHAPE_REQUIRES = {
    "direct": ("dispatch",),
    "reviewed": ("dispatch", "sandbox_read_only"),
    "graph": ("dispatch", "sandbox_read_only", "durable_attempts"),
}

#: Assurance each shape carries. `verify` is the task's own check and is never optional.
ASSURANCE = ("verify", "independent-review", "acceptance")
SHAPE_ASSURANCE = {
    "direct": ("verify",),
    "reviewed": ("verify", "independent-review"),
    "graph": ("verify", "independent-review", "acceptance"),
}

AVAILABILITY = ("available", "unavailable", "unknown")

#: Why a candidate was set aside. Hard filters first, then the preference's ranking.
FILTERS = ("unavailable", "not-routable", "reserved", "pinned-elsewhere", "excluded",
           "effort-unsupported", "below-floor", "over-budget", "ranked-lower")

UNCERTAINTY = ("low", "medium", "high")

#: What each policy does with a plan that names the reserved tier and with the reserved
#: model as a candidate. Stated as data so the explanation can quote it.
POLICY_RULES = {
    "reserved": {
        "reserved_model_implements": False,
        "plan_above_ceiling": "migrate-down",
        "frontier_needs_failed_attempt": True,
    },
    "adaptive": {
        "reserved_model_implements": True,
        "plan_above_ceiling": "honour",
        "frontier_needs_failed_attempt": False,
    },
}


class RoutingError(ValueError):
    """A request the router cannot act on: an unknown policy, preference, or a malformed catalog."""


def _check_vocab(value, allowed, what):
    if value not in allowed:
        raise RoutingError(f"unknown {what} {value!r}; valid: {', '.join(allowed)}")
    return value


def catalog_entry(model_id, tier, rank, availability="unknown", routable=True, reserved=False,
                  efforts=None, default_effort=None, estimate=None, note=""):
    """One catalog row. `rank` is the tier's index in the HARNESS's own order; the router
    compares ranks and never tier names. `estimate` is `{"api_equivalent_usd", "profile"}`
    from the harness's own price engine, or None when nothing priced it."""
    _check_vocab(availability, AVAILABILITY, "availability")
    return {
        "id": model_id, "tier": tier, "rank": int(rank), "availability": availability,
        "routable": bool(routable), "reserved": bool(reserved),
        "efforts": list(efforts) if efforts is not None else None,
        "default_effort": default_effort, "estimate": estimate, "note": note,
    }


def catalog_from_pricing(pricing, harness, tier_order, reserved_model=None, estimator=None):
    """A catalog from one harness's pricing dict, using THAT harness's tier order.

    Generic enough for any of the three files: a model is routable when its tier is in
    `tier_order` (Codex's cost-only and non-routing entries fall out here), availability is
    the file's `available` flag or `unknown` when it carries none, and efforts come from the
    model's own `supported_reasoning_efforts` when the file records them. `estimator(model_id)`
    is the harness's own price function, or None for an unpriced catalog. Never merges files:
    one call, one pricing dict.
    """
    entries = []
    for model_id, info in (pricing.get("models") or {}).items():
        tier = info.get("tier")
        routable = tier in tier_order
        flag = info.get("available")
        availability = "unknown" if flag is None else ("available" if flag is not False
                                                       else "unavailable")
        estimate = None
        if estimator is not None and routable:
            try:
                estimate = estimator(model_id)
            except (KeyError, ValueError, TypeError):
                estimate = None
        entries.append(catalog_entry(
            model_id, tier, tier_order.index(tier) if routable else -1,
            availability=availability, routable=routable,
            reserved=(model_id == reserved_model),
            efforts=info.get("supported_reasoning_efforts"),
            default_effort=info.get("default_reasoning_effort"),
            estimate=estimate, note=(info.get("notes") or "")[:120],
        ))
    return entries


def _rank_of_tier(tiers, tier):
    return tiers.index(tier) if tier in tiers else None


def _floor(request, catalog, tiers, policy):
    """The lowest rank the task may run at, and the signals that put it there."""
    basis = []
    planned = request.get("planned")
    by_id = {e["id"]: e for e in catalog}
    pinned = None
    if planned is None:
        default_tier = request.get("default_tier")
        rank = _rank_of_tier(tiers, default_tier) if default_tier else 0
        basis.append(f"no plan: default tier {default_tier or tiers[0]}")
    elif planned in tiers:
        rank = tiers.index(planned)
        basis.append(f"planned tier {planned}")
    elif planned in by_id:
        pinned = planned
        rank = by_id[planned]["rank"]
        basis.append(f"pinned model {planned} ({by_id[planned]['tier']})")
    else:
        raise RoutingError(f"unknown planned model or tier {planned!r}")
    if rank is None or rank < 0:
        raise RoutingError(f"planned {planned!r} is not a routable tier")
    ceiling = max((e["rank"] for e in catalog if e["routable"] and not
                   (policy == "reserved" and e["reserved"])), default=rank)
    migrated = None
    if rank > ceiling and POLICY_RULES[policy]["plan_above_ceiling"] == "migrate-down":
        migrated = (tiers[rank], tiers[ceiling])
        basis.append(f"reserved policy: {tiers[rank]} plan migrates down to {tiers[ceiling]}")
        rank = ceiling
    failures = int(request.get("prior_failures") or 0)
    if failures:
        raised = min(rank + failures, ceiling if pinned is None else rank)
        if raised != rank:
            basis.append(f"{failures} prior failed attempt(s): floor raised {tiers[rank]} -> "
                         f"{tiers[raised]}")
            rank = raised
        else:
            basis.append(f"{failures} prior failed attempt(s): floor already at "
                         f"{'the pin' if pinned else tiers[rank]}")
    return {"tier": tiers[rank], "rank": rank, "basis": basis, "pinned": pinned,
            "migrated": migrated}


def _uncertainty(request, floor):
    if floor["pinned"]:
        return "low"
    if request.get("planned") is None:
        return "high" if not request.get("prior_failures") else "medium"
    return "medium" if request.get("prior_failures") else "low"


def _effort_for(entry, request, policy, difficult):
    """The initial effort for `entry` -> `(effort, basis)`.

    Explicit effort wins and must be supported (the caller filtered for that). Otherwise the
    model's own default; under `adaptive` a difficult task starts one step above the default
    when the host reports that step, and says so. `reserved` never chooses an effort the
    caller did not give, so the legacy dispatch line is byte-identical.
    """
    explicit = request.get("effort")
    if explicit:
        return explicit, "explicit"
    if policy == "reserved":
        return None, "host-default"
    efforts = entry.get("efforts") or []
    default = entry.get("default_effort")
    if not default or default not in efforts:
        return default, "model-default" if default else "host-default"
    if difficult:
        idx = efforts.index(default)
        if idx + 1 < len(efforts):
            return efforts[idx + 1], f"raised one step above the model default {default!r}"
    return default, "model-default"


def _shape(request, policy, difficult, capabilities):
    """The workflow shape and what its capabilities look like on this host."""
    wanted = request.get("shape")
    if wanted is None:
        if policy == "reserved":
            wanted = "graph" if request.get("in_kit") else "direct"
        else:
            wanted = "graph" if request.get("in_kit") else (
                "reviewed" if difficult and (request.get("evidence") or "red-green") ==
                "red-green" else "direct"
            )
    _check_vocab(wanted, SHAPES, "shape")
    notes = []
    shape = wanted
    while True:
        states = {c: capabilities.get(c, "unknown") for c in SHAPE_REQUIRES[shape]}
        unsupported = [c for c, s in states.items() if s == "unsupported"]
        if not unsupported or shape == "direct":
            break
        simpler = SHAPES[SHAPES.index(shape) - 1]
        notes.append(f"{shape} needs {', '.join(unsupported)}, which this host reports "
                     f"unsupported; falling back to {simpler}")
        shape = simpler
    return {
        "shape": shape, "requested": wanted, "notes": notes,
        "capabilities": states,
        "unverified": [c for c, s in states.items() if s == "unknown"],
        "unsupported": [c for c, s in states.items() if s == "unsupported"],
    }


def decide(catalog, request, policy=DEFAULT_POLICY, preference=DEFAULT_PREFERENCE,
           chosen=None, ladder=None):
    """The four routing decisions for one task -> a decision dict.

    `catalog` is the harness's rows (`catalog_entry`); `request` carries the task's signals:
    `planned` (tier word, model id, or None), `role`, `effort` (explicit or None),
    `prior_failures`, `evidence`, `brief_chars`, `excludes`, `budget` (`{"ok", "reason"}` or
    None), `capabilities` (`{name: state}` from the registry), `tiers` (the harness's own
    order), `default_tier`, `in_kit`, `shape` (to force one), `review_model`,
    `acceptance_model`, `harness`, `task_id`.

    `chosen` and `ladder` let a harness whose legacy resolver already picked (the `reserved`
    policy on Codex delegates to `resolve_assignment`, unchanged) have the decision recorded
    and explained around that pick rather than re-derived by a second rule. When `chosen` is
    None the router picks, which is the `adaptive` path.
    """
    _check_vocab(policy, POLICIES, "policy")
    _check_vocab(preference, PREFERENCES, "preference")
    tiers = tuple(request.get("tiers") or ())
    if not tiers:
        raise RoutingError("request.tiers must name the harness's tier order")
    rules = POLICY_RULES[policy]
    capabilities = request.get("capabilities") or {}
    floor = _floor(request, catalog, tiers, policy)
    difficult = (floor["rank"] > (_rank_of_tier(tiers, request.get("default_tier")) or 0)
                 or bool(request.get("prior_failures")))
    shape = _shape(request, policy, difficult, capabilities)
    budget = request.get("budget")
    excludes = set(request.get("excludes") or ())
    explicit_effort = request.get("effort")

    # ---- hard filters, in order; the first that applies is the one reported ----
    candidates = []
    for entry in catalog:
        reasons = []
        if not entry["routable"]:
            reasons.append("not-routable")
        elif entry["availability"] == "unavailable":
            reasons.append("unavailable")
        elif floor["pinned"] and entry["id"] != floor["pinned"]:
            reasons.append("pinned-elsewhere")
        elif entry["id"] in excludes:
            reasons.append("excluded")
        elif entry["reserved"] and not rules["reserved_model_implements"] \
                and request.get("role", "implementer") == "implementer":
            reasons.append("reserved")
        elif explicit_effort and entry["efforts"] is not None \
                and explicit_effort not in entry["efforts"]:
            reasons.append("effort-unsupported")
        elif entry["rank"] < floor["rank"]:
            reasons.append("below-floor")
        elif budget is not None and not budget.get("ok", True):
            reasons.append("over-budget")
        candidates.append({**entry, "eligible": not reasons, "reasons": reasons})

    eligible = [c for c in candidates if c["eligible"]]
    refusal = None
    pick = None
    if chosen is not None:
        pick = next((c for c in candidates if c["id"] == chosen), None)
        if pick is None:
            raise RoutingError(f"chosen model {chosen!r} is not in the catalog")
    elif budget is not None and not budget.get("ok", True):
        refusal = f"budget: {budget.get('reason') or 'admission refused'}"
    elif not eligible:
        held = sorted({r for c in candidates for r in c["reasons"]})
        refusal = (f"no eligible model at or above tier {floor['tier']} "
                   f"(filters that applied: {', '.join(held) or 'none'})")
        if explicit_effort and "effort-unsupported" in held:
            supporters = [c["id"] for c in candidates if "effort-unsupported" not in
                          c["reasons"] and c["efforts"]]
            refusal += (f"; effort {explicit_effort!r} is not supported by the models at that "
                        f"tier" + (f" (supported by: {', '.join(supporters)})" if supporters
                                   else ""))
    else:
        pick = _prefer(eligible, preference)

    # ---- the preference's ranking, recorded on the alternatives ----
    if pick is not None:
        for c in candidates:
            if c["eligible"] and c["id"] != pick["id"]:
                c["reasons"].append("ranked-lower")

    effort, effort_basis = (None, None)
    if pick is not None:
        effort, effort_basis = _effort_for(pick, request, policy, difficult)

    if ladder is None:
        ladder = _ladder(eligible if chosen is None else
                         [c for c in candidates if c["eligible"] or c["id"] == chosen], pick)

    estimate = _estimate(pick, request, shape["shape"], catalog)
    signals = {
        "planned": request.get("planned"),
        "prior_failures": int(request.get("prior_failures") or 0),
        "evidence": request.get("evidence"),
        "brief_chars": request.get("brief_chars"),
        "role": request.get("role", "implementer"),
        "difficult": difficult,
        "in_kit": bool(request.get("in_kit")),
    }
    preference_note = None
    if preference == "latency":
        preference_note = ("no latency data in this catalog; the choice is the balanced one "
                           "and this note says so rather than pretending otherwise")
    return {
        "v": CONTRACT_VERSION,
        "harness": request.get("harness"),
        "task_id": request.get("task_id"),
        "policy": policy,
        "policy_rules": dict(rules),
        "preference": preference,
        "preference_note": preference_note,
        "shape": shape["shape"],
        "shape_requested": shape["requested"],
        "shape_notes": shape["notes"],
        "assurance": list(SHAPE_ASSURANCE[shape["shape"]]),
        "model": pick["id"] if pick else None,
        "tier": pick["tier"] if pick else None,
        "rank": pick["rank"] if pick else None,
        "tiers": list(tiers),
        "effort": effort,
        "effort_basis": effort_basis,
        "floor": floor,
        "signals": signals,
        "uncertainty": _uncertainty(request, floor),
        "candidates": candidates,
        "ladder": list(ladder),
        "estimate": estimate,
        "capabilities": {"required": list(SHAPE_REQUIRES[shape["shape"]]),
                         "states": shape["capabilities"],
                         "unverified": shape["unverified"],
                         "unsupported": shape["unsupported"]},
        "refusal": refusal,
    }


def _prefer(eligible, preference):
    """Choose among candidates that survived every filter. Ties keep catalog order."""
    if preference == "quality":
        top = max(c["rank"] for c in eligible)
        return next(c for c in eligible if c["rank"] == top)
    low = min(c["rank"] for c in eligible)
    at_floor = [c for c in eligible if c["rank"] == low]
    if preference == "cost":
        priced = [c for c in at_floor if c["estimate"] and
                  c["estimate"].get("api_equivalent_usd") is not None]
        if priced:
            return min(priced, key=lambda c: c["estimate"]["api_equivalent_usd"])
    return at_floor[0]


def _ladder(pool, pick):
    """One candidate per rank above the pick, in catalog order."""
    if pick is None:
        return []
    ladder, seen = [], set()
    for c in sorted(pool, key=lambda c: c["rank"]):
        if c["rank"] > pick["rank"] and c["rank"] not in seen and c["id"] != pick["id"]:
            ladder.append(c["id"])
            seen.add(c["rank"])
    return ladder


def _estimate(pick, request, shape, catalog):
    """The whole workflow's estimate, per stage, from the catalog's own figures.

    Labelled est. and API-equivalent: the price engines' `usd_api` is what a token-metered
    run would cost, and a subscription run has no bill to compare it to. `priced` is False
    for that reason; a stage whose model is unpriced or unavailable is named, not zeroed.
    """
    if pick is None:
        return None
    by_id = {e["id"]: e for e in catalog}
    stages = []

    def stage(name, model_id):
        entry = by_id.get(model_id) if model_id else None
        usd = None
        if entry and entry.get("estimate"):
            usd = entry["estimate"].get("api_equivalent_usd")
        status = ("no model" if not model_id else "unavailable" if entry is None or
                  entry["availability"] == "unavailable" else "unpriced" if usd is None
                  else "est.")
        stages.append({"stage": name, "model": model_id, "api_equivalent_usd": usd,
                       "status": status})

    stage("implementation", pick["id"])
    if shape in ("reviewed", "graph"):
        stage("independent-review", request.get("review_model"))
    if shape == "graph":
        stage("acceptance", request.get("acceptance_model"))
    known = [s["api_equivalent_usd"] for s in stages if s["api_equivalent_usd"] is not None]
    profile = (pick.get("estimate") or {}).get("profile")
    return {
        "label": "est., API-equivalent, never a bill",
        "priced": False,
        "profile": profile,
        "stages": stages,
        "total_api_equivalent_usd": round(sum(known), 4) if known else None,
        "complete": len(known) == len(stages),
    }


def explain(decision):
    """The decision as an operator reads it: a few lines, every number labelled."""
    d = decision
    lines = [
        f"routing: policy={d['policy']} preference={d['preference']} shape={d['shape']} "
        f"assurance={'+'.join(d['assurance'])}"
    ]
    if d["refusal"]:
        lines.append(f"  refused: {d['refusal']}")
    else:
        effort = f" effort={d['effort']} ({d['effort_basis']})" if d["effort"] else \
            f" effort=host-default"
        lines.append(
            f"  model: {d['model']} ({d['tier']}, rank {d['rank'] + 1}/{len(d['tiers'])})"
            f"{effort}"
        )
    floor = d["floor"]
    lines.append(f"  floor: {floor['tier']} -- " + "; ".join(floor["basis"]))
    s = d["signals"]
    lines.append(
        f"  signals: planned={s['planned'] or 'none'} prior_failures={s['prior_failures']} "
        f"evidence={s['evidence'] or 'red-green (default)'} brief_chars={s['brief_chars']} "
        f"uncertainty={d['uncertainty']}"
    )
    if d["preference_note"]:
        lines.append(f"  preference: {d['preference_note']}")
    for note in d["shape_notes"]:
        lines.append(f"  shape: {note}")
    if d["ladder"]:
        lines.append(f"  ladder: {' -> '.join(d['ladder'])}")
    est = d["estimate"]
    if est:
        parts = []
        for st in est["stages"]:
            usd = st["api_equivalent_usd"]
            parts.append(f"{st['stage']}={st['model'] or '-'}:"
                         f"{'%.4f' % usd if usd is not None else st['status']}")
        total = est["total_api_equivalent_usd"]
        lines.append(
            f"  estimate ({est['label']}"
            f"{', profile ' + est['profile'] if est['profile'] else ''}): "
            + " ".join(parts)
            + (f" total={total:.4f}" if total is not None else " total=unknown")
            + ("" if est["complete"] else " (incomplete)")
        )
    alternatives = [c for c in d["candidates"] if c["id"] != d["model"]]
    if alternatives:
        lines.append("  alternatives: " + "; ".join(
            f"{c['id']} ({c['tier'] or 'no tier'}) {','.join(c['reasons']) or 'eligible'}"
            for c in alternatives
        ))
    caps = d["capabilities"]
    if caps["unsupported"] or caps["unverified"]:
        bits = []
        if caps["unsupported"]:
            bits.append("unsupported: " + ", ".join(caps["unsupported"]))
        if caps["unverified"]:
            bits.append("unverified: " + ", ".join(caps["unverified"]))
        lines.append(f"  capabilities ({d['shape']}): " + "; ".join(bits))
    return "\n".join(lines)


# ---- demo and command line ----------------------------------------------------------------------

def _demo_catalog():
    """Two synthetic rosters with different tier orders, round fake prices, no real ids."""
    def est(usd):
        return {"api_equivalent_usd": usd, "profile": "M"}
    codex_like = [
        catalog_entry("demo-cheap", "cheap", 0, "available", efforts=["low", "medium", "high"],
                      default_effort="medium", estimate=est(0.05)),
        catalog_entry("demo-mid", "mid", 1, "available", efforts=["low", "medium", "high", "max"],
                      default_effort="medium", estimate=est(0.40)),
        catalog_entry("demo-strong", "strong", 2, "available",
                      efforts=["low", "medium", "high", "max"], default_effort="low",
                      estimate=est(0.90)),
        catalog_entry("demo-top", "frontier", 3, "available", reserved=True,
                      efforts=["low", "medium", "high", "max"], default_effort="medium",
                      estimate=est(2.50)),
        catalog_entry("demo-cost-only", "cost-only", -1, "available", routable=False),
        catalog_entry("demo-gone", "mid", 1, "unavailable", estimate=est(0.30)),
    ]
    claude_like = [
        catalog_entry("demo-small", "haiku", 0, "unknown", estimate=est(0.02)),
        catalog_entry("demo-medium", "sonnet", 1, "unknown", estimate=est(0.20)),
        catalog_entry("demo-large", "opus", 2, "unknown", estimate=est(1.00)),
        catalog_entry("demo-apex", "frontier", 3, "unknown", estimate=est(3.00)),
    ]
    return codex_like, claude_like


def _demo(out=None):
    out = out or sys.stdout

    def say(line=""):
        print(line, file=out)

    codex_like, claude_like = _demo_catalog()
    tiers_c = ("cheap", "mid", "strong", "frontier")
    caps = {"dispatch": "unknown", "sandbox_read_only": "unknown", "durable_attempts": "unknown"}
    base = {"harness": "demo-codex", "task_id": "T1", "tiers": tiers_c, "default_tier": "mid",
            "capabilities": caps, "review_model": "demo-strong", "acceptance_model": "demo-top",
            "brief_chars": 900, "evidence": "red-green"}

    say("== the same hard task under both policies (planned frontier, one prior failure) ==")
    req = {**base, "planned": "frontier", "prior_failures": 1}
    say(explain(decide(codex_like, req, "reserved", chosen="demo-strong", ladder=[])))
    say()
    say(explain(decide(codex_like, req, "adaptive", "quality")))
    say()
    say("== the reserved model is unavailable; the worker-only path still routes ==")
    gone = [dict(e, availability="unavailable") if e["reserved"] else e for e in codex_like]
    say(explain(decide(gone, {**base, "planned": "mid"}, "adaptive")))
    say()
    say("== an explicit pin is honoured; an unsupported effort is refused, not substituted ==")
    say(explain(decide(codex_like, {**base, "planned": "demo-cheap"}, "adaptive", "quality")))
    say()
    say(explain(decide(codex_like, {**base, "planned": "demo-cheap", "effort": "max"},
                       "adaptive")))
    say()
    say("== cost preference within the floor; budget refusal before any choice ==")
    say(explain(decide(codex_like, {**base, "planned": "mid"}, "adaptive", "cost")))
    say()
    say(explain(decide(codex_like, {**base, "planned": "mid",
                                    "budget": {"ok": False, "reason": "max-dispatches=3 reached"}},
                       "adaptive")))
    say()
    say("== a different roster, a different tier order, the same rule ==")
    tiers_k = ("haiku", "sonnet", "opus", "frontier")
    say(explain(decide(claude_like, {"harness": "demo-claude", "task_id": "T9", "tiers": tiers_k,
                                     "default_tier": "sonnet", "planned": "opus",
                                     "capabilities": caps, "brief_chars": 3000},
                       "adaptive", "cost")))


def _cli(argv=None):
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(
        prog="routing_policy.py",
        description="Workflow shape, model, initial effort, and assurance as four separate "
                    "decisions. `decide` routes one request against a harness's own pricing "
                    "file; `demo` walks synthetic rosters and spends nothing.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("decide", help="route one request against a harness's pricing file")
    p.add_argument("--harness", required=True, choices=("claude", "copilot", "codex"))
    p.add_argument("--pricing-dir", default=str(Path(__file__).resolve().parent.parent / "data"),
                   help="directory holding the pricing files (default: the repo's data/)")
    p.add_argument("--planned", default=None, help="tier word, model id, or omitted")
    p.add_argument("--policy", default=DEFAULT_POLICY, choices=POLICIES)
    p.add_argument("--preference", default=DEFAULT_PREFERENCE, choices=PREFERENCES)
    p.add_argument("--effort", default=None)
    p.add_argument("--prior-failures", type=int, default=0)
    p.add_argument("--shape", default=None, choices=SHAPES)
    p.add_argument("--json", action="store_true")
    sub.add_parser("demo", help="synthetic rosters under both policies; spends nothing")
    args = parser.parse_args(argv)

    if args.cmd == "demo":
        _demo()
        return 0

    files = {"claude": "pricing.json", "copilot": "pricing.copilot.json",
             "codex": "pricing.codex.json"}
    orders = {"claude": ("haiku", "sonnet", "opus", "frontier"),
              "copilot": ("cheap", "mid", "strong", "frontier"),
              "codex": ("cheap", "mid", "strong", "frontier")}
    pricing = json.loads((Path(args.pricing_dir) / files[args.harness]).read_text())
    policy_block = pricing.get("orchestration_policy") or {}
    reserved = policy_block.get("orchestrator_model") if args.harness == "codex" else None
    cat = catalog_from_pricing(pricing, args.harness, orders[args.harness],
                               reserved_model=reserved)
    request = {
        "harness": args.harness, "tiers": orders[args.harness],
        "default_tier": policy_block.get("default_worker_tier") or orders[args.harness][1],
        "planned": args.planned, "effort": args.effort, "prior_failures": args.prior_failures,
        "shape": args.shape, "capabilities": {},
    }
    chosen = None
    if args.policy == "reserved" and args.harness == "codex" and reserved:
        # The command line is a preview: it does not run the harness's own resolver, so the
        # reserved policy is applied by this module's rules and says so.
        request["preview_note"] = "reserved rules applied here; the driver uses its own resolver"
    try:
        decision = decide(cat, request, args.policy, args.preference, chosen=chosen)
    except RoutingError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(decision, indent=2, sort_keys=True))
    else:
        print(explain(decision))
    return 0 if decision["model"] else 1


if __name__ == "__main__":
    sys.exit(_cli())
