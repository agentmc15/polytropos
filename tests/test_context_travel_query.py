"""Offline CT4 query contract tests with explicit temporary bindings."""

import copy
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


BIN = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location("ct4_test_" + name, BIN / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ct = _load("context_travel")
query = _load("context_travel_query")

TASKS = ("### T1 — Synthetic task\n- status: pending\n- model: strong\n"
         "\n**Brief.** Explain the fixture.\n"
         "\n**Acceptance.** Criterion one must hold.\n"
         "\n**Verify.**\n```bash\ntrue\n```\n")


class QueryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.kit = ".claude/kits/alpha"
        kit_dir = self.root / self.kit
        kit_dir.mkdir(parents=True)
        (kit_dir / "TASKS.md").write_text(TASKS)
        self.config_dict = {
            "v": "polytropos.context-query-config/1",
            "repositories": [{"id": "repo-a", "root": str(self.root),
                              "kits": [{"path": self.kit, "kit_files": ["TASKS.md"],
                                        "graph_path": None, "evidence": None}]}],
            "deny_prefixes": [],
            "limits": {"max_sources": 2, "max_source_bytes": 4096,
                       "max_total_bytes": 8192, "max_items": 16},
            "max_output_bytes": 32768,
        }
        self.config = query.parse_config(json.dumps(self.config_dict).encode("utf-8"))
        self.request = ct.make_request("repo-a", "checkout-a", None, self.kit, "T1",
                                       "assignment-a", "implementer", "What is next?")
        self.assignment = {"repository_id": "repo-a", "checkout_id": "checkout-a",
                           "revision": None, "kit_path": self.kit, "task_id": "T1",
                           "assignment_id": "assignment-a", "assignment_role": "implementer",
                           "question": "What is next?"}

    def test_live_overview_and_brief_preserve_critical_criteria(self):
        overview = query.run_query(self.config, "overview", {"request": self.request})
        brief = query.run_query(self.config, "brief", {"request": self.request})
        self.assertEqual(overview["v"], "polytropos.context-query/1")
        self.assertEqual(overview["operation"], "overview")
        self.assertEqual(brief["operation"], "brief")
        self.assertIn("Criterion one must hold.",
                      json.dumps(brief["data"]))
        self.assertLessEqual(len(query.canonical_bytes(overview)), 32768)

    def test_plain_assignment_first_call_matches_sealed_request(self):
        for operation in ("overview", "brief"):
            with self.subTest(operation=operation):
                sealed = query.run_query(self.config, operation,
                                         {"request": self.request})
                plain = query.run_query(self.config, operation,
                                        {"assignment": self.assignment})
                self.assertEqual(plain, sealed)
                self.assertEqual(plain["data"]["request"], self.request)

    def test_assignment_form_is_exclusive_and_closed_before_reads(self):
        invalid = (
            {"assignment": self.assignment, "request": self.request},
            {"assignment": self.assignment, "view": {}},
            {"assignment": {**self.assignment, "root": str(self.root)}},
            {"assignment": {**self.assignment, "kit_files": ["TASKS.md"]}},
        )
        for args in invalid:
            with self.subTest(keys=list(args)):
                with mock.patch("os.open", side_effect=AssertionError("source read")):
                    with self.assertRaises(query.QueryError):
                        query.run_query(self.config, "overview", args)

    def test_text_render_preserves_criteria_or_refuses_small_budget(self):
        envelope = query.run_query(self.config, "brief", {"request": self.request})
        text = query.render_text(envelope, max_bytes=32768)
        self.assertIn("Criterion one must hold.", text)
        self.assertLessEqual(len(text.encode("utf-8")), 32768)
        with self.assertRaises(query.QueryError):
            query.render_text(envelope, max_bytes=1024)

    def test_imported_view_reuses_exact_artifact_without_source_read(self):
        live = query.run_query(self.config, "overview", {"request": self.request})
        view = live["data"]
        with mock.patch("os.open", side_effect=AssertionError("source rescan")):
            imported_overview = query.run_query(self.config, "overview", {"view": view})
            imported_brief = query.run_query(self.config, "brief", {"view": view})
            explained = query.run_query(self.config, "explain",
                                        {"view": view, "finding_id": None})
            compared = query.run_query(self.config, "changes",
                                       {"before": view, "after": view})
        self.assertEqual(imported_overview["data"], view)
        self.assertEqual(imported_brief["data"], view)
        self.assertEqual(explained["data"]["view_sha"], view["content_sha"])
        self.assertEqual(compared["data"]["kind"], "comparison")

    def test_tool_arguments_cannot_override_startup_bindings(self):
        for extra in ("repository_bindings", "root", "kit_files", "deny_prefixes", "limits",
                      "graph_path", "evidence_bindings"):
            with self.subTest(extra=extra):
                args = {"request": self.request, extra: None}
                with self.assertRaises(query.QueryError):
                    query.run_query(self.config, "overview", args)

    def test_unknown_config_field_is_refused(self):
        bad = copy.deepcopy(self.config_dict)
        bad["credential_source"] = "synthetic"
        with self.assertRaises(query.QueryError):
            query.parse_config(json.dumps(bad))

    def test_duplicate_repository_and_kit_bindings_are_refused(self):
        for mutation in (
            lambda c: c["repositories"].append(copy.deepcopy(c["repositories"][0])),
            lambda c: c["repositories"][0]["kits"].append(
                copy.deepcopy(c["repositories"][0]["kits"][0])),
        ):
            bad = copy.deepcopy(self.config_dict)
            mutation(bad)
            with self.assertRaises(query.QueryError):
                query.parse_config(json.dumps(bad))

    def test_config_rejects_duplicate_json_nonfinite_and_nested_unknown(self):
        malformed = (
            '{"v":"polytropos.context-query-config/1","v":"other"}',
            json.dumps(self.config_dict).replace('"max_output_bytes": 32768',
                                                 '"max_output_bytes": 1e999'),
        )
        for raw in malformed:
            with self.subTest(raw=raw[:20]), self.assertRaises(query.QueryError):
                query.parse_config(raw)
        bad = copy.deepcopy(self.config_dict)
        bad["repositories"][0]["kits"][0]["read_all"] = True
        with self.assertRaises(query.QueryError):
            query.parse_config(json.dumps(bad))

    def test_config_output_ceiling_is_enforced(self):
        for amount in (0, 1023, 32769):
            bad = copy.deepcopy(self.config_dict)
            bad["max_output_bytes"] = amount
            with self.subTest(amount=amount), self.assertRaises(query.QueryError):
                query.parse_config(json.dumps(bad))

    def test_unconfigured_repository_and_kit_are_refused(self):
        other_repo = ct.make_request("repo-b", "checkout-a", None, self.kit, "T1",
                                     "assignment-a", "implementer", "What is next?")
        other_kit = ct.make_request("repo-a", "checkout-a", None, ".claude/kits/beta",
                                    "T1", "assignment-a", "implementer", "What is next?")
        for request in (other_repo, other_kit):
            with self.subTest(subject=request["task_identity"]):
                with mock.patch("os.open", side_effect=AssertionError("source read")):
                    with self.assertRaises(query.QueryError):
                        query.run_query(self.config, "overview", {"request": request})

    def test_imported_view_subject_must_be_configured(self):
        live = query.run_query(self.config, "overview", {"request": self.request})
        other_config = copy.deepcopy(self.config_dict)
        other_config["repositories"][0]["id"] = "repo-b"
        parsed = query.parse_config(json.dumps(other_config))
        with self.assertRaises(query.QueryError):
            query.run_query(parsed, "brief", {"view": live["data"]})

    def test_capabilities_do_not_list_binding_roots(self):
        envelope = query.run_query(self.config, "capabilities", {})
        serialized = json.dumps(envelope)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn(self.kit, serialized)
        self.assertIn("overview", serialized)

    def test_config_load_refuses_symlink_leaf_and_parent(self):
        real = self.root / "config.json"
        real.write_text(json.dumps(self.config_dict))
        self.assertEqual(query.load_config(str(real)), self.config)
        alias = self.root / "alias.json"
        alias.symlink_to(real)
        with self.assertRaises(query.QueryError):
            query.load_config(str(alias))
        real_parent = self.root / "real-parent"
        real_parent.mkdir()
        (real_parent / "config.json").write_text(json.dumps(self.config_dict))
        alias_parent = self.root / "alias-parent"
        alias_parent.symlink_to(real_parent, target_is_directory=True)
        with self.assertRaises(query.QueryError):
            query.load_config(str(alias_parent / "config.json"))

    def test_config_loader_requires_explicit_absolute_path(self):
        for path in ("", "config.json", "../config.json"):
            with self.subTest(path=path), self.assertRaises(query.QueryError):
                query.load_config(path)

    def test_control_paths_reject_nul_and_newline_before_read(self):
        for bad_segment in ("\x00", "\n"):
            with self.subTest(segment=repr(bad_segment)):
                bad_root = copy.deepcopy(self.config_dict)
                bad_root["repositories"][0]["root"] = str(self.root) + bad_segment
                with mock.patch("os.open", side_effect=AssertionError("source read")):
                    with self.assertRaises(query.QueryError):
                        query.parse_config(json.dumps(bad_root))

                bad_evidence = copy.deepcopy(self.config_dict)
                bad_evidence["repositories"][0]["kits"][0]["evidence"] = {
                    "root": str(self.root) + bad_segment,
                    "events_rel": "alpha/events.jsonl"}
                with mock.patch("os.open", side_effect=AssertionError("source read")):
                    with self.assertRaises(query.QueryError):
                        query.parse_config(json.dumps(bad_evidence))

                with mock.patch("os.open", side_effect=AssertionError("config read")):
                    with self.assertRaises(query.QueryError):
                        query.load_config(str(self.root / "config.json") + bad_segment)

    def test_denied_kit_selection_opens_no_task_content(self):
        # Warm the public reader once so lazy sibling imports happen outside the
        # instrumented interval; importing while os.open is patched can capture
        # the mock in safe_paths' supported-operation constant.
        self.assertEqual(query.run_query(self.config, "overview",
                                         {"request": self.request})["data"]["status"],
                         "complete")
        denied = copy.deepcopy(self.config_dict)
        denied["deny_prefixes"] = [self.kit]
        config = query.parse_config(json.dumps(denied))
        real_open = os.open
        opened = []

        def tracing_open(path, *args, **kwargs):
            opened.append(str(path))
            return real_open(path, *args, **kwargs)

        with mock.patch("os.open", side_effect=tracing_open):
            envelope = query.run_query(config, "overview", {"request": self.request})
        self.assertNotIn("TASKS.md", opened)
        self.assertIn("forbidden", json.dumps(envelope["data"]))

    def test_symlinked_task_source_does_not_leak_outside_content(self):
        outside = self.root / "synthetic-secret.txt"
        marker = "synthetic-secret-marker"
        outside.write_text(marker)
        task_path = self.root / self.kit / "TASKS.md"
        task_path.unlink()
        task_path.symlink_to(outside)
        envelope = query.run_query(self.config, "overview", {"request": self.request})
        self.assertNotIn(marker, json.dumps(envelope))
        self.assertIn("forbidden", json.dumps(envelope["data"]))


if __name__ == "__main__":
    unittest.main()
