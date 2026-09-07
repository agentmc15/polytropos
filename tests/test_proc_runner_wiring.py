"""Every process this repo starts goes through the one runner (step 12).

`tests/test_proc_runner.py` proves the runner behaves. This file proves it is actually USED --
that the dispatch, verify, benchmark, and summary paths named in the roadmap route through it,
and that a bare `subprocess.run` cannot quietly come back to any of them.

Nothing here invokes a real harness CLI. Where a test needs a process, it builds a local stub
script in a temp directory and passes its ABSOLUTE path, so no name is ever resolved off PATH.
"""

import ast
import importlib.util
import inspect
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_wiring", ROOT / "bin" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pr = _load("proc_runner")

#: The modules whose dispatch/verify/benchmark/summary subprocesses step 12 bound.
WIRED = ("claude_execute", "copilot_execute", "codex_execute", "copilot_ralph",
         "journal_summarize", "repo_bench", "exec_policy", "kit_contract")

#: Spawn sites that deliberately do NOT go through the runner, each with the reason it is
#: exempt. A new entry here is a decision, not an oversight -- which is the point of pinning
#: the set rather than the count.
EXEMPT_SPAWNS = {
    # Fire-and-forget desktop notification. Nothing waits on it, it has no pipes to hold, and
    # its output goes to DEVNULL -- there is no lifetime to bound.
    ("agent_tracker.py", "log_fable"),
    # Already bounded, and returns the caught exception object itself so its callers can react
    # per error kind. That contract, not the spawn, is what its callers are written against.
    ("journal_sources.py", "_git"),
}


def _spawn_sites():
    """(file, enclosing function) for every `subprocess.run/Popen/call/check_output` in bin/."""
    found = set()
    for path in sorted((ROOT / "bin").glob("*.py")):
        if path.name == "proc_runner.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr in ("run", "Popen", "call", "check_output")
                        and isinstance(sub.func.value, ast.Name)
                        and sub.func.value.id == "subprocess"):
                    found.add((path.name, node.name))
    return found


class OneRunnerTests(unittest.TestCase):
    def test_no_module_spawns_a_process_outside_the_runner_without_saying_why(self):
        self.assertEqual(
            _spawn_sites(),
            EXEMPT_SPAWNS,
            "a subprocess spawn appeared outside bin/proc_runner.py; route it through the "
            "runner, or add it to EXEMPT_SPAWNS with the reason it cannot be",
        )

    def test_every_wired_module_reaches_the_runner(self):
        # Directly, or through `bin/kit_contract.py`, which is where step 15 moved the three
        # drivers' identical loader. What matters is that the module cannot start a process
        # except through the runner -- which `test_no_module_spawns_a_process_outside_the_runner`
        # above is the actual guarantee for. This one checks the wiring is present at all.
        contract = (ROOT / "bin" / "kit_contract.py").read_text(encoding="utf-8")
        self.assertIn("proc_runner.py", contract)
        for name in WIRED:
            with self.subTest(module=name):
                source = (ROOT / "bin" / f"{name}.py").read_text(encoding="utf-8")
                self.assertTrue(
                    "proc_runner.py" in source or "kit_contract.py" in source,
                    f"{name} reaches the process runner neither directly nor through the "
                    f"shared kit contract",
                )


class DriverDispatchTests(unittest.TestCase):
    """The three kit drivers' real-dispatch seams, exercised with local stubs only."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def stub(self, body="echo stub-output\n"):
        path = self.dir / "stub.sh"
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
        return str(path)

    def drivers(self):
        for name in ("claude_execute", "copilot_execute", "codex_execute"):
            yield name, _load(name).default_runner

    def test_a_missing_binary_comes_back_as_a_result_not_an_exception(self):
        # The reported evidence for this step: a runner exception left a task stranded
        # in-progress because the driver never got a result to record.
        missing = str(self.dir / "not-installed")
        for name, runner in self.drivers():
            with self.subTest(driver=name):
                rc, output = runner([missing], cwd=self.dir)[:2]
                self.assertEqual(rc, pr.INFRASTRUCTURE_RC)
                self.assertIn("not found", str(output))

    def test_a_stalled_dispatch_is_bounded_rather_than_waited_on(self):
        stub = self.stub("sleep 30\n")
        for name, runner in self.drivers():
            with self.subTest(driver=name):
                rc, output = runner([stub], cwd=self.dir, timeout=1)[:2]
                self.assertEqual(rc, pr.INFRASTRUCTURE_RC)
                self.assertIn("wall-clock", str(output))

    def test_a_dispatch_does_not_carry_the_machines_unrelated_credentials(self):
        stub = self.stub('echo "${AWS_SECRET_ACCESS_KEY:-absent}"\n')
        os.environ["AWS_SECRET_ACCESS_KEY"] = "must-not-leak"
        self.addCleanup(os.environ.pop, "AWS_SECRET_ACCESS_KEY", None)
        for name, runner in self.drivers():
            with self.subTest(driver=name):
                _rc, output = runner([stub], cwd=self.dir)[:2]
                self.assertIn("absent", str(output))
                self.assertNotIn("must-not-leak", str(output))

    def test_a_normal_dispatch_still_returns_its_output(self):
        stub = self.stub("echo hello; exit 0\n")
        for name, runner in self.drivers():
            with self.subTest(driver=name):
                result = runner([stub], cwd=self.dir)
                self.assertEqual(result[0], 0)
                self.assertIn("hello", str(result[1]))

    def test_the_codex_runner_still_returns_its_third_telemetry_element(self):
        stub = self.stub("echo '{}'\n")
        result = _load("codex_execute").default_runner([stub], cwd=self.dir)
        self.assertEqual(len(result), 3)
        self.assertIsInstance(result[2], dict)


class RalphVerifyTests(unittest.TestCase):
    def test_ralphs_verify_line_no_longer_runs_in_the_parent_shell(self):
        # Step 05 moved every kit driver's verify command inside the OS boundary and left this
        # one behind: it was still `subprocess.run(cmd, shell=True)` with the loop's own
        # privileges, running code a model had just written.
        path = ROOT / "bin" / "copilot_ralph.py"
        source = path.read_text(encoding="utf-8")
        # Asserted over parsed CALL nodes, not raw text: `_build_tick_argv`'s docstring
        # legitimately says "an argv LIST, never `shell=True`", and describing the thing is
        # not doing it.
        shell_calls = [
            node for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and any(kw.arg == "shell" for kw in node.keywords)
        ]
        self.assertEqual(shell_calls, [])
        self.assertIn("verify_runner", source)
        self.assertIn("--exec-mode", source)


class ConfinedRunTests(unittest.TestCase):
    def test_the_boundary_reports_the_runners_outcome_vocabulary(self):
        ep = _load("exec_policy")
        with tempfile.TemporaryDirectory() as workspace:
            policy = ep.ExecPolicy(workspace, name="verify")
            result = ep.run_confined(["/bin/sh", "-c", "exit 3"], policy, mode="trusted-host")
            self.assertEqual(result["outcome"], pr.OUTCOME_FAILED)
            self.assertTrue(result["terminal"])
            self.assertEqual(result["rc"], 3)
            # Confinement reporting is unchanged: the two concerns stay separate.
            self.assertEqual(result["confinement"], "trusted-host")

    def test_a_verify_command_may_not_run_outside_its_workspace(self):
        ep = _load("exec_policy")
        with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as other:
            policy = ep.ExecPolicy(workspace, name="verify")
            result = ep.run_confined(["/bin/pwd"], policy, cwd=other, mode="trusted-host")
            self.assertEqual(result["outcome"], pr.OUTCOME_BAD_WORKDIR)


if __name__ == "__main__":
    unittest.main()
