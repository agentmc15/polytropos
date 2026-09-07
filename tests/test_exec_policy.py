"""Execution-boundary tests (step 05).

The point of this module is that it does NOT stop at argv assertions. A wrapped command line
that looks right proves nothing about what the kernel then refuses, so the enforcement tests
below run real commands under the real backend and check what actually happened on disk and on
the network. The argv-level tests are here too, for the parts that must hold on every host.
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
SPEC = importlib.util.spec_from_file_location("exec_policy_tests", BIN_DIR / "exec_policy.py")
ep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ep)


def sandbox_usable():
    """True when this host can actually apply a profile right now.

    Not the same question as `detect_backend()`: Seatbelt refuses to nest, so a test run that
    is ITSELF already sandboxed (a kit verify command under `--exec-mode enforced`) has the
    binary but cannot use it. Skipping on that is honest; asserting enforcement we cannot
    exercise would be a test that passes for the wrong reason.
    """
    if ep.detect_backend() != "sandbox-exec":
        return False
    try:
        proc = subprocess.run(
            ["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)", "/bin/echo", "ok"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


ENFORCEABLE = sandbox_usable()
requires_sandbox = unittest.skipUnless(
    ENFORCEABLE, "no usable OS confinement backend here (absent, or already sandboxed)"
)


class BackendDetectionTests(unittest.TestCase):
    def test_only_implemented_platforms_report_a_backend(self):
        self.assertIsNone(ep.detect_backend(platform="linux"))
        self.assertIsNone(ep.detect_backend(platform="win32"))
        self.assertIsNone(ep.detect_backend(platform="freebsd14"))

    @unittest.skipUnless(sys.platform == "darwin", "darwin-only")
    def test_darwin_reports_sandbox_exec(self):
        self.assertEqual(ep.detect_backend(), "sandbox-exec")


class FailClosedTests(unittest.TestCase):
    def test_enforced_without_a_backend_refuses_rather_than_running(self):
        with tempfile.TemporaryDirectory() as td:
            policy = ep.ExecPolicy(td, name="verify")
            with self.assertRaises(ep.SandboxUnavailable) as caught:
                ep.run_confined(["/bin/echo", "hi"], policy, mode="enforced", backend=None)
            message = str(caught.exception)
            self.assertIn("refusing to execute unconfined", message)
            # The refusal names the opt-out and states what it costs.
            self.assertIn("trusted-host", message)
            self.assertIn("NO", message)

    def test_trusted_host_is_reported_as_itself_not_as_enforcement(self):
        with tempfile.TemporaryDirectory() as td:
            policy = ep.ExecPolicy(td, name="verify")
            result = ep.run_confined(["/bin/echo", "hi"], policy, mode="trusted-host")
            self.assertEqual(result["rc"], 0)
            self.assertEqual(result["confinement"], "trusted-host")
            self.assertNotEqual(result["confinement"], ep.detect_backend())

    def test_an_unknown_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                ep.run_confined(["/bin/echo"], ep.ExecPolicy(td), mode="sandboxed-ish")


class PolicyComparisonTests(unittest.TestCase):
    """`is_at_most` is the step-05 rule as a predicate: verification must not gain broader
    write, network, or credential access than the worker whose files it executes."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.ws = Path(self.td) / "ws"
        self.ws.mkdir()
        self.worker = ep.ExecPolicy(self.ws, name="worker")

    def test_an_equal_policy_is_at_most(self):
        self.assertTrue(ep.ExecPolicy(self.ws, name="verify").is_at_most(self.worker))

    def test_network_is_a_widening(self):
        wider = ep.ExecPolicy(self.ws, allow_network=True, name="verify")
        self.assertFalse(wider.is_at_most(self.worker))

    def test_a_wider_workspace_is_a_widening(self):
        wider = ep.ExecPolicy(self.td, name="verify")
        self.assertFalse(wider.is_at_most(self.worker))

    def test_an_extra_credential_is_a_widening(self):
        wider = ep.ExecPolicy(
            self.ws, env={"ANTHROPIC_API_KEY": "x"}, name="verify"
        )
        self.assertFalse(wider.is_at_most(self.worker))

    def test_read_only_reference_inputs_are_not_a_widening(self):
        """Verification MAY hold read-only inputs the worker cannot see -- withheld tests,
        reference answers -- and that is not extra privilege."""
        narrower = ep.ExecPolicy(
            self.ws, read_only=[self.td], deny_read=[self.td], name="verify"
        )
        self.assertTrue(narrower.is_at_most(self.worker))


@requires_sandbox
class EnforcementTests(unittest.TestCase):
    """What the kernel actually refuses. Every assertion here is about an observed effect on
    disk or on the network, never about the shape of an argv."""

    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.ws = self.td / "workspace"
        self.ws.mkdir()
        self.outside = self.td / "outside"
        self.outside.mkdir()
        (self.outside / "answers.txt").write_text("REFERENCE ANSWER\n")
        self.scratch = self.td / "scratch"
        self.scratch.mkdir()
        self.policy = ep.ExecPolicy(
            self.ws, scratch=self.scratch, deny_read=[self.outside], name="verify"
        )

    def verify(self, cmd):
        return ep.run_verify(cmd, self.policy, timeout=90)

    def test_the_workspace_is_writable(self):
        result = self.verify("echo written > inside.txt")
        self.assertEqual(result["rc"], 0, result["output"])
        self.assertEqual((self.ws / "inside.txt").read_text().strip(), "written")

    def test_writes_outside_the_workspace_are_refused(self):
        result = self.verify(f"echo pwned > {self.outside}/escaped.txt")
        self.assertNotEqual(result["rc"], 0)
        self.assertFalse((self.outside / "escaped.txt").exists())

    def test_the_home_directory_is_not_writable(self):
        marker = Path.home() / "polytropos-exec-policy-should-not-exist.txt"
        self.assertFalse(marker.exists(), "stale marker from an earlier failing run")
        result = self.verify(f"echo pwned > {marker}")
        self.assertNotEqual(result["rc"], 0)
        self.assertFalse(marker.exists())

    def test_declared_confidential_paths_are_unreadable(self):
        result = self.verify(f"cat {self.outside}/answers.txt")
        self.assertNotEqual(result["rc"], 0)
        self.assertNotIn("REFERENCE ANSWER", result["output"])

    def test_the_network_is_denied(self):
        result = self.verify(
            "python3 -c \"import socket; socket.create_connection(('1.1.1.1', 80), timeout=5)\""
        )
        self.assertNotEqual(result["rc"], 0)

    def test_a_declared_network_allowance_is_honoured_in_the_profile(self):
        allowed = ep.ExecPolicy(self.ws, allow_network=True, name="verify")
        self.assertIn("(allow network*)", allowed.sbpl())
        self.assertNotIn("(deny network*)", allowed.sbpl())
        self.assertIn("(deny network*)", self.policy.sbpl())

    def test_temporary_files_still_work_through_the_run_scoped_scratch(self):
        result = self.verify(
            "python3 -c \"import tempfile, os, pathlib; "
            "d = tempfile.mkdtemp(); "
            "pathlib.Path(d, 'f').write_text('x'); "
            "print(d)\""
        )
        self.assertEqual(result["rc"], 0, result["output"])
        self.assertTrue(
            result["output"].strip().startswith(os.path.realpath(self.scratch)),
            f"temp files landed outside the run-scoped scratch: {result['output']!r}",
        )

    def test_credentials_are_not_inherited(self):
        os.environ["POLYTROPOS_FAKE_SECRET"] = "super-secret-value"
        try:
            result = self.verify("env")
            self.assertEqual(result["rc"], 0, result["output"])
            self.assertNotIn("super-secret-value", result["output"])
            self.assertNotIn("POLYTROPOS_FAKE_SECRET", result["output"])
        finally:
            del os.environ["POLYTROPOS_FAKE_SECRET"]

    def test_worker_modified_imported_code_cannot_reach_excluded_paths(self):
        """THE step-05 defect, end to end.

        The fixed, approved verify command is unchanged. What changed is the code it imports --
        exactly what a worker gets to do between the precheck and the verification. Before the
        boundary, that import ran with the parent's privileges and wrote a marker outside its
        workspace."""
        marker = self.outside / "verifier-escaped.txt"
        (self.ws / "helper.py").write_text(
            "import pathlib\n"
            f"pathlib.Path({str(marker)!r}).write_text('the verifier wrote this')\n"
        )
        (self.ws / "test_suite.py").write_text("import helper\n")

        result = self.verify("python3 -c 'import test_suite'")

        self.assertNotEqual(result["rc"], 0, "the escaping import should have failed")
        self.assertFalse(marker.exists(), "worker-modified verifier code escaped its workspace")

    def test_a_verify_command_that_legitimately_builds_still_succeeds(self):
        """The boundary must not break ordinary work: writing build output inside the
        workspace, reading the interpreter's own installation, and using temp files."""
        (self.ws / "src.py").write_text("VALUE = 41\n")
        result = self.verify(
            "python3 -c \"import src, pathlib, json, tempfile; "
            "pathlib.Path('built.json').write_text(json.dumps({'v': src.VALUE + 1}))\""
        )
        self.assertEqual(result["rc"], 0, result["output"])
        self.assertIn('"v": 42', (self.ws / "built.json").read_text())

    def test_the_shell_contract_is_preserved_inside_the_boundary(self):
        """Verify lines are repo-authored shell, pipes and all. That contract is intact; only
        the process interpreting them changed."""
        result = self.verify("printf 'b\\na\\n' | sort | tr -d '\\n'")
        self.assertEqual(result["rc"], 0, result["output"])
        self.assertIn("ab", result["output"])

    def test_the_result_reports_the_backend_that_enforced_it(self):
        result = self.verify("true")
        self.assertEqual(result["confinement"], "sandbox-exec")
        self.assertEqual(result["policy"]["network"], "denied")
        self.assertEqual(result["policy"]["workspace"], os.path.realpath(self.ws))


@requires_sandbox
class VerifyRunnerTests(unittest.TestCase):
    """The runner shape the drivers actually inject."""

    def test_the_injected_runner_confines_and_returns_the_driver_tuple(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "ws"
            ws.mkdir()
            outside = Path(td) / "outside"
            outside.mkdir()
            runner = ep.verify_runner(ws, deny_read=[])

            rc, output = runner("echo ok > inside.txt")
            self.assertEqual(rc, 0, output)
            self.assertTrue((ws / "inside.txt").exists())

            rc, _output = runner(f"echo pwned > {outside}/escaped.txt")
            self.assertNotEqual(rc, 0)
            self.assertFalse((outside / "escaped.txt").exists())

    def test_each_call_gets_a_fresh_scratch_that_does_not_survive(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / "ws"
            ws.mkdir()
            runner = ep.verify_runner(ws, deny_read=[])
            rc, output = runner("python3 -c \"import tempfile; print(tempfile.gettempdir())\"")
            self.assertEqual(rc, 0, output)
            self.assertFalse(Path(output.strip()).exists(), "scratch outlived the call")


class TimeoutAndOutputTests(unittest.TestCase):
    def test_a_hanging_command_is_bounded_and_reported(self):
        with tempfile.TemporaryDirectory() as td:
            policy = ep.ExecPolicy(td, name="verify")
            result = ep.run_confined(
                ["/bin/sh", "-c", "sleep 30"], policy, mode="trusted-host", timeout=2
            )
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["rc"], 124)
            # Assert the structured verdict, not the sentence: since step 12 the wall-clock
            # bound is `bin/proc_runner.py`'s and it words the report its own way.
            self.assertEqual(result["outcome"], "timeout")
            self.assertFalse(result["terminal"])
            self.assertIn("wall-clock limit", result["output"])

    def test_output_is_truncated_rather_than_unbounded(self):
        with tempfile.TemporaryDirectory() as td:
            policy = ep.ExecPolicy(td, name="verify")
            result = ep.run_confined(
                ["/bin/sh", "-c", "printf 'x%.0s' $(seq 1 5000)"], policy,
                mode="trusted-host", output_limit=500,
            )
            self.assertLessEqual(len(result["output"]), 600)
            self.assertTrue(result["truncated"])
            self.assertIn("bytes dropped", result["output"])


class ProfileRenderingTests(unittest.TestCase):
    def test_denies_follow_allows_so_the_last_matching_rule_wins(self):
        with tempfile.TemporaryDirectory() as td:
            secret = Path(td) / "secret"
            secret.mkdir()
            profile = ep.ExecPolicy(td, deny_read=[secret]).sbpl()
            self.assertLess(profile.index("(allow file-read*)"), profile.index("(deny file-read*"))

    def test_paths_with_quotes_are_escaped_into_the_profile(self):
        with tempfile.TemporaryDirectory() as td:
            odd = Path(td) / 'we"ird'
            odd.mkdir()
            profile = ep.ExecPolicy(odd).sbpl()
            self.assertIn('we\\"ird', profile)

    def test_the_environment_is_an_allowlist_not_a_filter(self):
        os.environ["POLYTROPOS_UNDECLARED"] = "leaked"
        try:
            with tempfile.TemporaryDirectory() as td:
                env = ep.ExecPolicy(td, env={"DECLARED": "yes"}).environment()
                self.assertNotIn("POLYTROPOS_UNDECLARED", env)
                self.assertEqual(env.get("DECLARED"), "yes")
        finally:
            del os.environ["POLYTROPOS_UNDECLARED"]

    def test_scratch_becomes_tmpdir_for_the_confined_stage(self):
        with tempfile.TemporaryDirectory() as td:
            scratch = Path(td) / "scratch"
            scratch.mkdir()
            env = ep.ExecPolicy(td, scratch=scratch).environment()
            self.assertEqual(env["TMPDIR"], os.path.realpath(scratch))


if __name__ == "__main__":
    unittest.main()
