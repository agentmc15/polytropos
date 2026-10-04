"""bin/route_experiment.py -- the four-route experiment harness.

Nothing here reaches a real CLI: dispatch goes to an injected runner or to the demo's generated
stub, the Copilot home is a temp dir, the run store is a temp dir, and `POLYTROPOS_DATA_HOME`
is pinned for the module so no default store can resolve to the user's own.
"""

import copy
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(f"t_{name}", ROOT / "bin" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rx = _load("route_experiment")
cu = _load("copilot_usage")
cp = _load("copilot_pricing")

_DATA_HOME = None
_DATA_HOME_PATCH = None


def setUpModule():
    global _DATA_HOME, _DATA_HOME_PATCH
    _DATA_HOME = tempfile.TemporaryDirectory(prefix="polytropos-test-data-")
    _DATA_HOME_PATCH = mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": _DATA_HOME.name})
    _DATA_HOME_PATCH.start()


def tearDownModule():
    _DATA_HOME_PATCH.stop()
    _DATA_HOME.cleanup()


PRICING = rx.load_pricing()


def real_experiment():
    return rx.load_experiment(rx.EXPERIMENT_DIR, PRICING)


def events(*objs):
    return "".join(json.dumps(o) + "\n" for o in objs)


def shutdown(metrics, total_nano=0):
    return {"type": "session.shutdown", "data": {"totalNanoAiu": total_nano,
                                                 "totalPremiumRequests": 2,
                                                 "modelMetrics": metrics}}


def details(inp, cread, cwrite, out):
    return {"input": {"tokenCount": inp}, "cache_read": {"tokenCount": cread},
            "cache_write": {"tokenCount": cwrite}, "output": {"tokenCount": out}}


class DefinitionTests(unittest.TestCase):
    def test_the_shipped_experiment_validates_against_the_pricing_file(self):
        exp, digest = real_experiment()
        self.assertEqual(sorted(exp["arms"]), ["A1", "A2", "A3", "A4"])
        self.assertEqual(len(exp["task_defs"]), 3)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_effort_tokens_come_from_the_pricing_ladder(self):
        efforts = rx.effort_values(PRICING)
        self.assertIn("xhigh", efforts)
        self.assertIn("max", efforts)

    def _raw(self):
        return json.loads((rx.EXPERIMENT_DIR / "experiment.json").read_text())

    def test_an_unknown_model_is_refused(self):
        raw = self._raw()
        raw["arms"]["A3"]["stages"]["solo"]["model"] = "no-such-model"
        with self.assertRaisesRegex(rx.ConfigError, "not an active model"):
            rx.validate_definition(raw, PRICING)

    def test_an_unknown_effort_is_refused(self):
        raw = self._raw()
        raw["arms"]["A1"]["stages"]["implementer"]["effort"] = "ludicrous"
        with self.assertRaisesRegex(rx.ConfigError, "effort"):
            rx.validate_definition(raw, PRICING)

    def test_a_pipeline_needs_every_stage(self):
        raw = self._raw()
        del raw["arms"]["A2"]["stages"]["verifier"]
        with self.assertRaisesRegex(rx.ConfigError, "needs the stages"):
            rx.validate_definition(raw, PRICING)

    def test_weights_must_sum_to_one(self):
        raw = self._raw()
        raw["scoring"]["weights"]["quality"] = 0.5
        with self.assertRaisesRegex(rx.ConfigError, "sum to 1"):
            rx.validate_definition(raw, PRICING)

    def test_the_digest_moves_when_an_oracle_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            import shutil
            copy_dir = Path(tmp) / "exp"
            shutil.copytree(rx.EXPERIMENT_DIR, copy_dir)
            _, before = rx.load_experiment(copy_dir, PRICING)
            oracle = copy_dir / "tasks" / "T1-statusline-rollover" / "oracle.py"
            oracle.write_text(oracle.read_text() + "\n# changed\n")
            _, after = rx.load_experiment(copy_dir, PRICING)
            self.assertNotEqual(before, after)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.exp, self.digest = real_experiment()

    def test_the_matrix_is_complete_and_counterbalanced(self):
        trials = rx.trial_plan(self.exp, 3)
        self.assertEqual(len(trials), 36)
        self.assertEqual(len({t["trial_id"] for t in trials}), 36)
        for arm in self.exp["arms"]:
            positions = [t["position"] for t in trials if t["arm"] == arm]
            self.assertEqual(len(positions), 9)
            self.assertGreaterEqual(len(set(positions)), 3, f"{arm} always runs in one slot")
        firsts = {t["arm"] for t in trials if t["position"] == 0}
        self.assertEqual(firsts, set(self.exp["arms"]))

    def test_estimates_are_derived_from_the_pricing_file(self):
        est = rx.arm_estimate(self.exp, PRICING, "A4")
        stage = self.exp["arms"]["A4"]["stages"]["solo"]
        expected = cp.est_cost(PRICING, self.exp["role_profiles"]["solo"], stage["model"])["aic"]
        self.assertAlmostEqual(est["min"], expected)
        pipe = rx.arm_estimate(self.exp, PRICING, "A1")
        self.assertEqual(pipe["dispatches_min"], 5)
        self.assertEqual(pipe["dispatches_max"], 9)
        self.assertGreater(pipe["max"], pipe["min"])

    def test_the_preregistered_plan_fits_its_ceiling(self):
        plan = rx.build_plan(self.exp, self.digest, PRICING, 3)
        self.assertLess(plan["aic"]["total_max"], self.exp["max_aic"])
        self.assertEqual(plan["dispatches"]["judge"], 9 * len(self.exp["judges"]))


class ArgvAndPromptTests(unittest.TestCase):
    def setUp(self):
        self.exp, _ = real_experiment()
        self.task = self.exp["task_defs"]["T2-est-multi-model"]

    def test_read_only_roles_deny_writes_and_judges_deny_the_shell(self):
        for role in ("planner", "verifier", "reviewer"):
            argv = rx.build_argv(self.exp, "copilot", "gpt-6-luna", "max", "P", "sid", role)
            self.assertIn("--deny-tool=write", argv)
            self.assertNotIn("--deny-tool=shell", argv)
        argv = rx.build_argv(self.exp, "copilot", "gpt-6-astra", "high", "P", "sid", "judge")
        self.assertIn("--deny-tool=shell", argv)
        argv = rx.build_argv(self.exp, "copilot", "gpt-6-luna", "max", "P", "sid", "implementer")
        self.assertNotIn("--deny-tool=write", argv)
        self.assertEqual(argv[-2:], ["-p", "P"])
        self.assertIn("--reasoning-effort=max", argv)
        self.assertEqual(argv[argv.index("--session-id") + 1], "sid")

    def test_every_dispatch_excludes_delegation_and_history(self):
        argv = rx.build_argv(self.exp, "copilot", "gpt-6-sol", "high", "P", "sid", "solo")
        for tool in ("task", "skill", "session_store_sql", "store_memory"):
            self.assertIn(f"--excluded-tools={tool}", argv)

    def test_no_prompt_leaks_the_oracle_or_names_the_experiment(self):
        for task in self.exp["task_defs"].values():
            prompts = [rx.prompt_for(role, task, plan="p", test_files=["tests/test_x.py"],
                                     patch="diff", findings="f", source="verifier")
                       for role in ("solo", "planner", "test_author", "implementer",
                                    "verifier", "reviewer")]
            prompts.append(rx.judge_prompt(task, [("W", "a"), ("X", "b")]))
            oracle_body = task["oracle_text"].split("class", 1)[1][:200]
            for prompt in prompts:
                self.assertNotIn(oracle_body, prompt)
                for marker in ("route-arms", "route_experiment", rx.ORACLE_TEST_NAME,
                               "reference.patch", "A1", "A2", "A3", "A4"):
                    self.assertNotIn(marker, prompt)

    def test_gates_ask_for_a_parseable_verdict(self):
        verifier = rx.prompt_for("verifier", self.task, patch="d")
        reviewer = rx.prompt_for("reviewer", self.task, patch="d")
        self.assertIn("VERIFY VERDICT=pass", verifier)
        self.assertIn("REVIEW VERDICT=reject", reviewer)
        self.assertEqual(rx.VERIFY_RE.findall("x\nVERIFY VERDICT=fail\n"), ["fail"])


class UsageTests(unittest.TestCase):
    def test_every_model_in_a_session_is_priced_from_its_own_tokens(self):
        a, b = details(1000, 50000, 2000, 3000), details(500, 0, 0, 100)
        text = events(
            {"type": "session.model_change", "data": {"newModel": "gpt-6-luna",
                                                      "reasoningEffort": "max"}},
            {"type": "tool.execution_start", "data": {"toolName": "bash", "arguments": {}}},
            shutdown({"gpt-6-luna": {"tokenDetails": a, "totalNanoAiu": 10 ** 9,
                                     "usage": {"reasoningTokens": 7}},
                      "claude-opus-5.5": {"tokenDetails": b, "totalNanoAiu": 0}},
                     total_nano=2 * 10 ** 9))
        usage = rx.session_usage(text, PRICING)
        flat = lambda d: {k: v["tokenCount"] for k, v in d.items()}
        want = sum(cu.usd_to_aic(cu.price_tokens(flat(d), m, PRICING), PRICING)
                   for m, d in (("gpt-6-luna", a), ("claude-opus-5.5", b)))
        self.assertAlmostEqual(usage["aic"], want, places=3)
        self.assertEqual(usage["reported_aiu"], 2.0)
        self.assertEqual(usage["tokens"]["cache_write"], 2000)
        self.assertEqual(usage["reasoning_tokens"], 7)
        self.assertEqual(usage["observed_efforts"], ["max"])
        self.assertEqual(usage["tool_calls"], {"bash": 1})
        self.assertEqual(usage["unpriced"], [])

    def test_an_unpriceable_model_falls_back_to_its_reported_aiu_and_is_named(self):
        text = events(shutdown({"mystery-9": {"tokenDetails": details(1, 1, 1, 1),
                                              "totalNanoAiu": 3 * 10 ** 9}}))
        usage = rx.session_usage(text, PRICING)
        self.assertEqual(usage["unpriced"], ["mystery-9"])
        self.assertAlmostEqual(usage["aic"], 3.0)

    def test_no_shutdown_means_unmeasured_not_zero(self):
        self.assertIsNone(rx.session_usage(events({"type": "session.start", "data": {}}),
                                           PRICING))


class ContaminationTests(unittest.TestCase):
    def test_only_tool_call_arguments_are_scanned(self):
        text = events(
            {"type": "tool.execution_complete",
             "data": {"result": {"content": "bin/copilot_execute.py route-arms"}}},
            {"type": "tool.execution_start",
             "data": {"toolName": "bash", "arguments": {"command": "ls"}}})
        self.assertEqual(rx.contamination(text, ["route-arms"]), [])

    def test_markers_nested_cli_and_delegation_are_flagged(self):
        text = events(
            {"type": "tool.execution_start",
             "data": {"toolName": "bash", "arguments": {"command": "cat /x/route-arms/o.py"}}},
            {"type": "tool.execution_start",
             "data": {"toolName": "bash", "arguments": {"command": "copilot -p hi"}}},
            {"type": "tool.execution_start", "data": {"toolName": "task", "arguments": {}}})
        self.assertEqual(rx.contamination(text, ["route-arms"]),
                         ["route-arms", "nested-cli", "delegation"])


    def test_naming_a_dispatcher_is_not_launching_one(self):
        # The live false positive: a planner grepping bin/copilot_execute.py for a symbol.
        for command in (
                'grep -n "copilot_pricing" bin/copilot_docs.py bin/copilot_execute.py | head',
                "sed -n 1,40p bin/copilot_ralph.py",
                "wc -l bin/copilot_execute.py && cat tests/test_copilot_execute.py",
                "rg 'copilot -p' docs/"):
            self.assertFalse(rx.nested_cli_launch(command), command)
        text = events({"type": "tool.execution_start",
                       "data": {"toolName": "view",
                                "arguments": {"path": "/w/bin/copilot_execute.py"}}})
        self.assertEqual(rx.contamination(text, []), [])

    def test_running_a_dispatcher_or_copilot_prompt_is_a_launch(self):
        for command in (
                "copilot -p 'do it'", "cd /w && copilot --model x --prompt=hi",
                "python3 bin/copilot_execute.py --kit k", "ls; python3 -u ./bin/copilot_ralph.py",
                "FOO=1 timeout 60 python3.12 bin/copilot_execute.py", "./bin/copilot_execute.py",
                "echo $(copilot -p x)"):
            self.assertTrue(rx.nested_cli_launch(command), command)


SAMPLE = '''"""Module doc."""
import os
import json


def branchy(x, items):
    """Doc
    string."""
    # comment
    if x > 1 and x < 10:
        for i in items:
            if i:
                return i
    elif x == 0:
        return None
    else:
        return [j for j in items if j]
    return json.dumps(x)
'''


class MetricTests(unittest.TestCase):
    def test_complexity_of_a_known_function(self):
        m = rx.source_metrics(SAMPLE)
        f = m["per_function"]["branchy"]
        # if + and + for + if + elif + comprehension(1 + 1 if) = 7 decisions
        self.assertEqual(f["cc"], 8)
        self.assertEqual(f["nesting"], 3)
        self.assertGreater(f["cognitive"], f["nesting"])
        self.assertGreater(m["halstead_volume"], 0)
        self.assertTrue(0 < m["mi"] <= 100)

    def test_sloc_skips_docstrings_comments_and_blanks(self):
        m = rx.source_metrics(SAMPLE)
        self.assertEqual(m["sloc"], 12)

    def test_parse_errors_are_reported_not_raised(self):
        self.assertIsNone(rx.source_metrics("def broken(:\n"))
        self.assertTrue(rx.complexity_delta("x = 1\n", "def broken(:\n")["parse_error"])

    def test_changed_functions_and_new_unused_imports(self):
        after = SAMPLE.replace("return json.dumps(x)", "return str(x)") + \
            "\n\ndef added():\n    return 1\n"
        delta = rx.complexity_delta(SAMPLE, after)
        self.assertEqual(delta["touched_functions"], ["added", "branchy"])
        self.assertEqual(delta["new_unused_imports"], ["json"])
        self.assertEqual(delta["undocumented_new_public"], ["added"])
        self.assertEqual(rx.unused_imports(SAMPLE), {"os"})

    def test_mutants_are_single_point_deterministic_and_confined(self):
        source = SAMPLE + "\n\ndef other(a):\n    return a + 1\n"
        first = rx.mutants(source, ["branchy"], 50, seed=7)
        again = rx.mutants(source, ["branchy"], 50, seed=7)
        self.assertEqual([m["id"] for m in first], [m["id"] for m in again])
        self.assertGreater(len(first), 4)
        other_line = source.splitlines().index("def other(a):") + 1
        for m in first:
            self.assertLess(m["line"], other_line)
            self.assertNotEqual(m["source"].strip(), source.strip())
            compile(m["source"], "<mutant>", "exec")
        self.assertEqual(len(rx.mutants(source, ["branchy"], 3, seed=7)), 3)

    def test_diff_stats_scope_and_guardrails(self):
        exp, _ = real_experiment()
        task = exp["task_defs"]["T1-statusline-rollover"]
        patch = ("diff --git a/bin/statusline.py b/bin/statusline.py\n--- a/bin/statusline.py\n"
                 "+++ b/bin/statusline.py\n@@ -1 +1,2 @@\n-x = 1\n+import subprocess\n+x = 2\n"
                 "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n"
                 "@@ -1 +1 @@\n-a\n+b  # TODO tidy\n"
                 "diff --git a/tests/test_new.py b/tests/test_new.py\nnew file mode 100644\n"
                 "--- /dev/null\n+++ b/tests/test_new.py\n@@ -0,0 +1 @@\n+import subprocess\n")
        stats = rx.diff_stats(patch, task)
        self.assertEqual(stats["out_of_scope"], ["README.md"])
        self.assertEqual(stats["guardrails"], {"subprocess": 1})
        self.assertEqual((stats["src_added"], stats["src_removed"], stats["test_added"]), (3, 2, 1))
        self.assertEqual(stats["todos_added"], 1)

    def test_v2_mutation_operators_add_kinds_and_spare_docstrings(self):
        source = ('def f(xs, flag=True):\n    """Doc."""\n    total = 0\n'
                  '    for x in xs:\n        if x:\n            total += -x\n'
                  '    return max(total, 0) if flag else "none"\n')
        v1 = {m["kind"] for m in rx.mutants(source, ["f"], 100, seed=1)}
        v2 = rx.mutants(source, ["f"], 100, seed=1, operators="v2")
        kinds = {m["kind"] for m in v2}
        self.assertFalse(kinds & {"bool", "str", "call-swap", "augassign", "negate-test", "neg"}
                         & v1)
        self.assertTrue({"bool", "str", "call-swap", "augassign", "negate-test", "neg"} <= kinds)
        for m in v2:
            compile(m["source"], "<mutant>", "exec")
            self.assertIn('"""Doc."""', m["source"].replace("'Doc.'", '"""Doc."""'))
        self.assertEqual([m["id"] for m in v2],
                         [m["id"] for m in rx.mutants(source, ["f"], 100, seed=1,
                                                      operators="v2")])

    def test_allowed_generated_paths_are_in_scope_and_outside_size(self):
        exp, _ = real_experiment()
        task = dict(exp["task_defs"]["T1-statusline-rollover"],
                    allowed_generated=["copilot-docs/"])
        patch = ("diff --git a/bin/statusline.py b/bin/statusline.py\n--- a/bin/statusline.py\n"
                 "+++ b/bin/statusline.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
                 "diff --git a/copilot-docs/aic-report.json b/copilot-docs/aic-report.json\n"
                 "--- a/copilot-docs/aic-report.json\n+++ b/copilot-docs/aic-report.json\n"
                 "@@ -1 +1 @@\n-a\n+b\n")
        stats = rx.diff_stats(patch, task)
        self.assertEqual(stats["out_of_scope"], [])
        self.assertEqual(stats["generated_files"], ["copilot-docs/aic-report.json"])
        self.assertEqual((stats["src_added"], stats["files_changed"]), (1, 1))
        plain = rx.diff_stats(patch, exp["task_defs"]["T1-statusline-rollover"])
        self.assertEqual(plain["out_of_scope"], ["copilot-docs/aic-report.json"])
        self.assertNotIn("generated_files", plain)

    def test_unittest_transcripts(self):
        ok = rx.parse_unittest("....\n------\nRan 4 tests in 0.1s\n\nOK\n")
        self.assertEqual((ok["ran"], ok["ok"]), (4, True))
        bad = rx.parse_unittest("Ran 5 tests in 0.1s\n\nFAILED (failures=2, errors=1, skipped=1)\n")
        self.assertEqual((bad["failures"], bad["errors"], bad["skipped"], bad["ok"]),
                         (2, 1, 1, False))
        self.assertFalse(rx.parse_unittest("Traceback: boom")["ok"])


class ScoringTests(unittest.TestCase):
    SCORING = {"weights": {"correctness": 0.4, "quality": 0.25, "test_strength": 0.15,
                           "simplicity": 0.1, "discipline": 0.1},
               "regression_gate": 0.5, "discipline_penalty": 0.25, "equivalence_margin": 5.0,
               "min_solve_rate": 0.6667, "bootstrap_iterations": 300, "confidence": 0.95}

    def grade(self, oracle=1.0, regression=True, mutation=1.0, src=(2, 0), out_of_scope=()):
        return {"applied": True, "oracle": {"score": oracle}, "regression": {"green": regression},
                "mutation": {"score": mutation},
                "diff": {"src_added": src[0], "src_removed": src[1], "out_of_scope": list(out_of_scope),
                         "guardrails": {}, "todos_added": 0},
                "metrics": {"aggregate": {"delta_cc": 1, "parse_errors": 0,
                                          "new_unused_imports": 0}},
                "reference": {"diff": {"src_added": 2, "src_removed": 0},
                              "metrics": {"aggregate": {"delta_cc": 1}}}}

    def trial(self, arm="A1", task="T1", rep=1, aic=10.0, fence=()):
        return {"trial_id": f"{task}-{arm}-r{rep}", "task": task, "arm": arm, "repeat": rep,
                "status": "complete", "aic": aic, "fence": list(fence), "dispatches": [{}]}

    def test_a_perfect_trial_scores_100_and_quality_renormalizes_when_absent(self):
        row = rx.score_trial(self.trial(), self.grade(), None, self.SCORING)
        self.assertEqual(row["qs"], 100.0)
        self.assertEqual(row["missing"], ["quality"])
        self.assertTrue(row["solved"])
        row = rx.score_trial(self.trial(), self.grade(), 0.0, self.SCORING)
        self.assertEqual(row["qs"], 75.0)

    def test_red_regression_halves_the_score_and_is_not_solved(self):
        row = rx.score_trial(self.trial(), self.grade(regression=False), None, self.SCORING)
        self.assertEqual(row["qs"], 50.0)
        self.assertFalse(row["solved"])

    def test_violations_and_excess_size_cost_points(self):
        row = rx.score_trial(self.trial(fence=[{"kind": "read-only-stage-wrote",
                                                "stage": "verifier"}]),
                             self.grade(src=(22, 0), out_of_scope=["README.md"]), None,
                             self.SCORING)
        self.assertEqual(len(row["violations"]), 2)
        self.assertAlmostEqual(row["components"]["discipline"], 0.5)
        self.assertAlmostEqual(row["components"]["simplicity"], 0.0)

    def rows(self, arm, qs_values, aic, solved=True):
        return [{"arm": arm, "task": f"T{i % 3}", "repeat": i // 3, "qs": q, "aic": aic,
                 "solved": solved} for i, q in enumerate(qs_values)]

    def summarise(self, arm_rows):
        return {a: {"n": len(rs), "solve_rate": sum(r["solved"] for r in rs) / len(rs),
                    "qs_mean": sum(r["qs"] for r in rs) / len(rs),
                    "aic_mean": sum(r["aic"] for r in rs) / len(rs)}
                for a, rs in arm_rows.items()}

    def test_the_cheapest_arm_tied_with_the_leader_wins(self):
        arm_rows = {"A1": self.rows("A1", [90, 92, 91, 93, 90, 92], 30),
                    "A2": self.rows("A2", [89, 90, 90, 91, 89, 90], 10),
                    "A3": self.rows("A3", [60, 62, 61, 60, 63, 61], 5)}
        d = rx.decide(arm_rows, self.summarise(arm_rows), self.SCORING)
        self.assertEqual(d["leader"], "A1")
        self.assertEqual(d["tied"], ["A1", "A2"])
        self.assertEqual(d["winner"], "A2")

    def test_the_time_tie_break_picks_the_faster_of_near_cost_tied_arms(self):
        arm_rows = {"A1": self.rows("A1", [90, 92, 91, 93, 90, 92], 30),
                    "A2": self.rows("A2", [89, 90, 90, 91, 89, 90], 10),
                    "A3": self.rows("A3", [90, 91, 90, 92, 90, 91], 10.5)}
        per_arm = self.summarise(arm_rows)
        for arm, wall in (("A1", 100), ("A2", 900), ("A3", 300)):
            per_arm[arm]["wall_s_median"] = wall
        d = rx.decide(arm_rows, per_arm, self.SCORING)
        self.assertEqual(d["winner"], "A2")
        d = rx.decide(arm_rows, per_arm, dict(self.SCORING, cost_tie_pct=10))
        self.assertEqual(d["winner"], "A3")
        self.assertIn("time tie-break", d["reason"])
        # A1 is faster still but costs 3x the cheapest: outside the band, never picked.
        d = rx.decide(arm_rows, per_arm, dict(self.SCORING, cost_tie_pct=1))
        self.assertEqual(d["winner"], "A2")

    def test_paired_gap_reports_its_spread_and_percentiles_are_nearest_rank(self):
        a = self.rows("A1", [90, 92, 94], 1)
        b = self.rows("A2", [90, 90, 90], 1)
        gap = rx.paired_gap(a, b, 200, 0.95, seed=1)
        self.assertEqual(gap["pairs"], 3)
        self.assertAlmostEqual(gap["mean"], 2.0)
        self.assertAlmostEqual(gap["sd"], 2.0)
        self.assertEqual(rx._pct([5, 1, 3, None, 4, 2], 0.5), 3)
        self.assertEqual(rx._pct([5, 1, 3, 4, 2], 0.9), 5)
        self.assertIsNone(rx._pct([None], 0.5))

    def test_an_arm_below_the_solve_floor_cannot_win(self):
        arm_rows = {"A1": self.rows("A1", [80] * 6, 30),
                    "A3": self.rows("A3", [99] * 6, 1, solved=False)}
        d = rx.decide(arm_rows, self.summarise(arm_rows), self.SCORING)
        self.assertEqual(d["eligible"], ["A1"])
        self.assertEqual(d["winner"], "A1")

    def test_statistics_helpers(self):
        lo, hi = rx.wilson(9, 9)
        self.assertGreater(lo, 0.6)
        self.assertEqual(hi, 1.0)
        self.assertEqual(rx.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertEqual(rx.spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)
        self.assertEqual(rx.pareto({"A": {"n": 1, "qs_mean": 90, "aic_mean": 10},
                                    "B": {"n": 1, "qs_mean": 80, "aic_mean": 20},
                                    "C": {"n": 1, "qs_mean": 70, "aic_mean": 5}}), ["A", "C"])

    def test_judge_output_parsing(self):
        labels = {"W": "A1", "X": "A3"}
        row = {"correctness": 8, "readability": 7, "design": 7, "tests": 6, "scope": 9,
               "overall": 7, "rationale": "fine"}
        text = "noise " + json.dumps({"candidates": {"W": row, "X": dict(row, overall=4)}})
        parsed = rx.parse_judge(text, labels)
        self.assertEqual(parsed["A3"]["overall"], 4.0)
        self.assertIsNone(rx.parse_judge(json.dumps({"candidates": {"W": row}}), labels))
        self.assertIsNone(rx.parse_judge(json.dumps(
            {"candidates": {"W": row, "X": dict(row, overall=11)}}), labels))
        self.assertIsNone(rx.parse_judge("no json at all", labels))


class JudgeV2Tests(unittest.TestCase):
    LABELS = {"W": "A2", "X": "A5", "Y": "A3"}

    def response(self, ranking=("X", "W", "Y"), checklist=(True, False), overall=7, **extra):
        cands = {label: {"checklist": list(checklist), "overall": overall, "rationale": "r"}
                 for label in self.LABELS}
        cands.update(extra)
        return "chatter " + json.dumps({"candidates": cands, "ranking": list(ranking)})

    def test_rubric_rank_parsing_is_strict(self):
        parsed = rx.parse_judge_rubric_rank(self.response(), self.LABELS, 2)
        self.assertEqual(parsed["ranking"], ["A5", "A2", "A3"])
        self.assertEqual(parsed["scores"]["A2"]["rubric_share"], 0.5)
        for bad in (self.response(ranking=("X", "W")),
                    self.response(ranking=("X", "W", "W")),
                    self.response(checklist=(True,)),
                    self.response(checklist=(1, 0)),
                    self.response(overall=11),
                    self.response(overall=True),
                    "no json"):
            self.assertIsNone(rx.parse_judge_rubric_rank(bad, self.LABELS, 2))

    def test_the_prompt_carries_the_rubric_and_names_no_arm(self):
        task = {"prompt_text": "Do it.", "rubric": ["First thing.", "Second thing."]}
        text = rx.judge_prompt_rubric_rank(task, [("W", "+a"), ("X", "+b")])
        self.assertIn("1. First thing.", text)
        self.assertIn("2 booleans", text)
        self.assertNotRegex(text.lower(), r"\b(a2|a5|luna|opus|sol|gpt|claude)\b")

    def record(self, judge, ranking, share=1.0, retest=False, key=None):
        return {"key": key or f"T4-r1-j{judge}" + ("-c" if retest else ""), "task": "T4",
                "repeat": 1, "judge_index": judge, "parsed": True, "ranking": ranking,
                "consistency": retest or None,
                "scores": {a: {"rubric_share": share, "overall": 5.0} for a in ranking}}

    def test_quality_is_half_checklist_half_rank_and_retests_never_count(self):
        records = [self.record(0, ["A5", "A2", "A3"], share=0.5),
                   self.record(0, ["A3", "A2", "A5"], share=0.0, retest=True)]
        q = rx.judge_quality(records)
        self.assertAlmostEqual(q[("T4", 1, "A5")], 0.75)
        self.assertAlmostEqual(q[("T4", 1, "A2")], 0.5)
        self.assertAlmostEqual(q[("T4", 1, "A3")], 0.25)

    def test_kendall_w_and_test_retest(self):
        self.assertAlmostEqual(rx.kendall_w([["a", "b", "c"]] * 3), 1.0)
        self.assertAlmostEqual(rx.kendall_w([["a", "b"], ["b", "a"]]), 0.0)
        self.assertIsNone(rx.kendall_w([["a", "b"]]))
        records = [self.record(0, ["A5", "A2", "A3"]), self.record(1, ["A5", "A2", "A3"]),
                   self.record(0, ["A5", "A3", "A2"], retest=True)]
        agreement = rx.judge_agreement(records)
        self.assertAlmostEqual(agreement["kendall_w_mean"], 1.0)
        self.assertEqual(agreement["groups"], 1)
        self.assertAlmostEqual(agreement["retest_spearman_mean"], 0.5)
        self.assertEqual(agreement["retest_top_pick_agreement"], 1.0)


class FakeCopilot:
    """An injected dispatch runner: acts by role in the sandbox, logs a fake session."""

    def __init__(self, home, verdicts=None, write_in_verifier=False):
        self.home = Path(home)
        self.calls = []
        self.prompts = []
        self.verdicts = list(verdicts or [])
        self.write_in_verifier = write_in_verifier

    def __call__(self, argv, cwd, timeout):
        prompt = argv[argv.index("-p") + 1]
        model = argv[argv.index("--model") + 1]
        session = argv[argv.index("--session-id") + 1]
        cwd = Path(cwd)
        role = next((r for r in ("PLANNER", "TEST AUTHOR", "IMPLEMENTER", "VERIFIER",
                                 "REVIEWER") if f"YOUR JOB: {r}" in prompt), "SOLO")
        self.calls.append(role)
        self.prompts.append(prompt)
        reply = "ok"
        if role in ("IMPLEMENTER", "SOLO"):
            (cwd / "bin" / "calc.py").write_text(rx.DEMO_FIXED)
        if role in ("TEST AUTHOR", "SOLO"):
            (cwd / "tests" / "test_calc_zero.py").write_text(rx.DEMO_STRONG_TESTS)
        if role in ("VERIFIER", "REVIEWER"):
            reply = self.verdicts.pop(0) if self.verdicts else (
                "VERIFY VERDICT=pass" if role == "VERIFIER" else "REVIEW VERDICT=accept")
            if role == "VERIFIER" and self.write_in_verifier:
                (cwd / "notes.txt").write_text("scribble")
        log = self.home / "session-state" / session
        log.mkdir(parents=True, exist_ok=True)
        (log / "events.jsonl").write_text(events(shutdown(
            {model: {"tokenDetails": details(1000, 4000, 0, 200), "totalNanoAiu": 0}})))
        return {"rc": 0, "outcome": "ok", "stdout": reply, "output": reply, "duration_s": 0.01,
                "timed_out": False}


class DriverTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="route-exp-test-")
        self.root = Path(self._tmp.name)
        exp_dir, self.repo, self.stub, self.home = rx.build_demo(self.root, PRICING)
        self.exp_dir = exp_dir
        self.exp, self.digest = rx.load_experiment(exp_dir, PRICING)
        self.store = self.root / "store"

    def tearDown(self):
        self._tmp.cleanup()

    def driver(self, runner=None, max_aic=10000, live=True, run_id="t-run", **kw):
        return rx.Experiment(self.exp, self.digest, PRICING, self.store, run_id,
                             binary=str(self.stub), copilot_home=self.home, repo=self.repo,
                             exec_mode="trusted-host", live=live, max_aic=max_aic,
                             dispatch_runner=runner, out=io.StringIO(), **kw)

    def trial(self, arm):
        return next(t for t in rx.trial_plan(self.exp, 1) if t["arm"] == arm)

    def test_a_failed_verification_gets_exactly_one_rework_then_a_reverify(self):
        fake = FakeCopilot(self.home, verdicts=["VERIFY VERDICT=fail", "VERIFY VERDICT=pass",
                                                "REVIEW VERDICT=accept"])
        ex = self.driver(fake)
        ex.open_run(1)
        record = ex.run_trial(self.trial("A1"))
        self.assertEqual(fake.calls, ["PLANNER", "TEST AUTHOR", "IMPLEMENTER", "VERIFIER",
                                      "IMPLEMENTER", "VERIFIER", "REVIEWER"])
        self.assertEqual(record["reworks"], 1)
        self.assertEqual([v["verdict"] for v in record["verdicts"]], ["fail", "pass", "accept"])
        self.assertEqual(record["status"], "complete")
        self.assertEqual(record["unmeasured_dispatches"], 0)
        self.assertAlmostEqual(record["aic"], sum(d["aic_charged"] for d in record["dispatches"]))

    def test_rework_is_bounded_even_when_every_gate_says_no(self):
        fake = FakeCopilot(self.home, verdicts=["VERIFY VERDICT=fail"] * 2 +
                           ["REVIEW VERDICT=reject", "VERIFY VERDICT=fail"])
        ex = self.driver(fake)
        ex.open_run(1)
        record = ex.run_trial(self.trial("A2"))
        self.assertEqual(len(fake.calls), 9)
        self.assertEqual(record["reworks"], 2)

    def test_a_read_only_stage_that_writes_is_a_recorded_violation(self):
        ex = self.driver(FakeCopilot(self.home, write_in_verifier=True))
        ex.open_run(1)
        record = ex.run_trial(self.trial("A1"))
        self.assertEqual(record["fence"][0]["kind"], "read-only-stage-wrote")
        self.assertEqual(record["fence"][0]["paths"], ["notes.txt"])

    def test_verdict_accuracy_is_judged_on_the_patch_the_gate_saw(self):
        fake = FakeCopilot(self.home, verdicts=["VERIFY VERDICT=fail", "VERIFY VERDICT=pass",
                                                "REVIEW VERDICT=accept"])
        ex = self.driver(fake)
        ex.open_run(1)
        record = ex.run_trial(self.trial("A1"))
        grade = ex.grade_trial(record)
        self.assertTrue(grade["oracle"]["score"] == 1.0)
        self.assertEqual(grade["verdicts"][0]["incorrect_rejection"], True)
        self.assertEqual([v["correct"] for v in grade["verdicts"]], [False, True, True])
        # The demo samples 6 of 7 mutants (seeded by patch sha); 5 are oracle-killable and the
        # strong tests miss only `100 / part / whole` (pct(1, 3) still rounds to 33). Stale
        # bytecode for same-size mutants once masked a kill here (3/5).
        self.assertEqual((grade["mutation"]["considered"], grade["mutation"]["killed"]), (5, 4))

    def test_the_ceiling_stops_before_the_first_dispatch(self):
        fake = FakeCopilot(self.home)
        ex = self.driver(fake, max_aic=0.001)
        self.assertEqual(ex.run(1), 4)
        self.assertEqual(fake.calls, [])
        stopped = ex.records("trials")
        self.assertEqual(stopped[0]["status"], "stopped")

    def test_an_unreadable_session_log_is_charged_its_estimate(self):
        fake = FakeCopilot(self.root / "elsewhere")
        ex = self.driver(fake)
        ex.open_run(1)
        record = ex.run_trial(self.trial("A4"))
        d = record["dispatches"][0]
        self.assertIsNone(d["usage"])
        self.assertGreater(d["aic_charged"], 0)
        self.assertIn("unmeasured", d["aic_basis"])
        self.assertEqual(record["unmeasured_dispatches"], 1)

    def test_a_rerun_failed_trial_keeps_the_failed_attempts_spend(self):
        fake = FakeCopilot(self.home)

        def flaky(argv, cwd, timeout):
            result = fake(argv, cwd, timeout)
            if len(fake.calls) == 1:
                result.update({"rc": 1, "outcome": "failed", "stdout": "", "output": ""})
            return result

        ex = self.driver(flaky)
        only = {self.trial("A4")["trial_id"]}
        self.assertEqual(ex.run(1, only=only), 0)
        first = ex.records("trials")[0]
        self.assertEqual(first["status"], "dispatch-failed")
        lost = first["dispatches"][0]["aic_charged"]
        self.assertGreater(lost, 0)
        self.assertEqual(ex.run(1, only=only), 0)
        second = ex.records("trials")[0]
        self.assertEqual(second["status"], "complete")
        self.assertEqual(second["attempt"], 2)
        self.assertEqual(len(second["prior_attempts"]), 1)
        self.assertTrue(second["dispatches"][0]["output_file"].endswith("/a2-01-solo.txt"))
        self.assertAlmostEqual(ex.spent(), lost + second["aic"])
        report = rx.build_report(ex)
        self.assertEqual(report["failed_spend"]["dispatches"], 1)
        self.assertAlmostEqual(report["failed_spend"]["measured_aic"], round(lost, 3))
        self.assertAlmostEqual(report["per_arm"]["A4"]["aic_total"], round(second["aic"], 3))

    def test_an_outage_stops_the_run_after_a_streak_of_failed_dispatches(self):
        calls = []

        def down(argv, cwd, timeout):
            calls.append(argv)
            return {"rc": 1, "outcome": "failed", "stdout": "", "output": "",
                    "duration_s": 0.01, "timed_out": False}

        ex = self.driver(down)
        self.assertEqual(ex.run(1), 5)
        self.assertEqual(len(calls), rx.FAILURE_STREAK_LIMIT)
        self.assertEqual([t["status"] for t in ex.records("trials")],
                         ["dispatch-failed"] * rx.FAILURE_STREAK_LIMIT)

    def add_arm(self, arm, shape, stages):
        self.exp["arms"][arm] = {"label": arm, "shape": shape, "stages": {
            role: {"model": self.exp["arms"]["A4"]["stages"]["solo"]["model"],
                   "effort": "high"} for role in stages}}
        return dict(self.trial("A4"), arm=arm,
                    trial_id=self.trial("A4")["trial_id"].replace("A4", arm))

    def test_a_reviewed_one_shot_reworks_once_per_reject_then_re_reviews(self):
        trial = self.add_arm("A6", "reviewed", ("solo", "reviewer"))
        fake = FakeCopilot(self.home, verdicts=["REVIEW VERDICT=reject",
                                                "REVIEW VERDICT=accept"])
        ex = self.driver(fake)
        ex.open_run(1)
        record = ex.run_trial(trial)
        self.assertEqual(fake.calls, ["SOLO", "REVIEWER", "SOLO", "REVIEWER"])
        self.assertIn("FINDINGS TO ADDRESS (from the reviewer)", fake.prompts[2])
        self.assertIn("REVIEW VERDICT=reject", fake.prompts[2])
        self.assertEqual(record["status"], "complete")
        self.assertEqual(record["reworks"], 1)
        self.assertEqual([v["verdict"] for v in record["verdicts"]], ["reject", "accept"])
        grade = ex.grade_trial(record)
        self.assertEqual(grade["oracle"]["score"], 1.0)

    def test_a_reviewed_one_shot_stops_after_its_rework_budget(self):
        trial = self.add_arm("A6", "reviewed", ("solo", "reviewer"))
        fake = FakeCopilot(self.home, verdicts=["REVIEW VERDICT=reject"] * 5)
        ex = self.driver(fake)
        ex.open_run(1)
        record = ex.run_trial(trial)
        budget = self.exp["rework"]["after_reviewer_reject"]
        self.assertEqual(record["reworks"], budget)
        self.assertEqual(fake.calls.count("REVIEWER"), budget + 1)

    def test_a_pipeline_without_a_reviewer_ends_at_the_verifier(self):
        trial = self.add_arm("A7", "pipeline",
                             ("planner", "test_author", "implementer", "verifier"))
        ex = self.driver(FakeCopilot(self.home))
        ex.open_run(1)
        record = ex.run_trial(trial)
        self.assertEqual(ex.dispatch_runner.calls,
                         ["PLANNER", "TEST AUTHOR", "IMPLEMENTER", "VERIFIER"])
        self.assertEqual(record["status"], "complete")

    def test_the_new_shapes_validate_and_estimate_only_their_own_stages(self):
        raw = json.loads((rx.EXPERIMENT_DIR / "experiment.json").read_text())
        luna = raw["arms"]["A1"]["stages"]["implementer"]
        raw["arms"]["A6"] = {"label": "x", "shape": "reviewed",
                             "stages": {"solo": luna, "reviewer": luna}}
        raw["arms"]["A7"] = {"label": "y", "shape": "pipeline", "stages": {
            k: v for k, v in raw["arms"]["A1"]["stages"].items() if k != "reviewer"}}
        rx.validate_definition(raw, PRICING)
        full = rx.arm_estimate(raw, PRICING, "A1")
        lean = rx.arm_estimate(raw, PRICING, "A7")
        self.assertLess(lean["max"], full["max"])
        self.assertEqual(rx.arm_estimate(raw, PRICING, "A6")["dispatches_min"], 2)
        raw["arms"]["A6"]["stages"]["planner"] = luna
        with self.assertRaisesRegex(rx.ConfigError, "reviewed"):
            rx.validate_definition(raw, PRICING)

    def test_rescan_remeasures_an_estimate_charged_dispatch_whose_log_now_exists(self):
        fake = FakeCopilot(self.home)
        ex = self.driver(fake)
        tid = self.trial("A4")["trial_id"]
        ex.run(1, only={tid}, grade=False)
        record = ex.records("trials")[0]
        measured = record["dispatches"][0]["aic_charged"]
        # Simulate the outage: the log was unreadable at dispatch time, estimate charged.
        record["dispatches"][0].update({"usage": None, "aic_charged": 99.0,
                                        "aic_basis": "unmeasured -- estimate charged"})
        record.update({"aic": 99.0, "unmeasured_dispatches": 1})
        ex.write(f"trials/{tid}.json", record)
        self.assertEqual(len(ex.rescan()), 1)
        after = ex.records("trials")[0]
        self.assertAlmostEqual(after["aic"], measured)
        self.assertEqual(after["unmeasured_dispatches"], 0)
        self.assertEqual(after["remeasures"][0]["dispatches"][0]["estimate_aic"], 99.0)
        self.assertIn("late", after["dispatches"][0]["aic_basis"])
        self.assertEqual(ex.rescan(), [])

    def test_the_v2_report_sections_render_spread_outage_and_sensitivity(self):
        self.exp["scoring"]["extended_report"] = True
        fake = FakeCopilot(self.home)
        ex = self.driver(fake)
        self.assertEqual(ex.run(1), 0)
        report = rx.build_report(ex)
        a4 = report["per_arm"]["A4"]
        self.assertIn("solo", a4["efforts"])
        self.assertEqual(a4["estimate_charged"]["dispatches"], 0)
        self.assertIsNotNone(a4["wall_s_median"])
        text = rx.render_report(report)
        self.assertIn("## Cost and time spread", text)
        del self.exp["scoring"]["extended_report"]
        self.assertNotIn("## Cost and time spread", rx.render_report(rx.build_report(ex)))

    def write_judges(self, ex, rankings):
        for j, ranking in enumerate(rankings):
            ex.write(f"judges/T1-r1-j{j}.json", {
                "key": f"T1-r1-j{j}", "task": self.trial("A4")["task"], "repeat": 1,
                "judge_index": j, "parsed": True, "mode": "rubric_rank", "ranking": ranking,
                "arms": sorted(ranking), "dispatches": [],
                "scores": {a: {"rubric_share": 1.0, "overall": 8.0} for a in ranking}})

    def test_low_judge_agreement_drops_quality_for_every_arm(self):
        self.exp["scoring"].update({"quality_mode": "rubric_rank", "judge_min_agreement": 0.5})
        ex = self.driver(FakeCopilot(self.home))
        self.assertEqual(ex.run(1), 0)
        arms = sorted(self.exp["arms"])
        self.write_judges(ex, [arms, arms[::-1]])
        report = rx.build_report(ex)
        self.assertEqual(report["dropped_components"], ["quality"])
        self.assertIn("Kendall", report["drop_reason"])
        self.assertIn("Left out for every arm: quality", rx.render_report(report))
        self.write_judges(ex, [arms, arms])
        report = rx.build_report(ex)
        self.assertEqual(report["dropped_components"], [])
        self.assertIn("Rank agreement: mean Kendall's W 1.00", rx.render_report(report))

    def test_the_median_basis_scores_simplicity_against_solved_candidates(self):
        ex = self.driver(FakeCopilot(self.home))
        self.assertEqual(ex.run(1), 0)
        basis = rx.simplicity_basis(ex, {g["trial_id"]: g for g in ex.records("grades")})
        task = self.trial("A4")["task"]
        self.assertEqual(basis[task]["basis"], "median")
        self.assertEqual(basis[task]["candidates"], 1 + len(self.exp["arms"]))
        self.exp["scoring"]["simplicity_basis"] = "median"
        self.assertTrue(rx.build_report(ex)["rows"])

    def test_the_probe_scores_each_gate_on_naive_and_reference_patches(self):
        for task in self.exp["task_defs"].values():
            task["naive_text"] = task["reference_text"]
        fake = FakeCopilot(self.home, verdicts=["REVIEW VERDICT=reject", "REVIEW VERDICT=accept",
                                                "VERIFY VERDICT=fail", "VERIFY VERDICT=fail"])
        ex = self.driver(fake)
        ex.open_run(1)
        plan = ex.probe_plan()
        self.assertEqual(len(plan), 2 * len(ex.gate_stages()) * len(self.exp["tasks"]))
        self.assertEqual(ex.probe(), 0)
        self.assertEqual(fake.calls, ["REVIEWER", "REVIEWER", "VERIFIER", "VERIFIER"])
        for prompt in fake.prompts:
            self.assertNotIn(rx.ORACLE_TEST_NAME, prompt)
        summary = {g["role"]: g for g in rx.probe_summary(ex.records("probes"))}
        self.assertEqual((summary["verifier"]["sensitivity"], summary["verifier"]["specificity"]),
                         (1.0, 0.0))
        self.assertEqual((summary["reviewer"]["sensitivity"], summary["reviewer"]["specificity"]),
                         (1.0, 1.0))
        self.assertGreater(ex.spent(), 0)
        self.assertEqual(ex.probe(), 0)
        self.assertEqual(len(fake.calls), 4)
        self.exp["probe"] = {"repeats": 1}
        plan = rx.build_plan(self.exp, "0" * 64, PRICING, 1)
        self.assertEqual(plan["probe"]["dispatches"], 4)
        self.assertGreater(plan["probe"]["aic"], 0)
        self.assertIn("Gate probe (separate command)", rx.render_plan(plan, self.exp))

    def test_rescan_reclassifies_from_the_session_logs_with_an_audit_trail(self):
        fake = FakeCopilot(self.home)
        ex = self.driver(fake)
        tid = self.trial("A4")["trial_id"]
        ex.run(1, only={tid}, grade=False)
        record = ex.records("trials")[0]
        # Simulate a verdict from an older, over-eager classifier.
        record["dispatches"][0]["contamination"] = ["nested-cli"]
        record.update({"status": "contaminated", "contamination": ["nested-cli"]})
        ex.write(f"trials/{tid}.json", record)
        self.assertEqual(ex.rescan(), [(tid, ["nested-cli"], [], "complete")])
        after = ex.records("trials")[0]
        self.assertEqual(after["status"], "complete")
        self.assertEqual(after["rescans"][0]["status_before"], "contaminated")
        self.assertEqual(ex.rescan(), [])

    def test_resuming_under_a_changed_definition_is_refused(self):
        ex = self.driver(FakeCopilot(self.home))
        ex.open_run(1)
        other = rx.Experiment(self.exp, "0" * 64, PRICING, self.store, "t-run",
                              copilot_home=self.home, repo=self.repo, out=io.StringIO())
        with self.assertRaisesRegex(rx.ConfigError, "preregistration"):
            other.open_run(1)

    def write_extension(self, model=None):
        model = model or self.exp["arms"]["A3"]["stages"]["solo"]["model"]
        ext_dir = Path(self.exp_dir) / "extensions"
        ext_dir.mkdir(exist_ok=True)
        (ext_dir / "A5.json").write_text(json.dumps({
            "version": rx.EXTENSION_VERSION, "arm": "A5", "reason": "post-hoc probe",
            "definition": {"label": "probe one-shot", "shape": "one-shot",
                           "stages": {"solo": {"model": model,
                                               "effort": self.exp["arms"]["A3"]["stages"][
                                                   "solo"]["effort"]}}}}), encoding="utf-8")
        exp, digest = rx.load_experiment(self.exp_dir, PRICING)
        return exp, digest

    def test_an_extension_arm_keeps_the_preregistered_digest_and_needs_an_opt_in(self):
        exp, digest = self.write_extension()
        self.assertEqual(digest, self.digest)
        self.assertNotIn("A5", exp["arms"])
        self.assertIn("A5", exp["extensions"])
        self.exp = exp
        fake = FakeCopilot(self.home)
        ex = self.driver(fake)
        self.assertEqual(ex.run(1, grade=False), 0)
        self.assertNotIn("A5", {t["arm"] for t in ex.records("trials")})
        self.assertNotIn("extensions", ex.read_json("run.json"))

    def test_extending_a_run_adds_only_the_new_arm_and_reports_it_apart(self):
        exp, _ = self.write_extension()
        self.exp = exp
        fake = FakeCopilot(self.home)
        ex = self.driver(fake)
        self.assertEqual(ex.run(1), 0)
        task = self.exp["tasks"][0]
        arms = sorted(self.exp["arms"])
        for j in (0, 1):
            ex.write(f"judges/D1-r1-j{j}.json", {
                "key": f"D1-r1-j{j}", "task": task, "repeat": 1, "judge_index": j,
                "arms": arms, "parsed": True, "dispatches": [],
                "scores": {a: {"overall": 5 + i} for i, a in enumerate(arms)}})
        before = rx.build_report(ex)
        self.assertIsNone(before.get("extended"))
        calls = len(fake.calls)
        self.assertEqual(ex.run(1, extend=["A5"]), 0)
        self.assertEqual(len(fake.calls), calls + 1)
        self.assertEqual(fake.calls[-1], "SOLO")
        manifest = ex.read_json("run.json")
        self.assertEqual(sorted(manifest["arms"]), arms)
        entry = manifest["extensions"][0]
        self.assertEqual((entry["arm"], entry["trials_before"]), ("A5", 4))
        self.assertEqual(entry["digest"], exp["extensions"]["A5"]["digest"])
        self.assertEqual(ex.preregistered_arms(), arms)
        self.assertNotIn("A5", next(iter(ex.judge_groups().values())))
        after = rx.build_report(ex)
        self.assertEqual(after["arms"], arms)
        self.assertEqual({a: p["qs_mean"] for a, p in after["per_arm"].items()},
                         {a: p["qs_mean"] for a, p in before["per_arm"].items()})
        self.assertEqual(after["decision"]["winner"], before["decision"]["winner"])
        extended = after["extended"]
        self.assertEqual(extended["arms"], arms + ["A5"])
        self.assertEqual(extended["dropped_components"], ["quality"])
        self.assertTrue(all(r["components"]["quality"] is None for r in extended["rows"]))
        text = rx.render_report(after)
        self.assertIn("## Post-hoc extension view -- all arms", text)
        self.assertIn("### Decision (preregistered rule), applied post hoc", text)
        self.assertLess(text.index("Post-hoc extension view"), len(text))
        self.assertEqual(ex.run(1, extend=["A5"]), 0)
        self.assertEqual(len(fake.calls), calls + 1)
        self.assertEqual(len(ex.read_json("run.json")["extensions"]), 1)

    def test_a_changed_or_missing_extension_is_refused_on_resume(self):
        exp, _ = self.write_extension()
        self.exp = exp
        ex = self.driver(FakeCopilot(self.home))
        ex.open_run(1, extend=["A5"])
        changed, digest = self.write_extension(model=self.exp["arms"]["A4"]["stages"]["solo"][
            "model"])
        other = rx.Experiment(changed, digest, PRICING, self.store, "t-run",
                              copilot_home=self.home, repo=self.repo, out=io.StringIO())
        with self.assertRaisesRegex(rx.ConfigError, "extension arm A5"):
            other.open_run(1)
        with self.assertRaisesRegex(rx.ConfigError, "no extension arm 'A6'"):
            ex.open_run(1, extend=["A6"])

    def test_an_extension_may_not_reuse_an_arm_id_or_skip_its_reason(self):
        ext_dir = Path(self.exp_dir) / "extensions"
        ext_dir.mkdir()
        body = {"version": rx.EXTENSION_VERSION, "arm": "A1", "reason": "x",
                "definition": self.exp["arms"]["A3"]}
        (ext_dir / "x.json").write_text(json.dumps(body), encoding="utf-8")
        with self.assertRaisesRegex(rx.ConfigError, "already exists"):
            rx.load_experiment(self.exp_dir, PRICING)
        body.update(arm="A7", reason="")
        (ext_dir / "x.json").write_text(json.dumps(body), encoding="utf-8")
        with self.assertRaisesRegex(rx.ConfigError, "reason"):
            rx.load_experiment(self.exp_dir, PRICING)

    def test_contaminated_trials_are_excluded_from_the_score(self):
        fake = FakeCopilot(self.home)
        ex = self.driver(fake)
        ex.markers.append("bin/calc.py")
        original = fake.__call__

        def leaky(argv, cwd, timeout):
            result = original(argv, cwd, timeout)
            session = argv[argv.index("--session-id") + 1]
            log = self.home / "session-state" / session / "events.jsonl"
            log.write_text(events({"type": "tool.execution_start",
                                   "data": {"toolName": "view",
                                            "arguments": {"path": "bin/calc.py"}}})
                           + log.read_text())
            return result

        ex.dispatch_runner = leaky
        ex.run(1, only={self.trial("A3")["trial_id"]})
        report = rx.build_report(ex)
        self.assertEqual(report["scored"], 0)
        self.assertEqual(report["excluded"][0]["reason"], "contaminated")

    def test_the_demo_runs_the_whole_pipeline_offline(self):
        out = io.StringIO()
        with mock.patch.object(rx, "run_demo", wraps=rx.run_demo):
            self.assertEqual(rx.run_demo(out=out), 0)
        text = out.getvalue()
        self.assertIn("VALID", text)
        self.assertIn("**Winner:", text)
        self.assertIn("Pipeline gates vs the hidden oracle", text)


class CliTests(unittest.TestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                rc = rx.main(list(argv))
            except SystemExit as exc:
                rc = exc.code
        return rc, out.getvalue(), err.getvalue()

    def test_run_refuses_without_an_explicit_mode_or_ceiling(self):
        rc, _, err = self.run_cli("run")
        self.assertEqual(rc, 2)
        self.assertIn("--live", err)
        rc, _, err = self.run_cli("run", "--live")
        self.assertEqual(rc, 2)
        self.assertIn("--max-aic", err)

    def test_full_regression_requires_trusted_host(self):
        rc, _, err = self.run_cli("run", "--dry-run", "--full-regression")
        self.assertEqual(rc, 2)
        self.assertIn("trusted-host", err)

    def test_dry_run_spawns_nothing_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store"
            with mock.patch.object(rx._pr(), "run", side_effect=AssertionError("spawned")):
                rc, out, _ = self.run_cli("--store-dir", str(store), "run", "--dry-run")
            self.assertEqual(rc, 0)
            self.assertIn("DRY RUN", out)
            self.assertIn("gpt-6-luna/max", out)
            self.assertFalse(store.exists())

    def test_probe_dry_run_spawns_nothing_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store"
            with mock.patch.object(rx._pr(), "run", side_effect=AssertionError("spawned")):
                rc, out, _ = self.run_cli("--store-dir", str(store), "probe", "--dry-run",
                                          "--run", "dry")
            self.assertEqual(rc, 0)
            self.assertIn("gate probes over", out)
            self.assertFalse(store.exists())
        rc, _, err = self.run_cli("probe", "--live", "--run", "dry")
        self.assertEqual(rc, 2)
        self.assertIn("--max-aic", err)

    def test_plan_json_is_machine_readable(self):
        rc, out, _ = self.run_cli("plan", "--json", "--repeats", "1")
        self.assertEqual(rc, 0)
        plan = json.loads(out)
        self.assertEqual(len(plan["trials"]), 12)

    def test_the_store_is_registered(self):
        rd = _load("runtime_data")
        self.assertIn(rx.STORE_NAME, rd.STORES)
        self.assertIn(f"/{rx.STORE_NAME}/", (ROOT / ".gitignore").read_text().splitlines())


if __name__ == "__main__":
    unittest.main()
