import contextlib
import importlib.util
import io
import json
import sys
import shutil
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "route_oracle_cost_report", ROOT / "bin" / "cost_report.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cr = _load()

_WORK_COUNTER = 0


@contextlib.contextmanager
def _workspace():
    global _WORK_COUNTER
    _WORK_COUNTER += 1
    root = ROOT / "tests" / ".route_oracle_workspace"
    path = root / f"case-{_WORK_COUNTER}"
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)
        try:
            root.rmdir()
        except OSError:
            pass


def _model(tier=None):
    pricing = cr.load_pricing()
    if tier is not None:
        for key, meta in pricing["models"].items():
            if meta.get("tier") == tier:
                return key
    return next(iter(pricing["models"]))


def _recent():
    return (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _old():
    return (datetime.now(timezone.utc) - timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_record(root, project, mid, model=None, session=None, ts=None, input_tokens=1000,
                  output_tokens=100, tool_uses=0):
    project_dir = Path(root) / project
    project_dir.mkdir(parents=True, exist_ok=True)
    content = [{"type": "tool_use", "name": "Tool"} for _ in range(tool_uses)]
    obj = {
        "timestamp": ts or _recent(),
        "sessionId": session or f"sess-{project}",
        "message": {
            "id": mid,
            "model": model or _model(),
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        },
    }
    if content:
        obj["message"]["content"] = content
    path = project_dir / f"{session or mid}.jsonl"
    with path.open("a") as f:
        f.write(json.dumps(obj) + "\n")
    return path


def _payload(projects_dir, **kwargs):
    return cr.build_report_payload(Path(projects_dir), days=30, top=10, mode=None, **kwargs)


def _run_main(argv):
    old_argv = sys.argv
    out = io.StringIO()
    err = io.StringIO()
    try:
        sys.argv = ["cost_report.py"] + list(argv)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                result = cr.main()
                code = 0
            except SystemExit as exc:
                result = exc
                code = exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.argv = old_argv
    return code, out.getvalue(), err.getvalue(), result


class NormalizeProjectPatternTests(unittest.TestCase):
    def test_none_normalizes_to_empty_list(self):
        self.assertEqual(cr.normalize_project_patterns(None), [])

    def test_single_pattern_list_is_preserved(self):
        self.assertEqual(cr.normalize_project_patterns(["alpha"]), ["alpha"])

    def test_comma_split_trims_and_preserves_order(self):
        got = cr.normalize_project_patterns([" alpha , beta* ", "gamma?"])
        self.assertEqual(got, ["alpha", "beta*", "gamma?"])

    def test_single_string_is_accepted(self):
        self.assertEqual(cr.normalize_project_patterns("alpha,beta"), ["alpha", "beta"])

    def test_empty_string_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "project filter patterns must not be empty"):
            cr.normalize_project_patterns("")

    def test_whitespace_string_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "project filter patterns must not be empty"):
            cr.normalize_project_patterns(["   "])

    def test_empty_comma_piece_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "project filter patterns must not be empty"):
            cr.normalize_project_patterns(["alpha,"])

    def test_forward_slash_pattern_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "project filters match project names only, not paths"):
            cr.normalize_project_patterns(["alpha/beta"])

    def test_backslash_pattern_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "project filters match project names only, not paths"):
            cr.normalize_project_patterns(["alpha\\beta"])


class ProjectMatchingTests(unittest.TestCase):
    def test_no_filters_allows_any_project(self):
        self.assertTrue(cr.project_allowed("anything", [], []))

    def test_include_exact_allows_matching_project(self):
        self.assertTrue(cr.project_allowed("alpha", ["alpha"], []))

    def test_include_exact_rejects_other_project(self):
        self.assertFalse(cr.project_allowed("beta", ["alpha"], []))

    def test_include_glob_allows_matching_project(self):
        self.assertTrue(cr.project_allowed("alpha-one", ["alpha-*"], []))

    def test_question_mark_glob_matches_one_character(self):
        self.assertTrue(cr.project_allowed("team-a", ["team-?"], []))

    def test_matching_is_case_sensitive(self):
        self.assertFalse(cr.project_allowed("Alpha", ["alpha"], []))

    def test_exclude_exact_rejects_project_without_include(self):
        self.assertFalse(cr.project_allowed("scratch", [], ["scratch"]))

    def test_exclude_glob_rejects_project(self):
        self.assertFalse(cr.project_allowed("scratch-one", [], ["scratch-*"]))

    def test_exclude_overrides_include(self):
        self.assertFalse(cr.project_allowed("alpha", ["alpha"], ["alpha"]))


class BuildPayloadFilterTests(unittest.TestCase):
    def test_payload_contains_normalized_project_filters(self):
        with _workspace() as td:
            Path(td, "alpha").mkdir()
            payload = _payload(td, project=[" alpha,beta* "], exclude_project="scratch?")
        self.assertEqual(payload["project_filters"], {
            "include": ["alpha", "beta*"],
            "exclude": ["scratch?"],
        })

    def test_include_exact_counts_only_selected_project(self):
        with _workspace() as td:
            _write_record(td, "alpha", "m1", session="s-alpha")
            _write_record(td, "beta", "m2", session="s-beta")
            payload = _payload(td, project=["alpha"])
        self.assertEqual(payload["totals"]["sessions"], 1)
        self.assertEqual([s["project"] for s in payload["sessions"]], ["alpha"])
        self.assertEqual(sum(b["messages"] for b in payload["by_model"]), 1)

    def test_include_glob_counts_multiple_matching_projects(self):
        with _workspace() as td:
            _write_record(td, "team-a", "m1", session="sa")
            _write_record(td, "team-b", "m2", session="sb")
            _write_record(td, "other", "m3", session="so")
            payload = _payload(td, project=["team-?"])
        self.assertEqual(payload["totals"]["sessions"], 2)
        self.assertEqual({s["project"] for s in payload["sessions"]}, {"team-a", "team-b"})

    def test_exclude_removes_matching_project(self):
        with _workspace() as td:
            _write_record(td, "alpha", "m1", session="s-alpha")
            _write_record(td, "scratch", "m2", session="s-scratch")
            payload = _payload(td, exclude_project=["scratch"])
        self.assertEqual({s["project"] for s in payload["sessions"]}, {"alpha"})

    def test_exclude_overrides_include_during_scan(self):
        with _workspace() as td:
            _write_record(td, "alpha", "m1", session="s-alpha")
            _write_record(td, "beta", "m2", session="s-beta")
            payload = _payload(td, project=["*"], exclude_project=["alpha"])
        self.assertEqual({s["project"] for s in payload["sessions"]}, {"beta"})

    def test_repeated_and_comma_patterns_are_all_applied(self):
        with _workspace() as td:
            _write_record(td, "alpha", "m1", session="sa")
            _write_record(td, "beta-one", "m2", session="sb")
            _write_record(td, "gamma", "m3", session="sg")
            payload = _payload(td, project=["alpha,beta-*", "missing"])
        self.assertEqual({s["project"] for s in payload["sessions"]}, {"alpha", "beta-one"})

    def test_no_matching_records_is_found_false_with_present_dir(self):
        with _workspace() as td:
            _write_record(td, "alpha", "m1")
            payload = _payload(td, project=["missing"])
        self.assertFalse(payload["found"])
        self.assertTrue(payload["dir_present"])
        self.assertEqual(payload["totals"], {"usd": 0.0, "sessions": 0, "tokens": 0})
        self.assertIn(f"no transcripts in window: {Path(td)}", payload["labels"])

    def test_missing_dir_payload_still_carries_filters(self):
        with _workspace() as td:
            missing = Path(td) / "missing"
            payload = _payload(missing, project="alpha", exclude_project="scratch")
        self.assertFalse(payload["dir_present"])
        self.assertEqual(payload["project_filters"], {"include": ["alpha"], "exclude": ["scratch"]})
        self.assertIn(f"transcript directory absent: {missing}", payload["labels"])

    def test_unknown_models_from_excluded_projects_are_ignored(self):
        with _workspace() as td:
            _write_record(td, "alpha", "m1")
            _write_record(td, "scratch", "m2", model="unknown-routing-model")
            payload = _payload(td, exclude_project=["scratch"])
        self.assertEqual(payload["unknown_models"], [])
        self.assertEqual({s["project"] for s in payload["sessions"]}, {"alpha"})

    def test_excluded_duplicate_message_id_does_not_poison_included_dedupe(self):
        with _workspace() as td:
            _write_record(td, "a-excluded", "same-id", model="unknown-routing-model")
            _write_record(td, "z-included", "same-id", session="included")
            payload = _payload(td, project=["*"], exclude_project=["a-*"])
        self.assertTrue(payload["found"])
        self.assertEqual(payload["totals"]["sessions"], 1)
        self.assertEqual(payload["sessions"][0]["project"], "z-included")
        self.assertEqual(payload["unknown_models"], [])

    def test_sessions_list_contains_only_included_projects(self):
        with _workspace() as td:
            _write_record(td, "keep", "m1", session="keep-session")
            _write_record(td, "drop", "m2", session="drop-session")
            payload = _payload(td, project=["keep"])
        self.assertEqual([s["session_id"] for s in payload["sessions"]], ["keep-session"])

    def test_downgrade_candidates_are_computed_only_from_included_projects(self):
        expensive = _model("frontier")
        with _workspace() as td:
            _write_record(td, "keep", "m1", model=expensive, session="keep-session", tool_uses=1)
            _write_record(td, "drop", "m2", model=expensive, session="drop-session", tool_uses=1)
            payload = _payload(td, project=["keep"])
        self.assertEqual([c["project"] for c in payload["downgrade_candidates"]], ["keep"])

    def test_old_records_in_selected_project_still_follow_days_window(self):
        with _workspace() as td:
            _write_record(td, "alpha", "old", ts=_old())
            payload = _payload(td, project=["alpha"])
        self.assertFalse(payload["found"])
        self.assertEqual(payload["sessions"], [])

    def test_filter_labels_are_added_only_when_active(self):
        with _workspace() as td:
            _write_record(td, "alpha", "m1")
            unfiltered = _payload(td)
            filtered = _payload(td, project=["alpha,beta"], exclude_project=["scratch*"])
        self.assertNotIn("project include: alpha", unfiltered["labels"])
        self.assertIn("project include: alpha, beta", filtered["labels"])
        self.assertIn("project exclude: scratch*", filtered["labels"])


class MainAndMarkdownFilterTests(unittest.TestCase):
    def test_json_main_applies_project_filter_and_reports_shape(self):
        with _workspace() as td:
            _write_record(td, "alpha", "m1", session="sa")
            _write_record(td, "beta", "m2", session="sb")
            code, out, err, _ = _run_main(["--json", "--projects-dir", td, "--project", "alpha"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["project_filters"], {"include": ["alpha"], "exclude": []})
        self.assertEqual([s["project"] for s in payload["sessions"]], ["alpha"])

    def test_json_main_applies_exclude_filter(self):
        with _workspace() as td:
            _write_record(td, "alpha", "m1", session="sa")
            _write_record(td, "beta", "m2", session="sb")
            code, out, err, _ = _run_main(["--json", "--projects-dir", td, "--exclude-project", "beta"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["project_filters"], {"include": [], "exclude": ["beta"]})
        self.assertEqual({s["project"] for s in payload["sessions"]}, {"alpha"})

    def test_cli_empty_pattern_exits_two(self):
        with _workspace() as td:
            code, out, err, _ = _run_main(["--json", "--projects-dir", td, "--project", "alpha,"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("project filter patterns must not be empty", err)

    def test_cli_path_pattern_exits_two(self):
        with _workspace() as td:
            code, out, err, _ = _run_main(["--json", "--projects-dir", td, "--exclude-project", "alpha/beta"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("project filters match project names only, not paths", err)

    def test_unfiltered_markdown_has_no_filter_line(self):
        with _workspace() as td:
            _write_record(td, "alpha", "m1")
            code, out, err, _ = _run_main(["--projects-dir", td])
        self.assertEqual(code, 0, err)
        self.assertIn("# Claude Code usage — last 30 days", out)
        self.assertNotIn("Project filters:", out)

    def test_filtered_markdown_has_exact_filter_line(self):
        with _workspace() as td:
            _write_record(td, "alpha", "m1")
            code, out, err, _ = _run_main([
                "--projects-dir", td, "--project", "alpha,beta*", "--exclude-project", "scratch?"
            ])
        self.assertEqual(code, 0, err)
        self.assertIn("Project filters: include `alpha`, `beta*`; exclude `scratch?`\n\n", out)
        self.assertLess(out.index("Project filters:"), out.index("**Total"))

    def test_filtered_markdown_include_only_clause(self):
        with _workspace() as td:
            _write_record(td, "alpha", "m1")
            code, out, err, _ = _run_main(["--projects-dir", td, "--project", "alpha"])
        self.assertEqual(code, 0, err)
        self.assertIn("Project filters: include `alpha`\n\n", out)
        self.assertNotIn("; exclude", out)

    def test_filtered_markdown_exclude_only_clause(self):
        with _workspace() as td:
            _write_record(td, "alpha", "m1")
            code, out, err, _ = _run_main(["--projects-dir", td, "--exclude-project", "scratch*"])
        self.assertEqual(code, 0, err)
        self.assertIn("Project filters: exclude `scratch*`\n\n", out)
        self.assertNotIn("include `", out)


if __name__ == "__main__":
    unittest.main()
