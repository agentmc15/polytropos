import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / "codex" / "skills"
METADATA_RELATIVE = Path("agents") / "openai.yaml"
REQUIRED_INTERFACE_KEYS = {
    "display_name",
    "short_description",
    "default_prompt",
}

SPEC = importlib.util.spec_from_file_location(
    "sync_codex_surfaces_metadata", ROOT / "bin" / "sync_codex_surfaces.py"
)
syncer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(syncer)

HARNESS_SPEC = importlib.util.spec_from_file_location(
    "harness_select_metadata", ROOT / "bin" / "harness_select.py"
)
harness = importlib.util.module_from_spec(HARNESS_SPEC)
HARNESS_SPEC.loader.exec_module(harness)


def canonical_skills(root=SKILLS_ROOT):
    return sorted(path for path in Path(root).iterdir() if (path / "SKILL.md").is_file())


def parse_metadata(path):
    """Parse the deliberately narrow JSON-string YAML subset used by these files."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "interface:":
        raise ValueError("metadata must begin with an interface mapping")
    values = {}
    for line in lines[1:]:
        if not line.startswith("  ") or ": " not in line:
            raise ValueError("metadata must contain indented key/value pairs only")
        key, raw_value = line[2:].split(": ", 1)
        if key in values:
            raise ValueError(f"duplicate interface key: {key}")
        value = json.loads(raw_value)
        if not isinstance(value, str):
            raise ValueError(f"interface value is not a string: {key}")
        values[key] = value
    if set(values) != REQUIRED_INTERFACE_KEYS:
        raise ValueError("metadata has unexpected or missing interface keys")
    return values


class CodexSkillMetadataTests(unittest.TestCase):
    def test_every_canonical_skill_has_complete_distinct_metadata(self):
        skills = canonical_skills()
        self.assertEqual(len(skills), 12)
        display_names = set()
        short_descriptions = set()
        for skill_dir in skills:
            with self.subTest(skill=skill_dir.name):
                metadata = parse_metadata(skill_dir / METADATA_RELATIVE)
                self.assertTrue(all(value.strip() for value in metadata.values()))
                self.assertIn(f"${skill_dir.name}", metadata["default_prompt"])
                display_names.add(metadata["display_name"])
                short_descriptions.add(metadata["short_description"])
        self.assertEqual(len(display_names), len(skills))
        self.assertEqual(len(short_descriptions), len(skills))

    def test_metadata_has_no_unsupported_references_or_absolute_root(self):
        for skill_dir in canonical_skills():
            with self.subTest(skill=skill_dir.name):
                raw = (skill_dir / METADATA_RELATIVE).read_text(encoding="utf-8")
                metadata = parse_metadata(skill_dir / METADATA_RELATIVE)
                self.assertNotIn("prompts:", raw)
                self.assertNotIn("dependencies:", raw)
                self.assertNotIn("model:", raw)
                self.assertNotIn("image:", raw)
                self.assertNotIn(str(ROOT), raw)
                self.assertNotIn("/Users/", raw)
                self.assertNotIn("/home/", raw)
                self.assertNotIn("$", metadata["display_name"])
                self.assertNotIn("$", metadata["short_description"])

    def test_metadata_survives_native_package_legacy_copy_and_relocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            relocated_root = Path(temporary) / "relocated"
            shutil.copytree(ROOT / "codex", relocated_root / "codex")
            shutil.copytree(ROOT / ".codex-plugin", relocated_root / ".codex-plugin")
            shutil.copytree(ROOT / ".agents", relocated_root / ".agents")
            (relocated_root / "data").mkdir()
            (relocated_root / "data" / "pricing.codex.json").write_text("{}\n")
            (relocated_root / "bin").mkdir()
            (relocated_root / "bin" / "codex_pricing.py").write_text("# fixture\n")

            home = Path(temporary) / "codex-home"
            plan = harness.plan_codex_setup(
                relocated_root,
                home,
                components=("skills",),
                legacy_copy=True,
            )
            metadata_actions = [
                action
                for action in plan["actions"]
                if action["source"].endswith(METADATA_RELATIVE.as_posix())
            ]
            self.assertEqual(len(metadata_actions), 12)
            self.assertEqual({action["state"] for action in metadata_actions}, {"install"})
            harness.apply_codex_plan(plan)

            for source_skill in canonical_skills(relocated_root / "codex" / "skills"):
                name = source_skill.name
                package_metadata = source_skill / METADATA_RELATIVE
                legacy_metadata = home / "skills" / name / METADATA_RELATIVE
                with self.subTest(skill=name):
                    self.assertEqual(package_metadata.read_bytes(), legacy_metadata.read_bytes())
                    self.assertEqual(parse_metadata(package_metadata), parse_metadata(legacy_metadata))
                    fields, _ = syncer._frontmatter(source_skill / "SKILL.md")
                    self.assertEqual(fields["name"], name)

            ownership = json.loads((home / harness.OWNERSHIP_RELATIVE).read_text(encoding="utf-8"))
            owned_metadata = [
                record
                for record in ownership["files"]
                if record["destination"].endswith(METADATA_RELATIVE.as_posix())
            ]
            self.assertEqual(len(owned_metadata), 12)

            route_skill = relocated_root / "codex" / "skills" / "route" / "SKILL.md"
            self.assertEqual(
                syncer.resolve_skill_root(route_skill, "codex_pricing.py"),
                relocated_root.resolve(),
            )

    def test_starters_keep_planning_execution_routing_effort_and_diagnosis_separate(self):
        metadata = {
            skill_dir.name: parse_metadata(skill_dir / METADATA_RELATIVE)
            for skill_dir in canonical_skills()
        }
        self.assertIn("plan", metadata["architect"]["default_prompt"].lower())
        self.assertIn("execute", metadata["execute"]["default_prompt"].lower())
        self.assertIn("tier", metadata["route"]["default_prompt"].lower())
        self.assertIn("reasoning-effort", metadata["effort"]["default_prompt"].lower())
        self.assertIn("diagnose", metadata["doctor"]["default_prompt"].lower())
        self.assertIn("without changing", metadata["doctor"]["default_prompt"].lower())


if __name__ == "__main__":
    unittest.main()
