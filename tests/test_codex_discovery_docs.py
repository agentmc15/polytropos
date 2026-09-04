import importlib.util
import shlex
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = (
    ROOT / "README.md",
    ROOT / "SETUP.md",
    ROOT / "codex" / "AGENTS.md",
    ROOT / "docs" / "CODEX-HARNESS.md",
    ROOT / "docs-site" / "getting-started" / "codex.md",
)


def _load(filename, module_name=None):
    name = module_name or filename
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{filename}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


selector = _load("harness_select", "harness_select_discovery_docs")


class CodexDiscoveryDocsTests(unittest.TestCase):
    def test_documented_harness_commands_parse_without_execution(self):
        parser = selector.build_parser()
        found = 0
        for path in DOCS:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.startswith("python3 bin/harness_select.py "):
                    continue
                found += 1
                parser.parse_args(shlex.split(line)[2:])
        self.assertGreaterEqual(found, 12)

    def test_documented_native_cli_commands_are_the_supported_shapes(self):
        commands = set()
        for path in DOCS:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("codex plugin "):
                    commands.add(tuple(shlex.split(line)))
        self.assertIn(("codex", "plugin", "marketplace", "add", "/path/to/polytropos"), commands)
        self.assertIn(("codex", "plugin", "add", "polytropos@polytropos-local"), commands)
        self.assertIn(("codex", "plugin", "list", "--marketplace", "polytropos-local", "--json"), commands)

    def test_current_guidance_is_skills_first_and_names_migration_limits(self):
        guidance = (ROOT / "codex" / "AGENTS.md").read_text(encoding="utf-8")
        harness = (ROOT / "docs" / "CODEX-HARNESS.md").read_text(encoding="utf-8")
        for text in (guidance, harness):
            self.assertIn("$route", text)
            self.assertIn("/skills", text)
        self.assertNotIn("`/route` prompt first", guidance)
        for term in (
            "package **readiness**", "activation", "--legacy-copy", "retire-legacy",
            "restore-legacy", "--native-skills-confirmed", "conflict", ".agents/skills",
            ".codex/skills", "cached package", "not been performed by automated verification",
        ):
            self.assertIn(term, harness)

    def test_generated_docs_are_current(self):
        builder = _load("docs_build", "docs_build_discovery_docs")
        stale, unknown = builder.check_site(ROOT)
        self.assertEqual((stale, unknown), ([], []))


if __name__ == "__main__":
    unittest.main()
