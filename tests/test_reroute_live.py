"""Stdlib unittest regression suite for the live re-route signal in
bin/routing_scorecard.py (fusion-tier2 T2).

SAFETY CONTRACT (binds every test in this file): no test here ever reads the real Claude
Code project store or resolves the caller's real home directory via the stdlib home
helper -- this file never calls it, and it never spells out the real projects path as a
literal string. Every kit fixture (TASKS.md / NOTES.md / PLAN.md) is written into a fresh
`tempfile.TemporaryDirectory()` and handed to the CLI or the pure functions via an
explicit `--kits-dir` / kit path -- never a bare slug against the real `.claude/kits`.
This file never opens `data/pricing.json` directly, and `test_pricing_free_live_path`
additionally PROVES the live path never loads it: it stubs `rs.cr.load_pricing` to raise
and shows the `--live` branch still succeeds (restoring the stub in `finally`). All
ids/values in every fixture are synthetic; the only model tokens anywhere in this file
are the sanctioned tier vocabulary (`haiku`/`sonnet`/`opus`/`frontier`) plus the `fable`
Agent-tool alias -- never a real model id.

bin/ is not a package; routing_scorecard.py is loaded via importlib by absolute path
computed from this file's own location (BIN_DIR), mirroring
tests/test_routing_scorecard.py.
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

def write_kit(tmp, tasks_md, notes_md=None, plan_md=None):
    """Write a temp kit dir under ``tmp/kits/kit`` (TASKS.md + optional NOTES.md/PLAN.md).

    ``tmp`` is a fresh directory (typically the root of a ``tempfile.TemporaryDirectory``).
    Returns the kit dir path; ``kit_dir.parent`` is the ``--kits-dir`` root and
    ``kit_dir.name`` ("kit") is the slug.
    """
    kits_root = Path(tmp) / "kits"
    kit_dir = kits_root / "kit"
    kit_dir.mkdir(parents=True)
    (kit_dir / "TASKS.md").write_text(tasks_md)
    if notes_md is not None:
        (kit_dir / "NOTES.md").write_text(notes_md)
    if plan_md is not None:
        (kit_dir / "PLAN.md").write_text(plan_md)
    return kit_dir


def _run_cli(args):
    """subprocess.run the real CLI from the repo root (never the dotted-module form)."""
    return subprocess.run(
        [sys.executable, "bin/routing_scorecard.py"] + args,
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )


def _task(tid, status="pending", model=None):
    """A minimal task dict -- the live functions read only id/status/model via .get."""
    return {"id": tid, "status": status, "model": model}


def _outcome(model, result, attempts=1, review="none"):
    """A parsed-outcome dict, matching parse_outcomes' per-id shape."""
    return {"model": model, "attempts": attempts, "result": result, "review": review}


# ---- CLI fixtures (spaced em dash headings, pinned outcome:/reroute: grammars) -----------------

REROUTE_TASKS_MD = """# TASKS — reroute-cli (synthetic test fixture)

## Phase 1 — only phase

### K1 — first sonnet task
- status: done
- model: sonnet

### K2 — second sonnet task
- status: done
- model: sonnet

### K3 — third sonnet task
- status: done
- model: sonnet

### K4 — pending sonnet task
- status: pending
- model: sonnet

### K5 — pending haiku task
- status: pending
- model: haiku
"""

REROUTE_NOTES_MD = """# NOTES — reroute-cli (synthetic test fixture)

## Outcome ledger
outcome: K1 model=sonnet attempts=2 result=blocked review=none
outcome: K2 model=sonnet attempts=2 result=blocked review=none
outcome: K3 model=sonnet attempts=1 result=pass review=clean
"""

PLAN_AUTO_MD = """# PLAN — reroute-cli (synthetic test fixture)

autonomy: auto
"""

KNOB_TASKS_MD = """# TASKS — reroute-knob (synthetic test fixture)

## Phase 1 — only phase

### M1 — done sonnet task
- status: done
- model: sonnet

### M2 — pending sonnet task
- status: pending
- model: sonnet
"""

KNOB_NOTES_MD = """# NOTES — reroute-knob (synthetic test fixture)

## Outcome ledger
outcome: M1 model=sonnet attempts=2 result=blocked review=none
"""


# ---- 1. parse_reroutes --------------------------------------------------------------------------


class ParseReroutesTests(unittest.TestCase):
    def test_parse_reroutes_happy_and_tolerant(self):
        text = "\n".join([
            "reroute: sonnet to=opus mode=advisory tasks=T1,T2 rate=1/3",
            "- reroute: haiku to=sonnet mode=applied tasks=T3 rate=0/3",
            "* reroute: sonnet to=opus mode=advisory tasks=T4 rate=2/4 foo=bar",
            "reroute: sonnet to=opus mode=advisory rate=1/3",       # missing tasks= -> []
            "reroute: sonnet to=opus mode=yolo tasks=T5",            # malformed mode
            "reroute: bogus to=opus mode=advisory tasks=T6",         # malformed from-tier
            "reroute: opus to=frontier mode=advisory tasks=T7 rate=1/3",  # out-of-policy
        ])
        events, notes = rs.parse_reroutes(text)

        self.assertEqual(len(events), 5)
        # file order preserved
        self.assertEqual([e["to"] for e in events],
                          ["opus", "sonnet", "opus", "opus", "frontier"])
        self.assertEqual(events[0], {
            "from": "sonnet", "to": "opus", "mode": "advisory",
            "tasks": ["T1", "T2"], "rate": "1/3",
        })
        self.assertEqual(events[1], {
            "from": "haiku", "to": "sonnet", "mode": "applied",
            "tasks": ["T3"], "rate": "0/3",
        })
        # unknown key=value (foo=bar) ignored -- only pinned keys survive
        self.assertEqual(events[2]["tasks"], ["T4"])
        self.assertEqual(events[2]["mode"], "advisory")
        # missing tasks= -> []
        self.assertEqual(events[3]["tasks"], [])
        # to=frontier still parsed (honest state reconstruction)
        self.assertEqual(events[4], {
            "from": "opus", "to": "frontier", "mode": "advisory",
            "tasks": ["T7"], "rate": "1/3",
        })

        self.assertEqual(
            sum(1 for n in notes if "unrecognized reroute line" in n), 2)
        self.assertTrue(any("targets frontier" in n and "out of policy" in n
                             for n in notes))


# ---- 2. parse_autonomy ---------------------------------------------------------------------------


class ParseAutonomyTests(unittest.TestCase):
    def test_parse_autonomy_defaults_and_override(self):
        self.assertEqual(rs.parse_autonomy("autonomy: auto\n"), ("auto", []))
        self.assertEqual(rs.parse_autonomy("autonomy: advisory\n"), ("advisory", []))

        # absent line -> advisory, no note
        self.assertEqual(
            rs.parse_autonomy("# PLAN\n\nsome prose, no autonomy line here.\n"),
            ("advisory", []))

        # None text (no PLAN.md) -> advisory + a note
        posture, notes = rs.parse_autonomy(None)
        self.assertEqual(posture, "advisory")
        self.assertTrue(any("no PLAN.md" in n for n in notes))

        # unrecognized value -> advisory + a note naming the bad value
        posture2, notes2 = rs.parse_autonomy("autonomy: yolo\n")
        self.assertEqual(posture2, "advisory")
        self.assertTrue(any("yolo" in n for n in notes2))

        # first match wins when duplicated
        self.assertEqual(
            rs.parse_autonomy("autonomy: advisory\nautonomy: auto\n"), ("advisory", []))
        self.assertEqual(
            rs.parse_autonomy("autonomy: auto\nautonomy: advisory\n"), ("auto", []))


# ---- 3. attribution -----------------------------------------------------------------------------


class AttributionTests(unittest.TestCase):
    def test_attribution_matrix(self):
        tasks = [
            _task("A1", status="done", model="haiku"),
            _task("A2", status="done", model="sonnet"),
            _task("A3", status="done", model="opus"),
            _task("A4", status="done", model="sonnet"),  # escalated evidence goes HERE
            _task("A5", status="done", model="fable"),
        ]
        outcomes = {
            "A1": _outcome("haiku", "pass"),
            "A2": _outcome("sonnet", "retry-pass"),
            "A3": _outcome("opus", "blocked"),
            # ledger's model= names the Fable fixer, not the failing tier
            "A4": _outcome("fable", "escalated-pass"),
            "A5": _outcome("fable", "pass"),
            "ZZZ": _outcome("haiku", "pass"),  # unknown task id
        }
        stats, notes = rs.live_tier_stats(tasks, outcomes, [])

        # all four LIVE_TIER_ORDER tiers always present
        self.assertEqual(set(stats), set(rs.LIVE_TIER_ORDER))

        self.assertEqual(stats["haiku"], {"completed": 1, "first_try": 1, "rate": 1.0})
        # A2 (retry-pass, sonnet) + A4 (escalated-pass, attributed to sonnet -- NEVER frontier)
        self.assertEqual(stats["sonnet"]["completed"], 2)
        self.assertEqual(stats["sonnet"]["first_try"], 0)
        self.assertEqual(stats["opus"], {"completed": 1, "first_try": 0, "rate": 0.0})
        # a fable-pinned task's pass lands in the frontier bucket
        self.assertEqual(stats["frontier"], {"completed": 1, "first_try": 1, "rate": 1.0})

        self.assertTrue(any("unknown task id" in n and "ZZZ" in n for n in notes))

    def test_escalated_attribution_follows_applied_upgrade(self):
        tasks = [_task("B1", status="pending", model="haiku")]
        applied_event = {"from": "haiku", "to": "sonnet", "mode": "applied",
                          "tasks": ["B1"], "rate": "0/3"}
        outcomes = {"B1": _outcome("fable", "escalated-pass")}

        stats, notes = rs.live_tier_stats(tasks, outcomes, [applied_event])

        self.assertEqual(stats["sonnet"]["completed"], 1)
        self.assertEqual(stats["sonnet"]["first_try"], 0)
        self.assertEqual(stats["haiku"]["completed"], 0)
        self.assertEqual(stats["frontier"]["completed"], 0)
        self.assertEqual(notes, [])


# ---- 4. upgrade_decision properties --------------------------------------------------------------


class UpgradeDecisionTests(unittest.TestCase):
    def test_never_frontier_sweep(self):
        # Fixture 1: struggling opus, default knobs -- at_ceiling locks the upgrade.
        tasks1 = [
            _task("C1", status="done", model="opus"),
            _task("C2", status="done", model="opus"),
            _task("C3", status="done", model="opus"),
            _task("C4", status="pending", model="opus"),
        ]
        outcomes1 = {
            "C1": _outcome("opus", "blocked"), "C2": _outcome("opus", "blocked"),
            "C3": _outcome("opus", "blocked"),
        }
        dec1 = rs.upgrade_decision(tasks1, outcomes1, [])
        self.assertEqual(dec1["recommendations"], [])
        self.assertTrue(dec1["signals"]["opus"]["at_ceiling"])
        self.assertTrue(dec1["signals"]["opus"]["below_threshold"])
        self.assertTrue(any(n.startswith("frontier locked: escalation valve only")
                             for n in dec1["notes"]))

        # Fixture 2: struggling frontier (fable pins), default knobs.
        tasks2 = [
            _task("D1", status="done", model="fable"),
            _task("D2", status="done", model="fable"),
            _task("D3", status="done", model="fable"),
            _task("D4", status="pending", model="fable"),
        ]
        outcomes2 = {
            "D1": _outcome("fable", "blocked"), "D2": _outcome("fable", "blocked"),
            "D3": _outcome("fable", "blocked"),
        }
        dec2 = rs.upgrade_decision(tasks2, outcomes2, [])
        self.assertEqual(dec2["recommendations"], [])
        self.assertTrue(dec2["signals"]["frontier"]["at_ceiling"])

        # Fixture 3: mixed struggling haiku + sonnet -- both recommend, never frontier.
        tasks3 = [
            _task("E1", status="done", model="haiku"),
            _task("E2", status="done", model="haiku"),
            _task("E3", status="done", model="haiku"),
            _task("E4", status="pending", model="haiku"),
            _task("E5", status="done", model="sonnet"),
            _task("E6", status="done", model="sonnet"),
            _task("E7", status="done", model="sonnet"),
            _task("E8", status="pending", model="sonnet"),
        ]
        outcomes3 = {
            "E1": _outcome("haiku", "blocked"), "E2": _outcome("haiku", "blocked"),
            "E3": _outcome("haiku", "blocked"),
            "E5": _outcome("sonnet", "blocked"), "E6": _outcome("sonnet", "blocked"),
            "E7": _outcome("sonnet", "blocked"),
        }
        dec3 = rs.upgrade_decision(tasks3, outcomes3, [])
        tos3 = {r["to"] for r in dec3["recommendations"]}
        self.assertEqual(tos3, {"sonnet", "opus"})
        self.assertNotIn("frontier", tos3)

        # Fixture 4: tiny threshold/min_sample via kwargs -- still locked at the ceiling.
        tasks4 = [
            _task("F1", status="done", model="opus"),
            _task("F2", status="pending", model="opus"),
        ]
        outcomes4 = {"F1": _outcome("opus", "blocked")}
        dec4 = rs.upgrade_decision(tasks4, outcomes4, [], threshold=0.99, min_sample=1)
        self.assertEqual(dec4["recommendations"], [])
        self.assertTrue(dec4["signals"]["opus"]["at_ceiling"])
        self.assertTrue(dec4["signals"]["opus"]["below_threshold"])

        for dec in (dec1, dec2, dec3, dec4):
            self.assertFalse(any(r["to"] == "frontier" for r in dec["recommendations"]))

    def test_min_sample_gate(self):
        tasks_two = [
            _task("G1", status="done", model="sonnet"),
            _task("G2", status="done", model="sonnet"),
            _task("G3", status="pending", model="sonnet"),
        ]
        outcomes_two = {
            "G1": _outcome("sonnet", "blocked"), "G2": _outcome("sonnet", "blocked"),
        }
        dec_two = rs.upgrade_decision(tasks_two, outcomes_two, [])
        self.assertEqual(dec_two["recommendations"], [])
        self.assertFalse(dec_two["signals"]["sonnet"]["below_threshold"])

        tasks_three = tasks_two + [_task("G4", status="done", model="sonnet")]
        outcomes_three = dict(outcomes_two)
        outcomes_three["G4"] = _outcome("sonnet", "blocked")
        dec_three = rs.upgrade_decision(tasks_three, outcomes_three, [])
        self.assertEqual(len(dec_three["recommendations"]), 1)
        rec = dec_three["recommendations"][0]
        self.assertEqual((rec["from"], rec["to"]), ("sonnet", "opus"))
        self.assertEqual(rec["task_ids"], ["G3"])

    def test_threshold_boundary(self):
        tasks = [
            _task("H1", status="done", model="sonnet"),
            _task("H2", status="done", model="sonnet"),
            _task("H3", status="done", model="sonnet"),
            _task("H4", status="done", model="sonnet"),
            _task("H5", status="pending", model="sonnet"),
        ]
        # exactly AT threshold (0.5) never triggers -- strictly below required
        outcomes_at = {
            "H1": _outcome("sonnet", "pass"), "H2": _outcome("sonnet", "pass"),
            "H3": _outcome("sonnet", "blocked"), "H4": _outcome("sonnet", "blocked"),
        }
        dec_at = rs.upgrade_decision(tasks, outcomes_at, [])
        self.assertAlmostEqual(dec_at["signals"]["sonnet"]["rate"], 0.5, places=9)
        self.assertFalse(dec_at["signals"]["sonnet"]["below_threshold"])
        self.assertEqual(dec_at["recommendations"], [])

        # just under triggers
        outcomes_under = {
            "H1": _outcome("sonnet", "pass"), "H2": _outcome("sonnet", "blocked"),
            "H3": _outcome("sonnet", "blocked"), "H4": _outcome("sonnet", "blocked"),
        }
        dec_under = rs.upgrade_decision(tasks, outcomes_under, [])
        self.assertLess(dec_under["signals"]["sonnet"]["rate"], 0.5)
        self.assertTrue(dec_under["signals"]["sonnet"]["below_threshold"])
        self.assertEqual(len(dec_under["recommendations"]), 1)

        # zero completed -> rate is None, never treated as below threshold
        dec_zero = rs.upgrade_decision(tasks, {}, [])
        self.assertIsNone(dec_zero["signals"]["sonnet"]["rate"])
        self.assertFalse(dec_zero["signals"]["sonnet"]["below_threshold"])
        self.assertEqual(dec_zero["recommendations"], [])

    def test_upgrade_is_one_step_and_pending_only(self):
        tasks = [
            _task("I1", status="done", model="sonnet"),
            _task("I2", status="done", model="sonnet"),
            _task("I3", status="done", model="sonnet"),
            _task("I4", status="pending", model="sonnet"),
            _task("I5", status="in-progress", model="sonnet"),
            _task("I6", status="blocked", model="sonnet"),
            _task("I7", status="pending", model="sonnet"),
            _task("I8", status="pending", model="haiku"),  # different tier, irrelevant
        ]
        outcomes = {
            "I1": _outcome("sonnet", "blocked"), "I2": _outcome("sonnet", "blocked"),
            "I3": _outcome("sonnet", "blocked"),
        }
        dec = rs.upgrade_decision(tasks, outcomes, [])
        self.assertEqual(len(dec["recommendations"]), 1)
        rec = dec["recommendations"][0]
        self.assertEqual(rec["from"], "sonnet")
        self.assertEqual(rec["to"], "opus")  # exactly one rung, never skipping to frontier
        self.assertEqual(rec["task_ids"], ["I4", "I7"])  # pending only, TASKS.md order
        for excluded in ("I1", "I2", "I3", "I5", "I6", "I8"):
            self.assertNotIn(excluded, rec["task_ids"])

    def test_effective_pin_shift(self):
        tasks = [
            _task("J1", status="pending", model="haiku"),  # re-routed to sonnet below
            _task("J2", status="done", model="haiku"),
            _task("J3", status="done", model="haiku"),
            _task("J4", status="done", model="haiku"),
            _task("J5", status="done", model="sonnet"),
            _task("J6", status="done", model="sonnet"),
            _task("J7", status="done", model="sonnet"),
        ]
        outcomes = {
            "J2": _outcome("haiku", "blocked"), "J3": _outcome("haiku", "blocked"),
            "J4": _outcome("haiku", "blocked"),
            "J5": _outcome("sonnet", "blocked"), "J6": _outcome("sonnet", "blocked"),
            "J7": _outcome("sonnet", "blocked"),
        }
        events = [{"from": "haiku", "to": "sonnet", "mode": "applied",
                   "tasks": ["J1"], "rate": "0/3"}]
        dec = rs.upgrade_decision(tasks, outcomes, events)

        by_from = {r["from"]: r for r in dec["recommendations"]}
        # J1's effective dispatch tier is now sonnet -- it converges to no-op for haiku.
        self.assertNotIn("haiku", by_from)
        self.assertIn("sonnet", by_from)
        self.assertIn("J1", by_from["sonnet"]["task_ids"])
        self.assertTrue(any(n == "no pending haiku tasks to upgrade"
                             for n in dec["notes"]))

    def test_budget_counting(self):
        advisory_events = [
            {"from": "sonnet", "to": "opus", "mode": "advisory", "tasks": [], "rate": None},
            {"from": "sonnet", "to": "opus", "mode": "advisory", "tasks": [], "rate": None},
            {"from": "sonnet", "to": "opus", "mode": "advisory", "tasks": [], "rate": None},
        ]
        dec = rs.upgrade_decision([], {}, advisory_events)
        self.assertEqual(dec["budget"], {
            "cap": rs.LIVE_MAX_AUTO_UPGRADES, "applied": 0,
            "remaining": rs.LIVE_MAX_AUTO_UPGRADES,
        })

        one_applied = [{"from": "haiku", "to": "sonnet", "mode": "applied",
                         "tasks": [], "rate": "0/3"}]
        dec1 = rs.upgrade_decision([], {}, one_applied)
        self.assertEqual(dec1["budget"]["applied"], 1)
        self.assertEqual(dec1["budget"]["remaining"], rs.LIVE_MAX_AUTO_UPGRADES - 1)

        # exhaust the budget; recommendations must still be listed
        two_applied = one_applied + [{"from": "sonnet", "to": "opus", "mode": "applied",
                                       "tasks": [], "rate": "0/3"}]
        struggling_tasks = [
            _task("K1", status="done", model="sonnet"),
            _task("K2", status="done", model="sonnet"),
            _task("K3", status="done", model="sonnet"),
            _task("K4", status="pending", model="sonnet"),
        ]
        struggling_outcomes = {
            "K1": _outcome("sonnet", "blocked"), "K2": _outcome("sonnet", "blocked"),
            "K3": _outcome("sonnet", "blocked"),
        }
        dec2 = rs.upgrade_decision(struggling_tasks, struggling_outcomes, two_applied)
        self.assertEqual(dec2["budget"], {
            "cap": rs.LIVE_MAX_AUTO_UPGRADES, "applied": 2, "remaining": 0,
        })
        self.assertEqual(len(dec2["recommendations"]), 1)
        self.assertTrue(any(n == "auto-upgrade budget exhausted — advisory only"
                             for n in dec2["notes"]))


# ---- 5. CLI end-to-end ----------------------------------------------------------------------


class CliLiveEndToEndTests(unittest.TestCase):
    def test_cli_live_json_keys(self):
        with tempfile.TemporaryDirectory() as td:
            kit_dir = write_kit(Path(td), REROUTE_TASKS_MD, notes_md=REROUTE_NOTES_MD)
            kits_root = kit_dir.parent
            result = _run_cli(["kit", "--kits-dir", str(kits_root), "--live", "--json"])

        self.assertEqual(result.returncode, 0, result.stderr)
        card = json.loads(result.stdout)
        self.assertEqual(set(card), {
            "schema_version", "kit", "generated_at", "autonomy",
            "signals", "recommendations", "budget", "notes",
        })
        self.assertEqual(card["schema_version"], 1)
        self.assertEqual(card["kit"], "kit")
        self.assertEqual(card["autonomy"], "advisory")

        s = card["signals"]["sonnet"]
        self.assertEqual((s["completed"], s["first_try"]), (3, 1))
        self.assertTrue(s["below_threshold"])
        self.assertAlmostEqual(s["rate"], 1 / 3, places=9)

        self.assertEqual(len(card["recommendations"]), 1)
        rec = card["recommendations"][0]
        self.assertEqual((rec["from"], rec["to"]), ("sonnet", "opus"))
        self.assertEqual(rec["task_ids"], ["K4"])
        self.assertEqual(card["budget"], {"cap": 2, "applied": 0, "remaining": 2})

        with tempfile.TemporaryDirectory() as td2:
            kit_dir2 = write_kit(Path(td2), REROUTE_TASKS_MD, notes_md=REROUTE_NOTES_MD)
            kits_root2 = kit_dir2.parent
            md_result = _run_cli(["kit", "--kits-dir", str(kits_root2), "--live"])

        self.assertEqual(md_result.returncode, 0, md_result.stderr)
        self.assertIn("# Live re-route signal —", md_result.stdout)
        self.assertIn("autonomy: advisory", md_result.stdout)
        self.assertIn("budget:", md_result.stdout)
        self.assertTrue("recommend:" in md_result.stdout
                         or "no re-route recommended" in md_result.stdout)

    def test_cli_live_missing_notes_and_plan(self):
        with tempfile.TemporaryDirectory() as td:
            kit_dir = write_kit(Path(td), REROUTE_TASKS_MD)  # TASKS.md only
            kits_root = kit_dir.parent
            result = _run_cli(["kit", "--kits-dir", str(kits_root), "--live", "--json"])

        self.assertEqual(result.returncode, 0, result.stderr)
        card = json.loads(result.stdout)
        self.assertEqual(card["recommendations"], [])
        self.assertEqual(card["autonomy"], "advisory")
        self.assertTrue(any("no NOTES.md" in n for n in card["notes"]))

        with tempfile.TemporaryDirectory() as td2:
            kit_dir2 = write_kit(Path(td2), REROUTE_TASKS_MD, notes_md=REROUTE_NOTES_MD,
                                  plan_md=PLAN_AUTO_MD)
            kits_root2 = kit_dir2.parent
            result2 = _run_cli(["kit", "--kits-dir", str(kits_root2), "--live", "--json"])

        self.assertEqual(result2.returncode, 0, result2.stderr)
        card2 = json.loads(result2.stdout)
        self.assertEqual(card2["autonomy"], "auto")

    def test_cli_live_rejects_session(self):
        with tempfile.TemporaryDirectory() as td:
            kit_dir = write_kit(Path(td), REROUTE_TASKS_MD)
            kits_root = kit_dir.parent
            result = _run_cli(["kit", "--kits-dir", str(kits_root), "--live",
                                "--session", "some-session"])

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--session", result.stderr)

    def test_cli_live_knob_flags(self):
        with tempfile.TemporaryDirectory() as td:
            kit_dir = write_kit(Path(td), KNOB_TASKS_MD, notes_md=KNOB_NOTES_MD)
            kits_root = kit_dir.parent
            default_result = _run_cli(
                ["kit", "--kits-dir", str(kits_root), "--live", "--json"])
            knob_result = _run_cli(
                ["kit", "--kits-dir", str(kits_root), "--live", "--json",
                 "--live-min-sample", "1"])

        self.assertEqual(default_result.returncode, 0, default_result.stderr)
        self.assertEqual(knob_result.returncode, 0, knob_result.stderr)
        default_card = json.loads(default_result.stdout)
        knob_card = json.loads(knob_result.stdout)
        self.assertEqual(default_card["recommendations"], [])
        self.assertEqual(len(knob_card["recommendations"]), 1)
        self.assertEqual(knob_card["recommendations"][0]["task_ids"], ["M2"])

        with tempfile.TemporaryDirectory() as td2:
            kit_dir2 = write_kit(Path(td2), KNOB_TASKS_MD, notes_md=KNOB_NOTES_MD)
            kits_root2 = kit_dir2.parent
            cap_result = _run_cli(
                ["kit", "--kits-dir", str(kits_root2), "--live", "--json",
                 "--live-max-auto", "0"])

        self.assertEqual(cap_result.returncode, 0, cap_result.stderr)
        cap_card = json.loads(cap_result.stdout)
        self.assertEqual(cap_card["budget"]["remaining"], 0)
        self.assertTrue(any("auto-upgrade budget exhausted" in n
                             for n in cap_card["notes"]))

    def test_demo_live_pinned_numbers(self):
        j = _run_cli(["--demo", "--live", "--json"])
        self.assertEqual(j.returncode, 0, j.stderr)
        d = json.loads(j.stdout)
        self.assertEqual(d["autonomy"], "advisory")
        s = d["signals"]["sonnet"]
        self.assertEqual((s["completed"], s["first_try"]), (3, 1))
        self.assertTrue(s["below_threshold"])
        recs = d["recommendations"]
        self.assertEqual(len(recs), 1)
        self.assertEqual((recs[0]["from"], recs[0]["to"]), ("sonnet", "opus"))
        self.assertEqual(recs[0]["task_ids"], ["L5", "L6"])
        self.assertEqual(d["budget"], {"cap": 2, "applied": 0, "remaining": 2})

        m = _run_cli(["--demo", "--live"])
        self.assertEqual(m.returncode, 0, m.stderr)
        for needle in ("# Live re-route signal —", "autonomy: advisory",
                       "- sonnet: first-try 1/3", "recommend: sonnet → opus — tasks L5, L6",
                       "budget: 0/2 auto-upgrades applied"):
            self.assertIn(needle, m.stdout)

    def test_tier1_demo_regression(self):
        result = _run_cli(["--demo", "--json"])
        self.assertEqual(result.returncode, 0, result.stderr)
        card = json.loads(result.stdout)
        q = card["quality"]
        self.assertEqual(
            (q["total"], q["with_outcome"], q["first_try_pass"], q["retry_pass"],
             q["escalated_pass"], q["blocked"]), (6, 6, 3, 1, 1, 1))
        self.assertEqual(card["model_mix"], {"haiku": 1, "sonnet": 4, "fable": 1})
        self.assertAlmostEqual(card["review"]["survival_rate"], 0.75, places=9)


# ---- 6. safety proofs -----------------------------------------------------------------------


class SafetyProofTests(unittest.TestCase):
    def test_pricing_free_live_path(self):
        original = rs.cr.load_pricing

        def _boom():
            raise RuntimeError("the --live path must never load pricing")

        rs.cr.load_pricing = _boom
        try:
            with tempfile.TemporaryDirectory() as td:
                kit_dir = write_kit(Path(td), REROUTE_TASKS_MD, notes_md=REROUTE_NOTES_MD)
                kits_root = kit_dir.parent
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = rs.main(["kit", "--live", "--kits-dir", str(kits_root), "--json"])
            self.assertEqual(rc, 0)
            card = json.loads(buf.getvalue())
            self.assertEqual(card["schema_version"], 1)
        finally:
            rs.cr.load_pricing = original

    def test_readonly_live_run(self):
        with tempfile.TemporaryDirectory() as td:
            kit_dir = write_kit(Path(td), REROUTE_TASKS_MD, notes_md=REROUTE_NOTES_MD)
            kits_root = kit_dir.parent

            def snapshot():
                files = sorted(p for p in kit_dir.rglob("*") if p.is_file())
                return [str(p) for p in files], {str(p): p.read_bytes() for p in files}

            before_paths, before_bytes = snapshot()
            result = _run_cli(["kit", "--kits-dir", str(kits_root), "--live", "--json"])
            after_paths, after_bytes = snapshot()

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(before_paths, after_paths)
            self.assertEqual(before_bytes, after_bytes)


if __name__ == "__main__":
    unittest.main()
