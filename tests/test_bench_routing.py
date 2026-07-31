"""Stdlib unittest regression suite for bin/bench_routing.py.

SAFETY CONTRACT (mirrors tests/test_context_weight.py / tests/test_routing_scorecard.py): no
test here writes anywhere except a fresh ``tempfile.TemporaryDirectory()``, never touches
``Path.home()``, and never invokes a real CLI other than this repo's own
``bin/bench_routing.py`` (in-process, via ``br.main``). Every benchmark/pricing/kit fixture used
by a unit test is synthetic — the one exception is ``ReadOnlyProofTests``, which points the real
CLI at this repo's REAL ``data/benchmarks.aa.json`` / ``data/pricing*.json`` / ``.claude/kits``
specifically to prove nothing under them is ever written.

bin/ is not a package; bench_routing.py is loaded via importlib by absolute path computed from
this file's own location (BIN_DIR), the ``_load`` idiom from tests/test_context_weight.py.
"""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
REPO_ROOT = BIN_DIR.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


br = _load("bench_routing")


def _run_main(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = br.main(argv)
    return rc, buf.getvalue()


# ---------------------------------------------------------------------------------------------
# Shared synthetic fixtures. Never real data/benchmarks.aa.json or data/pricing*.json.

BENCH_FIXTURE = {
    "source": "TestSource",
    "index_name": "Test Index",
    "cached_date": "2026-01-01",
    "transcribed_from": "synthetic test fixture — not real benchmark data",
    "caveats": ["Test caveat one.", "Test caveat two."],
    "entries": [
        {"label": "A-high", "model": "model-a", "effort": "max", "provider": "acme",
         "intelligence_index": 80, "usd_per_task": 2.0},
        {"label": "A-cheap", "model": "model-a", "effort": "low", "provider": "acme",
         "intelligence_index": 40, "usd_per_task": 0.1},
        {"label": "B-mid", "model": "model-b", "effort": "default", "provider": "acme",
         "intelligence_index": 60, "usd_per_task": 0.5},
        # dash-form id — pricing.copilot.json-style fixture below carries the DOT form of the
        # same model, exercising the exact join hazard the module docstring describes.
        {"label": "C-dot", "model": "model-c-4-8", "effort": "max", "provider": "acme",
         "intelligence_index": 55, "usd_per_task": 0.4},
        {"label": "Zero-cost", "model": "model-z", "effort": "max", "provider": "acme",
         "intelligence_index": 70, "usd_per_task": 0},
        {"label": "Unavailable", "model": "ghost-model", "effort": "max", "provider": "other",
         "intelligence_index": 90, "usd_per_task": 1.0},
    ],
}

CLAUDE_PRICING_FIXTURE = {"models": {
    "model-a": {"tier": "opus", "context_window": 1_000_000},
    "model-b": {"tier": "sonnet", "context_window": 1_000_000},
    "model-c-4-8": {"tier": "opus", "context_window": 1_000_000},
    "model-z": {"tier": "haiku", "context_window": 200_000},
    # ghost-model deliberately absent — unavailable everywhere.
}}
CODEX_PRICING_FIXTURE = {"models": {
    "model-a": {"tier": "mid"},
    "codex-only-nonroute": {"tier": "non-routing"},  # must be excluded from availability
}}
COPILOT_PRICING_FIXTURE = {"models": {
    "model-c-4.8": {},   # DOT form of model-c-4-8 — the join test target
    "model-b": {},
}}

PRICING_BUNDLE_FIXTURE = {
    "claude": CLAUDE_PRICING_FIXTURE, "codex": CODEX_PRICING_FIXTURE, "copilot": COPILOT_PRICING_FIXTURE,
}


def _write_pricing_dir(tmp_path):
    d = Path(tmp_path) / "pricing"
    d.mkdir(parents=True, exist_ok=True)
    (d / "pricing.json").write_text(json.dumps(CLAUDE_PRICING_FIXTURE))
    (d / "pricing.codex.json").write_text(json.dumps(CODEX_PRICING_FIXTURE))
    (d / "pricing.copilot.json").write_text(json.dumps(COPILOT_PRICING_FIXTURE))
    return d


def _write_benchmarks(tmp_path, data=BENCH_FIXTURE):
    p = Path(tmp_path) / "benchmarks.json"
    p.write_text(json.dumps(data))
    return p


def _write_kit(kits_root, slug, tasks_md, notes_md):
    kit_dir = Path(kits_root) / slug
    kit_dir.mkdir(parents=True)
    (kit_dir / "TASKS.md").write_text(tasks_md)
    (kit_dir / "NOTES.md").write_text(notes_md)
    return kit_dir


def _tasks_notes(prefix, model_tier, n, result="pass"):
    """Build a tiny synthetic TASKS.md/NOTES.md pair: ``n`` tasks, all pinned to
    ``model_tier`` and all recording ``result`` (default 'pass')."""
    ids = [f"{prefix}{i}" for i in range(1, n + 1)]
    tasks = [f"# TASKS — {prefix}-kit (synthetic)\n\n## Phase 1 — only phase\n"]
    for tid in ids:
        tasks.append(f"\n### {tid} — synthetic task\n- status: done\n- model: {model_tier}\n")
    notes = [f"# NOTES — {prefix}-kit (synthetic)\n\n## Outcome ledger\n"]
    for tid in ids:
        notes.append(f"outcome: {tid} model={model_tier} result={result} review=clean\n")
    return "".join(tasks), "".join(notes)


# ---- normalize_id / availability (dash/dot join) --------------------------------------------


class NormalizeIdTests(unittest.TestCase):
    def test_dash_and_dot_normalize_to_same_shape(self):
        self.assertEqual(br.normalize_id("claude-opus-4-8"), br.normalize_id("claude-opus-4.8"))
        self.assertEqual(br.normalize_id("claude-opus-4-8"), "claude-opus-4-8")

    def test_none_and_empty(self):
        self.assertEqual(br.normalize_id(None), "")
        self.assertEqual(br.normalize_id(""), "")


class AvailabilityJoinTests(unittest.TestCase):
    def test_claude_availability_excludes_ghost_model(self):
        ids, _raw = br.available_ids_for_harness(CLAUDE_PRICING_FIXTURE)
        avail = br.dispatchable_entries(BENCH_FIXTURE["entries"], ids)
        labels = {e["label"] for e in avail}
        self.assertEqual(labels, {"A-high", "A-cheap", "B-mid", "C-dot", "Zero-cost"})
        unavail = br.unavailable_entries(BENCH_FIXTURE["entries"], ids)
        self.assertEqual({e["label"] for e in unavail}, {"Unavailable"})

    def test_codex_availability_excludes_non_routing_tier(self):
        ids, _raw = br.available_ids_for_harness(CODEX_PRICING_FIXTURE)
        # codex-only-nonroute carries tier "non-routing" and must never appear as available.
        self.assertNotIn(br.normalize_id("codex-only-nonroute"), ids)
        avail = br.dispatchable_entries(BENCH_FIXTURE["entries"], ids)
        self.assertEqual({e["label"] for e in avail}, {"A-high", "A-cheap"})

    def test_copilot_availability_joins_dash_benchmark_id_to_dot_pricing_key(self):
        # This is the exact hazard the module docstring names: benchmark model is
        # "model-c-4-8" (dash), pricing.copilot.json-style fixture carries "model-c-4.8" (dot).
        ids, raw = br.available_ids_for_harness(COPILOT_PRICING_FIXTURE)
        avail = br.dispatchable_entries(BENCH_FIXTURE["entries"], ids)
        self.assertEqual({e["label"] for e in avail}, {"C-dot", "B-mid"})
        self.assertEqual(raw[br.normalize_id("model-c-4-8")], "model-c-4.8")


# ---- rank_by_value / pareto_frontier / coverage_gaps -----------------------------------------


class ValueRankingTests(unittest.TestCase):
    def test_value_ranking_order(self):
        ranked, excluded = br.rank_by_value(BENCH_FIXTURE["entries"])
        self.assertEqual(
            [e["label"] for e in ranked],
            ["A-cheap", "C-dot", "B-mid", "Unavailable", "A-high"],
        )
        self.assertEqual([e["label"] for e in excluded], ["Zero-cost"])

    def test_value_of_none_for_zero_cost(self):
        zero = next(e for e in BENCH_FIXTURE["entries"] if e["label"] == "Zero-cost")
        self.assertIsNone(br.value_of(zero))


class FrontierTests(unittest.TestCase):
    def test_frontier_selection_is_a_skyline(self):
        frontier = br.pareto_frontier(BENCH_FIXTURE["entries"])
        # Unavailable(90,$1.0) dominates A-high(80,$2.0) — A-high must NOT appear.
        self.assertEqual(
            [e["label"] for e in frontier],
            ["Unavailable", "B-mid", "C-dot", "A-cheap"],
        )
        # Frontier entries are listed index-descending; the skyline property means cost must
        # be STRICTLY decreasing across the list too (each kept entry is cheaper than every
        # higher-or-equal-index entry already kept) — proves this isn't just index-sorted
        # output with no cost filtering at all.
        costs = [e["usd_per_task"] for e in frontier]
        self.assertEqual(costs, sorted(costs, reverse=True))
        self.assertEqual(len(costs), len(set(costs)))

    def test_frontier_excludes_zero_cost_entries(self):
        frontier = br.pareto_frontier(BENCH_FIXTURE["entries"])
        self.assertNotIn("Zero-cost", [e["label"] for e in frontier])


class CoverageGapTests(unittest.TestCase):
    def test_detects_single_effort_model_against_multi_effort_ceiling(self):
        entries = [
            {"model": "m1", "effort": "max"},
            {"model": "m1", "effort": "medium"},
            {"model": "m1", "effort": "low"},
            {"model": "m2", "effort": "max"},
        ]
        cov = br.effort_coverage(entries)
        self.assertEqual(cov, {"m1": ["max", "medium", "low"], "m2": ["max"]})
        gaps = br.coverage_gaps(cov)
        self.assertEqual(gaps, {"ceiling": 3, "gaps": [{"model": "m2", "efforts": 1}]})

    def test_no_gap_when_all_models_share_the_ceiling(self):
        entries = [{"model": "m1", "effort": "max"}, {"model": "m2", "effort": "max"}]
        gaps = br.coverage_gaps(br.effort_coverage(entries))
        self.assertEqual(gaps, {"ceiling": 1, "gaps": []})

    def test_empty_map(self):
        self.assertEqual(br.coverage_gaps({}), {"ceiling": 0, "gaps": []})

    def test_real_dataset_flags_sonnet_5_single_effort(self):
        # Not hardcoding the example's numbers — reads the real repo file and asserts the
        # STRUCTURAL fact the honesty requirement names: Sonnet 5 has fewer effort points than
        # the dataset's ceiling.
        benchmarks = br.load_benchmarks(br.DEFAULT_BENCHMARKS_PATH)
        gaps = br.coverage_gaps(br.effort_coverage(benchmarks["entries"]))
        gap_models = {g["model"] for g in gaps["gaps"]}
        self.assertIn("claude-sonnet-5", gap_models)
        sonnet_gap = next(g for g in gaps["gaps"] if g["model"] == "claude-sonnet-5")
        self.assertEqual(sonnet_gap["efforts"], 1)
        self.assertGreater(gaps["ceiling"], 1)


# ---- recommend_role: cost-sensitive vs cost-insensitive divergence ---------------------------


class RecommendRoleTests(unittest.TestCase):
    # Cheap is the cheapest entry clearing the floor; BestValue costs MORE than Cheap but has a
    # much higher index/usd ratio; Expensive clears the floor but is neither cheapest nor best
    # value. This is the minimal fixture where cost-sensitive and cost-insensitive genuinely
    # disagree (proves the two policies are not accidentally equivalent).
    POOL = [
        {"label": "Cheap", "model": "cheap", "effort": "m", "provider": "p",
         "intelligence_index": 50, "usd_per_task": 0.10},        # value 500
        {"label": "BestValue", "model": "bv", "effort": "m", "provider": "p",
         "intelligence_index": 95, "usd_per_task": 0.15},        # value 633.33
        {"label": "Expensive", "model": "exp", "effort": "m", "provider": "p",
         "intelligence_index": 99, "usd_per_task": 5.0},         # value 19.8
    ]

    def test_cost_sensitive_picks_best_value(self):
        rec = br.recommend_role(self.POOL, "role", 50, cost_sensitive=True)
        self.assertEqual(rec["picked"]["label"], "BestValue")
        self.assertTrue(rec["clears_floor"])

    def test_cost_insensitive_picks_cheapest(self):
        rec = br.recommend_role(self.POOL, "role", 50, cost_sensitive=False)
        self.assertEqual(rec["picked"]["label"], "Cheap")
        self.assertTrue(rec["clears_floor"])

    def test_no_entry_clears_floor_reports_best_available(self):
        rec = br.recommend_role(self.POOL, "role", 999, cost_sensitive=True)
        self.assertIsNone(rec["picked"])
        self.assertFalse(rec["clears_floor"])
        self.assertEqual(rec["best_available"]["label"], "Expensive")  # highest index (99)

    def test_empty_pool_reports_no_best_available(self):
        rec = br.recommend_role([], "role", 10, cost_sensitive=True)
        self.assertIsNone(rec["picked"])
        self.assertIsNone(rec["best_available"])


# ---- roles card: dispatchable/total, unavailable reporting -----------------------------------


class RolesCardTests(unittest.TestCase):
    def test_dispatchable_and_unavailable_counts_per_harness(self):
        card = br.build_roles_card(
            BENCH_FIXTURE, PRICING_BUNDLE_FIXTURE, list(br.HARNESSES), floors={}
        )
        by_harness = {sec["harness"]: sec for sec in card["sections"]}
        self.assertEqual(by_harness["claude"]["dispatchable"], 5)
        self.assertEqual(by_harness["claude"]["total"], 6)
        self.assertEqual(by_harness["claude"]["unavailable"], ["Unavailable"])

        self.assertEqual(by_harness["codex"]["dispatchable"], 2)
        self.assertEqual(sorted(by_harness["codex"]["unavailable"]),
                          sorted(["B-mid", "C-dot", "Zero-cost", "Unavailable"]))

        self.assertEqual(by_harness["copilot"]["dispatchable"], 2)

    def test_role_rows_cover_every_role_policy_entry(self):
        card = br.build_roles_card(BENCH_FIXTURE, PRICING_BUNDLE_FIXTURE, ["claude"], floors={})
        section = card["sections"][0]
        self.assertEqual([r["role"] for r in section["roles"]], list(br.ROLE_NAMES))


# ---- --floor override --------------------------------------------------------------------

class FloorOverrideTests(unittest.TestCase):
    def test_parse_floor_overrides_valid(self):
        floors = br.parse_floor_overrides(["implementer=90", "reviewer=10"])
        self.assertEqual(floors, {"implementer": 90, "reviewer": 10})

    def test_parse_floor_overrides_rejects_unknown_role(self):
        with self.assertRaises(ValueError):
            br.parse_floor_overrides(["bogus=5"])

    def test_parse_floor_overrides_rejects_bad_shape(self):
        with self.assertRaises(ValueError):
            br.parse_floor_overrides(["implementer"])
        with self.assertRaises(ValueError):
            br.parse_floor_overrides(["implementer=notanumber"])

    def test_cli_floor_override_changes_recommendation(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench_path = _write_benchmarks(tmp)
            pricing_dir = _write_pricing_dir(tmp)
            rc, out = _run_main([
                "roles", "--benchmarks", str(bench_path), "--pricing-dir", str(pricing_dir),
                "--harness", "claude", "--floor", "mechanical sweep=999", "--json",
            ])
            self.assertEqual(rc, 0)
            data = json.loads(out)
            section = data["sections"][0]
            sweep = next(r for r in section["roles"] if r["role"] == "mechanical sweep")
            self.assertIsNone(sweep["picked"])
            self.assertFalse(sweep["clears_floor"])
            self.assertEqual(data["floors"]["mechanical sweep"], 999)

    def test_cli_unknown_floor_role_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench_path = _write_benchmarks(tmp)
            pricing_dir = _write_pricing_dir(tmp)
            rc, _out = _run_main([
                "roles", "--benchmarks", str(bench_path), "--pricing-dir", str(pricing_dir),
                "--floor", "bogus=5",
            ])
            self.assertNotEqual(rc, 0)


# ---- compare: the point of the tool -----------------------------------------------------------

COMPARE_BENCH = {
    "source": "TestSource", "index_name": "Test Index", "cached_date": "2026-01-01",
    "transcribed_from": "synthetic compare fixture",
    "caveats": [],
    "entries": [
        {"label": "Sonnet-x", "model": "sonnet-x", "effort": "max", "provider": "acme",
         "intelligence_index": 50, "usd_per_task": 0.4},           # value 125
        {"label": "Opus-x (medium)", "model": "opus-x", "effort": "medium", "provider": "acme",
         "intelligence_index": 56, "usd_per_task": 0.3},           # value 186.7 — best value
        {"label": "Opus-x (max)", "model": "opus-x", "effort": "max", "provider": "acme",
         "intelligence_index": 70, "usd_per_task": 2.0},           # value 35
        {"label": "Haiku-x", "model": "haiku-x", "effort": "default", "provider": "acme",
         "intelligence_index": 30, "usd_per_task": 0.05},          # value 600 — best of all
    ],
}
COMPARE_PRICING_BUNDLE = {
    "claude": {"models": {
        "sonnet-x": {"tier": "sonnet"}, "opus-x": {"tier": "opus"}, "haiku-x": {"tier": "haiku"},
    }},
    "codex": {"models": {}}, "copilot": {"models": {}},
}


class CompareTests(unittest.TestCase):
    def test_flags_a_contradiction_not_supported(self):
        # implementer (floor 49, cost-sensitive) picks Opus-x medium (best value) -> tier opus,
        # current tier sonnet. Ledger: both tiers 3/3 pass (100%) -> zero marginal gain -> the
        # benchmark's implied upgrade is NOT supported, even though nothing regressed.
        with tempfile.TemporaryDirectory() as tmp:
            kits_dir = Path(tmp) / "kits"
            s_tasks, s_notes = _tasks_notes("S", "sonnet", 3, "pass")
            o_tasks, o_notes = _tasks_notes("O", "opus", 3, "pass")
            _write_kit(kits_dir, "sonnet-kit", s_tasks, s_notes)
            _write_kit(kits_dir, "opus-kit", o_tasks, o_notes)

            card = br.build_compare_card(COMPARE_BENCH, COMPARE_PRICING_BUNDLE, kits_dir, {})
            row = next(r for r in card["rows"] if r["role"] == "implementer")
            self.assertEqual(row["picked"]["label"], "Opus-x (medium)")
            self.assertEqual(row["recommended_tier"], "opus")
            self.assertEqual(row["current_tier"], "sonnet")
            self.assertEqual(row["verdict"], "not_supported")
            self.assertAlmostEqual(row["marginal_gain"], 0.0)
            self.assertIn("measured outcomes win", row["explanation"])
            # Opus-x has 2 measured effort points, Sonnet-x has 1 — the coverage-gap note must
            # be present and must name both models.
            self.assertIn("coverage_note", row)
            self.assertIn("sonnet-x", row["coverage_note"])
            self.assertIn("opus-x", row["coverage_note"])

    def test_supported_when_measured_gain_is_large(self):
        with tempfile.TemporaryDirectory() as tmp:
            kits_dir = Path(tmp) / "kits"
            s_tasks, s_notes = _tasks_notes("S", "sonnet", 3, "blocked")  # 0/3 first-try
            o_tasks, o_notes = _tasks_notes("O", "opus", 3, "pass")       # 3/3 first-try
            _write_kit(kits_dir, "sonnet-kit", s_tasks, s_notes)
            _write_kit(kits_dir, "opus-kit", o_tasks, o_notes)

            card = br.build_compare_card(COMPARE_BENCH, COMPARE_PRICING_BUNDLE, kits_dir, {})
            row = next(r for r in card["rows"] if r["role"] == "implementer")
            self.assertEqual(row["verdict"], "supported")
            self.assertGreater(row["marginal_gain"], br.MARGINAL_GAIN_THRESHOLD)

    def test_insufficient_sample_when_below_min(self):
        with tempfile.TemporaryDirectory() as tmp:
            kits_dir = Path(tmp) / "kits"
            # Only 2 sonnet tasks — below routing_scorecard.LIVE_MIN_SAMPLE (3).
            s_tasks, s_notes = _tasks_notes("S", "sonnet", 2, "pass")
            o_tasks, o_notes = _tasks_notes("O", "opus", 3, "pass")
            _write_kit(kits_dir, "sonnet-kit", s_tasks, s_notes)
            _write_kit(kits_dir, "opus-kit", o_tasks, o_notes)

            card = br.build_compare_card(COMPARE_BENCH, COMPARE_PRICING_BUNDLE, kits_dir, {})
            row = next(r for r in card["rows"] if r["role"] == "implementer")
            self.assertEqual(row["verdict"], "insufficient_sample")
            self.assertNotIn("marginal_gain", row)

    def test_cheapest_tier_needs_no_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            kits_dir = Path(tmp) / "kits"
            kits_dir.mkdir(parents=True)
            # mechanical sweep (floor 30, cost-sensitive) picks Haiku-x (best value, 600) —
            # haiku is the cheapest repo tier, so there is nothing cheaper to compare against.
            card = br.build_compare_card(COMPARE_BENCH, COMPARE_PRICING_BUNDLE, kits_dir, {})
            row = next(r for r in card["rows"] if r["role"] == "mechanical sweep")
            self.assertEqual(row["picked"]["label"], "Haiku-x")
            self.assertEqual(row["verdict"], "cheapest_tier")
            self.assertIsNone(row["current_tier"])

    def test_no_recommendation_when_floor_unreachable(self):
        with tempfile.TemporaryDirectory() as tmp:
            kits_dir = Path(tmp) / "kits"
            kits_dir.mkdir(parents=True)
            card = br.build_compare_card(
                COMPARE_BENCH, COMPARE_PRICING_BUNDLE, kits_dir,
                floors={"architect/planner": 999},
            )
            row = next(r for r in card["rows"] if r["role"] == "architect/planner")
            self.assertEqual(row["verdict"], "no_recommendation")
            self.assertIsNone(row["picked"])

    def test_real_ledger_tier_attribution_holds(self):
        """Tier attribution stays coherent against the repo's REAL kit ledger (read-only).

        This test used to pin literal counts (haiku 20/20, sonnet 83/86, opus 18/18). Those
        are derived from ``.claude/kits/``, a directory that GROWS every time any kit
        executes — so the assertion failed on the very next kit run and was doomed the moment
        it was written. It went red mid-run for a correct reason and stayed red, degrading
        "suite green" into "green except the one I know about", which is the state in which a
        real regression gets waved through.

        The intent was right: catch a change that silently breaks tier attribution. These
        invariants catch that and survive growth. Conservation is the load-bearing one —
        misattributed or dropped tasks change the sum even when every individual count still
        looks plausible.
        """
        records, notes = br.rs.scan_kits(br.rs.DEFAULT_KITS_DIR)
        history = br.rs.build_history(br.rs.DEFAULT_KITS_DIR, records, {}, None, notes)
        tiers = history["tiers"]

        self.assertEqual(set(tiers), set(br.rs.LIVE_TIER_ORDER))

        for name, t in tiers.items():
            self.assertGreaterEqual(t["with_outcome"], 0, name)
            self.assertGreaterEqual(t["with_outcome"], t["first_try"], name)
            self.assertGreaterEqual(t["first_try"], 0, name)

        # CONSERVATION: every task carrying an outcome lands in exactly one tier. Attribution
        # that drops or double-counts breaks this even when the per-tier numbers look sane.
        total_with_outcome = sum(t["with_outcome"] for t in tiers.values())
        ledger_outcomes = sum(len(r["outcomes"]) for r in records)
        self.assertEqual(total_with_outcome, ledger_outcomes)

        # The repo routes real work through these three; zero means attribution stopped
        # working, not that the ledger is empty. Floors, never equalities — they only grow.
        for name in ("haiku", "sonnet", "opus"):
            self.assertGreater(tiers[name]["with_outcome"], 0, name)
        self.assertGreater(tiers["sonnet"]["with_outcome"], tiers["opus"]["with_outcome"])


def _section(markdown, role):
    """Extract the ``## <role>`` block from a rendered compare card (up to the next ``## `` or
    end of string) — lets a test assert on ONE role's rendered text without the header/footer
    (which legitimately mention percentages/rates elsewhere on the page) polluting the check."""
    marker = f"## {role} ("
    start = markdown.index(marker)
    rest = markdown[start + len(marker):]
    nxt = rest.find("\n## ")
    return rest if nxt == -1 else rest[:nxt]


# Reuses COMPARE_BENCH/COMPARE_PRICING_BUNDLE — a fixture with an extra Frontier entry, for the
# coordinator's "sharpest case": a role (architect/planner) whose benchmark recommendation lands
# on a repo tier (frontier) that ALSO happens to have zero ledger tasks. The role-evidence gate
# must fire (no_role_evidence) regardless of sample size — this is a role-scoping bug, not a
# sample-size bug, and the two must not be conflated.
FRONTIER_BENCH = {
    "source": "TestSource", "index_name": "Test Index", "cached_date": "2026-01-01",
    "transcribed_from": "synthetic frontier-role fixture", "caveats": [],
    "entries": [
        {"label": "Frontier-x", "model": "frontier-x", "effort": "max", "provider": "acme",
         "intelligence_index": 95, "usd_per_task": 5.0},
        {"label": "Opus-x", "model": "opus-x", "effort": "max", "provider": "acme",
         "intelligence_index": 70, "usd_per_task": 1.0},
    ],
}
FRONTIER_PRICING_BUNDLE = {
    "claude": {"models": {"frontier-x": {"tier": "frontier"}, "opus-x": {"tier": "opus"}}},
    "codex": {"models": {}}, "copilot": {"models": {}},
}


class RoleEvidenceGateTests(unittest.TestCase):
    """The ledger records per-TASK outcomes (implementer work) — no `outcome:` line carries a
    role=, and the separate `agent:` ledger that DOES carry role= carries no result=. Only
    "implementer" may be judged against a measured first-try rate; every other non-cheapest-tier
    role must get `no_role_evidence` and must NEVER quote a first-try percentage borrowed from a
    different job function."""

    def test_non_implementer_role_gets_no_role_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            kits_dir = Path(tmp) / "kits"
            s_tasks, s_notes = _tasks_notes("S", "sonnet", 3, "pass")
            o_tasks, o_notes = _tasks_notes("O", "opus", 3, "pass")
            _write_kit(kits_dir, "sonnet-kit", s_tasks, s_notes)
            _write_kit(kits_dir, "opus-kit", o_tasks, o_notes)

            card = br.build_compare_card(COMPARE_BENCH, COMPARE_PRICING_BUNDLE, kits_dir, {})
            for role in ("architect/planner", "reviewer", "orchestrator", "verifier"):
                row = next(r for r in card["rows"] if r["role"] == role)
                self.assertEqual(row["verdict"], "no_role_evidence", role)
                self.assertNotIn("measured", row, role)
                self.assertNotIn("marginal_gain", row, role)

    def test_rendered_card_has_no_first_try_percentage_for_ungated_roles(self):
        # (b) — the whole defect was quoting a number that doesn't bear on the role. Assert the
        # RENDERED block for a no_role_evidence role carries no "%" at all.
        with tempfile.TemporaryDirectory() as tmp:
            kits_dir = Path(tmp) / "kits"
            s_tasks, s_notes = _tasks_notes("S", "sonnet", 3, "pass")
            o_tasks, o_notes = _tasks_notes("O", "opus", 3, "pass")
            _write_kit(kits_dir, "sonnet-kit", s_tasks, s_notes)
            _write_kit(kits_dir, "opus-kit", o_tasks, o_notes)

            card = br.build_compare_card(COMPARE_BENCH, COMPARE_PRICING_BUNDLE, kits_dir, {})
            markdown = br.render_compare_markdown(card)
            for role in ("architect/planner", "reviewer", "orchestrator", "verifier"):
                block = _section(markdown, role)
                self.assertNotIn("%", block, f"{role} section unexpectedly quoted a rate:\n{block}")
                self.assertIn("no_role_evidence", block)

    def test_implementer_still_produces_its_evidenced_verdict(self):
        # (c) — the one role the ledger actually evidences must be UNCHANGED by the fix.
        with tempfile.TemporaryDirectory() as tmp:
            kits_dir = Path(tmp) / "kits"
            s_tasks, s_notes = _tasks_notes("S", "sonnet", 3, "pass")
            o_tasks, o_notes = _tasks_notes("O", "opus", 3, "pass")
            _write_kit(kits_dir, "sonnet-kit", s_tasks, s_notes)
            _write_kit(kits_dir, "opus-kit", o_tasks, o_notes)

            card = br.build_compare_card(COMPARE_BENCH, COMPARE_PRICING_BUNDLE, kits_dir, {})
            row = next(r for r in card["rows"] if r["role"] == "implementer")
            self.assertEqual(row["verdict"], "not_supported")
            self.assertIn("measured", row)
            self.assertEqual(row["measured"]["recommended_tier"]["first_try_rate"], 1.0)
            self.assertEqual(row["measured"]["current_tier"]["first_try_rate"], 1.0)

            markdown = br.render_compare_markdown(card)
            block = _section(markdown, "implementer")
            self.assertIn("%", block)  # implementer IS allowed to quote its evidenced rate

    def test_sharpest_case_frontier_role_with_zero_ledger_tasks(self):
        # The coordinator's concrete case: architect/planner runs on Fable (frontier tier) in
        # this repo, which has 0 measured tasks. This must be no_role_evidence, NOT
        # insufficient_sample — the fix is a ROLE-scoping gate, not a sample-size guard, and an
        # empty kits dir (zero tasks on every tier) must not be confused for "not enough yet."
        with tempfile.TemporaryDirectory() as tmp:
            kits_dir = Path(tmp) / "kits"
            kits_dir.mkdir(parents=True)  # no kits at all — every tier has 0 with_outcome
            card = br.build_compare_card(
                FRONTIER_BENCH, FRONTIER_PRICING_BUNDLE, kits_dir,
                floors={"architect/planner": 90},  # only Frontier-x (95) clears
            )
            row = next(r for r in card["rows"] if r["role"] == "architect/planner")
            self.assertEqual(row["picked"]["label"], "Frontier-x")
            self.assertEqual(row["recommended_tier"], "frontier")
            self.assertEqual(row["verdict"], "no_role_evidence")
            self.assertNotIn("measured", row)
            markdown = br.render_compare_markdown(card)
            self.assertNotIn("%", _section(markdown, "architect/planner"))

    def test_card_header_states_ledger_scope_and_howto(self):
        with tempfile.TemporaryDirectory() as tmp:
            kits_dir = Path(tmp) / "kits"
            kits_dir.mkdir(parents=True)
            card = br.build_compare_card(COMPARE_BENCH, COMPARE_PRICING_BUNDLE, kits_dir, {})
            self.assertIn("per-task", card["ledger_scope_note"])
            self.assertIn("role=", card["evidence_howto_note"])
            markdown = br.render_compare_markdown(card)
            self.assertIn(card["ledger_scope_note"], markdown)
            self.assertIn(card["evidence_howto_note"], markdown)


# ---- demo -----------------------------------------------------------------------------------

class DemoTests(unittest.TestCase):
    def test_demo_exits_zero_and_prints_all_three_cards(self):
        rc, out = _run_main(["demo"])
        self.assertEqual(rc, 0)
        self.assertIn("Bench routing — demo", out)
        self.assertIn("Benchmark ranking", out)
        self.assertIn("Role routing", out)
        self.assertIn("Benchmark vs. measured", out)
        self.assertIn("not_supported", out)
        self.assertIn("cheapest_tier", out)

    def test_demo_json_has_all_three_cards(self):
        rc, out = _run_main(["demo", "--json"])
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertTrue(data["demo"])
        for key in ("rank", "roles", "compare"):
            self.assertIn(key, data)
        self.assertEqual(data["rank"]["schema_version"], br.SCHEMA_VERSION)


# ---- CLI end-to-end ---------------------------------------------------------------------------

class CliEndToEndTests(unittest.TestCase):
    def test_rank_json_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench_path = _write_benchmarks(tmp)
            rc, out = _run_main(["rank", "--benchmarks", str(bench_path), "--json", "--top", "3"])
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertEqual(data["schema_version"], br.SCHEMA_VERSION)
            self.assertLessEqual(len(data["by_index"]), 3)
            self.assertLessEqual(len(data["by_value"]), 3)

    def test_rank_provider_and_model_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench_path = _write_benchmarks(tmp)
            rc, out = _run_main([
                "rank", "--benchmarks", str(bench_path), "--provider", "other", "--json",
            ])
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertEqual([e["label"] for e in data["by_index"]], ["Unavailable"])

    def test_roles_json_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench_path = _write_benchmarks(tmp)
            pricing_dir = _write_pricing_dir(tmp)
            rc, out = _run_main([
                "roles", "--benchmarks", str(bench_path), "--pricing-dir", str(pricing_dir),
                "--harness", "all", "--json",
            ])
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertEqual(len(data["sections"]), 3)

    def test_compare_json_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench_path = _write_benchmarks(tmp, COMPARE_BENCH)
            pricing_dir = Path(tmp) / "pricing"
            pricing_dir.mkdir()
            (pricing_dir / "pricing.json").write_text(json.dumps(COMPARE_PRICING_BUNDLE["claude"]))
            (pricing_dir / "pricing.codex.json").write_text(json.dumps({"models": {}}))
            (pricing_dir / "pricing.copilot.json").write_text(json.dumps({"models": {}}))
            kits_dir = Path(tmp) / "kits"
            s_tasks, s_notes = _tasks_notes("S", "sonnet", 3, "pass")
            o_tasks, o_notes = _tasks_notes("O", "opus", 3, "pass")
            _write_kit(kits_dir, "sonnet-kit", s_tasks, s_notes)
            _write_kit(kits_dir, "opus-kit", o_tasks, o_notes)

            rc, out = _run_main([
                "compare", "--benchmarks", str(bench_path), "--pricing-dir", str(pricing_dir),
                "--kits-dir", str(kits_dir), "--json",
            ])
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertEqual(len(data["rows"]), len(br.ROLE_POLICY))

    def test_rank_markdown_mentions_honesty_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench_path = _write_benchmarks(tmp)
            rc, out = _run_main(["rank", "--benchmarks", str(bench_path)])
            self.assertEqual(rc, 0)
            self.assertIn("never a price", out)
            self.assertIn("never this repo's pricing", out)
            self.assertIn("Test caveat one.", out)


# ---- read-only proof --------------------------------------------------------------------------


def _snapshot(paths):
    snap = {}
    for root in paths:
        root = Path(root)
        if root.is_file():
            st = root.stat()
            snap[str(root)] = (st.st_mtime_ns, st.st_size)
        elif root.is_dir():
            for p in root.rglob("*"):
                if p.is_file():
                    st = p.stat()
                    snap[str(p)] = (st.st_mtime_ns, st.st_size)
    return snap


class ReadOnlyProofTests(unittest.TestCase):
    def test_real_data_untouched_by_every_subcommand(self):
        watched = [
            REPO_ROOT / "data" / "benchmarks.aa.json",
            REPO_ROOT / "data" / "pricing.json",
            REPO_ROOT / "data" / "pricing.codex.json",
            REPO_ROOT / "data" / "pricing.copilot.json",
            br.rs.DEFAULT_KITS_DIR,
        ]
        before = _snapshot(watched)
        self.assertTrue(before, "expected at least one real file to snapshot")

        rc1, _ = _run_main(["rank", "--top", "3"])
        rc2, _ = _run_main(["roles", "--harness", "claude", "--json"])
        rc3, _ = _run_main(["compare", "--json"])
        rc4, _ = _run_main(["demo"])
        self.assertEqual((rc1, rc2, rc3, rc4), (0, 0, 0, 0))

        after = _snapshot(watched)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
