"""Stdlib unittest regression suite for bin/lessons_promote.py (PLAN.md E2, evidence-loop kit).

SAFETY CONTRACT (binds every test in this file): every test that needs kit evidence points
``--kits-dir``/``--lessons-file`` at a fresh ``tempfile.TemporaryDirectory()`` fixture — never
the real ``.claude/kits`` or the real ``tasks/lessons.md``. The one exception is
``test_real_run_touches_only_gitignored_path``, which snapshots ``git status --porcelain``
before and after a real subprocess invocation of the tool (still with a synthetic
``--kits-dir``) to prove the default output path never modifies anything tracked; it cleans up
any file it creates.

``bin/`` is not a package; ``lessons_promote.py`` is loaded via importlib by absolute path,
mirroring ``tests/test_memory_store.py``.
"""

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lp = _load("lessons_promote")


def _write_notes(kit_dir, lines):
    kit_dir.mkdir(parents=True, exist_ok=True)
    (kit_dir / "NOTES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_capture(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = lp.main(argv)
    return rc, buf.getvalue()


def _run_capture_both(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = lp.main(argv)
    return rc, out.getvalue(), err.getvalue()


class DiscoverKitsTests(unittest.TestCase):
    def test_only_dirs_with_notes_md_are_discovered(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_notes(root / "kit-a", ["defect: T1 kind=foo"])
            (root / "kit-b").mkdir()  # no NOTES.md
            (root / "not-a-kit-file.txt").write_text("x", encoding="utf-8")
            found = lp.discover_kits(root)
            self.assertEqual([d.name for d in found], ["kit-a"])

    def test_missing_kits_dir_returns_empty(self):
        self.assertEqual(lp.discover_kits("/nonexistent/does-not-exist"), [])


class ClusterDefectsTests(unittest.TestCase):
    def setUp(self):
        self.scorecard = lp._load_scorecard_module()

    def test_recurrence_across_two_kits_becomes_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_notes(root / "kit-a", ["defect: T1 kind=unspecified-path"])
            _write_notes(root / "kit-b", ["defect: T9 kind=unspecified-path"])
            evidence, notes = lp.collect_defect_evidence(root, self.scorecard.parse_defects)
            self.assertEqual(notes, [])
            candidates, residue = lp.cluster_defects(evidence)
            self.assertIn("unspecified-path", candidates)
            self.assertEqual(candidates["unspecified-path"]["kits"], ["kit-a", "kit-b"])
            self.assertEqual(residue, {})

    def test_single_kit_kind_lands_in_residue(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_notes(root / "kit-a", ["defect: T1 kind=stale-pin",
                                          "defect: T2 kind=stale-pin"])
            evidence, notes = lp.collect_defect_evidence(root, self.scorecard.parse_defects)
            candidates, residue = lp.cluster_defects(evidence)
            self.assertEqual(candidates, {})
            self.assertIn("stale-pin", residue)
            self.assertEqual(residue["stale-pin"]["kits"], ["kit-a"])
            self.assertEqual(len(residue["stale-pin"]["evidence"]), 2)

    def test_three_kit_recurrence_is_still_one_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_notes(root / "kit-a", ["defect: T1 kind=contradictory-acceptance"])
            _write_notes(root / "kit-b", ["defect: T2 kind=contradictory-acceptance"])
            _write_notes(root / "kit-c", ["defect: T3 kind=contradictory-acceptance"])
            evidence, _ = lp.collect_defect_evidence(root, self.scorecard.parse_defects)
            candidates, residue = lp.cluster_defects(evidence)
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates["contradictory-acceptance"]["kits"],
                              ["kit-a", "kit-b", "kit-c"])
            self.assertEqual(residue, {})

    def test_no_fuzzy_matching_between_similar_kinds(self):
        """`stale-pin` and `stale-plan-decision` share a prefix but are DIFFERENT tokens —
        they must never merge into one cluster even though each alone is single-kit.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_notes(root / "kit-a", ["defect: T1 kind=stale-pin"])
            _write_notes(root / "kit-b", ["defect: T2 kind=stale-plan-decision"])
            evidence, _ = lp.collect_defect_evidence(root, self.scorecard.parse_defects)
            candidates, residue = lp.cluster_defects(evidence)
            self.assertEqual(candidates, {})
            self.assertEqual(set(residue.keys()), {"stale-pin", "stale-plan-decision"})

    def test_kit_level_defect_task_dash_is_preserved_verbatim(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_notes(root / "kit-a", ["defect: - kind=stale-plan-decision"])
            _write_notes(root / "kit-b", ["defect: - kind=stale-plan-decision"])
            evidence, _ = lp.collect_defect_evidence(root, self.scorecard.parse_defects)
            candidates, _ = lp.cluster_defects(evidence)
            tasks = {e["task"] for e in candidates["stale-plan-decision"]["evidence"]}
            self.assertEqual(tasks, {"-"})

    def test_malformed_defect_line_note_is_kit_prefixed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_notes(root / "kit-a", ["defect: T1 nokindhere"])
            _, notes = lp.collect_defect_evidence(root, self.scorecard.parse_defects)
            self.assertTrue(any(n.startswith("kit-a:") for n in notes))


class LoadLessonsTests(unittest.TestCase):
    def test_parses_valid_jsonl_entries(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "lessons.md"
            f.write_text(
                json.dumps({"date": "2026-01-01", "failure_pattern": "fp1", "lesson": "l1",
                            "applies_to": ["routing"]}) + "\n" +
                json.dumps({"date": "2026-01-02", "failure_pattern": "fp2", "lesson": "l2",
                            "applies_to": []}) + "\n",
                encoding="utf-8")
            lessons, notes = lp.load_lessons(f)
            self.assertEqual(len(lessons), 2)
            self.assertEqual(notes, [])
            self.assertEqual(lessons[0]["failure_pattern"], "fp1")

    def test_malformed_line_is_skipped_with_note_not_a_crash(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "lessons.md"
            f.write_text(
                json.dumps({"date": "2026-01-01", "failure_pattern": "fp1", "lesson": "l1"}) +
                "\n" + "{this is not valid json" + "\n" +
                json.dumps({"date": "2026-01-03", "failure_pattern": "fp3", "lesson": "l3"}) +
                "\n",
                encoding="utf-8")
            lessons, notes = lp.load_lessons(f)
            self.assertEqual(len(lessons), 2)
            self.assertEqual(len(notes), 1)
            self.assertIn("line 2", notes[0])

    def test_missing_required_field_is_skipped_with_note(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "lessons.md"
            f.write_text(json.dumps({"date": "2026-01-01", "lesson": "no failure_pattern"}) +
                         "\n", encoding="utf-8")
            lessons, notes = lp.load_lessons(f)
            self.assertEqual(lessons, [])
            self.assertEqual(len(notes), 1)

    def test_blank_lines_are_skipped_silently(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "lessons.md"
            f.write_text(
                "\n" +
                json.dumps({"date": "2026-01-01", "failure_pattern": "fp1", "lesson": "l1"}) +
                "\n\n",
                encoding="utf-8")
            lessons, notes = lp.load_lessons(f)
            self.assertEqual(len(lessons), 1)
            self.assertEqual(notes, [])

    def test_missing_file_notes_and_returns_empty(self):
        lessons, notes = lp.load_lessons("/nonexistent/lessons.md")
        self.assertEqual(lessons, [])
        self.assertEqual(len(notes), 1)
        self.assertIn("not found", notes[0])


class RenderDraftReadsAsDraftTests(unittest.TestCase):
    def test_candidate_section_carries_evidence_and_draft_language(self):
        candidates = {"unspecified-path": {
            "kits": ["kit-a", "kit-b"],
            "evidence": [{"kit": "kit-a", "task": "T1", "kind": "unspecified-path"},
                         {"kit": "kit-b", "task": "T9", "kind": "unspecified-path"}],
        }}
        residue = {"stale-pin": {
            "kits": ["kit-a"],
            "evidence": [{"kit": "kit-a", "task": "T2", "kind": "stale-pin"}],
        }}
        draft = lp.render_draft(candidates, residue, [], [], kits_scanned=2, today="2026-07-26")
        self.assertIn("DRAFT", draft)
        self.assertIn("human review required", draft)
        self.assertIn("kit=kit-a task=T1 kind=unspecified-path", draft)
        self.assertIn("kit=kit-b task=T9 kind=unspecified-path", draft)
        # Residue reported verbatim, never merged into the candidate section.
        self.assertIn("Residue", draft)
        self.assertIn("kit=kit-a task=T2 kind=stale-pin", draft)

    def test_lessons_section_lists_entries_verbatim_and_uncustered(self):
        lessons = [{"date": "2026-01-01", "failure_pattern": "fp1", "lesson": "l1",
                    "applies_to": ["routing"]}]
        draft = lp.render_draft({}, {}, lessons, [], kits_scanned=0, today="2026-07-26")
        self.assertIn("fp1", draft)
        self.assertIn("l1", draft)
        self.assertIn("cannot satisfy the kit-recurrence gate", draft)

    def test_empty_everything_prints_friendly_lines_not_fabrication(self):
        draft = lp.render_draft({}, {}, [], [], kits_scanned=0, today="2026-07-26")
        self.assertIn("No defect kind met", draft)
        self.assertIn("No entries.", draft)
        self.assertIn("No residue.", draft)


class CliBehaviorTests(unittest.TestCase):
    def _fixture(self, td):
        root = Path(td)
        kits_dir = root / "kits"
        _write_notes(kits_dir / "kit-a", ["defect: T1 kind=unspecified-path"])
        _write_notes(kits_dir / "kit-b", ["defect: T9 kind=unspecified-path",
                                          "defect: T3 kind=stale-pin"])
        lessons_file = root / "lessons.md"
        lessons_file.write_text(
            json.dumps({"date": "2026-01-01", "failure_pattern": "fp1", "lesson": "l1",
                        "applies_to": ["routing"]}) + "\n", encoding="utf-8")
        return kits_dir, lessons_file

    def test_print_writes_nothing_to_disk(self):
        with tempfile.TemporaryDirectory() as td:
            kits_dir, lessons_file = self._fixture(td)
            out_dir = Path(td) / "out"
            rc, out = _run_capture([
                "--kits-dir", str(kits_dir), "--lessons-file", str(lessons_file),
                "--output-dir", str(out_dir), "--now", "2026-07-26", "--print"])
            self.assertEqual(rc, 0)
            self.assertIn("unspecified-path", out)
            self.assertFalse(out_dir.exists(), "--print must not create the output dir")

    def test_default_mode_writes_only_under_output_dir(self):
        with tempfile.TemporaryDirectory() as td:
            kits_dir, lessons_file = self._fixture(td)
            out_dir = Path(td) / "out"
            rc, stdout = _run_capture([
                "--kits-dir", str(kits_dir), "--lessons-file", str(lessons_file),
                "--output-dir", str(out_dir), "--now", "2026-07-26"])
            self.assertEqual(rc, 0)
            written = out_dir / "2026-07-26.md"
            self.assertTrue(written.is_file())
            content = written.read_text(encoding="utf-8")
            self.assertIn("unspecified-path", content)
            self.assertIn(str(written), stdout)
            # nothing else appeared under out_dir
            all_files = sorted(p.relative_to(out_dir) for p in out_dir.rglob("*") if p.is_file())
            self.assertEqual(all_files, [Path("2026-07-26.md")])

    def test_gate_split_end_to_end_via_cli(self):
        with tempfile.TemporaryDirectory() as td:
            kits_dir, lessons_file = self._fixture(td)
            out_dir = Path(td) / "out"
            _run_capture([
                "--kits-dir", str(kits_dir), "--lessons-file", str(lessons_file),
                "--output-dir", str(out_dir), "--now", "2026-07-26", "--print"])
            rc, out = _run_capture([
                "--kits-dir", str(kits_dir), "--lessons-file", str(lessons_file),
                "--output-dir", str(out_dir), "--now", "2026-07-26", "--print"])
            # unspecified-path recurs in kit-a + kit-b -> candidate
            candidate_idx = out.index("## Candidates")
            residue_idx = out.index("## Residue")
            self.assertIn("unspecified-path", out[candidate_idx:residue_idx])
            # stale-pin appears only in kit-b -> residue, not a candidate
            self.assertNotIn("stale-pin", out[candidate_idx:residue_idx])
            self.assertIn("stale-pin", out[residue_idx:])


class OutputContainmentTests(unittest.TestCase):
    """The kit's defining fence, enforced rather than asserted in a docstring.

    Before this, ``main()`` did ``Path(args.output_dir).mkdir(...)`` then wrote to
    ``out_dir / f"{args.now}.md"`` with no validation of either value, so
    ``--now '../../CLAUDE'`` escaped the output dir and overwrote a tracked file — while the
    confirmation line printed the unresolved path, hiding where the write landed.
    """

    def _fixture(self, td):
        root = Path(td)
        kits_dir = root / "kits"
        _write_notes(kits_dir / "kit-a", ["defect: T1 kind=unspecified-path"])
        lessons_file = root / "lessons.md"
        lessons_file.write_text("", encoding="utf-8")
        return kits_dir, lessons_file

    def test_traversing_now_is_refused_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            kits_dir, lessons_file = self._fixture(td)
            out_dir = Path(td) / "promotions"
            decoy = Path(td) / "CLAUDE.md"
            decoy.write_text("ORIGINAL TRACKED CONTENT\n", encoding="utf-8")
            rc, stdout, stderr = _run_capture_both([
                "--kits-dir", str(kits_dir), "--lessons-file", str(lessons_file),
                "--output-dir", str(out_dir), "--now", "../CLAUDE"])
            self.assertNotEqual(rc, 0, "a traversing --now must exit nonzero")
            self.assertIn("--now", stderr)
            self.assertEqual(decoy.read_text(encoding="utf-8"), "ORIGINAL TRACKED CONTENT\n",
                             "the traversal target must be untouched")
            self.assertFalse(out_dir.exists(),
                             "a refused run must not even create the output dir")
            self.assertEqual(stdout, "")

    def test_now_with_path_separator_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            kits_dir, lessons_file = self._fixture(td)
            out_dir = Path(td) / "promotions"
            rc, _, stderr = _run_capture_both([
                "--kits-dir", str(kits_dir), "--lessons-file", str(lessons_file),
                "--output-dir", str(out_dir), "--now", "sub/2026-07-26"])
            self.assertNotEqual(rc, 0)
            self.assertIn("path separator", stderr)
            self.assertFalse(out_dir.exists())

    def test_empty_now_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            kits_dir, lessons_file = self._fixture(td)
            rc, _, stderr = _run_capture_both([
                "--kits-dir", str(kits_dir), "--lessons-file", str(lessons_file),
                "--output-dir", str(Path(td) / "out"), "--now", "   "])
            self.assertNotEqual(rc, 0)
            self.assertIn("empty", stderr)

    def test_containment_holds_independently_of_the_now_pattern_check(self):
        """``resolve_output_path`` is the load-bearing guarantee: validating ``--now`` is the
        cheap early failure, but containment is what holds for anything the pattern misses —
        here, an output name that is a SYMLINK pointing out of the directory.
        """
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "promotions"
            out_dir.mkdir()
            outside = Path(td) / "outside.md"
            outside.write_text("DO NOT CLOBBER\n", encoding="utf-8")
            (out_dir / "2026-07-26.md").symlink_to(outside)
            path, err = lp.resolve_output_path(out_dir, "2026-07-26")
            self.assertIsNone(path)
            self.assertIn("refusing to write outside --output-dir", err)
            self.assertEqual(outside.read_text(encoding="utf-8"), "DO NOT CLOBBER\n")

    def test_validate_now_token_accepts_a_plain_date(self):
        self.assertIsNone(lp.validate_now_token("2026-07-26"))

    def test_output_dir_outside_the_repo_is_a_legitimate_operator_choice(self):
        """Containment restricts the write to WITHIN --output-dir; it does not restrict where
        --output-dir may be. An operator pointing the draft at a scratch dir outside the repo
        is supported and must keep working.
        """
        with tempfile.TemporaryDirectory() as td:
            kits_dir, lessons_file = self._fixture(td)
            out_dir = Path(td) / "elsewhere" / "drafts"
            self.assertFalse(str(out_dir.resolve()).startswith(str(REPO_ROOT.resolve()) + "/"),
                             "fixture must genuinely sit outside the repo")
            rc, stdout, _ = _run_capture_both([
                "--kits-dir", str(kits_dir), "--lessons-file", str(lessons_file),
                "--output-dir", str(out_dir), "--now", "2026-07-26"])
            self.assertEqual(rc, 0)
            self.assertTrue((out_dir / "2026-07-26.md").is_file())
            self.assertIn(str((out_dir / "2026-07-26.md").resolve()), stdout)

    def test_confirmation_line_prints_the_resolved_path(self):
        """The operator's log must show where the file actually went, not the string they
        typed — an unresolved path is exactly what hid the traversal.
        """
        with tempfile.TemporaryDirectory() as td:
            kits_dir, lessons_file = self._fixture(td)
            out_dir = Path(td) / "out"
            out_dir.mkdir()
            unresolved = str(out_dir / "sub" / ".." )  # normalises to out_dir
            (out_dir / "sub").mkdir()
            rc, stdout, _ = _run_capture_both([
                "--kits-dir", str(kits_dir), "--lessons-file", str(lessons_file),
                "--output-dir", unresolved, "--now", "2026-07-26"])
            self.assertEqual(rc, 0)
            self.assertIn(str((out_dir / "2026-07-26.md").resolve()), stdout)
            self.assertNotIn("/..", stdout)


class EvidenceBaseHonestyTests(unittest.TestCase):
    """F2/F3/F4: the draft must not state a coverage figure more confident than its evidence."""

    def _draft(self, **kw):
        candidates = {"unspecified-path": {
            "kits": ["kit-a", "kit-b"],
            "evidence": [{"kit": "kit-a", "task": "T1", "kind": "unspecified-path"},
                         {"kit": "kit-b", "task": "T9", "kind": "unspecified-path"}],
        }}
        residue = {"stale-pin": {
            "kits": ["kit-a"],
            "evidence": [{"kit": "kit-a", "task": "T2", "kind": "stale-pin"}],
        }}
        kw.setdefault("kits_scanned", 27)
        kw.setdefault("today", "2026-07-26")
        return lp.render_draft(candidates, residue, [], [], **kw)

    def test_defect_recording_kit_count_is_printed_beside_the_scanned_count(self):
        draft = self._draft()
        self.assertIn("Kits with a NOTES.md (scanned): 27", draft)
        self.assertIn("Kits that recorded ANY `defect:` line: 2", draft)
        self.assertIn("gate-1 denominator", draft)
        # The 25 kits that contribute nothing are named as such, not silently averaged in.
        self.assertIn("25 contribute no defect evidence", draft)

    def test_what_is_not_scanned_is_stated(self):
        draft = self._draft()
        self.assertIn("Not scanned by this tool:", draft)
        for token in ("`reviewer:` lines", "`outcome:` results", "NOTES", "prose"):
            self.assertIn(token, draft)

    def test_per_kind_entries_carry_the_defect_recording_denominator(self):
        draft = self._draft()
        self.assertIn("recurs across 2 of 2 defect-recording kits", draft)
        self.assertIn("1 of 2 defect-recording kits", draft)

    def test_exposure_is_declared_uncomputable_rather_than_guessed(self):
        draft = self._draft()
        self.assertIn("no kit chronology", draft)
        self.assertIn("will not invent one", draft)
        # Residue must not read as "cleared".
        self.assertIn("insufficient evidence either way", draft)
        self.assertIn("exposure unknown", draft)

    def test_self_reference_is_labelled_and_the_live_kit_is_not_excluded(self):
        draft = self._draft(self_kit="kit-a")
        self.assertIn("Self-reference", draft)
        self.assertIn("currently-executing kit", draft)
        self.assertIn("`kit-a` as the currently-executing kit", draft)
        self.assertIn("contributed 2 of 3 defect evidence lines", draft)
        # Its evidence is still counted — exclusion would discard the freshest evidence.
        self.assertIn("kit=kit-a task=T1 kind=unspecified-path", draft)

    def test_self_kit_with_no_defect_lines_says_so_instead_of_printing_zero_of(self):
        draft = self._draft(self_kit="kit-zzz")
        self.assertIn("recorded no `defect:` line in this scan", draft)

    def test_per_kit_contribution_is_listed(self):
        draft = self._draft()
        self.assertIn("Per-kit defect evidence", draft)
        self.assertIn("- kit-a: 2", draft)
        self.assertIn("- kit-b: 1", draft)

    def test_gate_one_limits_are_stated_in_the_preamble(self):
        draft = self._draft()
        self.assertIn("What clearing gate 1 does NOT establish", draft)
        self.assertIn("Recurrence is not importance", draft)
        self.assertIn("SINGLE recurrence", draft)
        self.assertIn("already", draft)

    def test_kinds_already_in_scaffolding_are_flagged_as_authored_not_read(self):
        draft = self._draft()
        self.assertIn("Part of this list is already in the scaffolding", draft)
        self.assertIn("skills/architect/SKILL.md", draft)
        self.assertIn("AUTHORED", draft)
        self.assertIn("does not read that file at run time", draft)
        # stale-pin is in the authored list, so its residue entry carries the marker.
        self.assertIn("ALREADY named in skills/architect/SKILL.md (authored note)", draft)

    def test_scaffolding_marker_is_authored_text_not_a_run_time_read(self):
        """The marker must not couple this tool to routing scaffolding. Outside comments, the
        skill path may appear exactly once — as the authored display constant, never as a
        path the module opens.
        """
        src = (BIN_DIR / "lessons_promote.py").read_text(encoding="utf-8")
        code_mentions = [ln.strip() for ln in src.splitlines()
                        if "skills/architect/SKILL.md" in ln
                        and not ln.lstrip().startswith("#")]
        self.assertEqual(
            code_mentions,
            ['SCAFFOLDING_NOTE_SOURCE = "skills/architect/SKILL.md"'],
            "the architect skill path must appear only as the authored constant")

    def test_per_kit_evidence_counts_is_the_denominator_source(self):
        candidates = {"k1": {"kits": ["a", "b"], "evidence": [
            {"kit": "a", "task": "T1", "kind": "k1"}, {"kit": "b", "task": "T2", "kind": "k1"}]}}
        residue = {"k2": {"kits": ["a"], "evidence": [{"kit": "a", "task": "T3", "kind": "k2"}]}}
        self.assertEqual(lp.per_kit_evidence_counts(candidates, residue), {"a": 2, "b": 1})


class NoDispatchImportTests(unittest.TestCase):
    """Static source audit: the tool must import nothing that can dispatch a real CLI."""

    def test_source_has_no_subprocess_or_execute_module_imports(self):
        src = (BIN_DIR / "lessons_promote.py").read_text(encoding="utf-8")
        forbidden = ["import subprocess", "os.system", "claude_execute", "copilot_execute",
                    "codex_execute", "copilot_ralph"]
        for token in forbidden:
            self.assertNotIn(token, src, f"forbidden token {token!r} found in lessons_promote.py")

    def test_module_binds_only_inert_stdlib_modules(self):
        """Replaces a bare ``assertFalse(hasattr(lp, "subprocess"))``, which proved close to
        nothing and invited a false reading.

        That assertion checked one name in one namespace, but a reader naturally takes it as
        "subprocess is not reachable here" — and it is: ``subprocess`` lands in
        ``sys.modules`` anyway via ``routing_scorecard``'s own imports the moment
        ``_load_scorecard_module`` runs. So the negative-name check could pass while the
        process holds a live dispatch primitive, and the guarantee people think it gives is
        one it never gave.

        What IS worth asserting is the positive, exhaustive form: enumerate every module
        ``lessons_promote`` actually binds and require each to be one of the inert stdlib
        modules it declares. A new dispatch-capable import fails this by name. The real
        process-level proof stays where it belongs — the source audit above, plus
        ``NoScaffoldingWritesTests``, which runs the tool for real and diffs git status.
        """
        bound = {name: mod for name, mod in vars(lp).items()
                 if isinstance(mod, types.ModuleType)}
        self.assertTrue(bound, "expected lessons_promote to bind at least one module")
        allowed = {"argparse", "importlib", "json", "os", "sys"}
        for name, mod in sorted(bound.items()):
            self.assertIn(
                mod.__name__.split(".")[0], allowed,
                f"lessons_promote binds unexpected module {name}={mod.__name__!r}")


class NoScaffoldingWritesTests(unittest.TestCase):
    """PLAN/GUARDRAILS: never edits GUARDRAILS.md, skills/, CLAUDE.md, or agent files; output
    goes only to stdout or the gitignored journal/promotions path.
    """

    def test_real_run_touches_only_gitignored_path(self):
        before = subprocess.run(
            ["git", "status", "--porcelain"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True).stdout

        default_dir = REPO_ROOT / "journal" / "promotions"
        before_files = (set(p for p in default_dir.rglob("*") if p.is_file())
                        if default_dir.is_dir() else set())

        with tempfile.TemporaryDirectory() as td:
            kits_dir, lessons_file = self._make_fixture(td)
            written_path = default_dir / "9999-01-01.md"
            try:
                result = subprocess.run(
                    [sys.executable, str(BIN_DIR / "lessons_promote.py"),
                     "--kits-dir", str(kits_dir), "--lessons-file", str(lessons_file),
                     "--now", "9999-01-01"],
                    cwd=REPO_ROOT, capture_output=True, text=True, check=True)
                self.assertIn("9999-01-01.md", result.stdout)
                self.assertTrue(written_path.is_file())
                # The confirmation line carries the RESOLVED path.
                self.assertIn(str(written_path.resolve()), result.stdout)
                # The default path writes EXACTLY one file — no strays, no traversal.
                after_files = set(p for p in default_dir.rglob("*") if p.is_file())
                self.assertEqual(after_files - before_files, {written_path},
                                "the default run must create exactly one new file")
            finally:
                if written_path.exists():
                    written_path.unlink()

            after = subprocess.run(
                ["git", "status", "--porcelain"], cwd=REPO_ROOT,
                capture_output=True, text=True, check=True).stdout
            self.assertEqual(before, after,
                            "a real run must never change tracked-file status")

    @staticmethod
    def _make_fixture(td):
        root = Path(td)
        kits_dir = root / "kits"
        _write_notes(kits_dir / "kit-a", ["defect: T1 kind=some-kind"])
        lessons_file = root / "lessons.md"
        lessons_file.write_text("", encoding="utf-8")
        return kits_dir, lessons_file


if __name__ == "__main__":
    unittest.main()
