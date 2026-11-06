"""Offline CT4 command line transport tests."""

import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


BIN = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location("ct4_cli_test_" + name, BIN / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ct = _load("context_travel")
query = _load("context_travel_query")
cli = _load("context_travel_cli")
proc = _load("proc_runner")

TASKS = ("### T1 — Synthetic task\n- status: pending\n"
         "\n**Brief.** Explain the fixture.\n"
         "\n**Acceptance.** Criterion one must hold.\n")


class CliTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.kit = ".claude/kits/alpha"
        kit_dir = self.root / self.kit
        kit_dir.mkdir(parents=True)
        (kit_dir / "TASKS.md").write_text(TASKS)
        config = {"v": "polytropos.context-query-config/1",
                  "repositories": [{"id": "repo-a", "root": str(self.root),
                                    "kits": [{"path": self.kit, "kit_files": ["TASKS.md"],
                                              "graph_path": None, "evidence": None}]}],
                  "deny_prefixes": [],
                  "limits": {"max_sources": 2, "max_source_bytes": 4096,
                             "max_total_bytes": 8192, "max_items": 16},
                  "max_output_bytes": 32768}
        self.config_path = self.root / "query-config.json"
        self.config_path.write_text(json.dumps(config))
        self.request = ct.make_request("repo-a", "checkout-a", None, self.kit, "T1",
                                       "assignment-a", "implementer", "What is next?")
        self.assignment = {"repository_id": "repo-a", "checkout_id": "checkout-a",
                           "revision": None, "kit_path": self.kit, "task_id": "T1",
                           "assignment_id": "assignment-a", "assignment_role": "implementer",
                           "question": "What is next?"}

    def invoke(self, operation, args, *, output_format="json"):
        stdout, stderr = io.StringIO(), io.StringIO()
        rc = cli.main(["--config", str(self.config_path), operation,
                       "--format", output_format],
                      stdin=io.StringIO(json.dumps(args) + "\n"),
                      stdout=stdout, stderr=stderr)
        return rc, stdout.getvalue(), stderr.getvalue()

    def test_json_stdout_is_one_query_envelope(self):
        rc, out, err = self.invoke("overview", {"request": self.request})
        self.assertEqual(rc, 0, err)
        self.assertEqual(err, "")
        self.assertEqual(out.count("\n"), 1)
        envelope = json.loads(out)
        self.assertEqual(envelope["operation"], "overview")
        self.assertEqual(envelope["v"], "polytropos.context-query/1")
        shared = query.run_query(query.load_config(str(self.config_path)),
                                 "overview", {"request": self.request})
        self.assertEqual(envelope, shared)

    def test_text_brief_retains_criteria(self):
        rc, out, err = self.invoke("brief", {"request": self.request}, output_format="text")
        self.assertEqual(rc, 0, err)
        self.assertIn("Criterion one must hold.", out)

    def test_plain_assignment_and_sealed_request_have_same_json(self):
        sealed_rc, sealed_out, sealed_err = self.invoke("overview", {"request": self.request})
        plain_rc, plain_out, plain_err = self.invoke("overview",
                                                    {"assignment": self.assignment})
        self.assertEqual((sealed_rc, plain_rc), (0, 0), sealed_err + plain_err)
        self.assertEqual(json.loads(plain_out), json.loads(sealed_out))

    def test_invalid_tool_arg_error_does_not_echo_input_or_path(self):
        secret = "AKIAIOSFODNN7EXAMPLE"
        rc, out, err = self.invoke("overview", {"request": self.request,
                                                "root": str(self.root / secret)})
        self.assertNotEqual(rc, 0)
        self.assertNotIn(secret, out + err)
        self.assertNotIn(str(self.root), out + err)

    def test_duplicate_argument_key_is_rejected(self):
        raw = '{"request":null,"request":null}\n'
        stdout, stderr = io.StringIO(), io.StringIO()
        rc = cli.main(["--config", str(self.config_path), "overview", "--format", "json"],
                      stdin=io.StringIO(raw), stdout=stdout, stderr=stderr)
        self.assertNotEqual(rc, 0)
        self.assertNotIn(raw.strip(), stdout.getvalue() + stderr.getvalue())

    def test_unknown_operation_is_rejected_without_config_echo(self):
        rc, out, err = self.invoke("unknown-operation", {})
        self.assertNotEqual(rc, 0)
        self.assertNotIn(str(self.root), out + err)

    def test_script_entry_point_runs_with_temp_home_and_protocol_stdout(self):
        env = {"HOME": str(self.root / "fixture-home"),
               "POLYTROPOS_DATA_HOME": str(self.root / "fixture-data"),
               "PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
        result = proc.run(
            ["/opt/homebrew/bin/python3.12", "-B", str(BIN / "context_travel_cli.py"),
             "--config", str(self.config_path), "overview", "--format", "json"],
            cwd=self.root, within=self.root, env=env, timeout=5, output_limit=65536,
            input_text=json.dumps({"request": self.request}) + "\n", text=False)
        self.assertEqual(result["outcome"], proc.OUTCOME_OK, result["stderr"])
        self.assertEqual(result["rc"], 0)
        self.assertEqual(result["stderr"], b"")
        self.assertEqual(result["stdout"].count(b"\n"), 1)
        envelope = json.loads(result["stdout"])
        self.assertEqual(envelope["operation"], "overview")
        self.assertFalse((self.root / "fixture-home").exists())

    def test_help_works_without_config_read(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch("os.open", side_effect=AssertionError("config read")):
            rc = cli.main(["--help"], stdin=io.StringIO(),
                          stdout=stdout, stderr=stderr)
        self.assertEqual(rc, 0)
        self.assertIn("--config", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_exact_core_byte_limit_keeps_complete_cli_line_within_frame(self):
        shared = query.run_query(query.load_config(str(self.config_path)),
                                 "overview", {"request": self.request})
        core_bytes = query.canonical_bytes(shared)
        self.assertGreaterEqual(len(core_bytes), 1024)
        config = json.loads(self.config_path.read_text())
        config["max_output_bytes"] = len(core_bytes)
        self.config_path.write_text(json.dumps(config))
        # Reuse the validated artifact so the live composer's own reserve does not
        # intentionally choose a smaller partial view under the tighter cap.
        rc, out, err = self.invoke("overview", {"view": shared["data"]})
        self.assertEqual(rc, 0, err)
        self.assertTrue(out.endswith("\n"))
        self.assertEqual(len(out.encode("utf-8")), len(core_bytes) + 1)
        self.assertLessEqual(len(out.encode("utf-8")), 131072)
        self.assertIn("Criterion one must hold.", out)


if __name__ == "__main__":
    unittest.main()
