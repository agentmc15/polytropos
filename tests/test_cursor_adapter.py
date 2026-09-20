"""bin/cursor_adapter.py (step 23): identity before trust, the argv, the output, the install.

SAFETY CONTRACT. No test here runs Cursor's `agent`, `cursor`, or any binary named like them.
The identity probe is exercised through the adapter's injected `runner` seam or through a
throwaway shell script written to a temp dir; `--cursor-bin` always names that script. The
install tests write only into temp project roots. Nothing reads or writes a home directory.
"""

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_cursor_adapter_test",
                                                  BIN_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ca = _load("cursor_adapter")
ha = ca._ha()  # the adapter's own copy, so exception classes compare equal
hs = _load("harness_select")

CURSOR_VERSION_LINE = "cursor-agent 2026.09.01-stub"
OTHER_VERSION_LINE = "acme-agent 3.1"

STUB_TEMPLATE = """#!/bin/sh
if [ "$1" = "--version" ]; then printf '%s\\n' "%VERSION%"; exit 0; fi
if [ "$1" = "about" ]; then printf '%s\\n' '%ABOUT%'; exit 0; fi
if [ "$1" = "models" ]; then printf 'stub-model-a\\nstub-model-b\\n'; exit 0; fi
printf '===CALL===\\n' >> "%LOG%"
for a in "$@"; do printf '%s\\n' "$a" >> "%LOG%"; done
printf '%s\\n' '{"model": "stub-model", "result": "done"}'
exit 0
"""


def write_stub(tmp, name="stub-agent", version=CURSOR_VERSION_LINE, about="{}", log=None):
    path = Path(tmp) / name
    path.write_text(STUB_TEMPLATE.replace("%VERSION%", version).replace("%ABOUT%", about)
                    .replace("%LOG%", str(log or (Path(tmp) / "stub.log"))))
    path.chmod(0o755)
    return path


def _runner(version="", about=None, rc=0):
    """An injected probe runner answering `--version` and `about --format json`."""
    def run(argv):
        if argv[-1] == "--version":
            return {"rc": rc, "stdout": version, "stderr": "", "outcome": "ok"}
        if argv[1:2] == ["about"]:
            return {"rc": 0, "stdout": json.dumps(about) if about is not None else "",
                    "stderr": "", "outcome": "ok"}
        return {"rc": 0, "stdout": "stub-model-a\nstub-model-b\n", "stderr": "",
                "outcome": "ok"}
    return run


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.bin = str(write_stub(self.tmp))

    def tearDown(self):
        self._tmp.cleanup()

    def test_version_naming_cursor_is_accepted(self):
        report = ca.identify(self.bin, runner=_runner(version="Cursor Agent 1.2.3\n"))
        self.assertEqual(report["identity"], "cursor")
        self.assertEqual(report["version"], "Cursor Agent 1.2.3")
        self.assertIs(ca.require_cursor(report), report)

    def test_about_json_naming_cursor_is_accepted_when_version_does_not(self):
        report = ca.identify(self.bin, runner=_runner(
            version="agent 0.1\n", about={"product": "Cursor CLI", "version": "0.1.9",
                                          "email": "someone@example.com"}))
        self.assertEqual(report["identity"], "cursor")
        self.assertEqual(report["version"], "0.1.9")
        self.assertNotIn("someone@example.com", json.dumps(report),
                         "only the version is kept from the about payload")

    def test_the_real_about_schema_is_accepted_though_no_value_names_cursor(self):
        """2026-09-16: the first real install. `--version` prints a bare version and `about`
        names Cursor nowhere; the `cliVersion` schema is the identity. Account fields are read
        for nothing and never kept."""
        real_shape = {"cliVersion": "2026.09.10-fd3934a", "latestStatus": "up_to_date",
                      "latestVersion": "2026.09.10-fd3934a", "model": "Auto",
                      "subscriptionTier": None, "osPlatform": "darwin", "osArch": "arm64",
                      "userEmail": "someone@example.com", "terminalProgram": "apple-terminal",
                      "shell": "zsh", "lastRequestId": None}
        report = ca.identify(self.bin, runner=_runner(version="2026.09.10-fd3934a\n",
                                                      about=real_shape))
        self.assertEqual(report["identity"], "cursor")
        self.assertEqual(report["version"], "2026.09.10-fd3934a")
        self.assertIn("cliVersion", report["reason"])
        self.assertNotIn("someone@example.com", json.dumps(report))
        self.assertIs(ca.require_cursor(report), report)

    def test_a_partial_or_non_string_cli_version_stays_unknown(self):
        for about in ({"cliVersion": "1.0"},                       # schema keys missing
                      {"cliVersion": 7, "latestStatus": "x", "latestVersion": "x",
                       "osPlatform": "darwin"},                    # not a string
                      {"cliVersion": "  ", "latestStatus": "x", "latestVersion": "x",
                       "osPlatform": "darwin"}):                   # blank
            with self.subTest(about=about):
                report = ca.identify(self.bin, runner=_runner(version="3.1\n", about=about))
                self.assertEqual(report["identity"], "unknown")

    def test_a_binary_that_never_names_cursor_is_unknown_and_refused(self):
        report = ca.identify(self.bin, runner=_runner(version="acme-agent 3.1\n",
                                                      about={"name": "acme"}))
        self.assertEqual(report["identity"], "unknown")
        self.assertIn("refusing", report["reason"])
        with self.assertRaises(ca.IdentityError) as ctx:
            ca.require_cursor(report)
        self.assertIn("unknown", str(ctx.exception))

    def test_an_absent_binary_is_absent_without_any_probe(self):
        calls = []
        report = ca.identify(str(self.tmp / "does-not-exist"), runner=lambda argv: calls.append(argv))
        self.assertEqual(report["identity"], "absent")
        self.assertEqual(calls, [])
        with self.assertRaises(ca.IdentityError):
            ca.require_cursor(report)

    def test_the_real_probe_path_runs_the_stub_through_the_process_runner(self):
        # No injected runner: the stub script itself answers, via proc_runner.
        report = ca.identify(self.bin, cwd=self.tmp)
        self.assertEqual(report["identity"], "cursor")
        self.assertIn("stub", report["version"])
        other = write_stub(self.tmp, name="other-agent", version=OTHER_VERSION_LINE)
        self.assertEqual(ca.identify(str(other), cwd=self.tmp)["identity"], "unknown")

    def test_models_come_from_the_host_or_are_unknown(self):
        models = ca.list_models(self.bin, runner=_runner())
        self.assertTrue(models["available"])
        self.assertEqual(models["models"], ["stub-model-a", "stub-model-b"])
        empty = ca.list_models(self.bin, runner=lambda argv: {"rc": 1, "stdout": "", "stderr": "no",
                                                              "outcome": "failed"})
        self.assertFalse(empty["available"])
        self.assertEqual(empty["models"], [])


class DispatchArgvTests(unittest.TestCase):
    def test_write_dispatch_is_headless_json_trusted_and_forced(self):
        argv = ca.build_dispatch({"id": "T1", "brief": "do it"}, model_id="m-1",
                                 prompt="[task=T1] do it", cursor_bin="agent",
                                 workspace="/w")
        self.assertEqual(argv[:8], ["agent", "-p", "--output-format", "json", "--trust",
                                    "--workspace", "/w", "--model"])
        self.assertEqual(argv[8], "m-1")
        self.assertIn("--force", argv)
        self.assertNotIn("--mode", argv)
        self.assertEqual(argv[-1], "[task=T1] do it")

    def test_read_only_dispatch_uses_mode_ask_and_never_force(self):
        argv = ca.build_dispatch({"id": "T1"}, prompt="review", cursor_bin="agent",
                                 read_only=True)
        self.assertIn("ask", argv[argv.index("--mode") + 1])
        self.assertNotIn("--force", argv)
        self.assertNotIn("--model", argv, "no model chosen means the host's default")

    def test_the_prompt_names_the_task_when_the_caller_did_not(self):
        argv = ca.build_dispatch({"id": "T7", "brief": "fix the thing"}, prompt="fix the thing")
        self.assertTrue(argv[-1].startswith("[task=T7]"))
        argv = ca.build_dispatch({"id": "T7"}, prompt="[kit=k run=r task=T7]\nfix")
        self.assertEqual(argv[-1].count("T7"), 1, "an id already present is not repeated")

    def test_extra_args_that_would_override_the_recorded_choice_are_refused(self):
        for bad in ("--force", "--mode=plan", "--model", "--api-key=x", "--resume", "-w",
                    "--output-format=text", "--yolo"):
            with self.subTest(arg=bad):
                with self.assertRaises(ValueError):
                    ca.build_dispatch({"id": "T1"}, prompt="p", extra_args=(bad,))
        argv = ca.build_dispatch({"id": "T1"}, prompt="p", extra_args=("--verbose",))
        self.assertIn("--verbose", argv)


class OutputTests(unittest.TestCase):
    def test_a_json_object_yields_the_model_it_names_and_no_usage(self):
        out = ca.parse_output(json.dumps({"model": "host-model", "result": "ok"}))
        self.assertEqual(out, {"parsed": True, "observed_model": "host-model",
                               "result_text": "ok", "usage": None})

    def test_a_stream_yields_its_last_object_and_text_yields_nothing(self):
        stream = 'noise\n{"type": "start"}\n{"model": "m2", "text": "t"}\n'
        self.assertEqual(ca.parse_output(stream)["observed_model"], "m2")
        self.assertEqual(ca.parse_output("plain words"),
                         {"parsed": False, "observed_model": None, "result_text": None,
                          "usage": None})
        self.assertIsNone(ca.parse_output('{"model": 3}')["observed_model"],
                          "a non-string model field is not a model")

    def test_usage_and_modes_are_reported_separately_and_honestly(self):
        self.assertFalse(ca.usage_report()["available"])
        self.assertIsNone(ca.usage_report()["billed_usd"])
        modes = ca.modes_report()
        self.assertEqual(set(modes), {"cli", "ide", "cloud"})
        # 2026-09-16: the CLI mode was run live (one dispatch, one review); it carries the date
        # and client version a verification must name. The IDE and cloud modes are files this
        # adapter installs, never driven, and stay unknown rather than being rounded up.
        self.assertEqual(modes["cli"]["verified"], "supported")
        self.assertTrue(modes["cli"]["verified_on"])
        self.assertTrue(modes["cli"]["client_version"])
        for mode in ("ide", "cloud"):
            with self.subTest(mode=mode):
                self.assertEqual(modes[mode]["verified"], "unknown")
        for mode, spec in modes.items():
            with self.subTest(mode=mode):
                self.assertTrue(spec["source"].startswith("https://cursor.com/docs/"))
        self.assertEqual(modes["cli"]["implemented"], "supported")
        self.assertEqual(modes["ide"]["implemented"], "files-only")
        self.assertEqual(modes["cloud"]["implemented"], "files-only")


class AmbientDiagnosisTests(unittest.TestCase):
    def test_other_harness_commands_in_discoverable_files_are_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude" / "agents").mkdir(parents=True)
            (root / ".claude" / "agents" / "impl.md").write_text(
                "run `claude -p` then /polytropos:execute demo\n")
            (root / ".claude" / "skills" / "clean").mkdir(parents=True)
            (root / ".claude" / "skills" / "clean" / "SKILL.md").write_text("harmless\n")
            (root / ".cursor" / "agents").mkdir(parents=True)
            (root / ".cursor" / "agents" / "ours.md").write_text("codex exec is not scanned here\n")
            findings = ca.diagnose_ambient(root)
            self.assertEqual([f["path"] for f in findings], [".claude/agents/impl.md"])
            self.assertEqual(findings[0]["kind"], "subagent")
            self.assertEqual(sorted(findings[0]["tokens"]), ["/polytropos:", "claude -p"])

    def test_a_clean_project_has_no_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(ca.diagnose_ambient(tmp), [])


class InstallTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.proj = self.root / "proj"
        self.proj.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _states(self, plan):
        return {a["destination"]: a["state"] for a in plan["actions"]}

    def test_bundle_sources_resolve_the_placeholder_to_this_checkout(self):
        sources = ca.bundle_sources()
        self.assertEqual(set(sources), {d for _s, d in ca.BUNDLE})
        resolved = 0
        for src, dest in ca.BUNDLE:
            data = sources[dest]
            with self.subTest(dest=dest):
                self.assertNotIn(ca.PLACEHOLDER.encode(), data)
                if ca.PLACEHOLDER in (ROOT / "cursor" / src).read_text():
                    self.assertIn(str(ROOT).encode(), data)
                    resolved += 1
        self.assertGreaterEqual(resolved, 1, "the skill entry point carries the placeholder")

    def test_fresh_install_writes_the_bundle_and_a_manifest_and_is_then_idempotent(self):
        plan = ca.plan_install(self.proj)
        self.assertEqual(set(self._states(plan).values()), {"install"})
        self.assertEqual(plan["conflicts"], [])
        written = ca.apply_install(plan)
        self.assertEqual(sorted(written), sorted(d for _s, d in ca.BUNDLE))
        manifest = json.loads((self.proj / ca.MANIFEST_REL).read_text())
        self.assertEqual(set(manifest["files"]), set(written))
        for rel in written:
            self.assertTrue((self.proj / rel).is_file())
            self.assertNotIn("{{POLYTROPOS_ROOT}}", (self.proj / rel).read_text())
        again = ca.plan_install(self.proj)
        self.assertEqual(set(self._states(again).values()), {"up-to-date"})
        self.assertEqual(ca.apply_install(again), [])

    def test_a_file_we_wrote_is_refreshed_and_a_file_we_did_not_is_preserved(self):
        ca.apply_install(ca.plan_install(self.proj))
        skill = self.proj / ".cursor" / "skills" / "polytropos-execute" / "SKILL.md"
        agent = self.proj / ".cursor" / "agents" / "polytropos-verifier.md"
        # Simulate an older managed version: manifest sha matches the current bytes but the
        # bundle moved on. Then a user edit on another file.
        with mock.patch.object(ca, "bundle_sources", return_value={
            **ca.bundle_sources(),
            ".cursor/skills/polytropos-execute/SKILL.md": skill.read_bytes() + b"\n# newer\n",
        }):
            agent.write_text("my own verifier\n")
            plan = ca.plan_install(self.proj)
            states = self._states(plan)
            self.assertEqual(states[".cursor/skills/polytropos-execute/SKILL.md"],
                             "managed-update")
            self.assertEqual(states[".cursor/agents/polytropos-verifier.md"], "unmanaged")
            self.assertEqual(plan["conflicts"], [".cursor/agents/polytropos-verifier.md"])
            before = skill.read_bytes()
            with self.assertRaises(ca.InstallConflict):
                ca.apply_install(plan)
            self.assertEqual(skill.read_bytes(), before, "a conflict means nothing is written")
            self.assertEqual(agent.read_text(), "my own verifier\n")
            # Adopt: the user's bytes are kept beside the new file.
            plan = ca.plan_install(self.proj, adopt_unmanaged=True)
            self.assertEqual(self._states(plan)[".cursor/agents/polytropos-verifier.md"],
                             "adopt-update")
            written = ca.apply_install(plan)
            self.assertIn(".cursor/agents/polytropos-verifier.md", written)
            backup = self.proj / (".cursor/agents/polytropos-verifier.md" + ca.BACKUP_SUFFIX)
            self.assertEqual(backup.read_text(), "my own verifier\n")
            self.assertNotEqual(agent.read_text(), "my own verifier\n")
            self.assertTrue(skill.read_bytes().endswith(b"# newer\n"))

    def test_an_unparseable_manifest_owns_nothing(self):
        ca.apply_install(ca.plan_install(self.proj))
        (self.proj / ca.MANIFEST_REL).write_text("{not json")
        skill = self.proj / ".cursor" / "skills" / "polytropos-execute" / "SKILL.md"
        skill.write_bytes(skill.read_bytes() + b"# drift\n")
        self.assertEqual(self._states(ca.plan_install(self.proj))[
            ".cursor/skills/polytropos-execute/SKILL.md"], "unmanaged")

    def test_a_destination_escaping_the_project_is_refused_not_written(self):
        outside = self.root / "outside.md"
        link_dir = self.proj / ".cursor"
        link_dir.mkdir()
        (link_dir / "agents").symlink_to(self.root)
        plan = ca.plan_install(self.proj)
        # The plan sees "absent" (nothing is readable through the link); the WRITE is where
        # the precondition is restated, and it refuses without following the link.
        with self.assertRaises(ca._sp().SafePathError) as ctx:
            ca.apply_install(plan)
        self.assertIn("without following a link", str(ctx.exception))
        self.assertFalse(outside.exists())
        self.assertFalse((self.root / "polytropos-implementer.md").exists())
        self.assertFalse((self.root / "polytropos-verifier.md").exists())
        skill = self.proj / ".cursor" / "skills" / "polytropos-execute" / "SKILL.md"
        self.assertFalse(skill.exists(), "the file written before the refusal is rolled back")
        self.assertFalse((self.proj / ca.MANIFEST_REL).exists())

    def test_harness_select_routes_cursor_to_the_adapter_with_project_scope(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            hs.main(["install", "--harness", "cursor", "--project", str(self.proj),
                     "--dry-run"])
        self.assertIn("install", out.getvalue())
        self.assertFalse((self.proj / ".cursor").exists(), "dry run writes nothing")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            hs.main(["install", "--harness", "cursor", "--project", str(self.proj)])
        # Derived from BUNDLE, not a literal: the count rots every time the bundle grows,
        # and what this line is actually about is that harness_select applied the whole plan.
        self.assertIn(f"wrote {len(ca.BUNDLE)} file(s)", out.getvalue())
        self.assertTrue((self.proj / ca.MANIFEST_REL).is_file())
        (self.proj / ".cursor" / "agents" / "polytropos-implementer.md").write_text("mine\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            hs.main(["install", "--harness", "cursor", "--project", str(self.proj)])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("--adopt-existing", err.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            hs.main(["install", "--harness", "cursor", "--project", str(self.proj),
                     "--adopt-existing"])
        self.assertIn("adopt-update", out.getvalue())

    def test_project_is_a_cursor_only_flag_and_detect_is_unchanged(self):
        with self.assertRaises(SystemExit):
            hs.main(["install", "--harness", "copilot", "--project", str(self.proj),
                     "--dry-run"])
        self.assertEqual(set(hs.detect()), {"claude-code", "copilot", "codex"})

    def test_doctor_reports_without_spawning_anything_but_the_named_stub(self):
        stub = write_stub(self.root, version=OTHER_VERSION_LINE)
        (self.proj / ".claude" / "agents").mkdir(parents=True)
        (self.proj / ".claude" / "agents" / "x.md").write_text("codex exec here\n")
        report = ca.doctor(self.proj, str(stub))
        self.assertEqual(report["binary"]["identity"], "unknown")
        self.assertEqual({a["state"] for a in report["install"]}, {"install"})
        self.assertEqual([f["path"] for f in report["ambient"]], [".claude/agents/x.md"])
        self.assertFalse(report["usage"]["available"])
        self.assertIn("--mode ask", report["smoke"]["command"])
        text = ca.render_doctor(report)
        self.assertIn("smoke (not run)", text)
        self.assertIn("identity unknown", text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            hs.main(["doctor", "--harness", "cursor", "--project", str(self.proj),
                     "--cursor-bin", str(stub), "--json"])
        self.assertEqual(json.loads(out.getvalue())["binary"]["identity"], "unknown")
        self.assertFalse((self.proj / ".cursor").exists(), "doctor writes nothing")


class RegistryAndPricingTests(unittest.TestCase):
    def test_the_adapter_reports_the_registry_rows_and_its_own_pricing_file(self):
        adapter = ca.adapter()
        self.assertIsInstance(adapter, ha.Adapter)
        self.assertEqual(adapter.name, "cursor")
        self.assertEqual(adapter.pricing_file, "data/pricing.cursor.json")
        rows = adapter.capabilities()
        for name in ("dispatch", "identity_probe", "read_only_dispatch", "ide_mode",
                     "cloud_mode", "usage_report", "ambient_diagnosis"):
            self.assertIn(name, rows)
        # 2026-09-16: `dispatch` was run live once and is verified with a date; `requires`
        # accepts it. A row nobody has run (`model_selection`: no --model was ever passed live)
        # is still refused, and `usage_report` stays unsupported: the product reports usage in
        # its JSON result, but this adapter does not read it yet.
        self.assertEqual(ha.effective(rows["dispatch"]), ha.SUPPORTED)
        self.assertTrue(rows["dispatch"]["verified_on"])
        self.assertTrue(adapter.requires("dispatch"))
        self.assertEqual(ha.effective(rows["model_selection"]), ha.UNKNOWN,
                         "never run live from here, so never more than unknown")
        self.assertEqual(ha.effective(rows["usage_report"]), ha.UNSUPPORTED)
        with self.assertRaises(ha.CapabilityError):
            adapter.requires("model_selection")

    def test_pricing_is_its_own_empty_file_with_a_date_and_no_borrowed_numbers(self):
        payload = json.loads((ROOT / "data" / "pricing.cursor.json").read_text())
        self.assertEqual(payload["models"], {})
        self.assertRegex(payload["cached_date"], r"^\d{4}-\d{2}-\d{2}$")
        for mode in payload["billing_modes"].values():
            self.assertIsNone(mode.get("usd_per_unit"))
        source = (BIN_DIR / "cursor_adapter.py").read_text() + \
            (BIN_DIR / "cursor_execute.py").read_text()
        for other in ("pricing.json", "pricing.codex.json", "pricing.copilot.json"):
            self.assertNotIn(other, source, f"cursor never reads {other}")

    def test_the_adapter_carries_no_process_primitive_of_its_own(self):
        source = (BIN_DIR / "cursor_adapter.py").read_text()
        for banned in ("import subprocess", "os.system", "Path.home(", "sqlite3",
                       "os.popen"):
            self.assertNotIn(banned, source)

    def test_the_demo_and_help_run_offline(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ca.main(["demo"])
        text = out.getvalue()
        self.assertIn("refused", text)
        self.assertIn("adopt-update", text)
        self.assertIn("smoke (not run)", text)
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stdout(io.StringIO()):
            ca.main(["--help"])
        self.assertEqual(ctx.exception.code, 0)


class BundleContentTests(unittest.TestCase):
    def test_the_bundle_names_no_other_harness_command_and_no_price(self):
        for src, _dest in ca.BUNDLE:
            text = (ROOT / "cursor" / src).read_text()
            with self.subTest(file=src):
                for token in ca.OTHER_HARNESS_TOKENS:
                    self.assertNotIn(token, text)
                self.assertNotIn("$", text.replace("${{", ""), "no dollar figures")
        skill = (ROOT / "cursor" / "skills" / "polytropos-execute" / "SKILL.md").read_text()
        self.assertIn("{{POLYTROPOS_ROOT}}", skill, "the entry point resolves at install")

    def test_subagent_frontmatter_states_write_access_explicitly(self):
        impl = (ROOT / "cursor" / "agents" / "polytropos-implementer.md").read_text()
        ver = (ROOT / "cursor" / "agents" / "polytropos-verifier.md").read_text()
        self.assertIn("readonly: false", impl)
        self.assertIn("readonly: true", ver)
        self.assertIn("model: inherit", impl)


if __name__ == "__main__":
    unittest.main()
