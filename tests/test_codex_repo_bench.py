import argparse
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from bin import codex_repo_bench as crb


def args(**overrides):
    values = dict(repo="/tmp/repo", models="cheap,mid", judge=None, mode="auto", limit=2,
                  test_cmd=None, setup_cmd=None, commit=None, exclude_subject=[], json=False)
    values.update(overrides)
    return argparse.Namespace(**values)


class CodexRepoBenchTests(unittest.TestCase):
    def setUp(self):
        self.pricing = {
            "cache_read_multiplier": 0.1,
            "orchestration_policy": {"worker_tiers": ["cheap", "mid", "strong"]},
            "models": {
                "small": {"tier": "cheap", "available": True, "input_per_mtok": 1,
                          "output_per_mtok": 2},
                "medium": {"tier": "mid", "available": True, "input_per_mtok": 2,
                           "output_per_mtok": 4},
                "judge": {"tier": "frontier", "available": True, "input_per_mtok": 4,
                          "output_per_mtok": 8},
            },
            "task_profiles": {"XS": {"input_tokens": 10, "output_tokens": 2},
                              "S": {"input_tokens": 20, "output_tokens": 4}},
        }
        self.mined = {"base_commit": "abc", "mode": "issue", "mode_reason": "fixture",
                      "tasks": [{"task_id": "t1", "size_profile": "S",
                                 "oracle_tests_available": True}],
                      "labels": [], "notes": []}

    def test_plan_reports_two_dispatches_per_candidate_and_proxy_only(self):
        card = crb.build_plan(args(), miner=lambda *a, **k: self.mined, pricing=self.pricing)
        self.assertEqual(card["dispatch_count"], 4)
        self.assertEqual(card["judge"], "judge")
        rendered = crb.render_plan(card)
        self.assertIn("burn index", rendered)
        self.assertIn("API-equivalent proxy", rendered)
        self.assertIn("not a bill or quota ceiling", rendered)

    def test_run_refuses_without_calling_a_dispatcher(self):
        card = {"repo": "/tmp/repo", "dispatch_count": 0, "candidates": [], "judge": "j",
                "rows": [], "limitation": "planning only", "tasks": [], "mode": "issue-replay",
                "mode_reason": "fixture", "labels": [], "notes": []}
        with patch.object(crb, "build_plan", return_value=card), redirect_stdout(io.StringIO()) as out:
            rc = crb.cmd_run(args())
        self.assertEqual(rc, 2)
        self.assertIn("refusing to dispatch", out.getvalue())

    def test_candidate_cannot_be_its_own_judge(self):
        with self.assertRaisesRegex(ValueError, "also a candidate"):
            crb.build_plan(args(judge="small"), miner=lambda *a, **k: self.mined,
                           pricing=self.pricing)

    def test_empty_candidates_are_refused_before_mining(self):
        with self.assertRaisesRegex(ValueError, "at least one candidate"):
            crb.build_plan(args(models=""), miner=lambda *a, **k: self.fail("mined"),
                           pricing=self.pricing)

    def test_unavailable_candidate_and_judge_are_refused(self):
        self.pricing["models"]["small"]["available"] = False
        with self.assertRaisesRegex(ValueError, "candidate model.*unavailable"):
            crb.build_plan(args(models="small"), miner=lambda *a, **k: self.fail("mined"),
                           pricing=self.pricing)
        self.pricing["models"]["small"]["available"] = True
        self.pricing["models"]["judge"]["available"] = False
        with self.assertRaisesRegex(ValueError, "judge model.*unavailable"):
            crb.build_plan(args(judge="judge"), miner=lambda *a, **k: self.fail("mined"),
                           pricing=self.pricing)

    def test_zero_task_plan_is_explicitly_not_a_comparison(self):
        mined = dict(self.mined, tasks=[], notes=["no qualifying issue-fix pair"])
        card = crb.build_plan(args(), miner=lambda *a, **k: mined, pricing=self.pricing)
        rendered = crb.render_plan(card)
        self.assertIn("tasks mined: 0", rendered)
        self.assertIn("cannot support a model comparison", rendered)
        self.assertIn("no qualifying issue-fix pair", rendered)

    def test_nonpositive_limit_is_refused_before_mining(self):
        with self.assertRaisesRegex(ValueError, "--limit must be at least 1"):
            crb.build_plan(args(limit=0), miner=lambda *a, **k: self.fail("mined"),
                           pricing=self.pricing)


if __name__ == "__main__":
    unittest.main()
