import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


context_weight = _load("context_weight")
bench_routing = _load("bench_routing")


class AnalysisSkillTests(unittest.TestCase):
    def test_context_weight_commands_parse_and_fidelity_is_bounded(self):
        parser = context_weight.build_parser()
        parser.parse_args(["session", "--harness", "codex", "--codex-home", "/tmp/codex"])
        parser.parse_args(["overview", "--harness", "codex", "--codex-home", "/tmp/codex"])
        parser.parse_args(["audit", "--project", "/tmp/repo"])
        parser.parse_args(["demo"])
        text = (ROOT / "codex" / "skills" / "context-weight" / "SKILL.md").read_text()
        flat = " ".join(text.split())
        self.assertIn("token-count growth curves", text)
        self.assertIn("not content provenance", flat)
        self.assertIn("`watch` is Claude-only", text)
        self.assertIn("cannot answer live pruning", text)
        self.assertIn("never dollars", flat)

    def test_bench_routing_commands_parse_and_keep_benchmark_limits(self):
        parser = bench_routing.build_parser()
        parser.parse_args(["roles", "--harness", "codex"])
        parser.parse_args(["rank"])
        parser.parse_args(["demo"])
        text = (ROOT / "codex" / "skills" / "bench-routing" / "SKILL.md").read_text()
        flat = " ".join(text.split())
        self.assertIn("Intelligence Index", text)
        self.assertIn("screenshot", text)
        self.assertIn("not this repository's pricing", flat)
        self.assertIn("not a guaranteed winner", text)

    def test_skills_are_thin_portable_and_unpinned(self):
        for stem in ("context-weight", "bench-routing"):
            text = (ROOT / "codex" / "skills" / stem / "SKILL.md").read_text()
            frontmatter = text.split("---", 2)[1]
            self.assertNotIn("model:", frontmatter)
            self.assertIn('POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"', text)
            self.assertNotIn("/Users/", text)
            self.assertNotIn("data/pricing.json", text)
            self.assertNotIn("data/pricing.copilot.json", text)


if __name__ == "__main__":
    unittest.main()
