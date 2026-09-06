"""Central Codex orchestrator/worker invariant tests with synthetic model ids."""

import copy
import importlib.util
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
spec = importlib.util.spec_from_file_location("codex_policy", BIN_DIR / "codex_policy.py")
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
bench_spec = importlib.util.spec_from_file_location("bench_routing_policy", BIN_DIR / "bench_routing.py")
bench = importlib.util.module_from_spec(bench_spec)
bench_spec.loader.exec_module(bench)


FIXTURE = {
    "models": {
        "tiny": {"tier": "cheap"},
        "normal": {"tier": "mid"},
        "hard": {"tier": "strong"},
        "boss": {"tier": "frontier"},
    },
    "orchestration_policy": {
        "orchestrator_model": "boss",
        "orchestrator_tier": "frontier",
        "worker_tiers": ["cheap", "mid", "strong"],
        "default_worker_tier": "mid",
        "maximum_worker_tier": "strong",
        "verification_tier": "strong",
        "recovery_evidence_kinds": [
            "verify_failure", "integration_conflict", "lower_tier_correction_failed"
        ],
    },
}


def evidence():
    return {
        "task_id": "T1", "kind": "verify_failure", "verify_exit_code": 1,
        "attempts": [{"dispatched_model": "hard", "actual_model": "hard", "result": "failed"}],
    }


class AssignmentTests(unittest.TestCase):
    def test_workers_remain_eligible(self):
        self.assertEqual(policy.resolve_assignment(FIXTURE, "cheap")["model_id"], "tiny")
        self.assertEqual(policy.resolve_assignment(FIXTURE, "mid")["model_id"], "normal")
        self.assertEqual(policy.resolve_assignment(FIXTURE, "strong")["model_id"], "hard")
        self.assertEqual(policy.eligible_models(FIXTURE, "implementer"), ["tiny", "normal", "hard"])

    def test_explicit_orchestrator_cannot_implement(self):
        with self.assertRaisesRegex(policy.PolicyError, "cannot perform ordinary"):
            policy.resolve_assignment(FIXTURE, "boss")

    def test_legacy_frontier_pin_migrates_to_strong_worker(self):
        got = policy.resolve_assignment(FIXTURE, "frontier")
        self.assertEqual(got["model_id"], "hard")
        self.assertIn("legacy", got["migration"])

    def test_unpinned_legacy_kit_migrates_to_default_worker(self):
        got = policy.resolve_assignment(FIXTURE)
        self.assertEqual(got["model_id"], "normal")
        self.assertIn("legacy", got["migration"])

    def test_routine_verification_uses_strong_worker(self):
        self.assertEqual(policy.resolve_assignment(FIXTURE, role="verifier")["model_id"], "hard")

    def test_recovery_requires_machine_visible_evidence(self):
        with self.assertRaises(policy.PolicyError):
            policy.resolve_assignment(FIXTURE, role="recovery", evidence={"preference": "best"})
        self.assertEqual(
            policy.resolve_assignment(FIXTURE, role="recovery", evidence=evidence())["model_id"],
            "boss",
        )

    def test_worker_ladder_never_contains_orchestrator(self):
        self.assertEqual(policy.worker_ladder(FIXTURE, "tiny"), ["normal", "hard"])

    def test_after_recovery_later_work_returns_to_default_worker(self):
        policy.resolve_assignment(FIXTURE, role="recovery", evidence=evidence())
        self.assertEqual(policy.resolve_assignment(FIXTURE)["model_id"], "normal")

    def test_missing_or_unavailable_orchestrator_fails_closed(self):
        missing = copy.deepcopy(FIXTURE)
        del missing["models"]["boss"]
        with self.assertRaisesRegex(policy.PolicyError, "execution is disabled"):
            policy.resolve_assignment(missing, "cheap")
        unavailable = copy.deepcopy(FIXTURE)
        unavailable["models"]["boss"]["available"] = False
        with self.assertRaisesRegex(policy.PolicyError, "execution is disabled"):
            policy.resolve_assignment(unavailable, "cheap")

    def test_vague_best_model_text_does_not_unlock_recovery(self):
        with self.assertRaises(policy.PolicyError):
            policy.validate_recovery({
                "task_id": "T1", "kind": "verify_failure", "verify_exit_code": 0,
                "attempts": [{"dispatched_model": "hard", "note": "use the best model"}],
            })

    def test_unknown_or_orchestrator_attempt_cannot_unlock_recovery(self):
        for dispatched in ("ghost", "boss"):
            bad = evidence()
            bad["attempts"][0]["dispatched_model"] = dispatched
            with self.assertRaisesRegex(policy.PolicyError, "eligible workers|lower-tier"):
                policy.resolve_assignment(FIXTURE, role="recovery", evidence=bad)

    def test_integration_conflict_requires_details(self):
        bad = evidence()
        bad.update({"kind": "integration_conflict", "unresolved": True, "conflict_id": "C1"})
        with self.assertRaisesRegex(policy.PolicyError, "details"):
            policy.resolve_assignment(FIXTURE, role="recovery", evidence=bad)

    def test_policy_status_reports_reserved_orchestrator_and_workers(self):
        got = policy.policy_status(FIXTURE)
        self.assertTrue(got["ready"])
        self.assertEqual(got["orchestrator_model"], "boss")
        self.assertNotIn("boss", got["worker_models"])

    def test_benchmark_roles_obey_codex_policy_without_affecting_claude(self):
        entries = [{
            "label": mid, "model": mid, "effort": "x", "provider": "test",
            "intelligence_index": 100, "usd_per_task": idx + 1,
        } for idx, mid in enumerate(FIXTURE["models"])]
        claude = {"models": {mid: {"tier": "sonnet"} for mid in FIXTURE["models"]}}
        card = bench.build_roles_card({"entries": entries}, {"codex": FIXTURE, "claude": claude},
                                      ["codex", "claude"], floors={r: 0 for r in bench.ROLE_NAMES})
        codex = card["sections"][0]
        picks = {r["role"]: r["picked"]["model"] for r in codex["roles"]}
        self.assertEqual(picks["architect/planner"], "boss")
        self.assertEqual(picks["orchestrator"], "boss")
        self.assertEqual(picks["reviewer"], "hard")
        self.assertEqual(picks["verifier"], "hard")
        self.assertNotEqual(picks["implementer"], "boss")
        self.assertEqual(picks["mechanical sweep"], "tiny")
        self.assertTrue(all(r["picked"] is not None for r in card["sections"][1]["roles"]))


if __name__ == "__main__":
    unittest.main()
