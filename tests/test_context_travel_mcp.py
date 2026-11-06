"""Offline newline JSON-RPC transport tests for CT4."""

import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


BIN = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location("ct4_mcp_test_" + name, BIN / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ct = _load("context_travel")
query = _load("context_travel_query")
mcp = _load("context_travel_mcp")
proc = _load("proc_runner")


def _frame(method, ident=None, params=None):
    value = {"jsonrpc": "2.0", "method": method}
    if ident is not None:
        value["id"] = ident
    if params is not None:
        value["params"] = params
    return value


class McpTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.kit = ".claude/kits/alpha"
        kit_dir = self.root / self.kit
        kit_dir.mkdir(parents=True)
        (kit_dir / "TASKS.md").write_text(
            "### T1 — Synthetic task\n- status: pending\n\n"
            "**Brief.** Explain fixture.\n\n**Acceptance.** Criterion one.\n")
        config = {"v": "polytropos.context-query-config/1",
                  "repositories": [{"id": "repo-a", "root": str(self.root),
                                    "kits": [{"path": self.kit, "kit_files": ["TASKS.md"],
                                              "graph_path": None, "evidence": None}]}],
                  "deny_prefixes": [],
                  "limits": {"max_sources": 2, "max_source_bytes": 4096,
                             "max_total_bytes": 8192, "max_items": 16},
                  "max_output_bytes": 32768}
        self.config = query.parse_config(json.dumps(config))
        self.config_path = self.root / "query-config.json"
        self.config_path.write_text(json.dumps(config))
        self.request = ct.make_request("repo-a", "checkout-a", None, self.kit, "T1",
                                       "assignment-a", "implementer", "What is next?")
        self.assignment = {"repository_id": "repo-a", "checkout_id": "checkout-a",
                           "revision": None, "kit_path": self.kit, "task_id": "T1",
                           "assignment_id": "assignment-a", "assignment_role": "implementer",
                           "question": "What is next?"}

    def exchange(self, frames):
        stdin = io.BytesIO("".join(json.dumps(frame) + "\n" for frame in frames)
                           .encode("utf-8"))
        stdout = io.BytesIO()
        mcp.serve(self.config, stdin, stdout)
        lines = stdout.getvalue().decode("utf-8").splitlines()
        return [json.loads(line) for line in lines]

    def raw_exchange(self, payload):
        stdout = io.BytesIO()
        mcp.serve(self.config, io.BytesIO(payload), stdout)
        return [json.loads(line) for line in stdout.getvalue().decode("utf-8").splitlines()]

    def initialized(self):
        return [_frame("initialize", 1, {"protocolVersion": "2025-11-25",
                                          "capabilities": {},
                                          "clientInfo": {"name": "fixture", "version": "1"}}),
                _frame("notifications/initialized")]

    def test_initialize_ping_and_tool_discovery(self):
        replies = self.exchange(self.initialized() + [
            _frame("ping", 2), _frame("tools/list", 3)])
        by_id = {reply["id"]: reply for reply in replies}
        self.assertEqual(by_id[1]["result"]["protocolVersion"], "2025-11-25")
        self.assertIn("result", by_id[2])
        names = {tool["name"] for tool in by_id[3]["result"]["tools"]}
        self.assertEqual(names, {"overview", "brief", "explain", "changes", "capabilities"})

    def test_discovery_exposes_closed_typed_first_call_assignment(self):
        replies = self.exchange(self.initialized() + [_frame("tools/list", 3)])
        tools = {item["name"]: item for item in replies[-1]["result"]["tools"]}
        required = {"repository_id", "checkout_id", "revision", "kit_path", "task_id",
                    "assignment_id", "assignment_role", "question"}
        for name in ("overview", "brief"):
            with self.subTest(name=name):
                tool = tools[name]
                schema = tool["inputSchema"]["properties"]["assignment"]
                self.assertEqual(schema["type"], "object")
                self.assertIs(schema["additionalProperties"], False)
                self.assertEqual(set(schema["required"]), required)
                self.assertEqual(schema["properties"]["question"]["type"], "string")
                self.assertIn("assignment", tool["description"].lower())

    def test_tool_result_contains_exact_query_envelope(self):
        live = query.run_query(self.config, "overview", {"request": self.request})
        replies = self.exchange(self.initialized() + [
            _frame("tools/call", 4, {"name": "overview",
                                     "arguments": {"view": live["data"]}})])
        reply = next(item for item in replies if item.get("id") == 4)
        content = reply["result"]["content"]
        self.assertEqual(len(content), 1)
        self.assertEqual(json.loads(content[0]["text"]), live)

    def test_first_call_plain_assignment_matches_sealed_core_query(self):
        expected = query.run_query(self.config, "overview", {"request": self.request})
        replies = self.exchange(self.initialized() + [
            _frame("tools/call", 4, {"name": "overview",
                                     "arguments": {"assignment": self.assignment}})])
        reply = next(item for item in replies if item.get("id") == 4)
        self.assertNotIn("error", reply)
        self.assertEqual(json.loads(reply["result"]["content"][0]["text"]), expected)

    def test_tools_are_gated_until_initialized(self):
        replies = self.exchange([_frame("tools/list", 1)])
        self.assertEqual(len(replies), 1)
        self.assertIn("error", replies[0])

    def test_duplicate_request_id_is_rejected(self):
        replies = self.exchange(self.initialized() + [_frame("ping", 2), _frame("ping", 2)])
        duplicates = [reply for reply in replies if reply.get("id") == 2]
        self.assertEqual(len(duplicates), 2)
        self.assertIn("result", duplicates[0])
        self.assertIn("error", duplicates[1])

    def test_malformed_frames_have_closed_errors_without_input_echo(self):
        invalid = (
            b"\xff\n",
            b'{"jsonrpc":"2.0","id":9,"method":"ping","x":1e999}\n',
            b'{"jsonrpc":"2.0","id":9,"method":"ping","id":10}\n',
            b"[" * 700 + b"0" + b"]" * 700 + b"\n",
        )
        for payload in invalid:
            with self.subTest(payload=payload[:20]):
                replies = self.raw_exchange(payload)
                self.assertTrue(replies)
                self.assertTrue(any("error" in reply for reply in replies))
                self.assertNotIn("1e999", json.dumps(replies))

    def test_oversized_frame_is_rejected_without_echo(self):
        marker = "synthetic-secret-marker"
        frame = json.dumps(_frame("ping", 9, {"blob": marker + "x" * 131072})).encode()
        replies = self.raw_exchange(frame + b"\n")
        self.assertTrue(any("error" in reply for reply in replies))
        self.assertNotIn(marker, json.dumps(replies))

    def test_invalid_tool_argument_cannot_select_root(self):
        marker = "synthetic-secret-marker"
        replies = self.exchange(self.initialized() + [
            _frame("tools/call", 4, {"name": "overview", "arguments": {
                "request": self.request, "root": marker}})])
        reply = next(item for item in replies if item.get("id") == 4)
        self.assertTrue("error" in reply or reply.get("result", {}).get("isError"))
        self.assertNotIn(marker, json.dumps(reply))

    def test_selected_read_oserror_is_closed_tool_error_and_session_survives(self):
        marker = "synthetic private path"
        with mock.patch.object(mcp._query._readers, "read_sources",
                               side_effect=OSError(marker)):
            replies = self.exchange(self.initialized() + [
                _frame("tools/call", 4, {"name": "overview",
                                         "arguments": {"request": self.request}}),
                _frame("ping", 5)])
        by_id = {reply.get("id"): reply for reply in replies}
        self.assertTrue(by_id[4].get("result", {}).get("isError"))
        self.assertNotIn(marker, json.dumps(by_id[4]))
        self.assertIn("result", by_id[5])

    def test_cancellation_notification_does_not_claim_cancelled_result(self):
        replies = self.exchange(self.initialized() + [
            _frame("notifications/cancelled", params={"requestId": 99,
                                                       "reason": "no longer needed"}),
            _frame("ping", 2)])
        self.assertEqual([reply["id"] for reply in replies], [1, 2])
        self.assertIn("result", replies[-1])

    def test_boolean_null_ids_and_batch_are_rejected(self):
        malformed = (
            b'{"jsonrpc":"2.0","id":true,"method":"ping"}\n',
            b'{"jsonrpc":"2.0","id":null,"method":"ping"}\n',
            b'[{"jsonrpc":"2.0","id":1,"method":"ping"}]\n',
        )
        for raw in malformed:
            with self.subTest(raw=raw[:28]):
                replies = self.raw_exchange(raw)
                self.assertTrue(replies)
                self.assertTrue(any("error" in reply for reply in replies))

    def test_unsupported_protocol_version_negotiates_and_stays_gated_until_initialized(self):
        replies = self.exchange([
            _frame("initialize", 1, {"protocolVersion": "1970-01-01",
                                      "capabilities": {},
                                      "clientInfo": {"name": "fixture", "version": "1"}}),
            _frame("tools/list", 2),
            _frame("notifications/initialized"),
            _frame("tools/list", 3)])
        self.assertEqual(next(reply for reply in replies if reply.get("id") == 1)
                         ["result"]["protocolVersion"], "2025-11-25")
        self.assertIn("error", next(reply for reply in replies if reply.get("id") == 2))
        self.assertIn("result", next(reply for reply in replies if reply.get("id") == 3))

    def test_ping_before_initialize_and_unknown_notifications_are_silent(self):
        replies = self.exchange([
            _frame("notifications/unknown", params={"x": "synthetic"}),
            _frame("ping", 1)])
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0]["id"], 1)
        self.assertIn("result", replies[0])

    def test_invalid_initialized_params_do_not_unlock_tools(self):
        replies = self.exchange([
            self.initialized()[0],
            _frame("notifications/initialized", params={"unexpected": 1}),
            _frame("tools/list", 2)])
        self.assertIn("error", next(reply for reply in replies if reply.get("id") == 2))

    def test_initialize_requires_valid_client_info(self):
        for client in ({}, {"name": "fixture"}, {"name": 3, "version": "1"}):
            with self.subTest(client=client):
                replies = self.exchange([_frame("initialize", 1, {
                    "protocolVersion": "2025-11-25", "capabilities": {},
                    "clientInfo": client})])
                self.assertIn("error", replies[0])

    def test_initialize_validates_known_roots_capability_shape(self):
        for roots in ({"listChanged": "yes"}, {"listChanged": 1},
                      {"listChanged": True, "unexpected": True}):
            with self.subTest(roots=roots):
                replies = self.exchange([_frame("initialize", 1, {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {"roots": roots},
                    "clientInfo": {"name": "fixture", "version": "1"}})])
                self.assertIn("error", replies[0])
        valid = self.exchange([_frame("initialize", 1, {
            "protocolVersion": "2025-11-25",
            "capabilities": {"roots": {"listChanged": True}},
            "clientInfo": {"name": "fixture", "version": "1"}})])
        self.assertIn("result", valid[0])

    def test_credential_shaped_request_id_is_rejected_without_echo(self):
        ident = "AKIAIOSFODNN7EXAMPLE"
        replies = self.exchange([_frame("ping", ident)])
        self.assertTrue(any("error" in reply for reply in replies))
        self.assertNotIn(ident, json.dumps(replies))

    def test_script_entry_point_serves_initialized_tool_call_offline(self):
        frames = self.initialized() + [
            _frame("tools/call", 4, {"name": "overview",
                                     "arguments": {"view": query.run_query(
                                         self.config, "overview",
                                         {"request": self.request})["data"]}})]
        payload = "".join(json.dumps(frame) + "\n" for frame in frames).encode("utf-8")
        env = {"HOME": str(self.root / "fixture-home"),
               "POLYTROPOS_DATA_HOME": str(self.root / "fixture-data"),
               "PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
        result = proc.run(
            ["/opt/homebrew/bin/python3.12", "-B", str(BIN / "context_travel_mcp.py"),
             "--config", str(self.config_path)], cwd=self.root, within=self.root,
            env=env, timeout=5, output_limit=131072, input_text=payload, text=False)
        self.assertEqual(result["outcome"], proc.OUTCOME_OK, result["stderr"])
        self.assertEqual(result["rc"], 0)
        self.assertEqual(result["stderr"], b"")
        replies = [json.loads(line) for line in result["stdout"].splitlines()]
        self.assertEqual([reply["id"] for reply in replies], [1, 4])
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-11-25")
        self.assertEqual(json.loads(replies[1]["result"]["content"][0]["text"])
                         ["operation"], "overview")
        self.assertFalse((self.root / "fixture-home").exists())

    def test_help_works_without_config_read(self):
        stdout, stderr = io.BytesIO(), io.StringIO()
        with mock.patch("os.open", side_effect=AssertionError("config read")):
            rc = mcp.main(["--help"], stdin=io.BytesIO(),
                          stdout=stdout, stderr=stderr)
        self.assertEqual(rc, 0)
        self.assertIn(b"--config", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_session_frame_cap_prevents_unbounded_work(self):
        frames = self.initialized() + [_frame("ping", i) for i in range(2, 262)]
        replies = self.exchange(frames)
        ping_successes = [reply for reply in replies
                          if reply.get("id") != 1 and "result" in reply]
        self.assertLess(len(ping_successes), 260)


if __name__ == "__main__":
    unittest.main()
