"""Stdlib unittest regression suite for the role-ledger kit's NOTES.md extensions in
bin/routing_scorecard.py:

- T1: the D1 role-ledger extension to ``agent:`` lines -- the optional
  ``findings=``/``confirmed=``/``result=`` quality fields on the existing per-task-role
  ledger line.
- T2: the two NEW line families ``reviewer:`` (per-phase reviewer precision) and
  ``defect:`` (architect brief defects) -- parsed by ``parse_reviewers``/``parse_defects``,
  disjoint by key from all four pre-existing families.
- T3: ``scan_kits`` threads ``agents``/``reviewers``/``defects`` through each record it
  builds (the ``build_history`` positional signature is frozen, so role data rides inside
  records).
- T4: ``role_quality_stats(records)`` aggregates verifier/escalation/reviewer/architect
  quality onto the ``--history`` card's new ``roles`` key (schema v2), and
  ``render_history_markdown`` gains an ALWAYS-rendered ``## Role quality`` section.

SAFETY CONTRACT: T1/T2/T4-aggregation tests are pure-function only -- they call
``rs.parse_agents`` / ``rs.parse_reviewers`` / ``rs.parse_defects`` / ``rs.role_quality_stats``
/ ``rs.render_history_markdown`` directly on in-memory strings/dicts, never touching disk, the
network, or any real ``~/.claude`` store, and spawn no subprocess. The T3 ``scan_kits`` tests
write only into a fresh ``tempfile.TemporaryDirectory()`` passed as an explicit path -- never a
bare run against a real kits dir -- with ONE exception, ``test_real_repo_kits_carry_agent_lines``,
which reads this repo's own ``.claude/kits`` (read-only, no writes, mirroring the brief's own
probe) to prove the wiring against real data. All ids/values are synthetic; the only model
tokens are the sanctioned tier vocabulary (``sonnet``/``opus``/``haiku``) plus the
``AGENT_ROLES``/``AGENT_RESULTS`` vocabulary itself.

bin/ is not a package; routing_scorecard.py is loaded via importlib by absolute path computed
from this file's own location (BIN_DIR), mirroring tests/test_routing_history.py.
"""

import importlib.util
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

NEW_KEYS = {"findings", "confirmed", "result"}


class AgentResultsVocabTests(unittest.TestCase):
    def test_agent_results_vocab_pinned(self):
        self.assertEqual(rs.AGENT_RESULTS, ("accepted", "revised", "blocked"))

    def test_agent_roles_untouched(self):
        # D1 must not extend AGENT_ROLES -- keep/skip criteria for the line are unchanged.
        self.assertEqual(rs.AGENT_ROLES, ("implementer", "verifier", "escalation"))


class OldStyleLineTests(unittest.TestCase):
    def test_old_style_line_gains_none_quality_fields(self):
        text = "agent: T1 id=a1 role=implementer model=sonnet\n"
        events, notes = rs.parse_agents(text)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertTrue(NEW_KEYS <= set(ev))
        self.assertIsNone(ev["findings"])
        self.assertIsNone(ev["confirmed"])
        self.assertIsNone(ev["result"])
        self.assertEqual(notes, [])


class HappyPathTests(unittest.TestCase):
    def test_happy_path_all_quality_fields(self):
        text = "agent: T1 id=a1 role=verifier model=sonnet findings=3 confirmed=1 result=accepted\n"
        events, notes = rs.parse_agents(text)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["findings"], 3)
        self.assertEqual(ev["confirmed"], 1)
        self.assertEqual(ev["result"], "accepted")
        self.assertEqual(notes, [])

    def test_happy_path_equal_confirmed_and_findings(self):
        # confirmed == findings is legal (not just confirmed < findings).
        text = "agent: T1 id=a1 role=verifier model=sonnet findings=2 confirmed=2 result=revised\n"
        events, notes = rs.parse_agents(text)
        ev = events[0]
        self.assertEqual(ev["findings"], 2)
        self.assertEqual(ev["confirmed"], 2)
        self.assertEqual(ev["result"], "revised")
        self.assertEqual(notes, [])

    def test_happy_path_zero_findings(self):
        # 0/0 is legal (non-negative, confirmed <= findings) -- never coerced to None.
        text = "agent: T1 id=a1 role=verifier model=sonnet findings=0 confirmed=0\n"
        events, notes = rs.parse_agents(text)
        ev = events[0]
        self.assertEqual(ev["findings"], 0)
        self.assertEqual(ev["confirmed"], 0)
        self.assertEqual(notes, [])


class LoneFindingsTests(unittest.TestCase):
    def test_lone_findings_degrades_both_with_note(self):
        text = "agent: T1 id=a1 role=verifier model=sonnet findings=3\n"
        events, notes = rs.parse_agents(text)
        self.assertEqual(len(events), 1)   # line itself is never dropped
        ev = events[0]
        self.assertIsNone(ev["findings"])
        self.assertIsNone(ev["confirmed"])
        self.assertEqual(len(notes), 1)
        self.assertIn("T1", notes[0])

    def test_lone_confirmed_degrades_both_with_note(self):
        text = "agent: T1 id=a1 role=verifier model=sonnet confirmed=1\n"
        events, notes = rs.parse_agents(text)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertIsNone(ev["findings"])
        self.assertIsNone(ev["confirmed"])
        self.assertEqual(len(notes), 1)


class ConfirmedExceedsFindingsTests(unittest.TestCase):
    def test_confirmed_greater_than_findings_degrades_both(self):
        text = "agent: T1 id=a1 role=verifier model=sonnet findings=2 confirmed=5\n"
        events, notes = rs.parse_agents(text)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertIsNone(ev["findings"])
        self.assertIsNone(ev["confirmed"])
        self.assertEqual(len(notes), 1)


class NonIntTests(unittest.TestCase):
    def test_non_integer_findings_degrades_both(self):
        text = "agent: T1 id=a1 role=verifier model=sonnet findings=three confirmed=1\n"
        events, notes = rs.parse_agents(text)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertIsNone(ev["findings"])
        self.assertIsNone(ev["confirmed"])
        self.assertEqual(len(notes), 1)

    def test_negative_findings_degrades_both(self):
        text = "agent: T1 id=a1 role=verifier model=sonnet findings=-1 confirmed=0\n"
        events, notes = rs.parse_agents(text)
        ev = events[0]
        self.assertIsNone(ev["findings"])
        self.assertIsNone(ev["confirmed"])
        self.assertEqual(len(notes), 1)

    def test_negative_confirmed_degrades_both(self):
        text = "agent: T1 id=a1 role=verifier model=sonnet findings=3 confirmed=-1\n"
        events, notes = rs.parse_agents(text)
        ev = events[0]
        self.assertIsNone(ev["findings"])
        self.assertIsNone(ev["confirmed"])
        self.assertEqual(len(notes), 1)


class UnknownResultTests(unittest.TestCase):
    def test_unknown_result_degrades_to_none_with_note(self):
        text = "agent: T1 id=a1 role=verifier model=sonnet result=chef\n"
        events, notes = rs.parse_agents(text)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertIsNone(ev["result"])
        self.assertEqual(len(notes), 1)
        self.assertIn("chef", notes[0])

    def test_valid_results_all_accepted(self):
        for result in rs.AGENT_RESULTS:
            with self.subTest(result=result):
                text = f"agent: T1 id=a1 role=escalation model=opus result={result}\n"
                events, notes = rs.parse_agents(text)
                self.assertEqual(events[0]["result"], result)
                self.assertEqual(notes, [])


class LastWinsReEmissionTests(unittest.TestCase):
    def test_enriched_line_wins_over_bare_line(self):
        text = "\n".join([
            "agent: T1 id=a1 role=verifier model=sonnet",
            "agent: T1 id=a1 role=verifier model=sonnet findings=4 confirmed=2 result=accepted",
        ])
        events, notes = rs.parse_agents(text)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["findings"], 4)
        self.assertEqual(ev["confirmed"], 2)
        self.assertEqual(ev["result"], "accepted")
        self.assertEqual(notes, [])

    def test_bare_line_after_enriched_line_reverts_to_none(self):
        # last wins is unconditional -- a later bare re-emission genuinely reverts quality
        # fields to None; parse_agents never merges across lines.
        text = "\n".join([
            "agent: T1 id=a1 role=verifier model=sonnet findings=4 confirmed=2 result=accepted",
            "agent: T1 id=a1 role=verifier model=sonnet",
        ])
        events, notes = rs.parse_agents(text)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertIsNone(ev["findings"])
        self.assertIsNone(ev["confirmed"])
        self.assertIsNone(ev["result"])

    def test_first_occurrence_position_kept_on_reemission(self):
        text = "\n".join([
            "agent: T1 id=a1 role=verifier model=sonnet",
            "agent: T1 id=a2 role=verifier model=sonnet",
            "agent: T1 id=a1 role=verifier model=sonnet findings=1 confirmed=1 result=accepted",
        ])
        events, notes = rs.parse_agents(text)
        self.assertEqual([e["agent_id"] for e in events], ["a1", "a2"])
        self.assertEqual(events[0]["result"], "accepted")


class DegradationNeverDropsLineTests(unittest.TestCase):
    def test_every_bad_quality_field_combo_keeps_the_line(self):
        bad_lines = [
            "agent: T1 id=a1 role=verifier model=sonnet findings=1",
            "agent: T1 id=a1 role=verifier model=sonnet confirmed=1",
            "agent: T1 id=a1 role=verifier model=sonnet findings=5 confirmed=9",
            "agent: T1 id=a1 role=verifier model=sonnet findings=x confirmed=1",
            "agent: T1 id=a1 role=verifier model=sonnet findings=-1 confirmed=0",
            "agent: T1 id=a1 role=verifier model=sonnet result=nope",
            "agent: T1 id=a1 role=verifier model=sonnet findings=5 confirmed=9 result=nope",
        ]
        for line in bad_lines:
            with self.subTest(line=line):
                events, notes = rs.parse_agents(line + "\n")
                self.assertEqual(len(events), 1, f"line dropped: {line!r}")
                # still keeps the base line's keep-criteria fields intact
                self.assertEqual(events[0]["task"], "T1")
                self.assertEqual(events[0]["agent_id"], "a1")
                self.assertEqual(events[0]["role"], "verifier")


class ProbeFromBriefTests(unittest.TestCase):
    """The exact scenario pinned in the T1 brief's verify command, as a regression test."""

    def test_brief_probe(self):
        text = (
            "agent: T1 id=a1 role=verifier model=sonnet findings=3 confirmed=1 result=accepted\n"
            "agent: T2 id=a2 role=implementer model=sonnet\n"
            "agent: T3 id=a3 role=verifier model=sonnet findings=2 confirmed=5\n"
            "agent: T4 id=a4 role=verifier model=sonnet result=chef\n"
        )
        ev, notes = rs.parse_agents(text)
        self.assertEqual(len(ev), 4)
        self.assertEqual(ev[0]["findings"], 3)
        self.assertEqual(ev[0]["confirmed"], 1)
        self.assertEqual(ev[0]["result"], "accepted")
        self.assertTrue({"findings", "confirmed", "result"} <= set(ev[1]))
        self.assertIsNone(ev[1]["findings"])
        self.assertIsNone(ev[1]["confirmed"])
        self.assertIsNone(ev[1]["result"])
        self.assertIsNone(ev[2]["findings"])
        self.assertIsNone(ev[2]["confirmed"])
        self.assertIsNone(ev[3]["result"])
        self.assertEqual(len(notes), 2)
        self.assertEqual(rs.AGENT_RESULTS, ("accepted", "revised", "blocked"))


# ---- T2: parse_reviewers ---------------------------------------------------------------------


class ParseReviewersTests(unittest.TestCase):
    def test_happy_path_with_result(self):
        text = "reviewer: P1 model=opus findings=2 confirmed=1 result=accepted\n"
        events, notes = rs.parse_reviewers(text)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(set(ev), {"phase", "model", "findings", "confirmed", "result"})
        self.assertEqual(ev["phase"], "P1")
        self.assertEqual(ev["model"], "opus")
        self.assertEqual(ev["findings"], 2)
        self.assertEqual(ev["confirmed"], 1)
        self.assertEqual(ev["result"], "accepted")
        self.assertEqual(notes, [])

    def test_happy_path_result_absent_no_note(self):
        text = "- reviewer: P2 model=sonnet findings=0 confirmed=0\n"
        events, notes = rs.parse_reviewers(text)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["findings"], 0)
        self.assertEqual(events[0]["confirmed"], 0)
        self.assertIsNone(events[0]["result"])
        self.assertEqual(notes, [])   # absent result is not a degrade, no note

    def test_happy_path_confirmed_equals_findings(self):
        text = "reviewer: P1 model=opus findings=3 confirmed=3\n"
        events, notes = rs.parse_reviewers(text)
        self.assertEqual(events[0]["findings"], 3)
        self.assertEqual(events[0]["confirmed"], 3)
        self.assertEqual(notes, [])

    def test_missing_model_skips_whole_line(self):
        text = "reviewer: P3 findings=1 confirmed=1\n"
        events, notes = rs.parse_reviewers(text)
        self.assertEqual(events, [])
        self.assertEqual(len(notes), 1)
        self.assertIn("unrecognized reviewer line", notes[0])

    def test_confirmed_exceeds_findings_skips_whole_line(self):
        text = "reviewer: P4 model=opus findings=1 confirmed=2\n"
        events, notes = rs.parse_reviewers(text)
        self.assertEqual(events, [])
        self.assertEqual(len(notes), 1)

    def test_non_integer_findings_skips_whole_line(self):
        text = "reviewer: P5 model=opus findings=x confirmed=1\n"
        events, notes = rs.parse_reviewers(text)
        self.assertEqual(events, [])
        self.assertEqual(len(notes), 1)

    def test_negative_findings_skips_whole_line(self):
        text = "reviewer: P6 model=opus findings=-1 confirmed=0\n"
        events, notes = rs.parse_reviewers(text)
        self.assertEqual(events, [])
        self.assertEqual(len(notes), 1)

    def test_missing_findings_or_confirmed_skips_whole_line(self):
        for text in (
            "reviewer: P7 model=opus confirmed=1\n",
            "reviewer: P7 model=opus findings=1\n",
        ):
            with self.subTest(text=text):
                events, notes = rs.parse_reviewers(text)
                self.assertEqual(events, [])
                self.assertEqual(len(notes), 1)

    def test_unknown_result_degrades_field_but_keeps_line(self):
        text = "reviewer: P8 model=opus findings=1 confirmed=1 result=nope\n"
        events, notes = rs.parse_reviewers(text)
        self.assertEqual(len(events), 1)   # findings/confirmed/model all valid -> kept
        self.assertIsNone(events[0]["result"])
        self.assertEqual(len(notes), 1)
        self.assertIn("nope", notes[0])

    def test_last_wins_per_phase_first_position_kept(self):
        text = "\n".join([
            "reviewer: P1 model=opus findings=2 confirmed=1 result=accepted",
            "reviewer: P2 model=sonnet findings=0 confirmed=0",
            "reviewer: P1 model=opus findings=3 confirmed=3",
        ])
        events, notes = rs.parse_reviewers(text)
        self.assertEqual([e["phase"] for e in events], ["P1", "P2"])
        self.assertEqual(events[0]["findings"], 3)
        self.assertEqual(events[0]["confirmed"], 3)
        self.assertIsNone(events[0]["result"])   # last line for P1 carried no result=
        self.assertEqual(notes, [])

    def test_brief_probe(self):
        revs, rn = rs.parse_reviewers(
            "reviewer: P1 model=opus findings=2 confirmed=1 result=accepted\n"
            "- reviewer: P2 model=sonnet findings=0 confirmed=0\n"
            "reviewer: P3 findings=1 confirmed=1\n"
            "reviewer: P1 model=opus findings=3 confirmed=3\n"
            "reviewer: P4 model=opus findings=1 confirmed=2\n")
        self.assertEqual([e["phase"] for e in revs], ["P1", "P2"])
        self.assertEqual(revs[0]["findings"], 3)
        self.assertEqual(revs[0]["confirmed"], 3)
        self.assertIsNone(revs[0]["result"])
        self.assertEqual(revs[1]["findings"], 0)
        self.assertEqual(revs[1]["model"], "sonnet")
        self.assertEqual(len(rn), 2)


# ---- T2: parse_defects -------------------------------------------------------------------------


class ParseDefectsTests(unittest.TestCase):
    def test_happy_path_task_scoped(self):
        events, notes = rs.parse_defects("defect: T3 kind=stale-pin\n")
        self.assertEqual(events, [{"task": "T3", "kind": "stale-pin"}])
        self.assertEqual(notes, [])

    def test_happy_path_kit_level_dash(self):
        events, notes = rs.parse_defects("defect: - kind=tautological-verify\n")
        self.assertEqual(events, [{"task": "-", "kind": "tautological-verify"}])
        self.assertEqual(notes, [])

    def test_missing_kind_skips_line(self):
        events, notes = rs.parse_defects("defect: T9 severity=high\n")
        self.assertEqual(events, [])
        self.assertEqual(len(notes), 1)
        self.assertIn("unrecognized defect line", notes[0])

    def test_duplicate_task_kind_keeps_first_with_note(self):
        text = "\n".join([
            "defect: T3 kind=stale-pin",
            "defect: T3 kind=stale-pin",
        ])
        events, notes = rs.parse_defects(text)
        self.assertEqual(events, [{"task": "T3", "kind": "stale-pin"}])
        self.assertEqual(len(notes), 1)
        self.assertIn("T3", notes[0])

    def test_suffixed_kind_is_a_distinct_event(self):
        # writer-side convention (T6): a genuinely second same-kind defect gets a suffixed
        # kind -- the parser treats it as an unrelated (task, kind) pair, no note.
        text = "\n".join([
            "defect: T3 kind=stale-pin",
            "defect: T3 kind=stale-pin-2",
        ])
        events, notes = rs.parse_defects(text)
        self.assertEqual(events, [{"task": "T3", "kind": "stale-pin"},
                                   {"task": "T3", "kind": "stale-pin-2"}])
        self.assertEqual(notes, [])

    def test_brief_probe(self):
        defs_, dn = rs.parse_defects(
            "defect: T3 kind=stale-pin\n"
            "defect: - kind=tautological-verify\n"
            "defect: T3 kind=stale-pin\n"
            "defect: T9 severity=high\n")
        self.assertEqual([(e["task"], e["kind"]) for e in defs_],
                          [("T3", "stale-pin"), ("-", "tautological-verify")])
        self.assertEqual(len(dn), 2)


# ---- T2: six-family disjointness ---------------------------------------------------------------


class SixFamilyDisjointTests(unittest.TestCase):
    """Extends test_per_task_dollars.py::ParserFamilyDisjointTests to all six line families:
    each parser sees only the lines belonging to its own family."""

    def test_all_six_families_disjoint(self):
        text = "\n".join([
            "outcome: T1 model=sonnet attempts=1 result=pass review=clean",
            "reroute: sonnet to=opus mode=advisory tasks=T1 rate=0/1",
            "session: abc-session",
            "agent: T1 id=a1 role=implementer model=sonnet",
            "reviewer: P1 model=opus findings=2 confirmed=1 result=accepted",
            "defect: T1 kind=stale-pin",
        ])
        outcomes, _ = rs.parse_outcomes(text)
        reroutes, _ = rs.parse_reroutes(text)
        sessions, _ = rs.parse_sessions(text)
        agents, _ = rs.parse_agents(text)
        reviewers, _ = rs.parse_reviewers(text)
        defects, _ = rs.parse_defects(text)

        self.assertEqual(set(outcomes), {"T1"})
        self.assertEqual(len(reroutes), 1)
        self.assertEqual(len(sessions), 1)
        self.assertEqual([(e["task"], e["agent_id"]) for e in agents], [("T1", "a1")])
        self.assertEqual([e["phase"] for e in reviewers], ["P1"])
        self.assertEqual([(e["task"], e["kind"]) for e in defects], [("T1", "stale-pin")])

    def test_reviewer_and_defect_invisible_to_pre_existing_parsers(self):
        blob = "\n".join([
            "outcome: T1 model=sonnet attempts=1 result=pass review=clean",
            "reroute: sonnet to=opus mode=advisory tasks=T1 rate=0/1",
            "session: s-1",
            "agent: T1 id=a1 role=verifier model=sonnet",
        ])
        self.assertEqual(rs.parse_reviewers(blob)[0], [])
        self.assertEqual(rs.parse_defects(blob)[0], [])

    def test_outcome_and_reroute_invisible_to_new_parsers(self):
        blob = "reviewer: P1 model=opus findings=1 confirmed=1\ndefect: T1 kind=x\n"
        self.assertEqual(rs.parse_outcomes(blob)[0], {})
        self.assertEqual(rs.parse_reroutes(blob)[0], [])
        self.assertEqual(rs.parse_sessions(blob)[0], [])
        self.assertEqual(rs.parse_agents(blob)[0], [])


# ---- T3: scan_kits threads agents/reviewers/defects through records -------------------------


class ScanKitsRoleFieldsTests(unittest.TestCase):
    def test_all_six_families_populate_record_fields(self):
        with tempfile.TemporaryDirectory() as td:
            k = Path(td) / "kit-x"
            k.mkdir(parents=True)
            (k / "TASKS.md").write_text(
                "# T\n\n## Phase 1 — p\n\n### X1 — t\n- status: done\n- model: sonnet\n")
            (k / "NOTES.md").write_text(
                "outcome: X1 model=sonnet result=pass review=clean\n"
                "reroute: sonnet to=opus mode=advisory tasks=X1 rate=0/1\n"
                "agent: X1 id=a1 role=verifier model=sonnet findings=1 confirmed=1 "
                "result=accepted\n"
                "reviewer: P1 model=opus findings=2 confirmed=1\n"
                "defect: X1 kind=stale-pin\n"
                "session: s-1\n")
            records, notes = rs.scan_kits(td)

        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["kit"], "kit-x")
        # pre-existing fields stay byte-identical in meaning
        self.assertEqual(set(rec["outcomes"]), {"X1"})
        self.assertEqual(len(rec["events"]), 1)         # reroute events
        self.assertEqual(rec["sessions"], ["s-1"])
        # new fields populated as parsed
        self.assertEqual(len(rec["agents"]), 1)
        self.assertEqual(rec["agents"][0]["findings"], 1)
        self.assertEqual(rec["agents"][0]["confirmed"], 1)
        self.assertEqual(rec["agents"][0]["result"], "accepted")
        self.assertEqual(len(rec["reviewers"]), 1)
        self.assertEqual(rec["reviewers"][0]["phase"], "P1")
        self.assertEqual(rec["defects"], [{"task": "X1", "kind": "stale-pin"}])
        self.assertEqual(notes, [])

    def test_tasks_only_kit_new_keys_empty_and_status_only_note_present(self):
        with tempfile.TemporaryDirectory() as td:
            k = Path(td) / "kit-bare"
            k.mkdir(parents=True)
            (k / "TASKS.md").write_text("# T\n\n### Y1 — t\n- status: pending\n- model: haiku\n")
            records, notes = rs.scan_kits(td)

        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["agents"], [])
        self.assertEqual(rec["reviewers"], [])
        self.assertEqual(rec["defects"], [])
        # pre-existing missing-NOTES behavior is unchanged
        self.assertEqual(rec["outcomes"], {})
        self.assertEqual(rec["events"], [])
        self.assertEqual(rec["sessions"], [])
        self.assertIn("kit-bare: no outcome ledger — status-only", rec["notes"])
        self.assertIn("kit-bare: no outcome ledger — status-only", notes)

    def test_record_key_set_grew_by_exactly_three(self):
        with tempfile.TemporaryDirectory() as td:
            k = Path(td) / "kit-solo"
            k.mkdir(parents=True)
            (k / "TASKS.md").write_text("# T\n\n### Z1 — t\n- status: pending\n- model: haiku\n")
            records, _ = rs.scan_kits(td)
        self.assertEqual(
            set(records[0]),
            {"kit", "tasks", "outcomes", "events", "sessions",
             "agents", "reviewers", "defects", "notes"})

    def test_real_repo_kits_carry_agent_lines(self):
        # read-only probe against this repo's own .claude/kits (mirrors the brief's own
        # verify command) -- proves the wiring against real data, not just a fixture.
        real, _ = rs.scan_kits(REPO_ROOT / ".claude" / "kits")
        self.assertTrue(any(r["agents"] for r in real),
                         "real kits carry agent: lines — none parsed")


# ---- T4: role_quality_stats aggregation -------------------------------------------------------


def _agent_event(task, agent_id, role, model, findings=None, confirmed=None, result=None):
    return {"task": task, "agent_id": agent_id, "role": role, "model": model,
            "findings": findings, "confirmed": confirmed, "result": result}


def _reviewer_event(phase, model, findings, confirmed, result=None):
    return {"phase": phase, "model": model, "findings": findings, "confirmed": confirmed,
            "result": result}


class RoleQualityStatsHappyPathTests(unittest.TestCase):
    def test_aggregation_across_two_records(self):
        records = [
            {
                "kit": "kit-a",
                "agents": [
                    _agent_event("T1", "a1", "verifier", "sonnet",
                                 findings=3, confirmed=1, result="accepted"),
                    # implementer role is deliberately ignored by role_quality_stats (PLAN D7)
                    _agent_event("T2", "a2", "implementer", "sonnet", result="accepted"),
                    _agent_event("T3", "a3", "escalation", "opus", result="blocked"),
                ],
                "reviewers": [_reviewer_event("P1", "opus", findings=2, confirmed=1)],
                "defects": [{"task": "T1", "kind": "stale-pin"}],
            },
            {
                "kit": "kit-b",
                "agents": [
                    _agent_event("U1", "b1", "verifier", "haiku",
                                 findings=1, confirmed=1, result="revised"),
                ],
                "reviewers": [],
                "defects": [{"task": "-", "kind": "stale-pin"},
                            {"task": "U2", "kind": "tautological-verify"}],
            },
        ]
        roles, notes = rs.role_quality_stats(records)
        self.assertEqual(notes, [])   # every model on-ladder -- no exclusion note

        v = roles["verifier"]
        self.assertEqual(set(v), {"events", "with_precision", "findings", "confirmed",
                                   "precision", "results", "by_tier"})
        self.assertEqual(v["events"], 2)
        self.assertEqual(v["with_precision"], 2)
        self.assertEqual(v["findings"], 4)
        self.assertEqual(v["confirmed"], 2)
        self.assertEqual(v["precision"], 0.5)
        self.assertEqual(v["results"],
                          {"accepted": 1, "revised": 1, "blocked": 0, "unrecorded": 0})
        self.assertEqual(v["by_tier"]["sonnet"],
                          {"events": 1, "with_precision": 1, "findings": 3, "confirmed": 1,
                           "precision": 1 / 3})
        self.assertEqual(v["by_tier"]["haiku"],
                          {"events": 1, "with_precision": 1, "findings": 1, "confirmed": 1,
                           "precision": 1.0})
        self.assertEqual(v["by_tier"]["opus"],
                          {"events": 0, "with_precision": 0, "findings": 0, "confirmed": 0,
                           "precision": None})
        self.assertEqual(v["by_tier"]["frontier"],
                          {"events": 0, "with_precision": 0, "findings": 0, "confirmed": 0,
                           "precision": None})

        esc = roles["escalation"]
        self.assertEqual(set(esc), {"events", "results"})
        self.assertEqual(esc["events"], 1)
        self.assertEqual(esc["results"],
                          {"accepted": 0, "revised": 0, "blocked": 1, "unrecorded": 0})

        rv = roles["reviewer"]
        self.assertEqual(set(rv), {"events", "findings", "confirmed", "precision",
                                    "results", "by_tier"})
        self.assertEqual(rv["events"], 1)
        self.assertEqual(rv["findings"], 2)
        self.assertEqual(rv["confirmed"], 1)
        self.assertEqual(rv["precision"], 0.5)
        self.assertEqual(rv["results"],
                          {"accepted": 0, "revised": 0, "blocked": 0, "unrecorded": 1})
        self.assertEqual(rv["by_tier"]["opus"],
                          {"events": 1, "with_precision": 1, "findings": 2, "confirmed": 1,
                           "precision": 0.5})

        arch = roles["architect"]
        self.assertEqual(set(arch), {"defects", "kits_recording", "by_kind", "by_kit"})
        self.assertEqual(arch["defects"], 3)
        self.assertEqual(arch["kits_recording"], 2)
        self.assertEqual(arch["by_kit"], {"kit-a": 1, "kit-b": 2})
        self.assertEqual(arch["by_kind"], {"stale-pin": 2, "tautological-verify": 1})

        self.assertEqual(set(roles), {"verifier", "escalation", "reviewer", "architect"})


class RoleQualityStatsZeroEvidenceTests(unittest.TestCase):
    def test_zero_evidence_shape_never_fabricates(self):
        records = [
            {"kit": "kit-a", "agents": [], "reviewers": [], "defects": []},
            {"kit": "kit-b", "agents": [], "reviewers": [], "defects": []},
        ]
        roles, notes = rs.role_quality_stats(records)
        self.assertEqual(notes, [])

        v = roles["verifier"]
        self.assertEqual(v["events"], 0)
        self.assertEqual(v["with_precision"], 0)
        self.assertEqual(v["findings"], 0)
        self.assertEqual(v["confirmed"], 0)
        self.assertIsNone(v["precision"])          # never a fabricated 0%
        self.assertEqual(v["results"],
                          {"accepted": 0, "revised": 0, "blocked": 0, "unrecorded": 0})
        for tier in rs.LIVE_TIER_ORDER:
            self.assertEqual(v["by_tier"][tier],
                              {"events": 0, "with_precision": 0, "findings": 0,
                               "confirmed": 0, "precision": None})

        self.assertEqual(roles["escalation"],
                          {"events": 0,
                           "results": {"accepted": 0, "revised": 0, "blocked": 0,
                                       "unrecorded": 0}})

        rv = roles["reviewer"]
        self.assertEqual(rv["events"], 0)
        self.assertIsNone(rv["precision"])

        arch = roles["architect"]
        self.assertEqual(arch, {"defects": 0, "kits_recording": 0, "by_kind": {},
                                 "by_kit": {}})

    def test_no_records_at_all(self):
        roles, notes = rs.role_quality_stats([])
        self.assertEqual(notes, [])
        self.assertEqual(roles["verifier"]["events"], 0)
        self.assertEqual(roles["architect"]["defects"], 0)


class RoleQualityStatsOffLadderTests(unittest.TestCase):
    def test_off_ladder_and_missing_model_excluded_with_one_note(self):
        records = [{
            "kit": "kit-a",
            "agents": [
                _agent_event("T1", "a1", "verifier", "some-custom-alias",
                             findings=2, confirmed=1, result="accepted"),
                _agent_event("T2", "a2", "verifier", None),
            ],
            "reviewers": [],
            "defects": [],
        }]
        roles, notes = rs.role_quality_stats(records)
        v = roles["verifier"]
        # both events still counted top-level -- never dropped
        self.assertEqual(v["events"], 2)
        self.assertEqual(v["with_precision"], 1)
        self.assertEqual(v["findings"], 2)
        # neither event lands in ANY by_tier bucket
        for tier in rs.LIVE_TIER_ORDER:
            self.assertEqual(v["by_tier"][tier]["events"], 0)
        # exactly ONE aggregate note, not one per event
        exclusion_notes = [n for n in notes if "verifier" in n and "excluded from by_tier" in n]
        self.assertEqual(len(exclusion_notes), 1)
        self.assertIn("2", exclusion_notes[0])

    def test_off_ladder_reviewer_model_gets_its_own_note(self):
        records = [{
            "kit": "kit-a",
            "agents": [],
            "reviewers": [_reviewer_event("P1", "unknown-model", findings=1, confirmed=1)],
            "defects": [],
        }]
        roles, notes = rs.role_quality_stats(records)
        rv = roles["reviewer"]
        self.assertEqual(rv["events"], 1)
        for tier in rs.LIVE_TIER_ORDER:
            self.assertEqual(rv["by_tier"][tier]["events"], 0)
        exclusion_notes = [n for n in notes if "reviewer" in n and "excluded from by_tier" in n]
        self.assertEqual(len(exclusion_notes), 1)


# ---- T4: render_history_markdown's ## Role quality section --------------------------------------


def _zero_tiers():
    return {tier: {"pinned": 0, "with_outcome": 0, "first_try": 0, "retry_pass": 0,
                   "escalated_pass": 0, "blocked": 0, "first_try_rate": None,
                   "escalation_rate": None,
                   "reroutes": {"applied_from": 0, "applied_to": 0,
                                "advisory_from": 0, "advisory_to": 0}}
            for tier in rs.LIVE_TIER_ORDER}


def _minimal_card(roles):
    return {
        "schema_version": rs.HISTORY_SCHEMA_VERSION,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "kits_dir": "/synthetic/kits",
        "kits": [],
        "tiers": _zero_tiers(),
        "reroutes": {"events": 0, "applied": 0, "advisory": 0},
        "roles": roles,
        "dollars": None,
        "notes": [],
    }


class RenderHistoryMarkdownRoleQualityTests(unittest.TestCase):
    def test_zero_evidence_branch_is_one_explicit_line(self):
        roles, _ = rs.role_quality_stats([])
        card = _minimal_card(roles)
        md = rs.render_history_markdown(card)

        self.assertIn("## Role quality", md)
        self.assertIn(
            "no role-quality evidence recorded — verifier, reviewer, escalation, and "
            "architect quality not yet measurable (implementer-only history).", md)
        # the populated-branch furniture must NOT appear
        self.assertNotIn("Implementer quality:", md)
        self.assertNotIn("| Role | Events |", md)

    def test_populated_branch_renders_table_tiers_and_architect(self):
        records = [{
            "kit": "kit-a",
            "agents": [
                _agent_event("T1", "a1", "verifier", "sonnet",
                             findings=3, confirmed=1, result="accepted"),
            ],
            "reviewers": [_reviewer_event("P1", "opus", findings=2, confirmed=1)],
            "defects": [{"task": "T1", "kind": "stale-pin"}],
        }]
        roles, _ = rs.role_quality_stats(records)
        card = _minimal_card(roles)
        md = rs.render_history_markdown(card)

        self.assertIn("## Role quality", md)
        self.assertIn(
            "Implementer quality: see the per-tier track record above (outcome ledger).", md)
        self.assertIn(
            "| Role | Events | With precision | Findings | Confirmed | Precision "
            "| Accepted | Revised | Blocked | Unrecorded |", md)
        self.assertIn("| verifier | 1 | 1 | 3 | 1 | 33% | 1 | 0 | 0 | 0 |", md)
        self.assertIn("| reviewer | 1 | 1 | 2 | 1 | 50% | 0 | 0 | 0 | 1 |", md)
        self.assertIn("| escalation | 0 | n/a | n/a | n/a | n/a | 0 | 0 | 0 | 0 |", md)
        self.assertIn(
            "- verifier sonnet: 1 event(s), 1 with recorded precision, findings 3, "
            "confirmed 1, precision 33%", md)
        self.assertIn(
            "- reviewer opus: 1 event(s), 1 with recorded precision, findings 2, "
            "confirmed 1, precision 50%", md)
        self.assertIn(
            "- Architect: 1 brief defects across 1 kits (floor — kits run before "
            "role-ledger adoption record none)", md)
        self.assertIn("kinds: stale-pin 1", md)
        # zero-evidence line must NOT appear once there IS evidence
        self.assertNotIn("no role-quality evidence recorded", md)

    def test_h2_appears_between_per_tier_and_reroute(self):
        roles, _ = rs.role_quality_stats([])
        card = _minimal_card(roles)
        md = rs.render_history_markdown(card)
        i_tier = md.index("## Per-tier track record")
        i_roles = md.index("## Role quality")
        i_reroute = md.index("## Re-route history")
        self.assertTrue(i_tier < i_roles < i_reroute)


class RenderHistoryMarkdownFalseZeroTests(unittest.TestCase):
    """F4 regression: 'ran, nothing recorded' must never render identically to
    'genuinely found zero'."""

    def test_unrecorded_precision_tier_is_not_a_bare_findings_zero(self):
        records = [{
            "kit": "kit-a",
            "agents": [
                # findings/confirmed both None -- "ran, nothing recorded", not a
                # measured zero.
                _agent_event("T1", "a1", "verifier", "haiku", result="accepted"),
                _agent_event("T2", "a2", "verifier", "haiku", result="accepted"),
            ],
            "reviewers": [],
            "defects": [],
        }]
        roles, _ = rs.role_quality_stats(records)
        self.assertEqual(roles["verifier"]["by_tier"]["haiku"]["with_precision"], 0)
        card = _minimal_card(roles)
        md = rs.render_history_markdown(card)

        self.assertIn(
            "- verifier haiku: 2 event(s), 0 with recorded precision — not measured", md)
        # the false-zero shape must never appear for this tier
        self.assertNotIn("verifier haiku: findings 0", md)
        for line in md.splitlines():
            if line.startswith("- verifier haiku"):
                self.assertNotIn("findings 0", line)
                self.assertNotIn("confirmed 0", line)

    def test_recorded_precision_tier_shows_its_numbers(self):
        records = [{
            "kit": "kit-a",
            "agents": [
                _agent_event("T1", "a1", "verifier", "sonnet",
                             findings=3, confirmed=1, result="accepted"),
                _agent_event("T2", "a2", "verifier", "sonnet",
                             findings=0, confirmed=0, result="accepted"),
                _agent_event("T3", "a3", "verifier", "sonnet",
                             findings=0, confirmed=0, result="accepted"),
            ],
            "reviewers": [],
            "defects": [],
        }]
        roles, _ = rs.role_quality_stats(records)
        self.assertEqual(roles["verifier"]["by_tier"]["sonnet"]["with_precision"], 3)
        card = _minimal_card(roles)
        md = rs.render_history_markdown(card)

        self.assertIn(
            "- verifier sonnet: 3 event(s), 3 with recorded precision, findings 3, "
            "confirmed 1, precision 33%", md)
        self.assertNotIn("not measured", md)

    def test_off_ladder_findings_gap_disclosed_when_nonzero(self):
        records = [{
            "kit": "kit-a",
            "agents": [
                _agent_event("T1", "a1", "verifier", "sonnet",
                             findings=3, confirmed=1, result="accepted"),
                # off-ladder model: counted in top-level findings, excluded from by_tier
                _agent_event("T2", "a2", "verifier", "some-custom-alias",
                             findings=2, confirmed=2, result="accepted"),
            ],
            "reviewers": [],
            "defects": [],
        }]
        roles, _ = rs.role_quality_stats(records)
        self.assertEqual(roles["verifier"]["findings"], 5)
        card = _minimal_card(roles)
        md = rs.render_history_markdown(card)

        self.assertIn(
            "- (2 finding(s) from off-ladder or unrecorded models are counted above "
            "but attributed to no tier)", md)

    def test_off_ladder_gap_line_absent_when_zero(self):
        records = [{
            "kit": "kit-a",
            "agents": [
                _agent_event("T1", "a1", "verifier", "sonnet",
                             findings=3, confirmed=1, result="accepted"),
            ],
            "reviewers": [],
            "defects": [],
        }]
        roles, _ = rs.role_quality_stats(records)
        card = _minimal_card(roles)
        md = rs.render_history_markdown(card)
        self.assertNotIn("attributed to no tier", md)


if __name__ == "__main__":
    unittest.main()
