"""Live-tree regression suite for the docs-site kit's AUDIT.md skill-card
dispositions (T9 Claude harness; also stands as a durable guard for T10/T11).

Style follows tests/test_docs_audit.py and tests/test_guardrails_layout.py: no
fixtures, asserts directly against the real, committed repo. Two kinds of
checks live here:

1. **Durable, harness-agnostic guards** (ReferencePointerTests,
   NoDocsSiteStringTests-adjacent items) that apply to any future task
   creating `references/*.md` beside a SKILL.md -- these are meant to survive
   T10 (Copilot) and T11 (Codex) unchanged and keep firing on any later kit
   that touches a skill card.
2. **T9-specific regressions** tying the Claude-harness relocate/enrich
   dispositions (context-weight, journal, setup, cost-report) to their real
   sources: `bin/context_weight.py` + tests/test_context_weight.py for the
   quotation-coupled strings, `bin/cost_report.py` for the enrich's two flags
   and two no-data messages, and tests/test_statusline.py's own payload for
   the setup sample-JSON exact-output contract. These derive their
   expectations from AUDIT.md's `## claude` entries and PLAN.md D1, not from
   reading what the implementer wrote.

No test here shells out to a real `claude`/`copilot`/`codex` CLI, reads a real
home directory, or invokes `git` -- word counts and body text are read via
`bin/docs_build.py`'s own `skill_inventory()` (the same parser the generator
and tests/test_docs_audit.py already trust), and engine behavior is exercised
by importing bin/context_weight.py and bin/cost_report.py directly (the
importlib sibling-loader idiom `_load`, matching tests/test_context_weight.py
and tests/test_docs_build.py).
"""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = REPO_ROOT / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True
    )


docs_build = _load("docs_build")
cw = _load("context_weight")
cost_report = _load("cost_report")
bench_routing = _load("bench_routing")


def _skill(name, harness="claude"):
    for record in docs_build.skill_inventory(repo_root=REPO_ROOT):
        if record["harness"] == harness and record["name"] == name:
            return record
    raise AssertionError(f"no such skill: {harness}/{name}")


# ---------------------------------------------------------------------------
# Group 1: durable, harness-agnostic guard -- PLAN.md D1 rule 2 ("Every
# reference file must be named from its SKILL.md with a one-line 'read
# references/<file> when X' trigger -- an unpointed reference is dead
# weight"). Scoped to flat `references/*.md` files (not recursive) so it
# does not fire on the pre-existing `skills/architect/references/roles/*.md`
# templates (named via a `<role>` pattern, not per-filename, by design --
# AUDIT marks that tree off-limits to this kit) or on the generated
# `references/pricing.json` mirrors beside route/fable-check (not markdown,
# not a "read when X" doc).
# ---------------------------------------------------------------------------


class ReferencePointerTests(unittest.TestCase):
    HARNESS_SKILL_ROOTS = (
        REPO_ROOT / "skills",
        REPO_ROOT / "copilot" / ".github" / "skills",
        REPO_ROOT / "codex" / "skills",
    )

    def test_every_flat_reference_md_has_a_pointer_in_its_skill_md(self):
        missing = []
        for root in self.HARNESS_SKILL_ROOTS:
            if not root.is_dir():
                continue
            for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
                refs_dir = skill_dir / "references"
                if not refs_dir.is_dir():
                    continue
                skill_md = skill_dir / "SKILL.md"
                skill_text = skill_md.read_text(encoding="utf-8") if skill_md.is_file() else ""
                for ref_file in sorted(refs_dir.glob("*.md")):
                    name = ref_file.name
                    if name not in skill_text:
                        missing.append(
                            f"{skill_dir.relative_to(REPO_ROOT)}: "
                            f"references/{name} has no pointer in SKILL.md"
                        )
        self.assertEqual(missing, [], f"unpointed reference file(s): {missing!r}")

    def test_the_five_new_t9_reference_files_exist_and_are_flat_md(self):
        # Sanity check that the guard above actually has live surface to bite on
        # for this task -- a passing-vacuously test proves nothing.
        expected = [
            "skills/context-weight/references/columns.md",
            "skills/context-weight/references/practices.md",
            "skills/journal/references/ask-the-tools.md",
            "skills/journal/references/scheduling.md",
            "skills/setup/references/kit-verify-hook.md",
        ]
        for rel in expected:
            self.assertTrue((REPO_ROOT / rel).is_file(), f"missing expected reference: {rel}")


# ---------------------------------------------------------------------------
# Group 2: claude/context-weight -- AUDIT's MUST-NOT-MOVE list, and the
# quotation-coupling risk the T8 test-author flagged (rewording a line that
# quotes bin/context_weight.py desyncs skill from engine even though no test
# reads the SKILL.md body directly).
# ---------------------------------------------------------------------------


class ContextWeightDispositionTests(unittest.TestCase):
    def setUp(self):
        self.body = _skill("context-weight")["body"]

    def test_must_not_move_sections_present(self):
        # AUDIT.md claude/context-weight: "MUST NOT move: 'What this skill
        # cannot do' ..., the three levers with their priority order,
        # 'Checkpoint before compacting' with its safe/dangerous split, the
        # watch-is-Claude-only refusal, and the closing honesty rules."
        for heading in (
            "## What this skill cannot do",
            "## The three levers, in priority order",
            "## Checkpoint before compacting",
            "## Honesty rules this tool holds",
        ):
            self.assertIn(heading, self.body, f"missing MUST-NOT-MOVE heading: {heading!r}")
        # The priority order itself (1. PREVENT, 2. PRUNE, 3. MEASURE) is the
        # acting content, not just the heading.
        self.assertIn("1. **PREVENT", self.body)
        self.assertIn("2. **PRUNE", self.body)
        self.assertIn("3. **MEASURE", self.body)
        # Safe/dangerous split under the checkpoint section.
        self.assertIn("**Safe to drop:**", self.body)
        self.assertIn("**Dangerous to drop:**", self.body)
        # watch-is-Claude-only refusal stated at least once outside the
        # references split (columns.md/practices.md do not carry this).
        self.assertIn("Claude-only", self.body)

    def test_watch_recommendation_string_is_quoted_verbatim_from_the_engine(self):
        # The single highest-risk quotation coupling per the T8 audit: the
        # skill quotes the engine's own recommendation string. Derive the
        # expected text from bin/context_weight.py itself (not from reading
        # the skill) and only then check it lands byte-identical.
        engine_string = cw._watch_recommendation(61)
        self.assertEqual(engine_string, "checkpoint decisions to disk, then compact")
        self.assertIn(engine_string, self.body)
        # And the test suite pins the same string against the same function,
        # so skill / engine / test all agree.
        test_source = (REPO_ROOT / "tests" / "test_context_weight.py").read_text(encoding="utf-8")
        self.assertIn(f'"{engine_string}"', test_source)

    def test_other_quotation_coupled_strings_survive(self):
        for token in (
            "python3 bin/context_weight.py watch",
            "est.",
            "/compact",
            "clear_tool_uses_20250919",
            "clear_thinking_20251015",
        ):
            self.assertIn(token, self.body, f"missing quotation-coupled token: {token!r}")

    def test_six_subcommands_documented_matching_the_real_parser(self):
        # AUDIT's missing-acting-fact addition: the engine ships six
        # subcommands (confirmed against the real argparse, not prose) and
        # the skill's "All five take --json" line must now say six.
        parser = cw.build_parser()
        subparsers_action = next(
            a for a in parser._subparsers._group_actions if a.dest == "command"
        )
        self.assertEqual(
            set(subparsers_action.choices),
            {"session", "overview", "audit", "watch", "constraints", "demo"},
        )
        self.assertIn("All six take", self.body)
        self.assertNotIn("All five take", self.body)
        self.assertIn("constraints", self.body)

    def test_watch_has_no_harness_flag_but_constraints_does(self):
        # The acting fact the enrich adds: watch is Claude-only by the
        # ABSENCE of --harness (a positional instead); constraints (like
        # session/overview) takes --harness. Verify against the real
        # argparse, then check the skill's claim matches.
        parser = cw.build_parser()
        watch_parser = parser._subparsers._group_actions[0].choices["watch"]
        constraints_parser = parser._subparsers._group_actions[0].choices["constraints"]
        watch_opts = {opt for a in watch_parser._actions for opt in a.option_strings}
        constraints_opts = {opt for a in constraints_parser._actions for opt in a.option_strings}
        self.assertNotIn("--harness", watch_opts)
        self.assertIn("--harness", constraints_opts)
        self.assertIn("`watch` has no `--harness` flag", self.body)

    def test_relocated_columns_and_practices_are_verbatim(self):
        # Confirm the two references/*.md files are the moved content, not a
        # paraphrase -- spot-check a handful of distinctive, exact phrases
        # that existed in the pre-T9 SKILL.md (per git history) and must
        # still read identically in their new home.
        columns = (REPO_ROOT / "skills/context-weight/references/columns.md").read_text(
            encoding="utf-8"
        )
        practices = (REPO_ROOT / "skills/context-weight/references/practices.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "`session-average` is the\n  honest substitute, not a curve in disguise.",
            "Estimates are ranks and magnitudes, never priced",
        ):
            self.assertIn(phrase, columns)
        for phrase in (
            "Delegate bulk reads to subagents that return conclusions, not raw dumps.",
            "Sidechain (subagents): N call(s), X tokens (Y%",
            "`current weight X of a Y-token window (Z%)`",
        ):
            self.assertIn(phrase, practices)


# ---------------------------------------------------------------------------
# Group 3: claude/journal -- the Privacy paragraph and the no-network
# declaration must stay in the skill (AUDIT: "fold into the skill, do not
# move"), and the two relocated blocks must be verbatim in their new files.
# ---------------------------------------------------------------------------


class JournalDispositionTests(unittest.TestCase):
    def setUp(self):
        self.body = _skill("journal")["body"]

    def test_privacy_paragraph_present_verbatim(self):
        privacy = (
            "Writing the summaries sends the digest — project and repo names, commit subjects, "
            "kit task\ntitles, and any inbox text — to a model. The digest itself is "
            "metadata-only: it never carries\ntranscript or message text, only counts, ids, "
            "titles, and short strings like the above.\nEverything the journal produces stays "
            "under the gitignored `journal/` directory; nothing here\nis committed to git. "
            "Pasted ask-the-tools bullets become inbox text, so they also travel to\nthe model "
            "when you write the summaries."
        )
        self.assertIn(privacy, self.body)

    def test_no_network_declaration_present(self):
        # AUDIT: "the no-network / no-OAuth / no-Graph / no-MCP declaration
        # stays in the skill even though the command it describes moves."
        self.assertIn("no Graph/OAuth/MCP connectors", self.body)
        self.assertIn("network,\nOAuth, Graph, or MCP calls", self.body)

    def test_relocated_scheduling_and_ask_the_tools_are_verbatim(self):
        scheduling = (REPO_ROOT / "skills/journal/references/scheduling.md").read_text(
            encoding="utf-8"
        )
        ask_the_tools = (REPO_ROOT / "skills/journal/references/ask-the-tools.md").read_text(
            encoding="utf-8"
        )
        self.assertIn('python3 "$ROOT/bin/journal_schedule.py" install', scheduling)
        self.assertIn("launchd plist (default 22:00)", scheduling)
        self.assertIn("the installer never runs `launchctl` itself", scheduling)
        self.assertIn('python3 "$ROOT/bin/journal_askpack.py" --date <date> --print', ask_the_tools)
        self.assertIn("at most 15 subject-level bullets per tool", ask_the_tools)


# ---------------------------------------------------------------------------
# Group 4: claude/setup -- the sample JSON payload in step 1 is off-limits
# (tests/test_statusline.py's exact-output test shares three field VALUES
# with it, not the rate-limit half). Derive the expected rendered line from
# the real statusline behavior, not from re-reading the skill's prose.
# ---------------------------------------------------------------------------


class SetupDispositionTests(unittest.TestCase):
    def setUp(self):
        self.body = _skill("setup")["body"]

    def test_sample_json_payload_values_present_verbatim(self):
        for token in ('"claude-fable-5"', '"Fable 5"', "1.23", '"used_percentage":42'):
            self.assertIn(token, self.body, f"setup sample JSON missing token: {token!r}")

    def test_sample_json_actually_renders_the_statusline_pinned_string(self):
        # Independently derive the expected output by running the real
        # statusline script as a subprocess (its own established test
        # pattern, per tests/test_statusline.py -- it reads stdin, prints one
        # line, and takes no importable main(argv)). Reuses the exact
        # payload tests/test_statusline.py's own exact-output test pins.
        import re as _re
        import subprocess
        import sys as _sys

        script = BIN_DIR / "statusline.py"
        payload = {
            "model": {"id": "claude-fable-5", "display_name": "Fable 5"},
            "cost": {"total_cost_usd": 1.23},
            "context_window": {"used_percentage": 42},
        }
        proc = subprocess.run(
            [_sys.executable, str(script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=10,
        )
        out = _re.sub(r"\x1b\[[0-9;]*m", "", proc.stdout).strip()
        self.assertEqual(out, "⬢ Fable 5 | $1.23 | ctx 42%")

    def test_kit_verify_hook_reference_is_verbatim_and_pointed(self):
        ref = (REPO_ROOT / "skills/setup/references/kit-verify-hook.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "a marker is written only\nby `record`, and `precheck` (run at the start of every "
            "attempt) deletes any existing marker for",
            ref,
        )
        self.assertIn("references/kit-verify-hook.md", self.body)

    def test_literal_absolute_path_rule_untouched(self):
        # CLAUDE.md invariant: the command written into ~/.claude/settings.json
        # must never be ${CLAUDE_PLUGIN_ROOT} -- that var doesn't exist outside
        # plugin context. Must survive the relocate.
        self.assertIn("literal", self.body.lower())
        commands = self._settings_json_commands()
        self.assertGreaterEqual(len(commands), 2, "expected both settings.json command snippets")
        for command in commands:
            self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", command)

    @staticmethod
    def _settings_json_commands():
        body = _skill("setup")["body"]
        # Extract every statusLine/hook command line from the JSON snippets.
        import re as _re

        return _re.findall(r'"command":\s*"([^"]+)"', body)


# ---------------------------------------------------------------------------
# Group 5: claude/cost-report -- the enrich must add the two real flags and
# the two no-data branch messages, and they must match the actual engine
# behavior (not just be typed into the skill).
# ---------------------------------------------------------------------------


class CostReportDispositionTests(unittest.TestCase):
    def setUp(self):
        self.body = _skill("cost-report")["body"]

    def test_json_and_projects_dir_flags_documented_and_real(self):
        self.assertIn("--json", self.body)
        self.assertIn("--projects-dir", self.body)
        parser = cost_report_parser()
        opts = {opt for a in parser._actions for opt in a.option_strings}
        self.assertIn("--json", opts)
        self.assertIn("--projects-dir", opts)

    def test_missing_directory_message_matches_engine_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist"
            with self.assertRaises(SystemExit) as ctx:
                cost_report.main(["--projects-dir", str(missing), "--days", "30"])
            self.assertEqual(str(ctx.exception), f"No transcript directory at {missing}")
        self.assertIn("No transcript directory at", self.body)

    def test_empty_directory_label_matches_engine_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty_dir = Path(tmp)
            payload = cost_report.build_report_payload(empty_dir, days=30)
            self.assertFalse(payload["found"])
            self.assertIn(f"no transcripts in window: {empty_dir}", payload["labels"])
        self.assertIn("no transcripts in window:", self.body)

    def test_no_data_outcomes_framed_as_honest_not_broken(self):
        # AUDIT: "a zero-row report is honest output, not a failure."
        self.assertIn("not a failure", self.body)


def cost_report_parser():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--mode", choices=["api", "subscription"], default=None)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--projects-dir", default=None)
    return ap


# ---------------------------------------------------------------------------
# Group 6: the three orchestration-ceiling skills may only shrink (D1).
# Durable across future kits: fails the moment any of the three GROWS past
# its recorded ceiling, without pinning them to never change at all.
# ---------------------------------------------------------------------------


class CeilingSkillsTests(unittest.TestCase):
    CEILINGS = {
        "architect": 2767,
        "execute": 5998,
        "repo-bench": 6567,
    }

    def test_ceiling_skills_have_not_grown(self):
        for name, ceiling in self.CEILINGS.items():
            body = _skill(name)["body"]
            word_count = len(body.split())
            self.assertLessEqual(
                word_count, ceiling,
                f"{name} SKILL.md body grew to {word_count} words, past its "
                f"D1 ceiling of {ceiling} (orchestration skills may only shrink)",
            )

    def test_ceiling_skills_untouched_by_t9(self):
        # T9's scope is context-weight/journal/setup/cost-report only; the
        # three ceiling skills should be byte-identical to their D1-recorded
        # word counts, not merely under the ceiling.
        for name, ceiling in self.CEILINGS.items():
            body = _skill(name)["body"]
            self.assertEqual(len(body.split()), ceiling, f"{name} word count drifted")


# ---------------------------------------------------------------------------
# Group 7: no price/model-id/date literal was introduced by T9's edits.
# Scoped to the four touched SKILL.md bodies plus the five new reference
# files -- the one known, pre-existing, explicitly-sanctioned exception is
# skills/setup/SKILL.md step 1's sample statusline JSON payload (predates
# this kit and is pinned byte-for-byte by tests/test_statusline.py), matched
# here by the presence of "total_cost_usd" on the same line.
# ---------------------------------------------------------------------------


class NoNewLiteralsTests(unittest.TestCase):
    FILES = [
        "skills/context-weight/SKILL.md",
        "skills/context-weight/references/columns.md",
        "skills/context-weight/references/practices.md",
        "skills/journal/SKILL.md",
        "skills/journal/references/ask-the-tools.md",
        "skills/journal/references/scheduling.md",
        "skills/setup/SKILL.md",
        "skills/setup/references/kit-verify-hook.md",
        "skills/cost-report/SKILL.md",
    ]

    def test_no_price_model_id_or_date_literals_outside_the_known_exception(self):
        import re

        pattern = re.compile(
            r"\$\d|claude-[a-z]+-\d|\bsonnet-\d|\bopus-\d|\b20\d{2}-\d{2}-\d{2}\b"
        )
        offenders = []
        for rel in self.FILES:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line) and "total_cost_usd" not in line:
                    offenders.append(f"{rel}:{lineno}: {line.strip()!r}")
        self.assertEqual(offenders, [], f"introduced literal(s): {offenders!r}")


# ---------------------------------------------------------------------------
# Group 8: codex/bench-routing (T11 enrich) -- the two added sentences' central
# factual claim is that `compare` has no `--harness` flag of its own. AUDIT
# confirmed this against `python3 bin/bench_routing.py compare --help` output;
# the durable form of the same guard checks the real argparse SOURCE instead
# (bin/bench_routing.py's own build_parser()), so a future edit that adds
# --harness to `compare` breaks this test even if nobody rereads the skill
# prose or re-runs --help by hand. Per AUDIT, the sentence mirrors wording
# "already proven in copilot/bench-routing" -- checked there too, so a single
# engine change trips every card claiming it at once.
# ---------------------------------------------------------------------------


def _subparser(command):
    parser = bench_routing.build_parser()
    subparsers_action = next(
        a for a in parser._subparsers._group_actions if a.dest == "command"
    )
    return subparsers_action.choices[command]


def _option_strings(subparser):
    return {opt for a in subparser._actions for opt in a.option_strings}


class CodexBenchRoutingDispositionTests(unittest.TestCase):
    def setUp(self):
        self.body = _skill("bench-routing", harness="codex")["body"]

    def test_compare_genuinely_has_no_harness_flag_in_the_real_parser(self):
        # The rot-prone assertion, checked against source rather than prose.
        self.assertNotIn("--harness", _option_strings(_subparser("compare")))

    def test_roles_subcommand_does_have_harness_for_contrast(self):
        # The claim is specific to `compare`, not a blanket "no --harness
        # anywhere" statement -- `roles` genuinely does take --harness.
        self.assertIn("--harness", _option_strings(_subparser("roles")))

    def test_skill_states_the_no_harness_flag_claim(self):
        self.assertIn("`compare` has no `--harness` flag", self.body)

    def test_same_claim_holds_in_the_copilot_sibling_card(self):
        # AUDIT: "mirroring the wording already proven in copilot/bench-routing".
        copilot_body = _skill("bench-routing", harness="copilot")["body"]
        self.assertIn("`compare` has no `--harness` flag", copilot_body)

    def test_skill_names_compare_and_the_claude_only_ledger_scope(self):
        # AUDIT's required content: name `compare`, state the ledger is
        # Claude-harness implementer evidence with no Codex per-role data,
        # and that the benchmark recommendation stands unchallenged.
        flat = " ".join(self.body.split())
        self.assertIn("compare` joins the benchmark prior", flat)
        self.assertIn("Claude-harness implementer evidence", flat)
        self.assertIn("no per-role outcome data for Codex", flat)
        self.assertIn("stands unchallenged", flat)

    def test_no_dollar_amount_or_bare_bill_claim_introduced(self):
        # Subscription-mode honesty: nothing in the edit should turn a Codex
        # benchmark/cost figure into something read as a real bill. The
        # existing "not ... a bill" negation (pinned elsewhere) must survive,
        # and no new $-amount literal should appear anywhere in the file.
        import re

        self.assertNotIn("$", self.body.replace("$POLYTROPOS_ROOT", ""))
        self.assertIsNone(re.search(r"\$\d", self.body))
        flat = " ".join(self.body.split())
        self.assertIn("not this repository's pricing, a bill, or routing certainty", flat)

    def test_five_pre_existing_pinned_sentences_survive_verbatim(self):
        # Independent second witness for tests/test_codex_analysis_skills.py's
        # own direct pins -- a regression here shows up in two suites at once.
        flat = " ".join(self.body.split())
        for token in (
            "Intelligence Index",
            "screenshot",
            "not this repository's pricing",
            "not a guaranteed winner",
        ):
            self.assertIn(token, flat)

    def test_word_count_is_in_the_audit_predicted_band(self):
        # AUDIT: 152-word body + "~50 words" -> "~200 words". Banded, not a
        # byte-exact pin (the exact count is separately re-derived below).
        count = len(self.body.split())
        self.assertGreaterEqual(count, 190)
        self.assertLessEqual(count, 210)

    def test_frontmatter_carries_no_model_pin(self):
        text = (REPO_ROOT / "codex/skills/bench-routing/SKILL.md").read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1]
        self.assertNotIn("model:", frontmatter)

    def test_bench_routing_is_not_mirrored_into_codex_prompts(self):
        # Explicit, AUDIT-derived negative: bench-routing is correctly NOT
        # one of the seven stems synced into codex/prompts/ (that set is
        # already roster-pinned in tests/test_codex_bundle.py's
        # EXPECTED_PROMPT_STEMS; this re-asserts the specific absence this
        # task's brief calls out by name).
        self.assertFalse((REPO_ROOT / "codex/prompts/bench-routing.md").exists())


# ---------------------------------------------------------------------------
# Group 9: codex/memory (T11 keep) -- regression check that the five NEGATIVE
# pins named in this task's brief still hold. It was a `keep` (AUDIT recorded
# it byte-unchanged), so this guards against silent drift introducing a
# real-home read, a subprocess call, a network primitive, a real codex CLI
# invocation, or the wrong pricing file name.
# ---------------------------------------------------------------------------


class CodexMemoryKeepRegressionTests(unittest.TestCase):
    def setUp(self):
        self.body = _skill("memory", harness="codex")["body"]

    def test_five_negative_pins_absent(self):
        for banned in ("Path.home", "subprocess", "urlopen", "codex exec", "pricing.json"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, self.body)


# ---------------------------------------------------------------------------
# Group 10: whole-of-T11 regression -- of the 12 `## codex` AUDIT entries, 11
# were `keep` (verified byte-unchanged) and exactly one (`bench-routing`) was
# `enrich`. Diffed against the committed HEAD, since this kit's own tree is
# still uncommitted mid-execution: any file under codex/skills/ other than
# bench-routing/SKILL.md showing a diff here is a real finding, not a false
# positive, because nothing else in `## codex` AUDIT authorized a change.
# ---------------------------------------------------------------------------


@unittest.skipUnless(
    _git("rev-parse", "--is-inside-work-tree").returncode == 0,
    "not inside a git work tree",
)
class CodexSkillsElevenKeepsByteUnchangedTests(unittest.TestCase):
    def test_only_bench_routing_skill_md_differs_from_head(self):
        result = _git("diff", "--name-only", "--", "codex/skills/")
        self.assertEqual(result.returncode, 0, result.stderr)
        changed = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(changed, ["codex/skills/bench-routing/SKILL.md"])


# ---------------------------------------------------------------------------
# Group 11: Phase-4-wide durable guard -- GUARDRAILS.md D1: "The string
# `docs-site` never appears in any SKILL.md (test-enforced)." Each task's own
# verify command greps for this per-harness, but no test in the suite scans
# every harness's skill roster together. With Codex (T11) now the third and
# final harness done in this kit, this closes that gap for good: it fires on
# any future SKILL.md edit in any of the three harnesses that leaks the
# generator's own vocabulary into model-loaded content.
# ---------------------------------------------------------------------------


class NoDocsSiteStringInAnySkillMdTests(unittest.TestCase):
    HARNESS_SKILL_ROOTS = (
        REPO_ROOT / "skills",
        REPO_ROOT / "copilot" / ".github" / "skills",
        REPO_ROOT / "codex" / "skills",
    )

    def test_no_skill_md_anywhere_mentions_docs_site(self):
        offenders = []
        for root in self.HARNESS_SKILL_ROOTS:
            if not root.is_dir():
                continue
            for skill_md in sorted(root.glob("*/SKILL.md")):
                text = skill_md.read_text(encoding="utf-8")
                if "docs-site" in text:
                    offenders.append(str(skill_md.relative_to(REPO_ROOT)))
        self.assertEqual(offenders, [], f"'docs-site' string leaked into: {offenders!r}")


if __name__ == "__main__":
    unittest.main()
