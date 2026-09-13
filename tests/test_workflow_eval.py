"""bin/workflow_eval.py (step 25): workflows compared on held-out tasks through the repo_bench
seam, every dispatch in the attempt ledger, oracle grading identical across workflows, per-basis
usage never summed, security outcomes recorded, a priced plan that dispatches nothing, and the
reviewed / versioned / reversible routing-policy process.

SAFETY CONTRACT. No test here runs a harness CLI. Every dispatch is a throwaway shell stub in a
temp dir (through the process runner) or an injected Python callable; every store, prefs dir and
ledger is a temp dir; the per-user data root is patched for the module. `git` is used only to
build fixture repositories the evaluator then reads. Verify commands run under the execution
boundary in `trusted-host` mode -- the confinement itself is proven in tests/test_exec_policy.py.
"""

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_workflow_eval_test", BIN_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


we = _load("workflow_eval")
rb = we._rb()
kc = we._kc()
al = we._al()

_DATA_HOME = None
_DATA_HOME_PATCH = None


def setUpModule():
    # Patched for THIS module's run only. Discovery imports every test module before any
    # runs, so an import-time write to os.environ would leak into every other module and
    # the subprocesses they spawn (test_lessons_promote's default journal path moved).
    global _DATA_HOME, _DATA_HOME_PATCH
    _DATA_HOME = tempfile.TemporaryDirectory(prefix="polytropos-test-data-")
    _DATA_HOME_PATCH = mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": _DATA_HOME.name})
    _DATA_HOME_PATCH.start()


def tearDownModule():
    _DATA_HOME_PATCH.stop()
    _DATA_HOME.cleanup()


def _git(repo, *args):
    proc = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
         "-c", "init.defaultBranch=fixture", "-c", "commit.gpgsign=false", *args],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"fixture git {args} failed: {proc.stdout}{proc.stderr}")
    return proc.stdout


FAKE_KEY = "AKIAABCDEFGHIJKLMNOP"


def build_repo(root, secret=False, strict=False):
    """Base: m.py returns 1, run_tests.py passes when tests/ is absent. Fix commit ('fixes #1')
    changes m.py and adds tests/test_m.py, so the kit's own check accepts an idle candidate
    while the withheld test fails it. `strict` makes the repository's own check demand the fix
    (it fails at base), for the resume scenarios."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "m.py").write_text("def f():\n    return 1\n")
    if strict:
        # exec, not import: a .pyc written by the recon check would be reused for a same-size
        # rewrite within the same second (pyc headers keep mtime in whole seconds), and the
        # check would judge stale bytecode.
        (root / "run_tests.py").write_text("ns = {}\nexec(open('m.py').read(), ns)\nassert ns['f']() == 2\n")
    else:
        (root / "run_tests.py").write_text(
            "import os, runpy\nif os.path.exists('tests/test_m.py'):\n    runpy.run_path('tests/test_m.py')\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "start")
    (root / "m.py").write_text("def f():\n    return 2\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_m.py").write_text("import m\nassert m.f() == 2\n")
    _git(root, "add", "-A")
    body = "\n\nRepro key for the issue: " + FAKE_KEY if secret else ""
    _git(root, "commit", "-q", "-m", "fixes #1: f() should return 2" + body)
    return root


def test_runner(cmd, cwd):
    proc = subprocess.run([sys.executable, "run_tests.py"], cwd=str(cwd), capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


STUB = """#!/bin/sh
# argv: --task ID --model M --workspace DIR [--mode ask] PROMPT
mode=write
for a in "$@"; do [ "$a" = "ask" ] && mode=ask; done
prompt=$(eval "echo \\"\\$$#\\"")
printf '===CALL=== %s %s %s %s\\n' "$2" "$4" "$mode" "$PWD" >> "%LOG%"
printf '%s' "$prompt" > "%PROMPTS%/$2.$mode.txt"
if [ "$mode" = "ask" ]; then
  if [ "$4" = "yes-reviewer" ]; then echo "REVIEW VERDICT=accept"; exit 0; fi
  case "$prompt" in *"+    return 2"*) echo "REVIEW VERDICT=accept";; *) echo "REVIEW VERDICT=reject";; esac
  exit 0
fi
case "$4" in
  fixer)    printf 'def f():\\n    return 2\\n' > m.py ;;
  tamper)   printf 'def f():\\n    return 2\\n' > m.py; mkdir -p tests; printf 'assert True\\n' > tests/test_extra.py ;;
  observed) printf 'def f():\\n    return 2\\n' > m.py; echo "OBSERVED-MODEL=somebody-else" ;;
  crasher)  echo "boom" >&2; exit 3 ;;
  idler)    : ;;
esac
echo '{"type":"result","subtype":"success"}'
exit 0
"""

FIXTURE_PRICING = {
    "cached_date": "2020-01-01", "cache_read_multiplier": 0.5, "cache_write_multiplier_5m": 2.0,
    "models": {
        "fake-haiku-1": {"tier": "haiku", "input_per_mtok": 1.0, "output_per_mtok": 5.0},
        "fake-sonnet-1": {"tier": "sonnet", "input_per_mtok": 3.0, "output_per_mtok": 15.0},
        "fake-opus-1": {"tier": "opus", "input_per_mtok": 5.0, "output_per_mtok": 25.0},
    },
    "task_profiles": {"XS": {"input_tokens": 1000, "output_tokens": 100},
                      "S": {"input_tokens": 4000, "output_tokens": 400},
                      "M": {"input_tokens": 10000, "output_tokens": 1000},
                      "L": {"input_tokens": 20000, "output_tokens": 2000}},
}


def claude_fixture_adapter():
    adapter = we.claude_adapter()
    adapter["load_pricing"] = lambda: FIXTURE_PRICING
    return adapter


def fixing_runner(usage=None, model_marker=None, calls=None):
    """An injected Python runner: writes the fix, returns canned harness JSON with `usage`."""
    calls = calls if calls is not None else []

    def runner(argv, cwd):
        calls.append({"argv": list(argv), "cwd": str(cwd)})
        if "--mode" in argv and "ask" in argv:
            return 0, "REVIEW VERDICT=accept"
        if "-p" in argv or "exec" in argv or "--agent" in argv or "--task" in argv:
            (Path(cwd) / "m.py").write_text("def f():\n    return 2\n")
        payload = {"type": "result", "subtype": "success"}
        if usage is not None:
            payload["usage"] = usage
        return 0, json.dumps(payload)

    runner.calls = calls
    return runner


class _Case(unittest.TestCase):
    """A temp fixture repo, a stub, a temp store, a temp prefs dir, a log of calls."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.repo = build_repo(self.root / "target")
        self.store = self.root / "store"
        self.prefs = self.root / "prefs"
        self.log = self.root / "stub.log"
        self.prompts = self.root / "prompts"
        self.prompts.mkdir()
        self.stub = self.root / "stub"
        self.stub.write_text(STUB.replace("%LOG%", str(self.log)).replace("%PROMPTS%", str(self.prompts)))
        self.stub.chmod(0o755)

    def tearDown(self):
        self._tmp.cleanup()

    def stub_runner(self):
        pr = we._pr()

        def runner(argv, cwd):
            r = pr.run(argv, cwd=str(cwd), timeout=60, name="test stub")
            return r.get("rc"), (r.get("stdout") or "") + (r.get("stderr") or ""), r

        return runner

    def plan(self, models=("fixer",), workflows=("direct",), policies=("pinned",), repeats=1,
             adapter=None, repo=None, test_cmd=f"{sys.executable} run_tests.py", **kw):
        adapter = adapter or we.stub_adapter()
        tasks = []
        plan = we.build_plan(repo or self.repo, adapter["name"], list(models), workflows=workflows,
                             policies=policies, repeats=repeats, mode="issue-replay",
                             test_cmd=test_cmd, scratch_dir=self.root / "scratch",
                             adapter=adapter, tasks_out=tasks, test_runner=test_runner, **kw)
        plan["_variants_full"] = we.build_variants(adapter["name"], plan["candidates"], plan["workflows"],
                                                   plan["policies"], instructions=kw.get("instructions"),
                                                   review_model=kw.get("review_model"))
        return plan, tasks, adapter

    def evaluate(self, plan, tasks, adapter, runner=None, **kw):
        kw.setdefault("max_usd", 1000.0)
        kw.setdefault("exec_mode", "trusted-host")
        out = io.StringIO()
        ev = we.Evaluation(plan, tasks, adapter, store_dir=self.store, runner=runner or self.stub_runner(),
                           test_runner=test_runner, binary=str(self.stub), out=out, err=out, **kw)
        env = ev.run()
        return ev, env

    def calls(self):
        return [ln.split()[1:] for ln in self.log.read_text().splitlines() if ln.startswith("===CALL===")] \
            if self.log.exists() else []

    def ledger(self, run_dir, ns="eval"):
        return al.AttemptLedger(run_dir / "attempts", ns)


# ---- adapters on the repo_bench seam --------------------------------------------------------------------

class AdapterTests(unittest.TestCase):
    def test_every_adapter_builds_a_dispatch_and_a_read_only_review_with_the_prompt_verbatim(self):
        prompt = "[kit=eval run=r task=t001]\n\nfix it\n\nRULES"
        for name in we.HARNESSES:
            with self.subTest(harness=name):
                adapter = we.make_adapter(name)
                argv = adapter["build_argv"]("the-bin", "some-model", prompt, task_id="t001", workspace="/ws")
                review = adapter["build_review_argv"]("the-bin", "some-model", prompt, task_id="t001",
                                                      workspace="/ws")
                self.assertTrue(all(isinstance(a, str) for a in argv + review))
                self.assertIn(prompt, argv, "the prompt is one argument, never a shell string")
                self.assertIn(prompt, review)
                self.assertIn("some-model", argv)
                self.assertNotEqual(argv, review, "a review is a different, read-only dispatch")

    def test_each_review_form_is_the_harness_documented_read_only_shape(self):
        p = "do it"
        claude = we.claude_adapter()
        self.assertIn("--dangerously-skip-permissions", claude["build_argv"]("c", "m", p))
        rv = claude["build_review_argv"]("c", "m", p)
        self.assertNotIn("--dangerously-skip-permissions", rv)
        self.assertTrue(any(a.startswith("--allowedTools") or a == "--allowedTools" for a in rv), rv)
        codex = we.codex_adapter()
        self.assertIn("workspace-write", codex["build_argv"]("x", "m", p))
        self.assertIn("read-only", codex["build_review_argv"]("x", "m", p))
        copilot = we.copilot_adapter()
        imp, rev = copilot["build_argv"]("cp", "m", p), copilot["build_review_argv"]("cp", "m", p)
        self.assertIn("--allow-all-tools", imp)
        self.assertNotIn("--allow-all-tools", rev)
        self.assertIn("reviewer", rev)
        cursor = we.cursor_adapter()
        self.assertIn("--force", cursor["build_argv"]("agent", "m", p, task_id="t1", workspace="/w"))
        self.assertIn("ask", cursor["build_review_argv"]("agent", "m", p, task_id="t1", workspace="/w"))
        self.assertIn("ask", we.stub_adapter()["build_review_argv"]("s", "m", p, task_id="t1"))

    def test_every_adapter_drives_repo_bench_dispatch_cell_unchanged(self):
        """The seam is repo_bench's: each adapter is a `dispatch_cell` adapter as it stands."""
        with tempfile.TemporaryDirectory() as td:
            repo = build_repo(Path(td) / "target")
            tasks, _ = rb.mine_issue_tasks(repo, gh_runner=None)
            task = tasks[0]
            for name in we.HARNESSES:
                with self.subTest(harness=name):
                    adapter = we.make_adapter(name)
                    adapter["load_pricing"] = lambda: FIXTURE_PRICING
                    info, baseline = rb.prepare_cell_sandbox(task, repo, Path(td) / f"cell-{name}")
                    runner = fixing_runner(usage={"input_tokens": 1000, "output_tokens": 200})
                    record = rb.dispatch_cell(task, "fake-haiku-1", adapter, info["path"], runner=runner,
                                              claude_bin="stub-bin", estimated_usd=0.25, baseline_commit=baseline)
                    self.assertEqual(record["dispatch_rc"], 0)
                    self.assertIn("return 2", record["patch"])
                    self.assertEqual(record["usd_basis"], "actual" if name == "claude" else "estimated")

    def test_each_adapter_reads_only_its_own_pricing_file(self):
        files = {"claude": "pricing.json", "codex": "pricing.codex.json", "copilot": "pricing.copilot.json",
                 "cursor": "pricing.cursor.json"}
        for name, filename in files.items():
            with self.subTest(harness=name):
                own = json.loads((ROOT / "data" / filename).read_text())
                loaded = we.make_adapter(name)["load_pricing"]()
                self.assertEqual(loaded.get("cached_date"), own.get("cached_date"))
                self.assertEqual(list(loaded.get("models") or {}), list(own.get("models") or {}))
        self.assertEqual(we.stub_adapter()["load_pricing"]()["models"], {})

    def test_estimates_carry_each_harness_billing_basis(self):
        claude = we.claude_adapter()
        est = claude["estimate"]("fake-haiku-1", "XS", FIXTURE_PRICING)
        self.assertEqual(est["basis"], "estimated")
        self.assertAlmostEqual(est["usd"], rb.estimate_dispatch_usd("fake-haiku-1", "XS", FIXTURE_PRICING))
        codex = we.codex_adapter()
        pricing = codex["load_pricing"]()
        mid = codex["resolve_model"](pricing, "mid")
        est = codex["estimate"](mid, "M", pricing)
        self.assertEqual(est["basis"], "proxy")
        self.assertIsNone(est["usd"], "a subscription figure is never a dollar bill")
        self.assertGreater(est["api_equivalent_usd"], 0)
        self.assertIn("never a bill", est["label"])
        copilot = we.copilot_adapter()
        pricing = copilot["load_pricing"]()
        mid = copilot["resolve_model"](pricing, "mid")
        est = copilot["estimate"](mid, "M", pricing)
        self.assertEqual(est["basis"], "estimated")
        self.assertAlmostEqual(est["credits"], est["usd"] / pricing["billing_unit"]["usd_per_credit"])
        cursor = we.cursor_adapter()
        self.assertEqual(cursor["estimate"]("anything", "M", cursor["load_pricing"]())["basis"], "unpriced")
        self.assertEqual(we.stub_adapter()["estimate"]("m", "M", {})["basis"], "unpriced")

    def test_totals_keep_bases_apart_and_only_priced_bases_count_against_a_ceiling(self):
        totals = we.empty_totals()
        we.add_cost(totals, {"basis": "estimated", "usd": 0.5, "credits": 50.0})
        we.add_cost(totals, {"basis": "proxy", "usd": None, "api_equivalent_usd": 9.0})
        we.add_cost(totals, {"basis": "model-reported", "usd": 0.25})
        we.add_cost(totals, {"basis": "unpriced", "usd": None})
        self.assertEqual(totals["estimated"], {"n": 1, "usd": 0.5})
        self.assertEqual(totals["proxy"], {"n": 1, "api_equivalent_usd": 9.0})
        self.assertEqual(totals["model-reported"], {"n": 1, "usd": 0.25})
        self.assertEqual(totals["credits"], {"n": 1, "credits": 50.0})
        self.assertEqual(totals["unpriced"], {"n": 1})
        self.assertEqual(we.priced_usd({"basis": "proxy", "api_equivalent_usd": 9.0}), 0.0)
        self.assertEqual(we.priced_usd({"basis": "estimated", "usd": 0.5}), 0.5)
        self.assertIn("never summed", totals["note"])

    def test_stage_cost_prefers_reported_tokens_and_falls_back_to_the_estimate(self):
        adapter = claude_fixture_adapter()
        reported = we.stage_cost(adapter, "fake-haiku-1", "XS", FIXTURE_PRICING,
                                 {"input_tokens": 1000, "output_tokens": 200})
        self.assertEqual(reported["basis"], "model-reported")
        estimated = we.stage_cost(adapter, "fake-haiku-1", "XS", FIXTURE_PRICING, None)
        self.assertEqual(estimated["basis"], "estimated")
        unknown = we.stage_cost(adapter, "not-a-model", "XS", FIXTURE_PRICING, None)
        self.assertEqual(unknown["basis"], "unpriced")

    def test_the_module_names_no_model_id_and_carries_no_process_primitive(self):
        source = (BIN_DIR / "workflow_eval.py").read_text()
        ids = set()
        for filename in ("pricing.json", "pricing.codex.json", "pricing.copilot.json"):
            ids.update(json.loads((ROOT / "data" / filename).read_text()).get("models") or {})
        leaked = sorted(i for i in ids if i in source)
        self.assertEqual(leaked, [], f"model ids hardcoded: {leaked}")
        self.assertNotIn("import subprocess", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("Path.home()", source)

    def test_capability_states_come_from_the_registry(self):
        states = we.capability_states(we.claude_adapter())
        self.assertIn("dispatch", states)
        self.assertEqual(we.capability_states(we.stub_adapter()).get(we.REVIEW_CAPABILITY, "unknown"), "unknown")

    def test_the_registry_records_workflow_evaluation_per_harness(self):
        registry = json.loads((ROOT / "primitives" / "harness-capabilities.json").read_text())
        for key in we.REGISTRY_KEYS.values():
            with self.subTest(harness=key):
                row = registry["harnesses"][key]["capabilities"]["workflow_evaluation"]
                self.assertEqual(row["implemented"], "supported")
                self.assertEqual(row["verified"], "supported" if key == "stub" else "unknown")


# ---- the plan ---------------------------------------------------------------------------------------------

class PlanTests(_Case):
    def test_the_plan_mines_the_same_tasks_repo_bench_mines_and_dispatches_nothing(self):
        plan, tasks, _ = self.plan(models=("fixer", "idler"), workflows=("direct", "reviewed", "kit"))
        bench = rb.build_plan(self.repo, ["haiku"], mode="issue-replay", scratch_dir=self.root / "s2")
        self.assertEqual([t["task_id"] for t in plan["tasks"]], [t["task_id"] for t in bench["tasks"]])
        self.assertEqual(plan["base_commit"], bench["base_commit"])
        self.assertFalse(self.log.exists(), "planning dispatched the stub")
        self.assertEqual(len(plan["variants"]), 6)
        self.assertEqual(len(plan["trials"]), 6)
        self.assertEqual(plan["caps"]["max_dispatches"], 8, "direct 2 + reviewed 2x2 + kit 2")
        self.assertEqual(plan["caps"]["max_check_runs"], 2 + 6)
        self.assertIn("nothing above was dispatched", we.render_plan_markdown(plan))
        self.assertIn("hard caps", we.render_plan_markdown(plan))
        self.assertIn("not a provider-side guarantee", we.render_plan_markdown(plan))

    def test_the_kit_workflow_needs_a_test_command_and_pinned_needs_a_model(self):
        with self.assertRaises(we.EvalError):
            self.plan(workflows=("kit",), test_cmd=None)
        with self.assertRaises(we.EvalError):
            self.plan(models=())

    def test_repeats_are_counterbalanced(self):
        plan, _, _ = self.plan(models=("fixer", "idler"), repeats=2)
        first = [t["variant"] for t in plan["trials"] if t["repeat"] == 1]
        second = [t["variant"] for t in plan["trials"] if t["repeat"] == 2]
        self.assertEqual(first, ["stub/direct/pinned:fixer", "stub/direct/pinned:idler"])
        self.assertEqual(second, ["stub/direct/pinned:idler", "stub/direct/pinned:fixer"])

    def test_an_unsupported_review_capability_refuses_the_reviewed_variant_before_any_dispatch(self):
        with mock.patch.object(we, "capability_states", return_value={we.REVIEW_CAPABILITY: "unsupported"}):
            plan, _, _ = self.plan(workflows=("direct", "reviewed"))
        self.assertEqual([v["workflow"] for v in plan["variants"]], ["direct"])
        self.assertEqual(len(plan["refused_variants"]), 1)
        self.assertIn("unsupported", plan["refused_variants"][0]["reason"])

    def test_a_statement_with_a_credential_shape_is_labelled_and_never_quoted(self):
        repo = build_repo(self.root / "secret-target", secret=True)
        plan, tasks, _ = self.plan(repo=repo)
        self.assertEqual(plan["tasks"][0]["privacy_redactions"], {"aws-access-key-id": 1})
        text = we.render_plan_markdown(plan)
        self.assertIn("privacy", text)
        self.assertNotIn(FAKE_KEY, text)

    def test_instruction_files_become_an_instruction_version_axis(self):
        a, b = self.root / "a.txt", self.root / "b.txt"
        a.write_text("Fix it carefully.\n")
        b.write_text("Fix it quickly.\n")
        plan, _, _ = self.plan(instructions=[("a", a.read_text()), ("b", b.read_text())])
        versions = {v["instruction_version"] for v in plan["variants"]}
        self.assertEqual(len(versions), 2)
        self.assertEqual(sorted(v["instructions"] for v in plan["variants"]), ["a", "b"])

    def test_adaptive_policy_on_a_priced_catalog_routes_and_a_tierless_harness_is_refused(self):
        plan, _, _ = self.plan(models=(), policies=("adaptive",), adapter=claude_fixture_adapter())
        stage = plan["stages"][0]
        self.assertIn(stage["model"], FIXTURE_PRICING["models"])
        self.assertIsNone(stage["refusal"])
        self.assertEqual(plan["totals"]["estimated"]["n"], 1)
        plan, _, _ = self.plan(models=(), policies=("adaptive",))
        self.assertIsNotNone(plan["stages"][0]["refusal"])
        self.assertEqual(plan["caps"]["max_dispatches"], 0)


# ---- the run ----------------------------------------------------------------------------------------------

class DirectWorkflowTests(_Case):
    def test_solved_comes_from_the_oracle_and_every_dispatch_is_in_the_ledger(self):
        plan, tasks, adapter = self.plan(models=("fixer", "idler"))
        ev, env = self.evaluate(plan, tasks, adapter)
        by = {r["variant"]: r for r in env["trials"]}
        self.assertTrue(by["stub/direct/pinned:fixer"]["solved"])
        self.assertFalse(by["stub/direct/pinned:idler"]["solved"])
        self.assertIsNone(by["stub/direct/pinned:fixer"]["accepted"], "direct has no acceptance step")
        events = self.ledger(ev.run_dir).events()
        kinds = [e["kind"] for e in events]
        self.assertEqual(kinds.count("attempt.started"), 2)
        self.assertEqual(kinds.count("attempt.finished"), 2)
        started = [e for e in events if e["kind"] == "attempt.started"]
        self.assertEqual({e["role"] for e in started}, {"implementer"})
        self.assertEqual({e["actor"] for e in started}, {"stub"})
        self.assertEqual(kinds[0], "eval.started")
        self.assertEqual(kinds[-1], "eval.finished")
        self.assertEqual(env["spend"]["dispatched"], 2)
        self.assertTrue((ev.run_dir / "results.json").exists())
        self.assertTrue((ev.run_dir / "trials" / "t001.json").exists())
        self.assertFalse((ev.run_dir / "work").exists(), "the working area is swept")

    def test_the_prompt_is_leak_free_and_the_store_is_written_only_after_every_dispatch(self):
        plan, tasks, adapter = self.plan()
        seen = {}

        def runner(argv, cwd):
            seen["prompt"] = argv[-1]
            seen["tasks_dir"] = sorted(p.name for p in (ev.run_dir / "tasks").iterdir())
            seen["trials_dir"] = (ev.run_dir / "trials").exists()
            (Path(cwd) / "m.py").write_text("def f():\n    return 2\n")
            return 0, "{}"

        out = io.StringIO()
        ev = we.Evaluation(plan, tasks, adapter, store_dir=self.store, runner=runner, test_runner=test_runner,
                           binary="stub", max_usd=1.0, exec_mode="trusted-host", out=out, err=out)
        ev.run()
        self.assertEqual(seen["tasks_dir"], [], "task records (reference patch, test blobs) were on disk during a dispatch")
        self.assertFalse(seen["trials_dir"])
        self.assertNotIn("assert m.f() == 2", seen["prompt"], "the withheld test reached the prompt")
        self.assertNotIn("+    return 2", seen["prompt"], "the reference patch reached the prompt")
        self.assertIn("[kit=eval-", seen["prompt"])
        self.assertIn(rb.PROMPT_INSTRUCTIONS, seen["prompt"])

    def test_a_credential_in_the_statement_is_redacted_before_dispatch_and_counted_by_kind(self):
        repo = build_repo(self.root / "secret-target", secret=True)
        plan, tasks, adapter = self.plan(repo=repo, workflows=("reviewed",))
        ev, env = self.evaluate(plan, tasks, adapter)
        for path in self.prompts.iterdir():
            self.assertNotIn(FAKE_KEY, path.read_text(), f"the key reached {path.name}")
            self.assertIn("[redacted:aws-access-key-id]", path.read_text())
        trial = env["trials"][0]
        self.assertEqual(trial["privacy"]["redactions"], {"aws-access-key-id": 1})
        self.assertEqual(trial["robustness"]["privacy"], {"aws-access-key-id": 1})
        self.assertNotIn(FAKE_KEY, json.dumps(trial))

    def test_a_host_attesting_another_model_excludes_the_trial_as_a_policy_violation(self):
        plan, tasks, adapter = self.plan(models=("observed",))
        ev, env = self.evaluate(plan, tasks, adapter)
        trial = env["trials"][0]
        self.assertEqual(trial["excluded"], "policy-mismatch")
        self.assertIn("somebody-else", trial["robustness"]["policy_violation"])
        card = we.build_card(env)
        self.assertEqual(card["variants"][0]["n"], 0, "an excluded trial does not count for the dispatched model")
        self.assertEqual(card["variants"][0]["excluded"], {"policy-mismatch": 1})

    def test_touching_test_paths_is_recorded_as_tampering_and_never_buys_a_grade(self):
        plan, tasks, adapter = self.plan(models=("tamper",))
        ev, env = self.evaluate(plan, tasks, adapter)
        trial = env["trials"][0]
        self.assertEqual(trial["robustness"]["evidence_tampering"], ["tests/test_extra.py"])
        self.assertTrue(trial["solved"], "the substrate withholds and restores the test surface; the fix itself is real")
        self.assertEqual(we.build_card(env)["variants"][0]["robustness"]["evidence_tampering"], 1)

    def test_a_dispatch_failure_is_classified_and_not_graded_as_solved(self):
        plan, tasks, adapter = self.plan(models=("crasher",))
        ev, env = self.evaluate(plan, tasks, adapter)
        trial = env["trials"][0]
        self.assertEqual(trial["stages"][0]["rc"], 3)
        self.assertFalse(trial["solved"])
        finished = [e for e in self.ledger(ev.run_dir).events() if e["kind"] == "attempt.finished"]
        self.assertEqual(finished[0]["outcome"], "failed")


class ReviewedWorkflowTests(_Case):
    def test_the_review_is_recorded_read_only_outside_the_run_dir_and_never_changes_solved(self):
        plan, tasks, adapter = self.plan(models=("fixer", "idler"), workflows=("reviewed",))
        ev, env = self.evaluate(plan, tasks, adapter)
        by = {r["variant"]: r for r in env["trials"]}
        fixer, idler = by["stub/reviewed/pinned:fixer"], by["stub/reviewed/pinned:idler"]
        self.assertEqual(fixer["review"], {"verdict": "accept", "parsed": True})
        self.assertEqual(idler["review"], {"verdict": "reject", "parsed": True})
        self.assertTrue(fixer["accepted"])
        self.assertFalse(idler["accepted"])
        self.assertEqual(fixer["acceptance_by"], "review")
        self.assertTrue(fixer["solved"])
        self.assertFalse(idler["solved"])
        self.assertFalse(idler["incorrect_acceptance"])
        calls = self.calls()
        review_calls = [c for c in calls if c[2] == "ask"]
        self.assertEqual(len(review_calls), 2)
        for c in review_calls:
            self.assertFalse(c[3].startswith(str(self.store)), "the reviewer's cwd was under the run dir")
        started = [e for e in self.ledger(ev.run_dir).events() if e["kind"] == "attempt.started"]
        self.assertEqual([e["op"] for e in started], ["initial", "review", "initial", "review"])
        self.assertEqual([e["role"] for e in started], ["implementer", "reviewer", "implementer", "reviewer"])
        review_prompt = (self.prompts / "t002.ask.txt").read_text()
        self.assertIn("REVIEW VERDICT", review_prompt)
        self.assertNotIn("assert m.f() == 2", review_prompt, "the reviewer saw the withheld test")

    def test_a_reviewer_accepting_a_failing_patch_is_an_incorrect_acceptance_and_solved_stays_false(self):
        plan, tasks, adapter = self.plan(models=("idler",), workflows=("reviewed",), review_model="yes-reviewer")
        ev, env = self.evaluate(plan, tasks, adapter)
        trial = env["trials"][0]
        self.assertEqual(trial["review"]["verdict"], "accept")
        self.assertTrue(trial["accepted"])
        self.assertFalse(trial["solved"])
        self.assertTrue(trial["incorrect_acceptance"])
        card = we.build_card(env)
        self.assertEqual(card["variants"][0]["incorrect_acceptance"], 1)
        self.assertEqual(card["variants"][0]["escaped_defects"], 1)
        self.assertEqual(card["escaped_defects_total"], 1)

    def test_an_unparseable_review_is_recorded_as_no_verdict(self):
        plan, tasks, adapter = self.plan(models=("fixer",), workflows=("reviewed",))

        def runner(argv, cwd):
            if "ask" in argv:
                return 0, "I am not sure what to say"
            (Path(cwd) / "m.py").write_text("def f():\n    return 2\n")
            return 0, "{}"

        ev, env = self.evaluate(plan, tasks, adapter, runner=runner)
        trial = env["trials"][0]
        self.assertEqual(trial["review"], {"verdict": None, "parsed": False})
        self.assertIsNone(trial["accepted"])
        self.assertTrue(trial["solved"])
        self.assertEqual(we.build_card(env)["variants"][0]["coverage"]["review_parsed"], 0.0)


class KitWorkflowTests(_Case):
    def test_the_kit_workflow_runs_on_the_contract_and_its_own_check_can_accept_wrongly(self):
        plan, tasks, adapter = self.plan(models=("fixer", "idler"), workflows=("kit",))
        ev, env = self.evaluate(plan, tasks, adapter, keep_work=True)
        by = {r["variant"]: r for r in env["trials"]}
        fixer, idler = by["stub/kit/pinned:fixer"], by["stub/kit/pinned:idler"]
        self.assertEqual(fixer["kit"]["status"], "done")
        self.assertEqual(idler["kit"]["status"], "done", "the repository's own tests pass without the fix")
        self.assertTrue(fixer["solved"])
        self.assertFalse(idler["solved"])
        self.assertTrue(idler["incorrect_acceptance"])
        self.assertEqual(idler["acceptance_by"], "kit-check")
        kit_dir = Path(idler["kit"]["kit_dir"])
        tasks_md = (kit_dir / "TASKS.md").read_text()
        self.assertIn("- status: done", tasks_md)
        notes = (kit_dir / "NOTES.md").read_text()
        self.assertRegex(notes, r"- outcome: t00\d model=idler attempts=1 result=pass")
        self.assertIn("- harness: stub", notes)
        ledger = self.ledger(ev.run_dir, kit_dir.name)
        kinds = [e["kind"] for e in ledger.events()]
        for kind in ("run.started", "attempt.started", "attempt.finished", "verify.finished",
                     "task.projected", "run.finished"):
            self.assertIn(kind, kinds)
        self.assertEqual(fixer["stages"][0]["check"]["mode"], "trusted-host")
        self.assertEqual(len([c for c in self.calls() if c[1] == "fixer"]), 1)

    def test_a_dead_attempt_is_settled_without_replay_and_the_resume_is_recorded(self):
        repo = build_repo(self.root / "strict-target", strict=True)
        plan, tasks, adapter = self.plan(models=("fixer",), workflows=("kit",), repo=repo)
        run_id, run_dir = rb.new_run_dir(self.store)
        # A run that died after dispatching: an open attempt from a pid that is gone.
        dead = al.AttemptLedger(run_dir / "attempts", "t001-kit")
        dead.append("run.started", run="dead-run", task="t001", actor="stub", pid=2 ** 22 + 7)
        dead.record_started("dead-run", "t001", "initial", "fixer", prompt="p", verify_cmd="run", actor="stub")
        with mock.patch.object(we._SIBLINGS["repo_bench"], "new_run_dir", return_value=(run_id, run_dir)):
            ev, env = self.evaluate(plan, tasks, adapter, keep_work=True)
        trial = env["trials"][0]
        self.assertEqual(trial["resume"]["closed_unknown"], 1)
        self.assertTrue(trial["resume"]["redispatched"], "the check failed on the untouched tree, so one more attempt")
        self.assertEqual(trial["robustness"]["resume"]["closed_unknown"], 1)
        self.assertEqual(len([c for c in self.calls() if c[1] == "fixer"]), 1, "never replayed")
        prompt = (self.prompts / "t001.write.txt").read_text()
        self.assertIn("PRIOR ATTEMPTS", prompt)
        self.assertEqual(trial["kit"]["status"], "done")
        self.assertTrue(trial["solved"])
        self.assertEqual(we.build_card(env)["variants"][0]["interventions"], 1)

    def test_a_kit_whose_budget_is_spent_by_dead_attempts_refuses_and_records_the_budget_outcome(self):
        repo = build_repo(self.root / "strict-target", strict=True)
        plan, tasks, adapter = self.plan(models=("fixer",), workflows=("kit",), repo=repo)
        run_id, run_dir = rb.new_run_dir(self.store)
        dead = al.AttemptLedger(run_dir / "attempts", "t001-kit")
        dead.append("run.started", run="dead-run", task="t001", actor="stub", pid=2 ** 22 + 7)
        for _ in range(2):
            dead.record_started("dead-run", "t001", "initial", "fixer", prompt="p", verify_cmd="run", actor="stub")
        with mock.patch.object(we._SIBLINGS["repo_bench"], "new_run_dir", return_value=(run_id, run_dir)):
            ev, env = self.evaluate(plan, tasks, adapter)
        trial = env["trials"][0]
        self.assertEqual(self.calls(), [], "over budget: nothing dispatched")
        self.assertEqual(trial["stages"][0]["skipped"], "budget-stop")
        self.assertIn("kit refused", trial["robustness"]["budget_overshoot"])
        self.assertEqual(trial["kit"]["status"], "blocked")
        self.assertFalse(trial["solved"])
        self.assertEqual(we.build_card(env)["variants"][0]["robustness"]["budget_overshoot"], 1)

    def test_finished_work_left_by_a_dead_run_is_recognised_and_not_redispatched(self):
        plan, tasks, adapter = self.plan(models=("fixer",), workflows=("kit",))
        run_id, run_dir = rb.new_run_dir(self.store)
        dead = al.AttemptLedger(run_dir / "attempts", "t001-kit")
        dead.append("run.started", run="dead-run", task="t001", actor="stub", pid=2 ** 22 + 7)
        dead.record_started("dead-run", "t001", "initial", "fixer", prompt="p", verify_cmd="run", actor="stub")
        # The dead run's work IS on the tree the kit would check: in this fixture the base
        # already passes its own tests, so the check recognises it and dispatches nothing.
        with mock.patch.object(we._SIBLINGS["repo_bench"], "new_run_dir", return_value=(run_id, run_dir)):
            ev, env = self.evaluate(plan, tasks, adapter)
        trial = env["trials"][0]
        self.assertEqual(trial["resume"]["redispatched"], False)
        self.assertEqual(self.calls(), [], "recognised work is never re-dispatched")
        self.assertEqual(trial["kit"]["status"], "done")
        self.assertFalse(trial["solved"], "and the oracle still says the task is not solved")
        self.assertTrue(trial["incorrect_acceptance"])


class CeilingAndCapTests(_Case):
    def test_the_usd_ceiling_stops_the_next_priced_dispatch_and_labels_the_run(self):
        adapter = claude_fixture_adapter()
        plan, tasks, adapter = self.plan(models=("fake-haiku-1", "fake-opus-1"), adapter=adapter)
        est_first = plan["stages"][0]["cost"]["usd"]
        ev, env = self.evaluate(plan, tasks, adapter, runner=fixing_runner(), max_usd=est_first * 1.5)
        self.assertEqual(env["trials"][0]["skipped"], None)
        self.assertEqual(env["trials"][1]["skipped"], "cost-ceiling")
        self.assertIn("partial (cost-ceiling)", env["labels"])
        self.assertEqual(env["spend"]["dispatched"], 1)
        self.assertEqual(env["totals"]["estimated"]["n"], 1)

    def test_reported_tokens_are_priced_and_an_overshoot_is_labelled_not_prevented(self):
        adapter = claude_fixture_adapter()
        plan, tasks, adapter = self.plan(models=("fake-haiku-1",), adapter=adapter)
        est = plan["stages"][0]["cost"]["usd"]
        big = {"input_tokens": 10_000_000, "output_tokens": 1_000_000}
        ev, env = self.evaluate(plan, tasks, adapter, runner=fixing_runner(usage=big), max_usd=est * 2)
        self.assertEqual(env["totals"]["model-reported"]["n"], 1)
        self.assertTrue(env["spend"]["overspent"])
        self.assertTrue(any(l.startswith("overspend") for l in env["labels"]))

    def test_the_hard_dispatch_cap_bounds_an_unpriced_harness(self):
        plan, tasks, adapter = self.plan(models=("fixer", "idler"))
        ev, env = self.evaluate(plan, tasks, adapter, max_dispatches=1)
        self.assertEqual(env["trials"][1]["skipped"], "hard-cap")
        self.assertIn("partial (hard-cap)", env["labels"])
        self.assertEqual(len(self.calls()), 1)

    def test_a_subscription_proxy_never_counts_against_the_ceiling(self):
        adapter = we.codex_adapter()
        pricing = adapter["load_pricing"]()
        mid = adapter["resolve_model"](pricing, "mid")
        plan, tasks, adapter = self.plan(models=(mid,), adapter=adapter)
        self.assertEqual(plan["totals"]["proxy"]["n"], 1)
        self.assertEqual(plan["totals"]["estimated"]["usd"], 0.0)
        ev, env = self.evaluate(plan, tasks, adapter, runner=fixing_runner(), max_usd=0.000001)
        self.assertIsNone(env["trials"][0]["skipped"], "a proxy figure is not a dollar and cannot trip a dollar ceiling")
        self.assertEqual(env["spend"]["spent_usd"], 0.0)
        self.assertEqual(env["totals"]["proxy"]["n"], 1)
        finished = [e for e in self.ledger(ev.run_dir).events() if e["kind"] == "attempt.finished"]
        self.assertIsNone(finished[0]["cost_usd"], "billed_usd stays null for a subscription run")
        self.assertEqual(finished[0]["cost_source"], "proxy")


class RoutingTests(_Case):
    def test_the_adaptive_policy_records_its_decision_and_the_reserved_policy_too(self):
        plan, tasks, adapter = self.plan(models=(), policies=("adaptive", "reserved"), adapter=claude_fixture_adapter())
        ev, env = self.evaluate(plan, tasks, adapter, runner=fixing_runner())
        for trial in env["trials"]:
            self.assertIsNone(trial["skipped"])
            self.assertIn(trial["model_dispatched"], FIXTURE_PRICING["models"])
            self.assertIn("routing: policy=", trial["routing"]["implement"]["decision"])
        self.assertEqual({t["policy"] for t in env["trials"]}, {"adaptive", "reserved"})

    def test_a_tierless_harness_under_a_routing_policy_is_skipped_as_refused(self):
        plan, tasks, adapter = self.plan(models=(), policies=("adaptive",))
        ev, env = self.evaluate(plan, tasks, adapter)
        self.assertEqual(env["trials"][0]["skipped"], "routing-refused")
        self.assertEqual(self.calls(), [])


# ---- the card ----------------------------------------------------------------------------------------------

def synthetic_envelope(n_tasks=6, repeats=2, kit_rate=1.0, direct_rate=0.5, run_id="2026-09-13-abcd"):
    variants = [{"id": "stub/kit/pinned:m", "harness": "stub", "workflow": "kit", "policy": "pinned",
                 "model": "m", "instructions": "builtin", "instruction_version": "v1"},
                {"id": "stub/direct/pinned:m", "harness": "stub", "workflow": "direct", "policy": "pinned",
                 "model": "m", "instructions": "builtin", "instruction_version": "v1"}]
    trials, n = [], 0
    for r in range(repeats):
        for i in range(n_tasks):
            for v in variants:
                n += 1
                rate = kit_rate if v["workflow"] == "kit" else direct_rate
                solved = (i / n_tasks) < rate
                trials.append({"trial": f"t{n:03d}", "task_id": f"task-{i}", "variant": v["id"],
                               "harness": "stub", "workflow": v["workflow"], "policy": "pinned", "repeat": r + 1,
                               "order": n, "size_profile": "S", "task_class": "issue-replay",
                               "instruction_version": "v1", "stages": [{"stage": "implement",
                               "cost": {"basis": "unpriced", "usd": None}, "wall_seconds": 1.0}],
                               "solved": solved, "accepted": True if v["workflow"] == "kit" else None,
                               "acceptance_by": "kit-check" if v["workflow"] == "kit" else None,
                               "incorrect_acceptance": (v["workflow"] == "kit" and not solved),
                               "review": None, "resume": None, "excluded": None, "skipped": None,
                               "wall_seconds": 1.0, "robustness": {k: None for k in we.ROBUSTNESS},
                               "oracles": {"tests": {"available": True}}})
    return {"v": we.EVAL_VERSION, "run_id": run_id, "repo": "/r", "harness": "stub", "repeats": repeats,
            "variants": variants, "trials": trials, "labels": [], "notes": [], "adjudications": [],
            "evidence_floor": rb.MIN_EVIDENCE_TASKS, "holdout": {"tasks": [f"task-{i}" for i in range(n_tasks)]},
            "spend": {"ceiling_usd": None, "spent_usd": 0.0, "dispatched": len(trials), "max_dispatches": len(trials)},
            "totals": we.empty_totals(), "registry": {}, "pricing_date": None, "untested_claims": list(we.UNTESTED_CLAIMS)}


class CardTests(_Case):
    def test_below_floor_is_never_a_ranking(self):
        plan, tasks, adapter = self.plan(models=("fixer", "idler"))
        ev, env = self.evaluate(plan, tasks, adapter)
        card = we.build_card(env)
        self.assertIsNone(card["ranking"])
        self.assertIn(we.NOT_A_RANKING, card["labels"])
        self.assertTrue(all(s["below_floor"] for s in card["variants"]))
        text = we.render_card_markdown(card)
        self.assertIn("BELOW EVIDENCE FLOOR", text)
        self.assertIn("## untested claims", text)
        self.assertIn("never merged", text)

    def test_enough_repeated_evidence_yields_a_ranking_with_intervals_and_stability(self):
        card = we.build_card(synthetic_envelope())
        self.assertEqual(card["ranking"], ["stub/kit/pinned:m", "stub/direct/pinned:m"])
        kit = card["variants"][0]
        self.assertEqual(kit["n"], 12)
        self.assertEqual(kit["interval_95"][0] > 0.7, True)
        self.assertEqual(kit["stability"], 1.0)
        self.assertEqual(card["strata"]["workflow"]["kit"], {"n": 12, "solved": 12})
        self.assertEqual(card["sample"]["repeats"], 2)
        single = we.build_card(synthetic_envelope(repeats=1))
        self.assertIsNone(single["ranking"], "one pass over the tasks is not a ranking")

    def test_adjudication_is_an_intervention_that_never_changes_solved(self):
        plan, tasks, adapter = self.plan(models=("idler",))
        ev, env = self.evaluate(plan, tasks, adapter)
        entry = we.adjudicate(self.store, ev.run_id, "t001", "a person", "solved", note="looked fine to me " + FAKE_KEY)
        self.assertNotIn(FAKE_KEY, entry["note"])
        env2 = we.read_envelope(self.store, ev.run_id)
        card = we.build_card(env2)
        self.assertEqual(card["adjudications"], 1)
        self.assertEqual(card["variants"][0]["interventions"], 1)
        self.assertEqual(card["variants"][0]["solved"], 0, "a person's verdict is recorded beside the oracle, not over it")
        with self.assertRaises(we.EvalError):
            we.adjudicate(self.store, ev.run_id, "t999", "a person", "solved")
        with self.assertRaises(we.EvalError):
            we.adjudicate(self.store, ev.run_id, "t001", "", "solved")

    def test_the_history_joins_every_namespace_through_attempt_history_with_registry_tiers(self):
        plan, tasks, adapter = self.plan(models=("fixer",), workflows=("direct", "reviewed", "kit"))
        ev, env = self.evaluate(plan, tasks, adapter)
        records, summary = we.history_records(self.store, ev.run_id)
        self.assertEqual(len(records), 4, "implement, implement+review, kit implement")
        self.assertEqual(set(summary["by_harness"]), {"stub"})
        self.assertEqual({r["role"] for r in records}, {"implementer", "reviewer"})
        self.assertEqual(summary["unknown"]["cost"], 4, "the stub is unpriced and says so")
        plan, tasks, adapter = self.plan(models=("fake-haiku-1",), adapter=claude_fixture_adapter())
        ev, env = self.evaluate(plan, tasks, adapter, runner=fixing_runner())
        records, summary = we.history_records(self.store, ev.run_id)
        self.assertEqual(records[0]["harness"], "claude")
        self.assertEqual(records[0]["cost"]["basis"], "estimated")

    def test_list_is_tolerant_of_an_absent_store_and_rogue_entries(self):
        rows, notes = we.list_runs(self.store)
        self.assertEqual(rows, [])
        self.assertEqual(len(notes), 1)
        self.store.mkdir()
        (self.store / "rogue").mkdir()
        (self.store / "junk.txt").write_text("x")
        plan, tasks, adapter = self.plan()
        ev, env = self.evaluate(plan, tasks, adapter)
        rows, notes = we.list_runs(self.store)
        self.assertEqual([r["run_id"] for r in rows], [ev.run_id])
        self.assertEqual(len(notes), 2)


# ---- policy: propose / review / apply / rollback -------------------------------------------------------------

class PolicyProcessTests(_Case):
    def _run_envelope(self, **kw):
        env = synthetic_envelope(**kw)
        run_dir = self.store / env["run_id"]
        run_dir.mkdir(parents=True)
        (run_dir / "results.json").write_text(json.dumps(env) + "\n")
        return env

    def test_propose_refuses_sparse_single_repeat_and_unmeasured_evidence(self):
        env = self._run_envelope(n_tasks=2)
        with self.assertRaises(we.EvalError) as cm:
            we.build_proposal(env, {"workflow": "kit"}, "me", self.prefs)
        self.assertIn("below the evidence floor", str(cm.exception))
        env = self._run_envelope(repeats=1, run_id="2026-09-13-0001")
        with self.assertRaises(we.EvalError) as cm:
            we.build_proposal(env, {"workflow": "kit"}, "me", self.prefs)
        self.assertIn("single repeat", str(cm.exception))
        env = self._run_envelope(run_id="2026-09-13-0002")
        with self.assertRaises(we.EvalError):
            we.build_proposal(env, {"workflow": "reviewed"}, "me", self.prefs)
        with self.assertRaises(we.EvalError):
            we.build_proposal(env, {"workflow": "kit"}, "", self.prefs)
        with self.assertRaises(we.EvalError):
            we.build_proposal(env, {"model": "x"}, "me", self.prefs)

    def test_apply_needs_an_accepting_review_and_a_current_base_then_versions_and_rolls_back(self):
        env = self._run_envelope()
        proposal = we.build_proposal(env, {"workflow": "kit"}, "proposer", self.prefs)
        we.write_proposal(self.prefs, proposal)
        pid = proposal["id"]
        with self.assertRaises(we.EvalError) as cm:
            we.apply_proposal(self.prefs, pid)
        self.assertIn("no accepting review", str(cm.exception))
        we.review_proposal(self.prefs, pid, "reviewer", "reject", note="not yet")
        with self.assertRaises(we.EvalError):
            we.apply_proposal(self.prefs, pid)
        we.review_proposal(self.prefs, pid, "reviewer", "accept", note="evidence read")
        new, old = we.apply_proposal(self.prefs, pid)
        self.assertIsNone(old)
        self.assertEqual(new["version"], 1)
        self.assertEqual(new["defaults"], {"workflow": "kit"})
        self.assertEqual(new["evidence_tasks"], sorted(env["holdout"]["tasks"]))
        self.assertIn("pull-only", new["consumption"])
        with self.assertRaises(we.EvalError):
            we.apply_proposal(self.prefs, pid)  # already applied
        with self.assertRaises(we.EvalError):
            we.rollback_policy(self.prefs)  # nothing earlier
        # A second run on FRESH tasks proposes v2; the first version is kept and restorable.
        env2 = self._run_envelope(run_id="2026-09-13-bbbb")
        for t in env2["trials"]:
            t["task_id"] = t["task_id"].replace("task-", "other-")
        env2["holdout"]["tasks"] = [f"other-{i}" for i in range(6)]
        proposal2 = we.build_proposal(env2, {"workflow": "direct"}, "proposer", self.prefs)
        we.write_proposal(self.prefs, proposal2)
        # The base changes underneath a proposal -> stale, refused.
        we.review_proposal(self.prefs, proposal2["id"], "reviewer", "accept")
        policy_path = self.prefs / we.POLICY_FILE
        original = policy_path.read_text()
        policy_path.write_text(original.replace("\"version\": 1", "\"version\": 1 "))
        with self.assertRaises(we.EvalError) as cm:
            we.apply_proposal(self.prefs, proposal2["id"])
        self.assertIn("different policy version", str(cm.exception))
        policy_path.write_text(original)
        new2, old2 = we.apply_proposal(self.prefs, proposal2["id"])
        self.assertEqual(new2["version"], 2)
        self.assertEqual(new2["defaults"], {"workflow": "direct"})
        self.assertEqual((self.prefs / we.POLICY_HISTORY / "v1.json").read_text(), original)
        restored, previous = we.rollback_policy(self.prefs)
        self.assertEqual(restored["version"], 1)
        self.assertEqual(policy_path.read_text(), original, "rollback restores the earlier bytes")
        self.assertTrue((self.prefs / we.POLICY_HISTORY / "v2.json").exists(), "the version rolled back from is kept")
        journal = [json.loads(l) for l in (self.prefs / we.POLICY_JOURNAL).read_text().splitlines()]
        self.assertEqual([j["kind"] for j in journal],
                         ["policy.proposed", "policy.reviewed", "policy.reviewed", "policy.applied",
                          "policy.proposed", "policy.reviewed", "policy.applied", "policy.rolled-back"])
        report = we.policy_report(self.prefs)
        self.assertEqual(report["history_versions"], [1, 2])
        self.assertEqual(report["policy"]["version"], 1)

    def test_evaluation_tasks_that_backed_the_applied_policy_are_reserved(self):
        env = self._run_envelope()
        proposal = we.build_proposal(env, {"workflow": "kit"}, "p", self.prefs)
        we.write_proposal(self.prefs, proposal)
        we.review_proposal(self.prefs, proposal["id"], "r", "accept")
        we.apply_proposal(self.prefs, proposal["id"])
        again = self._run_envelope(run_id="2026-09-13-cccc")
        with self.assertRaises(we.EvalError) as cm:
            we.build_proposal(again, {"workflow": "direct"}, "p", self.prefs)
        self.assertIn("reserved", str(cm.exception))

    def test_a_task_class_scope_lands_under_by_task_class(self):
        env = self._run_envelope()
        proposal = we.build_proposal(env, {"workflow": "kit"}, "p", self.prefs, task_class="S")
        we.write_proposal(self.prefs, proposal)
        we.review_proposal(self.prefs, proposal["id"], "r", "accept")
        new, _ = we.apply_proposal(self.prefs, proposal["id"])
        self.assertEqual(new["by_task_class"], {"S": {"workflow": "kit"}})
        self.assertEqual(new["defaults"], {})

    def test_nothing_in_the_repository_reads_the_policy_file_automatically(self):
        readers = []
        for path in sorted(BIN_DIR.glob("*.py")):
            if path.name == "workflow_eval.py":
                continue
            if we.POLICY_FILE in path.read_text():
                readers.append(path.name)
        self.assertEqual(readers, [], "a driver started reading the applied policy without being wired on purpose")


# ---- CLI --------------------------------------------------------------------------------------------------

def _run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = we.main(argv)
    return code, out.getvalue(), err.getvalue()


class CliTests(_Case):
    def _argv(self, *extra):
        return ["run", "--repo", str(self.repo), "--harness", "stub", "--models", "fixer",
                "--test-cmd", f"{sys.executable} run_tests.py", "--mode", "issue-replay",
                "--store-dir", str(self.store), "--bin", str(self.stub), "--exec-mode", "trusted-host", *extra]

    def test_run_refuses_without_both_live_and_ceiling_and_leaves_no_run_dir(self):
        code, out, err = _run_cli(self._argv())
        self.assertEqual(code, 2)
        self.assertIn("requires --live AND --max-usd", err)
        self.assertIn("workflow-eval plan", out)
        code, _, err = _run_cli(self._argv("--live"))
        self.assertEqual(code, 2)
        code, _, err = _run_cli(self._argv("--live", "--max-usd", "nan"))
        self.assertEqual(code, 2)
        self.assertIn("refusing", err)
        self.assertFalse(self.store.exists() and any(self.store.iterdir()))
        self.assertFalse(self.log.exists())

    def test_run_with_the_gate_open_dispatches_the_stub_and_renders_the_card(self):
        code, out, err = _run_cli(self._argv("--live", "--max-usd", "1", "--workflows", "direct,kit"))
        self.assertEqual(code, 0, err)
        self.assertIn("workflow-eval card", out)
        self.assertIn("results.json:", out)
        self.assertEqual(len(self.calls()), 2)
        run_id = [p.name for p in self.store.iterdir()][0]
        code, out, _ = _run_cli(["card", "--run", run_id, "--store-dir", str(self.store), "--history"])
        self.assertEqual(code, 0)
        self.assertIn("attempt history (2 record(s)", out)
        code, out, _ = _run_cli(["list", "--store-dir", str(self.store)])
        self.assertEqual(code, 0)
        self.assertIn(run_id, out)
        code, out, _ = _run_cli(["adjudicate", "--run", run_id, "--trial", "t001", "--by", "me",
                                 "--verdict", "unsure", "--store-dir", str(self.store)])
        self.assertEqual(code, 0)
        self.assertIn("solved is unchanged", out)

    def test_plan_prints_and_dispatches_nothing(self):
        code, out, err = _run_cli(["plan", "--repo", str(self.repo), "--harness", "stub", "--models", "fixer",
                                   "--mode", "issue-replay", "--workflows", "direct,reviewed", "--json"])
        self.assertEqual(code, 0, err)
        card = json.loads(out)
        self.assertEqual(card["caps"]["max_dispatches"], 3)
        self.assertFalse(self.log.exists())

    def test_the_policy_cli_walks_propose_review_apply_rollback(self):
        env = synthetic_envelope()
        run_dir = self.store / env["run_id"]
        run_dir.mkdir(parents=True)
        (run_dir / "results.json").write_text(json.dumps(env) + "\n")
        code, out, _ = _run_cli(["propose", "--run", env["run_id"], "--set", "workflow=kit", "--by", "me",
                                 "--store-dir", str(self.store), "--prefs-dir", str(self.prefs)])
        self.assertEqual(code, 0)
        pid = re.search(r"proposal (prop-\S+) written", out).group(1)
        code, _, err = _run_cli(["apply", "--proposal", pid, "--prefs-dir", str(self.prefs)])
        self.assertEqual(code, 2)
        self.assertIn("no accepting review", err)
        code, _, _ = _run_cli(["review", "--proposal", pid, "--by", "them", "--decision", "accept",
                               "--prefs-dir", str(self.prefs)])
        self.assertEqual(code, 0)
        code, out, _ = _run_cli(["apply", "--proposal", pid, "--prefs-dir", str(self.prefs)])
        self.assertEqual(code, 0)
        self.assertIn("routing policy v1", out)
        code, out, _ = _run_cli(["policy", "--prefs-dir", str(self.prefs)])
        self.assertEqual(code, 0)
        self.assertIn("v1", out)
        code, _, err = _run_cli(["rollback", "--prefs-dir", str(self.prefs)])
        self.assertEqual(code, 2)
        self.assertIn("nothing to roll back", err)

    def test_demo_runs_offline_and_spends_nothing(self):
        out = io.StringIO()
        with mock.patch.object(we, "default_runner", side_effect=AssertionError("a real dispatch path was reached")):
            code = we._demo(out=out)
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("incorrect acceptance 2/2", text)
        self.assertIn("propose refused", text)
        self.assertIn("nothing dispatched a model", text)


if __name__ == "__main__":
    unittest.main()
