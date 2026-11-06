"""Offline, synthetic context-travel contract tests."""

import copy
import importlib.util
import json
import os
import socket
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "bin" / "context_travel.py"
SPEC = importlib.util.spec_from_file_location("context_travel", MODULE_PATH)
ct = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ct)


def request(**changes):
    parts = dict(repository_id="repo-A", checkout_id="checkout-1", revision="abc123",
                 kit_path=".claude/kits/example", task_id="CT1", assignment_id="run-1",
                 assignment_role="implementer", question="Summarize this task")
    parts.update(changes)
    return ct.make_request(**parts)


def briefing(req=None):
    return ct.make_briefing(req or request(), "A summary", ["First criterion", "Second criterion"],
                            evidence=[{"kind": "source", "ref": None, "note": "Unknown source"}])


class ContextTravelTests(unittest.TestCase):
    def test_import_has_no_bin_path_dependency(self):
        self.assertEqual(ct.CONTRACT_VERSION, "polytropos.context-travel/1")
        self.assertEqual(request()["repository_id"], "repo-A")

    def test_roundtrip_and_canonical_order(self):
        req = request()
        brief = briefing(req)
        self.assertEqual(ct.parse_request(ct.canonical_bytes(req)), req)
        self.assertEqual(ct.parse_briefing(req, ct.canonical_bytes(brief)), brief)
        self.assertEqual(ct.canonical_bytes(req), ct.canonical_bytes(dict(reversed(list(req.items())))))
        self.assertEqual(ct.content_sha(req), ct.content_sha(dict(reversed(list(req.items())))))
        changed = ct.make_briefing(req, "A summary", ["Second criterion", "First criterion"])
        self.assertNotEqual(changed["content_sha"], brief["content_sha"])

    def test_namespaces_and_applicability(self):
        base = request()
        self.assertNotEqual(base["task_identity"], request(repository_id="repo-B")["task_identity"])
        self.assertNotEqual(base["task_identity"], request(kit_path=".claude/kits/other")["task_identity"])
        changed = request(revision="def456", checkout_id="checkout-2")
        self.assertEqual(base["task_identity"], changed["task_identity"])
        self.assertNotEqual(base["request_sha"], changed["request_sha"])
        state = {"id": "dirty-tree-A", "sha": None, "v": None}
        self.assertNotEqual(base["request_sha"], request(source_state_ref=state)["request_sha"])
        self.assertEqual(request(task_id="Ä-01")["task_id"], "Ä-01")

    def test_correlation_and_tampering(self):
        req = request()
        value = briefing(req)
        for changed in (request(repository_id="repo-B"), request(assignment_id="run-2"),
                        request(revision="def456"), request(source_state_ref={"id": "dirty", "sha": None, "v": None}),
                        request(question="A different question"),
                        request(acceptance_ref={"id": "acceptance-2", "sha": None, "v": None})):
            with self.subTest(changed=changed["request_sha"]), self.assertRaises(ct.ContractError):
                ct.parse_briefing(changed, ct.canonical_bytes(value))
        tampered = copy.deepcopy(value)
        tampered["criteria"][0]["text"] = "Changed criterion"
        with self.assertRaises(ct.ContractError):
            ct.parse_briefing(req, ct.canonical_bytes(tampered))
        unknown = copy.deepcopy(value)
        unknown["authority"] = "accept"
        with self.assertRaises(ct.ContractError):
            ct.parse_briefing(req, ct.canonical_bytes(unknown))
        nested = copy.deepcopy(value)
        nested["evidence"][0]["ref"] = {"id": "source", "sha": None, "v": None, "extra": 1}
        nested["content_sha"] = ct.content_sha({k: v for k, v in nested.items() if k != "content_sha"})
        with self.assertRaises(ct.ContractError):
            ct.parse_briefing(req, ct.canonical_bytes(nested))

    def test_unknown_provenance_and_redaction(self):
        req = request(question="Token: hunter2")
        self.assertEqual(req["question"]["redactions"], {"assigned-secret": 1})
        self.assertNotIn("hunter2", ct.canonical_bytes(req).decode())
        value = briefing(req)
        self.assertEqual(set(value["provenance"]), set(ct.attempt_ledger.PROVENANCE_REFS))
        self.assertTrue(all(ref is None for ref in value["provenance"].values()))
        self.assertIsNone(value["evidence"][0]["ref"])

    def test_strict_json_and_limits(self):
        req = request()
        for raw in ('{"v":1,"v":2}', '{"v":NaN}', '[1e999]', '{"v": Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ct.ContractError):
                ct.parse_request(raw)
        for bad in ({**req, "extension": 1}, {**req, "v": "future"},
                    {**req, "request_sha": "0" * 64}):
            with self.assertRaises(ct.ContractError):
                ct.parse_request(ct.canonical_bytes(bad))
        for bad in ("../kit", "/absolute", "a//b", "C:/drive", "a\\b"):
            with self.subTest(path=bad), self.assertRaises(ct.ContractError):
                request(kit_path=bad)
        with self.assertRaises(ct.ContractError):
            request(repository_id="ghp_" + "x" * 30)
        with self.assertRaises(ct.ContractError):
            ct.make_briefing(req, "summary", ["x" * (ct.MAX_TEXT + 1)])
        with self.assertRaises(ct.ContractError):
            ct.make_briefing(req, "summary", ["ok"] * (ct.MAX_ITEMS + 1))
        with self.assertRaises(ct.ContractError):
            ct.parse_request(" " * (ct.MAX_BYTES + 1))
        with self.assertRaises(ct.ContractError):
            ct.canonical_bytes({"bad": object()})

    def test_nested_refs_missing_fields_and_versions(self):
        req = request()
        for malformed in ({"id": "x", "sha": None},
                          {"id": None, "sha": None, "v": None},
                          {"id": "x", "sha": "wrong", "v": None},
                          {"id": "ghp_" + "x" * 30, "sha": None, "v": None},
                          {"id": "x", "sha": None, "v": "secret=hunter2"}):
            with self.subTest(ref=malformed), self.assertRaises(ct.ContractError):
                request(source_ref=malformed)
        missing = copy.deepcopy(req)
        del missing["assignment_role"]
        with self.assertRaises(ct.ContractError):
            ct.parse_request(ct.canonical_bytes(missing))
        bad_identity = copy.deepcopy(req)
        bad_identity["task_identity"] = "sha256:" + "0" * 64
        bad_identity["request_sha"] = ct.content_sha({k: v for k, v in bad_identity.items()
                                                        if k != "request_sha"})
        with self.assertRaises(ct.ContractError):
            ct.parse_request(ct.canonical_bytes(bad_identity))
        value = briefing(req)
        for edit in (lambda x: x.pop("summary"), lambda x: x.update(v="future"),
                     lambda x: x.update(extra="unapproved")):
            changed = copy.deepcopy(value)
            edit(changed)
            with self.assertRaises(ct.ContractError):
                ct.parse_briefing(req, ct.canonical_bytes(changed))
        bad_ref = copy.deepcopy(value)
        bad_ref["provenance"]["policy_ref"] = {"id": "p", "sha": None}
        bad_ref["content_sha"] = ct.content_sha({k: v for k, v in bad_ref.items()
                                                  if k != "content_sha"})
        with self.assertRaises(ct.ContractError):
            ct.parse_briefing(req, ct.canonical_bytes(bad_ref))

    def test_depth_cycles_and_independent_echo(self):
        cycle = []
        cycle.append(cycle)
        with self.assertRaises(ct.ContractError):
            ct.canonical_bytes(cycle)
        with self.assertRaises(ct.ContractError):
            ct.parse_request("[" * 1200 + "0" + "]" * 1200)
        source = {"id": "source-state", "sha": None, "v": None}
        req = request(source_state_ref=source)
        value = briefing(req)
        value["source_state_ref"]["id"] = "mutated"
        value["question"]["text"] = "mutated"
        self.assertEqual(req["source_state_ref"]["id"], "source-state")
        self.assertEqual(req["question"]["text"], "Summarize this task")

    def test_contract_operations_do_not_use_external_seams(self):
        def prohibited(*args, **kwargs):
            raise AssertionError("contract operation used an external seam")

        with (mock.patch("builtins.open", prohibited),
              mock.patch.object(Path, "open", prohibited),
              mock.patch.object(Path, "read_text", prohibited),
              mock.patch.object(Path, "write_text", prohibited),
              mock.patch.object(Path, "home", prohibited),
              mock.patch.object(os, "getcwd", prohibited),
              mock.patch.object(os, "getenv", prohibited),
              mock.patch.object(os, "system", prohibited),
              mock.patch.object(time, "time", prohibited),
              mock.patch.object(time, "monotonic", prohibited),
              mock.patch.object(subprocess, "Popen", prohibited),
              mock.patch.object(socket, "socket", prohibited)):
            req = request()
            value = briefing(req)
            self.assertEqual(ct.parse_request(ct.canonical_bytes(req)), req)
            self.assertEqual(ct.parse_briefing(req, ct.canonical_bytes(value)), value)


if __name__ == "__main__":
    unittest.main()
