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

role-roster kit additions (a SEPARATE, later kit — its own tasks, sharing this file per its
own brief: "role measurement is this file's concern"):

- T1: ``AGENT_ROLES`` extends to the ten-token tuple, and ``parse_agents`` learns the
  optional ``marginal=`` pair (meaningful only alongside ``findings=``/``confirmed=``).
- T2: the standalone ``--roles`` per-role value view (PLAN D3-D5) -- ``kit_roster``,
  ``_role_value_bucket``/``_kit_role_buckets``/``_merge_role_buckets``,
  ``_role_dollars_from_by_task``, ``build_roles_card``/``render_roles_markdown``, and the
  ``run_roles``/``run_roles_demo`` CLI flow -- plus the ADDITIVE ``--by-task`` extras line
  (D3) for tasks carrying a non-trio role.

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

The role-roster ``--roles`` tests below follow the SAME contract, extended the same way
``test_crossrepo_trend.py`` extends it for its own CLI-level demo/golden tests: ``rs.main(...)``
is called IN-PROCESS with stdout captured via ``contextlib.redirect_stdout`` (never a real
subprocess), and every filesystem write lands in a fresh ``tempfile.TemporaryDirectory()``.

bin/ is not a package; routing_scorecard.py is loaded via importlib by absolute path computed
from this file's own location (BIN_DIR), mirroring tests/test_routing_history.py.
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


rs = _load("routing_scorecard")

NEW_KEYS = {"findings", "confirmed", "result"}


class AgentResultsVocabTests(unittest.TestCase):
    def test_agent_results_vocab_pinned(self):
        self.assertEqual(rs.AGENT_RESULTS, ("accepted", "revised", "blocked"))

    def test_agent_roles_extended_exactly(self):
        # Superseded by role-roster D1: extension is additive-tolerant (old ledgers parse
        # byte-identically; out-of-vocab still drops). Was test_agent_roles_untouched,
        # which pinned the role-ledger kit's original trio + escalation tuple.
        self.assertEqual(rs.AGENT_ROLES, (
            "implementer", "verifier", "escalation", "scout", "test-author",
            "second-verifier", "red-team", "security-auditor", "docs-editor",
            "synthesizer"))


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


# ---- role-roster D1: the seven new role tokens ------------------------------------------------


class NewRoleTokensTests(unittest.TestCase):
    def test_each_new_token_parses_and_survives(self):
        new_tokens = ("scout", "test-author", "second-verifier", "red-team",
                      "security-auditor", "docs-editor", "synthesizer")
        for role in new_tokens:
            with self.subTest(role=role):
                text = f"agent: T1 id=a1 role={role} model=sonnet\n"
                events, notes = rs.parse_agents(text)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["role"], role)
                self.assertEqual(notes, [])

    def test_chef_still_drops_with_note(self):
        text = "agent: T1 id=a1 role=chef model=sonnet\n"
        events, notes = rs.parse_agents(text)
        self.assertEqual(events, [])
        self.assertEqual(len(notes), 1)
        self.assertIn("unrecognized agent line", notes[0])


# ---- role-roster D2: marginal= -----------------------------------------------------------------


class MarginalTests(unittest.TestCase):
    def test_happy_path(self):
        text = "agent: T1 id=a1 role=verifier model=sonnet findings=3 confirmed=2 marginal=1\n"
        events, notes = rs.parse_agents(text)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["findings"], 3)
        self.assertEqual(ev["confirmed"], 2)
        self.assertEqual(ev["marginal"], 1)
        self.assertEqual(notes, [])

    def test_marginal_equal_to_confirmed_is_legal(self):
        text = "agent: T1 id=a1 role=verifier model=sonnet findings=2 confirmed=2 marginal=2\n"
        events, notes = rs.parse_agents(text)
        ev = events[0]
        self.assertEqual(ev["marginal"], 2)
        self.assertEqual(notes, [])

    def test_marginal_zero_is_legal(self):
        text = "agent: T1 id=a1 role=verifier model=sonnet findings=3 confirmed=1 marginal=0\n"
        events, notes = rs.parse_agents(text)
        ev = events[0]
        self.assertEqual(ev["marginal"], 0)
        self.assertEqual(notes, [])

    def test_marginal_exceeds_confirmed_degrades_with_note(self):
        text = "agent: T1 id=a1 role=verifier model=sonnet findings=5 confirmed=2 marginal=3\n"
        events, notes = rs.parse_agents(text)
        self.assertEqual(len(events), 1)   # line survives
        ev = events[0]
        self.assertIsNone(ev["marginal"])
        # findings/confirmed themselves are untouched by a bad marginal
        self.assertEqual(ev["findings"], 5)
        self.assertEqual(ev["confirmed"], 2)
        self.assertEqual(len(notes), 1)
        self.assertIn("T1", notes[0])

    def test_negative_marginal_degrades_with_note(self):
        text = "agent: T1 id=a1 role=verifier model=sonnet findings=3 confirmed=2 marginal=-1\n"
        events, notes = rs.parse_agents(text)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertIsNone(ev["marginal"])
        self.assertEqual(len(notes), 1)

    def test_non_integer_marginal_degrades_with_note(self):
        text = "agent: T1 id=a1 role=verifier model=sonnet findings=3 confirmed=2 marginal=one\n"
        events, notes = rs.parse_agents(text)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertIsNone(ev["marginal"])
        self.assertEqual(len(notes), 1)

    def test_orphan_marginal_without_findings_confirmed_degrades_with_note(self):
        text = "agent: T1 id=a1 role=verifier model=sonnet marginal=1\n"
        events, notes = rs.parse_agents(text)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertIsNone(ev["marginal"])
        self.assertIsNone(ev["findings"])
        self.assertIsNone(ev["confirmed"])
        self.assertEqual(len(notes), 1)

    def test_orphan_marginal_with_only_lone_findings_degrades_both_notes(self):
        # findings= alone (no confirmed=) already degrades findings/confirmed to None with
        # its own note; marginal= then finds findings/confirmed unavailable and degrades too,
        # with its own separate note.
        text = "agent: T1 id=a1 role=verifier model=sonnet findings=3 marginal=1\n"
        events, notes = rs.parse_agents(text)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertIsNone(ev["findings"])
        self.assertIsNone(ev["confirmed"])
        self.assertIsNone(ev["marginal"])
        self.assertEqual(len(notes), 2)

    def test_absent_marginal_is_none(self):
        text = "agent: T1 id=a1 role=verifier model=sonnet findings=3 confirmed=1 result=accepted\n"
        events, notes = rs.parse_agents(text)
        ev = events[0]
        self.assertIsNone(ev["marginal"])
        self.assertEqual(notes, [])

    def test_legacy_line_no_marginal_key_parses_with_marginal_none(self):
        # A pre-role-roster ledger line (no marginal= token at all) parses byte-identically
        # and the new "marginal" key on the event dict reads None -- unmeasured, never zero.
        text = "agent: T1 id=a1 role=implementer model=sonnet\n"
        events, notes = rs.parse_agents(text)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertIn("marginal", ev)
        self.assertIsNone(ev["marginal"])
        self.assertEqual(notes, [])


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


# ================================================================================================
# role-roster T2 -- the standalone ``--roles`` per-role value view
# ================================================================================================


def _capture(argv):
    """Run ``rs.main(argv)`` in-process, stdout captured -- never a subprocess (this file's own
    safety contract, extended to CLI-level ``--roles`` tests exactly like
    ``test_crossrepo_trend.py`` extends it for its own demo/golden tests)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = rs.main(argv)
    return rc, buf.getvalue()


# ---- constants ----------------------------------------------------------------------------


class RolesConstantsTests(unittest.TestCase):
    def test_schema_version_and_floor_pinned(self):
        self.assertEqual(rs.ROLES_SCHEMA_VERSION, 1)
        self.assertEqual(rs.MIN_ROLE_DISPATCHES, 5)


# ---- kit_roster (D5) ------------------------------------------------------------------------


class KitRosterTests(unittest.TestCase):
    def test_escalation_never_counts_toward_roster(self):
        record = {
            "agents": [_agent_event("T1", "a1", "escalation", "opus", result="accepted")],
            "reviewers": [],
            "outcomes": {},
        }
        self.assertEqual(rs.kit_roster(record), set())

    def test_reviewer_added_iff_reviewer_lines_present(self):
        record = {"agents": [], "reviewers": [_reviewer_event("P1", "opus", 1, 1)],
                  "outcomes": {}}
        self.assertEqual(rs.kit_roster(record), {"reviewer"})

    def test_implementer_derived_from_outcomes_not_agent_lines(self):
        # implementer rides the OUTCOME ledger (mirrors role_quality_stats' "one number, one
        # home" precedent) -- present with zero agent: role=implementer lines at all.
        record = {"agents": [], "reviewers": [], "outcomes": {"T1": {"model": "sonnet"}}}
        self.assertEqual(rs.kit_roster(record), {"implementer"})

    def test_r3_trio_and_r7_extended_roster_sizes(self):
        trio = {
            "agents": [_agent_event("T1", "a1", "verifier", "sonnet")],
            "reviewers": [_reviewer_event("P1", "opus", 1, 1)],
            "outcomes": {"T1": {}},
        }
        self.assertEqual(len(rs.kit_roster(trio)), 3)

        extended = {
            "agents": [
                _agent_event("T1", "a1", "verifier", "sonnet"),
                _agent_event("T1", "a2", "scout", "haiku"),
                _agent_event("T1", "a3", "test-author", "sonnet"),
                _agent_event("T1", "a4", "second-verifier", "sonnet"),
                _agent_event("T1", "a5", "red-team", "opus"),
                _agent_event("T1", "a6", "escalation", "opus"),  # never counted
            ],
            "reviewers": [_reviewer_event("P1", "opus", 1, 1)],
            "outcomes": {"T1": {}},
        }
        self.assertEqual(len(rs.kit_roster(extended)), 7)


# ---- _role_value_bucket / _kit_role_buckets (D2/D4) ------------------------------------------


class RoleValueBucketTests(unittest.TestCase):
    def test_dispatches_findings_confirmed_precision(self):
        events = [
            _agent_event("T1", "a1", "verifier", "sonnet", findings=4, confirmed=3),
            _agent_event("T2", "a2", "verifier", "sonnet", findings=2, confirmed=1),
        ]
        b = rs._role_value_bucket(events)
        self.assertEqual(b["dispatches"], 2)
        self.assertEqual(b["with_precision"], 2)
        self.assertEqual(b["findings"], 6)
        self.assertEqual(b["confirmed"], 4)
        self.assertAlmostEqual(b["precision"], 4 / 6)

    def test_precision_none_not_zero_when_unmeasured(self):
        events = [_agent_event("T1", "a1", "scout", "haiku")]
        b = rs._role_value_bucket(events)
        self.assertEqual(b["dispatches"], 1)
        self.assertEqual(b["findings"], 0)
        self.assertIsNone(b["precision"])

    def test_marginal_measured_vs_unmeasured_never_folded_to_zero(self):
        events = [
            dict(_agent_event("T1", "a1", "verifier", "sonnet", findings=2, confirmed=1),
                 marginal=1),
            _agent_event("T2", "a2", "verifier", "sonnet", findings=1, confirmed=1),  # legacy
        ]
        b = rs._role_value_bucket(events)
        self.assertEqual(b["marginal"], 1)
        self.assertEqual(b["marginal_measured"], 1)
        self.assertEqual(b["marginal_unmeasured"], 1)
        # measured-denominator rate (PLAN D4 amendment): marginal / marginal_measured (1/1),
        # never marginal / dispatches (1/2) -- the unmeasured legacy dispatch must not
        # dilute the rate.
        self.assertAlmostEqual(b["marginal_rate"], 1 / 1)

    def test_marginal_cell_is_none_when_marginal_measured_is_zero_all_unmeasured(self):
        # PLAN D4 amendment: the Marginal cell/field itself is None (never a fabricated 0)
        # when zero dispatches carried a measured `marginal=` -- distinct from "measured and
        # confirmed zero" (test_marginal_rate_real_zero_when_measured_but_zero below).
        events = [_agent_event("T1", "a1", "verifier", "sonnet", findings=2, confirmed=1),
                  _agent_event("T2", "a2", "verifier", "sonnet", findings=1, confirmed=1)]
        b = rs._role_value_bucket(events)
        self.assertEqual(b["marginal_measured"], 0)
        self.assertIsNone(b["marginal"])
        self.assertIsNone(b["marginal_rate"])

    def test_marginal_rate_partially_measured_uses_measured_denominator_not_dispatches(self):
        # The exact boundary case named in the brief: 2 marginal over 2 measured of 6
        # dispatches must render 100%, never 33% (2/6).
        events = (
            [dict(_agent_event("T1", "a1", "verifier", "sonnet", findings=3, confirmed=2),
                  marginal=1),
             dict(_agent_event("T2", "a2", "verifier", "sonnet", findings=3, confirmed=2),
                  marginal=1)]
            + [_agent_event("T3", f"a{i}", "verifier", "sonnet") for i in range(3, 7)]
        )
        b = rs._role_value_bucket(events)
        self.assertEqual(b["dispatches"], 6)
        self.assertEqual(b["marginal_measured"], 2)
        self.assertEqual(b["marginal"], 2)
        self.assertEqual(b["marginal_unmeasured"], 4)
        self.assertEqual(b["marginal_rate"], 1.0)

    def test_marginal_rate_none_when_nothing_measured(self):
        events = [_agent_event("T1", "a1", "scout", "haiku")]
        b = rs._role_value_bucket(events)
        self.assertEqual(b["marginal_measured"], 0)
        self.assertEqual(b["marginal_unmeasured"], 1)
        self.assertIsNone(b["marginal_rate"])

    def test_marginal_rate_real_zero_when_measured_but_zero(self):
        events = [dict(_agent_event("T1", "a1", "second-verifier", "sonnet",
                                    findings=1, confirmed=0), marginal=0)]
        b = rs._role_value_bucket(events)
        self.assertEqual(b["marginal_measured"], 1)
        self.assertEqual(b["marginal_rate"], 0.0)
        self.assertIsNotNone(b["marginal_rate"])

    def test_insufficient_sample_threshold_exact(self):
        four = [_agent_event("T1", f"a{i}", "scout", "haiku") for i in range(4)]
        five = [_agent_event("T1", f"a{i}", "scout", "haiku") for i in range(5)]
        self.assertTrue(rs._role_value_bucket(four)["insufficient_sample"])
        self.assertFalse(rs._role_value_bucket(five)["insufficient_sample"])

    def test_reviewer_events_never_carry_marginal_key_yet_bucket_still_works(self):
        # parse_reviewers' event keys are exactly {"phase","model","findings","confirmed",
        # "result"} -- no "marginal" key at all. _role_value_bucket must tolerate that via
        # .get(), which is exactly how "reviewer marginal: unmeasured" falls out for free.
        events = [_reviewer_event("P1", "opus", 3, 2)]
        b = rs._role_value_bucket(events)
        self.assertEqual(b["marginal_measured"], 0)
        self.assertEqual(b["marginal_unmeasured"], 1)
        self.assertIsNone(b["marginal_rate"])

    def test_kit_role_buckets_excludes_escalation_includes_reviewer(self):
        record = {
            "agents": [
                _agent_event("T1", "a1", "verifier", "sonnet", findings=1, confirmed=1),
                _agent_event("T1", "a2", "escalation", "opus", result="accepted"),
            ],
            "reviewers": [_reviewer_event("P1", "opus", 2, 1)],
        }
        buckets = rs._kit_role_buckets(record)
        self.assertNotIn("escalation", buckets)
        self.assertIn("verifier", buckets)
        self.assertIn("reviewer", buckets)

    def test_role_with_zero_events_is_absent_not_zero(self):
        record = {"agents": [], "reviewers": []}
        self.assertEqual(rs._kit_role_buckets(record), {})


# ---- _merge_role_buckets ---------------------------------------------------------------------


class MergeRoleBucketsTests(unittest.TestCase):
    def test_sums_raw_counts_and_recomputes_rates_over_the_merge(self):
        b1 = rs._role_value_bucket(
            [_agent_event("T1", "a1", "verifier", "sonnet", findings=4, confirmed=2)])
        b2 = rs._role_value_bucket(
            [_agent_event("T2", "a2", "verifier", "sonnet", findings=2, confirmed=2)])
        merged = rs._merge_role_buckets([b1, b2])
        self.assertEqual(merged["dispatches"], 2)
        self.assertEqual(merged["findings"], 6)
        self.assertEqual(merged["confirmed"], 4)
        # recomputed over the MERGED sums (4/6), never an average of 0.5 and 1.0
        self.assertAlmostEqual(merged["precision"], 4 / 6)

    def test_marginal_none_when_merged_measured_is_zero(self):
        # Two buckets, neither measured any marginal -- the merged field is None (never a
        # fabricated 0), mirroring _role_value_bucket's own None-not-zero treatment.
        b1 = rs._role_value_bucket(
            [_agent_event("T1", "a1", "verifier", "sonnet", findings=1, confirmed=1)])
        b2 = rs._role_value_bucket(
            [_agent_event("T2", "a2", "verifier", "sonnet", findings=1, confirmed=1)])
        merged = rs._merge_role_buckets([b1, b2])
        self.assertEqual(merged["marginal_measured"], 0)
        self.assertIsNone(merged["marginal"])
        self.assertIsNone(merged["marginal_rate"])

    def test_marginal_rate_over_merged_measured_denominator_not_dispatches(self):
        # The brief's exact boundary: 2 marginal over 2 measured of 6 dispatches, spread
        # across two kits' buckets, must merge to 100%, never 33% (2/6).
        b1 = rs._role_value_bucket(
            [dict(_agent_event("T1", "a1", "verifier", "sonnet", findings=3, confirmed=2),
                  marginal=1),
             _agent_event("T1", "a2", "verifier", "sonnet")])
        b2 = rs._role_value_bucket(
            [dict(_agent_event("T2", "a3", "verifier", "sonnet", findings=3, confirmed=2),
                  marginal=1)]
            + [_agent_event("T2", f"a{i}", "verifier", "sonnet") for i in range(4, 7)])
        merged = rs._merge_role_buckets([b1, b2])
        self.assertEqual(merged["dispatches"], 6)
        self.assertEqual(merged["marginal_measured"], 2)
        self.assertEqual(merged["marginal"], 2)
        self.assertEqual(merged["marginal_unmeasured"], 4)
        self.assertEqual(merged["marginal_rate"], 1.0)


# ---- _role_dollars_from_by_task (D2/D4) -------------------------------------------------------


class RoleDollarsFromByTaskTests(unittest.TestCase):
    def test_sums_task_role_subtotals_excludes_escalation(self):
        bt = {"tasks": [
            {"roles": {"implementer": {"subtotal_usd": 1.0},
                       "scout": {"subtotal_usd": 2.0},
                       "escalation": {"subtotal_usd": 9.0}}},
            {"roles": {"implementer": {"subtotal_usd": 1.5},
                       "scout": {"subtotal_usd": None}}},
        ]}
        dollars, notes = rs._role_dollars_from_by_task(bt)
        self.assertEqual(dollars["implementer"], 2.5)
        self.assertEqual(dollars["scout"], 2.0)
        self.assertNotIn("escalation", dollars)
        self.assertEqual(len(notes), 1)
        self.assertIn("scout", notes[0])
        self.assertIn("1/2", notes[0])

    def test_role_fully_unpriced_is_none_not_a_fabricated_zero(self):
        bt = {"tasks": [{"roles": {"verifier": {"subtotal_usd": None}}}]}
        dollars, notes = rs._role_dollars_from_by_task(bt)
        self.assertIsNone(dollars["verifier"])
        self.assertEqual(notes, [])


# ---- build_roles_card key locks ---------------------------------------------------------------


class BuildRolesCardKeyLockTests(unittest.TestCase):
    def test_top_level_key_set(self):
        record = {"kit": "kit-a", "tasks": [], "outcomes": {"T1": {}}, "events": [],
                  "sessions": [], "agents": [_agent_event("T1", "a1", "verifier", "sonnet")],
                  "reviewers": [], "defects": [], "notes": []}
        card = rs.build_roles_card([record], "/tmp/kits")
        self.assertEqual(set(card), {"schema_version", "generated_at", "kits_dir",
                                     "min_dispatches", "dollars_kit", "kits", "aggregate",
                                     "notes"})
        self.assertEqual(set(card["kits"][0]),
                         {"kit", "roster", "roster_size", "roster_label", "roles"})
        self.assertEqual(set(card["aggregate"]),
                         {"roster", "roster_size", "roster_label", "roles"})

    def test_dollars_attribute_only_to_the_named_kit(self):
        rec_a = {"kit": "kit-a", "outcomes": {}, "agents": [
            _agent_event("T1", "a1", "verifier", "sonnet")], "reviewers": []}
        rec_b = {"kit": "kit-b", "outcomes": {}, "agents": [
            _agent_event("T1", "b1", "verifier", "sonnet")], "reviewers": []}
        card = rs.build_roles_card(
            [rec_a, rec_b], "/tmp/kits", dollars_kit="kit-a",
            dollars_by_role={"verifier": 3.5})
        self.assertEqual(card["kits"][0]["roles"]["verifier"]["dollars_usd"], 3.5)
        self.assertIsNone(card["kits"][1]["roles"]["verifier"]["dollars_usd"])


# ---- aggregate dollars single-basis guard (PLAN D4 amendment) ---------------------------------


class AggregateDollarsGuardTests(unittest.TestCase):
    def test_two_record_fold_one_priced_one_not_yields_aggregate_na_and_note(self):
        # kit-a is the priced kit (--session scoped it); kit-b also dispatched the SAME
        # role (verifier) but was never priced -- a multi-kit fold with any unpriced kit
        # must never render a blended/fabricated aggregate dollar figure.
        priced_kit = {"kit": "kit-a", "outcomes": {}, "agents": [
            dict(_agent_event("T1", "a1", "verifier", "sonnet", findings=2, confirmed=1),
                 marginal=1)], "reviewers": []}
        unpriced_kit = {"kit": "kit-b", "outcomes": {}, "agents": [
            _agent_event("T1", "b1", "verifier", "sonnet", findings=1, confirmed=1)],
            "reviewers": []}
        card = rs.build_roles_card(
            [priced_kit, unpriced_kit], "/tmp/kits", dollars_kit="kit-a",
            dollars_by_role={"verifier": 4.0})

        # the priced kit's OWN per-kit section still shows its dollars, untouched.
        self.assertEqual(card["kits"][0]["roles"]["verifier"]["dollars_usd"], 4.0)
        self.assertEqual(card["kits"][0]["roles"]["verifier"]["cost_per_marginal_usd"], 4.0)
        self.assertIsNone(card["kits"][1]["roles"]["verifier"]["dollars_usd"])

        # the aggregate fold spans BOTH kits' dispatches but only one is priced -> n/a.
        agg_verifier = card["aggregate"]["roles"]["verifier"]
        self.assertIsNone(agg_verifier["dollars_usd"])
        self.assertIsNone(agg_verifier["cost_per_marginal_usd"])
        self.assertTrue(any(
            "aggregate cost n/a — not all kits priced; per-kit dollars only" in n
            for n in card["notes"]))

    def test_single_kit_fold_still_prices_the_aggregate(self):
        # No regression: when the aggregate role draws from exactly the priced kit (today's
        # only reachable CLI shape), the aggregate keeps its dollars.
        record = {"kit": "kit-a", "outcomes": {}, "agents": [
            dict(_agent_event("T1", "a1", "verifier", "sonnet", findings=2, confirmed=1),
                 marginal=1)], "reviewers": []}
        card = rs.build_roles_card([record], "/tmp/kits", dollars_kit="kit-a",
                                   dollars_by_role={"verifier": 4.0})
        agg_verifier = card["aggregate"]["roles"]["verifier"]
        self.assertEqual(agg_verifier["dollars_usd"], 4.0)
        self.assertEqual(agg_verifier["cost_per_marginal_usd"], 4.0)
        self.assertFalse(any("aggregate cost n/a" in n for n in card["notes"]))


# ---- render_roles_markdown honesty proofs ------------------------------------------------------


class RenderRolesMarkdownHonestyTests(unittest.TestCase):
    def test_absent_role_never_renders_a_row(self):
        record = {"kit": "kit-a", "outcomes": {}, "agents": [
            _agent_event("T1", "a1", "verifier", "sonnet")], "reviewers": []}
        card = rs.build_roles_card([record], "/tmp/kits")
        md = rs.render_roles_markdown(card)
        self.assertNotIn("| scout ", md)
        self.assertNotIn("| red-team ", md)

    def test_escalation_never_appears_and_legend_explains_it(self):
        record = {"kit": "kit-a", "outcomes": {}, "agents": [
            _agent_event("T1", "a1", "escalation", "opus", result="accepted")],
            "reviewers": []}
        card = rs.build_roles_card([record], "/tmp/kits")
        md = rs.render_roles_markdown(card)
        self.assertNotIn("| escalation ", md)
        self.assertIn("Escalation is excluded from every role row", md)

    def test_dollars_na_legend_when_no_session(self):
        card = rs.build_roles_card([], "/tmp/kits")
        md = rs.render_roles_markdown(card)
        self.assertIn("Dollars: n/a (no `--session`)", md)

    def test_dollars_priced_legend_names_the_kit(self):
        record = {"kit": "kit-a", "outcomes": {}, "agents": [
            _agent_event("T1", "a1", "verifier", "sonnet")], "reviewers": []}
        card = rs.build_roles_card([record], "/tmp/kits", dollars_kit="kit-a",
                                   dollars_by_role={"verifier": 1.0})
        md = rs.render_roles_markdown(card)
        self.assertIn("Dollars priced for kit `kit-a` only", md)

    def test_cost_per_marginal_line_only_when_both_measured(self):
        priced_with_marginal = {"kit": "kit-a", "outcomes": {}, "agents": [
            dict(_agent_event("T1", "a1", "verifier", "sonnet", findings=2, confirmed=1),
                 marginal=1)], "reviewers": []}
        card = rs.build_roles_card([priced_with_marginal], "/tmp/kits", dollars_kit="kit-a",
                                   dollars_by_role={"verifier": 4.0})
        md = rs.render_roles_markdown(card)
        self.assertIn("cost per marginal catch: $4.00", md)

        priced_no_marginal = {"kit": "kit-b", "outcomes": {}, "agents": [
            _agent_event("T1", "b1", "verifier", "sonnet", findings=2, confirmed=1)],
            "reviewers": []}
        card2 = rs.build_roles_card([priced_no_marginal], "/tmp/kits", dollars_kit="kit-b",
                                    dollars_by_role={"verifier": 4.0})
        md2 = rs.render_roles_markdown(card2)
        self.assertNotIn("cost per marginal catch", md2)

    def test_insufficient_sample_tag_at_the_floor(self):
        four = {"kit": "kit-a", "outcomes": {}, "reviewers": [], "agents": [
            _agent_event("T1", f"a{i}", "scout", "haiku") for i in range(4)]}
        five = {"kit": "kit-b", "outcomes": {}, "reviewers": [], "agents": [
            _agent_event("T1", f"a{i}", "scout", "haiku") for i in range(5)]}
        card = rs.build_roles_card([four, five], "/tmp/kits")
        md = rs.render_roles_markdown(card)
        self.assertIn("scout (insufficient sample) | 4", md)
        self.assertIn("| scout | 5", md)

    def test_marginal_cell_renders_na_not_zero_when_unmeasured(self):
        # PLAN D4 amendment: the Marginal cell renders `n/a`, never a fabricated 0, when
        # marginal_measured == 0 for that role.
        record = {"kit": "kit-a", "outcomes": {}, "agents": [
            _agent_event("T1", "a1", "verifier", "sonnet", findings=2, confirmed=1)],
            "reviewers": []}
        card = rs.build_roles_card([record], "/tmp/kits")
        md = rs.render_roles_markdown(card)
        row = next(l for l in md.splitlines() if l.startswith("| verifier "))
        cells = [c.strip() for c in row.split("|")]
        # | verifier (insuff) | Dispatches | Findings | Confirmed | Precision | Marginal | ...
        self.assertEqual(cells[6], "n/a")

    def test_marginal_cell_renders_measured_zero_as_zero_not_na(self):
        record = {"kit": "kit-a", "outcomes": {}, "agents": [
            dict(_agent_event("T1", "a1", "second-verifier", "sonnet",
                              findings=1, confirmed=0), marginal=0)],
            "reviewers": []}
        card = rs.build_roles_card([record], "/tmp/kits")
        md = rs.render_roles_markdown(card)
        row = next(l for l in md.splitlines() if l.startswith("| second-verifier "))
        cells = [c.strip() for c in row.split("|")]
        self.assertEqual(cells[6], "0")

    def test_legend_states_marginal_rate_denominator_is_measured_dispatches(self):
        card = rs.build_roles_card([], "/tmp/kits")
        md = rs.render_roles_markdown(card)
        self.assertIn("Marginal rate is per MEASURED dispatch", md)
        self.assertIn("unmeasured count beside it shows coverage", md)

    def test_legend_discloses_marginal_rate_can_exceed_100_percent(self):
        # T2R2 closing remediation (F2): the marginal rate is catches per measured
        # dispatch, not a share of dispatches -- a single dispatch can carry several
        # marginal catches, so the cell can legitimately exceed 100%.
        card = rs.build_roles_card([], "/tmp/kits")
        md = rs.render_roles_markdown(card)
        self.assertIn("catches per measured dispatch, not a share of dispatches", md)
        self.assertIn("can exceed 100%", md)

    def test_marginal_rate_renders_over_100_percent_when_catches_exceed_dispatches(self):
        # A measured dispatch can carry marginal > 1 (several confirmed findings on one
        # dispatch, each caught by no earlier layer) -- 4 marginal catches over 2
        # measured dispatches renders 200%, not a capped 100%.
        record = {"kit": "kit-a", "outcomes": {}, "agents": [
            dict(_agent_event("T1", "a1", "verifier", "sonnet",
                              findings=5, confirmed=4), marginal=2),
            dict(_agent_event("T2", "a2", "verifier", "sonnet",
                              findings=3, confirmed=3), marginal=2)],
            "reviewers": []}
        card = rs.build_roles_card([record], "/tmp/kits")
        roles = card["kits"][0]["roles"]
        self.assertEqual(roles["verifier"]["marginal"], 4)
        self.assertEqual(roles["verifier"]["marginal_measured"], 2)
        self.assertEqual(roles["verifier"]["marginal_rate"], 2.0)
        md = rs.render_roles_markdown(card)
        row = next(l for l in md.splitlines() if l.startswith("| verifier "))
        cells = [c.strip() for c in row.split("|")]
        self.assertEqual(cells[8], "200%")

    def test_legend_names_phase_scoped_roles_dollars_as_structurally_na(self):
        card = rs.build_roles_card([], "/tmp/kits")
        md = rs.render_roles_markdown(card)
        for role in ("security-auditor", "docs-editor", "synthesizer"):
            self.assertIn(f"`{role}`", md)
        self.assertIn("structurally n/a, not missing data", md)

    def test_legend_names_indirect_value_roles_as_no_adjudicable_findings(self):
        card = rs.build_roles_card([], "/tmp/kits")
        md = rs.render_roles_markdown(card)
        self.assertIn("no adjudicable findings by design", md)
        self.assertIn("judged qualitatively", md)
        for role in ("scout", "docs-editor", "synthesizer"):
            self.assertIn(f"`{role}`", md)


# ---- --by-task extras line (D3, additive) ------------------------------------------------------


class ByTaskExtrasLineTests(unittest.TestCase):
    def test_extra_roles_print_in_agent_roles_canonical_order(self):
        text = (
            "agent: T1 id=impl-1 role=implementer model=sonnet\n"
            "agent: T1 id=red-1 role=red-team model=opus\n"
            "agent: T1 id=scout-1 role=scout model=haiku\n"
        )
        events, notes = rs.parse_agents(text)
        self.assertEqual(notes, [])
        bt = rs.build_by_task([{"id": "T1"}], events, {}, None, None, rs.cr.load_pricing())
        lines = rs.render_by_task_lines(bt)
        idx = next(i for i, l in enumerate(lines) if l.startswith("| T1"))
        # canonical AGENT_ROLES order: scout before red-team, regardless of ledger order
        self.assertEqual(lines[idx + 1], "  - extra roles: scout n/a, red-team n/a")

    def test_trio_only_task_prints_no_extras_line(self):
        text = "agent: T1 id=impl-1 role=implementer model=sonnet\n"
        events, notes = rs.parse_agents(text)
        bt = rs.build_by_task([{"id": "T1"}], events, {}, None, None, rs.cr.load_pricing())
        lines = rs.render_by_task_lines(bt)
        idx = next(i for i, l in enumerate(lines) if l.startswith("| T1"))
        self.assertFalse(lines[idx + 1].strip().startswith("- extra roles"))

    def test_three_column_header_and_trio_cells_byte_unchanged(self):
        # regression proof alongside tests/test_per_task_dollars.py's own needle set.
        text = "agent: T1 id=impl-1 role=implementer model=sonnet\n"
        events, notes = rs.parse_agents(text)
        bt = rs.build_by_task([{"id": "T1"}], events, {}, None, None, rs.cr.load_pricing())
        lines = rs.render_by_task_lines(bt)
        self.assertIn("| Task | Implementer $ | Verifier $ | Escalation $ | Total $ |", lines)


# ---- CLI guardrails -----------------------------------------------------------------------


class RolesCliGuardTests(unittest.TestCase):
    def _expect_exit(self, argv, substr):
        with self.assertRaises(SystemExit) as cm:
            rs.main(argv)
        self.assertIn(substr, str(cm.exception))

    def test_live_by_task_envelope_rejected(self):
        for flag in ("--live", "--by-task", "--envelope"):
            with self.subTest(flag=flag):
                self._expect_exit(["--roles", flag],
                                  "--roles takes no --live/--by-task/--envelope")

    def test_history_mutually_exclusive(self):
        self._expect_exit(["--roles", "--history"], "mutually exclusive")

    def test_snapshot_trend_rejected(self):
        for flag in ("--snapshot", "--trend"):
            with self.subTest(flag=flag):
                self._expect_exit(["--roles", flag],
                                  "--roles takes no --snapshot/--trend")

    def test_session_without_kit_rejected(self):
        self._expect_exit(["--roles", "--session", "abc"],
                          "--roles --session requires a kit argument")

    def test_demo_takes_no_kit_argument(self):
        self._expect_exit(["--demo", "--roles", "some-kit"], "--demo takes no kit argument")


# ---- single-kit standalone (no --session) ------------------------------------------------------


class RolesSingleKitNoSessionTests(unittest.TestCase):
    def test_single_kit_view_works_without_session_dollars_na(self):
        with tempfile.TemporaryDirectory() as td:
            kit_dir = Path(td) / "solo-kit"
            kit_dir.mkdir()
            (kit_dir / "TASKS.md").write_text(
                "# T\n\n### T1 — t\n- status: done\n- model: sonnet\n")
            (kit_dir / "NOTES.md").write_text(
                "outcome: T1 model=sonnet result=pass review=clean\n"
                "agent: T1 id=a1 role=verifier model=sonnet findings=1 confirmed=1\n")
            rc, out = _capture([str(kit_dir), "--roles", "--json"])
        self.assertEqual(rc, 0)
        card = json.loads(out)
        self.assertIsNone(card["dollars_kit"])
        self.assertEqual(card["kits"][0]["kit"], "solo-kit")
        self.assertIsNone(card["kits"][0]["roles"]["verifier"]["dollars_usd"])


# ---- single-kit + --session dollars integration (D2/D4) --------------------------------------


class RolesSessionDollarsIntegrationTests(unittest.TestCase):
    def test_by_task_machinery_prices_per_role_dollars(self):
        # Reuses the existing --by-task demo fixture (DEMO_BYTASK_*) verbatim -- proves the
        # SAME transcript-pricing machinery folds into --roles' per-role dollars column, not a
        # re-implementation. Model ids computed from data/pricing.json at run time; only the
        # token VOLUMES are fixture-pinned (mirrors run_by_task_demo's own sanctioned pattern).
        pricing = rs.cr.load_pricing()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            kit_dir = tmp / "per-task-demo-kit"
            kit_dir.mkdir()
            (kit_dir / "TASKS.md").write_text(rs.DEMO_BYTASK_TASKS_MD)
            (kit_dir / "NOTES.md").write_text(rs.DEMO_BYTASK_NOTES_MD)

            proj = tmp / "projects" / "-demo"
            proj.mkdir(parents=True)
            ts = "2026-07-01T12:00:00+00:00"
            lines = []
            for tier in ("haiku", "sonnet", "opus", "frontier"):
                model_id = rs._first_model_of_tier(pricing, tier)
                if model_id is None:
                    continue
                inp, outp = rs.DEMO_VOLUMES[tier]
                lines.append(json.dumps({
                    "timestamp": ts,
                    "message": {"model": model_id, "id": f"demo-bt-main-{tier}",
                               "usage": {"input_tokens": inp, "output_tokens": outp}}}))
            (proj / "per-task-demo.jsonl").write_text("\n".join(lines) + "\n")

            tasks_out = tmp / "tasks"
            tasks_out.mkdir()
            for agent_id, (tier, inp, outp) in rs.DEMO_BYTASK_VOLUMES.items():
                model_id = rs._first_model_of_tier(pricing, tier)
                if model_id is None:
                    continue
                msg = json.dumps({
                    "timestamp": ts,
                    "message": {"model": model_id, "id": f"demo-bt-{agent_id}",
                               "usage": {"input_tokens": inp, "output_tokens": outp}}})
                (tasks_out / f"{agent_id}.output").write_text(msg + "\n")

            argv = [str(kit_dir), "--session", "per-task-demo",
                    "--projects-dir", str(tmp / "projects"),
                    "--tasks-dir", str(tasks_out), "--roles", "--json"]
            rc, out = _capture(argv)

        self.assertEqual(rc, 0)
        card = json.loads(out)
        self.assertEqual(card["dollars_kit"], "per-task-demo-kit")
        roles = card["kits"][0]["roles"]
        # implementer priced (partial -- ag-ghost has no *.output); verifier fully priced.
        self.assertIsNotNone(roles["implementer"]["dollars_usd"])
        self.assertGreater(roles["implementer"]["dollars_usd"], 0)
        self.assertIsNotNone(roles["verifier"]["dollars_usd"])
        self.assertGreater(roles["verifier"]["dollars_usd"], 0)
        # escalation excluded from the value table entirely -- never a dollars row either.
        self.assertNotIn("escalation", roles)
        self.assertTrue(any("dollars partial" in n for n in card["notes"]))


# ---- --demo --roles: the CLAUDE.md smoke, byte-pinned as this view's OWN golden --------------

GOLDEN_ROLES_DEMO_MARKDOWN = "# Per-role value — role-roster measurement (read-only)\n\n**2 kit(s) scanned · aggregate roster R7 (implementer, red-team, reviewer, scout, second-verifier, test-author, verifier)**\n\nEscalation is excluded from every role row here — it delivers fixes, not verdicts (existing law) — and never counts toward roster size. A dispatch with no `marginal=` is counted as marginal unmeasured, never folded into marginal=0; the Marginal cell itself renders `n/a` (never a fabricated 0) when zero dispatches carry a measured `marginal=`. Marginal rate is per MEASURED dispatch — the unmeasured count beside it shows coverage — it is never diluted by dividing over every dispatch. The rate is catches per measured dispatch, not a share of dispatches — a dispatch can contribute several marginal catches, so the cell can exceed 100%. Reviewer marginal: unmeasured (the `reviewer:` family carries no marginal field).\n\nPhase/run-scoped roles (`security-auditor`, `docs-editor`, `synthesizer`) can carry no per-task dollars under the never-split law — their dollars cells are structurally n/a, not missing data. `scout`, `docs-editor`, and `synthesizer` produce no adjudicable findings by design — their rows are dispatch-cost with indirect value, judged qualitatively, never by precision or marginal rate.\n\nDollars: n/a (no `--session`)\n\n## Aggregate role value\n\n| Role | Dispatches | Findings | Confirmed | Precision | Marginal | Marginal unmeasured | Marginal rate | Dollars |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|\n| implementer (insufficient sample) | 4 | 0 | 0 | n/a | n/a | 4 | n/a | n/a |\n| red-team (insufficient sample) | 2 | 0 | 0 | n/a | n/a | 2 | n/a | n/a |\n| reviewer (insufficient sample) | 2 | 4 | 3 | 75% | n/a | 2 | n/a | n/a |\n| scout (insufficient sample) | 2 | 0 | 0 | n/a | n/a | 2 | n/a | n/a |\n| second-verifier (insufficient sample) | 2 | 1 | 0 | 0% | 0 | 1 | 0% | n/a |\n| test-author | 5 | 0 | 0 | n/a | n/a | 5 | n/a | n/a |\n| verifier | 7 | 18 | 11 | 61% | 5 | 2 | 100% | n/a |\n\n## Per-kit\n\n### roles-r3-legacy — R3 (implementer, reviewer, verifier)\n\n| Role | Dispatches | Findings | Confirmed | Precision | Marginal | Marginal unmeasured | Marginal rate | Dollars |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|\n| implementer (insufficient sample) | 2 | 0 | 0 | n/a | n/a | 2 | n/a | n/a |\n| reviewer (insufficient sample) | 1 | 1 | 1 | 100% | n/a | 1 | n/a | n/a |\n| verifier (insufficient sample) | 2 | 3 | 2 | 67% | n/a | 2 | n/a | n/a |\n\n### roles-r7-marginal — R7 (implementer, red-team, reviewer, scout, second-verifier, test-author, verifier)\n\n| Role | Dispatches | Findings | Confirmed | Precision | Marginal | Marginal unmeasured | Marginal rate | Dollars |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|\n| implementer (insufficient sample) | 2 | 0 | 0 | n/a | n/a | 2 | n/a | n/a |\n| red-team (insufficient sample) | 2 | 0 | 0 | n/a | n/a | 2 | n/a | n/a |\n| reviewer (insufficient sample) | 1 | 3 | 2 | 67% | n/a | 1 | n/a | n/a |\n| scout (insufficient sample) | 2 | 0 | 0 | n/a | n/a | 2 | n/a | n/a |\n| second-verifier (insufficient sample) | 2 | 1 | 0 | 0% | 0 | 1 | 0% | n/a |\n| test-author | 5 | 0 | 0 | n/a | n/a | 5 | n/a | n/a |\n| verifier | 5 | 15 | 9 | 60% | 5 | 0 | 100% | n/a |\n\nNotes:\n- roles-r7-marginal: unrecognized agent line: 'agent: W9 id=r7-bad role=chef model=sonnet'\n"

GOLDEN_ROLES_DEMO_JSON = '{"schema_version": 1, "min_dispatches": 5, "dollars_kit": null, "kits": [{"kit": "roles-r3-legacy", "roster": ["implementer", "reviewer", "verifier"], "roster_size": 3, "roster_label": "R3", "roles": {"implementer": {"dispatches": 2, "with_precision": 0, "findings": 0, "confirmed": 0, "precision": null, "marginal": null, "marginal_measured": 0, "marginal_unmeasured": 2, "marginal_rate": null, "insufficient_sample": true, "dollars_usd": null, "cost_per_marginal_usd": null}, "verifier": {"dispatches": 2, "with_precision": 2, "findings": 3, "confirmed": 2, "precision": 0.6666666666666666, "marginal": null, "marginal_measured": 0, "marginal_unmeasured": 2, "marginal_rate": null, "insufficient_sample": true, "dollars_usd": null, "cost_per_marginal_usd": null}, "reviewer": {"dispatches": 1, "with_precision": 1, "findings": 1, "confirmed": 1, "precision": 1.0, "marginal": null, "marginal_measured": 0, "marginal_unmeasured": 1, "marginal_rate": null, "insufficient_sample": true, "dollars_usd": null, "cost_per_marginal_usd": null}}}, {"kit": "roles-r7-marginal", "roster": ["implementer", "red-team", "reviewer", "scout", "second-verifier", "test-author", "verifier"], "roster_size": 7, "roster_label": "R7", "roles": {"implementer": {"dispatches": 2, "with_precision": 0, "findings": 0, "confirmed": 0, "precision": null, "marginal": null, "marginal_measured": 0, "marginal_unmeasured": 2, "marginal_rate": null, "insufficient_sample": true, "dollars_usd": null, "cost_per_marginal_usd": null}, "verifier": {"dispatches": 5, "with_precision": 5, "findings": 15, "confirmed": 9, "precision": 0.6, "marginal": 5, "marginal_measured": 5, "marginal_unmeasured": 0, "marginal_rate": 1.0, "insufficient_sample": false, "dollars_usd": null, "cost_per_marginal_usd": null}, "scout": {"dispatches": 2, "with_precision": 0, "findings": 0, "confirmed": 0, "precision": null, "marginal": null, "marginal_measured": 0, "marginal_unmeasured": 2, "marginal_rate": null, "insufficient_sample": true, "dollars_usd": null, "cost_per_marginal_usd": null}, "test-author": {"dispatches": 5, "with_precision": 0, "findings": 0, "confirmed": 0, "precision": null, "marginal": null, "marginal_measured": 0, "marginal_unmeasured": 5, "marginal_rate": null, "insufficient_sample": false, "dollars_usd": null, "cost_per_marginal_usd": null}, "second-verifier": {"dispatches": 2, "with_precision": 1, "findings": 1, "confirmed": 0, "precision": 0.0, "marginal": 0, "marginal_measured": 1, "marginal_unmeasured": 1, "marginal_rate": 0.0, "insufficient_sample": true, "dollars_usd": null, "cost_per_marginal_usd": null}, "red-team": {"dispatches": 2, "with_precision": 0, "findings": 0, "confirmed": 0, "precision": null, "marginal": null, "marginal_measured": 0, "marginal_unmeasured": 2, "marginal_rate": null, "insufficient_sample": true, "dollars_usd": null, "cost_per_marginal_usd": null}, "reviewer": {"dispatches": 1, "with_precision": 1, "findings": 3, "confirmed": 2, "precision": 0.6666666666666666, "marginal": null, "marginal_measured": 0, "marginal_unmeasured": 1, "marginal_rate": null, "insufficient_sample": true, "dollars_usd": null, "cost_per_marginal_usd": null}}}], "aggregate": {"roster": ["implementer", "red-team", "reviewer", "scout", "second-verifier", "test-author", "verifier"], "roster_size": 7, "roster_label": "R7", "roles": {"implementer": {"dispatches": 4, "with_precision": 0, "findings": 0, "confirmed": 0, "precision": null, "marginal": null, "marginal_measured": 0, "marginal_unmeasured": 4, "marginal_rate": null, "insufficient_sample": true, "dollars_usd": null, "cost_per_marginal_usd": null}, "verifier": {"dispatches": 7, "with_precision": 7, "findings": 18, "confirmed": 11, "precision": 0.6111111111111112, "marginal": 5, "marginal_measured": 5, "marginal_unmeasured": 2, "marginal_rate": 1.0, "insufficient_sample": false, "dollars_usd": null, "cost_per_marginal_usd": null}, "reviewer": {"dispatches": 2, "with_precision": 2, "findings": 4, "confirmed": 3, "precision": 0.75, "marginal": null, "marginal_measured": 0, "marginal_unmeasured": 2, "marginal_rate": null, "insufficient_sample": true, "dollars_usd": null, "cost_per_marginal_usd": null}, "scout": {"dispatches": 2, "with_precision": 0, "findings": 0, "confirmed": 0, "precision": null, "marginal": null, "marginal_measured": 0, "marginal_unmeasured": 2, "marginal_rate": null, "insufficient_sample": true, "dollars_usd": null, "cost_per_marginal_usd": null}, "test-author": {"dispatches": 5, "with_precision": 0, "findings": 0, "confirmed": 0, "precision": null, "marginal": null, "marginal_measured": 0, "marginal_unmeasured": 5, "marginal_rate": null, "insufficient_sample": false, "dollars_usd": null, "cost_per_marginal_usd": null}, "second-verifier": {"dispatches": 2, "with_precision": 1, "findings": 1, "confirmed": 0, "precision": 0.0, "marginal": 0, "marginal_measured": 1, "marginal_unmeasured": 1, "marginal_rate": 0.0, "insufficient_sample": true, "dollars_usd": null, "cost_per_marginal_usd": null}, "red-team": {"dispatches": 2, "with_precision": 0, "findings": 0, "confirmed": 0, "precision": null, "marginal": null, "marginal_measured": 0, "marginal_unmeasured": 2, "marginal_rate": null, "insufficient_sample": true, "dollars_usd": null, "cost_per_marginal_usd": null}}}, "notes": ["roles-r7-marginal: unrecognized agent line: \'agent: W9 id=r7-bad role=chef model=sonnet\'"]}'

_ROLES_JSON_VOLATILE = ("generated_at", "kits_dir")


def _roles_json_without_volatile_keys(stdout):
    card = json.loads(stdout)
    for key in _ROLES_JSON_VOLATILE:
        card.pop(key, None)
    return json.dumps(card)


class RolesDemoGoldenTests(unittest.TestCase):
    def test_demo_roles_markdown_byte_pinned(self):
        rc, out = _capture(["--demo", "--roles"])
        self.assertEqual(rc, 0)
        self.assertEqual(out, GOLDEN_ROLES_DEMO_MARKDOWN)

    def test_demo_roles_json_pinned(self):
        rc, out = _capture(["--demo", "--roles", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(_roles_json_without_volatile_keys(out), GOLDEN_ROLES_DEMO_JSON)

    def test_demo_roles_exit_zero_the_claude_md_smoke(self):
        rc, out = _capture(["--demo", "--roles"])
        self.assertEqual(rc, 0)
        self.assertTrue(out)


if __name__ == "__main__":
    unittest.main()
