"""Structural tests for primitives/*.json (PLAN.md D1/D5/D7, aesop-fold kit T3).

primitives/model.json and primitives/harness-matrix.json are the nine-primitive model and
the per-harness support table, transcribed from aesop (commit
9c4108ee8ca32fe7f7420a94b15b072c92a6ccf8) as data. primitives/aesop.schema.v1.json is a
byte-identical, LOCKED vendored copy of aesop's manifest schema — its enums are the source
of truth for the model's enum tokens, and its sha256 is pinned so nobody edits it by accident.
"""

import hashlib
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIMITIVES_DIR = REPO_ROOT / "primitives"
MODEL_PATH = PRIMITIVES_DIR / "model.json"
MATRIX_PATH = PRIMITIVES_DIR / "harness-matrix.json"
SCHEMA_PATH = PRIMITIVES_DIR / "aesop.schema.v1.json"

# Pinned in PLAN.md and the T3 brief — byte-identical to aesop schemas/aesop.schema.json
# at commit 9c4108ee8ca32fe7f7420a94b15b072c92a6ccf8. Never refresh silently.
SCHEMA_SHA256 = "a8b5ce94dda62c547728fea03335b22bb877c70426b1ce2eee9cce23f62b2f4f"

PRIMITIVE_IDS = [
    "instructions",
    "skill",
    "agent",
    "command",
    "mcp",
    "hook",
    "permissions",
    "loop",
    "state",
]

# The cell-for-cell pin, transcribed from aesop's emitter capabilities() bodies
# (src/emitters/*.ts), re-verified against the source at T3 execution time.
EXPECTED_CAPABILITIES = {
    "claude-code": {
        "goal_mode": "native",
        "native": {"instructions", "skill", "agent", "command", "mcp", "hook", "permissions", "loop", "state"},
        "fallback": set(),
    },
    "codex": {
        "goal_mode": "native",
        "native": {"instructions", "skill", "agent", "command", "mcp", "permissions", "loop", "state"},
        "fallback": {"hook"},
    },
    "copilot": {
        "goal_mode": "ralph",
        "native": {"instructions", "skill", "agent", "command", "mcp", "state"},
        "fallback": {"hook", "permissions", "loop"},
    },
    "cursor": {
        "goal_mode": "ralph",
        "native": {"instructions", "mcp", "state"},
        "fallback": {"skill", "agent", "command", "hook", "permissions", "loop"},
    },
    "antigravity": {
        "goal_mode": "scheduled",
        "native": {"instructions", "skill", "state", "loop"},
        "fallback": {"agent", "command", "mcp", "hook", "permissions"},
    },
    "vscode": {
        "goal_mode": "ralph",
        "native": {"mcp", "state"},
        "fallback": {"instructions", "skill", "agent", "command", "hook", "permissions", "loop"},
    },
}


def load_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


class TestModelAndMatrixParse(unittest.TestCase):
    def test_model_parses_and_schema_string(self):
        model = load_json(MODEL_PATH)
        self.assertEqual(model["schema"], "polytropos-primitives/v1")

    def test_matrix_parses_and_schema_string(self):
        matrix = load_json(MATRIX_PATH)
        self.assertEqual(matrix["schema"], "polytropos-harness-matrix/v1")


class TestModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = load_json(MODEL_PATH)

    def test_primitive_ids_in_order(self):
        ids = [p["id"] for p in self.model["primitives"]]
        self.assertEqual(ids, PRIMITIVE_IDS)

    def test_order_field_is_1_through_9(self):
        orders = [p["order"] for p in self.model["primitives"]]
        self.assertEqual(orders, list(range(1, 10)))

    def test_every_primitive_has_required_shape(self):
        for p in self.model["primitives"]:
            with self.subTest(primitive=p.get("id")):
                self.assertTrue(p.get("title"), "title must be non-empty")
                self.assertTrue(p.get("manifest_key"), "manifest_key must be non-empty")
                self.assertIn(p.get("authored_as"), {"inline", "referenced"})
                self.assertTrue(p.get("semantics"), "semantics must be non-empty")
                fields = p.get("fields")
                self.assertIsInstance(fields, list)
                self.assertTrue(fields, "fields must be non-empty")
                for field in fields:
                    with self.subTest(field=field.get("name")):
                        self.assertIn("name", field)
                        self.assertIn("type", field)
                        self.assertIn("required", field)
                        self.assertIsInstance(field["required"], bool)


class TestMatrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = load_json(MATRIX_PATH)
        cls.schema = load_json(SCHEMA_PATH)

    def test_harness_ids_match_vendored_schema_enum(self):
        schema_harnesses = set(self.schema["properties"]["harnesses"]["items"]["enum"])
        matrix_harnesses = set(self.matrix["harnesses"].keys())
        self.assertEqual(matrix_harnesses, schema_harnesses)

    def test_every_harness_has_exactly_nine_cells(self):
        for harness, spec in self.matrix["harnesses"].items():
            with self.subTest(harness=harness):
                self.assertEqual(set(spec["cells"].keys()), set(PRIMITIVE_IDS))

    def test_every_support_value_is_valid(self):
        for harness, spec in self.matrix["harnesses"].items():
            for primitive, cell in spec["cells"].items():
                with self.subTest(harness=harness, primitive=primitive):
                    self.assertIn(cell["support"], self.matrix["support_values"])

    def test_every_goal_mode_is_valid(self):
        for harness, spec in self.matrix["harnesses"].items():
            with self.subTest(harness=harness):
                self.assertIn(spec["goal_mode"], self.matrix["goal_modes"])

    def test_every_target_is_a_list_of_relative_strings(self):
        for harness, spec in self.matrix["harnesses"].items():
            for primitive, cell in spec["cells"].items():
                with self.subTest(harness=harness, primitive=primitive):
                    target = cell["target"]
                    self.assertIsInstance(target, list)
                    for entry in target:
                        self.assertIsInstance(entry, str)
                        self.assertFalse(entry.startswith("/"), f"absolute path in target: {entry}")
                        self.assertFalse(entry.startswith("~"), f"home-relative path in target: {entry}")

    def test_capability_table_matches_aesop_emitters_cell_for_cell(self):
        for harness, expected in EXPECTED_CAPABILITIES.items():
            with self.subTest(harness=harness):
                spec = self.matrix["harnesses"][harness]
                self.assertEqual(spec["goal_mode"], expected["goal_mode"])
                cells = spec["cells"]
                native = {p for p, c in cells.items() if c["support"] == "native"}
                fallback = {p for p, c in cells.items() if c["support"] == "fallback"}
                self.assertEqual(native, expected["native"])
                self.assertEqual(fallback, expected["fallback"])

    def test_cursor_column_matches_aesop_cursor_emitter(self):
        # Named separately so a future edit to just this column is caught by name
        # (src/emitters/cursor.ts capabilities(): native instructions/mcp/state,
        # fallback skill/agent/command/hook/permissions/loop, goalMode "ralph").
        cursor = self.matrix["harnesses"]["cursor"]
        self.assertEqual(cursor["goal_mode"], "ralph")
        cells = cursor["cells"]
        self.assertEqual(cells["instructions"]["support"], "native")
        self.assertEqual(cells["mcp"]["support"], "native")
        self.assertEqual(cells["state"]["support"], "native")
        for primitive in ("skill", "agent", "command", "hook", "permissions", "loop"):
            with self.subTest(primitive=primitive):
                self.assertEqual(cells[primitive]["support"], "fallback")


class TestVendoredSchema(unittest.TestCase):
    def test_schema_file_hash_matches_pin(self):
        digest = hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()
        self.assertEqual(digest, SCHEMA_SHA256)


class TestEnumTokensSubsetOfSchema(unittest.TestCase):
    """Enum tokens transcribed into model.json must be subsets of the vendored schema's own
    enums, so the model never invents a value aesop's LOCKED schema doesn't recognize."""

    @classmethod
    def setUpClass(cls):
        cls.model = load_json(MODEL_PATH)
        cls.schema = load_json(SCHEMA_PATH)
        cls.by_id = {p["id"]: p for p in cls.model["primitives"]}

    def _field(self, primitive_id: str, field_name: str) -> dict:
        for field in self.by_id[primitive_id]["fields"]:
            if field["name"] == field_name:
                return field
        self.fail(f"field {field_name!r} not found on primitive {primitive_id!r}")

    def test_agent_model_and_effort_enums(self):
        agent_ref = self.schema["$defs"]["agentRef"]["oneOf"][1]["properties"]
        model_field = self._field("agent", "model")
        effort_field = self._field("agent", "effort")
        self.assertTrue(set(model_field["enum"]) <= set(agent_ref["model"]["enum"]))
        self.assertTrue(set(effort_field["enum"]) <= set(agent_ref["effort"]["enum"]))

    def test_mcp_transport_and_trust_enums(self):
        mcp_server = self.schema["$defs"]["mcpServer"]["properties"]
        transport_field = self._field("mcp", "transport")
        trust_field = self._field("mcp", "trust")
        self.assertTrue(set(transport_field["enum"]) <= set(mcp_server["transport"]["enum"]))
        self.assertTrue(set(trust_field["enum"]) <= set(mcp_server["trust"]["enum"]))

    def test_permissions_unattended_enum(self):
        unattended_schema_enum = self.schema["properties"]["primitives"]["properties"]["permissions"][
            "properties"
        ]["unattended"]["enum"]
        unattended_field = self._field("permissions", "unattended")
        self.assertTrue(set(unattended_field["enum"]) <= set(unattended_schema_enum))

    def test_loop_autonomy_enum(self):
        goal_recipe_enum = self.schema["$defs"]["goalRecipe"]["properties"]["autonomy"]["enum"]
        autonomy_field = self._field("loop", "autonomy")
        self.assertTrue(set(autonomy_field["enum"]) <= set(goal_recipe_enum))

    def test_hook_event_enum_pinned_from_registry_ts(self):
        # No schema enum for hook event (src/registry.ts HookSpec.event is a TS union, not part
        # of the JSON Schema) — pinned here from that source instead.
        REGISTRY_TS_HOOK_EVENTS = {"pre-tool", "post-tool", "stop", "session-start"}
        event_field = self._field("hook", "event")
        self.assertTrue(set(event_field["enum"]) <= REGISTRY_TS_HOOK_EVENTS)


if __name__ == "__main__":
    unittest.main()
