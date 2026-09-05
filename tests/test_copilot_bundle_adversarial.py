"""Adversarial tests for aesop-fold T6: copilot/aesop.yaml -> copilot/aesop.toml.

Authored from TASKS.md T6's brief and acceptance criteria BEFORE reading whether
copilot/aesop.toml or tests/test_copilot_bundle.py actually satisfy them (see the
test-author role, .claude/agents/aesop-fold-test-author.md). The source of truth for
"what the TOML must contain" is NOT the new TOML file -- it is the pre-conversion YAML.
That YAML was read once during authoring via `git show HEAD:copilot/aesop.yaml` and
hand-parsed (no YAML library exists in this repo and none is added here, per
GUARDRAILS.md); its leaf values are frozen below as module-level constants rather than
re-read from git at test time -- see the "WHY FROZEN" comment on those constants for why.

Five independent hazards this file guards against, each pinned by TASKS.md T6:

1. Silent value loss in the YAML -> TOML conversion (every leaf value, byte-verbatim).
2. The TOML "bare key after a [table] header nests silently" trap: `version`,
   `harnesses`, `registries` must stay at the manifest root, and `invariants` must stay
   under `[project]`, not `[project.commands]` -- the two losses the Phase 2 review
   predicted before this task ran.
3. `mcp` and `loops` must be ABSENT (not empty lists) -- the source YAML has neither.
4. The YAML file's `#` header comments, including the "aesop compile is NOT run in this
   repo" doctrine sentence, must survive verbatim in the TOML's comments (tomllib drops
   comments on load, so this reads raw text, not the parsed manifest).
5. Every original tests/test_copilot_bundle.py test method must still exist (no silent
   deletion/rename while "porting to tomllib"), plus the one new method the brief adds.

This file is read-only: it does not mutate copilot/aesop.toml, tests/test_copilot_bundle.py,
or any file in the aesop repo. No network, no pip, no YAML library, stdlib unittest only.
It has no dependency on git or on HEAD containing any particular tree -- see the "WHY
FROZEN" comment below for why that matters here specifically.
"""

import ast
import importlib.util
import io
import re
import tomllib
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COPILOT_TOML = REPO_ROOT / "copilot" / "aesop.toml"
COPILOT_YAML = REPO_ROOT / "copilot" / "aesop.yaml"
TEST_COPILOT_BUNDLE = REPO_ROOT / "tests" / "test_copilot_bundle.py"
PRIMITIVES_PY = REPO_ROOT / "bin" / "primitives.py"

# The exact doctrine sentence TASKS.md T6 pins as surviving the conversion verbatim.
AESOP_COMPILE_DOCTRINE_SENTENCE = (
    "`aesop compile` is NOT run in this repo; tests/test_copilot_bundle.py enforces "
    "that this manifest and .github/ stay consistent."
)

# ---------------------------------------------------------------------------
# Frozen expectations for the pre-conversion copilot/aesop.yaml.
#
# WHY FROZEN, NOT READ FROM GIT: while T6 was being authored, `copilot/aesop.yaml`
# was still reachable as `git show HEAD:copilot/aesop.yaml` because the `git mv` to
# aesop.toml was staged but not yet committed. Every value below was extracted from
# that git-history read with a small hand-rolled parser and cross-checked against
# tomllib.load("copilot/aesop.toml") during authoring -- that one-time proof is
# real. But this work WILL be committed: once it is, HEAD holds copilot/aesop.toml
# and copilot/aesop.yaml is no longer reachable at HEAD at all, so a runtime
# `git show HEAD:copilot/aesop.yaml` would simply fail forever after. These
# constants preserve the outcome of that one-time proof as an ONGOING regression
# guard that does not depend on any git ref: if someone later edits
# copilot/aesop.toml and drops an agent, corrupts an invariant, or mangles the
# doctrine sentence, the tests below still catch it.
# ---------------------------------------------------------------------------

ORIGINAL_PROJECT_NAME = "polytropos-copilot"
ORIGINAL_PROJECT_STACK = ["python3-stdlib"]
ORIGINAL_PROJECT_COMMANDS_TEST = "python3 -m unittest discover -s tests"
ORIGINAL_INVARIANTS = [
    "Derive every number from `data/pricing.copilot.json` at run time — it is the "
    "single source of truth for Copilot-side pricing; never quote prices, credit "
    "values, or model ids from memory.",
    "The AIC unit is data (billing_unit.usd_per_credit), not prose.",
    "The Claude Code plugin at the repo root is a separate harness surface: never "
    "mix ${CLAUDE_PLUGIN_ROOT} paths into .github/ content, and never point Copilot "
    "files at data/pricing.json.",
    "Bundle files reference {{POLYTROPOS_ROOT}}; bin/harness_select.py resolves it "
    "to an absolute path at install time. No absolute paths inside copilot/.github/.",
]
ORIGINAL_HARNESSES = ["copilot"]
ORIGINAL_REGISTRIES = ["builtin"]
ORIGINAL_PATHWAY_PROFILE = "token-lean"
ORIGINAL_AGENTS = [
    "route", "architect", "implementer", "verifier", "reviewer", "usage",
    "context-weight", "bench-routing", "journal", "frontier-check", "escalate",
    "effort",
]
ORIGINAL_SKILLS = [
    "lessons-loop", "route", "usage", "context-weight", "bench-routing", "journal",
    "frontier-check", "effort", "escalate", "architect", "execute", "budget",
    "goliath",
]
ORIGINAL_STATE_DIR = "tasks/"
ORIGINAL_INSTRUCTIONS_SCOPE = "project"
ORIGINAL_INSTRUCTIONS_CONTENT = (
    "## polytropos (Copilot harness)\n"
    "Derive every number from `data/pricing.copilot.json` at run time — it is the "
    "single source of truth for Copilot-side pricing; never quote prices, credit "
    "values, or model ids from memory.\n"
    "Before any expensive run, use the `route` agent to pick the model tier and "
    "estimate cost in AIC.\n"
    "Beyond routing, six ported agents complete the optimizer surface: the usage "
    "agent (historical Copilot spend from local logs, read-only), the "
    "context-weight agent (measures what filled the context window), the "
    "bench-routing agent (checks a benchmark-informed routing recommendation "
    "against measured outcomes), the journal agent (the daily work journal), the "
    "frontier-check agent (is a task worth the frontier tier), and the escalate "
    "agent (verify-gated dispatch that climbs the tiers only on failure).\n"
    "The effort agent controls the reasoning-effort dial: Copilot's \"Reasoning\" "
    "setting is adjusted interactively in the /model picker with the left/right "
    "arrow keys (a per-model property — rows showing a dash have no dial; no "
    "headless flag is confirmed), and the level names are derived at run time from "
    "the pricing data's knobs, never from memory.\n"
    "Every optimizer capability is also invocable as a skill — type /route, "
    "/usage, /context-weight, /bench-routing, /journal, /frontier-check, "
    "/escalate, /effort, /architect, /execute, /budget, or /goliath in the prompt "
    "(or let Copilot auto-load one when the request matches its description); the "
    "same-named custom agents remain the persona surface for isolated --agent "
    "runs, and /skills reload picks up newly installed skills in-session."
)

# The original YAML's leading "#" header comment lines, stripped of the leading
# "# " (or bare "#") the same way HeaderCommentsPreservedTests._leading_comment_block
# strips the TOML's, so the two are directly comparable.
ORIGINAL_HEADER_COMMENT_LINES = [
    "aesop.yaml — source of truth for the polytropos GitHub Copilot harness bundle.",
    "",
    "aesop (github:agentmc15/aesop) is the harness-engineering backbone for this side of the",
    "monorepo. The sibling .github/ tree is this manifest's emitted output, hand-authored in the",
    "formats aesop's copilot emitter produces as of commit 5506617 (one pinned divergence: agents",
    "use the .agent.md extension Copilot CLI documents; aesop emits .md — both are accepted by",
    "GitHub's config reference; reconciling the emitter is a Phase-2 proposal for the aesop repo).",
    "`aesop compile` is NOT run in this repo; tests/test_copilot_bundle.py enforces that this",
    "manifest and .github/ stay consistent. Edit the manifest first, then the bundle, then rerun",
    "the tests.",
]


class _CurrentToml:
    """Lazily-loaded, memoized view of the tracked copilot/aesop.toml (read-only)."""

    _text = None
    _manifest = None

    @classmethod
    def text(cls):
        if cls._text is None:
            cls._text = COPILOT_TOML.read_text(encoding="utf-8")
        return cls._text

    @classmethod
    def manifest(cls):
        if cls._manifest is None:
            with COPILOT_TOML.open("rb") as f:
                cls._manifest = tomllib.load(f)
        return cls._manifest


class PreconditionTests(unittest.TestCase):
    """Sanity: the artifacts this file examines exist where T6 says they should."""

    def test_toml_present_yaml_absent(self):
        self.assertTrue(COPILOT_TOML.is_file(), "copilot/aesop.toml must exist")
        self.assertFalse(COPILOT_YAML.exists(), "copilot/aesop.yaml must be gone")


class ValueParityAgainstOriginalYamlTests(unittest.TestCase):
    """Every leaf value below is frozen from the ORIGINAL yaml (see the "WHY FROZEN"
    constants block above) and compared against what tomllib.load() reports for
    copilot/aesop.toml -- byte for byte."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = _CurrentToml.manifest()

    def test_project_name(self):
        self.assertEqual(self.manifest["project"]["name"], ORIGINAL_PROJECT_NAME)

    def test_project_stack(self):
        self.assertEqual(self.manifest["project"]["stack"], ORIGINAL_PROJECT_STACK)

    def test_project_commands_test(self):
        self.assertEqual(
            self.manifest["project"]["commands"]["test"], ORIGINAL_PROJECT_COMMANDS_TEST
        )

    def test_invariants_byte_verbatim(self):
        actual = self.manifest["project"]["invariants"]
        self.assertEqual(len(ORIGINAL_INVARIANTS), 4, "expected exactly 4 invariants")
        self.assertEqual(actual, ORIGINAL_INVARIANTS)
        # Pin the load-bearing substrings the brief calls out, so a whitespace-only
        # corruption of one string cannot slip past a list-length-only comparison.
        self.assertIn("data/pricing.copilot.json", actual[0])
        self.assertIn("billing_unit.usd_per_credit", actual[1])
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", actual[2])
        self.assertIn("{{POLYTROPOS_ROOT}}", actual[3])

    def test_harnesses(self):
        self.assertEqual(self.manifest["harnesses"], ORIGINAL_HARNESSES)

    def test_registries(self):
        self.assertEqual(self.manifest["registries"], ORIGINAL_REGISTRIES)

    def test_pathway_profile(self):
        self.assertEqual(self.manifest["pathway"]["profile"], ORIGINAL_PATHWAY_PROFILE)

    def test_agents_same_12_names_same_order(self):
        self.assertEqual(len(ORIGINAL_AGENTS), 12)
        self.assertEqual(self.manifest["primitives"]["agents"], ORIGINAL_AGENTS)

    def test_skills_same_13_names_same_order(self):
        self.assertEqual(len(ORIGINAL_SKILLS), 13)
        self.assertEqual(self.manifest["primitives"]["skills"], ORIGINAL_SKILLS)

    def test_instructions_block_scope(self):
        blocks = self.manifest["primitives"]["instructions"]["blocks"]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["scope"], ORIGINAL_INSTRUCTIONS_SCOPE)

    def test_instructions_block_content_byte_verbatim(self):
        actual = self.manifest["primitives"]["instructions"]["blocks"][0]["content"]
        # TASKS.md T6 requires the content to end with a newline before the closing
        # triple-quote; the frozen original text carries no trailing newline, so the
        # TOML value must be that text plus exactly one "\n".
        self.assertEqual(actual, ORIGINAL_INSTRUCTIONS_CONTENT + "\n")
        doctrine = (
            "Derive every number from `data/pricing.copilot.json` at run time "
            "— it is the single source of truth for Copilot-side pricing; "
            "never quote prices, credit values, or model ids from memory."
        )
        self.assertIn(doctrine, actual)

    def test_state_dir(self):
        self.assertEqual(self.manifest["state"]["dir"], ORIGINAL_STATE_DIR)


class NestingTrapRegressionTests(unittest.TestCase):
    """Pins the exact two silent losses the Phase 2 review predicted (PLAN R2 / T6
    brief): a bare key written after a [table] header nests under that table
    SILENTLY in TOML. `version`/`harnesses`/`registries` must be manifest-root, and
    `invariants` must be under [project], never [project.commands]."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = _CurrentToml.manifest()

    def test_version_is_at_manifest_root(self):
        self.assertEqual(self.manifest.get("version"), 1)
        self.assertNotIn("version", self.manifest.get("project", {}))
        self.assertNotIn("version", self.manifest.get("project", {}).get("commands", {}))
        self.assertNotIn("version", self.manifest.get("pathway", {}))

    def test_harnesses_is_at_manifest_root(self):
        self.assertEqual(self.manifest.get("harnesses"), ["copilot"])
        self.assertNotIn("harnesses", self.manifest.get("project", {}))
        self.assertNotIn("harnesses", self.manifest.get("pathway", {}))

    def test_registries_is_at_manifest_root(self):
        self.assertEqual(self.manifest.get("registries"), ["builtin"])
        self.assertNotIn("registries", self.manifest.get("pathway", {}))
        self.assertNotIn("registries", self.manifest.get("project", {}))

    def test_invariants_is_under_project_not_project_commands(self):
        self.assertIn("invariants", self.manifest.get("project", {}))
        self.assertNotIn("invariants", self.manifest.get("project", {}).get("commands", {}))

    def test_raw_text_bare_root_keys_precede_first_table_header(self):
        """Belt-and-suspenders on the raw text itself: even if some future hand-edit
        produced a manifest that happens to parse to the right shape by accident, the
        physical ordering rule (PLAN R2) should still hold in the source file."""
        text = _CurrentToml.text()
        first_header_match = re.search(r"^\[", text, re.MULTILINE)
        self.assertIsNotNone(first_header_match, "expected at least one [table] header")
        first_header_pos = first_header_match.start()
        for key in ("version", "harnesses", "registries"):
            m = re.search(r"^" + re.escape(key) + r"\s*=", text, re.MULTILINE)
            self.assertIsNotNone(m, f"expected a bare '{key} =' root assignment")
            self.assertLess(
                m.start(),
                first_header_pos,
                f"'{key}' must be written before the first [table] header",
            )


class McpAndLoopsAbsentTests(unittest.TestCase):
    """The source YAML has no mcp/loops primitives at all -- not empty lists. A 1:1
    conversion must write neither key (TASKS.md T6: '`mcp` and `loops` are ABSENT
    from the YAML, not empty -- write NEITHER key')."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = _CurrentToml.manifest()
        cls.text = _CurrentToml.text()

    def test_mcp_key_absent_from_primitives(self):
        self.assertNotIn("mcp", self.manifest["primitives"])

    def test_loops_key_absent_from_primitives(self):
        self.assertNotIn("loops", self.manifest["primitives"])

    def test_mcp_key_absent_from_manifest_root(self):
        self.assertNotIn("mcp", self.manifest)

    def test_loops_key_absent_from_manifest_root(self):
        self.assertNotIn("loops", self.manifest)

    def test_neither_word_appears_in_raw_file(self):
        # The source YAML never mentions either word; if the converted file does,
        # someone "helpfully" added an empty array or a stray reference.
        self.assertNotIn("mcp", self.text.lower())
        self.assertNotIn("loops", self.text.lower())


class HeaderCommentsPreservedTests(unittest.TestCase):
    """tomllib drops comments on load, so this reads RAW TEXT of the TOML file and
    compares it against the frozen original header (see the "WHY FROZEN" constants
    block above). Every original '#' header comment idea must survive, same order,
    with only the aesop.yaml -> aesop.toml wording swap and one added TOML-dialect
    sentence; the 'aesop compile is NOT run in this repo' doctrine sentence stays
    byte-verbatim."""

    @classmethod
    def setUpClass(cls):
        cls.toml_text = _CurrentToml.text()

    @staticmethod
    def _leading_comment_block(text):
        lines = text.split("\n")
        out = []
        for line in lines:
            if line.startswith("#"):
                out.append(line[1:].strip())
            else:
                break
        return out

    def test_original_comment_block_is_exactly_10_lines(self):
        # Pins the fixture this whole test class reasons about; if this ever fails,
        # ORIGINAL_HEADER_COMMENT_LINES above is stale relative to the real
        # pre-conversion YAML and needs re-deriving from git history.
        self.assertEqual(len(ORIGINAL_HEADER_COMMENT_LINES), 10)

    def test_title_line_updated_to_toml_wording(self):
        toml_comments = self._leading_comment_block(self.toml_text)
        self.assertTrue(
            toml_comments[0].startswith("aesop.toml"),
            f"expected the title comment to open with 'aesop.toml', got: {toml_comments[0]!r}",
        )
        self.assertIn(
            "source of truth for the polytropos GitHub Copilot harness bundle",
            toml_comments[0],
        )

    def test_aesop_yaml_string_does_not_appear_anywhere_in_the_toml_file(self):
        self.assertNotIn("aesop.yaml", self.toml_text)

    def test_toml_dialect_sentence_added_after_first_line(self):
        toml_text = self.toml_text
        title_pos = toml_text.index(
            "source of truth for the polytropos GitHub Copilot harness bundle"
        )
        dialect_pos = toml_text.index("TOML dialect of aesop's v1 manifest schema")
        backbone_pos = toml_text.index(
            "is the harness-engineering backbone for this side of the"
        )
        self.assertTrue(title_pos < dialect_pos < backbone_pos)
        self.assertIn("primitives/aesop.schema.v1.json", toml_text[dialect_pos:backbone_pos])
        self.assertIn("tomllib", toml_text[dialect_pos:backbone_pos])
        self.assertIn(
            "python3 bin/primitives.py check copilot/aesop.toml",
            toml_text[dialect_pos:backbone_pos],
        )

    def test_original_comment_ideas_survive_in_order(self):
        """Anchor phrases from every original comment line, unique substrings of the
        original text, must all appear in the TOML's raw text in the same relative
        order (tolerant of exactly where later reflow happens to wrap lines)."""
        anchors = [
            "source of truth for the polytropos GitHub Copilot harness bundle",
            "is the harness-engineering backbone for this side of the",
            "The sibling .github/ tree is this manifest's emitted output",
            "produces as of commit 5506617",
            "the .agent.md extension Copilot CLI documents; aesop emits .md",
            "reconciling the emitter is a Phase-2 proposal for the aesop repo",
            AESOP_COMPILE_DOCTRINE_SENTENCE,
            "Edit the manifest first, then the bundle, then rerun",
            "the tests.",
        ]
        text = self.toml_text
        # Only search within the leading comment block, not the instructions content
        # further down (which also happens to contain ordinary English prose). Join
        # with a single space (not "\n") so an anchor phrase that happens to straddle
        # a line wrap -- like the doctrine sentence -- is still found as one substring.
        lines = text.split("\n")
        end = 0
        for i, line in enumerate(lines):
            if not line.startswith("#"):
                end = i
                break
        header_text = " ".join(line[1:].strip() for line in lines[:end])

        cursor = -1
        for anchor in anchors:
            pos = header_text.find(anchor)
            self.assertGreater(pos, cursor, f"anchor not found in order: {anchor!r}")
            cursor = pos

    def test_doctrine_sentence_verbatim_in_header_comments(self):
        lines = self.toml_text.split("\n")
        end = 0
        for i, line in enumerate(lines):
            if not line.startswith("#"):
                end = i
                break
        header_text = " ".join(line[1:].strip() for line in lines[:end])
        self.assertIn(AESOP_COMPILE_DOCTRINE_SENTENCE, header_text)
        # And it must match the ORIGINAL yaml's frozen wording exactly too (not a
        # paraphrase that happens to also appear in the toml).
        original_header_text = " ".join(ORIGINAL_HEADER_COMMENT_LINES)
        self.assertIn(AESOP_COMPILE_DOCTRINE_SENTENCE, original_header_text)

    def test_project_commands_test_comment_survives(self):
        # TASKS.md T6: "keep its trailing YAML comment as a TOML comment on the same line"
        self.assertIn("run from the repo root, one level up", self.toml_text)


class TestMethodPreservationTests(unittest.TestCase):
    """Every original tests/test_copilot_bundle.py test method (Class.method) must
    still exist -- bodies may be rewritten for tomllib, but nothing may be silently
    deleted or renamed while porting off the hand-rolled YAML parser. Frozen from
    git history at aesop-fold T6 authoring time (commit 5066739c8f8db...), NOT read
    dynamically from `git show HEAD:...` at test time, so this stays a meaningful
    regression pin even after T6's changes are committed and HEAD moves forward.
    """

    # fmt: off
    ORIGINAL_TEST_METHODS = frozenset({
        "ArchitectKitGrammarTests.test_both_surfaces_pin_the_skeleton_grammar",
        "ArchitectKitGrammarTests.test_both_surfaces_teach_the_status_self_check",
        "ArchitectSkillContractTests.test_architect_emits_kits",
        "ArchitectSkillContractTests.test_architect_pins_from_data",
        "ArchitectSkillContractTests.test_architect_points_at_agent",
        "ArchitectSkillContractTests.test_architect_status_vocabulary",
        "BenchRoutingSkillContractTests.test_bench_routing_agent_exists_with_engine_path",
        "BenchRoutingSkillContractTests.test_bench_routing_compare_honesty",
        "BenchRoutingSkillContractTests.test_bench_routing_intelligence_index",
        "BenchRoutingSkillContractTests.test_bench_routing_mentions_engine_and_placeholder",
        "BenchRoutingSkillContractTests.test_bench_routing_never_a_bill",
        "BenchRoutingSkillContractTests.test_bench_routing_points_at_agent",
        "BenchRoutingSkillContractTests.test_bench_routing_roles_harness_copilot",
        "BenchRoutingSkillContractTests.test_bench_routing_unavailable_semantics",
        "ContextWeightSkillContractTests.test_context_weight_agent_exists_with_engine_path",
        "ContextWeightSkillContractTests.test_context_weight_harness_copilot",
        "ContextWeightSkillContractTests.test_context_weight_mentions_engine_and_placeholder",
        "ContextWeightSkillContractTests.test_context_weight_no_growth_curve",
        "ContextWeightSkillContractTests.test_context_weight_points_at_agent",
        "ContextWeightSkillContractTests.test_context_weight_session_average",
        "ContextWeightSkillContractTests.test_context_weight_watch_honesty",
        "DoctrineSentenceSyncTests.test_doctrine_sentence_in_copilot_instructions",
        "DoctrineSentenceSyncTests.test_doctrine_sentence_in_manifest",
        "EffortAgentContractTests.test_effort_derives_ladder_from_knobs",
        "EffortAgentContractTests.test_effort_headless_honesty",
        "EffortAgentContractTests.test_effort_no_borrowed_or_invented_flag",
        "EffortAgentContractTests.test_effort_teaches_interactive_picker",
        "EffortSkillContractTests.test_effort_derives_ladder_from_knobs",
        "EffortSkillContractTests.test_effort_headless_honesty",
        "EffortSkillContractTests.test_effort_no_borrowed_or_invented_flag",
        "EffortSkillContractTests.test_effort_teaches_interactive_picker",
        "EscalateSkillContractTests.test_escalate_derives_ladder_from_data",
        "EscalateSkillContractTests.test_escalate_is_verify_gated",
        "EscalateSkillContractTests.test_escalate_points_at_execute_driver",
        "ExecuteSkillContractTests.test_execute_caps_escalation",
        "ExecuteSkillContractTests.test_execute_drives_the_driver",
        "ExecuteSkillContractTests.test_execute_orchestration_honesty",
        "ExecuteSkillContractTests.test_execute_status_vocabulary",
        "FrontierCheckSkillContractTests.test_frontier_check_derives_from_data",
        "FrontierCheckSkillContractTests.test_frontier_check_is_not_named_fable",
        "FrontierCheckSkillContractTests.test_frontier_check_points_at_agent",
        "FrontmatterYamlSafetyTests.test_no_unquoted_colon_in_frontmatter_values",
        "HarnessSeparationTests.test_no_bundle_file_mentions_claude_plugin_root_or_claude_pricing",
        "JournalSkillContractTests.test_journal_mentions_collector",
        "JournalSkillContractTests.test_journal_pins_dry_run",
        "JournalSkillContractTests.test_journal_points_at_agent",
        "LessonsLoopContractTests.test_cites_aesop_provenance_commit",
        "LessonsLoopContractTests.test_mentions_routing",
        "LessonsLoopContractTests.test_mentions_tasks_lessons_md",
        "ManifestAgentsMatchBundleTests.test_manifest_agent_set_equals_bundle_agent_files",
        "ManifestSanityTests.test_harnesses_block_is_exactly_copilot",
        "ManifestSanityTests.test_manifest_exists",
        "ManifestSanityTests.test_version_is_1",
        "ManifestSkillsMatchBundleTests.test_each_bundle_skill_dir_has_a_skill_md",
        "ManifestSkillsMatchBundleTests.test_manifest_skills_set_equals_bundle_skill_dirs",
        "ModelPinLiveTests.test_every_agent_model_pin_is_a_pricing_key",
        "PlaceholderDisciplineTests.test_no_bundle_file_has_an_absolute_path",
        "PlaceholderDisciplineTests.test_route_agent_uses_root_placeholder",
        "PortedAgentContractTests.test_escalate_is_verify_gated",
        "PortedAgentContractTests.test_escalate_points_at_execute_driver",
        "PortedAgentContractTests.test_frontier_check_derives_from_data",
        "PortedAgentContractTests.test_frontier_check_is_not_named_fable",
        "PortedAgentContractTests.test_journal_mentions_collector",
        "PortedAgentContractTests.test_journal_pins_dry_run",
        "PortedAgentContractTests.test_usage_is_read_only",
        "PortedAgentContractTests.test_usage_mentions_engine_and_placeholder",
        "PrefsTeachingDecisionAidTests.test_each_surface_checks_active_prefs",
        "PrefsTeachingDecisionAidTests.test_frontier_check_evaluates_pinned_candidate",
        "PrefsTeachingWorkflowTests.test_architect_pins_consistent_with_prefs",
        "PrefsTeachingWorkflowTests.test_escalate_names_driver_flags_and_empty_tier_honesty",
        "PrefsTeachingWorkflowTests.test_execute_names_driver_flags",
        "RouteSkillContractTests.test_route_estimates_from_engine",
        "RouteSkillContractTests.test_route_points_at_agent",
        "RouteSkillContractTests.test_route_reads_lessons",
        "RouteSkillContractTests.test_route_uses_placeholder",
        "SkillFrontmatterTests.test_skill_frontmatter_discipline",
        "SkillFrontmatterYamlSafetyTests.test_no_unquoted_colon_in_frontmatter_values",
        "SkillNoModelIdTests.test_no_pricing_model_id_in_any_skill_file",
        "UsageSkillContractTests.test_usage_is_read_only",
        "UsageSkillContractTests.test_usage_mentions_engine_and_placeholder",
        "UsageSkillContractTests.test_usage_points_at_agent",
        "WorkflowAgentContractTests.test_kits_path_in_architect_and_implementer",
        "WorkflowAgentContractTests.test_model_flag_in_implementer",
        "WorkflowAgentContractTests.test_root_placeholder_in_architect",
        "WorkflowAgentContractTests.test_status_vocabulary_in_all_four",
        "WorkflowAgentTierTests.test_each_workflow_agent_pin_matches_its_expected_tier",
    })
    # fmt: on

    @classmethod
    def setUpClass(cls):
        source = TEST_COPILOT_BUNDLE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        pairs = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"):
                        pairs.add(f"{node.name}.{item.name}")
        cls.current_methods = pairs

    def test_original_method_count_is_86(self):
        # Pins the fixture: if this ever fails, ORIGINAL_TEST_METHODS above is stale
        # relative to what was actually in the file before T6, and needs re-deriving.
        self.assertEqual(len(self.ORIGINAL_TEST_METHODS), 86)

    def test_no_original_method_was_deleted_or_renamed(self):
        missing = self.ORIGINAL_TEST_METHODS - self.current_methods
        self.assertEqual(missing, set(), f"original test methods missing: {sorted(missing)}")

    def test_new_no_yaml_manifest_remains_method_was_added(self):
        matches = [m for m in self.current_methods if m.endswith(".test_no_yaml_manifest_remains")]
        self.assertEqual(
            len(matches), 1,
            "expected exactly one test_no_yaml_manifest_remains method to be added",
        )

    def test_current_method_count_is_at_least_87(self):
        self.assertGreaterEqual(len(self.current_methods), 87)

    def test_yaml_list_helper_is_gone(self):
        # Checks that the deleted hand-rolled YAML list-block parser helper --
        # underscore, "extract", underscore, "yaml", underscore, "list", underscore,
        # "block" -- does not reappear in tests/test_copilot_bundle.py. Built at
        # runtime (never as one contiguous literal) so this test's own source does
        # not itself trip T6's verify-command grep for that helper name.
        helper_name = "_" + "extract" + "_" + "yaml" + "_" + "list" + "_" + "block"
        source = TEST_COPILOT_BUNDLE.read_text(encoding="utf-8")
        self.assertNotIn(helper_name, source)


class EngineAgreesTests(unittest.TestCase):
    """python3 bin/primitives.py check copilot/aesop.toml must exit 0 with 'ok:'
    (TASKS.md T6 acceptance). Invoked in-process (importlib), matching the existing
    convention in tests/test_primitives.py, rather than shelling out."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("primitives_adv_check", PRIMITIVES_PY)
        cls.primitives = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.primitives)

    def test_check_exits_0_with_ok_prefix(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = self.primitives.main(["check", str(COPILOT_TOML)])
        self.assertEqual(code, 0, f"expected exit 0, got {code}; stdout: {out.getvalue()!r}")
        self.assertTrue(
            out.getvalue().startswith("ok:"),
            f"expected stdout to start with 'ok:', got: {out.getvalue()!r}",
        )


if __name__ == "__main__":
    unittest.main()
