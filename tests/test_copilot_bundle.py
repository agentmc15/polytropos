"""Stdlib unittest suite enforcing copilot/aesop.yaml <-> copilot/.github/ consistency.

Per PLAN.md D2, this test IS the enforcement mechanism standing in for `aesop compile`, which
this repo never runs (no node toolchain in scope). It parses copilot/aesop.yaml as plain text
with a small line-oriented helper -- stdlib has no YAML parser, and none is added here -- and
cross-checks it against the hand-authored bundle under copilot/.github/ and the pricing data at
data/pricing.copilot.json. This test reads files only: no writes, no network.
"""

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COPILOT_DIR = REPO_ROOT / "copilot"
AESOP_YAML = COPILOT_DIR / "aesop.yaml"
GITHUB_DIR = COPILOT_DIR / ".github"
AGENTS_DIR = GITHUB_DIR / "agents"
SKILLS_DIR = GITHUB_DIR / "skills"
INSTRUCTIONS_MD = GITHUB_DIR / "copilot-instructions.md"
PRICING_COPILOT_JSON = REPO_ROOT / "data" / "pricing.copilot.json"

# Pinned verbatim in TASKS.md T6 -- the shared doctrine sentence that must appear, byte for
# byte (backticks included), in both the manifest and the emitted Copilot instructions file.
DOCTRINE_SENTENCE = (
    "Derive every number from `data/pricing.copilot.json` at run time — it is the single "
    "source of truth for Copilot-side pricing; never quote prices, credit values, or model "
    "ids from memory."
)


def _extract_yaml_list_block(yaml_text, key):
    """Return the `- <item>` values in the indented block that follows a `<key>:` line.

    Line-oriented, indentation-based text parsing only (no YAML parser). Blank lines inside
    the block are skipped; the block ends at the first non-blank line whose indentation is not
    greater than the `key:` line's own indentation.
    """
    lines = yaml_text.splitlines()
    key_line_re = re.compile(r"^(\s*)" + re.escape(key) + r":\s*$")
    items = []
    in_block = False
    key_indent = None
    for line in lines:
        if not in_block:
            m = key_line_re.match(line)
            if m:
                in_block = True
                key_indent = len(m.group(1))
            continue
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent <= key_indent:
            break
        item_m = re.match(r"^-\s+(\S+)\s*$", line.strip())
        if not item_m:
            break
        items.append(item_m.group(1))
    return items


def _iter_bundle_files():
    return sorted(p for p in GITHUB_DIR.rglob("*") if p.is_file())


def _iter_agent_files():
    return sorted(AGENTS_DIR.glob("*.agent.md"))


def _iter_skill_md_files():
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(SKILLS_DIR.glob("*/SKILL.md"))


def _frontmatter(text):
    """Return the YAML frontmatter block (between the first pair of `---` lines) as text."""
    parts = text.split("---")
    # parts[0] is empty/whitespace before the first '---'; parts[1] is the frontmatter body.
    return parts[1]


class ManifestSanityTests(unittest.TestCase):
    """Case 1: copilot/aesop.yaml exists, is version 1, and harnesses is exactly [copilot]."""

    def test_manifest_exists(self):
        self.assertTrue(AESOP_YAML.is_file(), f"missing manifest: {AESOP_YAML}")

    def test_version_is_1(self):
        text = AESOP_YAML.read_text()
        self.assertRegex(text, r"(?m)^version:\s*1\s*$")

    def test_harnesses_block_is_exactly_copilot(self):
        text = AESOP_YAML.read_text()
        harnesses = _extract_yaml_list_block(text, "harnesses")
        self.assertEqual(harnesses, ["copilot"])


class ManifestAgentsMatchBundleTests(unittest.TestCase):
    """Case 2: manifest agent names == *.agent.md stems in copilot/.github/agents/."""

    def test_manifest_agent_set_equals_bundle_agent_files(self):
        text = AESOP_YAML.read_text()
        manifest_agents = set(_extract_yaml_list_block(text, "agents"))
        self.assertTrue(manifest_agents, "manifest agents: block parsed as empty")

        bundle_stems = {p.name[: -len(".agent.md")] for p in _iter_agent_files()}

        self.assertEqual(manifest_agents, bundle_stems)


class DoctrineSentenceSyncTests(unittest.TestCase):
    """Case 3: the doctrine sentence appears verbatim in both the manifest and instructions."""

    def test_doctrine_sentence_in_manifest(self):
        text = AESOP_YAML.read_text()
        self.assertIn(DOCTRINE_SENTENCE, text)

    def test_doctrine_sentence_in_copilot_instructions(self):
        text = INSTRUCTIONS_MD.read_text()
        self.assertIn(DOCTRINE_SENTENCE, text)


class ModelPinLiveTests(unittest.TestCase):
    """Case 4: every agent frontmatter `model:` value is a key of pricing.copilot.json models."""

    def test_every_agent_model_pin_is_a_pricing_key(self):
        pricing = json.loads(PRICING_COPILOT_JSON.read_text())
        models = pricing["models"]

        agent_files = _iter_agent_files()
        self.assertTrue(agent_files, "no *.agent.md files found under copilot/.github/agents/")

        for agent_path in agent_files:
            fm = _frontmatter(agent_path.read_text())
            m = re.search(r"^model:\s*(\S+)\s*$", fm, re.M)
            self.assertIsNotNone(m, f"no model: field in frontmatter of {agent_path}")
            model_id = m.group(1)
            self.assertIn(
                model_id,
                models,
                f"{agent_path}: model '{model_id}' is not a key in pricing.copilot.json models",
            )


class PlaceholderDisciplineTests(unittest.TestCase):
    """Case 5: {{POLYTROPOS_ROOT}} used in route.agent.md; no absolute paths anywhere."""

    def test_route_agent_uses_root_placeholder(self):
        route_path = AGENTS_DIR / "route.agent.md"
        self.assertTrue(route_path.is_file(), f"missing {route_path}")
        text = route_path.read_text()
        self.assertIn("{{POLYTROPOS_ROOT}}", text)

    def test_no_bundle_file_has_an_absolute_path(self):
        offenders = []
        for path in _iter_bundle_files():
            text = path.read_text()
            if "/Users/" in text or "/home/" in text:
                offenders.append(str(path))
        self.assertEqual(offenders, [], f"absolute paths found in: {offenders}")


class HarnessSeparationTests(unittest.TestCase):
    """Case 6: no bundle file mentions CLAUDE_PLUGIN_ROOT or the Claude-side pricing.json."""

    def test_no_bundle_file_mentions_claude_plugin_root_or_claude_pricing(self):
        offenders = []
        for path in _iter_bundle_files():
            text = path.read_text()
            if "CLAUDE_PLUGIN_ROOT" in text or "data/pricing.json" in text:
                offenders.append(str(path))
        self.assertEqual(offenders, [], f"Claude-harness references found in: {offenders}")


# Per TASKS.md T2 / PLAN.md D4: pins may change with the roster, but the tier a workflow agent
# is pinned to is the contract. Assert tiers via data lookup only -- no model-id literals here.
WORKFLOW_AGENT_TIERS = {
    "architect": "frontier",
    "implementer": "mid",
    "verifier": "cheap",
    "reviewer": "strong",
    "route": "mid",
    "usage": "cheap",
    "journal": "mid",
    "frontier-check": "mid",
    "escalate": "mid",
    "effort": "mid",
}


class WorkflowAgentTierTests(unittest.TestCase):
    """Case 7: each workflow agent's frontmatter model: pin is a live key of the expected tier."""

    def test_each_workflow_agent_pin_matches_its_expected_tier(self):
        pricing = json.loads(PRICING_COPILOT_JSON.read_text())
        models = pricing["models"]

        for stem, expected_tier in WORKFLOW_AGENT_TIERS.items():
            agent_path = AGENTS_DIR / f"{stem}.agent.md"
            with self.subTest(agent=stem):
                self.assertTrue(agent_path.is_file(), f"missing {agent_path}")
                fm = _frontmatter(agent_path.read_text())
                m = re.search(r"^model:\s*(\S+)\s*$", fm, re.M)
                self.assertIsNotNone(m, f"no model: field in frontmatter of {agent_path}")
                model_id = m.group(1)
                self.assertIn(
                    model_id,
                    models,
                    f"{agent_path}: model '{model_id}' is not a key in pricing.copilot.json models",
                )
                self.assertEqual(
                    models[model_id]["tier"],
                    expected_tier,
                    f"{agent_path}: model '{model_id}' has tier "
                    f"'{models[model_id]['tier']}', expected '{expected_tier}'",
                )


class WorkflowAgentContractTests(unittest.TestCase):
    """Case 8: text-level contracts pinned in TASKS.md T1/T2 for the four new workflow agents."""

    NEW_AGENT_STEMS = ("architect", "implementer", "verifier", "reviewer")

    def _text(self, stem):
        return (AGENTS_DIR / f"{stem}.agent.md").read_text()

    def test_status_vocabulary_in_all_four(self):
        for stem in self.NEW_AGENT_STEMS:
            with self.subTest(agent=stem):
                self.assertIn("pending | in-progress | done | blocked", self._text(stem))

    def test_kits_path_in_architect_and_implementer(self):
        for stem in ("architect", "implementer"):
            with self.subTest(agent=stem):
                self.assertIn("tasks/kits/", self._text(stem))

    def test_root_placeholder_in_architect(self):
        self.assertIn("{{POLYTROPOS_ROOT}}", self._text("architect"))

    def test_model_flag_in_implementer(self):
        self.assertIn("--model", self._text("implementer"))


class PortedAgentContractTests(unittest.TestCase):
    """Case 8b: text-level contracts pinned in TASKS.md for the ported (non-workflow) agents."""

    def _text(self, stem):
        return (AGENTS_DIR / f"{stem}.agent.md").read_text()

    def test_usage_mentions_engine_and_placeholder(self):
        text = self._text("usage")
        self.assertIn("bin/copilot_usage.py", text)
        self.assertIn("{{POLYTROPOS_ROOT}}", text)

    def test_usage_is_read_only(self):
        self.assertIn("read-only", self._text("usage"))

    def test_journal_mentions_collector(self):
        self.assertIn("bin/journal_collect.py", self._text("journal"))

    def test_journal_pins_dry_run(self):
        self.assertIn("--dry-run", self._text("journal"))

    def test_frontier_check_derives_from_data(self):
        text = self._text("frontier-check")
        self.assertIn("bin/copilot_pricing.py", text)
        self.assertIn("frontier", text)

    def test_frontier_check_is_not_named_fable(self):
        self.assertNotIn("fable-check", self._text("frontier-check").lower())

    def test_escalate_is_verify_gated(self):
        self.assertIn("verify", self._text("escalate"))

    def test_escalate_points_at_execute_driver(self):
        self.assertIn("bin/copilot_execute.py", self._text("escalate"))


class EffortAgentContractTests(unittest.TestCase):
    """Case 8c: text-level contracts pinned in TASKS.md T5 / PLAN.md D7/D8 for the effort agent."""

    def _text(self, stem):
        return (AGENTS_DIR / f"{stem}.agent.md").read_text()

    def test_effort_derives_ladder_from_knobs(self):
        text = self._text("effort")
        self.assertIn("bin/copilot_pricing.py", text)
        self.assertIn("knobs", text)

    def test_effort_teaches_interactive_picker(self):
        text = self._text("effort")
        self.assertIn("/model", text)
        self.assertIn("arrow", text.lower())

    def test_effort_headless_honesty(self):
        self.assertIn("unconfirmed", self._text("effort").lower())

    def test_effort_no_borrowed_or_invented_flag(self):
        text = self._text("effort")
        self.assertNotIn("--effort", text)
        self.assertNotIn("model_reasoning_effort", text)


class ManifestSkillsMatchBundleTests(unittest.TestCase):
    """Case 9: manifest skills: block == directory names under copilot/.github/skills/,
    each containing a SKILL.md."""

    def test_manifest_skills_set_equals_bundle_skill_dirs(self):
        text = AESOP_YAML.read_text()
        manifest_skills = set(_extract_yaml_list_block(text, "skills"))
        self.assertTrue(manifest_skills, "manifest skills: block parsed as empty")

        bundle_skill_dirs = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()} if SKILLS_DIR.is_dir() else set()

        self.assertEqual(manifest_skills, bundle_skill_dirs)

    def test_each_bundle_skill_dir_has_a_skill_md(self):
        text = AESOP_YAML.read_text()
        manifest_skills = set(_extract_yaml_list_block(text, "skills"))
        self.assertTrue(manifest_skills, "manifest skills: block parsed as empty")

        for name in manifest_skills:
            with self.subTest(skill=name):
                skill_md = SKILLS_DIR / name / "SKILL.md"
                self.assertTrue(skill_md.is_file(), f"missing {skill_md}")


class LessonsLoopContractTests(unittest.TestCase):
    """Case 10: text-level contract pinned in TASKS.md T7 / PLAN.md D7 for lessons-loop."""

    def _text(self):
        return (SKILLS_DIR / "lessons-loop" / "SKILL.md").read_text()

    def test_cites_aesop_provenance_commit(self):
        self.assertIn("5506617", self._text())

    def test_mentions_tasks_lessons_md(self):
        self.assertIn("tasks/lessons.md", self._text())

    def test_mentions_routing(self):
        self.assertIn("routing", self._text())


class FrontmatterYamlSafetyTests(unittest.TestCase):
    """Regression guard (a real bug shipped once): a frontmatter value containing an unquoted
    ``: `` (colon-space) is read by real YAML loaders — including Copilot CLI's — as a nested
    mapping and the whole agent is REJECTED ('mapping values are not allowed in this context').
    The regex-based tests above cannot catch this (stdlib has no YAML parser), so scan every
    agent's frontmatter for the breaker. Fix by quoting the value or dropping the inner ``: ``."""

    def test_no_unquoted_colon_in_frontmatter_values(self):
        offenders = []
        for agent_path in _iter_agent_files():
            for line in _frontmatter(agent_path.read_text()).splitlines():
                m = re.match(r"^([A-Za-z][\w-]*): (.*)$", line)
                if not m:
                    continue
                value = m.group(2)
                if value[:1] in ('"', "'"):
                    continue  # a quoted scalar may legally contain ': '
                if ": " in value:
                    offenders.append(f"{agent_path.name} [{m.group(1)}]")
        self.assertEqual(
            offenders, [],
            f"frontmatter values with an unquoted ': ' (breaks real YAML loaders): {offenders}",
        )


class SkillFrontmatterTests(unittest.TestCase):
    """Generic sweep (D6): every skill's frontmatter has name: == parent dir name, a non-empty
    description:, and NO model: line -- skills carry no model pin."""

    def test_skill_frontmatter_discipline(self):
        skill_files = _iter_skill_md_files()
        self.assertTrue(skill_files, "no SKILL.md files found under copilot/.github/skills/")

        for skill_path in skill_files:
            dir_name = skill_path.parent.name
            with self.subTest(skill=dir_name):
                fm = _frontmatter(skill_path.read_text())

                name_m = re.search(r"^name:\s*(\S+)\s*$", fm, re.M)
                self.assertIsNotNone(name_m, f"no name: field in frontmatter of {skill_path}")
                self.assertEqual(name_m.group(1), dir_name)

                desc_m = re.search(r"^description:\s*(\S.*)$", fm, re.M)
                self.assertIsNotNone(
                    desc_m, f"no non-empty description: field in frontmatter of {skill_path}"
                )

                self.assertNotRegex(
                    fm, r"(?m)^model:", f"{skill_path}: skills must carry no model: pin"
                )


class SkillFrontmatterYamlSafetyTests(unittest.TestCase):
    """Generic sweep (D6): twin of FrontmatterYamlSafetyTests, scanning skill frontmatter."""

    def test_no_unquoted_colon_in_frontmatter_values(self):
        offenders = []
        for skill_path in _iter_skill_md_files():
            for line in _frontmatter(skill_path.read_text()).splitlines():
                m = re.match(r"^([A-Za-z][\w-]*): (.*)$", line)
                if not m:
                    continue
                value = m.group(2)
                if value[:1] in ('"', "'"):
                    continue  # a quoted scalar may legally contain ': '
                if ": " in value:
                    offenders.append(f"{skill_path.parent.name}/SKILL.md [{m.group(1)}]")
        self.assertEqual(
            offenders, [],
            f"frontmatter values with an unquoted ': ' (breaks real YAML loaders): {offenders}",
        )


class SkillNoModelIdTests(unittest.TestCase):
    """Generic sweep (D6): no skill file names a live pricing-key model id -- skills stay
    tier-worded and id-free."""

    def test_no_pricing_model_id_in_any_skill_file(self):
        pricing = json.loads(PRICING_COPILOT_JSON.read_text())
        model_ids = list(pricing["models"].keys())

        for skill_path in _iter_skill_md_files():
            text = skill_path.read_text()
            with self.subTest(skill=skill_path.parent.name):
                for model_id in model_ids:
                    self.assertNotIn(
                        model_id,
                        text,
                        f"{skill_path}: contains pricing-key model id '{model_id}'",
                    )


class RouteSkillContractTests(unittest.TestCase):
    """Case: text-level contracts pinned in TASKS.md T1 / PLAN.md D1/D2 for the route skill."""

    def _text(self):
        return (SKILLS_DIR / "route" / "SKILL.md").read_text()

    def test_route_estimates_from_engine(self):
        text = self._text()
        self.assertIn("bin/copilot_pricing.py", text)
        self.assertIn("est", text)

    def test_route_uses_placeholder(self):
        self.assertIn("{{POLYTROPOS_ROOT}}", self._text())

    def test_route_points_at_agent(self):
        self.assertIn("copilot --agent route", self._text())

    def test_route_reads_lessons(self):
        self.assertIn("tasks/lessons.md", self._text())


class UsageSkillContractTests(unittest.TestCase):
    """Case: text-level contracts pinned in TASKS.md T2 / PLAN.md D1/D2 for the usage skill."""

    def _text(self):
        return (SKILLS_DIR / "usage" / "SKILL.md").read_text()

    def test_usage_mentions_engine_and_placeholder(self):
        text = self._text()
        self.assertIn("bin/copilot_usage.py", text)
        self.assertIn("{{POLYTROPOS_ROOT}}", text)

    def test_usage_is_read_only(self):
        self.assertIn("read-only", self._text())

    def test_usage_points_at_agent(self):
        self.assertIn("copilot --agent usage", self._text())


class JournalSkillContractTests(unittest.TestCase):
    """Case: text-level contracts pinned in TASKS.md T2 / PLAN.md D1/D2 for the journal skill."""

    def _text(self):
        return (SKILLS_DIR / "journal" / "SKILL.md").read_text()

    def test_journal_mentions_collector(self):
        self.assertIn("bin/journal_collect.py", self._text())

    def test_journal_pins_dry_run(self):
        self.assertIn("--dry-run", self._text())

    def test_journal_points_at_agent(self):
        self.assertIn("copilot --agent journal", self._text())


class FrontierCheckSkillContractTests(unittest.TestCase):
    """Case: text-level contracts pinned in TASKS.md T3 / PLAN.md D1/D2/D7 for the
    frontier-check skill."""

    def _text(self):
        return (SKILLS_DIR / "frontier-check" / "SKILL.md").read_text()

    def test_frontier_check_derives_from_data(self):
        text = self._text()
        self.assertIn("bin/copilot_pricing.py", text)
        self.assertIn("frontier", text)

    def test_frontier_check_is_not_named_fable(self):
        self.assertNotIn("fable-check", self._text().lower())

    def test_frontier_check_points_at_agent(self):
        self.assertIn("copilot --agent frontier-check", self._text())


class EffortSkillContractTests(unittest.TestCase):
    """Case: text-level contracts pinned in TASKS.md T3 / PLAN.md D7/D8 for the effort skill."""

    def _text(self):
        return (SKILLS_DIR / "effort" / "SKILL.md").read_text()

    def test_effort_derives_ladder_from_knobs(self):
        text = self._text()
        self.assertIn("bin/copilot_pricing.py", text)
        self.assertIn("knobs", text)

    def test_effort_teaches_interactive_picker(self):
        text = self._text()
        self.assertIn("/model", text)
        self.assertIn("arrow", text.lower())

    def test_effort_headless_honesty(self):
        self.assertIn("unconfirmed", self._text().lower())

    def test_effort_no_borrowed_or_invented_flag(self):
        text = self._text()
        self.assertNotIn("--effort", text)
        self.assertNotIn("model_reasoning_effort", text)


class EscalateSkillContractTests(unittest.TestCase):
    """Case: text-level contracts pinned in TASKS.md T4 / PLAN.md D1/D2 for the escalate skill."""

    def _text(self):
        return (SKILLS_DIR / "escalate" / "SKILL.md").read_text()

    def test_escalate_is_verify_gated(self):
        self.assertIn("verify", self._text())

    def test_escalate_points_at_execute_driver(self):
        self.assertIn("bin/copilot_execute.py", self._text())

    def test_escalate_derives_ladder_from_data(self):
        self.assertIn("bin/copilot_pricing.py", self._text())


class ArchitectSkillContractTests(unittest.TestCase):
    """Case: text-level contracts pinned in TASKS.md T5 / PLAN.md D1/D4 for the architect skill."""

    def _text(self):
        return (SKILLS_DIR / "architect" / "SKILL.md").read_text()

    def test_architect_emits_kits(self):
        self.assertIn("tasks/kits/", self._text())

    def test_architect_status_vocabulary(self):
        self.assertIn("pending | in-progress | done | blocked", self._text())

    def test_architect_pins_from_data(self):
        self.assertIn("bin/copilot_pricing.py", self._text())

    def test_architect_points_at_agent(self):
        self.assertIn("copilot --agent architect", self._text())


class ExecuteSkillContractTests(unittest.TestCase):
    """Case: text-level contracts pinned in TASKS.md T6 / PLAN.md D3 for the execute skill."""

    def _text(self):
        return (SKILLS_DIR / "execute" / "SKILL.md").read_text()

    def test_execute_drives_the_driver(self):
        text = self._text()
        self.assertIn("bin/copilot_execute.py", text)
        self.assertIn("--kit", text)

    def test_execute_status_vocabulary(self):
        self.assertIn("pending | in-progress | done | blocked", self._text())

    def test_execute_caps_escalation(self):
        self.assertIn("--max-escalations", self._text())

    def test_execute_orchestration_honesty(self):
        text = self._text().lower()
        self.assertIn("parallel", text)
        self.assertIn("serially", text)


class ContextWeightSkillContractTests(unittest.TestCase):
    """Case: text-level contracts pinned in copilot-measure-parity TASKS.md T1/T2 / PLAN.md
    D2/D3 for the context-weight skill and its same-named agent."""

    def _text(self):
        return (SKILLS_DIR / "context-weight" / "SKILL.md").read_text()

    def _agent_text(self):
        return (AGENTS_DIR / "context-weight.agent.md").read_text()

    def test_context_weight_mentions_engine_and_placeholder(self):
        text = self._text()
        self.assertIn("bin/context_weight.py", text)
        self.assertIn("{{POLYTROPOS_ROOT}}", text)

    def test_context_weight_harness_copilot(self):
        self.assertIn("--harness copilot", self._text())

    def test_context_weight_session_average(self):
        self.assertIn("session-average", self._text())

    def test_context_weight_watch_honesty(self):
        text = self._text()
        self.assertIn("watch", text)
        self.assertIn("refus", text)

    def test_context_weight_no_growth_curve(self):
        self.assertIn("no growth curve", self._text())

    def test_context_weight_points_at_agent(self):
        self.assertIn("copilot --agent context-weight", self._text())

    def test_context_weight_agent_exists_with_engine_path(self):
        text = self._agent_text()
        self.assertIn("bin/context_weight.py", text)
        self.assertIn("{{POLYTROPOS_ROOT}}", text)


class BenchRoutingSkillContractTests(unittest.TestCase):
    """Case: text-level contracts pinned in copilot-measure-parity TASKS.md T3/T4 / PLAN.md
    D2/D3 for the bench-routing skill and its same-named agent."""

    def _text(self):
        return (SKILLS_DIR / "bench-routing" / "SKILL.md").read_text()

    def _agent_text(self):
        return (AGENTS_DIR / "bench-routing.agent.md").read_text()

    def test_bench_routing_mentions_engine_and_placeholder(self):
        text = self._text()
        self.assertIn("bin/bench_routing.py", text)
        self.assertIn("{{POLYTROPOS_ROOT}}", text)

    def test_bench_routing_roles_harness_copilot(self):
        self.assertIn("roles --harness copilot", self._text())

    def test_bench_routing_unavailable_semantics(self):
        self.assertIn("unavailable", self._text())

    def test_bench_routing_never_a_bill(self):
        self.assertIn("never a bill", self._text())

    def test_bench_routing_intelligence_index(self):
        self.assertIn("Intelligence Index", self._text())

    def test_bench_routing_compare_honesty(self):
        self.assertIn("stands unchallenged", self._text())

    def test_bench_routing_points_at_agent(self):
        self.assertIn("copilot --agent bench-routing", self._text())

    def test_bench_routing_agent_exists_with_engine_path(self):
        text = self._agent_text()
        self.assertIn("bin/bench_routing.py", text)
        self.assertIn("{{POLYTROPOS_ROOT}}", text)


class PrefsTeachingDecisionAidTests(unittest.TestCase):
    """Pins/excludes teaching (copilot-model-prefs PLAN.md D8): route + frontier-check,
    skill and agent surfaces."""

    FILES = {
        "route skill": SKILLS_DIR / "route" / "SKILL.md",
        "route agent": AGENTS_DIR / "route.agent.md",
        "frontier-check skill": SKILLS_DIR / "frontier-check" / "SKILL.md",
        "frontier-check agent": AGENTS_DIR / "frontier-check.agent.md",
    }

    def test_each_surface_checks_active_prefs(self):
        for label, path in self.FILES.items():
            with self.subTest(surface=label):
                text = path.read_text()
                self.assertIn("User model prefs", text)
                self.assertIn("copilot_pricing.py", text)
                self.assertIn("prefs", text)
                self.assertIn("exclude", text)

    def test_frontier_check_evaluates_pinned_candidate(self):
        for label in ("frontier-check skill", "frontier-check agent"):
            with self.subTest(surface=label):
                self.assertIn("overrides the roster", self.FILES[label].read_text())


class PrefsTeachingWorkflowTests(unittest.TestCase):
    """Pins/excludes teaching (copilot-model-prefs PLAN.md D8): architect + escalate
    (skill and agent) and the execute skill's driver-flag sentence."""

    def _skill(self, name):
        return (SKILLS_DIR / name / "SKILL.md").read_text()

    def _agent(self, name):
        return (AGENTS_DIR / f"{name}.agent.md").read_text()

    def test_architect_pins_consistent_with_prefs(self):
        for text in (self._skill("architect"), self._agent("architect")):
            self.assertIn("User model prefs", text)
            self.assertIn("never an excluded id", text)

    def test_escalate_names_driver_flags_and_empty_tier_honesty(self):
        for text in (self._skill("escalate"), self._agent("escalate")):
            self.assertIn("--pin", text)
            self.assertIn("--exclude", text)
            self.assertIn("tops out", text)

    def test_execute_names_driver_flags(self):
        text = self._skill("execute")
        self.assertIn("--pin", text)
        self.assertIn("--exclude", text)
        self.assertIn("--no-prefs", text)
        self.assertIn("prefs/copilot.json", text)


class ArchitectKitGrammarTests(unittest.TestCase):
    """Regression guard (found by the first real Copilot-architected kit): the architect
    surfaces must pin the EXACT machine-parsed TASKS.md grammar — a prose-only contract let
    a frontier model write backticked pins, semantic depends, and unrecognized verify
    headings, crashing the execute driver. Both surfaces must carry the literal skeleton
    and the status self-check."""

    FILES = {
        "architect skill": SKILLS_DIR / "architect" / "SKILL.md",
        "architect agent": AGENTS_DIR / "architect.agent.md",
    }

    def test_both_surfaces_pin_the_skeleton_grammar(self):
        for label, path in self.FILES.items():
            with self.subTest(surface=label):
                text = path.read_text()
                self.assertIn("machine-parsed", text)
                self.assertIn("- model: <model-id>", text)
                self.assertIn("**Verify.**", text)
                self.assertIn("```bash", text)
                self.assertIn("task IDS", text)

    def test_both_surfaces_teach_the_status_self_check(self):
        for label, path in self.FILES.items():
            with self.subTest(surface=label):
                self.assertIn("status --kit", path.read_text())


if __name__ == "__main__":
    unittest.main()
