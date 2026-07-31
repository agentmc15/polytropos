"""Stdlib unittest regression suite for bin/journal_collect.py (PLAN.md D4/D8 collector CLI).

SAFETY CONTRACT (binds every test in this file): no test here ever reads or writes any of the
three real tool home directories that journal_collect.py can be pointed at (the user's real
Claude Code project store, Copilot CLI home, or Codex CLI home), and no test here resolves the
caller's real home directory via the stdlib Path.home helper. Every ``jc.main([...])`` call in
this file passes EXPLICIT ``--claude-projects``/``--copilot-home``/``--codex-home``/
``--journal-dir``/``--kits-dir`` overrides pointed at fresh ``tempfile.TemporaryDirectory()``
fixtures -- never the real defaults journal_collect.py falls back to at runtime. No test here
invokes a real ``claude``, ``copilot``, or ``codex`` CLI binary -- journal_collect.py makes no
such call to gather data (it is a deterministic, model-free ingestion tool; the separate
summarizer is the one that later shells out to ``claude``, and that file is untouched by this
kit task). The ONLY subprocess use anywhere in this file is one end-to-end smoke test that
invokes ``bin/journal_collect.py`` itself via ``sys.executable`` (a sanctioned self-invocation,
not a third-party CLI) with every root flag pointed at temp fixtures; this file needs no git
fixtures at all -- the git-only "sources_active" day-membership case is proven directly against
``build_digest``'s report-dict contract via a synthetic report dict, so no real ``git`` binary
is ever spawned here.

Both real plugin pricing files (``data/pricing.json``, ``data/pricing.copilot.json``) ARE
opened by ``jc.main`` (via the reused ``cr.load_pricing``/``cu.load_pricing`` calls baked into
journal_collect.py's own ``main``) -- that is sanctioned reuse of checked-in repo config, not a
live-home read, and every fixture model id used in this file (``fake-big``, ``fake-copilot-x``,
etc.) is deliberately absent from both real pricing files, so those records always land in the
"unpriced" bucket rather than accidentally matching a real priced model.

CONTENT HYGIENE (PLAN.md D4): one dedicated test builds a Claude Code fixture message whose
``message.content`` carries a distinctive marker string and asserts the marker never reaches
the written digest.json -- proving the metadata-only contract holds all the way through
``jc.main``, not just inside the adapter engine tested by T5.

bin/ is not a package; journal_collect.py is loaded via importlib by absolute path computed
from this file's own location (BIN_DIR), mirroring tests/test_journal_sources.py.
"""

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


jc = _load("journal_collect")

DIGEST_TOP_KEYS = frozenset({
    "schema_version", "date", "generated_at", "day_start", "day_end", "timezone",
    "sources", "totals", "signals",
})

DAY_START = datetime(2026, 6, 30, tzinfo=timezone.utc)
DAY_END = DAY_START + timedelta(days=1)


def _call_main(argv):
    """Run jc.main(argv) in-process with stdout captured -> (rc, stdout_text)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = jc.main(argv)
    return rc, buf.getvalue()


# ---- Claude Code transcript-line builder (self-contained, mirrors T5's _crec) ---------------

def _claude_line(model, ts, mid, session_id="sess-1", inp=1000, out=100, cwd=None,
                  content=None):
    msg = {
        "model": model,
        "id": mid,
        "usage": {"input_tokens": inp, "output_tokens": out},
    }
    if content is not None:
        msg["content"] = content
    obj = {"timestamp": ts, "sessionId": session_id, "message": msg}
    if cwd:
        obj["cwd"] = cwd
    return json.dumps(obj)


# ---- Copilot CLI fixture builders (self-contained, mirrors T5's _ev/_td/_mksession) ----------

def _ev(etype, ts, **data):
    return json.dumps({"type": etype, "timestamp": ts, "data": data})


def _td(inp, cache_read, cache_write, out):
    return {
        "input": {"tokenCount": inp},
        "cache_read": {"tokenCount": cache_read},
        "cache_write": {"tokenCount": cache_write},
        "output": {"tokenCount": out},
    }


def _mk_copilot_session(copilot_home, name, lines, workspace_text):
    d = copilot_home / "session-state" / name
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text("\n".join(lines) + "\n")
    (d / "workspace.yaml").write_text(workspace_text)
    return d


# ---- kit TASKS.md fixture builder (mirrors bin/copilot_execute.py's parse_tasks contract) ----

def _kit_task_block(task_id, title, status, model=None):
    lines = [f"### {task_id} — {title}", f"- status: {status}"]
    if model:
        lines.append(f"- model: {model}")
    lines.append("- depends: (none)")
    lines.append("- independent: no")
    lines.append("")
    lines.append(f"**Brief.** Fixture brief text for {task_id}.")
    lines.append("")
    lines.append("**Verify.**")
    lines.append("```bash")
    lines.append("true")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def _write_kit(kits_dir, kit_name, blocks_text):
    kit_dir = kits_dir / kit_name
    kit_dir.mkdir(parents=True)
    (kit_dir / "TASKS.md").write_text("# TASKS — fixture kit\n\n" + blocks_text)
    return kit_dir


# ---- 1. load_config ---------------------------------------------------------------------------


class LoadConfigTests(unittest.TestCase):
    def test_missing_file_returns_empty_config_and_no_notes(self):
        with tempfile.TemporaryDirectory() as td:
            config, notes = jc.load_config(Path(td) / "nope.json")
            self.assertEqual(config, {})
            self.assertEqual(notes, [])

    def test_invalid_json_returns_note(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.json"
            path.write_text("{not valid json at all")
            config, notes = jc.load_config(path)
            self.assertEqual(config, {})
            self.assertEqual(len(notes), 1)
            self.assertIn("config unreadable", notes[0])

    def test_non_dict_top_level_returns_note(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.json"
            path.write_text(json.dumps([1, 2, 3]))
            config, notes = jc.load_config(path)
            self.assertEqual(config, {})
            self.assertEqual(len(notes), 1)
            self.assertIn("config unreadable", notes[0])

    def test_repos_parsed_to_path_objects_non_strings_dropped(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.json"
            path.write_text(json.dumps({
                "repos": ["/fake/repoA", "/fake/repoB", 123, None],
            }))
            config, notes = jc.load_config(path)
            self.assertEqual(notes, [])
            self.assertEqual(config["repos"], [Path("/fake/repoA"), Path("/fake/repoB")])
            for r in config["repos"]:
                self.assertIsInstance(r, Path)

    def test_unknown_keys_are_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.json"
            path.write_text(json.dumps({
                "repos": ["/fake/repoA"],
                "some_unknown_key": True,
                "another": {"nested": 1},
            }))
            config, notes = jc.load_config(path)
            self.assertEqual(set(config), {"repos"})
            self.assertEqual(config["repos"], [Path("/fake/repoA")])


# ---- 2. read_inbox ------------------------------------------------------------------------------


class ReadInboxTests(unittest.TestCase):
    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "inbox.md"
            result = jc.read_inbox(path)
            self.assertEqual(result, {
                "present": False, "path": str(path), "items": [], "truncated": False,
            })

    def test_marker_stripping_and_comment_blank_skip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "inbox.md"
            path.write_text("\n".join([
                "# a comment line, skipped",
                "",
                "- dash item",
                "* star item",
                "[ ] checkbox item",
                "plain item, no marker",
                "   ",
                "# another comment",
            ]))
            result = jc.read_inbox(path)
            self.assertTrue(result["present"])
            self.assertFalse(result["truncated"])
            self.assertEqual(result["items"], [
                "dash item", "star item", "checkbox item", "plain item, no marker",
            ])

    def test_truncation_at_max_inbox_items(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "inbox.md"
            n = jc.MAX_INBOX_ITEMS + 5
            path.write_text("\n".join(f"- item {i}" for i in range(n)))
            result = jc.read_inbox(path)
            self.assertTrue(result["present"])
            self.assertTrue(result["truncated"])
            self.assertEqual(len(result["items"]), jc.MAX_INBOX_ITEMS)
            self.assertEqual(result["items"][0], "item 0")


# ---- 3. scan_kit_tasks --------------------------------------------------------------------------


class ScanKitTasksTests(unittest.TestCase):
    def test_two_kits_pending_and_in_progress_kept_done_blocked_dropped(self):
        with tempfile.TemporaryDirectory() as td:
            kits_dir = Path(td) / "kits"
            healthy = (
                _kit_task_block("A1", "Pending task one", "pending", model="sonnet")
                + "\n"
                + _kit_task_block("A2", "In progress task two", "in-progress", model="opus")
                + "\n"
                + _kit_task_block("A3", "Done task three", "done")
                + "\n"
                + _kit_task_block("A4", "Blocked task four", "blocked")
            )
            _write_kit(kits_dir, "kitA", healthy)

            items, errors = jc.scan_kit_tasks(kits_dir)
            self.assertEqual(errors, [])
            self.assertEqual(items, [
                {"kit": "kitA", "id": "A1", "title": "Pending task one",
                 "status": "pending", "model": "sonnet"},
                {"kit": "kitA", "id": "A2", "title": "In progress task two",
                 "status": "in-progress", "model": "opus"},
            ])

    def test_malformed_kit_lands_in_errors_without_killing_the_other_kit(self):
        with tempfile.TemporaryDirectory() as td:
            kits_dir = Path(td) / "kits"
            healthy = _kit_task_block("A1", "Pending task one", "pending", model="sonnet")
            _write_kit(kits_dir, "kitA", healthy)
            malformed = _kit_task_block("B1", "Bad status task", "not-a-real-status")
            _write_kit(kits_dir, "kitB", malformed)

            items, errors = jc.scan_kit_tasks(kits_dir)
            self.assertEqual(len(errors), 1)
            self.assertIn("kitB", errors[0])
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["kit"], "kitA")
            self.assertEqual(items[0]["id"], "A1")

    def test_cap_respected_across_many_pending_tasks(self):
        with tempfile.TemporaryDirectory() as td:
            kits_dir = Path(td) / "kits"
            n = jc.MAX_KIT_TASKS + 5
            blocks = "\n".join(
                _kit_task_block(f"C{i:04d}", f"Cap fixture task {i}", "pending")
                for i in range(n)
            )
            _write_kit(kits_dir, "kitCap", blocks)

            items, errors = jc.scan_kit_tasks(kits_dir)
            self.assertEqual(errors, [])
            self.assertEqual(len(items), jc.MAX_KIT_TASKS)


# ---- 4. build_wip --------------------------------------------------------------------------------


class BuildWipTests(unittest.TestCase):
    def test_dirty_repos_in_clean_repos_out(self):
        git_report = {
            "extra": {
                "repos": [
                    {"root": "/fake/repoA", "branch": "main", "dirty_files": 2,
                     "untracked": 1, "commit_count": 0, "commits": []},
                    {"root": "/fake/repoB", "branch": "main", "dirty_files": 0,
                     "untracked": 0, "commit_count": 3, "commits": []},
                    {"root": "/fake/repoC", "branch": "dev", "dirty_files": 0,
                     "untracked": 2, "commit_count": 0, "commits": []},
                ],
            },
        }
        wip = jc.build_wip(git_report)
        self.assertEqual(wip, [
            {"repo": "repoA", "branch": "main", "dirty_files": 2, "untracked": 1},
            {"repo": "repoC", "branch": "dev", "dirty_files": 0, "untracked": 2},
        ])

    def test_no_repos_key_yields_empty_wip(self):
        self.assertEqual(jc.build_wip({}), [])
        self.assertEqual(jc.build_wip({"extra": {}}), [])


# ---- 5. build_digest -----------------------------------------------------------------------------


class BuildDigestTests(unittest.TestCase):
    def _reports(self):
        # Built from journal_sources' OWN schema-locked empty_report helper (jc.js is the
        # journal_sources instance journal_collect.py itself loaded) -- never hand-rolled, so
        # this stays in lockstep with T5's schema lock.
        reports = {
            "claude_code": jc.js.empty_report("claude_code", True),
            "copilot_cli": jc.js.empty_report("copilot_cli", True),
            "codex_cli": jc.js.empty_report("codex_cli", False),
            "git": jc.js.empty_report("git", False),
        }
        reports["claude_code"]["available"] = True
        reports["claude_code"]["sessions"] = 2
        reports["claude_code"]["usd"] = 1.5

        reports["copilot_cli"]["available"] = True
        reports["copilot_cli"]["sessions"] = 0
        reports["copilot_cli"]["usd"] = None  # e.g. "no pricing provided"

        reports["codex_cli"]["available"] = True
        reports["codex_cli"]["sessions"] = 0
        reports["codex_cli"]["usd"] = None

        # git-only-activity day: zero sessions, but commits present.
        reports["git"]["available"] = True
        reports["git"]["sessions"] = 0
        reports["git"]["usd"] = None
        reports["git"]["extra"]["repos"] = [{
            "root": "/fake/repoA", "branch": "main", "dirty_files": 0, "untracked": 0,
            "commit_count": 3,
            "commits": [{"sha": "abc123", "date": "2026-06-30T10:00:00+00:00",
                         "author": "T", "subject": "fixture commit"}],
        }]
        return reports

    def test_top_level_key_set_is_frozen(self):
        signals = {"kit_tasks": [], "inbox": {"present": False, "path": "x", "items": [],
                                               "truncated": False}, "wip": []}
        digest = jc.build_digest(self._reports(), DAY_START, DAY_END, "2026-06-30", signals)
        self.assertEqual(frozenset(digest), DIGEST_TOP_KEYS)

    def test_usd_priced_ignores_none_and_sums_only_priced_sources(self):
        signals = {"kit_tasks": [], "inbox": {}, "wip": []}
        digest = jc.build_digest(self._reports(), DAY_START, DAY_END, "2026-06-30", signals)
        self.assertAlmostEqual(digest["totals"]["usd_priced"], 1.5, places=9)
        self.assertEqual(digest["totals"]["sessions"], 2)

    def test_sources_active_includes_git_only_day(self):
        signals = {"kit_tasks": [], "inbox": {}, "wip": []}
        digest = jc.build_digest(self._reports(), DAY_START, DAY_END, "2026-06-30", signals)
        active = set(digest["totals"]["sources_active"])
        self.assertIn("claude_code", active)  # sessions > 0
        self.assertIn("git", active)          # sessions == 0 but commit_count > 0
        self.assertNotIn("copilot_cli", active)  # sessions == 0, no commits
        self.assertNotIn("codex_cli", active)

    def test_unpriced_sources_lists_available_and_unpriced_only(self):
        signals = {"kit_tasks": [], "inbox": {}, "wip": []}
        digest = jc.build_digest(self._reports(), DAY_START, DAY_END, "2026-06-30", signals)
        unpriced = set(digest["totals"]["unpriced_sources"])
        self.assertEqual(unpriced, {"codex_cli", "git"})
        # copilot_cli has usd=None but priced=True -- NOT in unpriced_sources (priced flag,
        # not usd value, drives this list).
        self.assertNotIn("copilot_cli", unpriced)
        self.assertNotIn("claude_code", unpriced)


# ---- 6. end-to-end main() -------------------------------------------------------------------------


class MainEndToEndTests(unittest.TestCase):
    def _base_fixture(self, root):
        """Build a claude + copilot + codex + one open kit task + inbox fixture under root.
        Returns the dict of CLI override paths (never real home paths)."""
        claude_root = root / "claude" / "projects"
        proj = claude_root / "-fake-projA"
        proj.mkdir(parents=True)
        (proj / "sess1.jsonl").write_text(
            _claude_line("fake-big", "2026-06-30T10:00:00Z", "m1", cwd="/work/projA") + "\n"
        )

        copilot_home = root / "copilot"
        _mk_copilot_session(copilot_home, "sess-co-1", [
            _ev("session.start", "2026-06-30T09:00:00Z", selectedModel="fake-copilot-x"),
            _ev("assistant.message", "2026-06-30T09:01:00Z", model="fake-copilot-x",
                outputTokens=40, apiCallId="c1"),
            _ev("session.shutdown", "2026-06-30T09:02:00Z", totalNanoAiu=100000000,
                totalPremiumRequests=1, currentModel="fake-copilot-x",
                tokenDetails=_td(400, 0, 0, 40)),
        ], "id: sess-co-1\nname: proj-co\ncwd: /work/proj-co\n")

        codex_home = root / "codex"
        codex_home.mkdir(parents=True)
        (codex_home / "session_index.jsonl").write_text(
            json.dumps({"id": "codex-1", "created_at": "2026-06-30T09:30:00Z"}) + "\n"
        )

        kits_dir = root / "kits"
        _write_kit(kits_dir, "kitX",
                   _kit_task_block("X1", "Open fixture task", "pending", model="sonnet"))

        journal_dir = root / "journal"
        journal_dir.mkdir(parents=True)
        (journal_dir / "inbox.md").write_text("- inbox item one\n- inbox item two\n")
        (journal_dir / "config.json").write_text(json.dumps({"repos": []}))

        return {
            "claude_projects": claude_root, "copilot_home": copilot_home,
            "codex_home": codex_home, "kits_dir": kits_dir, "journal_dir": journal_dir,
        }

    def _argv(self, paths, extra=()):
        return [
            "--date", "2026-06-30", "--utc",
            "--claude-projects", str(paths["claude_projects"]),
            "--copilot-home", str(paths["copilot_home"]),
            "--codex-home", str(paths["codex_home"]),
            "--kits-dir", str(paths["kits_dir"]),
            "--journal-dir", str(paths["journal_dir"]),
        ] + list(extra)

    def test_digest_written_where_expected_with_active_sources(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = self._base_fixture(root)
            rc, _out = _call_main(self._argv(paths))
            self.assertEqual(rc, 0)
            digest_path = paths["journal_dir"] / "2026-06-30" / "digest.json"
            self.assertTrue(digest_path.is_file())
            digest = json.loads(digest_path.read_text())
            self.assertEqual(frozenset(digest), DIGEST_TOP_KEYS)
            self.assertTrue(digest["sources"]["claude_code"]["available"])
            self.assertTrue(digest["sources"]["copilot_cli"]["available"])
            self.assertTrue(digest["sources"]["codex_cli"]["available"])
            self.assertEqual(len(digest["signals"]["kit_tasks"]), 1)
            self.assertEqual(digest["signals"]["kit_tasks"][0]["id"], "X1")
            self.assertEqual(digest["signals"]["inbox"]["items"],
                              ["inbox item one", "inbox item two"])

    def test_print_flag_dumps_parseable_json_to_stdout(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = self._base_fixture(root)
            rc, out = _call_main(self._argv(paths, extra=["--print"]))
            self.assertEqual(rc, 0)
            json_start = out.index("{")
            parsed = json.loads(out[json_start:])
            self.assertEqual(frozenset(parsed), DIGEST_TOP_KEYS)

    def test_rerun_overwrites_not_appends(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = self._base_fixture(root)
            rc1, _ = _call_main(self._argv(paths))
            self.assertEqual(rc1, 0)
            digest_path = paths["journal_dir"] / "2026-06-30" / "digest.json"
            first = json.loads(digest_path.read_text())
            self.assertEqual(len(first["signals"]["inbox"]["items"]), 2)

            (paths["journal_dir"] / "inbox.md").write_text(
                "- inbox item one\n- inbox item two\n- inbox item three\n"
            )
            rc2, _ = _call_main(self._argv(paths))
            self.assertEqual(rc2, 0)
            second_text = digest_path.read_text()
            second = json.loads(second_text)  # still a single well-formed JSON doc
            self.assertEqual(len(second["signals"]["inbox"]["items"]), 3)
            self.assertEqual(second["signals"]["inbox"]["items"][-1], "inbox item three")

    def test_crashing_source_root_records_error_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = self._base_fixture(root)

            def _raiser(ctx):
                raise RuntimeError("synthetic crash injected by T7 test")

            original_adapters = jc.js.ADAPTERS
            patched = tuple(
                (name, _raiser) if name == "claude_code" else (name, fn)
                for name, fn in original_adapters
            )
            jc.js.ADAPTERS = patched
            try:
                rc, _out = _call_main(self._argv(paths))
            finally:
                jc.js.ADAPTERS = original_adapters
            self.assertEqual(rc, 0)

            digest_path = paths["journal_dir"] / "2026-06-30" / "digest.json"
            digest = json.loads(digest_path.read_text())
            errors = digest["sources"]["claude_code"]["errors"]
            self.assertTrue(errors)
            self.assertIn("adapter crashed", errors[0])
            # The other sources stayed intact despite the crash.
            self.assertTrue(digest["sources"]["copilot_cli"]["available"])

    def test_cli_entry_point_smoke_via_subprocess(self):
        # The ONE sanctioned subprocess use in this file: invoking bin/journal_collect.py
        # itself (never a third-party CLI) via sys.executable, every root flag pointed at
        # temp fixtures.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = self._base_fixture(root)
            script = BIN_DIR / "journal_collect.py"
            proc = subprocess.run(
                [sys.executable, str(script)] + self._argv(paths),
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            digest_path = paths["journal_dir"] / "2026-06-30" / "digest.json"
            self.assertTrue(digest_path.is_file())


# ---- 7. CLI error paths -------------------------------------------------------------------------


class MainErrorPathTests(unittest.TestCase):
    def test_garbage_date_raises_systemexit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            argv = [
                "--date", "not-a-real-date", "--utc",
                "--claude-projects", str(root / "claude"),
                "--copilot-home", str(root / "copilot"),
                "--codex-home", str(root / "codex"),
                "--kits-dir", str(root / "kits"),
                "--journal-dir", str(root / "journal"),
            ]
            with self.assertRaises(SystemExit):
                jc.main(argv)

    def test_unwritable_journal_dir_raises_systemexit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            journal_as_file = root / "journal_as_a_file"
            journal_as_file.write_text("this is a file, not a directory")
            argv = [
                "--date", "2026-06-30", "--utc",
                "--claude-projects", str(root / "claude"),
                "--copilot-home", str(root / "copilot"),
                "--codex-home", str(root / "codex"),
                "--kits-dir", str(root / "kits"),
                "--journal-dir", str(journal_as_file),
            ]
            with self.assertRaises(SystemExit):
                jc.main(argv)


# ---- 8. READ-ONLY byte-snapshot proof -------------------------------------------------------------


class ReadOnlyProofTests(unittest.TestCase):
    def test_source_and_kit_trees_are_byte_identical_only_journal_dir_gains_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            claude_root = root / "claude" / "projects"
            proj = claude_root / "-fake-projA"
            proj.mkdir(parents=True)
            (proj / "sess1.jsonl").write_text(
                _claude_line("fake-big", "2026-06-30T10:00:00Z", "ro1",
                             cwd="/work/projA") + "\n"
            )

            copilot_home = root / "copilot"
            _mk_copilot_session(copilot_home, "sess-co-1", [
                _ev("session.start", "2026-06-30T09:00:00Z", selectedModel="fake-copilot-x"),
                _ev("assistant.message", "2026-06-30T09:01:00Z", model="fake-copilot-x",
                    outputTokens=40, apiCallId="ro2"),
                _ev("session.shutdown", "2026-06-30T09:02:00Z", totalNanoAiu=100000000,
                    totalPremiumRequests=1, currentModel="fake-copilot-x",
                    tokenDetails=_td(400, 0, 0, 40)),
            ], "id: sess-co-1\nname: proj-co\ncwd: /work/proj-co\n")

            codex_home = root / "codex"
            codex_home.mkdir(parents=True)
            (codex_home / "session_index.jsonl").write_text(
                json.dumps({"id": "ro3", "created_at": "2026-06-30T09:30:00Z"}) + "\n"
            )

            kits_dir = root / "kits"
            _write_kit(kits_dir, "kitX",
                       _kit_task_block("X1", "Read-only fixture task", "pending"))

            journal_dir = root / "journal"
            journal_dir.mkdir(parents=True)
            (journal_dir / "inbox.md").write_text("- pre-existing inbox item\n")
            (journal_dir / "config.json").write_text(json.dumps({"repos": []}))

            def snapshot():
                files = sorted(p for p in root.rglob("*") if p.is_file())
                return {p: p.read_bytes() for p in files}

            before = snapshot()
            rc, _out = _call_main([
                "--date", "2026-06-30", "--utc",
                "--claude-projects", str(claude_root),
                "--copilot-home", str(copilot_home),
                "--codex-home", str(codex_home),
                "--kits-dir", str(kits_dir),
                "--journal-dir", str(journal_dir),
            ])
            self.assertEqual(rc, 0)
            after = snapshot()

            # Every pre-existing file is byte-identical afterward.
            for path, data in before.items():
                self.assertIn(path, after)
                self.assertEqual(after[path], data, f"{path} was mutated")

            # Every newly created file lives under journal_dir.
            new_paths = set(after) - set(before)
            self.assertTrue(new_paths)
            for path in new_paths:
                self.assertIn(journal_dir, path.parents)


# ---- 9. content hygiene -------------------------------------------------------------------------


class ContentHygieneTests(unittest.TestCase):
    def test_transcript_text_marker_never_reaches_the_written_digest(self):
        marker = "SECRET-TRANSCRIPT-TEXT"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            claude_root = root / "claude" / "projects"
            proj = claude_root / "-fake-projA"
            proj.mkdir(parents=True)
            (proj / "sess1.jsonl").write_text(
                _claude_line(
                    "fake-big", "2026-06-30T10:00:00Z", "hy1", cwd="/work/projA",
                    content=[{"type": "text",
                              "text": f"assistant prose containing {marker} inline"}],
                ) + "\n"
            )
            journal_dir = root / "journal"
            journal_dir.mkdir(parents=True)

            rc, out = _call_main([
                "--date", "2026-06-30", "--utc",
                "--claude-projects", str(claude_root),
                "--copilot-home", str(root / "copilot"),
                "--codex-home", str(root / "codex"),
                "--kits-dir", str(root / "kits"),
                "--journal-dir", str(journal_dir),
                "--print",
            ])
            self.assertEqual(rc, 0)
            self.assertNotIn(marker, out)

            digest_path = journal_dir / "2026-06-30" / "digest.json"
            digest_text = digest_path.read_text()
            self.assertNotIn(marker, digest_text)
            # Sanity: the fixture really did carry activity for that message (otherwise this
            # test would trivially pass by never having processed the record at all).
            digest = json.loads(digest_text)
            self.assertEqual(digest["sources"]["claude_code"]["extra"]["messages"], 1)


if __name__ == "__main__":
    unittest.main()
