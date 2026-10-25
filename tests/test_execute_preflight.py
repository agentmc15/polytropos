"""The execute skill checks a kit against itself before the first dispatch (kit-preflight T10).

`kit_contract.py analyze` is static, and nothing in bin/ can observe whether the interactive
loop ran it or the P0 spec review that follows it. What this suite can hold is the instruction
itself, so a later edit cannot drop the step, move it after the first dispatch, lose the
`workflow=direct` skip, or lose the reference that carries the review's prompt and recording
rules. It also holds PLAN A4's recording half, through the scorecard's own parsers and
aggregate: a `reviewer: P0` line counts as a review event, and a `when=pre-run` defect counts
as caught pre-run. The fixture kit lives in a temp dir; no committed kit is read.
"""

import importlib.util
import re
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = REPO_ROOT / "bin"
SKILL = REPO_ROOT / "skills" / "execute" / "SKILL.md"
REFERENCE = REPO_ROOT / "skills" / "execute" / "references" / "spec-review.md"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rs = _load("routing_scorecard")


def _section(text, heading):
    start = text.index(heading)
    end = text.find("\n## ", start + len(heading))
    return text[start:] if end == -1 else text[start:end]


class PreDispatchStepTests(unittest.TestCase):
    """SKILL.md runs analyze and the P0 review after graph/roster and before any task."""

    def setUp(self):
        loop = _section(SKILL.read_text(encoding="utf-8"), "## The loop")
        self.assertIn("Before the first dispatch", loop)
        self.assertIn("For each task in order", loop)
        start = loop.index("Before the first dispatch")
        self.span = loop[start:loop.index("For each task in order", start)]

    def test_analyze_runs_between_the_first_dispatch_marker_and_the_task_loop(self):
        self.assertIn("kit_contract.py analyze", self.span)

    def test_analyze_follows_roster_and_the_review_follows_analyze(self):
        for needle in ("kit_contract.py roster", "kit_contract.py analyze",
                       "references/spec-review.md"):
            self.assertIn(needle, self.span)
        roster = self.span.index("kit_contract.py roster")
        analyze = self.span.index("kit_contract.py analyze")
        review = self.span.index("references/spec-review.md")
        self.assertLess(roster, analyze, "analyze must run after roster")
        self.assertLess(analyze, review, "the spec review must come after analyze")

    def test_the_review_is_gated_on_no_reviewer_p0_line_yet(self):
        self.assertIn("`reviewer: P0`", self.span)
        self.assertIn("before step 1 of the first task", self.span)

    def test_a_direct_workflow_skips_the_review_and_says_so(self):
        # PLAN D17(b): the skip sits beside the dispatch it suppresses, and is recorded.
        self.assertIn("workflow=direct", self.span)
        self.assertIn("skipped", self.span)

    def test_the_reference_is_listed_with_a_read_when_trigger(self):
        refs = _section(SKILL.read_text(encoding="utf-8"), "## References — read when")
        line = next((ln for ln in refs.splitlines() if "references/spec-review.md" in ln), None)
        self.assertIsNotNone(line, "references/spec-review.md is not listed")
        self.assertIn("read when", line)
        self.assertIn("reviewer: P0", line)


class AcceptStepTests(unittest.TestCase):
    """Step 4 ("On pass") records the acceptance with ONE `accept` call after the outcome line
    (kit-preflight T11, PLAN B2/D6/R10)."""

    def setUp(self):
        loop = _section(SKILL.read_text(encoding="utf-8"), "## The loop")
        start = loop.index("4. **On pass**")
        end = loop.find("\n5. ", start)
        self.step4 = loop[start:end]
        self.assertIn("`outcome:` line", self.step4)

    def test_step_four_names_the_accept_call(self):
        self.assertIn("kit_contract.py accept", self.step4)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/bin/kit_contract.py accept", self.step4)

    def test_the_call_passes_the_kit_task_and_the_run_id_of_the_outcome_line(self):
        at = self.step4.index("kit_contract.py accept")
        sentence = self.step4[at:]
        for flag in ("--kit", "--task", "--run"):
            self.assertIn(flag, sentence)
        self.assertIn("same `run=` id", sentence)

    def test_accept_comes_after_the_outcome_clause_not_before_it(self):
        outcome = self.step4.index("append the task's `outcome:` line")
        accept = self.step4.index("kit_contract.py accept")
        self.assertLess(outcome, accept)
        self.assertLess(outcome, self.step4.index("--run", accept))

    def test_the_sentence_says_when_accept_refuses_and_to_call_it_right_away(self):
        self.assertIn("right after the status flip", self.step4)
        sentence = self.step4[self.step4.index("kit_contract.py accept"):]
        for needle in ("exits 2", "missing", "another run", "more than a day old",
                       "as it is when it runs", "one stdout line"):
            self.assertIn(needle, sentence)

    def test_an_accept_refusal_is_noted_in_prose_never_fixed_with_an_outcome_line(self):
        sentence = self.step4[self.step4.index("kit_contract.py accept"):]
        self.assertIn("If it exits 2, note the reason in NOTES.md prose and carry on", sentence)
        self.assertIn("never add or edit an `outcome:` line to satisfy it", sentence)

    def test_the_existing_step_four_wording_is_kept(self):
        for needle in ("mark `done`", "note anything learned that later tasks need",
                       "(grammar in `references/ledger.md`)",
                       "A fresh outcome line is a fresh signal"):
            self.assertIn(needle, self.step4)


class SpecReviewReferenceTests(unittest.TestCase):
    """The reference carries the prompt, the adjudication rule, and the recording."""

    def setUp(self):
        self.assertTrue(REFERENCE.is_file(), f"missing {REFERENCE.relative_to(REPO_ROOT)}")
        self.text = REFERENCE.read_text(encoding="utf-8")

    def _prompt(self):
        m = re.search(r"^```[a-z]*\n(.*?)\n```$", self.text, re.S | re.M)
        self.assertIsNotNone(m, "no fenced prompt in spec-review.md")
        self.assertTrue(m.group(1).strip(), "the fenced prompt is empty")
        return m.group(1)

    def test_the_fenced_prompt_names_what_the_reviewer_reads_and_returns(self):
        prompt = self._prompt()
        for needle in ("PLAN.md", "TASKS.md", "GUARDRAILS.md", "analyze", "file:line",
                       "contradictory-acceptance", "no findings"):
            with self.subTest(needle=needle):
                self.assertIn(needle, prompt)

    def test_the_reference_names_the_files_the_kind_and_the_pair(self):
        for needle in ("PLAN.md", "TASKS.md", "contradictory-acceptance", "when=pre-run",
                       "`<slug>-reviewer`", "model: opus"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.text)

    def test_the_recording_grammar_is_stated(self):
        self.assertIn("reviewer: P0 model=opus findings=<n> confirmed=<n> "
                      "result=<accepted|revised|blocked>", self.text)
        self.assertIn("defect: <task-id> kind=<kind> when=pre-run", self.text)

    def test_the_verify_findings_map_to_unrunnable_verify(self):
        lines = [ln for ln in self.text.splitlines()
                 if "kind=unrunnable-verify when=pre-run" in ln]
        self.assertEqual(len(lines), 1, lines)
        for finding in ("verify-missing-path", "verify-missing-executable",
                        "verify-unparseable"):
            with self.subTest(finding=finding):
                self.assertIn(f"`{finding}`", lines[0])
        self.assertNotIn("brief-missing-path", lines[0])

    def test_the_brief_finding_maps_to_unspecified_path(self):
        lines = [ln for ln in self.text.splitlines()
                 if "kind=unspecified-path when=pre-run" in ln]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("`brief-missing-path`", lines[0])
        self.assertNotIn("verify-", lines[0])

    def test_only_the_interactive_loop_judges_analyze_warnings(self):
        flat = " ".join(self.text.split())
        self.assertIn("Only the interactive loop adjudicates `analyze`'s warnings.", flat)
        self.assertIn("The headless drivers and `workflow: direct` kits print them, and nothing "
                      "judges them.", flat)

    def test_confirmed_means_an_edit_or_a_stop(self):
        flat = " ".join(self.text.split())
        self.assertIn("confirmed** only when it produces a TASKS.md or PLAN.md edit or a "
                      "stop-and-report", flat)
        self.assertIn("stop and report to the user before any dispatch", flat)

    def test_the_direct_skip_is_stated_with_its_notes_line(self):
        flat = " ".join(self.text.split())
        self.assertIn("workflow=direct", flat)
        self.assertIn("P0 spec review was skipped because the kit declared `direct`", flat)

    def test_the_reference_never_names_the_generated_site(self):
        self.assertNotIn("docs-site", self.text)


# PLAN A4, carried from the Phase 1 review: the recording the reference prescribes is what
# the scorecard counts. The lines are bare, as NOTES.md carries them; a backticked line does
# not parse, which is why the reference shows them unbackticked in an indented block.
NOTES = """\
# fixture kit — notes

reviewer: P0 model=opus findings=2 confirmed=1
defect: T1 kind=stale-pin when=pre-run
"""

TASKS = """\
# fixture kit — tasks

## Phase 1 — one

### T1 — one
- id: T1
- title: one
- status: pending
- model: sonnet

**Brief.** Do one thing.

**Acceptance.** It is done.

**Verify.**
```bash
true
```
"""


class PreRunRecordingTests(unittest.TestCase):
    def _assert_counted(self, records):
        roles, _ = rs.role_quality_stats(records)
        reviewer = roles["reviewer"]
        self.assertEqual(reviewer["events"], 1, "the P0 line is not a review event")
        self.assertEqual((reviewer["findings"], reviewer["confirmed"]), (2, 1))
        self.assertEqual(reviewer["by_tier"]["opus"]["events"], 1)
        architect = roles["architect"]
        self.assertEqual(architect["defects"], 1)
        self.assertEqual(architect.get("pre_run"), 1)
        return roles

    def test_parsers_and_aggregate_count_the_p0_review_and_one_pre_run_defect(self):
        reviewers, r_notes = rs.parse_reviewers(NOTES)
        defects, d_notes = rs.parse_defects(NOTES)
        self.assertEqual((r_notes, d_notes), ([], []))
        self.assertEqual([e["phase"] for e in reviewers], ["P0"])
        self.assertEqual(defects, [{"task": "T1", "kind": "stale-pin", "when": "pre-run"}])
        self._assert_counted([{"kit": "fixture", "agents": [],
                               "reviewers": reviewers, "defects": defects}])

    def test_a_fixture_kit_on_disk_reaches_the_history_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            kits = Path(tmp) / ".claude" / "kits"
            kit = kits / "fixture"
            kit.mkdir(parents=True)
            (kit / "TASKS.md").write_text(TASKS, encoding="utf-8")
            (kit / "NOTES.md").write_text(NOTES, encoding="utf-8")
            records, notes = rs.scan_kits(kits)
            self.assertEqual(notes, [])
            self.assertEqual([r["kit"] for r in records], ["fixture"])
            self._assert_counted(records)
            card = rs.build_history(kits, records, {}, None, [])
        self.assertIn("caught pre-run: 1", rs.render_history_markdown(card))


if __name__ == "__main__":
    unittest.main()
