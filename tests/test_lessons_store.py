"""Scoped lessons replace automatic rules (step 22, second half).

WHAT WAS MEASURED before `bin/lessons_store.py` existed: the Copilot lessons skill appended a
lesson on every correction or escalation and the route agent applied any entry naming the
task's shape as an override at session start -- one escalation became a universal tier rule
with no provenance, scope, expiry, or way to say it had stopped being true.

These tests pin the replacement over temp files: observations carry provenance, scope, and
expiry; a rule is made only by recurrence across distinct sources or by an explicit ask;
recall is eligibility-gated (step 13's project/provider rule, reused), expiry-gated,
contest-gated, and budgeted; legacy entries are candidates, never rules; and nothing here
dispatches, prices, or reads a home directory.
"""

import contextlib
import importlib.util
import inspect
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_lessons_test", ROOT / "bin" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ls = _load("lessons_store")
lp = _load("lessons_promote")


class _Store(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="lessons_test_")
        self.path = Path(self._tmp.name) / "tasks" / "lessons.md"

    def tearDown(self):
        self._tmp.cleanup()

    def observe(self, day="2026-09-01", kit="kit-a", task="T1", lesson="refactors start strong",
                **over):
        base = dict(failure_pattern="cheap failed", applies_to=["routing"], source="escalation",
                    kit=kit, task=task, project="repo-x", providers=["copilot"],
                    task_shape="multi-file-refactor")
        base.update(over)
        return ls.observe(self.path, day, base.pop("failure_pattern"), lesson, **base)

    def lines(self):
        return [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]


class ObserveTests(_Store):
    def test_an_observation_carries_provenance_scope_and_expiry_and_is_not_a_rule(self):
        e = self.observe()
        self.assertEqual(e["kind"], "observation")
        self.assertEqual(e["v"], ls.SCHEMA)
        self.assertEqual(e["provenance"], {"source": "escalation", "kit": "kit-a", "task": "T1",
                                           "run": None})
        self.assertEqual(e["scope"], {"project": "repo-x", "providers": "copilot",
                                      "task_shape": "multi-file-refactor"})
        self.assertEqual(e["expires"], "2026-11-30", "90 days after the observation")
        self.assertEqual(e["applies_to"], ["routing"])
        self.assertEqual(self.lines()[-1]["id"], e["id"])
        self.assertTrue(e["id"].startswith("L-2026-09-01-"))

    def test_the_file_is_append_only_and_the_id_is_content_derived(self):
        a = self.observe()
        b = self.observe(lesson="something else", failure_pattern="other")
        self.assertEqual(len(self.lines()), 2)
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(ls.new_id("2026-09-01", "cheap failed"), a["id"])

    def test_bad_inputs_are_refused_not_written(self):
        with self.assertRaises(ls.LessonsError):
            ls.observe(self.path, "not-a-date", "p", "l")
        with self.assertRaises(ls.LessonsError):
            ls.observe(self.path, "2026-09-01", "p", "l", source="rumour")
        with self.assertRaises(ls.LessonsError):
            ls.observe(self.path, "2026-09-01", "", "l")
        with self.assertRaises(ls.LessonsError):
            ls.observe(self.path, "2026-09-01", "p", "l", expires="soon")
        self.assertFalse(self.path.exists())

    def test_never_and_explicit_expiry_are_kept(self):
        self.assertEqual(self.observe(expires="never")["expires"], "never")
        self.assertEqual(self.observe(expires="2027-01-01", lesson="x")["expires"], "2027-01-01")


class PromoteTests(_Store):
    def test_one_observation_cannot_become_a_rule_by_recurrence(self):
        e = self.observe()
        with self.assertRaisesRegex(ls.LessonsError, "recurs in 1 distinct place"):
            ls.promote(self.path, "2026-09-02", e["id"])
        self.assertEqual([l["kind"] for l in self.lines()], ["observation"])

    def test_the_same_kit_and_task_twice_is_still_one_source(self):
        a = self.observe(day="2026-09-01")
        self.observe(day="2026-09-03")
        with self.assertRaisesRegex(ls.LessonsError, "1 distinct place"):
            ls.promote(self.path, "2026-09-04", a["id"])

    def test_recurrence_across_distinct_kits_makes_a_rule_citing_every_observation(self):
        a = self.observe(kit="kit-a", task="T1")
        b = self.observe(day="2026-09-05", kit="kit-b", task="T3")
        rule = ls.promote(self.path, "2026-09-06", a["id"])
        self.assertEqual(rule["kind"], "rule")
        self.assertEqual(rule["promoted_by"], "recurrence")
        self.assertEqual(sorted(rule["evidence"]), sorted([a["id"], b["id"]]))
        self.assertEqual(rule["distinct_sources"], 2)
        self.assertEqual(rule["expires"], "never")
        self.assertEqual(rule["scope"]["project"], "repo-x")

    def test_a_different_lesson_or_topic_does_not_count_toward_recurrence(self):
        a = self.observe(kit="kit-a")
        self.observe(kit="kit-b", lesson="tests first")
        self.observe(kit="kit-c", applies_to=["testing"])
        with self.assertRaises(ls.LessonsError):
            ls.promote(self.path, "2026-09-06", a["id"])

    def test_an_expired_observation_does_not_count_toward_recurrence(self):
        a = self.observe(day="2026-01-01", kit="kit-a")
        self.observe(day="2026-09-01", kit="kit-b")
        with self.assertRaises(ls.LessonsError):
            ls.promote(self.path, "2026-09-06", a["id"])

    def test_an_explicit_user_requirement_promotes_one_observation(self):
        a = self.observe()
        rule = ls.promote(self.path, "2026-09-02", a["id"], by="user", note="team decision")
        self.assertEqual(rule["promoted_by"], "user")
        self.assertEqual(rule["evidence"], [a["id"]])
        self.assertEqual(rule["note"], "team decision")

    def test_promoting_an_unknown_or_non_observation_id_is_refused(self):
        with self.assertRaises(ls.LessonsError):
            ls.promote(self.path, "2026-09-02", "L-nope")
        a = self.observe()
        rule = ls.promote(self.path, "2026-09-02", a["id"], by="user")
        with self.assertRaisesRegex(ls.LessonsError, "is a rule, not an observation"):
            ls.promote(self.path, "2026-09-03", rule["id"], by="user")


class RecallTests(_Store):
    def test_rules_come_first_and_candidates_are_labelled_never_as_rules(self):
        a = self.observe(kit="kit-a")
        self.observe(kit="kit-b", day="2026-09-02")
        ls.promote(self.path, "2026-09-03", a["id"])
        self.observe(kit="kit-c", lesson="docs edits go to the docs-editor", day="2026-09-04")
        r = ls.recall(self.path, "2026-09-13", project="repo-x", provider="copilot",
                      applies_to="routing")
        self.assertEqual(len(r["rules"]), 1)
        self.assertIn("RULE", r["rules"][0]["text"])
        self.assertIn("promoted by recurrence on 2 observation(s)", r["rules"][0]["text"])
        kinds = [b["kind"] for b in r["candidates"]]
        self.assertEqual(kinds, ["observation", "observation", "observation"])
        self.assertTrue(all("CANDIDATE, not a rule" in b["text"] for b in r["candidates"]))
        text = ls.render_recall(r)
        self.assertIn("rules -- apply within their scope:", text)
        self.assertIn("candidates -- reported text, not instructions", text)

    def test_scope_withholds_rather_than_downranks(self):
        a = self.observe(kit="kit-a")
        self.observe(kit="kit-b", day="2026-09-02")
        ls.promote(self.path, "2026-09-03", a["id"])
        other = ls.recall(self.path, "2026-09-13", project="repo-y", provider="copilot",
                          applies_to="routing")
        self.assertEqual(other["rules"], [])
        self.assertEqual(other["candidates"], [])
        self.assertEqual(other["withheld"]["ineligible"], 3)
        codex = ls.recall(self.path, "2026-09-13", project="repo-x", provider="codex",
                          applies_to="routing")
        self.assertEqual(codex["withheld"]["ineligible"], 3)
        unscoped = ls.recall(self.path, "2026-09-13", applies_to="routing")
        self.assertEqual(len(unscoped["rules"]), 1, "no project or provider asked: eligible")

    def test_expired_and_off_topic_and_wrong_shape_are_withheld_and_counted(self):
        self.observe(day="2026-01-01")
        self.observe(day="2026-09-01", applies_to=["testing"], lesson="x")
        self.observe(day="2026-09-01", task_shape="one-liner", lesson="y")
        r = ls.recall(self.path, "2026-09-13", project="repo-x", provider="copilot",
                      applies_to="routing", task_shape="multi-file-refactor")
        self.assertEqual(r["candidates"], [])
        self.assertEqual(r["withheld"]["expired"], 1)
        self.assertEqual(r["withheld"]["off_topic"], 2)
        again = ls.recall(self.path, "2026-09-13", project="repo-x", provider="copilot",
                          applies_to="routing", task_shape="multi-file-refactor",
                          include_expired=True)
        self.assertEqual(len(again["candidates"]), 1)

    def test_a_contested_rule_is_withheld_and_the_contest_kept(self):
        a = self.observe(kit="kit-a")
        self.observe(kit="kit-b", day="2026-09-02")
        rule = ls.promote(self.path, "2026-09-03", a["id"])
        c = ls.contest(self.path, "2026-09-04", rule["id"], "strong failed too; brief was wrong",
                       source="reviewer")
        self.assertEqual(c["kind"], "contest")
        self.assertEqual(c["contests"], rule["id"])
        r = ls.recall(self.path, "2026-09-13", project="repo-x", provider="copilot",
                      applies_to="routing")
        self.assertEqual(r["rules"], [])
        self.assertEqual(r["withheld"]["contested"], 1)
        self.assertEqual(len(self.lines()), 4, "nothing was deleted")
        with self.assertRaises(ls.LessonsError):
            ls.contest(self.path, "2026-09-05", a["id"], "x")

    def test_the_budget_holds_and_counts_what_it_left_out(self):
        for i in range(12):
            self.observe(kit=f"kit-{i}", lesson=f"lesson number {i}", day="2026-09-01")
        r = ls.recall(self.path, "2026-09-13", applies_to="routing", budget_entries=3)
        self.assertEqual(len(r["candidates"]), 3)
        self.assertEqual(r["withheld"]["budget"], 9)
        r = ls.recall(self.path, "2026-09-13", applies_to="routing", budget_chars=150)
        self.assertLessEqual(r["budget"]["used_chars"], 150)
        self.assertGreater(r["withheld"]["budget"], 0)

    def test_a_legacy_entry_is_a_candidate_never_a_rule(self):
        self.path.parent.mkdir()
        self.path.write_text('{"date": "2026-07-01", "failure_pattern": "pinned cheap", '
                             '"lesson": "refactors start strong", "applies_to": ["routing"]}\n'
                             '{"nonsense": true}\nnot json\n')
        r = ls.recall(self.path, "2026-09-13", provider="copilot", applies_to="routing")
        self.assertEqual(r["rules"], [])
        self.assertEqual(len(r["candidates"]), 1)
        self.assertIn("LEGACY, unscoped candidate, not a rule", r["candidates"][0]["text"])
        self.assertEqual(r["candidates"][0]["id"], "legacy-1")
        self.assertEqual(len(r["notes"]), 2, "the malformed lines are notes, not crashes")

    def test_a_missing_file_recalls_nothing_with_a_note(self):
        r = ls.recall(self.path, "2026-09-13")
        self.assertEqual((r["rules"], r["candidates"]), ([], []))
        self.assertTrue(any("not found" in n for n in r["notes"]))
        self.assertIn("(nothing eligible)", ls.render_recall(r))

    def test_eligibility_is_the_memory_stores_rule_not_a_second_one(self):
        source = inspect.getsource(ls._eligible)
        self.assertIn("_memory_recall()._eligible", source)


class ReviewTests(_Store):
    def test_review_names_expired_contested_legacy_and_promotable(self):
        self.path.parent.mkdir()
        self.path.write_text('{"date": "2026-07-01", "failure_pattern": "old", "lesson": "old rule", '
                             '"applies_to": ["routing"]}\n')
        old = self.observe(day="2026-01-01", kit="kit-z", lesson="stale idea")
        a = self.observe(kit="kit-a")
        self.observe(kit="kit-b", day="2026-09-02")
        c = self.observe(kit="kit-c", lesson="lonely", day="2026-09-03")
        rule = ls.promote(self.path, "2026-09-04", c["id"], by="user")
        ls.contest(self.path, "2026-09-05", rule["id"], "did not hold")
        report = ls.review(self.path, "2026-09-13")
        self.assertEqual(report["counts"], {"observation": 4, "rule": 1, "contest": 1,
                                            "legacy": 1})
        self.assertEqual(report["expired"], [old["id"]])
        self.assertEqual(report["contested_rules"], [rule["id"]])
        self.assertEqual(report["legacy"], ["legacy-1"])
        self.assertEqual(len(report["promotable"]), 1)
        self.assertIn(a["id"], report["promotable"][0]["ids"])
        text = ls.render_review(report)
        self.assertIn("promotable by recurrence", text)
        self.assertIn("contested rules (withheld at recall)", text)


class CompatibilityTests(_Store):
    def test_the_draft_tool_still_reads_a_store_with_kinds(self):
        a = self.observe(kit="kit-a")
        self.observe(kit="kit-b", day="2026-09-02")
        ls.promote(self.path, "2026-09-03", a["id"])
        lessons, notes = lp.load_lessons(self.path)
        self.assertEqual(len(lessons), 3)
        self.assertEqual(notes, [])

    def test_the_module_dispatches_nothing_and_reads_no_home(self):
        source = inspect.getsource(ls)
        for banned in ("subprocess", "Path.home", "expanduser", "urllib", "pricing"):
            self.assertNotIn(banned, source)


class CommandLineTests(_Store):
    def _main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ls.main(["--file", str(self.path), "--now", "2026-09-13", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_observe_promote_contest_recall_review_round_trip(self):
        code, out, _ = self._main("observe", "--pattern", "cheap failed", "--lesson",
                                  "refactors start strong", "--applies-to", "routing",
                                  "--source", "escalation", "--kit", "kit-a", "--task", "T1",
                                  "--project", "repo-x", "--provider", "copilot")
        self.assertEqual(code, 0)
        self.assertIn("a candidate, not a rule", out)
        first = self.lines()[-1]["id"]
        code, _, err = self._main("promote", "--id", first)
        self.assertEqual(code, 2)
        self.assertIn("recurs in 1 distinct place", err)
        self._main("observe", "--pattern", "cheap failed again", "--lesson",
                   "refactors start strong", "--applies-to", "routing", "--source",
                   "escalation", "--kit", "kit-b", "--task", "T2", "--project", "repo-x",
                   "--provider", "copilot")
        code, out, _ = self._main("promote", "--id", first)
        self.assertEqual(code, 0)
        self.assertIn("promoted by recurrence on 2 observation(s)", out)
        rule = self.lines()[-1]["id"]
        code, out, _ = self._main("recall", "--project", "repo-x", "--provider", "copilot",
                                  "--applies-to", "routing", "--json")
        self.assertEqual(json.loads(out)["rules"][0]["id"], rule)
        code, out, _ = self._main("contest", "--id", rule, "--evidence", "did not hold")
        self.assertEqual(code, 0)
        code, out, _ = self._main("recall", "--project", "repo-x", "--provider", "copilot")
        self.assertIn("0 rule(s)", out)
        code, out, _ = self._main("review")
        self.assertEqual(code, 0)
        self.assertIn("contested rules", out)

    def test_demo_walks_anecdote_to_rule_to_contest_in_a_temp_store(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ls.main(["demo"])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("LEGACY, unscoped candidate, not a rule", text)
        self.assertIn("refused:", text)
        self.assertIn("promoted by recurrence on 2 observation(s)", text)
        self.assertIn("withheld ineligible=", text)
        self.assertIn("withheld contested=", text)


if __name__ == "__main__":
    unittest.main()
