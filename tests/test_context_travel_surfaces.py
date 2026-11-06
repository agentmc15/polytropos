"""CT5 offline package and handoff checks; no installed client is invoked."""

import importlib.util
import copy
import json
import re
import shlex
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "bin"
SKILL_ROOTS = (
    ROOT / "skills" / "context-travel",
    ROOT / "codex" / "skills" / "context-travel",
    ROOT / "copilot" / ".github" / "skills" / "context-travel",
)
SURFACE_IDS = {
    "codex-desktop", "codex-cli", "claude-desktop", "claude-code-cli",
    "copilot-desktop-app", "copilot-cli",
}


def _load(name):
    spec = importlib.util.spec_from_file_location("ct5_" + name, BIN / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


selector = _load("harness_select")
query = _load("context_travel_query")
proc = _load("proc_runner")


class SurfacePackageTests(unittest.TestCase):
    def test_exact_surface_and_mode_roster_preserves_distinct_desktop_modes(self):
        data = json.loads((ROOT / "primitives" / "context-travel-surfaces.json").read_text())
        self.assertEqual(data["schema_version"], "polytropos.context-travel-surfaces/1")
        surfaces = data["surfaces"]
        self.assertEqual({surface["id"] for surface in surfaces}, SURFACE_IDS)
        self.assertEqual(len(surfaces), 6)
        modes = [(surface["id"], mode["id"])
                 for surface in surfaces for mode in surface["modes"]]
        self.assertEqual(len(modes), 7)
        self.assertEqual(len(set(modes)), 7)
        desktop_modes = [mode for sid, mode in modes if sid == "claude-desktop"]
        self.assertEqual(set(desktop_modes), {"claude-desktop-chat", "claude-desktop-code"})
        for surface in surfaces:
            with self.subTest(surface=surface["id"]):
                self.assertTrue((ROOT / surface["skill_root"] / "SKILL.md").is_file())
                for mode in surface["modes"]:
                    for field in ("client_version", "os", "execution_location",
                                  "organization_policy", "documented_product", "installed_client"):
                        self.assertEqual(mode[field], "unknown")
                    self.assertIn(mode["transport"],
                                  {"conditional-local-cli", "bounded-artifact-handoff"})
                    self.assertIn(mode["fallback"],
                                  {"bounded-artifact-handoff", "existing-workflow"})
                    self.assertTrue(mode["packaged_implementation"])

    def test_each_native_skill_has_a_bounded_shared_recipe(self):
        shared = ROOT / "docs" / "CONTEXT-TRAVEL-SURFACES.md"
        self.assertTrue(shared.is_file())
        guide = shared.read_text()
        for operation in ("overview", "brief", "explain", "changes", "capabilities"):
            self.assertIn(operation, guide)
        for root in SKILL_ROOTS:
            with self.subTest(root=root):
                card = (root / "SKILL.md").read_text()
                self.assertIn("context-travel", card)
                self.assertIn("CONTEXT-TRAVEL-SURFACES.md", card)
                self.assertIn("context_travel_cli.py", card)
                self.assertIn("{{POLYTROPOS_ROOT}}" if root != SKILL_ROOTS[0]
                              else "${CLAUDE_PLUGIN_ROOT}", card)
        self.assertTrue((SKILL_ROOTS[1] / "agents" / "openai.yaml").is_file())

    def test_existing_workflow_entrypoints_reference_optional_context_without_authority_transfer(self):
        workflows = (
            ROOT / "skills" / "architect" / "SKILL.md",
            ROOT / "skills" / "route" / "SKILL.md",
            ROOT / "skills" / "execute" / "SKILL.md",
            ROOT / "skills" / "assess-improvement" / "SKILL.md",
            ROOT / "skills" / "escalate" / "SKILL.md",
            ROOT / "codex" / "skills" / "architect" / "SKILL.md",
            ROOT / "codex" / "skills" / "route" / "SKILL.md",
            ROOT / "codex" / "skills" / "execute" / "SKILL.md",
            ROOT / "codex" / "skills" / "assess-improvement" / "SKILL.md",
            ROOT / "codex" / "skills" / "escalate" / "SKILL.md",
            ROOT / "codex" / "agents" / "kit-implementer.toml",
            ROOT / "codex" / "agents" / "kit-verifier.toml",
            ROOT / "codex" / "agents" / "phase-reviewer.toml",
            ROOT / "copilot" / ".github" / "agents" / "architect.agent.md",
            ROOT / "copilot" / ".github" / "agents" / "route.agent.md",
            ROOT / "copilot" / ".github" / "agents" / "escalate.agent.md",
            ROOT / "copilot" / ".github" / "agents" / "implementer.agent.md",
            ROOT / "copilot" / ".github" / "agents" / "verifier.agent.md",
            ROOT / "copilot" / ".github" / "agents" / "reviewer.agent.md",
            ROOT / "copilot" / ".github" / "skills" / "architect" / "SKILL.md",
            ROOT / "copilot" / ".github" / "skills" / "route" / "SKILL.md",
            ROOT / "copilot" / ".github" / "skills" / "execute" / "SKILL.md",
            ROOT / "copilot" / ".github" / "skills" / "escalate" / "SKILL.md",
        )
        for path in workflows:
            with self.subTest(path=path):
                self.assertIn("context-travel", path.read_text().lower())
        for root in SKILL_ROOTS:
            card = (root / "SKILL.md").read_text().lower()
            self.assertTrue(any(word in card for word in ("optional", "on demand")))
            self.assertIn("verification", card)
            self.assertTrue("authority" in card or "authoritative" in card)

    def test_package_discovery_and_no_clobber_use_fixture_homes_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            codex_home = base / "codex-home"
            copilot_home = base / "copilot-home"
            inventory = selector._source_inventory(ROOT, codex_home, ("skills",), "user")
            self.assertIn(
                ("skills", SKILL_ROOTS[1] / "SKILL.md",
                 codex_home / "skills" / "context-travel" / "SKILL.md"), inventory)
            first = selector.install_codex(codex_home, repo_root=ROOT)
            self.assertIn((codex_home / "skills" / "context-travel", "install"), first)
            self.assertIn((codex_home / "skills" / "context-travel", "up-to-date"),
                          selector.install_codex(codex_home, repo_root=ROOT))
            codex_card = codex_home / "skills" / "context-travel" / "SKILL.md"
            codex_card.write_text("user-owned fixture\n")
            self.assertIn((codex_card.parent, "skip-differs"),
                          selector.install_codex(codex_home, repo_root=ROOT))
            self.assertEqual(codex_card.read_text(), "user-owned fixture\n")

            copilot_card = copilot_home / "skills" / "context-travel" / "SKILL.md"
            first = selector.install_copilot(copilot_home, repo_root=ROOT)
            self.assertIn(copilot_card, first)
            self.assertTrue(copilot_card.is_file())
            self.assertIn("{{POLYTROPOS_ROOT}}", (SKILL_ROOTS[2] / "SKILL.md").read_text())
            self.assertNotIn("{{POLYTROPOS_ROOT}}", copilot_card.read_text())
            second = selector.install_copilot(copilot_home, repo_root=ROOT)
            self.assertFalse(second.conflicts)
            copilot_card.write_text("user-owned fixture\n")
            third = selector.install_copilot(copilot_home, repo_root=ROOT)
            self.assertTrue(any(Path(action["destination"]) == copilot_card
                                for action in third.conflicts))
            self.assertEqual(copilot_card.read_text(), "user-owned fixture\n")

    def test_context_skill_write_rolls_back_in_fixture_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "copilot-home"
            plan = selector.plan_copilot_install(home, repo_root=ROOT)
            writable = [action for action in plan["actions"]
                        if action["state"] in selector.COPILOT_WRITE_STATES]
            skill = home / "skills" / "context-travel" / "SKILL.md"
            stop = next(index for index, action in enumerate(writable, 1)
                        if Path(action["destination"]) == skill)
            with self.assertRaisesRegex(RuntimeError, "simulated copilot install failure"):
                selector.apply_copilot_plan(plan, fail_after=stop)
            self.assertFalse(skill.exists())
            self.assertFalse((home / selector.COPILOT_OWNERSHIP_RELATIVE).exists())


class SharedHandoffTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        kit = self.root / "tasks" / "kits" / "fixture"
        kit.mkdir(parents=True)
        (kit / "TASKS.md").write_text(
            "### T1 — Fixture handoff\n- status: pending\n\n"
            "**Brief.** Carry this synthetic context.\n\n"
            "**Acceptance.** Criterion one stays intact.\n")
        self.kit_path = "tasks/kits/fixture"
        self.config_path = self.root / "query-config.json"
        self.config_path.write_text(json.dumps({
            "v": "polytropos.context-query-config/1",
            "repositories": [{"id": "repo-a", "root": str(self.root),
                              "kits": [{"path": self.kit_path, "kit_files": ["TASKS.md"],
                                        "graph_path": None, "evidence": None}]}],
            "deny_prefixes": [],
            "limits": {"max_sources": 2, "max_source_bytes": 4096,
                       "max_total_bytes": 8192, "max_items": 16},
            "max_output_bytes": 32768,
        }))
        self.assignment = {"repository_id": "repo-a", "checkout_id": "checkout-a",
                           "revision": None, "kit_path": self.kit_path,
                           "task_id": "T1", "assignment_id": "handoff-a",
                           "assignment_role": "implementer", "question": "What is next?"}

    def _process(self, script, input_text, extra=()):
        env = {"HOME": str(self.root / "fixture-home"),
               "POLYTROPOS_DATA_HOME": str(self.root / "fixture-data"),
               "TMPDIR": str(self.root / "fixture-tmp"),
               "PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
        return proc.run(
            [sys.executable, "-B", str(BIN / script),
             "--config", str(self.config_path), *extra],
            cwd=self.root, within=self.root, env=env, timeout=5, output_limit=65536,
            input_text=input_text, text=False)

    def test_cli_and_mcp_handoff_carry_same_core_payload(self):
        supplied = query.run_query(query.load_config(str(self.config_path)),
                                   "overview", {"assignment": self.assignment})
        arguments = {"view": supplied["data"]}
        (self.root / self.kit_path / "TASKS.md").unlink()
        cli_result = self._process("context_travel_cli.py", json.dumps(arguments) + "\n",
                                   ("brief", "--format", "json"))
        self.assertEqual(cli_result["outcome"], proc.OUTCOME_OK, cli_result["stderr"])
        self.assertEqual(cli_result["rc"], 0)
        cli_payload = json.loads(cli_result["stdout"])
        frames = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-11-25", "capabilities": {},
                "clientInfo": {"name": "fixture", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "brief", "arguments": arguments}},
        ]
        mcp_result = self._process("context_travel_mcp.py",
                                   "".join(json.dumps(frame) + "\n" for frame in frames))
        self.assertEqual(mcp_result["outcome"], proc.OUTCOME_OK, mcp_result["stderr"])
        self.assertEqual(mcp_result["rc"], 0)
        replies = [json.loads(line) for line in mcp_result["stdout"].splitlines()]
        response = next(item for item in replies if item.get("id") == 2)
        self.assertNotIn("error", response)
        mcp_payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(cli_payload, mcp_payload)
        self.assertEqual(cli_payload["data"], supplied["data"])
        self.assertIn("Criterion one stays intact.", json.dumps(cli_payload))
        self.assertFalse((self.root / "fixture-home").exists())

    def test_documented_config_assignment_and_command_execute_in_fixture(self):
        guide = (ROOT / "docs" / "CONTEXT-TRAVEL-SURFACES.md").read_text()
        examples = re.findall(r"```json\n(.*?)\n```", guide, re.DOTALL)
        self.assertGreaterEqual(len(examples), 2)
        config, arguments = (json.loads(examples[0]), json.loads(examples[1]))
        command = re.search(r"```sh\n([^\n]+)\n```", guide)
        self.assertIsNotNone(command)
        tokens = shlex.split(command.group(1))
        self.assertEqual(tokens[0], "python3")
        self.assertTrue(tokens[1].endswith("/bin/context_travel_cli.py"))
        self.assertIn("--config", tokens)
        self.assertIn("brief", tokens)
        self.assertIn("<", tokens)
        self.assertIn(">", tokens)
        kit_path = arguments["assignment"]["kit_path"]
        target = self.root / kit_path / "TASKS.md"
        target.parent.mkdir(parents=True)
        target.write_text((self.root / self.kit_path / "TASKS.md").read_text())
        config["repositories"][0]["root"] = str(self.root)
        self.config_path.write_text(json.dumps(config))
        result = self._process("context_travel_cli.py", json.dumps(arguments) + "\n",
                               ("brief", "--format", "json"))
        self.assertEqual(result["rc"], 0, result["stderr"])
        self.assertIn("Criterion one stays intact.", result["stdout"].decode())

    def test_imported_view_survives_removed_source_but_not_applicability_check(self):
        config = json.loads(self.config_path.read_text())
        config["repositories"][0]["kits"][0]["graph_path"] = "missing-graph.json"
        self.config_path.write_text(json.dumps(config))
        old = dict(self.assignment, checkout_id="checkout-old", revision="rev-old")
        supplied = query.run_query(query.load_config(str(self.config_path)),
                                   "overview", {"assignment": old})["data"]
        self.assertTrue(supplied["limitations"])
        source = self.root / self.kit_path / "TASKS.md"
        source.unlink()
        result = self._process("context_travel_cli.py",
                               json.dumps({"view": supplied}) + "\n",
                               ("brief", "--format", "json"))
        self.assertEqual(result["rc"], 0, result["stderr"])
        imported = json.loads(result["stdout"])["data"]
        self.assertEqual(imported, supplied)
        self.assertIn("Criterion one stays intact.", json.dumps(imported))
        self.assertEqual(imported["limitations"], supplied["limitations"])
        self.assertEqual(imported["subject"]["checkout_id"], "checkout-old")
        guide = (ROOT / "docs" / "CONTEXT-TRAVEL-SURFACES.md").read_text().lower()
        for field in ("checkout_id", "revision", "source_state_ref", "assignment_role"):
            self.assertIn(field, guide)
        self.assertIn("does **not** automatically compare", guide)
        self.assertIn("establish freshness", guide)

    def test_imported_view_rejects_tampering_and_valid_unbound_subjects(self):
        baseline = json.loads(self.config_path.read_text())
        for repo_id, kit_path in (("repo-b", self.kit_path),
                                  ("repo-a", "tasks/kits/other")):
            with self.subTest(repo=repo_id, kit=kit_path):
                target = self.root / kit_path / "TASKS.md"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text((self.root / self.kit_path / "TASKS.md").read_text())
                wider = copy.deepcopy(baseline)
                added_kit = {
                    "path": kit_path, "kit_files": ["TASKS.md"],
                    "graph_path": None, "evidence": None,
                }
                if repo_id != "repo-a":
                    wider["repositories"].append({
                        "id": repo_id, "root": str(self.root), "kits": [added_kit],
                    })
                else:
                    wider["repositories"][0]["kits"].append(added_kit)
                self.config_path.write_text(json.dumps(wider))
                assignment = dict(self.assignment, repository_id=repo_id,
                                  kit_path=kit_path)
                valid = query.run_query(query.load_config(str(self.config_path)),
                                        "overview", {"assignment": assignment})["data"]
                self.config_path.write_text(json.dumps(baseline))
                refused = self._process("context_travel_cli.py",
                                        json.dumps({"view": valid}) + "\n",
                                        ("brief", "--format", "json"))
                self.assertNotEqual(refused["rc"], 0)
                self.assertEqual(refused["stdout"], b"")
        valid = query.run_query(query.load_config(str(self.config_path)),
                                "overview", {"assignment": self.assignment})["data"]
        tampered = copy.deepcopy(valid)
        tampered["brief"]["criteria_text"] = "fabricated criterion"
        refused = self._process("context_travel_cli.py",
                                json.dumps({"view": tampered}) + "\n",
                                ("brief", "--format", "json"))
        self.assertNotEqual(refused["rc"], 0)
        self.assertEqual(refused["stdout"], b"")

    def test_unbound_repository_and_kit_cannot_cross_handoff(self):
        for change in ({"repository_id": "repo-b"}, {"kit_path": "tasks/kits/other"}):
            with self.subTest(change=change):
                assignment = dict(self.assignment, **change)
                result = self._process("context_travel_cli.py",
                                       json.dumps({"assignment": assignment}) + "\n",
                                       ("brief", "--format", "json"))
                self.assertNotEqual(result["rc"], 0)
                self.assertNotIn(str(self.root).encode(), result["stdout"] + result["stderr"])

    def test_missing_config_fails_closed_even_with_valid_assignment(self):
        missing = self.root / "missing.json"
        self.config_path = missing
        result = self._process("context_travel_cli.py",
                               json.dumps({"assignment": self.assignment}) + "\n",
                               ("brief", "--format", "json"))
        self.assertNotEqual(result["rc"], 0)
        self.assertEqual(result["stdout"], b"")
        self.assertNotIn(str(self.root).encode(), result["stderr"])


if __name__ == "__main__":
    unittest.main()
