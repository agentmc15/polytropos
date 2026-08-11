"""Stdlib unittest suite enforcing codex/ bundle consistency + the codex installer contract.

Per PLAN.md D5, there is deliberately NO `codex/aesop.yaml` (aesop@5506617 has no codex
emitter), so this test file IS the enforcement mechanism the copilot side gets from
`tests/test_copilot_bundle.py` (read as the template for the bundle-contract half) -- it reads
`codex/AGENTS.md` and `codex/prompts/*.md` as plain text and cross-checks them against
`data/pricing.codex.json`. It also carries the codex installer tests that PLAN.md D6 keeps out
of the frozen `tests/test_harness_select.py` (mirrored in style from that file's
`InstallCopilot*`/`DetectTests` classes).

SAFETY: every `install_codex` call in this file passes an explicit home directory rooted under
a `tempfile.TemporaryDirectory()`. Nothing here ever reads or writes the real `~/.codex` --
`Path.home()` is never invoked, and the real `codex` CLI is never invoked in any form. This
file reads bundle/pricing files only otherwise: no writes, no network.
"""

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
REPO_ROOT = Path(__file__).resolve().parent.parent
CODEX_DIR = REPO_ROOT / "codex"
CODEX_AGENTS_MD = CODEX_DIR / "AGENTS.md"
CODEX_PROMPTS_DIR = CODEX_DIR / "prompts"
CODEX_SKILLS_DIR = CODEX_DIR / "skills"
PRICING_CODEX_JSON = REPO_ROOT / "data" / "pricing.codex.json"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hs = _load("harness_select")


# Pinned verbatim in TASKS.md T8 / PLAN.md -- the doctrine sentence that must appear, byte for
# byte (backticks included), in codex/AGENTS.md.
DOCTRINE_SENTENCE = (
    "Derive every number from `data/pricing.codex.json` at run time — it is the single "
    "source of truth for Codex-side pricing; never quote prices, plan limits, or model ids "
    "from memory."
)

PORTED_PROMPT_STEMS = ("usage", "journal", "frontier-check", "escalate")

EXPECTED_PROMPT_STEMS = {"route", "architect", "implementer", "verifier", "reviewer"} | set(PORTED_PROMPT_STEMS) | {"effort"}

# The Codex desktop app reads Agent Skills under <codex-home>/skills/<name>/, NOT prompts. The
# user-facing prompts are mirrored there as SKILL.md skill dirs so /usage etc. surface in the
# desktop app's `/`-palette Skills section as well as the terminal CLI's prompt list. The four
# ported capabilities plus the two workflow commands a user types (architect, route); the
# execution-loop roles (implementer/verifier/reviewer) are CLI-prompt-only dispatch targets, so
# they are deliberately NOT skills.
PORTED_SKILL_STEMS = ("usage", "journal", "frontier-check", "escalate")
WORKFLOW_SKILL_STEMS = ("architect", "route")
EXPECTED_SKILL_STEMS = (
    set(PORTED_SKILL_STEMS)
    | set(WORKFLOW_SKILL_STEMS)
    | {"effort", "execute", "doctor", "context-weight", "bench-routing", "memory"}
)


def _iter_bundle_files():
    return sorted(p for p in CODEX_DIR.rglob("*") if p.is_file())


def _frontmatter(text):
    """Return the YAML frontmatter block (between the first pair of `---` lines) as text."""
    parts = text.split("---")
    # parts[0] is empty/whitespace before the first '---'; parts[1] is the frontmatter body.
    return parts[1]


# ---- Bundle contract cases (read files only) -----------------------------------------------


class DoctrineSentenceTests(unittest.TestCase):
    """Case 1: the doctrine sentence appears verbatim in codex/AGENTS.md."""

    def test_doctrine_sentence_in_agents_md(self):
        text = CODEX_AGENTS_MD.read_text()
        self.assertIn(DOCTRINE_SENTENCE, text)


class PromptRosterTests(unittest.TestCase):
    """Case 2: codex/prompts/ contains exactly the expected workflow + ported prompts, no
    more, no less."""

    def test_prompt_roster_matches_expected_stems(self):
        stems = {p.name[: -len(".md")] for p in CODEX_PROMPTS_DIR.glob("*.md")}
        self.assertEqual(stems, EXPECTED_PROMPT_STEMS)


class FrontmatterDisciplineTests(unittest.TestCase):
    """Case 3: every prompt has a description: line and NO model: line in its frontmatter."""

    def test_every_prompt_has_description_and_no_model_pin(self):
        for stem in sorted(EXPECTED_PROMPT_STEMS):
            path = CODEX_PROMPTS_DIR / f"{stem}.md"
            with self.subTest(prompt=stem):
                self.assertTrue(path.is_file(), f"missing {path}")
                fm = _frontmatter(path.read_text())
                self.assertRegex(fm, r"(?m)^description:\s*\S")
                self.assertNotRegex(fm, r"(?m)^model:\s*\S")


class PlaceholderDisciplineTests(unittest.TestCase):
    """Case 4: {{POLYTROPOS_ROOT}} used in route.md and architect.md; no absolute paths
    anywhere under codex/."""

    def test_placeholder_in_route_and_architect(self):
        for stem in ("route", "architect"):
            with self.subTest(prompt=stem):
                path = CODEX_PROMPTS_DIR / f"{stem}.md"
                text = path.read_text()
                self.assertIn(hs.PLACEHOLDER, text)

    def test_no_bundle_file_has_an_absolute_path(self):
        offenders = []
        for path in _iter_bundle_files():
            text = path.read_text()
            if "/Users/" in text or "/home/" in text:
                offenders.append(str(path))
        self.assertEqual(offenders, [], f"absolute paths found in: {offenders}")


class HarnessSeparationTests(unittest.TestCase):
    """Case 5: no file under codex/ mentions CLAUDE_PLUGIN_ROOT, data/pricing.json, or
    data/pricing.copilot.json (plain substring checks -- data/pricing.json is not a substring
    of data/pricing.codex.json)."""

    def test_no_bundle_file_mentions_other_harness_surfaces(self):
        offenders = []
        for path in _iter_bundle_files():
            text = path.read_text()
            if (
                "CLAUDE_PLUGIN_ROOT" in text
                or "data/pricing.json" in text
                or "data/pricing.copilot.json" in text
            ):
                offenders.append(str(path))
        self.assertEqual(offenders, [], f"other-harness references found in: {offenders}")


class NoHardcodedRosterTests(unittest.TestCase):
    """Case 6: no file under codex/ contains any model id key from the real
    data/pricing.codex.json (loaded at test run time -- ids never appear as literals here
    either)."""

    def test_no_bundle_file_contains_a_real_model_id_literal(self):
        pricing = json.loads(PRICING_CODEX_JSON.read_text())
        model_ids = list(pricing["models"].keys())
        self.assertTrue(model_ids, "pricing.codex.json models: empty")

        offenders = []
        for path in _iter_bundle_files():
            text = path.read_text()
            for model_id in model_ids:
                if model_id in text:
                    offenders.append(f"{path}: {model_id}")
        self.assertEqual(offenders, [], f"hardcoded model ids found: {offenders}")


class PortedPromptContractTests(unittest.TestCase):
    """Case: contract checks specific to the ported (non-workflow) prompts in
    PORTED_PROMPT_STEMS -- grown additively across T2/T4/T6/T8."""

    def _text(self, stem):
        return (CODEX_PROMPTS_DIR / f"{stem}.md").read_text()

    def test_placeholder_in_all_ported_prompts(self):
        for stem in PORTED_PROMPT_STEMS:
            with self.subTest(prompt=stem):
                self.assertIn(hs.PLACEHOLDER, self._text(stem))

    def test_no_fable_in_any_ported_prompt(self):
        for stem in PORTED_PROMPT_STEMS:
            with self.subTest(prompt=stem):
                self.assertNotIn("fable", self._text(stem).lower())

    def test_usage_mentions_engine_and_proxy(self):
        text = self._text("usage")
        self.assertIn("bin/codex_usage.py", text)
        self.assertIn("proxy", text)

    def test_journal_mentions_collector_and_dry_run(self):
        text = self._text("journal")
        self.assertIn("bin/journal_collect.py", text)
        self.assertIn("--dry-run", text)

    def test_frontier_check_derives_from_data(self):
        text = self._text("frontier-check")
        self.assertIn("bin/codex_pricing.py", text)
        self.assertIn("frontier", text)

    def test_escalate_dispatches_and_points_at_driver(self):
        text = self._text("escalate")
        self.assertIn("codex exec", text)
        self.assertIn("bin/codex_execute.py", text)


class EffortPromptContractTests(unittest.TestCase):
    """Contract checks for the effort prompt (PLAN.md D7/D8) -- derives the ladder from data,
    quotes the real confirmed flag and driver, and never enumerates the level tokens."""

    def _text(self):
        return (CODEX_PROMPTS_DIR / "effort.md").read_text()

    def test_effort_derives_ladder_from_knobs(self):
        text = self._text()
        self.assertIn("bin/codex_pricing.py", text)
        self.assertIn("knobs", text)

    def test_effort_quotes_real_flag_and_driver(self):
        text = self._text()
        self.assertIn("model_reasoning_effort", text)
        self.assertIn("bin/codex_execute.py", text)
        self.assertIn("--effort", text)

    def test_effort_no_level_enumeration(self):
        self.assertNotIn("minimal", self._text())


# ---- Skills bundle cases (Codex desktop-app Agent-Skills surface) --------------------------


class SkillRosterTests(unittest.TestCase):
    """codex/skills/ contains exactly the four ported skills, each a dir with a SKILL.md."""

    def test_skill_roster_matches_expected_stems(self):
        self.assertTrue(CODEX_SKILLS_DIR.is_dir(), f"missing {CODEX_SKILLS_DIR}")
        stems = {p.name for p in CODEX_SKILLS_DIR.iterdir() if p.is_dir()}
        self.assertEqual(stems, EXPECTED_SKILL_STEMS)

    def test_every_skill_has_a_skill_md(self):
        for stem in sorted(EXPECTED_SKILL_STEMS):
            with self.subTest(skill=stem):
                self.assertTrue((CODEX_SKILLS_DIR / stem / "SKILL.md").is_file())


class SkillFrontmatterTests(unittest.TestCase):
    """Every SKILL.md has name: (matching its dir) and description: in frontmatter, and NO
    model: pin — the desktop app supplies its own model, exactly as the CLI prompts carry no
    model: line."""

    def test_name_matches_dir_and_has_description_no_model(self):
        for stem in sorted(EXPECTED_SKILL_STEMS):
            path = CODEX_SKILLS_DIR / stem / "SKILL.md"
            with self.subTest(skill=stem):
                fm = _frontmatter(path.read_text())
                self.assertRegex(fm, r"(?m)^name:\s*" + stem + r"\s*$")
                self.assertRegex(fm, r"(?m)^description:\s*\S")
                self.assertNotRegex(fm, r"(?m)^model:\s*\S")


class PortedSkillContractTests(unittest.TestCase):
    """The skills carry the SAME engine references and honesty discipline as the ported
    prompts — mirrors PortedPromptContractTests against codex/skills/<name>/SKILL.md."""

    def _text(self, stem):
        return (CODEX_SKILLS_DIR / stem / "SKILL.md").read_text()

    def test_placeholder_in_all_ported_skills(self):
        for stem in EXPECTED_SKILL_STEMS:
            with self.subTest(skill=stem):
                self.assertIn(hs.PLACEHOLDER, self._text(stem))

    def test_no_fable_in_any_ported_skill(self):
        for stem in EXPECTED_SKILL_STEMS:
            with self.subTest(skill=stem):
                self.assertNotIn("fable", self._text(stem).lower())

    def test_usage_mentions_engine_and_proxy(self):
        text = self._text("usage")
        self.assertIn("bin/codex_usage.py", text)
        self.assertIn("proxy", text)

    def test_journal_mentions_collector_and_dry_run(self):
        text = self._text("journal")
        self.assertIn("bin/journal_collect.py", text)
        self.assertIn("--dry-run", text)

    def test_frontier_check_derives_from_data(self):
        text = self._text("frontier-check")
        self.assertIn("bin/codex_pricing.py", text)
        self.assertIn("frontier", text)

    def test_escalate_dispatches_and_points_at_driver(self):
        text = self._text("escalate")
        self.assertIn("codex exec", text)
        self.assertIn("bin/codex_execute.py", text)


class WorkflowSkillContractTests(unittest.TestCase):
    """The two workflow skills (architect, route) carry the same engine wiring and shared kit
    contract as their CLI prompts."""

    def _text(self, stem):
        return (CODEX_SKILLS_DIR / stem / "SKILL.md").read_text()

    def test_architect_emits_kit_and_names_the_driver(self):
        text = self._text("architect")
        self.assertIn("bin/codex_execute.py", text)
        self.assertIn("bin/codex_pricing.py", text)
        self.assertIn("tasks/kits/", text)
        # Shared kit contract: exact status vocabulary must survive verbatim.
        self.assertIn("pending | in-progress | done | blocked", text)

    def test_route_estimates_and_dispatches(self):
        text = self._text("route")
        self.assertIn("bin/codex_pricing.py", text)
        self.assertIn("codex exec", text)


class EffortSkillContractTests(unittest.TestCase):
    """Contract checks for the effort skill (PLAN.md D7/D8) -- mirrors
    EffortPromptContractTests against codex/skills/effort/SKILL.md."""

    def _text(self):
        return (CODEX_SKILLS_DIR / "effort" / "SKILL.md").read_text()

    def test_effort_derives_ladder_from_knobs(self):
        text = self._text()
        self.assertIn("bin/codex_pricing.py", text)
        self.assertIn("knobs", text)

    def test_effort_quotes_real_flag_and_driver(self):
        text = self._text()
        self.assertIn("model_reasoning_effort", text)
        self.assertIn("bin/codex_execute.py", text)
        self.assertIn("--effort", text)

    def test_effort_no_level_enumeration(self):
        self.assertNotIn("minimal", self._text())


# ---- Installer cases (mirror tests/test_harness_select.py's style) --------------------------

# Fake bundle content -- deliberately not real route.md text, just something with the
# placeholder appearing twice plus surrounding text that must survive byte-identical.
FAKE_PROMPT_TEXT = (
    "---\n"
    "description: fake prompt fixture for tests\n"
    "---\n"
    "\n"
    "Repo root is {{POLYTROPOS_ROOT}}.\n"
    "Pricing data lives at {{POLYTROPOS_ROOT}}/data/pricing.codex.json.\n"
    "Nothing else here should change.\n"
)

# Fake AGENTS.md content -- deliberately not the real codex/AGENTS.md text.
FAKE_AGENTS_MD_TEXT = (
    "# fake codex AGENTS.md fixture\n"
    "\n"
    "Repo root is {{POLYTROPOS_ROOT}}.\n"
    "Nothing else here should change.\n"
)


def _make_fake_repo_root(tmp_path, prompt_text=FAKE_PROMPT_TEXT, filename="route.md"):
    """Build `<tmp_path>/codex/prompts/<filename>` with `prompt_text`."""
    prompts_dir = tmp_path / "codex" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / filename).write_text(prompt_text)
    return tmp_path


def _add_fake_agents_md(tmp_path, agents_text=FAKE_AGENTS_MD_TEXT):
    """Add `<tmp_path>/codex/AGENTS.md` with `agents_text` to an existing fake repo root."""
    agents_path = tmp_path / "codex" / "AGENTS.md"
    agents_path.parent.mkdir(parents=True, exist_ok=True)
    agents_path.write_text(agents_text)
    return tmp_path


# Fake skill content -- placeholder appears twice; everything else must survive byte-identical.
FAKE_SKILL_TEXT = (
    "---\n"
    "name: fakeskill\n"
    "description: fake skill fixture for tests\n"
    "---\n"
    "\n"
    "Repo root is {{POLYTROPOS_ROOT}}.\n"
    "Data lives at {{POLYTROPOS_ROOT}}/data/pricing.codex.json.\n"
    "Nothing else here should change.\n"
)


def _add_fake_skill(tmp_path, name="fakeskill", text=FAKE_SKILL_TEXT):
    """Add `<tmp_path>/codex/skills/<name>/SKILL.md` with `text` to a fake repo root."""
    skill_dir = tmp_path / "codex" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(text)
    return tmp_path


def _result_map(results):
    """Turn the `install_codex` list of `(dest_path, action)` tuples into a dict keyed by
    dest_path for easy lookup in assertions."""
    return {dest: action for dest, action in results}


class InstallCodexPlaceholderTests(unittest.TestCase):
    """Case 7: placeholder resolution -- route.md (placeholder x2) + AGENTS.md, both written
    with all occurrences replaced and everything else byte-identical."""

    def test_placeholder_replaced_both_occurrences_rest_identical(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = _make_fake_repo_root(Path(tmp_root_s))
            _add_fake_agents_md(tmp_root)
            tmp_home = Path(tmp_home_s)

            results = hs.install_codex(tmp_home, repo_root=tmp_root)
            actions = _result_map(results)

            prompt_dest = tmp_home / "prompts" / "route.md"
            agents_dest = tmp_home / "AGENTS.md"
            self.assertEqual(actions.get(prompt_dest), "install")
            self.assertEqual(actions.get(agents_dest), "install")

            written_prompt = prompt_dest.read_text()
            expected_prompt = FAKE_PROMPT_TEXT.replace(hs.PLACEHOLDER, str(tmp_root))
            self.assertEqual(written_prompt, expected_prompt)
            self.assertNotIn(hs.PLACEHOLDER, written_prompt)
            self.assertEqual(written_prompt.count(str(tmp_root)), 2)
            self.assertIn("description: fake prompt fixture for tests\n", written_prompt)
            self.assertIn("Nothing else here should change.\n", written_prompt)

            written_agents = agents_dest.read_text()
            expected_agents = FAKE_AGENTS_MD_TEXT.replace(hs.PLACEHOLDER, str(tmp_root))
            self.assertEqual(written_agents, expected_agents)
            self.assertNotIn(hs.PLACEHOLDER, written_agents)


class InstallCodexDryRunTests(unittest.TestCase):
    """Case 8: dry-run -- same destination list, no files/dirs created."""

    def test_dry_run_returns_dest_list_but_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = _make_fake_repo_root(Path(tmp_root_s))
            _add_fake_agents_md(tmp_root)
            tmp_home = Path(tmp_home_s)

            results = hs.install_codex(tmp_home, repo_root=tmp_root, dry_run=True)
            actions = _result_map(results)

            prompt_dest = tmp_home / "prompts" / "route.md"
            agents_dest = tmp_home / "AGENTS.md"
            self.assertIn(prompt_dest, actions)
            self.assertIn(agents_dest, actions)

            # dry-run must create nothing at all.
            self.assertFalse((tmp_home / "prompts").exists())
            self.assertFalse(agents_dest.exists())
            self.assertEqual(list(tmp_home.iterdir()), [])


class InstallCodexIdempotenceTests(unittest.TestCase):
    """Case 9: two installs -> same content; AGENTS.md second pass reports up-to-date."""

    def test_install_twice_same_content_agents_md_up_to_date(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = _make_fake_repo_root(Path(tmp_root_s))
            _add_fake_agents_md(tmp_root)
            tmp_home = Path(tmp_home_s)

            first_results = hs.install_codex(tmp_home, repo_root=tmp_root)
            first_actions = _result_map(first_results)
            prompt_dest = tmp_home / "prompts" / "route.md"
            agents_dest = tmp_home / "AGENTS.md"
            first_prompt_text = prompt_dest.read_text()
            first_agents_text = agents_dest.read_text()
            self.assertEqual(first_actions.get(agents_dest), "install")

            second_results = hs.install_codex(tmp_home, repo_root=tmp_root)
            second_actions = _result_map(second_results)
            second_prompt_text = prompt_dest.read_text()
            second_agents_text = agents_dest.read_text()

            self.assertEqual(first_prompt_text, second_prompt_text)
            self.assertEqual(first_agents_text, second_agents_text)
            self.assertEqual(second_actions.get(agents_dest), "up-to-date")
            # Not doubled/appended.
            self.assertEqual(
                second_prompt_text.count("description: fake prompt fixture for tests"), 1
            )


class InstallCodexNoClobberTests(unittest.TestCase):
    """Case 10: pre-seeded differing <home>/AGENTS.md is byte-identical after install;
    prompts still installed."""

    def test_preseeded_differing_agents_md_survives_untouched(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = _make_fake_repo_root(Path(tmp_root_s))
            _add_fake_agents_md(tmp_root)
            tmp_home = Path(tmp_home_s)

            preseeded_text = "# the user's own global Codex instructions\nDo not touch this.\n"
            (tmp_home / "AGENTS.md").write_text(preseeded_text)

            results = hs.install_codex(tmp_home, repo_root=tmp_root)
            actions = _result_map(results)

            agents_dest = tmp_home / "AGENTS.md"
            self.assertEqual(actions.get(agents_dest), "skip-differs")
            self.assertEqual(agents_dest.read_text(), preseeded_text)

            # Prompts still installed.
            prompt_dest = tmp_home / "prompts" / "route.md"
            self.assertEqual(actions.get(prompt_dest), "install")
            self.assertTrue(prompt_dest.is_file())


class InstallCodexMissingBundleTests(unittest.TestCase):
    """Case 11: empty temp repo_root raises FileNotFoundError naming the prompts path."""

    def test_missing_bundle_raises_filenotfounderror_naming_expected_path(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = Path(tmp_root_s)  # empty -- no codex/prompts at all
            tmp_home = Path(tmp_home_s)

            expected_bundle_path = tmp_root / "codex" / "prompts"

            with self.assertRaises(FileNotFoundError) as ctx:
                hs.install_codex(tmp_home, repo_root=tmp_root)

            self.assertIn(str(expected_bundle_path), str(ctx.exception))
            # And nothing was written.
            self.assertFalse((tmp_home / "prompts").exists())
            self.assertFalse((tmp_home / "AGENTS.md").exists())

    def test_empty_prompts_dir_also_raises(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = Path(tmp_root_s)
            prompts_dir = tmp_root / "codex" / "prompts"
            prompts_dir.mkdir(parents=True)  # exists, but no *.md files inside
            tmp_home = Path(tmp_home_s)

            with self.assertRaises(FileNotFoundError) as ctx:
                hs.install_codex(tmp_home, repo_root=tmp_root)

            self.assertIn(str(prompts_dir), str(ctx.exception))


class InstallCodexSkillsTests(unittest.TestCase):
    """Codex-desktop skills install: placeholder resolution, per-skill no-clobber,
    idempotence, dry-run, and tolerance of a missing codex/skills/ dir. Every call passes a
    temp home + temp repo root -- the real ~/.codex is never touched."""

    def test_skill_installed_with_placeholder_resolved(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = _make_fake_repo_root(Path(tmp_root_s))
            _add_fake_skill(tmp_root)
            tmp_home = Path(tmp_home_s)

            results = hs.install_codex(tmp_home, repo_root=tmp_root)
            actions = _result_map(results)

            skill_dest = tmp_home / "skills" / "fakeskill"
            self.assertEqual(actions.get(skill_dest), "install")

            written = (skill_dest / "SKILL.md").read_text()
            expected = FAKE_SKILL_TEXT.replace(hs.PLACEHOLDER, str(tmp_root))
            self.assertEqual(written, expected)
            self.assertNotIn(hs.PLACEHOLDER, written)
            self.assertEqual(written.count(str(tmp_root)), 2)

    def test_skill_dry_run_lists_but_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = _make_fake_repo_root(Path(tmp_root_s))
            _add_fake_skill(tmp_root)
            tmp_home = Path(tmp_home_s)

            results = hs.install_codex(tmp_home, repo_root=tmp_root, dry_run=True)
            actions = _result_map(results)

            skill_dest = tmp_home / "skills" / "fakeskill"
            self.assertEqual(actions.get(skill_dest), "install")
            self.assertFalse((tmp_home / "skills").exists())

    def test_skill_idempotent_second_pass_up_to_date(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = _make_fake_repo_root(Path(tmp_root_s))
            _add_fake_skill(tmp_root)
            tmp_home = Path(tmp_home_s)

            hs.install_codex(tmp_home, repo_root=tmp_root)
            skill_md = tmp_home / "skills" / "fakeskill" / "SKILL.md"
            first_text = skill_md.read_text()

            second = _result_map(hs.install_codex(tmp_home, repo_root=tmp_root))
            self.assertEqual(second.get(tmp_home / "skills" / "fakeskill"), "up-to-date")
            self.assertEqual(skill_md.read_text(), first_text)

    def test_preseeded_differing_skill_survives_untouched(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = _make_fake_repo_root(Path(tmp_root_s))
            _add_fake_skill(tmp_root)
            tmp_home = Path(tmp_home_s)

            preseeded = "---\nname: fakeskill\n---\nthe user's own skill; do not touch.\n"
            user_skill = tmp_home / "skills" / "fakeskill"
            user_skill.mkdir(parents=True)
            (user_skill / "SKILL.md").write_text(preseeded)

            actions = _result_map(hs.install_codex(tmp_home, repo_root=tmp_root))
            self.assertEqual(actions.get(user_skill), "skip-differs")
            self.assertEqual((user_skill / "SKILL.md").read_text(), preseeded)
            # Prompts still installed alongside the skipped skill.
            self.assertTrue((tmp_home / "prompts" / "route.md").is_file())

    def test_missing_skills_dir_tolerated(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = _make_fake_repo_root(Path(tmp_root_s))  # prompts only, no skills/
            tmp_home = Path(tmp_home_s)

            results = hs.install_codex(tmp_home, repo_root=tmp_root)
            skill_dests = [d for d, _ in results if "skills" in d.parts]
            self.assertEqual(skill_dests, [])
            self.assertFalse((tmp_home / "skills").exists())
            self.assertTrue((tmp_home / "prompts" / "route.md").is_file())


class DetectCodexTests(unittest.TestCase):
    """Case 12: detect() has exactly {"claude-code", "copilot", "codex"} keys and correct
    booleans for a codex-present combo."""

    def test_detect_codex_present_combo(self):
        which_map = {"codex": "/usr/local/bin/codex"}

        def fake_which(name, _map=which_map):
            return _map.get(name)

        with mock.patch.object(hs.shutil, "which", side_effect=fake_which):
            result = hs.detect()

        self.assertEqual(set(result.keys()), {"claude-code", "copilot", "codex"})
        self.assertEqual(
            result, {"claude-code": False, "copilot": False, "codex": True}
        )


class LiveTreeGuardTests(unittest.TestCase):
    """Case 13: guards against someone accidentally committing a resolved (non-placeholder)
    bundle -- the REAL codex/prompts/route.md must still contain the placeholder."""

    def test_real_route_prompt_has_placeholder_intact(self):
        route_prompt = CODEX_PROMPTS_DIR / "route.md"
        self.assertTrue(route_prompt.is_file(), f"expected {route_prompt} to exist")
        text = route_prompt.read_text()
        self.assertIn(hs.PLACEHOLDER, text)


class FrontmatterYamlSafetyTests(unittest.TestCase):
    """Regression guard (parity with the Copilot suite): a frontmatter value containing an
    unquoted ``: `` (colon-space) is read by real YAML loaders as a nested mapping and the
    file is REJECTED. Scan every prompt and skill frontmatter for the breaker (top-level
    ``key: value`` lines only; nested/indented keys are ignored)."""

    def test_no_unquoted_colon_in_frontmatter_values(self):
        files = sorted(CODEX_PROMPTS_DIR.glob("*.md")) + sorted(CODEX_SKILLS_DIR.glob("*/SKILL.md"))
        offenders = []
        for path in files:
            for line in _frontmatter(path.read_text()).splitlines():
                m = re.match(r"^([A-Za-z][\w-]*): (.*)$", line)
                if not m:
                    continue
                value = m.group(2)
                if value[:1] in ('"', "'"):
                    continue
                if ": " in value:
                    offenders.append(f"{path.parent.name}/{path.name} [{m.group(1)}]")
        self.assertEqual(
            offenders, [],
            f"frontmatter values with an unquoted ': ' (breaks real YAML loaders): {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
