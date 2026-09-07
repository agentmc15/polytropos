"""Bounding a subprocess's lifetime, output, environment, and working directory (step 12).

Every test here starts a real process, because the defects this module exists for are all in
what the operating system does rather than in what the code says. They are bounded to a second
or two each and use only temp directories and local stub scripts -- no network, no harness CLI,
no real home.

THE DEFECT THAT MOTIVATED IT, stated as the test that proves it: a command that succeeds in
under a second while leaving one background process behind is reported by
`subprocess.run(capture_output=True, timeout=T)` as a TIMEOUT after the full T, its output
discarded, and the background process left running. At this repo's 1800-second default that is
a half-hour stall ending in a false verdict on a command that passed. See
`CommandExitEndsTheRunTests`.
"""

import importlib.util
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("proc_runner_under_test", ROOT / "bin" / "proc_runner.py")
pr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pr)

#: Short everywhere: these assert on behaviour at a boundary, not on patience.
FAST = {"timeout": 2, "grace": 0.4}


class _Scripts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def script(self, body, name="s.sh"):
        path = self.dir / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
        return str(path)

    def alive(self, marker):
        pid = int(Path(marker).read_text().strip())
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


class NormalCompletionTests(_Scripts):
    def test_a_clean_exit_is_ok_and_keeps_its_output(self):
        result = pr.run([self.script("echo out; echo err >&2\n")], cwd=self.dir, **FAST)
        self.assertEqual(result["outcome"], pr.OUTCOME_OK)
        self.assertEqual(result["rc"], 0)
        self.assertTrue(result["terminal"])
        self.assertEqual(result["stdout"].strip(), "out")
        self.assertEqual(result["stderr"].strip(), "err")

    def test_stdout_and_stderr_are_not_merged_into_each_other(self):
        # A caller parsing structured events on stdout must not be handed diagnostics
        # interleaved into them. `output` stays available for callers that want one stream.
        result = pr.run([self.script('echo \'{"event":1}\'; echo warning >&2\n')],
                        cwd=self.dir, **FAST)
        self.assertNotIn("warning", result["stdout"])
        self.assertNotIn("event", result["stderr"])
        self.assertIn("warning", result["output"])
        self.assertIn("event", result["output"])

    def test_a_nonzero_exit_is_failed_and_the_code_survives(self):
        result = pr.run([self.script("exit 7\n")], cwd=self.dir, **FAST)
        self.assertEqual(result["outcome"], pr.OUTCOME_FAILED)
        self.assertEqual(result["rc"], 7)
        self.assertTrue(result["terminal"])

    def test_stdin_is_delivered(self):
        result = pr.run(["/bin/cat"], cwd=self.dir, input_text="fed in", **FAST)
        self.assertEqual(result["stdout"], "fed in")
        self.assertEqual(result["outcome"], pr.OUTCOME_OK)


class InfrastructureFailureTests(_Scripts):
    """Each way a run can fail to happen gets its own name, and none of them raise."""

    def test_a_missing_executable_is_an_outcome_not_an_exception(self):
        # The reported evidence for this step: a runner exception left a task stranded
        # in-progress, because the driver never got a result to record.
        result = pr.run([str(self.dir / "nope")], cwd=self.dir, **FAST)
        self.assertEqual(result["outcome"], pr.OUTCOME_MISSING_EXECUTABLE)
        self.assertFalse(result["terminal"])
        self.assertIn("not found", result["detail"])

    def test_a_non_executable_file_is_reported_as_not_permitted(self):
        path = self.dir / "plain.sh"
        path.write_text("#!/bin/sh\necho hi\n")
        path.chmod(0o644)
        result = pr.run([str(path)], cwd=self.dir, **FAST)
        self.assertEqual(result["outcome"], pr.OUTCOME_NOT_PERMITTED)
        self.assertFalse(result["terminal"])

    def test_an_infrastructure_outcome_is_never_read_as_a_verdict(self):
        # 124 is a real exit code a command may choose. Callers must branch on `outcome`.
        for result in (
            pr.run([str(self.dir / "nope")], cwd=self.dir, **FAST),
            pr.run(["/bin/echo"], cwd=self.dir / "nowhere", **FAST),
        ):
            self.assertEqual(result["rc"], pr.INFRASTRUCTURE_RC)
            self.assertNotIn(result["outcome"], pr.TERMINAL_OUTCOMES)


class WorkdirTests(_Scripts):
    def test_a_process_may_not_inherit_the_launch_directory(self):
        with self.assertRaises(pr.WorkdirError):
            pr.validate_workdir(None)
        result = pr.run(["/bin/echo", "x"], cwd=None, **FAST)
        self.assertEqual(result["outcome"], pr.OUTCOME_BAD_WORKDIR)

    def test_a_missing_or_non_directory_workdir_is_refused_before_anything_starts(self):
        missing = self.dir / "gone"
        self.assertEqual(pr.run(["/bin/echo"], cwd=missing, **FAST)["outcome"],
                         pr.OUTCOME_BAD_WORKDIR)
        file_path = self.dir / "afile"
        file_path.write_text("x")
        self.assertEqual(pr.run(["/bin/echo"], cwd=file_path, **FAST)["outcome"],
                         pr.OUTCOME_BAD_WORKDIR)

    def test_a_workdir_outside_the_bound_root_is_refused(self):
        inside = self.dir / "workspace"
        inside.mkdir()
        with tempfile.TemporaryDirectory() as elsewhere:
            with self.assertRaises(pr.WorkdirError):
                pr.validate_workdir(elsewhere, within=inside)
            result = pr.run(["/bin/echo"], cwd=elsewhere, within=inside, **FAST)
            self.assertEqual(result["outcome"], pr.OUTCOME_BAD_WORKDIR)

    def test_a_link_that_leaves_the_bound_root_is_refused(self):
        inside = self.dir / "workspace"
        inside.mkdir()
        with tempfile.TemporaryDirectory() as elsewhere:
            link = inside / "escape"
            link.symlink_to(elsewhere, target_is_directory=True)
            with self.assertRaises(pr.WorkdirError):
                pr.validate_workdir(link, within=inside)

    def test_the_process_actually_runs_in_the_given_directory(self):
        inside = self.dir / "workspace"
        inside.mkdir()
        result = pr.run(["/bin/pwd"], cwd=inside, **FAST)
        self.assertEqual(result["stdout"].strip(), os.path.realpath(str(inside)))


class TimeoutAndTreeCleanupTests(_Scripts):
    def test_a_stalled_command_is_terminated_at_its_limit(self):
        started = time.monotonic()
        result = pr.run([self.script("sleep 30\n")], cwd=self.dir, timeout=1, grace=0.4)
        elapsed = time.monotonic() - started
        self.assertEqual(result["outcome"], pr.OUTCOME_TIMEOUT)
        self.assertEqual(result["rc"], pr.INFRASTRUCTURE_RC)
        self.assertFalse(result["terminal"])
        self.assertLess(elapsed, 10, "the wall-clock limit did not bound the wait")

    def test_a_command_that_ignores_sigterm_is_still_stopped(self):
        result = pr.run([self.script('trap "" TERM\nsleep 30\n')], cwd=self.dir,
                        timeout=1, grace=0.4)
        self.assertEqual(result["outcome"], pr.OUTCOME_TIMEOUT)
        self.assertIn("process-group", result["tree_cleanup"])

    def test_a_timed_out_commands_grandchildren_do_not_survive_it(self):
        marker = self.dir / "grandchild.pid"
        script = self.script(f'(sleep 30 & echo $! > {marker})\nsleep 30\n')
        result = pr.run([script], cwd=self.dir, timeout=1, grace=0.4)
        self.assertEqual(result["outcome"], pr.OUTCOME_TIMEOUT)
        time.sleep(0.4)
        self.assertFalse(self.alive(marker), "a grandchild outlived the terminated task")


class CommandExitEndsTheRunTests(_Scripts):
    """The run is over when the COMMAND ends, not when its pipes close."""

    def test_a_finished_command_that_left_a_daemon_is_not_reported_as_a_timeout(self):
        marker = self.dir / "daemon.pid"
        script = self.script(f'(sleep 30 & echo $! > {marker})\necho finished\nexit 0\n')

        started = time.monotonic()
        result = pr.run([script], cwd=self.dir, timeout=20, grace=0.4)
        elapsed = time.monotonic() - started

        # The command's own verdict, not the leftover's.
        self.assertEqual(result["outcome"], pr.OUTCOME_OK)
        self.assertEqual(result["rc"], 0)
        self.assertIn("finished", result["stdout"])
        # And it did not wait out the limit to say so.
        self.assertLess(elapsed, 15, "waited on the leftover instead of the command")
        self.assertTrue(result["leftovers"])
        self.assertIn("left processes holding its output", result["detail"])

    def test_the_leftover_itself_is_not_allowed_to_outlive_the_run(self):
        marker = self.dir / "daemon.pid"
        script = self.script(f'(sleep 30 & echo $! > {marker})\necho finished\n')
        pr.run([script], cwd=self.dir, timeout=20, grace=0.4)
        time.sleep(0.4)
        self.assertFalse(self.alive(marker), "a leftover process outlived the run")

    def test_output_written_just_before_exit_still_arrives(self):
        # The drain window exists so that ending on the command's exit does not cost output
        # the command actually produced.
        result = pr.run([self.script("echo first; echo last; exit 3\n")], cwd=self.dir, **FAST)
        self.assertEqual(result["rc"], 3)
        self.assertIn("first", result["stdout"])
        self.assertIn("last", result["stdout"])


class OutputBoundTests(_Scripts):
    def test_output_past_the_limit_is_truncated_but_the_end_is_kept(self):
        script = self.script(
            "echo THE_BEGINNING\n"
            "i=0; while [ $i -lt 3000 ]; do echo AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA; i=$((i+1)); done\n"
            "echo THE_END\n"
        )
        result = pr.run([script], cwd=self.dir, output_limit=4000, timeout=20, grace=0.4)
        self.assertEqual(result["outcome"], pr.OUTCOME_OK)
        self.assertTrue(result["truncated"])
        self.assertIn("THE_BEGINNING", result["stdout"])
        self.assertIn("THE_END", result["stdout"], "the tail is where a failure usually says why")
        self.assertLess(len(result["stdout"]), 4000 + 200)

    def test_a_process_that_overruns_the_limit_still_exits(self):
        # The deadlock this guards: stop reading a full pipe and the writer blocks in `write`
        # forever, so the noisy process the bound exists for is exactly the one that hangs.
        script = self.script(
            "i=0; while [ $i -lt 20000 ]; do echo XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX; i=$((i+1)); done\n"
        )
        result = pr.run([script], cwd=self.dir, output_limit=1024, timeout=25, grace=0.4)
        self.assertEqual(result["outcome"], pr.OUTCOME_OK, "draining stopped and the writer blocked")
        self.assertTrue(result["truncated"])

    def test_output_under_the_limit_is_untouched(self):
        result = pr.run([self.script("echo small\n")], cwd=self.dir, output_limit=4096, **FAST)
        self.assertFalse(result["truncated"])
        self.assertEqual(result["stdout"], "small\n")


class BoundedCaptureTests(unittest.TestCase):
    def test_it_keeps_a_head_and_a_tail_and_says_how_much_it_dropped(self):
        capture = pr._BoundedCapture(100)
        capture.feed(b"H" * 200)
        capture.feed(b"T" * 200)
        text = capture.text()
        self.assertTrue(capture.truncated)
        self.assertTrue(text.startswith("H" * 75))
        self.assertTrue(text.endswith("T" * 25))
        self.assertIn("bytes dropped", text)
        self.assertEqual(capture.total, 400)

    def test_it_is_a_passthrough_below_the_limit(self):
        capture = pr._BoundedCapture(100)
        capture.feed(b"exactly this")
        self.assertFalse(capture.truncated)
        self.assertEqual(capture.text(), "exactly this")


class DispatchEnvironmentTests(_Scripts):
    BASE = {"PATH": "/usr/bin:/bin", "HOME": "/home/x", "LANG": "C"}

    def test_a_provider_gets_its_own_credentials_and_the_base_set(self):
        env = pr.dispatch_env("claude", base={**self.BASE, "ANTHROPIC_API_KEY": "k",
                                              "CLAUDE_CODE_FOO": "1"})
        self.assertEqual(env["ANTHROPIC_API_KEY"], "k")
        self.assertEqual(env["CLAUDE_CODE_FOO"], "1")
        self.assertEqual(env["PATH"], "/usr/bin:/bin")
        self.assertEqual(env["HOME"], "/home/x")

    def test_one_providers_credentials_do_not_reach_another_providers_cli(self):
        source = {**self.BASE, "ANTHROPIC_API_KEY": "anthropic", "OPENAI_API_KEY": "openai"}
        self.assertNotIn("ANTHROPIC_API_KEY", pr.dispatch_env("codex", base=source))
        self.assertIn("OPENAI_API_KEY", pr.dispatch_env("codex", base=source))
        self.assertNotIn("OPENAI_API_KEY", pr.dispatch_env("claude", base=source))

    def test_unrelated_machine_credentials_are_not_forwarded_at_all(self):
        source = {**self.BASE, "AWS_SECRET_ACCESS_KEY": "s", "SLACK_TOKEN": "s",
                  "NPM_TOKEN": "s", "KUBECONFIG": "/k"}
        for provider in ("claude", "copilot", "codex"):
            env = pr.dispatch_env(provider, base=source)
            for leaked in ("AWS_SECRET_ACCESS_KEY", "SLACK_TOKEN", "NPM_TOKEN", "KUBECONFIG"):
                self.assertNotIn(leaked, env, f"{leaked} reached the {provider} dispatch")

    def test_an_unknown_provider_gets_the_base_set_only(self):
        env = pr.dispatch_env("cursor", base={**self.BASE, "ANTHROPIC_API_KEY": "k"})
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertIn("PATH", env)

    def test_a_host_can_widen_the_list_it_cannot_otherwise_recover_from(self):
        source = {**self.BASE, "WEIRD_CORP_VAR": "v", pr.EXTRA_ENV_VAR: "WEIRD_CORP_VAR"}
        self.assertEqual(pr.dispatch_env("claude", base=source)["WEIRD_CORP_VAR"], "v")

    def test_the_reduced_environment_is_what_the_process_actually_sees(self):
        script = self.script("echo \"${SECRET_TOKEN:-absent}\"\n")
        result = pr.run([script], cwd=self.dir,
                        env=pr.dispatch_env("claude", base={**self.BASE, "SECRET_TOKEN": "leak"}),
                        **FAST)
        self.assertEqual(result["stdout"].strip(), "absent")


if __name__ == "__main__":
    unittest.main()
