"""Offline selected-source observations for CT2; no user stores or live clients."""

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


BIN = Path(__file__).resolve().parent.parent / "bin"
SPEC = importlib.util.spec_from_file_location("ct2_context_readers_tests", BIN / "context_readers.py")
readers = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readers)
LEDGER_SPEC = importlib.util.spec_from_file_location("ct2_ledger_fixture", BIN / "attempt_ledger.py")
ledger_module = importlib.util.module_from_spec(LEDGER_SPEC)
LEDGER_SPEC.loader.exec_module(ledger_module)

LIMITS = {"max_sources": 4, "max_source_bytes": 4096,
          "max_total_bytes": 16384, "max_items": 16}
TASKS = ("### T1 — A task\n- status: pending\n- model: strong\n"
         "\n**Brief.** Implement the fixture.\n"
         "\n**Acceptance.** The fixture is parsed.\n"
         "\n**Verify.**\n```bash\ntrue\n```\n")


class SelectedSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.kit = ".claude/kits/alpha"
        kit = self.root / self.kit
        kit.mkdir(parents=True)
        (kit / "TASKS.md").write_text(TASKS)

    def read(self, **overrides):
        kwargs = dict(repository_bindings={"repo-a": self.root},
                      repository_id="repo-a", kit_path=self.kit,
                      kit_files=("TASKS.md",), limits=LIMITS)
        kwargs.update(overrides)
        return readers.read_sources(**kwargs)

    def test_explicit_tasks_only_does_not_select_graph_or_evidence(self):
        report = self.read()
        self.assertEqual(report["v"], "polytropos.context-sources/1")
        self.assertEqual(report["subject"],
                         {"repository_id": "repo-a", "kit_path": self.kit})
        self.assertEqual([(s["kind"], s["state"]) for s in report["sources"]],
                         [("kit:TASKS.md", "ok")])
        self.assertEqual(report["reads"]["selected"], 1)
        self.assertEqual(report["reads"]["opened"], 2)
        self.assertGreater(report["reads"]["bytes"], 0)
        self.assertEqual(report["sources"][0]["consistency"], "consistent-at-read")
        self.assertEqual(report["sources"][0]["freshness"],
                         {"state": "unknown", "basis": "not-assessed"})

    def test_missing_selected_file_is_a_source_outcome(self):
        report = self.read(kit_files=("NOTES.md",))
        self.assertEqual([(s["kind"], s["state"]) for s in report["sources"]],
                         [("kit:NOTES.md", "missing")])
        self.assertEqual(report["reads"]["bytes"], 0)

    def test_unbound_repository_is_a_config_error(self):
        with self.assertRaises(ValueError):
            self.read(repository_id="repo-b")

    def test_same_named_kit_in_two_repositories_keeps_subject_binding(self):
        second = self.root / "second-repository"
        second.mkdir()
        kit = second / self.kit
        kit.mkdir(parents=True)
        (kit / "TASKS.md").write_text(TASKS.replace("fixture", "other"))
        first = self.read(repository_bindings={"repo-a": self.root, "repo-b": second})
        other = self.read(repository_bindings={"repo-a": self.root, "repo-b": second},
                          repository_id="repo-b")
        self.assertNotEqual(first["subject"], other["subject"])
        self.assertEqual(first["sources"][0]["state"], "ok")
        self.assertEqual(other["sources"][0]["state"], "ok")
        self.assertNotEqual(first["sources"][0]["ref"], other["sources"][0]["ref"])

    def test_other_supported_kit_layout_is_selected_without_search(self):
        kit_path = "tasks/kits/alpha"
        kit = self.root / kit_path
        kit.mkdir(parents=True)
        (kit / "TASKS.md").write_text(TASKS)
        report = self.read(kit_path=kit_path)
        self.assertEqual(report["subject"]["kit_path"], kit_path)
        self.assertEqual(report["sources"][0]["state"], "ok")

    def test_graph_present_does_not_trigger_source_file_reads(self):
        graph = self.root / "graphify-out" / "graph.json"
        graph.parent.mkdir()
        graph.write_text(json.dumps({"version": "fixture-0.1", "directed": True,
                                     "nodes": [{"id": "secret", "name": "secret",
                                                "source_file": "credential.txt"}],
                                     "links": []}))
        credential = self.root / "credential.txt"
        credential.write_text("synthetic credential")
        real_open = os.open
        attempted = []

        def traced_open(path, *args, **kwargs):
            attempted.append(str(path))
            return real_open(path, *args, **kwargs)

        with mock.patch("os.open", side_effect=traced_open):
            report = self.read(kit_files=(), graph_path="graphify-out/graph.json",
                               deny_prefixes=("credential.txt",))
        self.assertEqual(report["sources"][0]["kind"], "graph")
        self.assertNotIn("credential.txt", attempted)
        self.assertNotIn("credential.txt", json.dumps(report))

    def test_invalid_json_is_corrupt_not_an_exception_or_content_echo(self):
        graph = self.root / "graph.json"
        graph.write_text('{"nodes": [NaN], "secret": "AKIAIOSFODNN7EXAMPLE"}')
        report = self.read(kit_files=(), graph_path="graph.json")
        self.assertEqual(report["sources"][0]["state"], "corrupt")
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", json.dumps(report))

    def test_nonfinite_json_exponent_is_corrupt(self):
        (self.root / "graph.json").write_text(
            '{"version":"fixture-0.1","directed":true,"nodes":[1e999],"links":[]}')
        report = self.read(kit_files=(), graph_path="graph.json")
        self.assertEqual(report["sources"][0]["state"], "corrupt")

    def test_duplicate_json_keys_are_corrupt(self):
        (self.root / "graph.json").write_text(
            '{"version":"fixture-0.1","directed":true,"nodes":[],"nodes":[],"links":[]}')
        report = self.read(kit_files=(), graph_path="graph.json")
        self.assertEqual(report["sources"][0]["state"], "corrupt")

    def test_graph_collections_cannot_be_strings(self):
        graph = self.root / "graph.json"
        for field in ("nodes", "links"):
            with self.subTest(field=field):
                payload = {"version": "fixture-0.1", "directed": True,
                           "nodes": [], "links": []}
                payload[field] = "not-a-collection"
                graph.write_text(json.dumps(payload))
                report = self.read(kit_files=(), graph_path="graph.json")
                self.assertEqual(report["sources"][0]["state"], "corrupt")

    def test_source_limit_stops_before_opening_later_selection(self):
        (self.root / self.kit / "PLAN.md").write_text("# Plan\n")
        report = self.read(kit_files=("TASKS.md", "PLAN.md"),
                           limits={**LIMITS, "max_sources": 1})
        self.assertEqual(report["reads"]["selected"], 1)
        self.assertFalse(report["coverage"]["complete"])
        self.assertEqual(report["coverage"]["stopped_by"], "max_sources")

    def test_no_implicit_evidence_store_when_unbound(self):
        report = self.read(evidence_bindings=None)
        self.assertEqual([s["kind"] for s in report["sources"]], ["kit:TASKS.md"])

    def test_invalid_kit_file_name_is_configuration_error(self):
        for filename in ("../../private.txt", "events.jsonl", "TASKS.md/other"):
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                self.read(kit_files=(filename,))

    def test_nonstring_kit_file_is_configuration_error_before_open(self):
        for filename in ({"name": "TASKS.md"}, ["TASKS.md"], 12, None):
            with self.subTest(filename=filename):
                attempted = []
                real_open = os.open

                def traced_open(path, *args, **kwargs):
                    attempted.append(str(path))
                    return real_open(path, *args, **kwargs)

                with mock.patch("os.open", side_effect=traced_open):
                    with self.assertRaises(ValueError):
                        self.read(kit_files=(filename,))
                self.assertNotIn("TASKS.md", attempted)

    def test_noncanonical_deny_prefix_is_configuration_error_before_open(self):
        attempted = []
        real_open = os.open

        def traced_open(path, *args, **kwargs):
            attempted.append(str(path))
            return real_open(path, *args, **kwargs)

        with mock.patch("os.open", side_effect=traced_open):
            with self.assertRaises(ValueError):
                self.read(deny_prefixes=("private//",))
        self.assertNotIn("TASKS.md", attempted)

    def test_denied_kit_path_never_opens_selected_content(self):
        attempted = []
        real_open = os.open

        def traced_open(path, *args, **kwargs):
            attempted.append(str(path))
            return real_open(path, *args, **kwargs)

        with mock.patch("os.open", side_effect=traced_open):
            report = self.read(deny_prefixes=(self.kit,))
        self.assertEqual(report["sources"][0]["state"], "forbidden")
        self.assertNotIn("TASKS.md", attempted)
        self.assertEqual(report["reads"]["bytes"], 0)

    def test_denial_does_not_match_lexical_sibling(self):
        report = self.read(deny_prefixes=(".claude/kits/al",))
        self.assertEqual(report["sources"][0]["state"], "ok")

    def test_denied_selected_graph_is_not_opened(self):
        graph = self.root / "private" / "graph.json"
        graph.parent.mkdir()
        graph.write_text('{"private":"synthetic-secret-marker"}')
        attempted = []
        real_open = os.open

        def traced_open(path, *args, **kwargs):
            attempted.append(str(path))
            return real_open(path, *args, **kwargs)

        with mock.patch("os.open", side_effect=traced_open):
            report = self.read(kit_files=(), graph_path="private/graph.json",
                               deny_prefixes=("private",))
        self.assertEqual(report["sources"][0]["state"], "forbidden")
        self.assertNotIn("graph.json", attempted)
        self.assertNotIn("synthetic-secret-marker", json.dumps(report))

    def test_credential_shape_in_task_text_is_redacted_from_observation(self):
        credential = "AKIAIOSFODNN7EXAMPLE"
        (self.root / self.kit / "TASKS.md").write_text(
            TASKS.replace("Implement the fixture.", f"Implement {credential}."))
        report = self.read()
        self.assertEqual(report["sources"][0]["state"], "ok")
        self.assertNotIn(credential, json.dumps(report))
        self.assertGreaterEqual(sum(report["sources"][0]["redactions"].values()), 1)

    def test_read_does_not_probe_home_cwd_or_run_git(self):
        with (mock.patch.object(Path, "home", side_effect=AssertionError("home lookup")),
              mock.patch("os.getcwd", side_effect=AssertionError("cwd lookup")),
              mock.patch.object(subprocess, "run", side_effect=AssertionError("process")),
              mock.patch.object(subprocess, "Popen", side_effect=AssertionError("process"))):
            report = self.read()
        self.assertEqual(report["sources"][0]["state"], "ok")

    def test_graph_freshness_is_unknown_without_provenance(self):
        graph = self.root / "graph.json"
        graph.write_text(json.dumps({"version": "fixture-0.1", "directed": True,
                                     "nodes": [], "links": []}))
        report = self.read(kit_files=(), graph_path="graph.json")
        self.assertEqual(report["sources"][0]["freshness"]["state"], "unknown")

    def test_duplicate_kit_files_are_rejected_as_configuration_error(self):
        with self.assertRaises(ValueError):
            self.read(kit_files=("TASKS.md", "TASKS.md"))

    def test_explicit_ledger_binding_reads_writer_created_events(self):
        store = self.root / "fixture-store"
        ledger = ledger_module.AttemptLedger(store, "alpha")
        ledger.record_started("run-fixture", "T1", "initial", "fixture-model")
        report = self.read(kit_files=(), evidence_bindings={
            ("repo-a", self.kit): {"root": store, "events_rel": "alpha/events.jsonl"}})
        self.assertEqual([(s["kind"], s["state"]) for s in report["sources"]],
                         [("attempt-events", "ok")])
        self.assertEqual(report["sources"][0]["freshness"]["state"], "unknown")

    def test_evidence_bound_to_other_repository_does_not_join(self):
        store = self.root / "fixture-store"
        ledger = ledger_module.AttemptLedger(store, "alpha")
        ledger.record_started("run-fixture", "T1", "initial", "fixture-model")
        try:
            report = self.read(kit_files=(), evidence_bindings={
                ("repo-b", self.kit): {"root": store, "events_rel": "alpha/events.jsonl"}})
        except ValueError:
            return  # A misbound selection is also a valid configuration refusal.
        self.assertTrue(all(s["state"] != "ok" for s in report["sources"]))
        self.assertEqual(report["reads"]["opened"], 0)

    def test_deep_graph_json_is_corrupt_or_over_limit(self):
        graph = self.root / "graph.json"
        graph.write_text("[" * 700 + "0" + "]" * 700)
        report = self.read(kit_files=(), graph_path="graph.json")
        self.assertIn(report["sources"][0]["state"], {"corrupt", "over-limit"})

    def test_graph_item_ceiling_refuses_unbounded_observation(self):
        graph = self.root / "graph.json"
        nodes = [{"id": f"n{i}", "name": f"n{i}", "source_file": "app.py"}
                 for i in range(30)]
        graph.write_text(json.dumps({"version": "fixture-0.1", "directed": True,
                                     "nodes": nodes, "links": []}))
        report = self.read(kit_files=(), graph_path="graph.json",
                           limits={**LIMITS, "max_items": 4})
        self.assertEqual(report["sources"][0]["state"], "over-limit")
        self.assertFalse(report["sources"][0]["coverage"]["complete"])

    def test_source_byte_ceiling_does_not_silently_trim_tasks(self):
        (self.root / self.kit / "TASKS.md").write_text(TASKS + "x" * 500)
        report = self.read(limits={**LIMITS, "max_source_bytes": 100})
        self.assertEqual(report["sources"][0]["state"], "over-limit")
        self.assertFalse(report["sources"][0]["coverage"]["complete"])

    def test_total_byte_budget_stops_before_later_file_open(self):
        (self.root / self.kit / "PLAN.md").write_text("# Plan\n")
        exact_first = 2 * len(TASKS.encode("utf-8"))
        attempted = []
        real_open = os.open

        def traced_open(path, *args, **kwargs):
            attempted.append(str(path))
            return real_open(path, *args, **kwargs)

        with mock.patch("os.open", side_effect=traced_open):
            report = self.read(kit_files=("TASKS.md", "PLAN.md"),
                               limits={**LIMITS, "max_total_bytes": exact_first})
        self.assertEqual(report["reads"]["bytes"], exact_first)
        self.assertFalse(report["coverage"]["complete"])
        self.assertNotIn("PLAN.md", attempted)


if __name__ == "__main__":
    unittest.main()
