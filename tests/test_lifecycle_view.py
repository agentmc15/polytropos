"""Independent offline CT3 lifecycle projection tests."""

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


BIN = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location("ct3_test_" + name, BIN / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ct = _load("context_travel")
readers = _load("context_readers")
lv = _load("lifecycle_view")
ledger_module = _load("attempt_ledger")

TASKS = ("### T1 — Synthetic task\n- status: pending\n- model: strong\n"
         "\n**Brief.** Produce an offline fixture.\n"
         "\n**Acceptance.** Criterion one must hold.\n"
         "\n**Verify.**\n```bash\ntrue\n```\n")
LIMITS = {"max_sources": 2, "max_source_bytes": 4096,
          "max_total_bytes": 8192, "max_items": 16}


class LifecycleViewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.kit = ".claude/kits/alpha"
        kit_dir = self.root / self.kit
        kit_dir.mkdir(parents=True)
        (kit_dir / "TASKS.md").write_text(TASKS)
        self.request = ct.make_request("repo-a", "checkout-a", None, self.kit, "T1",
                                       "assignment-a", "implementer", "What is next?")
        self.sources = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=("TASKS.md",), limits=LIMITS)

    def compose(self, **overrides):
        args = {"request": self.request, "sources": self.sources, "role": "implementer"}
        args.update(overrides)
        return lv.compose_view(**args)

    def test_projection_preserves_subject_and_criteria_without_ready_claim(self):
        view = self.compose()
        self.assertEqual(view["v"], "polytropos.lifecycle-view/1")
        self.assertEqual(view["kind"], "projection")
        self.assertEqual(view["request"], self.request)
        self.assertEqual(view["subject"]["task_identity"], self.request["task_identity"])
        self.assertEqual(view["status"], "complete")
        self.assertEqual(view["overview"]["task_status"], "pending")
        self.assertIn("Criterion one must hold.", view["brief"]["criteria_text"])
        self.assertNotIn("ready", view)
        self.assertNotIn("accepted", view)

    def test_unselected_tasks_cannot_invent_acceptance(self):
        empty = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=(), limits=LIMITS)
        view = self.compose(sources=empty)
        self.assertEqual(view["status"], "partial")
        self.assertIsNone(view["brief"]["criteria_text"])
        self.assertTrue(any(item["critical"] for item in view["limitations"]))

    def test_missing_and_corrupt_selected_tasks_remain_distinct(self):
        path = self.root / self.kit / "TASKS.md"
        path.unlink()
        missing = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=("TASKS.md",), limits=LIMITS)
        missing_view = self.compose(sources=missing)
        self.assertEqual(missing_view["status"], "partial")
        self.assertIn("missing", [s["state"] for s in
                                  missing_view["overview"]["source_states"]])
        path.write_text(TASKS.replace("- status: pending", "- status: impossible"))
        corrupt = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=("TASKS.md",), limits=LIMITS)
        corrupt_view = self.compose(sources=corrupt)
        self.assertEqual(corrupt_view["status"], "partial")
        self.assertIn("corrupt", [s["state"] for s in
                                  corrupt_view["overview"]["source_states"]])
        self.assertNotEqual(missing_view["content_sha"], corrupt_view["content_sha"])

    def test_mismatched_source_subject_is_refused(self):
        wrong = copy.deepcopy(self.sources)
        wrong["subject"]["repository_id"] = "repo-b"
        with self.assertRaises(lv.ViewError):
            self.compose(sources=wrong)

    def test_composition_does_not_access_files_or_processes(self):
        with (mock.patch.object(Path, "open", side_effect=AssertionError("file open")),
              mock.patch("os.open", side_effect=AssertionError("fd open")),
              mock.patch.object(Path, "home", side_effect=AssertionError("home")),
              mock.patch("os.getcwd", side_effect=AssertionError("cwd")),
              mock.patch("os.getenv", side_effect=AssertionError("environment")),
              mock.patch.object(subprocess, "run", side_effect=AssertionError("process")),
              mock.patch.object(subprocess, "Popen", side_effect=AssertionError("process"))):
            view = self.compose()
        self.assertEqual(view["kind"], "projection")

    def test_returned_projection_cannot_mutate_request_or_sources(self):
        request_before = copy.deepcopy(self.request)
        sources_before = copy.deepcopy(self.sources)
        view = self.compose()
        view["request"]["question"]["text"] = "changed"
        view["overview"]["source_states"].clear()
        self.assertEqual(self.request, request_before)
        self.assertEqual(self.sources, sources_before)

    def test_source_read_telemetry_does_not_change_projection_identity(self):
        changed = copy.deepcopy(self.sources)
        changed["reads"]["opened"] += 1
        changed["reads"]["bytes"] += 1
        before = self.compose()
        after = self.compose(sources=changed)
        self.assertEqual(before["content_sha"], after["content_sha"])
        self.assertEqual(lv.canonical_bytes(before), lv.canonical_bytes(after))

    def test_all_critical_limitations_are_retained_in_role_brief(self):
        empty = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=(), limits=LIMITS)
        view = self.compose(sources=empty)
        critical = [item for item in view["limitations"] if item["critical"]]
        self.assertTrue(critical)
        self.assertEqual(view["brief"]["critical_limitations"], critical)

    def test_bounded_render_refuses_or_fails_without_trimmed_criteria(self):
        long_criterion = "A" * 3000
        (self.root / self.kit / "TASKS.md").write_text(
            TASKS.replace("Criterion one must hold.", long_criterion))
        sources = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=("TASKS.md",),
            limits={**LIMITS, "max_source_bytes": 4096, "max_total_bytes": 8192})
        try:
            view = self.compose(sources=sources, max_bytes=1800)
        except lv.ViewError:
            return  # Even the minimal refusal may exceed a caller's cap.
        self.assertLessEqual(len(lv.canonical_bytes(view)), 1800)
        self.assertEqual(view["status"], "refused")
        self.assertIsNone(view["brief"])

    def test_invalid_role_and_link_subjects_are_refused(self):
        with self.assertRaises(lv.ViewError):
            self.compose(role="verifier")
        wrong_subject = {"repository_id": "repo-b", "kit_path": self.kit,
                         "task_id": "T1"}
        link = {"subject": wrong_subject, "kind": "goal", "ref": None,
                "epistemic": "caller-declared"}
        with self.assertRaises(lv.ViewError):
            self.compose(intent_links=(link,))

    def test_projection_hash_round_trips_through_parser(self):
        view = self.compose()
        parsed = lv.parse_view(lv.canonical_bytes(view))
        self.assertEqual(parsed, view)
        tampered = copy.deepcopy(view)
        tampered["overview"]["task_status"] = "done"
        with self.assertRaises(lv.ViewError):
            lv.parse_view(json.dumps(tampered).encode("utf-8"))

    def test_legacy_attempt_with_same_task_id_is_unbound(self):
        store = self.root / "fixture-store"
        ledger = ledger_module.AttemptLedger(store, "alpha")
        ledger.record_started("run-fixture", "T1", "initial", "fixture-model")
        sources = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=("TASKS.md",),
            evidence_bindings={("repo-a", self.kit):
                               {"root": store, "events_rel": "alpha/events.jsonl"}},
            limits=LIMITS)
        view = self.compose(sources=sources)
        unbound = [item for item in view["findings"]
                   if item["applicability"] == "unbound"]
        self.assertTrue(unbound)
        self.assertFalse(any(item["claim"] == "task accepted" for item in unbound))

    def test_unbound_passing_verify_does_not_measure_this_task(self):
        store = self.root / "fixture-store"
        ledger = ledger_module.AttemptLedger(store, "alpha")
        attempt = ledger.record_started("run-old", "T1", "initial", "fixture-model")
        ledger.record_verify("run-old", "T1", attempt, 0, "OK")
        sources = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=("TASKS.md",),
            evidence_bindings={("repo-a", self.kit):
                               {"root": store, "events_rel": "alpha/events.jsonl"}},
            limits=LIMITS)
        view = self.compose(sources=sources)
        self.assertTrue(any(item["applicability"] == "unbound"
                            for item in view["findings"]))
        self.assertFalse(any(item["kind"] == "measured-verification"
                             for item in view["relationships"]))
        self.assertEqual(view["overview"]["task_status"], "pending")

    def test_precheck_from_other_run_cannot_validate_passing_verify(self):
        store = self.root / "fixture-store"
        ledger = ledger_module.AttemptLedger(store, "alpha")
        ledger.append("verify.precheck", run="run-A", task="T1",
                      tautological=False, rc=1, repository_id="repo-a",
                      kit_path=self.kit)
        attempt = ledger.record_started("run-B", "T1", "initial", "fixture-model",
                                        repository_id="repo-a", kit_path=self.kit)
        ledger.record_verify("run-B", "T1", attempt, 0, "OK",
                             repository_id="repo-a", kit_path=self.kit)
        sources = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=("TASKS.md",),
            evidence_bindings={("repo-a", self.kit):
                               {"root": store, "events_rel": "alpha/events.jsonl"}},
            limits=LIMITS)
        view = self.compose(sources=sources)
        self.assertTrue(any(item["kind"] == "measured-verification"
                            for item in view["relationships"]))
        self.assertTrue(any("precheck" in item["code"] and item["critical"]
                            for item in view["limitations"]))

    def test_late_precheck_same_run_cannot_validate_earlier_pass(self):
        (self.root / self.kit / "TASKS.md").write_text(
            TASKS.replace("- status: pending", "- status: done"))
        store = self.root / "fixture-store"
        ledger = ledger_module.AttemptLedger(store, "alpha")
        attempt = ledger.record_started("run-X", "T1", "initial", "fixture-model",
                                        repository_id="repo-a", kit_path=self.kit)
        ledger.record_verify("run-X", "T1", attempt, 0, "OK",
                             repository_id="repo-a", kit_path=self.kit)
        ledger.append("verify.precheck", run="run-X", task="T1",
                      tautological=False, rc=1, repository_id="repo-a",
                      kit_path=self.kit)
        sources = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=("TASKS.md",),
            evidence_bindings={("repo-a", self.kit):
                               {"root": store, "events_rel": "alpha/events.jsonl"}},
            limits=LIMITS)
        view = self.compose(sources=sources)
        self.assertTrue(any("precheck" in item["code"] and item["critical"]
                            for item in view["limitations"]))

    def test_comparison_separates_checkout_change_from_task_identity(self):
        before = self.compose()
        next_request = ct.make_request("repo-a", "checkout-b", "revision-b", self.kit,
                                       "T1", "assignment-a", "implementer", "What is next?")
        after = self.compose(request=next_request)
        comparison = lv.compare_views(before, after)
        self.assertEqual(comparison["kind"], "comparison")
        self.assertEqual(comparison["before_sha"], before["content_sha"])
        self.assertEqual(comparison["after_sha"], after["content_sha"])
        self.assertTrue(comparison["applicability_changes"])
        self.assertEqual(comparison["subject"]["task_identity"],
                         self.request["task_identity"])

    def test_comparison_refuses_different_stable_task_identity(self):
        before = self.compose()
        other_request = ct.make_request("repo-a", "checkout-a", None, self.kit,
                                        "T2", "assignment-a", "implementer", "What is next?")
        other = self.compose(request=other_request)
        with self.assertRaises(lv.ViewError):
            lv.compare_views(before, other)

    def test_comparable_source_ref_mismatch_is_visible_not_authenticated(self):
        selected_ref = self.sources["sources"][0]["ref"]
        different_ref = {**selected_ref, "sha": "0" * 64}
        self.assertNotEqual(different_ref, selected_ref)
        request = ct.make_request("repo-a", "checkout-a", None, self.kit, "T1",
                                  "assignment-a", "implementer", "What is next?",
                                  source_ref=different_ref)
        view = self.compose(request=request)
        self.assertEqual(view["status"], "partial")
        self.assertTrue(any("mismatch" in item["code"] and item["critical"]
                            for item in view["limitations"]))

    def test_unverifiable_source_state_pin_stays_unknown(self):
        source_state_ref = {"id": "declared-state", "sha": "f" * 64,
                            "v": "fixture-state/1"}
        request = ct.make_request("repo-a", "checkout-a", None, self.kit, "T1",
                                  "assignment-a", "implementer", "What is next?",
                                  source_state_ref=source_state_ref)
        view = self.compose(request=request)
        self.assertTrue(any("source-state" in item["code"] or
                            "source_state" in item["code"]
                            for item in view["limitations"]))
        self.assertTrue(all(s["freshness"]["state"] == "unknown"
                            for s in view["overview"]["source_states"]))

    def test_role_changes_focus_without_changing_underlying_findings(self):
        implementer = self.compose()
        verifier_request = ct.make_request("repo-a", "checkout-a", None, self.kit, "T1",
                                           "assignment-a", "verifier", "What is next?")
        verifier = self.compose(request=verifier_request, role="verifier")
        self.assertEqual({item["id"] for item in implementer["findings"]},
                         {item["id"] for item in verifier["findings"]})
        self.assertEqual({(item["kind"], item["claim"]) for item in implementer["findings"]},
                         {(item["kind"], item["claim"]) for item in verifier["findings"]})
        self.assertEqual(verifier["brief"]["role"], "verifier")

    def test_duplicate_declared_acceptance_link_is_refused(self):
        link = {"subject": {"repository_id": "repo-a", "kit_path": self.kit,
                            "task_id": "T1"},
                "ref": self.sources["sources"][0]["ref"],
                "epistemic": "caller-declared"}
        with self.assertRaises(lv.ViewError):
            self.compose(acceptance_links=(link, link))

    def test_declared_stale_dependency_is_warning_not_readiness_proof(self):
        (self.root / self.kit / "TASKS.md").write_text(
            TASKS.replace("- model: strong", "- model: strong\n- depends: T0"))
        sources = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=("TASKS.md",), limits=LIMITS)
        declaration = {"subject": {"repository_id": "repo-a", "kit_path": self.kit,
                                   "task_id": "T0"},
                       "state": "stale", "ref": sources["sources"][0]["ref"],
                       "epistemic": "caller-declared"}
        view = self.compose(sources=sources, dependency_freshness=(declaration,))
        self.assertTrue(any(item["kind"] == "declared-dependency"
                            for item in view["relationships"]))
        self.assertTrue(any("stale" in item["code"] for item in view["limitations"]))
        self.assertNotIn("ready", view)

    def test_malformed_source_version_counters_and_extra_fields_are_refused(self):
        changes = (
            lambda s: s.update(v="polytropos.context-sources/999"),
            lambda s: s["reads"].update(bytes=float("nan")),
            lambda s: s.update(unexpected="not part of CT2"),
        )
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                source = copy.deepcopy(self.sources)
                change(source)
                with self.assertRaises(lv.ViewError):
                    self.compose(sources=source)

    def test_comparison_rejects_tampered_projection_hash(self):
        before = self.compose()
        after = copy.deepcopy(before)
        after["overview"]["task_status"] = "done"
        with self.assertRaises(lv.ViewError):
            lv.compare_views(before, after)

    def test_acceptance_only_declared_ref_change_is_separate_from_criteria(self):
        subject = {"repository_id": "repo-a", "kit_path": self.kit, "task_id": "T1"}
        left_ref = {"id": "acceptance-a", "sha": "a" * 64, "v": "fixture/1"}
        right_ref = {"id": "acceptance-b", "sha": "b" * 64, "v": "fixture/1"}
        left = self.compose(acceptance_links=(
            {"subject": subject, "ref": left_ref, "epistemic": "caller-declared"},))
        right = self.compose(acceptance_links=(
            {"subject": subject, "ref": right_ref, "epistemic": "caller-declared"},))
        self.assertEqual(left["brief"]["criteria_text"], right["brief"]["criteria_text"])
        comparison = lv.compare_views(left, right)
        self.assertTrue(comparison["changes"])
        self.assertIn("acceptance", json.dumps(comparison["changes"]).lower())

    def test_done_and_passing_note_without_precheck_keeps_critical_unknown(self):
        kit_dir = self.root / self.kit
        (kit_dir / "TASKS.md").write_text(TASKS.replace("- status: pending", "- status: done"))
        (kit_dir / "NOTES.md").write_text(
            "outcome: T1 model=fixture attempts=1 result=pass review=none\n")
        sources = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=("TASKS.md", "NOTES.md"), limits=LIMITS)
        view = self.compose(sources=sources)
        self.assertEqual(view["overview"]["task_status"], "done")
        self.assertTrue(any("precheck" in item["code"] and item["critical"]
                            for item in view["limitations"]))
        self.assertNotIn("accepted", view)

    def test_tautological_precheck_event_cannot_prove_done_task(self):
        kit_dir = self.root / self.kit
        (kit_dir / "TASKS.md").write_text(TASKS.replace("- status: pending", "- status: done"))
        store = self.root / "fixture-store"
        ledger = ledger_module.AttemptLedger(store, "alpha")
        ledger.append("verify.precheck", run="run-fixture", task="T1",
                      tautological=True, rc=0)
        sources = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=("TASKS.md",),
            evidence_bindings={("repo-a", self.kit):
                               {"root": store, "events_rel": "alpha/events.jsonl"}},
            limits=LIMITS)
        view = self.compose(sources=sources)
        self.assertTrue(any("precheck" in item["code"] and item["critical"]
                            for item in view["limitations"]))
        self.assertTrue(any(item["applicability"] == "unbound"
                            for item in view["findings"]))

    def test_done_status_and_blocked_note_remain_visible_as_conflict(self):
        kit_dir = self.root / self.kit
        (kit_dir / "TASKS.md").write_text(TASKS.replace("- status: pending", "- status: done"))
        (kit_dir / "NOTES.md").write_text(
            "outcome: T1 model=fixture attempts=1 result=blocked review=none\n")
        sources = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=("TASKS.md", "NOTES.md"), limits=LIMITS)
        view = self.compose(sources=sources)
        self.assertEqual(view["overview"]["task_status"], "done")
        self.assertTrue(any("conflict" in item["code"] or
                            "contradict" in item["code"] for item in view["limitations"]))
        self.assertTrue(any("blocked" in item["claim"].lower()
                            for item in view["findings"]))

    def test_escalated_pass_is_recognized_without_status_conflict(self):
        kit_dir = self.root / self.kit
        (kit_dir / "TASKS.md").write_text(TASKS.replace("- status: pending", "- status: done"))
        (kit_dir / "NOTES.md").write_text(
            "outcome: T1 model=fixture attempts=2 result=escalated-pass review=none\n")
        sources = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=("TASKS.md", "NOTES.md"), limits=LIMITS)
        view = self.compose(sources=sources)
        self.assertFalse(any(item["code"] == "status-outcome-conflict"
                             for item in view["limitations"]))
        self.assertTrue(any("precheck" in item["code"] and item["critical"]
                            for item in view["limitations"]))

    def test_unknown_note_result_is_not_invented_failure(self):
        kit_dir = self.root / self.kit
        (kit_dir / "TASKS.md").write_text(TASKS.replace("- status: pending", "- status: done"))
        (kit_dir / "NOTES.md").write_text(
            "outcome: T1 model=fixture attempts=1 result=future-label review=none\n")
        sources = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=("TASKS.md", "NOTES.md"), limits=LIMITS)
        view = self.compose(sources=sources)
        self.assertTrue(any("future-label" in item["claim"] for item in view["findings"]))
        self.assertFalse(any(item["code"] == "status-outcome-conflict"
                             for item in view["limitations"]))

    def test_all_four_roles_keep_critical_limitations_and_same_facts(self):
        empty = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=(), limits=LIMITS)
        baseline = None
        for role in ("architect", "implementer", "verifier", "reviewer"):
            with self.subTest(role=role):
                request = ct.make_request("repo-a", "checkout-a", None, self.kit, "T1",
                                          "assignment-a", role, "What is next?")
                view = self.compose(request=request, sources=empty, role=role)
                critical = [item for item in view["limitations"] if item["critical"]]
                self.assertEqual(view["brief"]["critical_limitations"], critical)
                facts = {(item["id"], item["kind"], item["claim"])
                         for item in view["findings"]}
                if baseline is None:
                    baseline = facts
                else:
                    self.assertEqual(facts, baseline)

    def test_graph_edge_is_navigation_and_never_task_dependency(self):
        graph = self.root / "graph.json"
        graph.write_text(json.dumps({
            "version": "fixture-0.1", "directed": True,
            "nodes": [{"id": "a", "name": "a", "source_file": "app/a.py"},
                      {"id": "b", "name": "b", "source_file": "app/b.py"}],
            "links": [{"source": "a", "target": "b", "relation": "calls"}]}))
        sources = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=("TASKS.md",), graph_path="graph.json",
            limits=LIMITS)
        view = self.compose(sources=sources)
        kinds = [item["kind"] for item in view["relationships"]]
        self.assertIn("code-navigation", kinds)
        self.assertNotIn("declared-dependency", kinds)

    def test_parser_rejects_deep_duplicate_and_nonfinite_json(self):
        malformed = (b"[" * 700 + b"0" + b"]" * 700,
                     b'{"v":1,"v":2}', b'{"value":1e999}')
        for raw in malformed:
            with self.subTest(raw=raw[:16]), self.assertRaises(lv.ViewError):
                lv.parse_view(raw)

    def test_parser_rejects_nested_tampering_even_with_recomputed_digest(self):
        complete = self.compose()
        empty_sources = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=(), limits=LIMITS)
        partial = self.compose(sources=empty_sources)
        for label, original, mutation in (
            ("overview-extra", complete,
             lambda v: v["overview"].update(unexpected="hidden")),
            ("finding-extra", complete,
             lambda v: v["findings"][0].update(unexpected="hidden")),
            ("finding-type", complete,
             lambda v: v["findings"][0].update(critical="yes")),
            ("limitation-extra", partial,
             lambda v: v["limitations"][0].update(unexpected="hidden")),
            ("limitation-type", partial,
             lambda v: v["limitations"][0].update(critical="yes")),
        ):
            with self.subTest(label=label):
                altered = copy.deepcopy(original)
                mutation(altered)
                body = {k: v for k, v in altered.items() if k != "content_sha"}
                altered["content_sha"] = hashlib.sha256(lv.canonical_bytes(body)).hexdigest()
                with self.assertRaises(lv.ViewError):
                    lv.parse_view(lv.canonical_bytes(altered))

    def test_malformed_nested_ct2_metadata_raises_viewerror(self):
        mutations = (
            lambda s: s["sources"][0]["freshness"].update(state="current"),
            lambda s: s["sources"][0]["coverage"].update(items="many"),
            lambda s: s["sources"][0].update(ref=["not", "a", "ref"]),
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                sources = copy.deepcopy(self.sources)
                mutation(sources)
                with self.assertRaises(lv.ViewError):
                    self.compose(sources=sources)

    def test_rehashed_comparison_rejects_malformed_nested_deltas(self):
        before = self.compose()
        next_request = ct.make_request("repo-a", "checkout-b", "revision-b", self.kit,
                                       "T1", "assignment-a", "implementer", "What is next?")
        after = self.compose(request=next_request)
        valid = lv.compare_views(before, after)
        self.assertTrue(valid["applicability_changes"])
        mutations = (
            lambda c: c["applicability_changes"][0].update(unexpected="hidden"),
            lambda c: c["applicability_changes"][0].update(before={"nested": "value"}),
            lambda c: c["applicability_changes"][0].update(
                after="AKIAIOSFODNN7EXAMPLE"),
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                altered = copy.deepcopy(valid)
                mutation(altered)
                body = {k: v for k, v in altered.items() if k != "content_sha"}
                altered["content_sha"] = hashlib.sha256(lv.canonical_bytes(body)).hexdigest()
                with self.assertRaises(lv.ViewError):
                    lv.parse_view(lv.canonical_bytes(altered))

    def test_rehashed_partial_view_cannot_hide_known_criteria(self):
        view = self.compose()
        self.assertIsNotNone(view["brief"]["criteria_text"])
        altered = copy.deepcopy(view)
        altered["status"] = "partial"
        altered["brief"]["criteria_text"] = None
        body = {k: v for k, v in altered.items() if k != "content_sha"}
        altered["content_sha"] = hashlib.sha256(lv.canonical_bytes(body)).hexdigest()
        with self.assertRaises(lv.ViewError):
            lv.parse_view(lv.canonical_bytes(altered))

    def test_credential_text_is_redacted_with_visible_counts(self):
        token = "AKIAIOSFODNN7EXAMPLE"
        (self.root / self.kit / "TASKS.md").write_text(
            TASKS.replace("Synthetic task", "Synthetic " + token)
                 .replace("Criterion one must hold.", "Keep " + token + " private."))
        sources = readers.read_sources(
            repository_bindings={"repo-a": self.root}, repository_id="repo-a",
            kit_path=self.kit, kit_files=("TASKS.md",), limits=LIMITS)
        view = self.compose(sources=sources)
        rendered = json.dumps(view)
        self.assertNotIn(token, rendered)
        self.assertIn("[redacted:aws-access-key-id]", rendered)
        source_redactions = view["overview"]["source_states"][0]["redactions"]
        self.assertGreaterEqual(source_redactions.get("aws-access-key-id", 0), 2)

    def test_credential_shaped_machine_identity_is_refused(self):
        bad_request = copy.deepcopy(self.request)
        bad_request["repository_id"] = "AKIAIOSFODNN7EXAMPLE"
        with self.assertRaises(lv.ViewError):
            self.compose(request=bad_request)


if __name__ == "__main__":
    unittest.main()
