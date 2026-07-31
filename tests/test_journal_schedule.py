"""Stdlib unittest regression suite for bin/journal_schedule.py (PLAN.md D12 launchd scheduler).

SAFETY CONTRACT (binds every test in this file): no test here ever touches the real macOS
Launch Agents directory or any other real home-relative path -- every install/status/uninstall
call in this file passes an explicit ``--launch-agents-dir`` pointed at a fresh
``tempfile.TemporaryDirectory()`` fixture (a subdirectory literally named ``launch_agents``,
never the real system directory name). No test here resolves the caller's real home directory
via the stdlib home-directory helper -- that helper is used exactly once inside
journal_schedule.py itself, purely as a runtime default that every call in this file overrides
with an explicit temp path. ``launchctl`` is never executed anywhere in this file -- this suite
proves that as a real test (not just a comment) by asserting the loaded module's own source
contains no subprocess import at all: the module only ever WRITES a plist and PRINTS the
``launchctl bootstrap``/``launchctl bootout`` commands as instructions for the user to run by
hand, later, outside this kit. ``cmd_run`` -- the in-process collector+summarizer dispatcher --
is exercised ONLY with injected fake ``collect_main``/``summarize_main`` callables built in this
file; the real ``journal_collect``/``journal_summarize`` modules (and therefore their own real
home-directory defaults) are never loaded or called from this file.

bin/ is not a package; journal_schedule.py is loaded via importlib by absolute path computed
from this file's own location (BIN_DIR), mirroring tests/test_journal_collect.py and
tests/test_journal_summarize.py.
"""

import contextlib
import importlib.util
import io
import plistlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


js = _load("journal_schedule")

PINNED_PLIST_KEYS = frozenset({
    "Label", "ProgramArguments", "StartCalendarInterval", "WorkingDirectory",
    "StandardOutPath", "StandardErrorPath", "RunAtLoad",
})

# Built by concatenation on purpose: the two halves are never adjacent in this file's own
# source text, so this file stays clean under the kit's own "no literal home-directory call"
# safety grep while still letting ModuleSafetyTests search bin/journal_schedule.py's source
# for exactly one real occurrence of that call.
_HOME_LOOKUP_NEEDLE = "Path" + ".home()"


def _run_cli(argv):
    """Run js.main(argv) in-process with stdout captured -> (rc, stdout_text)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = js.main(argv)
    return rc, buf.getvalue()


def _fake_main(rc, record=None):
    """Build a fake main(argv) that records the argv it was called with and returns rc."""
    def _main(argv):
        if record is not None:
            record.append(list(argv))
        return rc
    return _main


def _bomb_main(argv):
    """A fake main that fails the test if it is ever invoked at all."""
    raise AssertionError("this main must not be invoked in this scenario")


# ---- render_plist validation + pinned key set --------------------------------------------

class RenderPlistTests(unittest.TestCase):
    def _kwargs(self, tmp):
        return dict(
            python_bin="/fake/bin/python3",
            script_path=Path(tmp) / "journal_schedule.py",
            journal_dir=Path(tmp) / "journal",
            plugin_root=Path(tmp) / "plugin",
        )

    def test_hour_24_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw = self._kwargs(tmp)
            with self.assertRaises(ValueError):
                js.render_plist(kw["python_bin"], kw["script_path"], 24, 0,
                                 kw["journal_dir"], kw["plugin_root"])

    def test_minute_60_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw = self._kwargs(tmp)
            with self.assertRaises(ValueError):
                js.render_plist(kw["python_bin"], kw["script_path"], 10, 60,
                                 kw["journal_dir"], kw["plugin_root"])

    def test_negative_hour_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw = self._kwargs(tmp)
            with self.assertRaises(ValueError):
                js.render_plist(kw["python_bin"], kw["script_path"], -1, 0,
                                 kw["journal_dir"], kw["plugin_root"])

    def test_negative_minute_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw = self._kwargs(tmp)
            with self.assertRaises(ValueError):
                js.render_plist(kw["python_bin"], kw["script_path"], 0, -1,
                                 kw["journal_dir"], kw["plugin_root"])

    def test_pinned_key_set_and_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            kw = self._kwargs(tmp)
            data = js.render_plist(kw["python_bin"], kw["script_path"], 10, 15,
                                    kw["journal_dir"], kw["plugin_root"])
            parsed = plistlib.loads(data)
            self.assertEqual(set(parsed.keys()), PINNED_PLIST_KEYS)
            self.assertEqual(parsed["Label"], js.LABEL)
            self.assertEqual(
                parsed["ProgramArguments"],
                [kw["python_bin"], str(kw["script_path"]), "run"],
            )
            self.assertEqual(parsed["StartCalendarInterval"], {"Hour": 10, "Minute": 15})
            self.assertEqual(parsed["WorkingDirectory"], str(kw["plugin_root"]))
            self.assertEqual(
                parsed["StandardOutPath"],
                str(kw["journal_dir"] / "logs" / "launchd.out.log"),
            )
            self.assertEqual(
                parsed["StandardErrorPath"],
                str(kw["journal_dir"] / "logs" / "launchd.err.log"),
            )
            self.assertIs(parsed["RunAtLoad"], False)


# ---- install -> status -> uninstall lifecycle ----------------------------------------------

class LifecycleTests(unittest.TestCase):
    def test_install_writes_valid_plist(self):
        with tempfile.TemporaryDirectory() as tmp:
            launch_dir = str(Path(tmp) / "launch_agents")
            journal_dir = str(Path(tmp) / "journal")
            rc, out = _run_cli([
                "install", "--launch-agents-dir", launch_dir,
                "--hour", "21", "--minute", "30", "--journal-dir", journal_dir,
            ])
            self.assertEqual(rc, 0)

            path = js.plist_path(launch_dir)
            self.assertTrue(path.is_file())
            with open(path, "rb") as f:
                data = plistlib.load(f)
            self.assertEqual(set(data.keys()), PINNED_PLIST_KEYS)
            self.assertEqual(data["Label"], js.LABEL)
            self.assertEqual(data["StartCalendarInterval"], {"Hour": 21, "Minute": 30})
            self.assertEqual(data["ProgramArguments"][-1], "run")
            self.assertTrue(data["ProgramArguments"][-2].endswith("journal_schedule.py"))
            self.assertTrue(
                data["StandardOutPath"].endswith(str(Path("logs") / "launchd.out.log"))
            )
            self.assertTrue(
                data["StandardErrorPath"].endswith(str(Path("logs") / "launchd.err.log"))
            )
            self.assertIs(data["RunAtLoad"], False)

    def test_install_stdout_has_bootstrap_and_bootout_instructions(self):
        with tempfile.TemporaryDirectory() as tmp:
            launch_dir = str(Path(tmp) / "launch_agents")
            journal_dir = str(Path(tmp) / "journal")
            rc, out = _run_cli([
                "install", "--launch-agents-dir", launch_dir,
                "--hour", "8", "--minute", "0", "--journal-dir", journal_dir,
            ])
            self.assertEqual(rc, 0)
            self.assertIn("launchctl bootstrap", out)
            self.assertIn("launchctl bootout", out)

    def test_status_zero_pads_single_digit_hour_and_minute(self):
        with tempfile.TemporaryDirectory() as tmp:
            launch_dir = str(Path(tmp) / "launch_agents")
            journal_dir = str(Path(tmp) / "journal")
            _run_cli([
                "install", "--launch-agents-dir", launch_dir,
                "--hour", "9", "--minute", "5", "--journal-dir", journal_dir,
            ])
            rc, out = _run_cli(["status", "--launch-agents-dir", launch_dir])
            self.assertEqual(rc, 0)
            self.assertIn("09:05", out)

    def test_status_not_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            launch_dir = str(Path(tmp) / "launch_agents")
            rc, out = _run_cli(["status", "--launch-agents-dir", launch_dir])
            self.assertEqual(rc, 0)
            self.assertIn("not installed", out)

    def test_uninstall_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            launch_dir = str(Path(tmp) / "launch_agents")
            journal_dir = str(Path(tmp) / "journal")
            _run_cli([
                "install", "--launch-agents-dir", launch_dir,
                "--hour", "22", "--minute", "0", "--journal-dir", journal_dir,
            ])
            path = js.plist_path(launch_dir)
            self.assertTrue(path.is_file())

            rc1, out1 = _run_cli(["uninstall", "--launch-agents-dir", launch_dir])
            self.assertEqual(rc1, 0)
            self.assertFalse(path.is_file())
            self.assertIn("removed", out1)

            # Second call against the same (now-empty) directory: still exits 0.
            rc2, out2 = _run_cli(["uninstall", "--launch-agents-dir", launch_dir])
            self.assertEqual(rc2, 0)
            self.assertIn("nothing installed", out2)

    def test_install_invalid_hour_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            launch_dir = str(Path(tmp) / "launch_agents")
            journal_dir = str(Path(tmp) / "journal")
            buf_out, buf_err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                with self.assertRaises(SystemExit) as cm:
                    js.main([
                        "install", "--launch-agents-dir", launch_dir,
                        "--hour", "24", "--minute", "0", "--journal-dir", journal_dir,
                    ])
            self.assertEqual(cm.exception.code, 2)


# ---- cmd_run passthrough matrix (injected fake mains only) ---------------------------------

class CmdRunTests(unittest.TestCase):
    def _args(self, **overrides):
        base = dict(date=None, utc=False, journal_dir=None, collect_only=False, dry_run=False)
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_collect_only_skips_summarizer(self):
        collect_record = []
        args = self._args(
            date="2026-06-30", utc=True, journal_dir="FAKE-JOURNAL-DIR", collect_only=True,
        )
        rc = js.cmd_run(
            args,
            collect_main=_fake_main(0, collect_record),
            summarize_main=_bomb_main,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(
            collect_record,
            [["--date", "2026-06-30", "--utc", "--journal-dir", "FAKE-JOURNAL-DIR"]],
        )

    def test_collector_failure_short_circuits(self):
        args = self._args()
        rc = js.cmd_run(
            args,
            collect_main=_fake_main(5),
            summarize_main=_bomb_main,
        )
        self.assertEqual(rc, 5)

    def test_summarizer_exit_3_propagates(self):
        args = self._args()
        rc = js.cmd_run(
            args,
            collect_main=_fake_main(0),
            summarize_main=_fake_main(3),
        )
        self.assertEqual(rc, 3)

    def test_dry_run_forwarded_to_summarizer_only(self):
        collect_record = []
        summarize_record = []
        args = self._args(dry_run=True)
        rc = js.cmd_run(
            args,
            collect_main=_fake_main(0, collect_record),
            summarize_main=_fake_main(0, summarize_record),
        )
        self.assertEqual(rc, 0)
        self.assertNotIn("--dry-run", collect_record[0])
        self.assertIn("--dry-run", summarize_record[0])

    def test_full_passthrough_reaches_both_mains(self):
        collect_record = []
        summarize_record = []
        args = self._args(
            date="2026-07-01", utc=True, journal_dir="FAKE-JOURNAL-DIR", dry_run=True,
        )
        rc = js.cmd_run(
            args,
            collect_main=_fake_main(0, collect_record),
            summarize_main=_fake_main(0, summarize_record),
        )
        self.assertEqual(rc, 0)
        expected_passthrough = ["--date", "2026-07-01", "--utc", "--journal-dir",
                                 "FAKE-JOURNAL-DIR"]
        self.assertEqual(collect_record, [expected_passthrough])
        self.assertEqual(summarize_record, [expected_passthrough + ["--dry-run"]])


# ---- module-level safety greps, run as real tests -------------------------------------------

class ModuleSafetyTests(unittest.TestCase):
    def test_module_has_no_subprocess(self):
        text = (BIN_DIR / "journal_schedule.py").read_text()
        self.assertNotIn("subprocess", text)

    def test_module_has_exactly_one_home_lookup(self):
        text = (BIN_DIR / "journal_schedule.py").read_text()
        self.assertEqual(text.count(_HOME_LOOKUP_NEEDLE), 1)


if __name__ == "__main__":
    unittest.main()
