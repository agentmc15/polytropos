#!/usr/bin/env python3
"""Bench routing — rank published benchmark entries, recommend model+effort per orchestration
role given what each harness can actually dispatch, and check that recommendation against this
repo's OWN measured outcomes.

The dataset (``data/benchmarks.aa.json``, read-only — never modified here) is the Artificial
Analysis Intelligence Index: a general-capability composite (HLE, GPQA, CritPt, AA-Omniscience,
...), screenshot-transcribed, NOT this repo's pricing. Every dollar figure from that file is
``usd_per_task`` — a benchmark-WORKLOAD cost, useful only for RELATIVE ranking within the file,
never summed, never presented as a bill, and never mixed with dollars from ``routing_scorecard``
(a different measurement entirely: this repo's own execution ledger). Coding Index and Agentic
Index are separate boards not included in this file — a strong general-index entry is not
automatically strong at agentic tool use; every card here says so.

Subcommands:

  rank     Ranked tables from the benchmark file: by intelligence index, by VALUE (index /
           usd_per_task — a derived ranking ratio, never a price), and a "capability frontier"
           (the cheapest entry clearing each index floor — a value-for-money skyline).
           ``--provider``, ``--model``, ``--top N``.

  roles    Per-harness role assignments — what to dispatch for each orchestration role, given
           what that harness can ACTUALLY select. Availability is derived at run time by joining
           the benchmark file's ``model`` ids against ``data/pricing.json`` (Claude Code),
           ``data/pricing.codex.json`` (Codex), and ``data/pricing.copilot.json`` (Copilot) —
           never a hardcoded model id or roster. A real join hazard: benchmark ids use dashes
           (``claude-opus-4-8``) while ``pricing.copilot.json`` uses dots (``claude-opus-4.8``);
           ``normalize_id`` folds both sides to one shape before comparing. A benchmark entry
           that matches no available model is reported as UNAVAILABLE, never silently dropped,
           and the card states how many entries were dispatchable vs. total for that harness.

           Role policy is the module-level ``ROLE_POLICY`` constant below — NOT inline literals —
           and is overridable per run with a repeatable ``--floor role=N`` flag. Cost-sensitive
           roles (dispatched many times per kit) pick the best VALUE clearing their floor;
           cost-insensitive roles (run once, or once per phase) pick the CHEAPEST entry clearing
           their floor. When no available entry clears a floor, the card says so by name and
           names the best available entry instead of emitting nothing.

           ``ROLE_POLICY``'s floors are THIS REPO'S JUDGEMENT, not published data — the one
           editorial input in this whole tool. Tune them for your own workload with ``--floor``.

  compare  The point of the tool: join the benchmark PRIOR against this repo's own MEASURED
           outcomes and flag disagreement. Reuses ``bin/routing_scorecard.py`` via the importlib
           pattern (``bin/context_weight.py``'s ``_load``) for ``scan_kits``/``build_history`` —
           ledger parsing is never re-implemented here. Each ``roles`` recommendation computed
           for the CLAUDE harness (the only harness whose models map onto this repo's own
           haiku/sonnet/opus/frontier tier vocabulary, via ``data/pricing.json``'s ``tier``
           field — never a hardcoded mapping) is checked against the ledger's per-tier first-try
           rate for the tier one rung cheaper — BUT ONLY for the role that rate actually
           evidences. This repo's ledger records per-TASK ``outcome:`` lines, which are
           implementer work; no ``outcome:`` line carries a role, and the separate ``agent:``
           ledger that DOES carry ``role=`` carries no result. So ``ROLE_LEDGER_EVIDENCE``
           restricts the ledger-backed verdict to ``"implementer"`` alone — every other
           non-cheapest-tier role (architect/planner, reviewer, orchestrator, verifier) gets
           ``no_role_evidence`` instead of a rate borrowed from a different job function; the
           benchmark's pick for that role stands unchallenged rather than being falsely
           confirmed or refuted. ``mechanical sweep`` is unaffected by the gate: when its pick
           lands on the cheapest repo tier (typical for its floor) it gets ``cheapest_tier`` — a
           statement about the tier ladder, not a borrowed outcome claim — and only falls under
           the evidence gate if a ``--floor`` override ever pushed its pick off the cheapest
           tier. For "implementer", the card states PLAINLY whether the measured record
           CONTRADICTS the benchmark recommendation, and that MEASURED OUTCOMES WIN — the
           benchmark is a general-capability composite; the ledger is this repo's own workload.
           It reports the MARGINAL GAIN (not just both numbers): a benchmark-favored upgrade
           whose measured gain is at or below ``MARGINAL_GAIN_THRESHOLD`` is flagged NOT
           supported, even when the gain is nominally positive (100% vs. 97% is real but
           marginal). Where a tier has fewer than ``routing_scorecard.LIVE_MIN_SAMPLE`` finished
           tasks, the card says "insufficient sample" rather than computing a confident rate.

           Coverage gaps are surfaced from the DATA, never hardcoded: when the model picked for
           a role and the tier-mate it would displace are measured at a different number of
           distinct effort points (``effort_coverage``), the card notes it — a comparison only
           covers the effort points actually measured, and a claim like "Opus at medium beats
           Sonnet" is a claim about measured points only when Sonnet has no medium-effort entry.

  demo     Synthetic smoke over an in-memory benchmark fixture, an in-memory three-harness
           pricing bundle, and one throwaway temp kit dir — no real ``data/pricing*.json``, no
           real ``data/benchmarks.aa.json``, no real kit ledger, no ``~/``. Exercises rank,
           roles (all three harnesses, including the dash/dot join), and compare (including a
           ``not_supported`` verdict and a ``cheapest_tier`` no-comparison branch). Exit 0.

Every subcommand renders markdown by default and machine-readable JSON with ``--json`` (the
JSON is the same plain, already-JSON-safe card dict the markdown renderer consumes — a thin
wrapper, never a second implementation). Every pure function here is independent of argparse —
CLI parsing lives only in the functions below the "CLI" banner — so every behavior is testable
without spawning the CLI.

Read-only, stdlib-only, no network. Injectable seams so tests never touch real data:
``--benchmarks`` (default ``data/benchmarks.aa.json``), ``--pricing-dir`` (default ``data/``,
must contain ``pricing.json``/``pricing.codex.json``/``pricing.copilot.json``), ``--kits-dir``
(default ``routing_scorecard.DEFAULT_KITS_DIR`` — reused, never duplicated). This module never
writes anything and never touches ``Path.home()``.

Usage:
  bench_routing.py rank    [--benchmarks PATH] [--provider P] [--model M] [--top N] [--json]
  bench_routing.py roles   [--benchmarks PATH] [--pricing-dir DIR]
                           [--harness claude|codex|copilot|all] [--floor role=N ...] [--json]
  bench_routing.py compare [--benchmarks PATH] [--pricing-dir DIR] [--kits-dir DIR]
                           [--floor role=N ...] [--json]
  bench_routing.py demo    [--json]
"""

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------------------------
# Reuse, never re-implement: routing_scorecard's TASKS.md/NOTES.md ledger parsing and cross-kit
# aggregation (the `_load` pattern from bin/context_weight.py / bin/session_cost.py).


def _load(name):
    spec = importlib.util.spec_from_file_location(name, PLUGIN_ROOT / "bin" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rs = _load("routing_scorecard")   # scan_kits, build_history, LIVE_TIER_ORDER, LIVE_MIN_SAMPLE


# ---------------------------------------------------------------------------------------------
# Sanctioned constants. Role floors are structural POLICY (this repo's editorial judgement, not
# published data — see the module docstring); the marginal-gain threshold is the same species —
# never a price, price ratio, model id, or pricing date.

SCHEMA_VERSION = 1

DEFAULT_BENCHMARKS_PATH = PLUGIN_ROOT / "data" / "benchmarks.aa.json"
DEFAULT_PRICING_DIR = PLUGIN_ROOT / "data"

PRICING_FILENAMES = {
    "claude": "pricing.json",
    "codex": "pricing.codex.json",
    "copilot": "pricing.copilot.json",
}
HARNESSES = ("claude", "codex", "copilot")

NON_ROUTING_TIER = "non-routing"

# (role, min_index, cost_sensitive). Cost-sensitive roles run many times per kit and pick the
# best VALUE (index / usd_per_task) clearing the floor; cost-insensitive roles run once (or once
# per phase) and pick the CHEAPEST entry clearing the floor — squeezing value on a one-shot call
# buys nothing. These floors are THIS REPO'S judgement about what "good enough" means per role,
# read off the general-capability composite — not a fact the benchmark publishes. Override per
# run with a repeatable ``--floor role=N`` (see ``parse_floor_overrides``).
ROLE_POLICY = (
    ("architect/planner",  58, False),
    ("reviewer",           55, False),
    ("orchestrator",       54, True),
    ("implementer",        49, True),
    ("verifier",           46, True),
    ("mechanical sweep",   30, True),
)
ROLE_NAMES = tuple(role for role, _floor, _cs in ROLE_POLICY)

ROLE_POLICY_NOTE = (
    "Role floors (below) are this repo's editorial judgement read off the general-capability "
    "index, not published data — the one editorial input in this tool. Tune them with a "
    "repeatable --floor role=N. Cost-sensitive roles pick the best VALUE clearing their floor; "
    "cost-insensitive roles pick the CHEAPEST entry clearing their floor."
)

# `compare`'s materiality bar: a benchmark-favored upgrade whose measured first-try-rate gain is
# AT OR BELOW this threshold is flagged NOT supported even when nominally positive (this repo's
# concrete case: sonnet already clears 97% over 86 tasks; opus clears 100% over 18 — a real but
# marginal ~3-point gain that does not justify an upgrade). Editorial, like ROLE_POLICY's floors,
# and of the same species (a policy threshold on a rate, never a price).
MARGINAL_GAIN_THRESHOLD = 0.05

# The ledger's outcome: lines record per-TASK results — implementer work, dispatched by the
# `model:` a kit's TASKS.md pins per task. No `outcome:` line carries a role= field, and the
# separate `agent:` ledger (which DOES carry role=) carries no result= — so architect/planner,
# reviewer, orchestrator, and verifier have no role-scoped evidence in this repo's ledger at
# all. Only "implementer" may be judged against a measured first-try rate; every other role
# gets `no_role_evidence` rather than a rate that measures a different job function.
ROLE_LEDGER_EVIDENCE = frozenset({"implementer"})

LEDGER_SCOPE_NOTE = (
    "This repo's ledger records per-task outcomes (implementer work) — it carries no "
    "per-role result data, so only the 'implementer' role below is judged against it; every "
    "other role is reported no_role_evidence rather than judged on a rate that doesn't bear "
    "on it."
)
EVIDENCE_HOWTO_NOTE = (
    "To get evidence for the other roles: NOTES.md agent: lines already carry role=; "
    "recording a result= there too (not just per-task outcome:) would let this tool judge "
    "them."
)

CAPABILITY_CAVEAT = (
    "The index is a general-capability composite (HLE, GPQA, CritPt, AA-Omniscience, ...). "
    "Coding Index and Agentic Index are separate boards not included here — a strong entry is "
    "not automatically strong at agentic tool use."
)
USD_PER_TASK_CAVEAT = (
    "usd_per_task is a benchmark-workload cost (screenshot-transcribed), never this repo's "
    "pricing and never summed into a bill — see data/pricing*.json for that."
)


# ---------------------------------------------------------------------------------------------
# Pure functions — loading.


def load_benchmarks(path):
    with open(path) as f:
        return json.load(f)


def load_pricing_bundle(pricing_dir):
    """Load all three harness pricing files from ``pricing_dir`` (the injectable seam — tests
    point this at a temp dir; the real CLI default is ``data/``). Returns ``{"claude": ...,
    "codex": ..., "copilot": ...}``, each the raw parsed pricing JSON."""
    d = Path(pricing_dir)
    return {harness: json.loads((d / filename).read_text())
            for harness, filename in PRICING_FILENAMES.items()}


# ---------------------------------------------------------------------------------------------
# Pure functions — id normalization + harness availability (the dash/dot join).


def normalize_id(model_id):
    """Fold a model id to one comparable shape: lowercase, dots -> dashes. Benchmark Claude ids
    use dashes (``claude-opus-4-8``); ``pricing.copilot.json`` uses dots (``claude-opus-4.8``).
    Normalizing both sides symmetrically makes the join correct regardless of which side (if
    either) already used dashes."""
    return (model_id or "").strip().lower().replace(".", "-")


def available_ids_for_harness(pricing):
    """Normalized model ids a harness can actually dispatch, from its own pricing file's
    ``models`` map. A model whose ``tier`` is ``NON_ROUTING_TIER`` (e.g. Codex's
    ``codex-auto-review`` — opaque, not user-selectable) is excluded: it is priced but not a
    routing target. Returns ``(ids_set, raw_map)`` where ``raw_map`` maps normalized id -> the
    original pricing key (first one seen, for display)."""
    ids = set()
    raw = {}
    for key, meta in (pricing.get("models") or {}).items():
        if isinstance(meta, dict) and meta.get("tier") == NON_ROUTING_TIER:
            continue
        norm = normalize_id(key)
        ids.add(norm)
        raw.setdefault(norm, key)
    return ids, raw


def dispatchable_entries(entries, available_ids):
    return [e for e in entries if normalize_id(e.get("model")) in available_ids]


def unavailable_entries(entries, available_ids):
    return [e for e in entries if normalize_id(e.get("model")) not in available_ids]


def claude_tier_for_model(model_id, claude_pricing):
    """The ``data/pricing.json`` tier (haiku/sonnet/opus/frontier) for ``model_id`` — joined by
    normalized id, never a hardcoded model->tier table. ``None`` when no pricing key matches."""
    norm = normalize_id(model_id)
    for key, meta in (claude_pricing.get("models") or {}).items():
        if normalize_id(key) == norm:
            return meta.get("tier")
    return None


# ---------------------------------------------------------------------------------------------
# Pure functions — ranking (rank subcommand).


def value_of(entry):
    """index / usd_per_task — a derived RANKING RATIO, never a price. ``None`` when
    usd_per_task is missing or non-positive (value is undefined, not zero)."""
    usd = entry.get("usd_per_task")
    if not usd or usd <= 0:
        return None
    return entry["intelligence_index"] / usd


def rank_by_index(entries):
    """Descending intelligence_index; usd_per_task ascending as a deterministic tiebreak."""
    return sorted(entries, key=lambda e: (-e["intelligence_index"], e.get("usd_per_task") or 0))


def rank_by_value(entries):
    """Descending value (see ``value_of``) over entries where value is defined. Returns
    ``(ranked, excluded)`` — ``excluded`` holds entries with no usable usd_per_task, reported
    rather than silently dropped."""
    valued = [e for e in entries if value_of(e) is not None]
    excluded = [e for e in entries if value_of(e) is None]
    ranked = sorted(valued, key=lambda e: -value_of(e))
    return ranked, excluded


def pareto_frontier(entries):
    """The capability frontier: the cheapest entry clearing each intelligence-index floor — a
    value-for-money skyline. Sorted by index descending (usd_per_task ascending tiebreak); an
    entry is KEPT only when it is STRICTLY cheaper than every higher-or-equal-index entry
    already kept (i.e. no entry at or above its index is at least as cheap — the classic
    Pareto/skyline property). Entries with no usable usd_per_task are excluded (undefined
    "cheapest")."""
    usable = [e for e in entries if value_of(e) is not None]
    ordered = sorted(usable, key=lambda e: (-e["intelligence_index"], e["usd_per_task"]))
    frontier = []
    best_cost = None
    for e in ordered:
        if best_cost is None or e["usd_per_task"] < best_cost:
            frontier.append(e)
            best_cost = e["usd_per_task"]
    return frontier


def effort_coverage(entries):
    """model -> list of distinct efforts recorded for it, in first-seen order. Used both to
    report the dataset's effort-point coverage (rank/roles footers) and to detect a coverage
    GAP between a picked model and the tier-mate it would displace (compare)."""
    cov = {}
    for e in entries:
        model = e.get("model")
        if model is None:
            continue
        lst = cov.setdefault(model, [])
        effort = e.get("effort")
        if effort not in lst:
            lst.append(effort)
    return cov


def coverage_gaps(coverage):
    """From an ``effort_coverage`` map, the models measured at FEWER effort points than the
    dataset's own ceiling (the most effort points recorded for any single model in this map) —
    computed from the data, never a hardcoded example. Returns ``{"ceiling": N, "gaps": [...]}``
    where each gap is ``{"model": m, "efforts": count}``, sorted by count ascending then model
    name. Empty map -> ``{"ceiling": 0, "gaps": []}``."""
    if not coverage:
        return {"ceiling": 0, "gaps": []}
    counts = {m: len(effs) for m, effs in coverage.items()}
    ceiling = max(counts.values())
    gaps = sorted(
        ({"model": m, "efforts": c} for m, c in counts.items() if c < ceiling),
        key=lambda g: (g["efforts"], g["model"]),
    )
    return {"ceiling": ceiling, "gaps": gaps}


def build_rank_card(benchmarks, provider=None, model=None, top=None):
    entries = benchmarks.get("entries", [])
    if provider:
        entries = [e for e in entries if e.get("provider") == provider]
    if model:
        entries = [e for e in entries if e.get("model") == model]

    by_index = rank_by_index(entries)
    by_value, value_excluded = rank_by_value(entries)
    frontier = pareto_frontier(entries)
    if top and top > 0:
        by_index = by_index[:top]
        by_value = by_value[:top]
        frontier = frontier[:top]

    # Coverage is reported over the WHOLE dataset (never the filtered view) — a gap is a fact
    # about the benchmark's own measurement coverage, independent of --provider/--model.
    gaps = coverage_gaps(effort_coverage(benchmarks.get("entries", [])))

    return {
        "schema_version": SCHEMA_VERSION,
        "source": benchmarks.get("source"),
        "index_name": benchmarks.get("index_name"),
        "cached_date": benchmarks.get("cached_date"),
        "transcribed_from": benchmarks.get("transcribed_from"),
        "caveats": benchmarks.get("caveats", []),
        "filters": {"provider": provider, "model": model, "top": top},
        "by_index": by_index,
        "by_value": by_value,
        "value_excluded": value_excluded,
        "frontier": frontier,
        "coverage_gaps": gaps,
    }


# ---------------------------------------------------------------------------------------------
# Pure functions — role recommendation (roles + compare).


def _pick(pool, cost_sensitive):
    """One entry from ``pool`` (all already clearing a role's floor): best VALUE for a
    cost-sensitive role, cheapest for a cost-insensitive one. Deterministic tiebreaks: value ties
    favor the higher index; cost ties favor the higher index."""
    if cost_sensitive:
        return max(pool, key=lambda e: (value_of(e) or 0.0, e["intelligence_index"]))
    return min(pool, key=lambda e: (e["usd_per_task"], -e["intelligence_index"]))


def recommend_role(entries_available, role, floor, cost_sensitive):
    """The role recommendation over entries a harness can actually dispatch.

    Returns ``{"role", "floor", "cost_sensitive", "picked", "clears_floor", "best_available",
    "clearing"}``. ``clearing`` is every available (priced, usable) entry meeting the floor —
    exposed so ``compare`` can re-filter it by tier without recomputing the floor. When nothing
    clears, ``picked`` is ``None`` and ``best_available`` names the highest-index entry among
    what IS available (never silence)."""
    usable = [e for e in entries_available if value_of(e) is not None]
    clearing = [e for e in usable if e["intelligence_index"] >= floor]
    if not clearing:
        best = max(usable, key=lambda e: e["intelligence_index"]) if usable else None
        return {
            "role": role, "floor": floor, "cost_sensitive": cost_sensitive,
            "picked": None, "clears_floor": False, "best_available": best, "clearing": [],
        }
    picked = _pick(clearing, cost_sensitive)
    return {
        "role": role, "floor": floor, "cost_sensitive": cost_sensitive,
        "picked": picked, "clears_floor": True, "best_available": None, "clearing": clearing,
    }


def parse_floor_overrides(raw):
    """Parse repeatable ``--floor role=N`` tokens into a ``{role: floor}`` override dict.
    Raises ``ValueError`` (never a crash) on a malformed token, an unrecognized role name, or a
    non-integer floor — the caller turns that into a clean CLI exit."""
    floors = {}
    for tok in raw:
        if "=" not in tok:
            raise ValueError(f"invalid --floor {tok!r} — expected role=N")
        role, val = tok.split("=", 1)
        role = role.strip()
        if role not in ROLE_NAMES:
            raise ValueError(
                f"unknown role {role!r} in --floor — valid roles: {', '.join(ROLE_NAMES)}"
            )
        try:
            floors[role] = int(val.strip())
        except ValueError:
            raise ValueError(f"invalid --floor {tok!r} — floor must be an integer")
    return floors


def effective_floors(floors):
    """Every ``ROLE_POLICY`` role's floor, with ``floors`` overrides applied — for display."""
    return {role: floors.get(role, default) for role, default, _cs in ROLE_POLICY}


def build_roles_card(benchmarks, pricing_bundle, harnesses, floors):
    entries = benchmarks.get("entries", [])
    sections = []
    for harness in harnesses:
        available_ids, _raw = available_ids_for_harness(pricing_bundle[harness])
        avail = dispatchable_entries(entries, available_ids)
        unavail = unavailable_entries(entries, available_ids)
        role_rows = []
        for role, default_floor, cost_sensitive in ROLE_POLICY:
            floor = floors.get(role, default_floor)
            rec = recommend_role(avail, role, floor, cost_sensitive)
            role_rows.append({
                "role": role, "floor": floor, "cost_sensitive": cost_sensitive,
                "picked": rec["picked"], "clears_floor": rec["clears_floor"],
                "best_available": rec["best_available"],
            })
        sections.append({
            "harness": harness,
            "dispatchable": len(avail),
            "total": len(entries),
            "unavailable": [e["label"] for e in unavail],
            "roles": role_rows,
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "source": benchmarks.get("source"),
        "index_name": benchmarks.get("index_name"),
        "cached_date": benchmarks.get("cached_date"),
        "transcribed_from": benchmarks.get("transcribed_from"),
        "caveats": benchmarks.get("caveats", []),
        "role_policy_note": ROLE_POLICY_NOTE,
        "floors": effective_floors(floors),
        "sections": sections,
    }


# ---------------------------------------------------------------------------------------------
# Pure functions — compare (the point of the tool).


def build_compare_card(benchmarks, pricing_bundle, kits_dir, floors):
    """Join the benchmark PRIOR (Claude-harness role recommendations) against this repo's
    MEASURED ledger (``routing_scorecard.scan_kits``/``build_history``, reused — never
    re-implemented) and flag disagreement. See the module docstring for the full contract."""
    entries = benchmarks.get("entries", [])
    claude_pricing = pricing_bundle["claude"]
    available_ids, _raw = available_ids_for_harness(claude_pricing)
    avail = dispatchable_entries(entries, available_ids)
    coverage = effort_coverage(entries)

    records, scan_notes = rs.scan_kits(kits_dir)
    history = rs.build_history(kits_dir, records, {}, None, scan_notes)
    tiers = history["tiers"]

    rows = []
    for role, default_floor, cost_sensitive in ROLE_POLICY:
        floor = floors.get(role, default_floor)
        rec = recommend_role(avail, role, floor, cost_sensitive)
        row = {"role": role, "floor": floor, "cost_sensitive": cost_sensitive,
               "picked": rec["picked"]}

        picked = rec["picked"]
        if picked is None:
            best = rec["best_available"]
            row["verdict"] = "no_recommendation"
            row["explanation"] = (
                f"no Claude-dispatchable entry clears the {floor} floor for {role}; "
                f"best available: {best['label'] if best else 'none available at all'}."
            )
            rows.append(row)
            continue

        rec_tier = claude_tier_for_model(picked["model"], claude_pricing)
        row["recommended_tier"] = rec_tier
        if rec_tier not in rs.LIVE_TIER_ORDER:
            row["verdict"] = "no_repo_tier"
            row["explanation"] = (
                f"{picked['label']} has no mapped tier in data/pricing.json — no ledger "
                "comparison is possible for this pick."
            )
            rows.append(row)
            continue

        idx = rs.LIVE_TIER_ORDER.index(rec_tier)
        if idx == 0:
            row["verdict"] = "cheapest_tier"
            row["current_tier"] = None
            row["explanation"] = (
                f"{rec_tier} is this repo's cheapest tier — no cheaper alternative to "
                "compare it against."
            )
            rows.append(row)
            continue

        current_tier = rs.LIVE_TIER_ORDER[idx - 1]
        row["current_tier"] = current_tier

        # ROLE-EVIDENCE GATE. The ledger's outcome: lines are per-TASK results — implementer
        # work. Only the "implementer" role has role-scoped evidence in it; a benchmark
        # recommendation for any other role that would otherwise need a ledger lookup here
        # (architect/planner, reviewer, orchestrator, verifier) must NOT be judged against a
        # rate that measures a different job function. Say so plainly and quote NO first-try
        # number — that is the whole fix (a borrowed number is worse than no verdict).
        if role not in ROLE_LEDGER_EVIDENCE:
            row["verdict"] = "no_role_evidence"
            row["explanation"] = (
                "no role evidence — the ledger's outcome: lines are per-task (implementer) "
                f"results only, not per-{role} results; the benchmark's {rec_tier} "
                f"recommendation for {role} stands unchallenged — neither confirmed nor "
                "refuted."
            )
            rows.append(row)
            continue

        rec_stats = tiers[rec_tier]
        cur_stats = tiers[current_tier]
        row["measured"] = {
            "recommended_tier": {"tier": rec_tier, "with_outcome": rec_stats["with_outcome"],
                                  "first_try_rate": rec_stats["first_try_rate"]},
            "current_tier": {"tier": current_tier, "with_outcome": cur_stats["with_outcome"],
                              "first_try_rate": cur_stats["first_try_rate"]},
        }

        insufficient = (
            rec_stats["with_outcome"] < rs.LIVE_MIN_SAMPLE
            or cur_stats["with_outcome"] < rs.LIVE_MIN_SAMPLE
            or rec_stats["first_try_rate"] is None
            or cur_stats["first_try_rate"] is None
        )
        if insufficient:
            row["verdict"] = "insufficient_sample"
            row["explanation"] = (
                f"insufficient sample — {current_tier} has {cur_stats['with_outcome']} "
                f"finished task(s), {rec_tier} has {rec_stats['with_outcome']}; need at least "
                f"{rs.LIVE_MIN_SAMPLE} on both tiers before this repo's ledger can judge the "
                "upgrade."
            )
            rows.append(row)
            continue

        gain = rec_stats["first_try_rate"] - cur_stats["first_try_rate"]
        row["marginal_gain"] = gain
        supported = gain > MARGINAL_GAIN_THRESHOLD
        row["verdict"] = "supported" if supported else "not_supported"
        row["explanation"] = (
            "measured outcomes win: "
            f"{current_tier} already clears {cur_stats['first_try_rate'] * 100:.0f}% first-try "
            f"over {cur_stats['with_outcome']} task(s); {rec_tier} clears "
            f"{rec_stats['first_try_rate'] * 100:.0f}% over {rec_stats['with_outcome']} — the "
            f"upgrade buys ~{gain * 100:.0f} point(s), which is "
            + ("enough to support it." if supported
               else f"NOT enough to support it (threshold {MARGINAL_GAIN_THRESHOLD * 100:.0f}).")
        )

        # Coverage-gap note: the incumbent is whichever available, floor-clearing entry at
        # current_tier this same selection rule would have picked — computed from `clearing`
        # (never re-filtered from scratch), so it obeys the same floor/cost-sensitivity as the
        # recommendation itself.
        tier_pool = [e for e in rec["clearing"]
                     if claude_tier_for_model(e["model"], claude_pricing) == current_tier]
        incumbent = _pick(tier_pool, cost_sensitive) if tier_pool else None
        row["incumbent"] = incumbent
        if incumbent is not None:
            picked_efforts = coverage.get(picked["model"], [])
            incumbent_efforts = coverage.get(incumbent["model"], [])
            if len(picked_efforts) != len(incumbent_efforts):
                row["coverage_note"] = (
                    f"coverage gap: {picked['model']} is measured at {len(picked_efforts)} "
                    f"effort point(s) ({', '.join(picked_efforts)}); {incumbent['model']} is "
                    f"measured at {len(incumbent_efforts)} ({', '.join(incumbent_efforts)}) — "
                    "this comparison covers only the effort points actually measured on each "
                    "side, not every possible effort level of either model."
                )

        rows.append(row)

    return {
        "schema_version": SCHEMA_VERSION,
        "source": benchmarks.get("source"),
        "index_name": benchmarks.get("index_name"),
        "cached_date": benchmarks.get("cached_date"),
        "transcribed_from": benchmarks.get("transcribed_from"),
        "caveats": benchmarks.get("caveats", []),
        "kits_dir": str(kits_dir),
        "min_sample": rs.LIVE_MIN_SAMPLE,
        "marginal_gain_threshold": MARGINAL_GAIN_THRESHOLD,
        "ledger_scope_note": LEDGER_SCOPE_NOTE,
        "evidence_howto_note": EVIDENCE_HOWTO_NOTE,
        "scan_notes": scan_notes,
        "rows": rows,
    }


# ---------------------------------------------------------------------------------------------
# Rendering — shared footer (provenance + caveats, per card).


def _footer(card):
    lines = []
    src = card.get("source")
    idx_name = card.get("index_name")
    if src or idx_name:
        lines.append(f"Source: {src} — {idx_name}, cached {card.get('cached_date')}.")
    transcribed = card.get("transcribed_from")
    if transcribed:
        lines.append(f"Provenance: {transcribed}")
    lines.append(USD_PER_TASK_CAVEAT)
    for c in card.get("caveats", []):
        lines.append(f"- {c}")
    return "\n".join(lines)


def _fmt_rate(rate):
    return f"{rate * 100:.0f}%" if rate is not None else "n/a"


# ---------------------------------------------------------------------------------------------
# Rendering — rank.


def render_rank_markdown(card):
    out = [f"# Benchmark ranking — {card['index_name']} ({card['source']})\n"]
    f = card["filters"]
    bits = [f"{k}={v}" for k, v in (("provider", f["provider"]), ("model", f["model"]),
                                     ("top", f["top"])) if v]
    if bits:
        out.append(f"filters: {', '.join(bits)}\n")

    out.append("## By intelligence index\n")
    out.append("| Rank | Entry | Provider | Effort | Index | usd_per_task (est.) |")
    out.append("|---:|---|---|---|---:|---:|")
    for i, e in enumerate(card["by_index"], 1):
        out.append(f"| {i} | {e['label']} | {e['provider']} | {e['effort']} "
                    f"| {e['intelligence_index']} | ${e['usd_per_task']:.2f} |")
    out.append("")

    out.append("## By value (index / usd_per_task — a ranking ratio, never a price)\n")
    out.append("| Rank | Entry | Provider | Effort | Index | Value |")
    out.append("|---:|---|---|---|---:|---:|")
    for i, e in enumerate(card["by_value"], 1):
        out.append(f"| {i} | {e['label']} | {e['provider']} | {e['effort']} "
                    f"| {e['intelligence_index']} | {value_of(e):.1f} |")
    if card["value_excluded"]:
        n = len(card["value_excluded"])
        out.append(f"\n({n} entr{'y' if n == 1 else 'ies'} excluded — no usable usd_per_task)")
    out.append("")

    out.append("## Capability frontier (cheapest entry clearing each index floor)\n")
    out.append("| Entry | Provider | Effort | Index | usd_per_task (est.) |")
    out.append("|---|---|---|---:|---:|")
    for e in card["frontier"]:
        out.append(f"| {e['label']} | {e['provider']} | {e['effort']} "
                    f"| {e['intelligence_index']} | ${e['usd_per_task']:.2f} |")
    out.append("")

    gaps = card["coverage_gaps"]
    if gaps["gaps"]:
        names = ", ".join(
            f"{g['model']} ({g['efforts']} effort point{'s' if g['efforts'] != 1 else ''})"
            for g in gaps["gaps"]
        )
        out.append(
            f"Effort coverage gap: up to {gaps['ceiling']} effort point(s) measured for a "
            f"single model elsewhere in this dataset; measured at fewer for: {names}. A "
            "cross-model comparison holds only at the specific effort points actually "
            "measured.\n"
        )

    out.append(_footer(card))
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------
# Rendering — roles.


def render_roles_markdown(card):
    out = [f"# Role routing — {card['index_name']} ({card['source']})\n"]
    out.append(card["role_policy_note"] + "\n")
    for sec in card["sections"]:
        out.append(f"## {sec['harness']}\n")
        out.append(
            f"{sec['dispatchable']}/{sec['total']} benchmark entries dispatchable via "
            f"{sec['harness']}.\n"
        )
        out.append("| Role | Floor | Selection | Pick | Index | usd_per_task (est.) | Clears |")
        out.append("|---|---:|---|---|---:|---:|---|")
        for r in sec["roles"]:
            sel = "value (cost-sensitive)" if r["cost_sensitive"] else "cheapest (cost-insensitive)"
            if r["picked"]:
                p = r["picked"]
                out.append(f"| {r['role']} | {r['floor']} | {sel} | {p['label']} "
                            f"| {p['intelligence_index']} | ${p['usd_per_task']:.2f} | yes |")
            else:
                best = r["best_available"]
                pick_desc = (f"none clears — best available: {best['label']} "
                             f"(index {best['intelligence_index']})" if best
                             else "no dispatchable entries at all")
                out.append(f"| {r['role']} | {r['floor']} | {sel} | {pick_desc} "
                            "| — | — | no |")
        out.append("")

    out.append(_footer(card))
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------
# Rendering — compare.


def render_compare_markdown(card):
    out = [f"# Benchmark vs. measured — {card['source']}\n"]
    out.append(
        "Measured outcomes win: this repo's own execution ledger is the tie-breaker over the "
        "general-capability benchmark composite.\n"
    )
    out.append(card["ledger_scope_note"] + "\n")
    out.append(
        f"Ledger sample floor: {card['min_sample']} finished task(s) per tier; "
        f"marginal-gain threshold for 'supported': >{card['marginal_gain_threshold'] * 100:.0f} "
        "point(s) (both editorial — see the module docstring).\n"
    )
    out.append(card["evidence_howto_note"] + "\n")
    for r in card["rows"]:
        cs = "cost-sensitive" if r["cost_sensitive"] else "cost-insensitive"
        out.append(f"## {r['role']} (floor {r['floor']}, {cs})\n")
        if r["picked"]:
            p = r["picked"]
            out.append(
                f"benchmark recommends: {p['label']} (index {p['intelligence_index']}, "
                f"${p['usd_per_task']:.2f} benchmark-workload cost, est.)\n"
            )
        out.append(f"**{r['verdict']}** — {r['explanation']}\n")
        if r.get("coverage_note"):
            out.append(f"{r['coverage_note']}\n")

    if card["scan_notes"]:
        out.append("Notes:")
        for n in card["scan_notes"]:
            out.append(f"- {n}")
        out.append("")

    out.append(_footer(card))
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------
# demo — synthetic, self-contained fixtures (in-memory benchmarks + pricing bundle; one
# throwaway temp kit dir for `compare`'s ledger reuse). Deliberately reuses the SAME real
# join/recommend/compare functions the CLI uses — never a divergent demo-only implementation.

DEMO_BENCHMARKS = {
    "source": "Synthetic (demo)",
    "index_name": "Demo Intelligence Index",
    "cached_date": "2026-01-01",
    "transcribed_from": (
        "synthetic demo fixture — not real benchmark data, generated fresh in a temp dir for "
        "`demo` and discarded on exit"
    ),
    "caveats": [
        "Demo data only — synthetic, never real benchmark data.",
        CAPABILITY_CAVEAT,
    ],
    "entries": [
        {"label": "Demo Frontier (max)", "model": "demo-frontier-9-0", "effort": "max",
         "provider": "anthropic", "intelligence_index": 90, "usd_per_task": 5.0},
        {"label": "Demo Opus (max)", "model": "demo-opus-4-8", "effort": "max",
         "provider": "anthropic", "intelligence_index": 70, "usd_per_task": 1.0},
        {"label": "Demo Opus (medium)", "model": "demo-opus-4-8", "effort": "medium",
         "provider": "anthropic", "intelligence_index": 55, "usd_per_task": 0.30},
        {"label": "Demo Sonnet (max)", "model": "demo-sonnet-5", "effort": "max",
         "provider": "anthropic", "intelligence_index": 50, "usd_per_task": 0.40},
        {"label": "Demo Haiku (default)", "model": "demo-haiku-1", "effort": "default",
         "provider": "anthropic", "intelligence_index": 32, "usd_per_task": 0.05},
        {"label": "Demo Other (max)", "model": "demo-other-1", "effort": "max",
         "provider": "otherco", "intelligence_index": 60, "usd_per_task": 0.80},
    ],
}

# Claude native ids (dash form). Codex only lists the frontier model. Copilot lists the opus
# model in DOT form — the exact dash/dot join hazard the module docstring describes.
DEMO_CLAUDE_PRICING = {"models": {
    "demo-frontier-9-0": {"tier": "frontier", "context_window": 1_000_000},
    "demo-opus-4-8": {"tier": "opus", "context_window": 1_000_000},
    "demo-sonnet-5": {"tier": "sonnet", "context_window": 1_000_000},
    "demo-haiku-1": {"tier": "haiku", "context_window": 200_000},
}}
DEMO_CODEX_PRICING = {"models": {
    "demo-frontier-9-0": {"tier": "frontier"},
}}
DEMO_COPILOT_PRICING = {"models": {
    "demo-opus-4.8": {},
}}

DEMO_KIT_TASKS_MD = """# TASKS — bench-routing-demo (synthetic)

## Phase 1 — demo

### T1 — sonnet task one
- status: done
- model: sonnet

### T2 — sonnet task two
- status: done
- model: sonnet

### T3 — sonnet task three
- status: done
- model: sonnet

### T4 — opus task one
- status: done
- model: opus

### T5 — opus task two
- status: done
- model: opus

### T6 — opus task three
- status: done
- model: opus
"""

DEMO_KIT_NOTES_MD = """# NOTES — bench-routing-demo (synthetic)

## Outcome ledger
outcome: T1 model=sonnet result=pass review=clean
outcome: T2 model=sonnet result=pass review=clean
outcome: T3 model=sonnet result=pass review=clean
outcome: T4 model=opus result=pass review=clean
outcome: T5 model=opus result=pass review=clean
outcome: T6 model=opus result=pass review=clean
"""

DEMO_HEADER = (
    "# Bench routing — demo\n\n"
    "Synthetic smoke across rank, roles (all three harnesses, including the dash/dot id join), "
    "and compare (including a `not_supported` verdict and a cheapest-tier no-comparison "
    "branch). Every fixture below — benchmarks, all three pricing files, and the kit ledger — "
    "is generated fresh in memory or a throwaway temp dir and discarded on exit. No real "
    "`data/benchmarks.aa.json`, `data/pricing*.json`, kit, or `~/` is read or written."
)


def build_demo_cards():
    pricing_bundle = {
        "claude": DEMO_CLAUDE_PRICING, "codex": DEMO_CODEX_PRICING, "copilot": DEMO_COPILOT_PRICING,
    }
    floors = {}
    rank_card = build_rank_card(DEMO_BENCHMARKS)
    roles_card = build_roles_card(DEMO_BENCHMARKS, pricing_bundle, list(HARNESSES), floors)
    with tempfile.TemporaryDirectory() as tmp_name:
        kits_dir = Path(tmp_name) / "kits"
        kit_dir = kits_dir / "bench-routing-demo"
        kit_dir.mkdir(parents=True)
        (kit_dir / "TASKS.md").write_text(DEMO_KIT_TASKS_MD)
        (kit_dir / "NOTES.md").write_text(DEMO_KIT_NOTES_MD)
        compare_card = build_compare_card(DEMO_BENCHMARKS, pricing_bundle, kits_dir, floors)
    return rank_card, roles_card, compare_card


def cmd_demo(args):
    rank_card, roles_card, compare_card = build_demo_cards()
    if args.json:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "demo": True,
            "rank": rank_card,
            "roles": roles_card,
            "compare": compare_card,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(DEMO_HEADER)
        print("\n" + render_rank_markdown(rank_card))
        print("\n" + render_roles_markdown(roles_card))
        print("\n" + render_compare_markdown(compare_card))
    return 0


# ---------------------------------------------------------------------------------------------
# CLI.


def cmd_rank(args):
    try:
        benchmarks = load_benchmarks(args.benchmarks)
    except (OSError, json.JSONDecodeError) as e:
        print(f"could not load --benchmarks {args.benchmarks!r}: {e}", file=sys.stderr)
        return 2
    card = build_rank_card(benchmarks, provider=args.provider, model=args.model, top=args.top)
    print(json.dumps(card, indent=2) if args.json else render_rank_markdown(card))
    return 0


def cmd_roles(args):
    try:
        benchmarks = load_benchmarks(args.benchmarks)
        pricing_bundle = load_pricing_bundle(args.pricing_dir)
    except (OSError, json.JSONDecodeError) as e:
        print(f"could not load benchmark/pricing data: {e}", file=sys.stderr)
        return 2
    try:
        floors = parse_floor_overrides(args.floor)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    harnesses = list(HARNESSES) if args.harness == "all" else [args.harness]
    card = build_roles_card(benchmarks, pricing_bundle, harnesses, floors)
    print(json.dumps(card, indent=2) if args.json else render_roles_markdown(card))
    return 0


def cmd_compare(args):
    try:
        benchmarks = load_benchmarks(args.benchmarks)
        pricing_bundle = load_pricing_bundle(args.pricing_dir)
    except (OSError, json.JSONDecodeError) as e:
        print(f"could not load benchmark/pricing data: {e}", file=sys.stderr)
        return 2
    try:
        floors = parse_floor_overrides(args.floor)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    card = build_compare_card(benchmarks, pricing_bundle, Path(args.kits_dir), floors)
    print(json.dumps(card, indent=2) if args.json else render_compare_markdown(card))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(
        prog="bench_routing.py",
        description="Rank benchmark entries, recommend per-role routing per harness, and check "
                     "it against this repo's own measured outcomes.",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    rank = sub.add_parser("rank", help="Ranked tables: by index, by value, capability frontier")
    rank.add_argument("--benchmarks", default=str(DEFAULT_BENCHMARKS_PATH))
    rank.add_argument("--provider", default=None)
    rank.add_argument("--model", default=None)
    rank.add_argument("--top", type=int, default=None)
    rank.add_argument("--json", action="store_true")

    roles = sub.add_parser(
        "roles", help="Per-harness role assignments from what each harness can actually dispatch"
    )
    roles.add_argument("--benchmarks", default=str(DEFAULT_BENCHMARKS_PATH))
    roles.add_argument("--pricing-dir", default=str(DEFAULT_PRICING_DIR))
    roles.add_argument("--harness", choices=["claude", "codex", "copilot", "all"], default="all")
    roles.add_argument("--floor", action="append", default=[], metavar="role=N",
                        help="override a ROLE_POLICY floor (repeatable)")
    roles.add_argument("--json", action="store_true")

    compare = sub.add_parser(
        "compare", help="Join the benchmark prior against this repo's measured outcomes"
    )
    compare.add_argument("--benchmarks", default=str(DEFAULT_BENCHMARKS_PATH))
    compare.add_argument("--pricing-dir", default=str(DEFAULT_PRICING_DIR))
    compare.add_argument("--kits-dir", default=str(rs.DEFAULT_KITS_DIR))
    compare.add_argument("--floor", action="append", default=[], metavar="role=N",
                          help="override a ROLE_POLICY floor (repeatable)")
    compare.add_argument("--json", action="store_true")

    demo = sub.add_parser("demo", help="Synthetic smoke over a temp fixture — no real data touched")
    demo.add_argument("--json", action="store_true")

    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.command == "rank":
        return cmd_rank(args)
    if args.command == "roles":
        return cmd_roles(args)
    if args.command == "compare":
        return cmd_compare(args)
    if args.command == "demo":
        return cmd_demo(args)
    ap.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
