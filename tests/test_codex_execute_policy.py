"""Execution-driver tests for reserved Astra recovery; never invokes the real Codex CLI."""

import importlib.util
import tempfile
import unittest
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
SPEC = importlib.util.spec_from_file_location("codex_execute_policy_tests", BIN_DIR / "codex_execute.py")
ce = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ce)

PRICING = {
    "knobs": {"reasoning_efforts": ["low", "high"]},
    "orchestration_policy": {
        "orchestrator_model": "astra",
        "orchestrator_tier": "frontier",
        "worker_tiers": ["cheap", "mid", "strong"],
        "default_worker_tier": "mid",
        "maximum_worker_tier": "strong",
        "verification_tier": "strong",
        "recovery_evidence_kinds": [
            "verify_failure", "integration_conflict", "lower_tier_correction_failed"
        ],
    },
    "models": {
        "luna": {"tier": "cheap"},
        "terra": {"tier": "mid"},
        "sol": {"tier": "strong"},
        "astra": {"tier": "frontier"},
    },
}


def task(model="cheap", depends=None):
    return {"id": "T1", "title": "fixture", "status": "pending", "model": model,
            "depends": depends or [], "independent": True, "brief": "fix fixture",
            "verify": "fixture-check"}


class ReservedRecoveryTests(unittest.TestCase):
    def test_worker_failure_unlocks_reserved_astra_and_records_full_recovery(self):
        runner = mock.Mock(return_value=(0, ""))
        verify = mock.Mock(side_effect=[(1, "luna failed"), (1, "terra failed"),
                                       (1, "sol failed"), (0, "astra fixed")])
        result = ce.run_task(task(), PRICING, runner, verify, codex_bin="stub")

        models = [call.args[0][call.args[0].index("--model") + 1]
                  for call in runner.call_args_list]
        self.assertEqual(models, ["luna", "terra", "sol", "astra"])
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["recovery"]["failure_evidence"]["kind"], "verify_failure")
        self.assertEqual(len(result["recovery"]["prior_attempts"]), 3)
        self.assertEqual(result["recovery"]["correction_scope"], "fix fixture")
        self.assertTrue(result["recovery"]["verification_result"]["passed"])

    def test_dispatch_failure_cannot_become_success_from_passing_verify(self):
        runner = mock.Mock(side_effect=[(9, "dispatch failed"), (0, ""), (0, ""), (0, "")])
        verify = mock.Mock(side_effect=[(1, "terra correction failed"), (1, "sol failed"),
                                       (0, "recovered")])
        result = ce.run_task(task(), PRICING, runner, verify, codex_bin="stub")
        self.assertEqual(result["attempts"][0]["result"], "dispatch-failed")
        self.assertIsNone(result["attempts"][0]["verify_exit_code"])
        self.assertEqual(verify.call_count, 3)
        self.assertEqual(result["status"], "done")

    def test_successful_recovery_does_not_promote_next_ordinary_task(self):
        failed_then_recovered = mock.Mock(side_effect=[(1, "x"), (1, "x"), (1, "x"), (0, "ok")])
        ce.run_task(task(), PRICING, mock.Mock(return_value=(0, "")), failed_then_recovered,
                    codex_bin="stub")
        next_runner = mock.Mock(return_value=(0, ""))
        ce.run_task(task(), PRICING, next_runner, mock.Mock(return_value=(0, "ok")),
                    codex_bin="stub")
        argv = next_runner.call_args.args[0]
        self.assertEqual(argv[argv.index("--model") + 1], "luna")

    def test_actual_use_is_separate_and_unknown_without_attestation(self):
        result = ce.run_task(task("mid"), PRICING, mock.Mock(return_value=(0, "model=astra")),
                             mock.Mock(return_value=(0, "ok")), codex_bin="stub")
        attempt = result["attempts"][0]
        self.assertEqual(attempt["planned_model"], "mid")
        self.assertEqual(attempt["dispatched_model"], "terra")
        self.assertIsNone(attempt["actual_model"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "NOTES.md"
            ce.append_note(path, result, task("mid"))
            text = path.read_text()
            self.assertIn("planned=mid dispatched_model=terra", text)
            self.assertIn("actual_model=unknown", text)

    def test_structured_runner_attestation_is_recorded_as_observed(self):
        result = ce.run_task(
            task("strong"), PRICING,
            mock.Mock(return_value=(0, "", {"actual_model": "sol", "actual_role": "implementer"})),
            mock.Mock(return_value=(0, "ok")), codex_bin="stub",
        )
        self.assertEqual(result["attempts"][0]["actual_model"], "sol")
        self.assertEqual(result["attempts"][0]["actual_role"], "implementer")

    def test_runtime_policy_mismatch_blocks_without_unlocking_recovery(self):
        runner = mock.Mock(return_value=(0, "", {"actual_model": "astra"}))
        verify = mock.Mock(return_value=(0, "would pass"))
        result = ce.run_task(task("mid"), PRICING, runner, verify, codex_bin="stub")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["attempts"][0]["result"], "policy-mismatch")
        self.assertIsNone(result["recovery"])
        verify.assert_not_called()
        self.assertEqual(runner.call_count, 1)

    def test_runner_oserror_becomes_audited_failure(self):
        runner = mock.Mock(side_effect=OSError("unavailable"))
        result = ce.run_task(task("strong"), PRICING, runner, mock.Mock(), codex_bin="stub")
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(all(a["result"] == "dispatch-failed" for a in result["attempts"]))
        self.assertIn("unavailable", result["attempts"][0]["failure_digest"])


class DriverPolicyBoundaryTests(unittest.TestCase):
    def test_review_fingerprint_changes_with_head_and_later_task_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kit = root / "tasks" / "kits" / "fixture"
            kit.mkdir(parents=True)
            tasks_text = """## Phase 1 — test
### T1 — done
- status: done
- model: mid
- depends: (none)
- independent: no
**Brief.** done
**Verify.**
```bash
true
```
"""
            (kit / "TASKS.md").write_text(tasks_text)
            (kit / "PLAN.md").write_text("goal\n")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture",
                            "-c", "user.email=fixture@example.invalid", "commit", "-qm", "A"],
                           check=True)
            first = ce.review_evidence_fingerprint(kit, tasks_text, "1")
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture",
                            "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty",
                            "-qm", "B"], check=True)
            second = ce.review_evidence_fingerprint(kit, tasks_text, "1")
            self.assertNotEqual(first, second)
            (kit / "NOTES.md").write_text("## now — T1\n- actual-use: attempt=2\n")
            third = ce.review_evidence_fingerprint(kit, tasks_text, "1")
            self.assertNotEqual(second, third)

    def test_missing_verify_fails_before_dispatch(self):
        runner = mock.Mock()
        with self.assertRaises(ce.PolicyError):
            ce.run_task(task() | {"verify": None}, PRICING, runner, mock.Mock(), codex_bin="stub")
        runner.assert_not_called()

    def test_runtime_attestation_requires_correlated_fresh_turn_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / "sessions" / "2026" / "09" / "05"
            sessions.mkdir(parents=True)
            thread_id = "12345678-fixture"
            rollout = sessions / f"rollout-fixture-{thread_id}.jsonl"
            records = [
                {"timestamp": "2026-09-05T11:59:00.000Z", "type": "turn_context",
                 "payload": {"model": "astra"}},
                {"timestamp": "2026-09-05T12:00:01.000Z", "type": "turn_context",
                 "payload": {"model": "sol"}},
            ]
            rollout.write_text("\n".join(json.dumps(r) for r in records))
            output = json.dumps({"type": "thread.started", "thread_id": thread_id})
            telemetry = ce.attest_runtime_model(
                output, datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc), codex_root=root
            )
            self.assertEqual(telemetry["actual_model"], "sol")
            self.assertEqual(telemetry["provenance"], "correlated-rollout-turn_context")

    def test_free_form_model_text_is_not_runtime_attestation(self):
        telemetry = ce.attest_runtime_model(
            "model=astra", datetime(2026, 9, 5, tzinfo=timezone.utc), codex_root="/missing"
        )
        self.assertEqual(telemetry, {})

    def test_extra_args_cannot_override_model_profile_or_model_config(self):
        for args in (("--model=astra",), ("-m", "astra"), ("--profile", "best"),
                     ("-mastra",), ("-pbest",), ("--config=provider=other",),
                     ("-c", '"model"="astra"'), ("-cmodel_reasoning_effort=max",),
                     ("--dangerously-bypass-approvals-and-sandbox",), ("--yolo",)):
            with self.subTest(args=args), self.assertRaises(ce.PolicyError):
                ce.build_dispatch("stub", "terra", "prompt", extra_args=args)

    def test_explicit_task_with_unfinished_dependency_is_ineligible(self):
        tasks = [task(), {**task("mid", ["T1"]), "id": "T2"}]
        self.assertIsNone(ce._select_task(tasks, "T2"))

    def test_review_is_pinned_to_sol_and_acceptance_to_astra(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp) / "kit"
            kit.mkdir()
            (kit / "TASKS.md").write_text("""## Phase 1 — test

### T1 — done
- status: done
- model: mid
- depends: (none)
- independent: no

**Brief.** done

**Verify.**
```bash
true
```
""")
            with mock.patch.object(ce, "load_pricing", return_value=PRICING), \
                 mock.patch.object(ce, "load_preamble", return_value="role"), \
                 mock.patch.object(ce, "review_evidence_fingerprint", return_value="fixture-fp"):
                from contextlib import redirect_stdout
                import io
                out = io.StringIO()
                with redirect_stdout(out):
                    ce.main(["review", "--kit", str(kit), "--phase", "1",
                             "--codex-bin", "stub", "--dry-run"])
                self.assertIn("--model sol", out.getvalue())
                (kit / "NOTES.md").write_text(
                    "## timestamp — phase-1-verifier\n"
                    "- actual-use: dispatched_model=sol dispatched_role=verifier dispatch_exit=0\n"
                    "- evidence-fingerprint: fixture-fp\n"
                )
                out = io.StringIO()
                with redirect_stdout(out):
                    ce.main(["accept", "--kit", str(kit), "--phase", "1",
                             "--codex-bin", "stub", "--dry-run"])
                self.assertIn("--model astra", out.getvalue())
                self.assertIn("scope=acceptance-only", out.getvalue())

    def test_acceptance_verdict_is_explicit_and_machine_readable(self):
        self.assertEqual(
            ce.parse_acceptance_verdict("analysis\nPOLYTROPOS_ACCEPTANCE: accepted\n"),
            "accepted",
        )
        self.assertIsNone(ce.parse_acceptance_verdict("looks good"))

    def test_later_review_supersedes_old_success_and_fingerprint_must_match(self):
        notes = (
            "## old — phase-1-verifier\n- actual-use: dispatch_exit=0\n"
            "- evidence-fingerprint: old\n\n"
            "## new — phase-1-verifier\n- actual-use: dispatch_exit=1\n"
            "- evidence-fingerprint: current\n"
        )
        self.assertFalse(ce._role_use_succeeded(notes, "1", "verifier", "current"))
        self.assertFalse(ce._role_use_succeeded(notes, "1", "verifier", "old"))

    def test_review_record_keeps_bounded_report_and_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "NOTES.md"
            ce.append_role_use(path, "1", "verifier", None, "sol", 0,
                               evidence_fingerprint="fp", report="finding " * 500)
            text = path.read_text()
            self.assertIn("report-sha256:", text)
            report_line = next(line for line in text.splitlines() if line.startswith("- report: "))
            self.assertLessEqual(len(report_line) - len("- report: "), 2000)

    def test_rejected_acceptance_is_recorded_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp) / "kit"
            kit.mkdir()
            (kit / "TASKS.md").write_text("""## Phase 1 — test
### T1 — done
- status: done
- model: mid
- depends: (none)
- independent: no
**Brief.** done
**Verify.**
```bash
true
```
""")
            (kit / "NOTES.md").write_text(
                "## old — phase-1-verifier\n- actual-use: dispatch_exit=0\n"
                "- evidence-fingerprint: fp\n"
            )
            with mock.patch.object(ce, "load_pricing", return_value=PRICING), \
                 mock.patch.object(ce, "load_preamble", return_value="role"), \
                 mock.patch.object(ce, "review_evidence_fingerprint", return_value="fp"), \
                 mock.patch.object(ce, "default_runner", return_value=(
                     0, "POLYTROPOS_ACCEPTANCE: rejected", {}
                 )):
                with self.assertRaises(SystemExit) as caught:
                    ce.main(["accept", "--kit", str(kit), "--phase", "1",
                             "--codex-bin", "stub"])
            self.assertEqual(caught.exception.code, 1)
            self.assertIn("result=rejected", (kit / "NOTES.md").read_text())


if __name__ == "__main__":
    unittest.main()
