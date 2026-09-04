import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("harness_select_discovery", ROOT / "bin" / "harness_select.py")
hs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hs)

AGENTS = ("kit-implementer", "kit-verifier", "phase-reviewer", "repo-explorer")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fixture(root):
    write(root / ".codex-plugin" / "plugin.json", json.dumps({
        "name": "polytropos", "version": "1.0.0", "skills": "./codex/skills/"
    }))
    write(root / ".agents" / "plugins" / "marketplace.json", json.dumps({
        "plugins": [{"name": "polytropos", "source": {"source": "local", "path": "./"}}]
    }))
    for name in AGENTS:
        write(root / "codex" / "agents" / f"{name}.toml",
              f'name = "{name}"\ndescription = "fixture"\ndeveloper_instructions = "fixture"\n')
    write(root / "codex" / "skills" / "route" / "SKILL.md", "root {{POLYTROPOS_ROOT}}\n")
    write(root / "codex" / "skills" / "route" / "agents" / "openai.yaml", "interface: {}\n")
    write(root / "codex" / "prompts" / "route.md", "root {{POLYTROPOS_ROOT}}\n")
    write(root / "codex" / "AGENTS.md", "root {{POLYTROPOS_ROOT}}\n")
    return root


def snapshot(root):
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*") if path.is_file()
    }


class CodexDiscoveryTests(unittest.TestCase):
    def test_ready_package_does_not_claim_activation_in_empty_home(self):
        with tempfile.TemporaryDirectory() as repo_s, tempfile.TemporaryDirectory() as home_s:
            repo, home = fixture(Path(repo_s)), Path(home_s)
            report = hs.doctor_codex(repo, home)
            self.assertEqual(report["package_readiness"]["state"], "ready")
            self.assertEqual(report["activation"]["state"], "unknown")
            self.assertTrue(all(
                surface["state"] == "absent" and surface["optional"]
                for surface in report["legacy_surfaces"].values()
            ))
            self.assertFalse(any("loaded" in action["reason"].lower() for action in report["actions"]))

    def test_invalid_metadata_is_distinct_from_unknown_activation(self):
        with tempfile.TemporaryDirectory() as repo_s, tempfile.TemporaryDirectory() as home_s:
            repo, home = fixture(Path(repo_s)), Path(home_s)
            write(repo / ".codex-plugin" / "plugin.json", "{}")
            report = hs.doctor_codex(repo, home)
            self.assertEqual(report["package_readiness"]["state"], "invalid")
            self.assertEqual(report["activation"]["state"], "unknown")
            self.assertEqual(report["actions"][0]["state"], "conflict")

    def test_matching_edited_and_duplicate_legacy_copies_are_reported(self):
        with tempfile.TemporaryDirectory() as repo_s, tempfile.TemporaryDirectory() as home_s:
            repo, home = fixture(Path(repo_s)), Path(home_s)
            write(home / "skills" / "route" / "SKILL.md", f"root {repo.resolve()}\n")
            write(home / "prompts" / "route.md", "personal edit\n")
            report = hs.doctor_codex(repo, home)
            states = {(a["component"], Path(a["destination"]).name): a["state"] for a in report["actions"]}
            self.assertEqual(states[("skills", "SKILL.md")], "up-to-date")
            self.assertEqual(states[("prompts", "route.md")], "conflict")
            duplicate = report["potential_duplicate_names"][0]
            self.assertEqual(duplicate["name"], "route")
            self.assertEqual(set(duplicate["surfaces"]), {
                "plugin-package", "legacy-prompt-copy", "legacy-skill-copy"
            })

    def test_text_json_and_diagnostic_are_read_only(self):
        with tempfile.TemporaryDirectory() as repo_s, tempfile.TemporaryDirectory() as home_s:
            repo, home = fixture(Path(repo_s)), Path(home_s)
            write(home / "skills" / "route" / "SKILL.md", f"root {repo.resolve()}\n")
            before_repo, before_home = snapshot(repo), snapshot(home)
            report = hs.doctor_codex(repo, home)
            text = hs.render_codex_plan(report)
            parsed = json.loads(hs.render_codex_plan(report, as_json=True))
            self.assertIn("package readiness: ready", text)
            self.assertIn("runtime activation: unknown", text)
            self.assertIn("potential duplicate: route", text)
            self.assertEqual(parsed["package_readiness"], report["package_readiness"])
            self.assertEqual(parsed["activation"], report["activation"])
            self.assertEqual(parsed["legacy_surfaces"], report["legacy_surfaces"])
            self.assertEqual(snapshot(repo), before_repo)
            self.assertEqual(snapshot(home), before_home)

    def test_metadata_only_legacy_skill_still_identifies_its_skill_name(self):
        with tempfile.TemporaryDirectory() as repo_s, tempfile.TemporaryDirectory() as home_s:
            repo, home = fixture(Path(repo_s)), Path(home_s)
            write(home / "skills" / "route" / "agents" / "openai.yaml", "interface: {}\n")
            report = hs.doctor_codex(repo, home)
            self.assertEqual(
                report["potential_duplicate_names"],
                [{"name": "route", "surfaces": ["legacy-skill-copy", "plugin-package"]}],
            )


if __name__ == "__main__":
    unittest.main()
