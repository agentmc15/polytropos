"""Stdlib unittest regression suite for the per-task dollar breakdown (``--by-task``) in
bin/routing_scorecard.py (per-task-dollars T2).

SAFETY CONTRACT (binds every test in this file): no test here ever reads the real Claude
Code project store or resolves the caller's real home directory via the stdlib home
helper -- this file never calls it, and it never spells out the real projects path as a
literal string. Every kit fixture (TASKS.md / NOTES.md) is written into a fresh
`tempfile.TemporaryDirectory()` and handed to the CLI or the pure functions via an
explicit `--kits-dir` / `--projects-dir` / `--tasks-dir` or an explicit path -- never a
bare run against real dirs. All ids/values in every fixture are synthetic; the only model
tokens anywhere in this file are the sanctioned tier vocabulary
(`haiku`/`sonnet`/`opus`/`frontier`) plus the `fable` Agent-tool alias, EXCEPT the
dollar-fixture transcript model ids, which are computed at run time from
`rs.cr.load_pricing()` + `rs._first_model_of_tier` -- never a spelled model id. Every
dollar comparison below goes through `price_of()`, which drives the REUSED
`rs.sc.collect()` pricing pipeline -- never a hand-computed figure.

bin/ is not a package; routing_scorecard.py is loaded via importlib by absolute path
computed from this file's own location (BIN_DIR), mirroring tests/test_routing_scorecard.py,
tests/test_reroute_live.py, and tests/test_routing_history.py.
"""

import importlib.util
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


def write_transcript(path, messages):
    """Write a synthetic transcript JSONL at the exact given ``path``.

    ``messages`` is a list of dicts ``{"model", "id", "input_tokens", "output_tokens"}``;
    the JSONL shape mirrors ``run_demo``'s transcript fixtures (``{"timestamp",
    "message": {"model", "id", "usage": {...}}}``). Used both for
    ``projects/<slug>/<session>.jsonl`` main transcripts and for
    ``tasks/<agent-id>.output`` subagent transcripts -- same shape, caller picks the path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
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
    path.write_text("\n".join(lines) + "\n")
    return path


def price_of(files):
    """Reference price for a list of transcript files via the REUSED ``sc.collect``
    pipeline -- every dollar comparison in this file goes through this helper, never a
    hand-computed figure. ``None`` when nothing could be read (mirrors ``build_by_task``'s
    own ``price_path``)."""
    pricing = rs.cr.load_pricing()
    data = rs.sc.collect(list(files), pricing)
    if data["files_read"] == 0:
        return None
    return sum(b["cost"] for b in data["by_model"].values())


def _run_cli(args):
    """subprocess.run the real CLI from the repo root (never the dotted-module form)."""
    return subprocess.run(
        [sys.executable, "bin/routing_scorecard.py"] + args,
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )


# ---- kit fixtures (spaced em dash headings, pinned outcome:/agent: grammars) -------------------

SOLO_TASKS_MD = """# TASKS — solo-kit (synthetic)

## Phase 1 — only phase

### S1 — a sonnet task
- status: done
- model: sonnet
"""

SOLO_NOTES_MD = """# NOTES — solo-kit (synthetic)

## Outcome ledger
outcome: S1 model=sonnet attempts=1 result=pass review=clean
"""

SOLO_AGENT_NOTES_MD = """# NOTES — solo-kit (synthetic)

## Outcome ledger
outcome: S1 model=sonnet attempts=1 result=pass review=clean

## Agent ledger
agent: S1 id=ag-s1-impl role=implementer model=sonnet
"""

ORCH_TASKS_MD = """# TASKS — orch-kit (synthetic)

## Phase 1 — only phase

### C1 — a sonnet task with a recorded implementer
- status: done
- model: sonnet
"""

ORCH_NOTES_MD = """# NOTES — orch-kit (synthetic)

## Outcome ledger
outcome: C1 model=sonnet attempts=1 result=pass review=clean

## Agent ledger
agent: C1 id=impl-x role=implementer model=sonnet
"""

OVERLAP_TASKS_MD = """# TASKS — overlap-kit (synthetic)

## Phase 1 — only phase

### E1 — a sonnet task whose implementer transcript overlaps the main session
- status: done
- model: sonnet
"""

OVERLAP_NOTES_MD = """# NOTES — overlap-kit (synthetic)

## Outcome ledger
outcome: E1 model=sonnet attempts=1 result=pass review=clean

## Agent ledger
agent: E1 id=impl-a role=implementer model=sonnet
"""

RO_TASKS_MD = """# TASKS — readonly-bt-kit (synthetic)

## Phase 1 — only phase

### RO1 — a task exercising the by-task read-only proof
- status: done
- model: sonnet
"""

RO_NOTES_MD = """# NOTES — readonly-bt-kit (synthetic)

## Outcome ledger
outcome: RO1 model=sonnet attempts=1 result=pass review=clean

## Agent ledger
agent: RO1 id=ag-ro-impl role=implementer model=sonnet
"""


# ---- 1/2. parse_agents ---------------------------------------------------------------------


class ParseAgentsTests(unittest.TestCase):
    def test_parse_agents_happy_and_tolerant(self):
        text = "\n".join([
            "agent: T1 id=a1 role=implementer model=sonnet",
            "- agent: T1 id=a2 role=verifier",                 # bullet, no model= -> None
            "* agent: T2 id=a1 role=implementer model=sonnet extra=ignore-me",  # bullet + junk pair
            "agent: T3 id=a3 role=chef model=sonnet",          # role outside AGENT_ROLES -> skip
            "agent: T4 role=implementer model=sonnet",         # missing id= -> skip
            "",
        ])
        events, notes = rs.parse_agents(text)

        self.assertEqual(
            [(e["task"], e["agent_id"], e["role"]) for e in events],
            [("T1", "a1", "implementer"), ("T1", "a2", "verifier"), ("T2", "a1", "implementer")])
        # events preserve file order
        self.assertEqual(events[0]["model"], "sonnet")
        self.assertIsNone(events[1]["model"])   # model= absent -> None, never validated
        self.assertEqual(events[2]["model"], "sonnet")
        # unknown key=value pairs are ignored, never surfaced on the event
        self.assertNotIn("extra", events[2])
        # two tolerant skips (bad role, missing id) each produce a note
        self.assertEqual(sum(1 for n in notes if "unrecognized agent line" in n), 2)

    def test_parse_agents_last_wins_per_pair(self):
        text = "\n".join([
            "agent: T1 id=a1 role=implementer model=sonnet",
            "agent: T1 id=a2 role=verifier model=sonnet",
            "agent: T1 id=a1 role=implementer model=opus",   # re-run: last wins for (T1, a1)
            "agent: T1 id=a3 role=escalation model=fable",
        ])
        events, notes = rs.parse_agents(text)
        self.assertEqual(notes, [])

        # exactly one event for the repeated (T1, a1) pair, carrying the LAST line's value
        a1_events = [e for e in events if e["agent_id"] == "a1"]
        self.assertEqual(len(a1_events), 1)
        self.assertEqual(a1_events[0]["model"], "opus")
        # the first occurrence's position is kept -- a1 stays first in file order
        self.assertEqual([e["agent_id"] for e in events], ["a1", "a2", "a3"])
        # distinct agent ids on the same task all survive (retry/verifier/escalation case)
        self.assertEqual({e["agent_id"] for e in events if e["task"] == "T1"}, {"a1", "a2", "a3"})


# ---- 3. parser family disjointness ------------------------------------------------------------


class ParserFamilyDisjointTests(unittest.TestCase):
    def test_parser_family_disjoint(self):
        text = "\n".join([
            "outcome: T1 model=sonnet attempts=1 result=pass review=clean",
            "reroute: sonnet to=opus mode=advisory tasks=T1 rate=0/1",
            "session: abc-session",
            "agent: T1 id=a1 role=implementer model=sonnet",
        ])
        outcomes, _ = rs.parse_outcomes(text)
        reroutes, _ = rs.parse_reroutes(text)
        sessions, _ = rs.parse_sessions(text)
        agents, _ = rs.parse_agents(text)

        self.assertEqual(set(outcomes), {"T1"})
        self.assertEqual(len(reroutes), 1)
        self.assertEqual(sessions, ["abc-session"])
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["agent_id"], "a1")

        # parse_agents sees NONE of the other three families' lines
        agents_only, _ = rs.parse_agents(
            "outcome: T1 model=sonnet result=pass\n"
            "reroute: sonnet to=opus mode=advisory tasks=T1 rate=0/1\n"
            "session: abc-session\n")
        self.assertEqual(agents_only, [])

        # and none of the other three families see an agent: line
        outcomes_only, _ = rs.parse_outcomes("agent: T1 id=a1 role=implementer model=sonnet\n")
        self.assertEqual(outcomes_only, {})
        reroutes_only, _ = rs.parse_reroutes("agent: T1 id=a1 role=implementer model=sonnet\n")
        self.assertEqual(reroutes_only, [])
        sessions_only, _ = rs.parse_sessions("agent: T1 id=a1 role=implementer model=sonnet\n")
        self.assertEqual(sessions_only, [])


# ---- 4. discover_agent_outputs -----------------------------------------------------------------


class DiscoverAgentOutputsTests(unittest.TestCase):
    def test_discover_agent_outputs_stem_mapping(self):
        pricing = rs.cr.load_pricing()
        model_id = rs._first_model_of_tier(pricing, "sonnet")
        self.assertIsNotNone(model_id)

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dir_a = tmp / "tasks-a"
            dir_b = tmp / "tasks-b"
            dir_a.mkdir()
            dir_b.mkdir()

            msg = lambda mid: {"model": model_id, "id": mid,
                               "input_tokens": 100, "output_tokens": 10}
            write_transcript(dir_a / "zeta.output", [msg("m1")])
            write_transcript(dir_a / "alpha.output", [msg("m2")])
            # duplicate stem across two dirs -- the FIRST dir seen wins
            write_transcript(dir_b / "alpha.output", [msg("m3")])
            write_transcript(dir_b / "beta.output", [msg("m4")])
            (dir_a / "notes.txt").write_text("not a transcript")  # non-.output ignored

            mapping, notes = rs.discover_agent_outputs([dir_a, dir_b])

        self.assertEqual(set(mapping), {"zeta", "alpha", "beta"})
        self.assertEqual(mapping["alpha"], dir_a / "alpha.output")   # first dir wins
        # sorted-glob-per-dir order is deterministic: dir_a's alpha,zeta then dir_b's beta
        self.assertEqual(list(mapping), ["alpha", "zeta", "beta"])
        self.assertTrue(any("duplicate agent transcript" in n and "alpha" in n for n in notes))

        # a dir that does not exist is noted once, never crashes
        mapping2, notes2 = rs.discover_agent_outputs([Path(td) / "does-not-exist"])
        self.assertEqual(mapping2, {})
        self.assertTrue(any("tasks dir not found" in n for n in notes2))


# ---- 5. build_by_task prices each output standalone --------------------------------------------


class BuildByTaskPricingTests(unittest.TestCase):
    def test_by_task_prices_each_output_standalone(self):
        pricing = rs.cr.load_pricing()
        haiku_id = rs._first_model_of_tier(pricing, "haiku")
        sonnet_id = rs._first_model_of_tier(pricing, "sonnet")
        opus_id = rs._first_model_of_tier(pricing, "opus")
        self.assertTrue(haiku_id and sonnet_id and opus_id)

        with tempfile.TemporaryDirectory() as td:
            tasks_dir = Path(td) / "tasks"
            tasks_dir.mkdir()
            impl1 = write_transcript(tasks_dir / "impl-a.output", [
                {"model": haiku_id, "id": "m1", "input_tokens": 50000, "output_tokens": 2000}])
            impl2 = write_transcript(tasks_dir / "impl-b.output", [
                {"model": sonnet_id, "id": "m2", "input_tokens": 70000, "output_tokens": 3000}])
            verif = write_transcript(tasks_dir / "verif-a.output", [
                {"model": opus_id, "id": "m3", "input_tokens": 20000, "output_tokens": 1000}])

            output_map, _ = rs.discover_agent_outputs([tasks_dir])

            tasks = [{"id": "A1"}]
            events = [
                {"task": "A1", "agent_id": "impl-a", "role": "implementer", "model": "haiku"},
                {"task": "A1", "agent_id": "impl-b", "role": "implementer", "model": "sonnet"},
                {"task": "A1", "agent_id": "verif-a", "role": "verifier", "model": "opus"},
            ]
            bt = rs.build_by_task(tasks, events, output_map, None, None, pricing)

            # reference prices computed via the reused pipeline WHILE the temp files still
            # exist (price_of re-reads the files -- it must run before the tempdir is gone)
            ref_impl1 = price_of([impl1])
            ref_impl2 = price_of([impl2])
            ref_verif = price_of([verif])

        row = bt["tasks"][0]
        impl_agents = {a["agent_id"]: a["cost_usd"] for a in row["roles"]["implementer"]["agents"]}
        self.assertAlmostEqual(impl_agents["impl-a"], ref_impl1, places=9)
        self.assertAlmostEqual(impl_agents["impl-b"], ref_impl2, places=9)
        verif_agent = row["roles"]["verifier"]["agents"][0]
        self.assertAlmostEqual(verif_agent["cost_usd"], ref_verif, places=9)

        # role subtotal = sum of that role's priced agents
        self.assertAlmostEqual(
            row["roles"]["implementer"]["subtotal_usd"],
            impl_agents["impl-a"] + impl_agents["impl-b"], places=9)
        # task total = sum over ALL priced agents across every role
        self.assertAlmostEqual(
            row["total_usd"],
            impl_agents["impl-a"] + impl_agents["impl-b"] + verif_agent["cost_usd"], places=9)


# ---- 6. missing transcript -> null, never zero --------------------------------------------------


class MissingTranscriptTests(unittest.TestCase):
    def test_missing_transcript_null_never_zero(self):
        pricing = rs.cr.load_pricing()
        tasks = [{"id": "A1"}]
        events = [{"task": "A1", "agent_id": "ghost", "role": "implementer", "model": "sonnet"}]
        bt = rs.build_by_task(tasks, events, {}, None, None, pricing)  # empty output_map

        row = bt["tasks"][0]
        self.assertIsNone(row["total_usd"])            # never 0.0
        self.assertEqual(row["missing_agents"], ["ghost"])
        self.assertIsNone(row["roles"]["implementer"]["subtotal_usd"])
        agent = row["roles"]["implementer"]["agents"][0]
        self.assertIsNone(agent["cost_usd"])
        self.assertTrue(any("ghost" in n for n in bt["notes"]))
        self.assertEqual(bt["coverage"], "partial")
        # no fabricated 0.0 stand-in anywhere in the serialized by-task JSON
        self.assertNotIn("0.0", json.dumps(bt))


# ---- 7. shared warm agent never split ------------------------------------------------------------


class SharedWarmAgentTests(unittest.TestCase):
    def test_shared_warm_agent_not_split(self):
        pricing = rs.cr.load_pricing()
        sonnet_id = rs._first_model_of_tier(pricing, "sonnet")
        haiku_id = rs._first_model_of_tier(pricing, "haiku")
        self.assertTrue(sonnet_id and haiku_id)

        with tempfile.TemporaryDirectory() as td:
            tasks_dir = Path(td) / "tasks"
            tasks_dir.mkdir()
            warm = write_transcript(tasks_dir / "ag-warm.output", [
                {"model": sonnet_id, "id": "wm1",
                 "input_tokens": 300000, "output_tokens": 15000}])
            solo = write_transcript(tasks_dir / "ag-solo.output", [
                {"model": haiku_id, "id": "sm1", "input_tokens": 40000, "output_tokens": 2000}])
            main = write_transcript(Path(td) / "main.jsonl", [
                {"model": sonnet_id, "id": "mm1", "input_tokens": 10000, "output_tokens": 500}])

            output_map, _ = rs.discover_agent_outputs([tasks_dir])

            tasks = [{"id": "B1"}, {"id": "B2"}]
            events = [
                {"task": "B1", "agent_id": "ag-warm", "role": "implementer", "model": "sonnet"},
                {"task": "B2", "agent_id": "ag-warm", "role": "implementer", "model": "sonnet"},
                {"task": "B2", "agent_id": "ag-solo", "role": "verifier", "model": "haiku"},
            ]
            bt = rs.build_by_task(tasks, events, output_map, main, None, pricing)

            # reference prices via the reused pipeline WHILE the temp files still exist
            ref_warm = price_of([warm])
            ref_solo = price_of([solo])
            ref_main = price_of([main])

        rows = {r["id"]: r for r in bt["tasks"]}

        # exactly one cluster row, carrying the FULL single-file price
        self.assertEqual(len(bt["clusters"]), 1)
        cl = bt["clusters"][0]
        self.assertEqual(cl["agent_id"], "ag-warm")
        self.assertEqual(cl["task_ids"], ["B1", "B2"])
        self.assertEqual(cl["roles"], ["implementer"])
        self.assertAlmostEqual(cl["cost_usd"], ref_warm, places=9)

        # NEITHER task row includes any share of the shared transcript
        self.assertEqual(rows["B1"]["roles"], {})
        self.assertIsNone(rows["B1"]["total_usd"])
        self.assertEqual(rows["B1"]["shared_agent_ids"], ["ag-warm"])
        self.assertEqual(rows["B2"]["shared_agent_ids"], ["ag-warm"])
        self.assertNotIn("implementer", rows["B2"]["roles"])   # ag-warm excluded from B2 too
        self.assertIn("verifier", rows["B2"]["roles"])         # ag-solo still counted normally

        # nothing lost, nothing divided: no unattributed files exist here
        self.assertEqual(bt["unattributed"]["count"], 0)
        total_parts = (bt["orchestrator"]["cost_usd"]
                       + rows["B2"]["total_usd"]
                       + cl["cost_usd"])
        expected = ref_main + ref_solo + ref_warm
        self.assertAlmostEqual(total_parts, expected, places=9)


# ---- 8. orchestrator never split ------------------------------------------------------------


class OrchestratorNeverSplitTests(unittest.TestCase):
    def test_orchestrator_never_split(self):
        pricing = rs.cr.load_pricing()
        sonnet_id = rs._first_model_of_tier(pricing, "sonnet")
        self.assertIsNotNone(sonnet_id)

        # --- pure-function half: the main price appears ONLY in orchestrator ---
        with tempfile.TemporaryDirectory() as td:
            tasks_dir = Path(td) / "tasks"
            tasks_dir.mkdir()
            impl = write_transcript(tasks_dir / "impl-a.output", [
                {"model": sonnet_id, "id": "im1", "input_tokens": 10000, "output_tokens": 500}])
            main = write_transcript(Path(td) / "main.jsonl", [
                {"model": sonnet_id, "id": "mm1",
                 "input_tokens": 500000, "output_tokens": 20000}])
            output_map, _ = rs.discover_agent_outputs([tasks_dir])
            tasks = [{"id": "C1"}]
            events = [{"task": "C1", "agent_id": "impl-a", "role": "implementer", "model": "sonnet"}]

            bt = rs.build_by_task(tasks, events, output_map, main, None, pricing)
            main_price = price_of([main])
            self.assertAlmostEqual(bt["orchestrator"]["cost_usd"], main_price, places=9)
            self.assertEqual(bt["clusters"], [])
            row = bt["tasks"][0]
            impl_cost = row["roles"]["implementer"]["agents"][0]["cost_usd"]
            self.assertNotAlmostEqual(impl_cost, main_price, places=6)
            self.assertNotAlmostEqual(row["total_usd"], main_price, places=6)

            bt_no_main = rs.build_by_task(tasks, events, output_map, None, None, pricing)
        self.assertIsNone(bt_no_main["orchestrator"]["cost_usd"])
        self.assertTrue(any("main transcript not found" in n for n in bt_no_main["notes"]))

        # --- CLI half: main transcript absent from the projects dir -> None + note, AND the
        # whole-kit Dollars block degrades exactly as it does today, unchanged by the flag ---
        with tempfile.TemporaryDirectory() as td2:
            kits_root = Path(td2) / "kits"
            write_kit(kits_root, "orch-kit", ORCH_TASKS_MD, ORCH_NOTES_MD)
            projects_root = Path(td2) / "projects"
            projects_root.mkdir()
            tasks_dir2 = Path(td2) / "tasks"
            tasks_dir2.mkdir()
            write_transcript(tasks_dir2 / "impl-x.output", [
                {"model": sonnet_id, "id": "ix1", "input_tokens": 8000, "output_tokens": 400}])

            result = _run_cli(["orch-kit", "--kits-dir", str(kits_root),
                               "--session", "no-such-session",
                               "--projects-dir", str(projects_root),
                               "--tasks-dir", str(tasks_dir2), "--by-task", "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            card = json.loads(result.stdout)

        self.assertIsNone(card["cost"])   # whole-kit dollars degrade exactly like today
        self.assertTrue(any("no transcript for session" in n for n in card["notes"]))
        self.assertIsNone(card["by_task"]["orchestrator"]["cost_usd"])
        self.assertTrue(any("main transcript not found" in n for n in card["by_task"]["notes"]))


# ---- 9. unattributed + unknown task id lines ----------------------------------------------------


class UnattributedTests(unittest.TestCase):
    def test_unattributed_and_unknown_task_lines(self):
        pricing = rs.cr.load_pricing()
        sonnet_id = rs._first_model_of_tier(pricing, "sonnet")
        self.assertIsNotNone(sonnet_id)

        with tempfile.TemporaryDirectory() as td:
            tasks_dir = Path(td) / "tasks"
            tasks_dir.mkdir()
            write_transcript(tasks_dir / "impl-a.output", [
                {"model": sonnet_id, "id": "i1", "input_tokens": 10000, "output_tokens": 500}])
            reviewer = write_transcript(tasks_dir / "ag-reviewer.output", [
                {"model": sonnet_id, "id": "r1", "input_tokens": 20000, "output_tokens": 800}])
            ghost = write_transcript(tasks_dir / "ag-unknown-task.output", [
                {"model": sonnet_id, "id": "g1", "input_tokens": 5000, "output_tokens": 200}])
            output_map, _ = rs.discover_agent_outputs([tasks_dir])

            tasks = [{"id": "D1"}]
            events = [
                {"task": "D1", "agent_id": "impl-a", "role": "implementer", "model": "sonnet"},
                {"task": "ZZZ", "agent_id": "ag-unknown-task", "role": "implementer",
                 "model": "sonnet"},
            ]
            bt = rs.build_by_task(tasks, events, output_map, None, None, pricing)

            # reference prices via the reused pipeline WHILE the temp files still exist
            expected_ua = price_of([reviewer]) + price_of([ghost])

        # ag-reviewer (referenced by no line) AND ag-unknown-task (referenced only by a
        # dropped unknown-task-id line) both land in unattributed, never on a task
        self.assertEqual(bt["unattributed"]["count"], 2)
        self.assertEqual(bt["unattributed"]["agent_ids"], ["ag-reviewer", "ag-unknown-task"])
        self.assertAlmostEqual(bt["unattributed"]["cost_usd"], expected_ua, places=9)

        # the unknown-task-id line is dropped with a note, never silently promoted to a task
        self.assertTrue(any("unknown task id" in n and "ZZZ" in n for n in bt["notes"]))
        self.assertEqual([r["id"] for r in bt["tasks"]], ["D1"])   # no phantom ZZZ row


# ---- 10. zero agent: lines degrades to n/a -----------------------------------------------------


class NoAgentLinesTests(unittest.TestCase):
    def test_no_agent_lines_degrades_na(self):
        pricing = rs.cr.load_pricing()
        sonnet_id = rs._first_model_of_tier(pricing, "sonnet")
        self.assertIsNotNone(sonnet_id)

        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            write_kit(kits_root, "solo", SOLO_TASKS_MD, SOLO_NOTES_MD)  # no agent: lines
            projects_root = Path(td) / "projects"
            write_transcript(projects_root / "-t" / "solo-sess.jsonl", [
                {"model": sonnet_id, "id": "m1", "input_tokens": 1000, "output_tokens": 100}])
            tasks_dir = Path(td) / "tasks"
            tasks_dir.mkdir()
            # a *.output file IS present -- the zero-events rung must not enumerate it
            write_transcript(tasks_dir / "some-agent.output", [
                {"model": sonnet_id, "id": "m2", "input_tokens": 500, "output_tokens": 50}])

            result = _run_cli(["solo", "--kits-dir", str(kits_root), "--session", "solo-sess",
                               "--projects-dir", str(projects_root),
                               "--tasks-dir", str(tasks_dir), "--by-task", "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            card = json.loads(result.stdout)

            md_result = _run_cli(["solo", "--kits-dir", str(kits_root), "--session", "solo-sess",
                                  "--projects-dir", str(projects_root),
                                  "--tasks-dir", str(tasks_dir), "--by-task"])
            self.assertEqual(md_result.returncode, 0, md_result.stderr)

        bt = card["by_task"]
        self.assertIsNone(bt["coverage"])
        self.assertEqual(bt["tasks"], [])
        self.assertEqual(bt["clusters"], [])
        self.assertEqual(bt["unattributed"], {"count": 0, "cost_usd": None, "agent_ids": []})
        self.assertTrue(any("no agent: lines recorded" in n for n in bt["notes"]))

        # the whole-kit dollars above are untouched by the flag
        self.assertIsNotNone(card["cost"])
        self.assertGreater(card["cost"]["actual_usd"], 0)

        self.assertIn(
            "n/a — no agent: lines recorded in NOTES.md", md_result.stdout)


# ---- 11. reconciliation note on parts-vs-whole overlap -------------------------------------------


class ReconciliationTests(unittest.TestCase):
    def test_reconciliation_note_on_overlap(self):
        pricing = rs.cr.load_pricing()
        sonnet_id = rs._first_model_of_tier(pricing, "sonnet")
        self.assertIsNotNone(sonnet_id)

        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            write_kit(kits_root, "overlap", OVERLAP_TASKS_MD, OVERLAP_NOTES_MD)
            projects_root = Path(td) / "projects"
            tasks_dir = Path(td) / "tasks"
            tasks_dir.mkdir()

            shared = {"model": sonnet_id, "id": "shared-msg",
                     "input_tokens": 200000, "output_tokens": 8000}
            main_only = {"model": sonnet_id, "id": "main-only",
                        "input_tokens": 10000, "output_tokens": 500}
            main_path = write_transcript(
                projects_root / "-t" / "overlap-sess.jsonl", [shared, main_only])
            impl_path = write_transcript(tasks_dir / "impl-a.output", [shared])

            result = _run_cli(["overlap", "--kits-dir", str(kits_root),
                               "--session", "overlap-sess",
                               "--projects-dir", str(projects_root),
                               "--tasks-dir", str(tasks_dir), "--by-task", "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            card = json.loads(result.stdout)

            # reference prices via the reused pipeline WHILE the temp files still exist
            ref_main = price_of([main_path])
            ref_impl = price_of([impl_path])

        whole = card["cost"]["actual_usd"]
        bt = card["by_task"]
        # the whole-session total dedupes the shared message id ONCE, but the standalone
        # per-transcript breakdown prices it in BOTH files -- parts sum strictly higher
        parts = bt["orchestrator"]["cost_usd"] + bt["tasks"][0]["total_usd"]
        self.assertGreater(parts, whole)
        self.assertTrue(any("reconciliation" in n for n in bt["notes"]))

        # a note, never an adjustment: the standalone figures still equal price_of() exactly
        self.assertAlmostEqual(bt["orchestrator"]["cost_usd"], ref_main, places=9)
        self.assertAlmostEqual(bt["tasks"][0]["total_usd"], ref_impl, places=9)


# ---- 12. CLI --by-task rejections ------------------------------------------------------------


class CliRejectionTests(unittest.TestCase):
    def test_cli_by_task_requires_session_and_rejections(self):
        r1 = _run_cli(["some-kit", "--by-task"])
        self.assertNotEqual(r1.returncode, 0)
        self.assertIn("--session", r1.stderr)

        r2 = _run_cli(["some-kit", "--by-task", "--session", "x", "--live"])
        self.assertNotEqual(r2.returncode, 0)
        self.assertIn("--live", r2.stderr)

        r3 = _run_cli(["--history", "--by-task"])
        self.assertNotEqual(r3.returncode, 0)
        self.assertIn("--history", r3.stderr)

        r4 = _run_cli(["some-kit", "--by-task", "--session", "x", "--no-subagents"])
        self.assertNotEqual(r4.returncode, 0)
        self.assertIn("--no-subagents", r4.stderr)


# ---- 13. flag-off byte-stable shape -----------------------------------------------------------


class WithoutFlagTests(unittest.TestCase):
    def test_without_flag_byte_stable_shape(self):
        pricing = rs.cr.load_pricing()
        sonnet_id = rs._first_model_of_tier(pricing, "sonnet")
        self.assertIsNotNone(sonnet_id)

        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            # NOTES.md carries agent: lines -- flag-off must ignore them entirely
            write_kit(kits_root, "solo", SOLO_TASKS_MD, SOLO_AGENT_NOTES_MD)
            projects_root = Path(td) / "projects"
            write_transcript(projects_root / "-t" / "solo-sess.jsonl", [
                {"model": sonnet_id, "id": "m1", "input_tokens": 1000, "output_tokens": 100}])

            result = _run_cli(["solo", "--kits-dir", str(kits_root), "--session", "solo-sess",
                               "--projects-dir", str(projects_root), "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            card = json.loads(result.stdout)

            md_result = _run_cli(["solo", "--kits-dir", str(kits_root), "--session", "solo-sess",
                                  "--projects-dir", str(projects_root)])
            self.assertEqual(md_result.returncode, 0, md_result.stderr)

        self.assertEqual(set(card), {
            "schema_version", "kit", "generated_at", "tasks", "quality",
            "model_mix", "review", "cost", "notes"})
        self.assertNotIn("by_task", card)
        self.assertFalse(any("agent" in n.lower() for n in card["notes"]))

        for h2 in rs.MD_H2S:
            self.assertIn(h2, md_result.stdout)
        self.assertNotIn("## Per-task dollars", md_result.stdout)


# ---- 14. --by-task JSON shape -----------------------------------------------------------------


class ByTaskShapeTests(unittest.TestCase):
    def test_by_task_json_shape(self):
        result = _run_cli(["--demo", "--by-task", "--json"])
        self.assertEqual(result.returncode, 0, result.stderr)
        card = json.loads(result.stdout)
        bt = card["by_task"]

        self.assertEqual(set(bt), {
            "schema_version", "coverage", "tasks", "clusters",
            "orchestrator", "unattributed", "notes"})
        self.assertTrue(bt["tasks"], "fixture must include at least one task row")
        self.assertTrue(bt["clusters"], "fixture must include at least one cluster row")
        for row in bt["tasks"]:
            self.assertEqual(
                set(row), {"id", "roles", "total_usd", "missing_agents", "shared_agent_ids"})
        for cl in bt["clusters"]:
            self.assertEqual(set(cl), {"agent_id", "task_ids", "roles", "cost_usd"})


# ---- 15. pinned --demo --by-task shape ---------------------------------------------------------


class DemoByTaskPinnedTests(unittest.TestCase):
    def test_demo_by_task_pinned_shape(self):
        j = _run_cli(["--demo", "--by-task", "--json"])
        self.assertEqual(j.returncode, 0, j.stderr)
        card = json.loads(j.stdout)
        bt = card["by_task"]

        rows = {r["id"]: r for r in bt["tasks"]}
        self.assertEqual(list(rows), ["P1", "P2", "P3", "P4", "P5"])

        p3 = rows["P3"]
        self.assertEqual(p3["shared_agent_ids"], ["ag-warm"])
        self.assertEqual(p3["roles"], {})
        self.assertIsNone(p3["total_usd"])

        p5 = rows["P5"]
        self.assertEqual(p5["missing_agents"], ["ag-ghost"])
        self.assertIsNone(p5["total_usd"])

        self.assertEqual(len(bt["clusters"]), 1)
        cl = bt["clusters"][0]
        self.assertEqual(cl["agent_id"], "ag-warm")
        self.assertEqual(cl["task_ids"], ["P3", "P4"])
        self.assertGreater(cl["cost_usd"], 0)

        self.assertEqual(bt["unattributed"]["count"], 1)
        self.assertEqual(bt["unattributed"]["agent_ids"], ["ag-reviewer"])
        self.assertGreater(bt["unattributed"]["cost_usd"], 0)

        self.assertEqual(bt["coverage"], "partial")

        m = _run_cli(["--demo", "--by-task"])
        self.assertEqual(m.returncode, 0, m.stderr)
        for needle in ("## Per-task dollars", "not split", "never split per task",
                      "coverage: partial", "ag-warm"):
            self.assertIn(needle, m.stdout)


# ---- 16. prior demos stay additive --------------------------------------------------------------


class PriorDemosRegressionTests(unittest.TestCase):
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
        self.assertNotIn("by_task", c)

        l = _run_cli(["--demo", "--live", "--json"])
        self.assertEqual(l.returncode, 0, l.stderr)
        d = json.loads(l.stdout)
        self.assertEqual(d["autonomy"], "advisory")
        self.assertEqual(d["budget"], {"cap": 2, "applied": 0, "remaining": 2})
        recs = d["recommendations"]
        self.assertEqual(len(recs), 1)
        self.assertEqual((recs[0]["from"], recs[0]["to"], recs[0]["task_ids"]),
                         ("sonnet", "opus", ["L5", "L6"]))

        h = _run_cli(["--demo", "--history", "--json"])
        self.assertEqual(h.returncode, 0, h.stderr)
        hc = json.loads(h.stdout)
        K = ("pinned", "with_outcome", "first_try", "retry_pass", "escalated_pass", "blocked")
        pick = lambda tier: tuple(hc["tiers"][tier][k] for k in K)
        self.assertEqual(pick("haiku"), (3, 3, 2, 1, 0, 0))
        self.assertEqual(pick("sonnet"), (6, 5, 2, 1, 1, 1))
        self.assertEqual(pick("opus"), (2, 1, 1, 0, 0, 0))
        self.assertEqual(pick("frontier"), (1, 0, 0, 0, 0, 0))
        self.assertEqual(hc["reroutes"], {"events": 1, "applied": 0, "advisory": 1})
        self.assertEqual(hc["dollars"]["coverage"], "partial")


# ---- 17. read-only proof -------------------------------------------------------------------


class SafetyProofTests(unittest.TestCase):
    def test_readonly_by_task_run(self):
        pricing = rs.cr.load_pricing()
        sonnet_id = rs._first_model_of_tier(pricing, "sonnet")
        self.assertIsNotNone(sonnet_id)

        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            write_kit(kits_root, "readonly-bt", RO_TASKS_MD, RO_NOTES_MD)
            projects_root = Path(td) / "projects"
            write_transcript(projects_root / "-t" / "ro-sess.jsonl", [
                {"model": sonnet_id, "id": "ro-m1", "input_tokens": 10000, "output_tokens": 500}])
            tasks_dir = Path(td) / "tasks"
            tasks_dir.mkdir()
            write_transcript(tasks_dir / "ag-ro-impl.output", [
                {"model": sonnet_id, "id": "ro-a1", "input_tokens": 5000, "output_tokens": 200}])

            def snapshot(root):
                files = sorted(p for p in Path(root).rglob("*") if p.is_file())
                return [str(p) for p in files], {str(p): p.read_bytes() for p in files}

            kits_before = snapshot(kits_root)
            proj_before = snapshot(projects_root)
            tasks_before = snapshot(tasks_dir)

            result = _run_cli(["readonly-bt", "--kits-dir", str(kits_root),
                               "--session", "ro-sess", "--projects-dir", str(projects_root),
                               "--tasks-dir", str(tasks_dir), "--by-task", "--json"])

            kits_after = snapshot(kits_root)
            proj_after = snapshot(projects_root)
            tasks_after = snapshot(tasks_dir)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(kits_before, kits_after)
        self.assertEqual(proj_before, proj_after)
        self.assertEqual(tasks_before, tasks_after)


if __name__ == "__main__":
    unittest.main()
