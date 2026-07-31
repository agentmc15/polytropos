"""Stdlib unittest regression suite for the cross-kit routing history (``--history``) in
bin/routing_scorecard.py (routing-history T2).

SAFETY CONTRACT (binds every test in this file): no test here ever reads the real Claude
Code project store or resolves the caller's real home directory via the stdlib home
helper -- this file never calls it, and it never spells out the real projects path as a
literal string. Every kit fixture (TASKS.md / NOTES.md) is written into a fresh
`tempfile.TemporaryDirectory()` and handed to the CLI or the pure functions via an
explicit `--kits-dir` / `--projects-dir` or an explicit path -- never a bare run against
real dirs. `test_history_pricing_free_without_sessions` additionally PROVES the
zero-`session:`-lines path never loads pricing: it stubs `rs.cr.load_pricing` to raise
and shows `--history` still succeeds (restoring the stub in `finally`). All ids/values in
every fixture are synthetic; the only model tokens anywhere in this file are the
sanctioned tier vocabulary (`haiku`/`sonnet`/`opus`/`frontier`) plus the `fable`
Agent-tool alias, EXCEPT the dollar-fixture transcript model ids, which are computed at
run time from `rs.cr.load_pricing()` + `rs._first_model_of_tier` -- never a spelled model
id.

bin/ is not a package; routing_scorecard.py is loaded via importlib by absolute path
computed from this file's own location (BIN_DIR), mirroring tests/test_routing_scorecard.py
and tests/test_reroute_live.py.
"""

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
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


rs = _load("routing_scorecard")


# ---- fixture helpers --------------------------------------------------------------------------

def write_kit(kits_root, name, tasks_md, notes_md=None):
    """Write a temp kit dir under ``kits_root/name`` (TASKS.md + optional NOTES.md).

    ``kits_root`` is a directory path (typically ``<tmp>/kits``, shared across several
    calls for a multi-kit fixture). Returns the kit dir path.
    """
    kit_dir = Path(kits_root) / name
    kit_dir.mkdir(parents=True, exist_ok=True)
    (kit_dir / "TASKS.md").write_text(tasks_md)
    if notes_md is not None:
        (kit_dir / "NOTES.md").write_text(notes_md)
    return kit_dir


def write_transcript(projects_root, session_id, messages):
    """Write a synthetic transcript JSONL under ``projects_root/-t/<session_id>.jsonl``.

    ``messages`` is a list of dicts ``{"model", "id", "input_tokens", "output_tokens"}``;
    the JSONL shape mirrors ``run_demo``'s transcript fixtures
    (``{"timestamp", "message": {"model", "id", "usage": {...}}}``). The project-slug
    subdir name (``-t``) is synthetic -- ``find_main_transcript`` locates files by
    recursive glob on the session-id filename, so the subdir name itself is irrelevant.
    """
    proj = Path(projects_root) / "-t"
    proj.mkdir(parents=True, exist_ok=True)
    ts = "2026-07-01T12:00:00+00:00"
    lines = []
    for m in messages:
        lines.append(json.dumps({
            "timestamp": ts,
            "message": {
                "model": m["model"],
                "id": m["id"],
                "usage": {
                    "input_tokens": m["input_tokens"],
                    "output_tokens": m["output_tokens"],
                },
            },
        }))
    path = proj / f"{session_id}.jsonl"
    path.write_text("\n".join(lines) + "\n")
    return path


def _task(tid, status="pending", model=None):
    """A minimal task dict -- the history functions read only id/status/model via .get."""
    return {"id": tid, "status": status, "model": model}


def _outcome(model, result, attempts=1, review="none"):
    """A parsed-outcome dict, matching parse_outcomes' per-id shape."""
    return {"model": model, "attempts": attempts, "result": result, "review": review}


def _run_cli(args):
    """subprocess.run the real CLI from the repo root (never the dotted-module form)."""
    return subprocess.run(
        [sys.executable, "bin/routing_scorecard.py"] + args,
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )


# ---- kit fixtures (spaced em dash headings, pinned outcome:/reroute:/session: grammars) --------

ALPHA_TASKS_MD = """# TASKS — aaa-kit (synthetic)

## Phase 1 — only phase

### AA1 — a haiku task
- status: done
- model: haiku
"""

SCAN_ZZZ_TASKS_MD = """# TASKS — zzz-kit (synthetic)

## Phase 1 — only phase

### Z1 — a sonnet task
- status: done
- model: sonnet
"""

SCAN_ZZZ_NOTES_MD = """# NOTES — zzz-kit (synthetic)

## Outcome ledger
outcome: Z1 model=sonnet attempts=1 result=pass review=clean
reroute: haiku to=sonnet mode=advisory tasks=Z1 rate=1/1
session: zzz-session
"""

BAD_STATUS_TASKS_MD = """# TASKS — bad-kit (synthetic)

## Phase 1 — only phase

### X1 — a task with a malformed status
- status: nonsense
- model: sonnet
"""

PRICED_TASKS_MD = """# TASKS — priced-kit (synthetic)

## Phase 1 — only phase

### R1 — a priced task
- status: done
- model: sonnet
"""

UNPRICED_TASKS_MD = """# TASKS — unpriced-kit (synthetic)

## Phase 1 — only phase

### S1 — an unpriced task
- status: done
- model: haiku
"""

UNPRICED_NOTES_MD = """# NOTES — unpriced-kit (synthetic)

## Outcome ledger
outcome: S1 model=haiku attempts=1 result=pass review=clean
"""

MULTI_TASKS_MD = """# TASKS — multi-kit (synthetic)

## Phase 1 — only phase

### M1 — a task with two sessions on record
- status: done
- model: sonnet
"""

GHOST_TASKS_MD = """# TASKS — ghost-kit (synthetic)

## Phase 1 — only phase

### G1 — a task whose sessions have no transcripts
- status: done
- model: sonnet
"""

SHARE1_TASKS_MD = """# TASKS — share-kit-1 (synthetic)

## Phase 1 — only phase

### SH1 — a task in the first kit sharing a session id
- status: done
- model: opus
"""

SHARE2_TASKS_MD = """# TASKS — share-kit-2 (synthetic)

## Phase 1 — only phase

### SH2 — a task in the second kit sharing a session id
- status: done
- model: opus
"""

READONLY_TASKS_MD = """# TASKS — readonly-kit (synthetic)

## Phase 1 — only phase

### RO1 — a task exercising the read-only proof
- status: done
- model: haiku
"""


# ---- 1. parse_sessions ---------------------------------------------------------------------


class ParseSessionsTests(unittest.TestCase):
    def test_parse_sessions_happy_and_tolerant(self):
        text = "\n".join([
            "session: abc-1",
            "- session: abc-1",          # duplicate, bullet -- dedupe preserves first-seen
            "* session: def-2",
            "session: def-2",            # duplicate again
            "session: two tokens",       # malformed -- extra token, no id-format validation
        ])
        ids, notes = rs.parse_sessions(text)

        self.assertEqual(ids, ["abc-1", "def-2"])
        self.assertEqual(
            sum(1 for n in notes if "unrecognized session line" in n), 1)
        # the id itself is never format-checked -- any single token is accepted
        ids2, notes2 = rs.parse_sessions("session: 12345-not-a-uuid-at-all\n")
        self.assertEqual(ids2, ["12345-not-a-uuid-at-all"])
        self.assertEqual(notes2, [])


# ---- 2/3. history_tier_stats -----------------------------------------------------------------


class HistoryTierStatsTests(unittest.TestCase):
    def test_history_tier_stats_attribution_matrix(self):
        tasks = [
            _task("A1", status="done", model="haiku"),
            _task("A2", status="done", model="sonnet"),
            _task("A3", status="done", model="opus"),
            _task("A4", status="done", model="sonnet"),  # escalated evidence goes HERE
            _task("A5", status="done", model="fable"),
            _task("A6", status="done", model="haiku"),   # escalated + applied re-route
        ]
        outcomes = {
            "A1": _outcome("haiku", "pass"),
            "A2": _outcome("sonnet", "retry-pass"),
            "A3": _outcome("opus", "blocked"),
            # ledger's model= names the Fable fixer, not the failing tier
            "A4": _outcome("fable", "escalated-pass"),
            "A5": _outcome("fable", "pass"),
            "A6": _outcome("fable", "escalated-pass"),
            "ZZZ": _outcome("haiku", "pass"),  # unknown task id
        }
        applied_events = [
            {"from": "haiku", "to": "sonnet", "mode": "applied",
             "tasks": ["A6"], "rate": "0/1"},
        ]
        stats, notes = rs.history_tier_stats(tasks, outcomes, applied_events)

        # all four LIVE_TIER_ORDER tiers always present
        self.assertEqual(set(stats), set(rs.LIVE_TIER_ORDER))

        self.assertEqual(stats["haiku"]["with_outcome"], 1)
        self.assertEqual(stats["haiku"]["first_try"], 1)

        self.assertEqual(stats["opus"]["with_outcome"], 1)
        self.assertEqual(stats["opus"]["blocked"], 1)

        # A2 (retry-pass, sonnet pin) + A4 (escalated-pass, sonnet pin, no covering event)
        # + A6 (escalated-pass, haiku pin BUT an applied haiku->sonnet event names it) --
        # all three land on sonnet, never frontier.
        self.assertEqual(stats["sonnet"]["with_outcome"], 3)
        self.assertEqual(stats["sonnet"]["retry_pass"], 1)
        self.assertEqual(stats["sonnet"]["escalated_pass"], 2)

        # a fable-pinned task's plain pass lands in the frontier bucket
        self.assertEqual(stats["frontier"]["with_outcome"], 1)
        self.assertEqual(stats["frontier"]["first_try"], 1)

        self.assertTrue(any("unknown task id" in n and "ZZZ" in n for n in notes))

    def test_history_tier_stats_pinned_and_unpinned(self):
        tasks = [
            _task("P1", status="pending", model="haiku"),
            _task("P2", status="pending", model=None),      # no pin
            _task("P3", status="pending", model="banana"),  # off-ladder pin
        ]
        applied_events = [
            {"from": "haiku", "to": "sonnet", "mode": "applied",
             "tasks": ["P1"], "rate": "0/1"},
        ]
        stats_no_reroute, _ = rs.history_tier_stats(tasks, {}, [])
        stats_with_reroute, notes = rs.history_tier_stats(tasks, {}, applied_events)

        # pinned counts follow the RAW pin -- an applied re-route never shifts them.
        self.assertEqual(stats_no_reroute["haiku"]["pinned"], 1)
        self.assertEqual(stats_with_reroute["haiku"]["pinned"], 1)
        self.assertEqual(stats_with_reroute["sonnet"]["pinned"], 0)
        for tier in rs.LIVE_TIER_ORDER:
            self.assertEqual(
                stats_no_reroute[tier]["pinned"], stats_with_reroute[tier]["pinned"])

        # unpinned / off-ladder tasks are excluded from every tier, one summary note
        for tier in rs.LIVE_TIER_ORDER:
            self.assertEqual(stats_with_reroute[tier]["with_outcome"], 0)
        self.assertEqual(
            sum(1 for n in notes if "without a recognized tier pin" in n), 1)
        self.assertTrue(
            any("2 tasks without a recognized tier pin" in n for n in notes))


# ---- 4. tally_reroutes ---------------------------------------------------------------------


class TallyReroutesTests(unittest.TestCase):
    def test_tally_reroutes_modes_and_tiers(self):
        events = [
            {"from": "haiku", "to": "sonnet", "mode": "advisory",
             "tasks": ["T1"], "rate": "0/1"},
            {"from": "haiku", "to": "sonnet", "mode": "applied",
             "tasks": ["T2"], "rate": "0/1"},
            {"from": "sonnet", "to": "opus", "mode": "advisory",
             "tasks": ["T3", "T4"], "rate": "1/2"},
        ]
        tally = rs.tally_reroutes(events)

        self.assertEqual(tally["events"], 3)   # events counted, not task ids
        self.assertEqual(tally["applied"], 1)
        self.assertEqual(tally["advisory"], 2)
        self.assertEqual(set(tally["by_tier"]), set(rs.LIVE_TIER_ORDER))

        self.assertEqual(tally["by_tier"]["haiku"], {
            "applied_from": 1, "applied_to": 0, "advisory_from": 1, "advisory_to": 0})
        self.assertEqual(tally["by_tier"]["sonnet"], {
            "applied_from": 0, "applied_to": 1, "advisory_from": 1, "advisory_to": 1})
        self.assertEqual(tally["by_tier"]["opus"], {
            "applied_from": 0, "applied_to": 0, "advisory_from": 0, "advisory_to": 1})
        # an untouched tier is still present, all zeros
        self.assertEqual(tally["by_tier"]["frontier"], {
            "applied_from": 0, "applied_to": 0, "advisory_from": 0, "advisory_to": 0})


# ---- 5/6. scan_kits --------------------------------------------------------------------------


class ScanKitsTests(unittest.TestCase):
    def test_scan_kits_tolerant_and_sorted(self):
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            write_kit(kits_root, "zzz-kit", SCAN_ZZZ_TASKS_MD, SCAN_ZZZ_NOTES_MD)
            write_kit(kits_root, "aaa-kit", ALPHA_TASKS_MD)          # no NOTES.md
            write_kit(kits_root, "bad-kit", BAD_STATUS_TASKS_MD)     # malformed status
            (kits_root / "no-tasks-dir").mkdir(parents=True, exist_ok=True)

            records, notes = rs.scan_kits(kits_root)

        # deterministic sorted-by-name order; malformed/no-TASKS.md kits excluded
        self.assertEqual([r["kit"] for r in records], ["aaa-kit", "zzz-kit"])

        aaa = next(r for r in records if r["kit"] == "aaa-kit")
        self.assertEqual(aaa["outcomes"], {})
        self.assertEqual(aaa["events"], [])
        self.assertEqual(aaa["sessions"], [])

        zzz = next(r for r in records if r["kit"] == "zzz-kit")
        self.assertIn("Z1", zzz["outcomes"])
        self.assertEqual(len(zzz["events"]), 1)
        self.assertEqual(zzz["sessions"], ["zzz-session"])

        self.assertTrue(any(n.startswith("no-tasks-dir: no TASKS.md") for n in notes))
        self.assertTrue(any(n.startswith("bad-kit:") and "malformed TASKS.md" in n
                             for n in notes))
        self.assertTrue(any(n.startswith("aaa-kit: no outcome ledger — status-only")
                             for n in notes))

    def test_ledger_free_kit_status_only(self):
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            write_kit(kits_root, "pre-ledger", ALPHA_TASKS_MD)  # TASKS.md only
            records, notes = rs.scan_kits(kits_root)

        rec = records[0]
        self.assertEqual(rec["kit"], "pre-ledger")
        self.assertEqual(rec["outcomes"], {})
        self.assertEqual(rec["events"], [])
        self.assertEqual(rec["sessions"], [])
        self.assertTrue(any("no outcome ledger — status-only" in n for n in rec["notes"]))

        # contributes pins only, nothing invented in the outcome counters
        stats, _ = rs.history_tier_stats(rec["tasks"], rec["outcomes"], [])
        self.assertEqual(stats["haiku"]["pinned"], 1)
        for tier in rs.LIVE_TIER_ORDER:
            self.assertEqual(stats[tier]["with_outcome"], 0)
            self.assertEqual(stats[tier]["first_try"], 0)


# ---- 7. zero-denominator rates -----------------------------------------------------------------


class ZeroDenominatorTests(unittest.TestCase):
    def test_zero_denominator_rates_null(self):
        tasks = [_task("Q1", status="pending", model="opus")]
        stats, _ = rs.history_tier_stats(tasks, {}, [])

        self.assertIsNone(stats["opus"]["first_try_rate"])
        self.assertIsNone(stats["opus"]["escalation_rate"])
        self.assertEqual(rs._rate_pct(stats["opus"]["first_try_rate"]), "n/a")

        records = [{"kit": "solo", "tasks": tasks, "outcomes": {}, "events": [],
                   "sessions": [], "notes": []}]
        card = rs.build_history("kits-dir", records, {}, None, [])
        for tier in rs.LIVE_TIER_ORDER:
            self.assertIsNone(card["tiers"][tier]["first_try_rate"])
            self.assertIsNone(card["tiers"][tier]["escalation_rate"])

        md = rs.render_history_markdown(card)
        self.assertNotIn("0%", md)
        self.assertIn("n/a", md)


# ---- 8. pricing-free without sessions -----------------------------------------------------


class PricingFreeTests(unittest.TestCase):
    def test_history_pricing_free_without_sessions(self):
        original = rs.cr.load_pricing

        def _boom():
            raise RuntimeError(
                "the zero-session-lines --history path must never load pricing")

        rs.cr.load_pricing = _boom
        try:
            with tempfile.TemporaryDirectory() as td:
                kits_root = Path(td) / "kits"
                write_kit(kits_root, "no-sessions", ALPHA_TASKS_MD)  # no NOTES.md at all
                projects_root = Path(td) / "projects"
                projects_root.mkdir()

                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = rs.main(["--history", "--kits-dir", str(kits_root),
                                 "--projects-dir", str(projects_root), "--json"])
            self.assertEqual(rc, 0)
            card = json.loads(buf.getvalue())
            self.assertIsNone(card["dollars"])
            self.assertTrue(any("no session: lines found" in n for n in card["notes"]))
        finally:
            rs.cr.load_pricing = original


# ---- 9-12. dollars aggregation ----------------------------------------------------------------


class DollarsAggregationTests(unittest.TestCase):
    def test_dollars_partial_and_labeled(self):
        pricing = rs.cr.load_pricing()
        model_id = rs._first_model_of_tier(pricing, "sonnet")
        self.assertIsNotNone(model_id)

        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            priced_notes = (
                "## Outcome ledger\n"
                "outcome: R1 model=sonnet attempts=1 result=pass review=clean\n"
                "session: priced-session\n"
            )
            write_kit(kits_root, "priced-kit", PRICED_TASKS_MD, priced_notes)
            write_kit(kits_root, "unpriced-kit", UNPRICED_TASKS_MD, UNPRICED_NOTES_MD)

            projects_root = Path(td) / "projects"
            write_transcript(projects_root, "priced-session", [
                {"model": model_id, "id": "priced-msg-1",
                 "input_tokens": 1000, "output_tokens": 200},
            ])

            result = _run_cli(["--history", "--kits-dir", str(kits_root),
                               "--projects-dir", str(projects_root),
                               "--no-subagents", "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            card = json.loads(result.stdout)

            md_result = _run_cli(["--history", "--kits-dir", str(kits_root),
                                  "--projects-dir", str(projects_root),
                                  "--no-subagents"])
            self.assertEqual(md_result.returncode, 0, md_result.stderr)

        rows = {r["kit"]: r for r in card["kits"]}
        self.assertIsNotNone(rows["priced-kit"]["cost"])
        self.assertGreater(rows["priced-kit"]["cost"]["actual_usd"], 0)
        self.assertIsNone(rows["unpriced-kit"]["cost"])

        dol = card["dollars"]
        self.assertIsNotNone(dol)
        self.assertEqual(dol["coverage"], "partial")
        self.assertEqual(dol["kits_with_sessions"], 1)
        self.assertEqual(dol["kits_total"], 2)
        self.assertGreater(dol["actual_usd"], 0)

        unpriced_lines = [ln for ln in md_result.stdout.splitlines()
                          if "unpriced-kit" in ln]
        self.assertTrue(unpriced_lines)
        self.assertTrue(all("n/a" in ln for ln in unpriced_lines))

    def test_multi_session_kit_single_collect(self):
        pricing = rs.cr.load_pricing()
        model_id = rs._first_model_of_tier(pricing, "sonnet")
        self.assertIsNotNone(model_id)

        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            notes_md = (
                "## Outcome ledger\n"
                "outcome: M1 model=sonnet attempts=1 result=pass review=clean\n"
                "session: multi-session-a\n"
                "session: multi-session-b\n"
            )
            write_kit(kits_root, "multi-kit", MULTI_TASKS_MD, notes_md)

            projects_root = Path(td) / "projects"
            shared = {"model": model_id, "id": "shared-msg",
                     "input_tokens": 1000, "output_tokens": 300}
            only_a = {"model": model_id, "id": "a-only-msg",
                     "input_tokens": 500, "output_tokens": 100}
            only_b = {"model": model_id, "id": "b-only-msg",
                     "input_tokens": 700, "output_tokens": 150}
            t_a = write_transcript(projects_root, "multi-session-a", [shared, only_a])
            t_b = write_transcript(projects_root, "multi-session-b", [shared, only_b])

            records, _ = rs.scan_kits(kits_root)
            rec = records[0]
            self.assertEqual(rec["sessions"], ["multi-session-a", "multi-session-b"])

            cost, transcripts, notes = rs.kit_cost_summary(
                rec["sessions"], str(projects_root), True, None, pricing)

            # ground truth: the SAME files priced via one reused-pipeline collect() call
            files = rs.sc.gather_files(None, [], [str(t_a), str(t_b)])
            data = rs.sc.collect(files, pricing)
            cf = rs.sc.resolve_counterfactual_model(None, pricing)
            rep = rs.sc.build_report(data, cf, pricing, pricing.get("billing_mode", "api"))

        self.assertIsNotNone(cost)
        self.assertEqual(len(transcripts), 2)
        self.assertEqual(cost["sessions_priced"], 2)
        # the duplicated message counts once: 3 unique messages, not 4
        self.assertEqual(data["unique_messages"], 3)
        self.assertAlmostEqual(cost["actual_usd"], rep["actual_total"], places=9)

    def test_missing_transcript_never_fabricates(self):
        pricing = rs.cr.load_pricing()

        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            notes_md = (
                "## Outcome ledger\n"
                "outcome: G1 model=sonnet attempts=1 result=pass review=clean\n"
                "session: ghost-session-1\n"
                "session: ghost-session-2\n"
            )
            write_kit(kits_root, "ghost-kit", GHOST_TASKS_MD, notes_md)
            projects_root = Path(td) / "projects"
            projects_root.mkdir()

            cost, transcripts, notes = rs.kit_cost_summary(
                ["ghost-session-1", "ghost-session-2"], str(projects_root),
                True, None, pricing)
            self.assertIsNone(cost)
            self.assertEqual(transcripts, [])
            self.assertTrue(any("ghost-session-1" in n for n in notes))
            self.assertTrue(any("ghost-session-2" in n for n in notes))

            result = _run_cli(["--history", "--kits-dir", str(kits_root),
                               "--projects-dir", str(projects_root),
                               "--no-subagents", "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            card = json.loads(result.stdout)

        self.assertIsNone(card["dollars"])
        self.assertIsNone(card["kits"][0]["cost"])
        self.assertTrue(any("ghost-session-1" in n for n in card["notes"]))
        self.assertTrue(any("ghost-session-2" in n for n in card["notes"]))
        # no zeroed stand-in anywhere in the JSON
        self.assertNotIn('"actual_usd": 0', json.dumps(card))
        self.assertNotIn("$0.00", json.dumps(card))

    def test_shared_session_priced_once_in_aggregate(self):
        pricing = rs.cr.load_pricing()
        model_id = rs._first_model_of_tier(pricing, "opus")
        self.assertIsNotNone(model_id)

        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            notes_1 = (
                "## Outcome ledger\n"
                "outcome: SH1 model=opus attempts=1 result=pass review=clean\n"
                "session: shared-session\n"
            )
            notes_2 = (
                "## Outcome ledger\n"
                "outcome: SH2 model=opus attempts=1 result=pass review=clean\n"
                "session: shared-session\n"
            )
            write_kit(kits_root, "share-kit-1", SHARE1_TASKS_MD, notes_1)
            write_kit(kits_root, "share-kit-2", SHARE2_TASKS_MD, notes_2)

            projects_root = Path(td) / "projects"
            write_transcript(projects_root, "shared-session", [
                {"model": model_id, "id": "shared-only-msg",
                 "input_tokens": 2000, "output_tokens": 400},
            ])

            result = _run_cli(["--history", "--kits-dir", str(kits_root),
                               "--projects-dir", str(projects_root),
                               "--no-subagents", "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            card = json.loads(result.stdout)

        rows = {r["kit"]: r for r in card["kits"]}
        # each per-kit row still carries its own full figure
        self.assertIsNotNone(rows["share-kit-1"]["cost"])
        self.assertIsNotNone(rows["share-kit-2"]["cost"])
        self.assertAlmostEqual(
            rows["share-kit-1"]["cost"]["actual_usd"],
            rows["share-kit-2"]["cost"]["actual_usd"], places=9)
        # the aggregate prices the shared session ONCE, not twice
        self.assertAlmostEqual(
            card["dollars"]["actual_usd"],
            rows["share-kit-1"]["cost"]["actual_usd"], places=9)
        self.assertEqual(card["dollars"]["sessions_found"], 1)
        self.assertTrue(any(
            "shared-session" in n and "shared by kits" in n for n in card["notes"]))


# ---- 13-17. CLI end-to-end ---------------------------------------------------------------------


class CliHistoryTests(unittest.TestCase):
    def test_cli_history_json_keys(self):
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            write_kit(kits_root, "solo-kit", ALPHA_TASKS_MD)
            projects_root = Path(td) / "projects"
            projects_root.mkdir()

            result = _run_cli(["--history", "--kits-dir", str(kits_root),
                               "--projects-dir", str(projects_root), "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            card = json.loads(result.stdout)

            md_result = _run_cli(["--history", "--kits-dir", str(kits_root),
                                  "--projects-dir", str(projects_root)])
            self.assertEqual(md_result.returncode, 0, md_result.stderr)

        self.assertEqual(set(card), {
            "schema_version", "generated_at", "kits_dir", "kits", "tiers",
            "reroutes", "roles", "dollars", "notes",
        })
        self.assertEqual(card["schema_version"], 2)
        for tier in rs.LIVE_TIER_ORDER:
            self.assertEqual(set(card["tiers"][tier]), {
                "pinned", "with_outcome", "first_try", "retry_pass", "escalated_pass",
                "blocked", "first_try_rate", "escalation_rate", "reroutes",
            })
            self.assertEqual(set(card["tiers"][tier]["reroutes"]), {
                "applied_from", "applied_to", "advisory_from", "advisory_to",
            })
        self.assertEqual(set(card["reroutes"]), {"events", "applied", "advisory"})

        h2s = ["## Verdict", "## Per-tier track record", "## Role quality",
               "## Re-route history", "## Kits", "## Dollars"]
        self.assertIn("# Routing history — cross-kit per-tier track record",
                      md_result.stdout)
        idx = [md_result.stdout.index(h) for h in h2s]
        self.assertEqual(idx, sorted(idx))

    def test_cli_history_rejects_kit_live_session(self):
        r1 = _run_cli(["some-kit", "--history"])
        self.assertNotEqual(r1.returncode, 0)
        self.assertIn("kit argument", r1.stderr)

        r2 = _run_cli(["--history", "--live"])
        self.assertNotEqual(r2.returncode, 0)
        self.assertIn("--live", r2.stderr)

        r3 = _run_cli(["--history", "--session", "some-session"])
        self.assertNotEqual(r3.returncode, 0)
        self.assertIn("--session", r3.stderr)

    def test_cli_history_empty_kits_dir(self):
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            kits_root.mkdir()
            projects_root = Path(td) / "projects"
            projects_root.mkdir()
            result = _run_cli(["--history", "--kits-dir", str(kits_root),
                               "--projects-dir", str(projects_root), "--json"])
        self.assertEqual(result.returncode, 0, result.stderr)
        card = json.loads(result.stdout)
        self.assertEqual(card["kits"], [])
        self.assertTrue(any("no kits" in n for n in card["notes"]))

        with tempfile.TemporaryDirectory() as td2:
            nonexistent = Path(td2) / "does-not-exist"
            result2 = _run_cli(["--history", "--kits-dir", str(nonexistent)])
        self.assertNotEqual(result2.returncode, 0)
        self.assertIn(str(nonexistent), result2.stderr)

    def test_demo_history_pinned_numbers(self):
        j = _run_cli(["--demo", "--history", "--json"])
        self.assertEqual(j.returncode, 0, j.stderr)
        card = json.loads(j.stdout)

        t = card["tiers"]
        K = ("pinned", "with_outcome", "first_try", "retry_pass", "escalated_pass",
             "blocked")
        pick = lambda tier: tuple(t[tier][k] for k in K)
        self.assertEqual(pick("haiku"), (3, 3, 2, 1, 0, 0))
        self.assertEqual(pick("sonnet"), (6, 5, 2, 1, 1, 1))
        self.assertEqual(pick("opus"), (2, 1, 1, 0, 0, 0))
        self.assertEqual(pick("frontier"), (1, 0, 0, 0, 0, 0))
        self.assertAlmostEqual(t["haiku"]["first_try_rate"], 2 / 3, places=9)
        self.assertAlmostEqual(t["sonnet"]["first_try_rate"], 0.4, places=9)
        self.assertAlmostEqual(t["sonnet"]["escalation_rate"], 0.2, places=9)
        self.assertIsNone(t["frontier"]["first_try_rate"])
        self.assertIsNone(t["frontier"]["escalation_rate"])

        self.assertEqual(card["reroutes"], {"events": 1, "applied": 0, "advisory": 1})
        self.assertEqual(t["haiku"]["reroutes"]["advisory_from"], 1)
        self.assertEqual(t["sonnet"]["reroutes"]["advisory_to"], 1)

        rows = {k["kit"]: k for k in card["kits"]}
        self.assertEqual(list(rows), ["hist-alpha", "hist-beta", "hist-gamma"])
        self.assertEqual((rows["hist-alpha"]["tasks"], rows["hist-alpha"]["with_outcome"]),
                         (5, 5))
        self.assertEqual((rows["hist-beta"]["tasks"], rows["hist-beta"]["with_outcome"]),
                         (4, 4))
        self.assertEqual((rows["hist-gamma"]["tasks"], rows["hist-gamma"]["with_outcome"]),
                         (3, 0))
        self.assertIsNone(rows["hist-beta"]["cost"])
        self.assertIsNone(rows["hist-gamma"]["cost"])
        self.assertIsNotNone(rows["hist-alpha"]["cost"])
        self.assertGreater(rows["hist-alpha"]["cost"]["actual_usd"], 0)

        dol = card["dollars"]
        self.assertIsNotNone(dol)
        self.assertEqual((dol["kits_total"], dol["kits_with_sessions"],
                          dol["sessions_found"], dol["sessions_priced"]), (3, 1, 1, 1))
        self.assertEqual(dol["coverage"], "partial")
        self.assertGreater(dol["actual_usd"], 0)

        roles = card["roles"]
        v = roles["verifier"]
        self.assertEqual((v["events"], v["with_precision"], v["findings"], v["confirmed"]),
                          (2, 2, 5, 3))
        self.assertAlmostEqual(v["precision"], 0.6, places=9)
        self.assertEqual(v["results"],
                          {"accepted": 1, "revised": 1, "blocked": 0, "unrecorded": 0})
        self.assertEqual(v["by_tier"]["haiku"]["precision"], 1.0)
        self.assertEqual(v["by_tier"]["sonnet"]["findings"], 3)
        self.assertEqual(roles["escalation"],
                          {"events": 1,
                           "results": {"accepted": 1, "revised": 0, "blocked": 0,
                                       "unrecorded": 0}})
        r = roles["reviewer"]
        self.assertEqual((r["events"], r["findings"], r["confirmed"]), (1, 2, 1))
        self.assertAlmostEqual(r["precision"], 0.5, places=9)
        a = roles["architect"]
        self.assertEqual(a["defects"], 2)
        self.assertEqual(a["kits_recording"], 1)
        self.assertEqual(a["by_kind"], {"stale-pin": 1, "tautological-verify": 1})
        self.assertEqual(a["by_kit"], {"hist-alpha": 2})

        m = _run_cli(["--demo", "--history"])
        self.assertEqual(m.returncode, 0, m.stderr)
        for needle in ("# Routing history — cross-kit per-tier track record",
                      "## Verdict", "## Per-tier track record", "## Role quality",
                      "## Re-route history", "## Kits", "## Dollars", "partial", "n/a",
                      "hist-alpha", "hist-gamma", "stale-pin"):
            self.assertIn(needle, m.stdout)

    def test_prior_demos_regression(self):
        j = _run_cli(["--demo", "--json"])
        self.assertEqual(j.returncode, 0, j.stderr)
        c = json.loads(j.stdout)
        q = c["quality"]
        self.assertEqual(
            (q["total"], q["with_outcome"], q["first_try_pass"], q["retry_pass"],
             q["escalated_pass"], q["blocked"]), (6, 6, 3, 1, 1, 1))
        self.assertEqual(c["model_mix"], {"haiku": 1, "sonnet": 4, "fable": 1})
        self.assertAlmostEqual(c["review"]["survival_rate"], 0.75, places=9)

        l = _run_cli(["--demo", "--live", "--json"])
        self.assertEqual(l.returncode, 0, l.stderr)
        d = json.loads(l.stdout)
        self.assertEqual(d["autonomy"], "advisory")
        self.assertEqual(d["budget"], {"cap": 2, "applied": 0, "remaining": 2})
        recs = d["recommendations"]
        self.assertEqual(len(recs), 1)
        self.assertEqual((recs[0]["from"], recs[0]["to"], recs[0]["task_ids"]),
                         ("sonnet", "opus", ["L5", "L6"]))


# ---- 18. read-only proof -------------------------------------------------------------------


class SafetyProofTests(unittest.TestCase):
    def test_readonly_history_run(self):
        pricing = rs.cr.load_pricing()
        model_id = rs._first_model_of_tier(pricing, "haiku")
        self.assertIsNotNone(model_id)

        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            notes_md = (
                "## Outcome ledger\n"
                "outcome: RO1 model=haiku attempts=1 result=pass review=clean\n"
                "session: readonly-session\n"
            )
            write_kit(kits_root, "readonly-kit", READONLY_TASKS_MD, notes_md)
            projects_root = Path(td) / "projects"
            write_transcript(projects_root, "readonly-session", [
                {"model": model_id, "id": "ro-msg",
                 "input_tokens": 100, "output_tokens": 20},
            ])

            def snapshot(root):
                files = sorted(p for p in Path(root).rglob("*") if p.is_file())
                return [str(p) for p in files], {str(p): p.read_bytes() for p in files}

            kits_before_paths, kits_before_bytes = snapshot(kits_root)
            proj_before_paths, proj_before_bytes = snapshot(projects_root)

            result = _run_cli(["--history", "--kits-dir", str(kits_root),
                               "--projects-dir", str(projects_root), "--json"])

            kits_after_paths, kits_after_bytes = snapshot(kits_root)
            proj_after_paths, proj_after_bytes = snapshot(projects_root)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(kits_before_paths, kits_after_paths)
        self.assertEqual(kits_before_bytes, kits_after_bytes)
        self.assertEqual(proj_before_paths, proj_after_paths)
        self.assertEqual(proj_before_bytes, proj_after_bytes)


# ---- 19. pure assemble_history_card (telemetry-store T4) -------------------------------------


class AssembleHistoryCardTests(unittest.TestCase):
    """The pure extraction of ``run_history``'s assembly (telemetry-store PLAN D3).

    Same safety contract as the rest of this file: every fixture is a temp dir handed in
    explicitly. ``test_projects_dir_none_resolves_to_module_default`` compares the resolved
    default against the loaded ``session_cost`` module's ``DEFAULT_PROJECTS_DIR`` CONSTANT
    and stubs ``rs.kit_cost_summary`` (the only consumer of ``projects_dir``), so the real
    projects dir is never read and no home path is ever spelled out here.
    """

    def test_card_matches_cli_history_json(self):
        pricing = rs.cr.load_pricing()
        model_id = rs._first_model_of_tier(pricing, "sonnet")
        self.assertIsNotNone(model_id)

        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            priced_notes = (
                "## Outcome ledger\n"
                "outcome: R1 model=sonnet attempts=1 result=pass review=clean\n"
                "session: pure-session\n"
            )
            write_kit(kits_root, "priced-kit", PRICED_TASKS_MD, priced_notes)
            write_kit(kits_root, "unpriced-kit", UNPRICED_TASKS_MD, UNPRICED_NOTES_MD)
            projects_root = Path(td) / "projects"
            write_transcript(projects_root, "pure-session", [
                {"model": model_id, "id": "pure-msg",
                 "input_tokens": 500, "output_tokens": 120},
            ])

            card = rs.assemble_history_card([str(kits_root)],
                                            projects_dir=str(projects_root))
            result = _run_cli(["--history", "--kits-dir", str(kits_root),
                               "--projects-dir", str(projects_root), "--json"])

        self.assertEqual(result.returncode, 0, result.stderr)
        cli_card = json.loads(result.stdout)

        # ``generated_at`` is a wall-clock stamp taken independently by each build; every
        # other byte of the card must match. Both must still carry a stamp.
        for c in (card, cli_card):
            self.assertTrue(str(c["generated_at"]).startswith("20"), c["generated_at"])
        cli_card["generated_at"] = card["generated_at"]

        self.assertEqual(card, cli_card)
        self.assertIsNotNone(card["dollars"])
        self.assertEqual(card["dollars"]["sessions_priced"], 1)
        self.assertFalse(any(str(n).startswith("snapshot written") for n in card["notes"]))

    def test_missing_kits_dir_raises_value_error(self):
        with tempfile.TemporaryDirectory() as td:
            nonexistent = Path(td) / "does-not-exist"
            with self.assertRaises(ValueError) as ctx:
                rs.assemble_history_card([str(nonexistent)],
                                         projects_dir=str(Path(td) / "projects"))
        self.assertEqual(str(ctx.exception), f"kits dir not found: {nonexistent}")

    def test_empty_kits_dirs_raises_value_error_not_index_error(self):
        """An empty token list resolves to zero entries. The CLI can never produce that
        (argparse defaults + ``main``'s backstop), but non-CLI callers can — e.g. the
        telemetry snapshot tool's ``[kits_dir] if kits_dir else []``. "Nothing to scan" is
        the same failure as "the dir isn't there", so it must raise the SAME ValueError
        shape, never reach ``entries[0]`` and blow up with IndexError."""
        for tokens in ([], ()):
            with self.subTest(tokens=tokens):
                with self.assertRaises(ValueError) as ctx:
                    rs.assemble_history_card(list(tokens))
                self.assertEqual(
                    str(ctx.exception), "kits dir not found: (none specified)"
                )

    def test_empty_kits_dirs_never_touches_the_filesystem_or_prints(self):
        """The empty-input guard fires before any scan, pricing load, or output."""
        original = rs.cr.load_pricing

        def _boom(*a, **k):  # pragma: no cover - must never be called
            raise AssertionError("pricing must not load on the empty-input path")

        rs.cr.load_pricing = _boom
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(ValueError):
                    rs.assemble_history_card([])
            self.assertEqual(buf.getvalue(), "")
        finally:
            rs.cr.load_pricing = original

    def test_projects_dir_none_resolves_to_module_default(self):
        seen = []

        def fake_kit_cost_summary(session_ids, projects_dir, no_subagents, vs, pricing):
            seen.append(projects_dir)
            return None, [], []

        real = rs.kit_cost_summary
        rs.kit_cost_summary = fake_kit_cost_summary
        try:
            with tempfile.TemporaryDirectory() as td:
                kits_root = Path(td) / "kits"
                notes_md = (
                    "## Outcome ledger\n"
                    "outcome: R1 model=sonnet attempts=1 result=pass review=clean\n"
                    "session: default-dir-session\n"
                )
                write_kit(kits_root, "priced-kit", PRICED_TASKS_MD, notes_md)
                card = rs.assemble_history_card([str(kits_root)])
        finally:
            rs.kit_cost_summary = real

        self.assertTrue(seen)
        self.assertEqual(set(seen), {str(rs.sc.DEFAULT_PROJECTS_DIR)})
        self.assertIsNone(card["dollars"])


if __name__ == "__main__":
    unittest.main()
