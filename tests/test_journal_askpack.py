"""Stdlib unittest regression suite for bin/journal_askpack.py (PLAN.md D1/D7 of the
journal-augment kit -- the offline ask-the-tools prompt pack).

SAFETY CONTRACT (binds every test in this file): no test here reads or writes any real home
directory (the stdlib home-directory helper is never called), no test here launches an
external process or reaches out over the network, and no test here opens any binary
session-store file. Every fixture -- digests, journal trees -- lives under a fresh
``tempfile.TemporaryDirectory()`` per test, and ``journal_askpack.main`` is always driven
in-process (never as a separately launched program) with every root flag pointed at those
temp fixtures.

CONTENT HYGIENE (PLAN.md D1): a dedicated test plants a marker string in a digest field OTHER
than ``projects`` (a commit-subject-like field under a source's ``extra``) and asserts it
never reaches any of the three built prompts -- only the sorted union of project NAMES may
ever cross from a digest into a prompt.

bin/ is not a package; journal_askpack.py is loaded via importlib by absolute path computed
from this file's own location (BIN_DIR), mirroring tests/test_journal_sources.py.
"""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load("journal_askpack")

CONTEXT_PREFIX = "For context, today I worked on these projects"


def _call_main(argv):
    """Run mod.main(argv) in-process with stdout captured -> (rc, stdout_text)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mod.main(argv)
    return rc, buf.getvalue()


# ---- 1. build_ask_prompts: keys + pinned content -------------------------------------------

class BuildAskPromptsShapeTests(unittest.TestCase):
    def test_exactly_three_keys_matching_tools(self):
        prompts = mod.build_ask_prompts("2026-03-01")
        self.assertEqual(set(prompts), set(mod.TOOLS))
        self.assertEqual(set(prompts), {"copilot_studio", "teams", "outlook"})

    def test_every_prompt_carries_the_pinned_elements(self):
        date_str = "2026-03-01"
        prompts = mod.build_ask_prompts(date_str)
        bullets_phrase = f"at most {mod.MAX_ASK_BULLETS} short bullet lines"
        hygiene_clause = (
            "subject-level only (titles, people, decisions, action items) — no "
            "message bodies, no attachments, no confidential excerpts"
        )
        paste_back = "I will paste these bullets into my daily journal's plain-text inbox."
        for tool, text in prompts.items():
            self.assertIn(date_str, text, tool)
            self.assertIn(bullets_phrase, text, tool)  # via mod.MAX_ASK_BULLETS, not a 2nd literal
            self.assertIn('"- "', text, tool)  # every bullet line starts with "- "
            self.assertIn(hygiene_clause, text, tool)
            self.assertIn(paste_back, text, tool)

    def test_per_tool_ask_is_distinct_and_on_topic(self):
        prompts = mod.build_ask_prompts("2026-03-01")
        self.assertIn("meetings", prompts["teams"].lower())
        self.assertIn("chat", prompts["teams"].lower())
        self.assertIn("email", prompts["outlook"].lower())
        self.assertIn("action items", prompts["outlook"].lower())
        self.assertIn("agent", prompts["copilot_studio"].lower())
        self.assertIn("topics", prompts["copilot_studio"].lower())


# ---- 2. digest enrichment: sorted project-name union, tolerant of odd shapes ----------------

class DigestEnrichmentTests(unittest.TestCase):
    def test_sorted_union_of_projects_appears_once_per_prompt(self):
        digest = {
            "sources": {
                "claude_code": {"projects": ["zeta", "alpha"]},
                "git": {"projects": ["alpha", "mid"]},
            }
        }
        prompts = mod.build_ask_prompts("2026-03-06", digest=digest)
        expected = f"{CONTEXT_PREFIX}: alpha, mid, zeta."
        for tool, text in prompts.items():
            self.assertEqual(text.count(expected), 1, tool)

    def test_digest_with_no_projects_yields_no_context_line(self):
        digest = {"sources": {"claude_code": {"projects": []}}}
        prompts = mod.build_ask_prompts("2026-03-06", digest=digest)
        for text in prompts.values():
            self.assertNotIn(CONTEXT_PREFIX, text)

    def test_digest_none_yields_no_context_line(self):
        prompts = mod.build_ask_prompts("2026-03-06", digest=None)
        for text in prompts.values():
            self.assertNotIn(CONTEXT_PREFIX, text)

    def test_malformed_digest_shapes_tolerated_without_crashing(self):
        for bad_digest in (["not", "a", "dict"], {"sources": "oops"}, {"no_sources": True}, 42):
            prompts = mod.build_ask_prompts("2026-03-06", digest=bad_digest)
            self.assertEqual(set(prompts), set(mod.TOOLS))
            for text in prompts.values():
                self.assertNotIn(CONTEXT_PREFIX, text)

    def test_non_string_project_entries_are_skipped_not_crashed(self):
        digest = {"sources": {"a": {"projects": ["ok", 123, None, {"x": 1}]}}}
        prompts = mod.build_ask_prompts("2026-03-06", digest=digest)
        for text in prompts.values():
            self.assertIn(f"{CONTEXT_PREFIX}: ok.", text)


# ---- 3. hygiene negative: nothing but project names ever leaks into a prompt ----------------

class HygieneNegativeTests(unittest.TestCase):
    def test_non_project_digest_content_never_reaches_a_prompt(self):
        marker = "MARKER-COMMIT-SUBJECT-NEVER-IN-PROMPT"
        digest = {
            "sources": {
                "git": {
                    "projects": ["proj-x"],
                    "extra": {"repos": [{"commits": [marker]}]},
                },
                "claude_code": {"sessions": 5, "usd": 1.23, "projects": []},
            }
        }
        prompts = mod.build_ask_prompts("2026-03-07", digest=digest)
        for text in prompts.values():
            self.assertNotIn(marker, text)
            self.assertNotIn("1.23", text)
            self.assertIn(f"{CONTEXT_PREFIX}: proj-x.", text)  # the project name IS allowed


# ---- 4. render_pack: pinned document shape ---------------------------------------------------

class RenderPackShapeTests(unittest.TestCase):
    def test_pinned_heading_shape_and_order(self):
        date_str = "2026-03-08"
        prompts = mod.build_ask_prompts(date_str)
        pack = mod.render_pack(date_str, prompts)
        lines = pack.splitlines()
        self.assertEqual(lines[0], f"# Ask the tools — {date_str}")

        how_idx = pack.index("## How to use")
        tool_indices = []
        for tool in mod.TOOLS:
            heading = f"## {mod.TOOL_TITLES[tool]}"
            idx = pack.index(heading)
            self.assertGreater(idx, how_idx, tool)
            tool_indices.append(idx)
        self.assertEqual(tool_indices, sorted(tool_indices))  # TOOLS order preserved

        for tool in mod.TOOLS:
            fenced = "```\n" + prompts[tool].rstrip("\n") + "\n```"
            self.assertIn(fenced, pack, tool)

    def test_two_pass_flow_mentions_inbox_and_collector_commands(self):
        prompts = mod.build_ask_prompts("2026-03-08")
        pack = mod.render_pack("2026-03-08", prompts)
        self.assertIn("journal/inbox.md", pack)
        self.assertIn("journal_collect.py", pack)


# ---- 5. CLI end-to-end: write scope, --print, digest enrichment, corrupt digest ------------

class CliEndToEndTests(unittest.TestCase):
    def test_writes_only_the_one_ask_pack_file_and_print_echoes(self):
        with tempfile.TemporaryDirectory() as td:
            journal_dir = Path(td) / "journal"
            rc, out = _call_main([
                "--date", "2026-03-09", "--utc",
                "--journal-dir", str(journal_dir), "--print",
            ])
            self.assertEqual(rc, 0)
            files = sorted(str(p) for p in journal_dir.rglob("*") if p.is_file())
            expected_path = journal_dir / "2026-03-09" / "ask-the-tools.md"
            self.assertEqual(files, [str(expected_path)])
            written = expected_path.read_text()
            self.assertIn(written.strip(), out)

    def test_existing_digest_contributes_project_context_line(self):
        with tempfile.TemporaryDirectory() as td:
            journal_dir = Path(td) / "journal"
            date_str = "2026-03-10"
            (journal_dir / date_str).mkdir(parents=True)
            digest = {"sources": {"claude_code": {"projects": ["zeta", "alpha"]}}}
            (journal_dir / date_str / "digest.json").write_text(json.dumps(digest))
            rc, _ = _call_main(
                ["--date", date_str, "--utc", "--journal-dir", str(journal_dir)])
            self.assertEqual(rc, 0)
            written = (journal_dir / date_str / "ask-the-tools.md").read_text()
            self.assertIn(f"{CONTEXT_PREFIX}: alpha, zeta.", written)

    def test_corrupt_digest_degrades_to_none_without_crashing(self):
        with tempfile.TemporaryDirectory() as td:
            journal_dir = Path(td) / "journal"
            date_str = "2026-03-11"
            (journal_dir / date_str).mkdir(parents=True)
            (journal_dir / date_str / "digest.json").write_bytes(
                b"\x00\x01not-valid-json-garbage")
            rc, _ = _call_main(
                ["--date", date_str, "--utc", "--journal-dir", str(journal_dir)])
            self.assertEqual(rc, 0)
            written = (journal_dir / date_str / "ask-the-tools.md").read_text()
            self.assertNotIn(CONTEXT_PREFIX, written)

    def test_explicit_missing_digest_path_degrades_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            journal_dir = Path(td) / "journal"
            date_str = "2026-03-12"
            rc, _ = _call_main([
                "--date", date_str, "--utc", "--journal-dir", str(journal_dir),
                "--digest", str(journal_dir / "nowhere" / "digest.json"),
            ])
            self.assertEqual(rc, 0)
            written = (journal_dir / date_str / "ask-the-tools.md").read_text()
            self.assertNotIn(CONTEXT_PREFIX, written)


# ---- 6. determinism ---------------------------------------------------------------------------

class DeterminismTests(unittest.TestCase):
    def test_two_runs_over_identical_inputs_produce_identical_bytes(self):
        with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
            date_str = "2026-03-13"
            digest = {"sources": {"claude_code": {"projects": ["b", "a"]}}}
            for td in (td1, td2):
                journal_dir = Path(td) / "journal"
                (journal_dir / date_str).mkdir(parents=True)
                (journal_dir / date_str / "digest.json").write_text(json.dumps(digest))

            rc1, _ = _call_main(
                ["--date", date_str, "--utc",
                 "--journal-dir", str(Path(td1) / "journal")])
            rc2, _ = _call_main(
                ["--date", date_str, "--utc",
                 "--journal-dir", str(Path(td2) / "journal")])
            self.assertEqual(rc1, 0)
            self.assertEqual(rc2, 0)

            b1 = (Path(td1) / "journal" / date_str / "ask-the-tools.md").read_bytes()
            b2 = (Path(td2) / "journal" / date_str / "ask-the-tools.md").read_bytes()
            self.assertEqual(b1, b2)


if __name__ == "__main__":
    unittest.main()
