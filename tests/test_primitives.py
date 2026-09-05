"""Tests for bin/primitives.py (PLAN.md D2-D6, aesop-fold kit T4).

Golden fixtures under tests/fixtures/primitives/ are TOML translations of aesop's own
three golden compile fixtures (minimal, full, token-lean) plus aesop's own aesop.yaml —
all four must validate clean. Adversarial fixtures are BASE_TOML (a small, complete, valid
manifest) with exactly one field mutated per test, each asserting the exact finding set the
mutation should trip and nothing else.
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = REPO_ROOT / "bin"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "primitives"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


primitives = _load("primitives")

BASE_TOML = """\
version = 1
harnesses = ["claude-code", "codex"]
registries = ["builtin"]

[project]
name = "sample-app"
stack = ["typescript", "node20"]
review_bandwidth = 2

[project.commands]
test = "npm test"
build = "npm run build"
lint = "npm run lint"

[project.models.primary]
family = "claude"
tier = "strong"

[project.models.judge]
family = "openai"
tier = "strong"

[pathway]
profile = "balanced"

[primitives]
skills = ["verify-loop"]
agents = ["explorer", { name = "security-reviewer", model = "strong", effort = "xhigh" }]
commands = ["commit-pr"]
hooks = ["block-dangerous-commands"]
mcp = [{ name = "github", transport = "stdio", command = "npx -y @modelcontextprotocol/server-github", env = ["GITHUB_TOKEN"], scopes = ["repo:read"], trust = "write" }]
loops = [{ name = "green-tests", goal = "all tests pass", verify = "npm test", plan_gate = true, stops = { max_iterations = 40, no_progress_after = 3, budget_usd = 25 } }]

[primitives.instructions]
template = "builtin:AGENTS.template"

[[primitives.instructions.blocks]]
scope = "project"
content = "Domain rule text."

[primitives.permissions]
mutate_allow = ["git commit *"]
irreversible = ["git push origin main"]
unattended = "none"

[state]
dir = "tasks/"
"""


def _run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = primitives.main(argv)
    return code, out.getvalue(), err.getvalue()


def _codes(findings):
    return sorted(f["code"] for f in findings)


class LoaderTests(unittest.TestCase):
    def test_load_schema_default(self):
        schema = primitives.load_schema()
        self.assertEqual(schema["title"], "Aesop manifest (aesop.yaml)")

    def test_load_model_default(self):
        model = primitives.load_model()
        self.assertEqual(len(model["primitives"]), 9)

    def test_load_matrix_default(self):
        matrix = primitives.load_matrix()
        self.assertIn("cursor", matrix["harnesses"])

    def test_load_manifest_missing_file_raises_manifest_error(self):
        with self.assertRaises(primitives.ManifestError) as cm:
            primitives.load_manifest("/definitely/does/not/exist/aesop.toml")
        self.assertIn("manifest not found:", str(cm.exception))

    def test_load_manifest_malformed_toml_message_contains_tomllib_text(self):
        bad = "version = [1, \n"
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
        try:
            tmp.write(bad)
            tmp.close()
            with self.assertRaises(primitives.ManifestError) as cm:
                primitives.load_manifest(tmp.name)
            try:
                tomllib.loads(bad)
                self.fail("expected malformed TOML to fail parsing")
            except tomllib.TOMLDecodeError as e:
                self.assertIn(str(e), str(cm.exception))
        finally:
            os.unlink(tmp.name)

    def test_load_manifest_parses_valid_toml(self):
        manifest = primitives.load_manifest(FIXTURES_DIR / "minimal.toml")
        self.assertEqual(manifest["project"]["name"], "minimal-app")


class GoldenFixtureTests(unittest.TestCase):
    """Every golden fixture must validate with zero findings."""

    def _assert_clean(self, name):
        path = FIXTURES_DIR / name
        raw_text = path.read_text(encoding="utf-8")
        manifest = tomllib.loads(raw_text)
        schema = primitives.load_schema()
        findings = primitives.validate(manifest, raw_text, schema)
        self.assertEqual(findings, [], f"{name} should validate clean, got: {findings}")

    def test_minimal(self):
        self._assert_clean("minimal.toml")

    def test_full(self):
        self._assert_clean("full.toml")

    def test_token_lean(self):
        self._assert_clean("token_lean.toml")

    def test_aesop_self(self):
        self._assert_clean("aesop_self.toml")

    def test_base_toml_control_is_clean(self):
        """BASE_TOML (below) is the control fixture every adversarial test mutates by exactly
        one field; it must itself be valid so a failing adversarial test means the mutation
        tripped the rule, not that the base was already broken."""
        manifest = tomllib.loads(BASE_TOML)
        schema = primitives.load_schema()
        findings = primitives.validate(manifest, BASE_TOML, schema)
        self.assertEqual(findings, [])


class AdversarialSchemaTests(unittest.TestCase):
    """Each test mutates exactly one field of BASE_TOML and asserts the resulting finding
    set — proving the fixture trips ONLY the rule under test."""

    def _findings(self, mutated_text):
        manifest = tomllib.loads(mutated_text)
        schema = primitives.load_schema()
        return primitives.validate(manifest, mutated_text, schema)

    def test_version_missing(self):
        mutated = BASE_TOML.replace('version = 1\n', '')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema", "schema"])
        self.assertTrue(all(f["at"] == "version" for f in findings))

    def test_version_not_one(self):
        mutated = BASE_TOML.replace('version = 1\n', 'version = 2\n')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "version")

    def test_harnesses_missing(self):
        mutated = BASE_TOML.replace('harnesses = ["claude-code", "codex"]\n', '')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "harnesses")

    def test_harnesses_empty(self):
        mutated = BASE_TOML.replace('harnesses = ["claude-code", "codex"]\n', 'harnesses = []\n')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "harnesses")

    def test_harnesses_unknown_id(self):
        mutated = BASE_TOML.replace('harnesses = ["claude-code", "codex"]\n', 'harnesses = ["claude-code", "nope"]\n')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "harnesses[1]")

    def test_unknown_top_level_key(self):
        mutated = BASE_TOML.replace('version = 1\n', 'version = 1\nweird_extra = "x"\n')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "weird_extra")

    def test_unknown_key_under_primitives(self):
        mutated = BASE_TOML.replace(
            'hooks = ["block-dangerous-commands"]\n',
            'hooks = ["block-dangerous-commands"]\nbogus_extra = "nope"\n',
        )
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "primitives.bogus_extra")

    def test_project_name_empty(self):
        mutated = BASE_TOML.replace('name = "sample-app"\n', 'name = "   "\n')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "project.name")

    def test_project_commands_test_empty(self):
        mutated = BASE_TOML.replace('test = "npm test"\n', 'test = ""\n')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "project.commands.test")

    def test_pathway_profile_missing(self):
        mutated = BASE_TOML.replace('profile = "balanced"\n', '')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "pathway.profile")

    def test_registries_bad_pattern(self):
        mutated = BASE_TOML.replace('registries = ["builtin"]\n', 'registries = ["bad pattern here"]\n')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "registries[0]")

    def test_instructions_block_scope_bad_pattern(self):
        mutated = BASE_TOML.replace('scope = "project"\n', 'scope = "not-a-valid-scope"\n')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "primitives.instructions.blocks[0].scope")

    def test_instructions_block_content_not_string(self):
        mutated = BASE_TOML.replace('content = "Domain rule text."\n', 'content = 123\n')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "primitives.instructions.blocks[0].content")

    def test_skill_ref_bad_pattern(self):
        mutated = BASE_TOML.replace('skills = ["verify-loop"]\n', 'skills = ["Bad_Name"]\n')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "primitives.skills[0]")

    def test_command_ref_table_without_name(self):
        mutated = BASE_TOML.replace('commands = ["commit-pr"]\n', 'commands = [{ from = "somewhere" }]\n')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "primitives.commands[0].name")

    def test_agent_bad_model_enum(self):
        mutated = BASE_TOML.replace('model = "strong"', 'model = "bogus"')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "primitives.agents[1].model")

    def test_agent_bad_effort_enum(self):
        mutated = BASE_TOML.replace('effort = "xhigh"', 'effort = "bogus"')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "primitives.agents[1].effort")

    def test_mcp_missing_name(self):
        mutated = BASE_TOML.replace(
            'mcp = [{ name = "github", transport = "stdio", command = "npx -y @modelcontextprotocol/server-github", env = ["GITHUB_TOKEN"], scopes = ["repo:read"], trust = "write" }]\n',
            'mcp = [{ transport = "stdio", command = "npx -y @modelcontextprotocol/server-github", env = ["GITHUB_TOKEN"], scopes = ["repo:read"], trust = "write" }]\n',
        )
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "primitives.mcp[0].name")

    def test_mcp_missing_transport(self):
        mutated = BASE_TOML.replace(
            'mcp = [{ name = "github", transport = "stdio", command = "npx -y @modelcontextprotocol/server-github", env = ["GITHUB_TOKEN"], scopes = ["repo:read"], trust = "write" }]\n',
            'mcp = [{ name = "github", command = "npx -y @modelcontextprotocol/server-github", env = ["GITHUB_TOKEN"], scopes = ["repo:read"], trust = "write" }]\n',
        )
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "primitives.mcp[0].transport")

    def test_mcp_bad_transport_enum(self):
        mutated = BASE_TOML.replace('transport = "stdio"', 'transport = "carrier-pigeon"')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "primitives.mcp[0].transport")

    def test_mcp_bad_trust_enum(self):
        mutated = BASE_TOML.replace('trust = "write"', 'trust = "bogus"')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "primitives.mcp[0].trust")

    def test_permissions_unattended_bad_enum(self):
        mutated = BASE_TOML.replace('unattended = "none"\n', 'unattended = "bogus"\n')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "primitives.permissions.unattended")

    def test_review_bandwidth_not_positive_int(self):
        mutated = BASE_TOML.replace('review_bandwidth = 2\n', 'review_bandwidth = 0\n')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "project.review_bandwidth")

    def test_state_dir_not_string(self):
        mutated = BASE_TOML.replace('dir = "tasks/"\n', 'dir = 5\n')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["schema"])
        self.assertEqual(findings[0]["at"], "state.dir")

    def test_enums_are_read_from_schema_not_retyped(self):
        """Copy the vendored schema to a temp dir, remove 'cursor' from the harness enum,
        reload it via load_schema(path=...), and confirm a manifest declaring cursor now
        yields a schema finding — proving the enum is read at call time, not retyped."""
        tmp_dir = tempfile.mkdtemp()
        try:
            schema = primitives.load_schema()
            mutated_schema = json.loads(json.dumps(schema))
            enum = mutated_schema["properties"]["harnesses"]["items"]["enum"]
            enum.remove("cursor")
            tmp_schema_path = Path(tmp_dir) / "aesop.schema.v1.json"
            tmp_schema_path.write_text(json.dumps(mutated_schema), encoding="utf-8")
            reloaded = primitives.load_schema(tmp_schema_path)

            manifest_text = BASE_TOML.replace(
                'harnesses = ["claude-code", "codex"]\n',
                'harnesses = ["claude-code", "cursor"]\n',
            )
            manifest = tomllib.loads(manifest_text)
            findings = primitives.validate(manifest, manifest_text, reloaded)
            self.assertEqual(_codes(findings), ["schema"])
            self.assertEqual(findings[0]["at"], "harnesses[1]")
        finally:
            shutil.rmtree(tmp_dir)


class AdversarialOtherRuleTests(unittest.TestCase):
    def _findings(self, mutated_text):
        manifest = tomllib.loads(mutated_text)
        schema = primitives.load_schema()
        return primitives.validate(manifest, mutated_text, schema)

    def test_stops_missing_entirely(self):
        mutated = BASE_TOML.replace(
            'loops = [{ name = "green-tests", goal = "all tests pass", verify = "npm test", plan_gate = true, stops = { max_iterations = 40, no_progress_after = 3, budget_usd = 25 } }]\n',
            'loops = [{ name = "green-tests", goal = "all tests pass", verify = "npm test", plan_gate = true }]\n',
        )
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["stops"])
        self.assertEqual(findings[0]["at"], "primitives.loops[0].stops")
        self.assertIn("all three hard stops are required", findings[0]["message"])

    def test_stops_missing_one_field(self):
        mutated = BASE_TOML.replace(
            'stops = { max_iterations = 40, no_progress_after = 3, budget_usd = 25 }',
            'stops = { max_iterations = 40, no_progress_after = 3 }',
        )
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["stops"])
        self.assertEqual(findings[0]["at"], "primitives.loops[0].stops.budget_usd")
        self.assertIn("all three hard stops are required", findings[0]["message"])

    def test_stops_max_iterations_invalid(self):
        mutated = BASE_TOML.replace("max_iterations = 40", "max_iterations = 0")
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["stops"])
        self.assertEqual(findings[0]["at"], "primitives.loops[0].stops.max_iterations")

    def test_stops_budget_usd_invalid(self):
        mutated = BASE_TOML.replace("budget_usd = 25", "budget_usd = -5")
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["stops"])
        self.assertEqual(findings[0]["at"], "primitives.loops[0].stops.budget_usd")

    def test_verify_loop_placeholder_test_command(self):
        mutated = BASE_TOML.replace('test = "npm test"\n', 'test = "TODO: set your test command"\n')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["verify-loop"])
        self.assertEqual(findings[0]["at"], "project.commands.test")

    def test_verify_loop_empty_loop_verify(self):
        mutated = BASE_TOML.replace('verify = "npm test"', 'verify = ""')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["verify-loop"])
        self.assertEqual(findings[0]["at"], "primitives.loops[0].verify")

    def test_judge_family_same_as_primary(self):
        mutated = BASE_TOML.replace('family = "openai"\n', 'family = "claude"\n')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["judge-family"])
        self.assertEqual(findings[0]["at"], "project.models.judge.family")

    def test_env_value_not_a_bare_name(self):
        mutated = BASE_TOML.replace('env = ["GITHUB_TOKEN"]', 'env = ["${GITHUB_TOKEN}"]')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["env-value"])
        self.assertEqual(findings[0]["at"], "primitives.mcp[0].env[0]")

    def test_unsafe_name_project_name(self):
        mutated = BASE_TOML.replace('name = "sample-app"\n', 'name = "sample/app"\n')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["unsafe-name"])
        self.assertEqual(findings[0]["at"], "project.name")

    def test_unsafe_name_mcp_name(self):
        mutated = BASE_TOML.replace('name = "github"', 'name = "gh/ub"')
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["unsafe-name"])
        self.assertEqual(findings[0]["at"], "primitives.mcp[0].name")

    def test_secret_github_token(self):
        mutated = BASE_TOML.replace(
            'content = "Domain rule text."\n',
            'content = "token ghp_ABCDEFGHIJ0123456789ABCD leaked here"\n',
        )
        findings = self._findings(mutated)
        self.assertEqual(_codes(findings), ["secret"])
        self.assertTrue(findings[0]["at"].startswith("line "))


class CliTests(unittest.TestCase):
    def test_check_exit_0_clean_manifest(self):
        code, out, err = _run_cli(["check", str(FIXTURES_DIR / "minimal.toml")])
        self.assertEqual(code, 0)
        self.assertIn("ok:", out)
        self.assertEqual(err, "")

    def test_check_exit_2_with_findings(self):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
        try:
            tmp.write(BASE_TOML.replace('version = 1\n', 'version = 2\n'))
            tmp.close()
            code, out, err = _run_cli(["check", tmp.name])
            self.assertEqual(code, 2)
            self.assertIn("schema", out)
            self.assertIn("1 finding", out)
        finally:
            os.unlink(tmp.name)

    def test_check_exit_1_missing_file(self):
        code, out, err = _run_cli(["check", "/definitely/does/not/exist/aesop.toml"])
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("error:"))
        self.assertEqual(out, "")

    def test_check_exit_1_malformed_toml(self):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
        try:
            tmp.write("version = [1, \n")
            tmp.close()
            code, out, err = _run_cli(["check", tmp.name])
            self.assertEqual(code, 1)
            self.assertTrue(err.startswith("error:"))
        finally:
            os.unlink(tmp.name)

    def test_check_json_output_has_exactly_three_keys(self):
        code, out, err = _run_cli(["check", str(FIXTURES_DIR / "minimal.toml"), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(set(payload.keys()), {"manifest", "ok", "findings"})
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["manifest"], str(FIXTURES_DIR / "minimal.toml"))

    def test_check_json_output_with_findings(self):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
        try:
            tmp.write(BASE_TOML.replace('version = 1\n', 'version = 2\n'))
            tmp.close()
            code, out, err = _run_cli(["check", tmp.name, "--json"])
            self.assertEqual(code, 2)
            payload = json.loads(out)
            self.assertEqual(set(payload.keys()), {"manifest", "ok", "findings"})
            self.assertFalse(payload["ok"])
            self.assertEqual(len(payload["findings"]), 1)
            self.assertEqual(set(payload["findings"][0].keys()), {"code", "message", "at"})
        finally:
            os.unlink(tmp.name)

    def test_model_command_exit_0(self):
        code, out, err = _run_cli(["model"])
        self.assertEqual(code, 0)
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(lines), 9)

    def test_model_json_output(self):
        code, out, err = _run_cli(["model", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(len(payload["primitives"]), 9)

    def test_matrix_harness_cursor_lists_all_nine_primitives(self):
        code, out, err = _run_cli(["matrix", "--harness", "cursor"])
        self.assertEqual(code, 0)
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertGreaterEqual(len(lines), 9)
        primitive_ids = {l.split()[0] for l in lines}
        expected = {"instructions", "skill", "agent", "command", "mcp", "hook", "permissions", "loop", "state"}
        self.assertEqual(primitive_ids, expected)

    def test_matrix_unknown_harness_exits_2(self):
        code, out, err = _run_cli(["matrix", "--harness", "nope"])
        self.assertEqual(code, 2)
        self.assertIn("nope", err)
        self.assertIn("claude-code", err)

    def test_matrix_json_output(self):
        code, out, err = _run_cli(["matrix", "--harness", "cursor", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertIn("cursor", payload)

    def test_main_no_command_exits_1(self):
        code, out, err = _run_cli([])
        self.assertEqual(code, 1)

    def test_main_bad_subcommand_exits_1(self):
        code, out, err = _run_cli(["bogus-command"])
        self.assertEqual(code, 1)


class PlanTests(unittest.TestCase):
    """T5: plan() is pure (manifest dict, matrix dict, harnesses) -> {"harnesses": {...}}."""

    def test_full_fixture_cursor_native_vs_fallback(self):
        manifest = tomllib.loads((FIXTURES_DIR / "full.toml").read_text(encoding="utf-8"))
        matrix = primitives.load_matrix()
        result = primitives.plan(manifest, matrix, ["cursor"])
        self.assertEqual(set(result["harnesses"]), {"cursor"})
        cursor = result["harnesses"]["cursor"]
        self.assertEqual(cursor["goal_mode"], "ralph")
        self.assertEqual(len(cursor["primitives"]), 9)
        by_id = {p["id"]: p for p in cursor["primitives"]}
        for pid in ("skill", "agent", "command", "hook", "permissions", "loop"):
            self.assertEqual(by_id[pid]["support"], "fallback", pid)
            self.assertTrue(by_id[pid]["declared"], pid)
        for pid in ("mcp", "instructions", "state"):
            self.assertEqual(by_id[pid]["support"], "native", pid)
        # full.toml declares every primitive at least once.
        self.assertTrue(all(p["declared"] for p in cursor["primitives"]))

    def test_minimal_fixture_defaults_to_declared_harnesses(self):
        manifest = tomllib.loads((FIXTURES_DIR / "minimal.toml").read_text(encoding="utf-8"))
        matrix = primitives.load_matrix()
        result = primitives.plan(manifest, matrix, None)
        self.assertEqual(set(result["harnesses"]), {"claude-code"})
        by_id = {p["id"]: p for p in result["harnesses"]["claude-code"]["primitives"]}
        self.assertFalse(by_id["mcp"]["declared"])

    def test_cursor_works_on_a_manifest_that_does_not_declare_it(self):
        """PLAN D7: Cursor-ready, not Cursor-built — plan --harness cursor must work even
        when the manifest only declares copilot."""
        manifest = tomllib.loads((FIXTURES_DIR / "minimal.toml").read_text(encoding="utf-8"))
        self.assertNotIn("cursor", manifest["harnesses"])
        matrix = primitives.load_matrix()
        result = primitives.plan(manifest, matrix, ["cursor"])
        self.assertEqual(set(result["harnesses"]), {"cursor"})

    def test_cli_invalid_manifest_exits_2_with_no_plan_output(self):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
        try:
            tmp.write(BASE_TOML.replace('version = 1\n', 'version = 2\n'))
            tmp.close()
            code, out, err = _run_cli(["plan", tmp.name])
            self.assertEqual(code, 2)
            self.assertIn("schema", out)
            self.assertNotIn("goal mode", out)
        finally:
            os.unlink(tmp.name)

    def test_cli_invalid_manifest_json_matches_check_failure_shape(self):
        """T5b: plan --json on an invalid manifest must stay JSON-shaped, key-for-key
        identical to check --json's failure object, instead of falling back to plain text."""
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
        try:
            tmp.write(BASE_TOML.replace('version = 1\n', 'version = 2\n'))
            tmp.close()
            code, out, err = _run_cli(["plan", tmp.name, "--json"])
            self.assertEqual(code, 2)
            payload = json.loads(out)
            self.assertEqual(set(payload.keys()), {"manifest", "ok", "findings"})
            self.assertIs(payload["ok"], False)
            self.assertTrue(payload["findings"])
        finally:
            os.unlink(tmp.name)

    def test_cli_full_cursor_json_shape(self):
        code, out, err = _run_cli(["plan", str(FIXTURES_DIR / "full.toml"), "--harness", "cursor", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(set(payload.keys()), {"manifest", "harnesses"})
        self.assertEqual(payload["manifest"], str(FIXTURES_DIR / "full.toml"))
        self.assertEqual(set(payload["harnesses"]), {"cursor"})

    def test_cli_text_output_has_header_and_nine_rows(self):
        code, out, err = _run_cli(["plan", str(FIXTURES_DIR / "full.toml"), "--harness", "cursor"])
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(lines[0], "## cursor  (goal mode: ralph)")
        self.assertEqual(len(lines), 10)

    def test_cli_unknown_harness_exits_2(self):
        code, out, err = _run_cli(["plan", str(FIXTURES_DIR / "minimal.toml"), "--harness", "nope"])
        self.assertEqual(code, 2)
        self.assertIn("claude-code", err)

    def test_cli_missing_manifest_exits_1(self):
        code, out, err = _run_cli(["plan", "/definitely/does/not/exist/aesop.toml"])
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("error:"))


def _reference_markdown_table(matrix):
    """A SECOND, independently written renderer of the same markdown table, built directly
    from the matrix JSON without calling primitives.render_matrix_markdown, so a bug shared
    by both implementations cannot pass this test (T5 orchestrator note)."""
    columns = list(matrix["harnesses"].keys())
    header_row = ["Primitive"]
    header_row.extend(columns)
    divider_row = ["---" for _ in header_row]
    table_lines = ["| " + " | ".join(header_row) + " |", "| " + " | ".join(divider_row) + " |"]
    for primitive_id in matrix["primitives"]:
        row = [primitive_id]
        for harness_id in columns:
            row.append(matrix["harnesses"][harness_id]["cells"][primitive_id]["support"])
        table_lines.append("| " + " | ".join(row) + " |")
    modes = []
    for harness_id in columns:
        modes.append(harness_id + "=" + matrix["harnesses"][harness_id]["goal_mode"])
    table_lines.append("")
    table_lines.append("Goal modes: " + " · ".join(modes))
    return "\n".join(table_lines)


class MarkdownMatrixTests(unittest.TestCase):
    def test_matches_an_independently_written_renderer(self):
        matrix = primitives.load_matrix()
        self.assertEqual(primitives.render_matrix_markdown(matrix), _reference_markdown_table(matrix))

    def test_pure_function_is_byte_stable(self):
        matrix = primitives.load_matrix()
        self.assertEqual(primitives.render_matrix_markdown(matrix), primitives.render_matrix_markdown(matrix))

    def test_no_carriage_returns(self):
        matrix = primitives.load_matrix()
        self.assertNotIn("\r", primitives.render_matrix_markdown(matrix))

    def test_cli_markdown_output_nine_rows_plus_header_and_divider(self):
        code, out, err = _run_cli(["matrix", "--markdown"])
        self.assertEqual(code, 0)
        pipe_lines = [l for l in out.splitlines() if l.startswith("| ")]
        self.assertEqual(len(pipe_lines), 11)
        self.assertTrue(out.endswith("\n") and not out.endswith("\n\n"))

    def test_cli_markdown_byte_stable_across_two_runs(self):
        code1, out1, _ = _run_cli(["matrix", "--markdown"])
        code2, out2, _ = _run_cli(["matrix", "--markdown"])
        self.assertEqual(code1, 0)
        self.assertEqual(code2, 0)
        self.assertEqual(out1, out2)

    def test_cli_markdown_with_harness_exits_1(self):
        code, out, err = _run_cli(["matrix", "--markdown", "--harness", "cursor"])
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("error:"))


class SourceIntrospectionTests(unittest.TestCase):
    """Static source audit: the engine must be offline, deterministic, and read-only —
    keep the forbidden literal names out of comments and docstrings too."""

    def test_source_has_no_nondeterministic_or_dispatch_calls(self):
        src = (BIN_DIR / "primitives.py").read_text(encoding="utf-8")
        forbidden = ["Path.home", "subprocess", "urlopen", "random.", "time.time", "date.today"]
        for token in forbidden:
            self.assertNotIn(token, src, f"forbidden token {token!r} found in primitives.py")

    def test_source_has_no_import_error_fallback(self):
        src = (BIN_DIR / "primitives.py").read_text(encoding="utf-8")
        self.assertNotIn("except ImportError", src)

    def test_module_line_count_is_reasonable(self):
        src = (BIN_DIR / "primitives.py").read_text(encoding="utf-8")
        line_count = len(src.splitlines())
        self.assertLess(line_count, 700, f"primitives.py has grown to {line_count} lines")


if __name__ == "__main__":
    unittest.main()
