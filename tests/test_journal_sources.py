"""Stdlib unittest regression suite for bin/journal_sources.py (PLAN.md D1-D7).

SAFETY CONTRACT (binds every test in this file): no test here ever reads or writes any of the
three real tool home directories that journal_sources.py can be pointed at (the user's real
Claude Code project store, Copilot CLI home, or Codex CLI home), and no test here resolves the
caller's real home directory via the stdlib Path.home helper. Every fixture -- Claude Code
transcript lines, Copilot CLI event/workspace lines, Codex CLI JSONL lines, and git
repositories -- is synthesized in-process under a fresh tempfile.TemporaryDirectory() per
test, and every source root is passed to the adapters explicitly via ctx (never inferred from
this machine). Both pricing dicts (P_CLAUDE, P_COPILOT) are synthetic module-level constants
-- fake model ids, round numbers -- and the real plugin pricing files are never opened by this
file. No test here invokes a real Claude, Copilot, or Codex CLI binary -- journal_sources.py
makes no such call to invoke. The ONLY subprocess use anywhere in this file is the read-only
git binary (via the `_mkrepo`/`_commit` fixture helpers, mirroring T4's own verify command),
used purely to build throwaway repositories inside temp dirs; tests that need it skip cleanly
when git is not on PATH. Day windows passed to adapters are always explicit, aware UTC
datetimes -- never the machine's local timezone.

bin/ is not a package; journal_sources.py is loaded via importlib by absolute path computed
from this file's own location (BIN_DIR), mirroring tests/test_copilot_usage.py.
"""

import importlib.util
import json
import os
import shutil
import subprocess
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


js = _load("journal_sources")


# ---- synthetic pricing fixtures ------------------------------------------------------------
#
# Deliberately fake ids and round numbers -- one Claude-side model with NO intro_pricing (so
# rates_for always returns the base rates) and one Copilot-side "mid" model with a
# billing_unit.usd_per_credit nowhere near the real rate, proving every dollar figure below is
# derived from these dicts at run time, never hardcoded.

P_CLAUDE = {
    "cached_date": "2020-01-01",
    "cache_read_multiplier": 0.1,
    "cache_write_multiplier_5m": 1.25,
    "models": {
        "fake-big": {
            "display": "Fake Big",
            "tier": "opus",
            "input_per_mtok": 10.0,
            "output_per_mtok": 50.0,
        },
    },
}

P_COPILOT = {
    "cached_date": "2020-01-01",
    "billing_unit": {"name": "FIC", "usd_per_credit": 0.5},
    "models": {
        "fake-co": {
            "display": "Fake Co",
            "tier": "mid",
            "input_per_mtok": 2.0,
            "cached_input_per_mtok": 0.2,
            "output_per_mtok": 8.0,
        },
    },
}

# The day window used throughout: an explicit, aware UTC datetime pair -- never local time.
DAY_START = datetime(2026, 6, 30, tzinfo=timezone.utc)
DAY_END = DAY_START + timedelta(days=1)

REPORT_KEYS = frozenset({
    "source", "available", "priced", "deferred", "sessions", "first_ts", "last_ts",
    "models", "totals", "usd", "projects", "tool_uses", "errors", "notes", "extra",
})


def _base_ctx(**overrides):
    ctx = {
        "day_start": DAY_START, "day_end": DAY_END,
        "claude_projects": None, "copilot_home": None, "codex_home": None,
        "repos": [], "pricing_claude": None, "pricing_copilot": None,
    }
    ctx.update(overrides)
    return ctx


# ---- Claude Code transcript-line builder ----------------------------------------------------

def _crec(model, ts, mid, session_id="sess-1", inp=1000, out=100, cache_read=0,
          cache_write=0, cwd=None):
    obj = {
        "timestamp": ts,
        "sessionId": session_id,
        "message": {
            "model": model,
            "id": mid,
            "usage": {
                "input_tokens": inp,
                "output_tokens": out,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_write,
            },
        },
    }
    if cwd:
        obj["cwd"] = cwd
    return json.dumps(obj)


# ---- Copilot CLI event-line builder ----------------------------------------------------------

def _ev(etype, ts, **data):
    return json.dumps({"type": etype, "timestamp": ts, "data": data})


def _td(inp, cache_read, cache_write, out):
    return {
        "input": {"tokenCount": inp},
        "cache_read": {"tokenCount": cache_read},
        "cache_write": {"tokenCount": cache_write},
        "output": {"tokenCount": out},
    }


def _mksession(session_dir, name, lines, workspace_text=None):
    d = session_dir / name
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text("\n".join(lines) + "\n")
    if workspace_text is not None:
        (d / "workspace.yaml").write_text(workspace_text)
    return d


# ---- git repo fixture helper (git is the ONLY sanctioned subprocess in this file) -----------

def _git_available():
    return shutil.which("git") is not None


def _mkrepo(repo):
    """Init a throwaway repo at ``repo`` (Path, must already exist as a dir) on branch
    ``main``. Callers must skipTest first when git is unavailable (see ``_git_available``).
    """
    subprocess.run(
        ["git", "-C", str(repo), "init", "-q", "-b", "main"],
        capture_output=True, check=True,
    )


def _stage(repo, relname, content):
    (Path(repo) / relname).write_text(content)
    subprocess.run(
        ["git", "-C", str(repo), "add", relname], capture_output=True, check=True,
    )


def _commit(repo, message, when_iso, allow_empty=False):
    """One commit with both author and committer date pinned to ``when_iso`` -- mirrors T4's
    own verify command exactly (env-dated commits, offline, read-only plumbing only).
    """
    env = dict(os.environ, GIT_COMMITTER_DATE=when_iso)
    args = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=T", "commit", "-q"]
    if allow_empty:
        args.append("--allow-empty")
    args += ["-m", message, "--date", when_iso]
    subprocess.run(args, capture_output=True, check=True, env=env)


# ---- 1. day_window ----------------------------------------------------------------------------


class DayWindowTests(unittest.TestCase):
    def test_utc_window_is_exactly_24h_from_utc_midnight(self):
        day_start, day_end = js.day_window("2026-06-30", utc=True)
        self.assertEqual(day_start, datetime(2026, 6, 30, tzinfo=timezone.utc))
        self.assertEqual(day_end - day_start, timedelta(days=1))
        self.assertIsNotNone(day_start.tzinfo)
        self.assertIsNotNone(day_end.tzinfo)

    def test_garbage_date_string_raises_valueerror(self):
        with self.assertRaises(ValueError):
            js.day_window("not-a-real-date", utc=True)

    def test_local_mode_returns_aware_datetimes_spanning_24h(self):
        day_start, day_end = js.day_window("2026-06-30", utc=False)
        self.assertIsNotNone(day_start.tzinfo)
        self.assertIsNotNone(day_end.tzinfo)
        self.assertEqual(day_end - day_start, timedelta(days=1))


# ---- 2. empty_report schema lock ---------------------------------------------------------------


class EmptyReportTests(unittest.TestCase):
    def test_schema_is_locked_to_the_pinned_key_set(self):
        report = js.empty_report("fake_source", True)
        self.assertEqual(frozenset(report), REPORT_KEYS)

    def test_default_values(self):
        report = js.empty_report("fake_source", True)
        self.assertEqual(report["source"], "fake_source")
        self.assertFalse(report["available"])
        self.assertTrue(report["priced"])
        self.assertFalse(report["deferred"])
        self.assertEqual(report["sessions"], 0)
        self.assertIsNone(report["first_ts"])
        self.assertIsNone(report["last_ts"])
        self.assertEqual(report["models"], {})
        self.assertEqual(
            report["totals"], {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
        )
        self.assertIsNone(report["usd"])
        self.assertEqual(report["projects"], [])
        self.assertEqual(report["tool_uses"], 0)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["notes"], [])
        self.assertEqual(report["extra"], {})


# ---- 3. Claude Code adapter ---------------------------------------------------------------------


class ClaudeAdapterTests(unittest.TestCase):
    def test_message_id_dedupe_across_two_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "projects"
            proj = root / "-fake-projA"
            proj.mkdir(parents=True)
            (proj / "file1.jsonl").write_text(
                _crec("fake-big", "2026-06-30T10:00:00Z", "dup-1", cwd="/work/projA") + "\n"
            )
            (proj / "file2.jsonl").write_text(
                _crec("fake-big", "2026-06-30T11:00:00Z", "dup-1", cwd="/work/projA") + "\n"
            )
            ctx = _base_ctx(claude_projects=root, pricing_claude=P_CLAUDE)
            report = js.collect_claude(ctx)
            self.assertEqual(report["extra"]["messages"], 1)
            self.assertEqual(report["models"]["fake-big"]["messages"], 1)
            self.assertEqual(report["models"]["fake-big"]["input"], 1000)

    def test_day_filter_excludes_out_of_window_records(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "projects"
            proj = root / "-fake-projA"
            proj.mkdir(parents=True)
            (proj / "file1.jsonl").write_text("\n".join([
                _crec("fake-big", "2026-06-30T10:00:00Z", "in-1", cwd="/work/projA"),
                _crec("outside-window-model", "2026-06-29T10:00:00Z", "out-1",
                      cwd="/work/projA"),
                _crec("outside-window-model", "2026-07-01T00:00:00Z", "out-2",
                      cwd="/work/projA"),
            ]) + "\n")
            ctx = _base_ctx(claude_projects=root, pricing_claude=P_CLAUDE)
            report = js.collect_claude(ctx)
            self.assertEqual(report["extra"]["messages"], 1)
            self.assertNotIn("outside-window-model", report["models"])

    def test_untimestamped_records_excluded_and_counted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "projects"
            proj = root / "-fake-projA"
            proj.mkdir(parents=True)
            no_ts = json.dumps({
                "sessionId": "sess-1",
                "message": {
                    "model": "fake-big", "id": "no-ts",
                    "usage": {"input_tokens": 5, "output_tokens": 5},
                },
            })
            (proj / "file1.jsonl").write_text("\n".join([
                _crec("fake-big", "2026-06-30T10:00:00Z", "in-1", cwd="/work/projA"),
                no_ts,
            ]) + "\n")
            ctx = _base_ctx(claude_projects=root, pricing_claude=P_CLAUDE)
            report = js.collect_claude(ctx)
            self.assertEqual(report["extra"]["untimestamped_records"], 1)
            self.assertEqual(report["extra"]["messages"], 1)

    def test_unmatched_model_bucketed_as_unpriced(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "projects"
            proj = root / "-fake-projA"
            proj.mkdir(parents=True)
            (proj / "file1.jsonl").write_text(
                _crec("mystery-model-9000", "2026-06-30T10:00:00Z", "u1",
                      cwd="/work/projA") + "\n"
            )
            ctx = _base_ctx(claude_projects=root, pricing_claude=P_CLAUDE)
            report = js.collect_claude(ctx)
            self.assertIn("mystery-model-9000", report["extra"]["unpriced_models"])
            self.assertIsNone(report["models"]["mystery-model-9000"]["usd"])
            self.assertEqual(report["models"]["mystery-model-9000"]["input"], 1000)
            self.assertEqual(report["usd"], 0.0)

    def test_hand_math_usd_matches_pricing_including_cache_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "projects"
            proj = root / "-fake-projA"
            proj.mkdir(parents=True)
            (proj / "file1.jsonl").write_text(
                _crec("fake-big", "2026-06-30T10:00:00Z", "h1", inp=1000, out=100,
                      cache_read=2000, cache_write=500, cwd="/work/projA") + "\n"
            )
            ctx = _base_ctx(claude_projects=root, pricing_claude=P_CLAUDE)
            report = js.collect_claude(ctx)
            expected = (
                1000 * 10.0 + 100 * 50.0 + 2000 * 10.0 * 0.1 + 500 * 10.0 * 1.25
            ) / 1e6
            self.assertAlmostEqual(report["usd"], expected, places=9)
            b = report["models"]["fake-big"]
            self.assertEqual(b["cache_read"], 2000)
            self.assertEqual(b["cache_write"], 500)
            self.assertAlmostEqual(b["usd"], expected, places=9)

    def test_projects_from_cwd_basename_with_slug_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "projects"
            proj = root / "-fake-slugProj"
            proj.mkdir(parents=True)
            (proj / "file1.jsonl").write_text("\n".join([
                _crec("fake-big", "2026-06-30T10:00:00Z", "p1",
                      cwd="/Users/dev/actual-project-name"),
                _crec("fake-big", "2026-06-30T10:05:00Z", "p2"),  # no cwd -> slug fallback
            ]) + "\n")
            ctx = _base_ctx(claude_projects=root, pricing_claude=P_CLAUDE)
            report = js.collect_claude(ctx)
            self.assertIn("actual-project-name", report["projects"])
            self.assertIn("-fake-slugProj", report["projects"])

    def test_no_pricing_provided_yields_usd_none_with_note(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "projects"
            proj = root / "-fake-projA"
            proj.mkdir(parents=True)
            (proj / "file1.jsonl").write_text(
                _crec("fake-big", "2026-06-30T10:00:00Z", "n1", cwd="/work/projA") + "\n"
            )
            ctx = _base_ctx(claude_projects=root, pricing_claude=None)
            report = js.collect_claude(ctx)
            self.assertIsNone(report["usd"])
            self.assertIn("no pricing provided", report["notes"])
            self.assertIn("fake-big", report["extra"]["unpriced_models"])

    def test_projects_dir_missing_is_unavailable(self):
        ctx = _base_ctx(claude_projects=None, pricing_claude=P_CLAUDE)
        report = js.collect_claude(ctx)
        self.assertFalse(report["available"])
        self.assertIn("claude projects dir not found", report["notes"])


# ---- 4. Copilot CLI adapter -----------------------------------------------------------------


class CopilotAdapterTests(unittest.TestCase):
    def test_last_event_day_membership_rule(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "cohome" / "session-state"
            _mksession(state, "sess-in", [
                _ev("session.start", "2026-06-30T09:00:00Z", selectedModel="fake-co"),
                _ev("assistant.message", "2026-06-30T09:01:00Z", model="fake-co",
                    outputTokens=50, apiCallId="a1"),
                _ev("session.shutdown", "2026-06-30T09:02:00Z", totalNanoAiu=1000000000,
                    totalPremiumRequests=1, currentModel="fake-co",
                    tokenDetails=_td(1000, 0, 0, 50)),
            ], "id: sess-in\nname: proj-in\ncwd: /work/proj-in\n")
            _mksession(state, "sess-out", [
                _ev("session.start", "2026-06-29T09:00:00Z", selectedModel="fake-co"),
                _ev("session.shutdown", "2026-06-29T09:02:00Z", totalNanoAiu=500000000,
                    totalPremiumRequests=1, currentModel="fake-co",
                    tokenDetails=_td(100, 0, 0, 20)),
            ], "id: sess-out\nname: proj-out\ncwd: /work/proj-out\n")
            ctx = _base_ctx(copilot_home=Path(td) / "cohome", pricing_copilot=P_COPILOT)
            report = js.collect_copilot(ctx)
            self.assertEqual(report["sessions"], 1)
            self.assertIn("proj-in", report["projects"])
            self.assertNotIn("proj-out", report["projects"])

    def test_single_model_session_is_attributed_exactly(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "cohome" / "session-state"
            _mksession(state, "sess-single", [
                _ev("session.start", "2026-06-30T09:00:00Z", selectedModel="fake-co"),
                _ev("assistant.message", "2026-06-30T09:01:00Z", model="fake-co",
                    outputTokens=50, apiCallId="s1"),
                _ev("session.shutdown", "2026-06-30T09:02:00Z", totalNanoAiu=1000000000,
                    totalPremiumRequests=1, currentModel="fake-co",
                    tokenDetails=_td(1000, 0, 0, 50)),
            ], "id: sess-single\nname: proj-s\ncwd: /work/proj-s\n")
            ctx = _base_ctx(copilot_home=Path(td) / "cohome", pricing_copilot=P_COPILOT)
            report = js.collect_copilot(ctx)
            self.assertIn("fake-co", report["models"])
            self.assertFalse(any("multi-model" in n for n in report["notes"]))
            expected = (1000 * 2.0 + 50 * 8.0) / 1e6
            self.assertAlmostEqual(report["usd"], expected, places=9)

    def test_multi_model_session_attributed_to_last_model_with_note(self):
        # A local pricing dict with a SECOND mid model, used only for this multi-model
        # scenario (P_COPILOT itself stays the pinned single-model fixture). The second key
        # is deliberately NOT a "<key>-suffix" of "fake-co" -- match_model's suffix-matching
        # is meant for date-suffixed ids (e.g. "model-20260101"), and a key like "fake-co-2"
        # would collide with that heuristic and resolve back to "fake-co".
        pricing_multi = json.loads(json.dumps(P_COPILOT))
        pricing_multi["models"]["fake-hi"] = {
            "display": "Fake Hi", "tier": "mid",
            "input_per_mtok": 3.0, "cached_input_per_mtok": 0.3, "output_per_mtok": 9.0,
        }
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "cohome" / "session-state"
            _mksession(state, "sess-multi", [
                _ev("session.start", "2026-06-30T09:00:00Z", selectedModel="fake-co"),
                _ev("session.model_change", "2026-06-30T09:01:00Z",
                    previousModel="fake-co", newModel="fake-hi"),
                _ev("assistant.message", "2026-06-30T09:02:00Z", model="fake-co",
                    outputTokens=20, apiCallId="m1"),
                _ev("assistant.message", "2026-06-30T09:03:00Z", model="fake-hi",
                    outputTokens=30, apiCallId="m2"),
                _ev("session.shutdown", "2026-06-30T09:04:00Z", totalNanoAiu=2000000000,
                    totalPremiumRequests=1, currentModel="fake-hi",
                    tokenDetails=_td(500, 0, 0, 50)),
            ], "id: sess-multi\nname: proj-m\ncwd: /work/proj-m\n")
            ctx = _base_ctx(copilot_home=Path(td) / "cohome", pricing_copilot=pricing_multi)
            report = js.collect_copilot(ctx)
            self.assertIn("fake-hi", report["models"])
            self.assertNotIn("fake-co", report["models"])
            self.assertTrue(any(
                "multi-model session attributed to last model" in n for n in report["notes"]
            ))

    def test_aiu_reported_and_aic_math_against_billing_unit(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "cohome" / "session-state"
            _mksession(state, "sess-a", [
                _ev("session.start", "2026-06-30T09:00:00Z", selectedModel="fake-co"),
                _ev("assistant.message", "2026-06-30T09:01:00Z", model="fake-co",
                    outputTokens=50, apiCallId="a1"),
                _ev("session.shutdown", "2026-06-30T09:02:00Z", totalNanoAiu=2500000000,
                    totalPremiumRequests=1, currentModel="fake-co",
                    tokenDetails=_td(1000, 0, 0, 50)),
            ], "id: sess-a\nname: proj-a\ncwd: /work/proj-a\n")
            ctx = _base_ctx(copilot_home=Path(td) / "cohome", pricing_copilot=P_COPILOT)
            report = js.collect_copilot(ctx)
            self.assertAlmostEqual(report["extra"]["aiu_reported"], 2.5, places=9)
            expected_usd = (1000 * 2.0 + 50 * 8.0) / 1e6
            self.assertAlmostEqual(report["usd"], expected_usd, places=9)
            self.assertAlmostEqual(report["extra"]["aic"], expected_usd / 0.5, places=9)

    def test_output_only_session_flagged_in_notes(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "cohome" / "session-state"
            _mksession(state, "sess-out-only", [
                _ev("session.start", "2026-06-30T09:00:00Z", selectedModel="fake-co"),
                _ev("assistant.message", "2026-06-30T09:01:00Z", model="fake-co",
                    outputTokens=150, apiCallId="o1"),
                # No session.shutdown at all -> no tokenDetails -> output-only fallback.
            ], "id: sess-out-only\nname: proj-o\ncwd: /work/proj-o\n")
            ctx = _base_ctx(copilot_home=Path(td) / "cohome", pricing_copilot=P_COPILOT)
            report = js.collect_copilot(ctx)
            self.assertTrue(any("output tokens only" in n for n in report["notes"]))

    def test_missing_session_state_dir_is_unavailable(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "cohome"  # no session-state subdir created at all
            ctx = _base_ctx(copilot_home=home, pricing_copilot=P_COPILOT)
            report = js.collect_copilot(ctx)
            self.assertFalse(report["available"])
            self.assertIn("copilot session-state dir not found", report["notes"])


# ---- 5. Codex CLI adapter -------------------------------------------------------------------


class CodexAdapterTests(unittest.TestCase):
    def test_iso_epoch_seconds_and_epoch_ms_timestamps_all_parse(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "codex"
            home.mkdir(parents=True)
            epoch_s = int(datetime(2026, 6, 30, 11, 0, tzinfo=timezone.utc).timestamp())
            epoch_ms = int(
                datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc).timestamp() * 1000
            )
            (home / "session_index.jsonl").write_text("\n".join([
                json.dumps({"id": "s-iso", "created_at": "2026-06-30T09:00:00Z"}),
                json.dumps({"id": "s-epoch-s", "created_at": epoch_s}),
                json.dumps({"id": "s-epoch-ms", "created_at": epoch_ms}),
            ]) + "\n")
            ctx = _base_ctx(codex_home=home)
            report = js.collect_codex(ctx)
            self.assertEqual(report["extra"]["records"], 3)
            self.assertEqual(report["sessions"], 3)

    def test_malformed_and_non_dict_lines_counted_not_crashed(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "codex"
            home.mkdir(parents=True)
            (home / "session_index.jsonl").write_text("\n".join([
                "NOT JSON AT ALL {{{",
                json.dumps([1, 2, 3]),  # valid JSON, but not a dict
                json.dumps({"id": "ok1", "created_at": "2026-06-30T09:00:00Z"}),
            ]) + "\n")
            ctx = _base_ctx(codex_home=home)
            report = js.collect_codex(ctx)
            self.assertEqual(report["extra"]["malformed_lines"], 2)
            self.assertEqual(report["extra"]["records"], 1)

    def test_session_dedupe_across_both_files(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "codex"
            home.mkdir(parents=True)
            (home / "session_index.jsonl").write_text(
                json.dumps({"id": "shared-1", "created_at": "2026-06-30T09:00:00Z"}) + "\n"
            )
            (home / "history.jsonl").write_text(
                json.dumps({"session_id": "shared-1", "ts": "2026-06-30T10:00:00Z"}) + "\n"
            )
            ctx = _base_ctx(codex_home=home)
            report = js.collect_codex(ctx)
            self.assertEqual(report["sessions"], 1)
            self.assertEqual(report["extra"]["records"], 2)

    def test_zero_usage_records_still_counted(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "codex"
            home.mkdir(parents=True)
            (home / "session_index.jsonl").write_text(
                json.dumps({"id": "zz1", "created_at": "2026-06-30T09:00:00Z"}) + "\n"
            )
            ctx = _base_ctx(codex_home=home)
            report = js.collect_codex(ctx)
            self.assertEqual(report["extra"]["records"], 1)
            self.assertEqual(
                report["totals"], {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
            )

    def test_priced_false_usd_none_with_pinned_unpriced_note(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "codex"
            home.mkdir(parents=True)
            (home / "session_index.jsonl").write_text(
                json.dumps({"id": "p1", "created_at": "2026-06-30T09:00:00Z"}) + "\n"
            )
            ctx = _base_ctx(codex_home=home)
            report = js.collect_codex(ctx)
            self.assertFalse(report["priced"])
            self.assertIsNone(report["usd"])
            self.assertIn(js.CODEX_UNPRICED_NOTE, report["notes"])

    def test_sqlite_subdir_present_and_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "codex"
            (home / "sqlite").mkdir(parents=True)
            (home / "sqlite" / "codex-dev.db").write_bytes(b"\x00NEVER-OPEN\x01")
            (home / "session_index.jsonl").write_text(
                json.dumps({"id": "sq1", "created_at": "2026-06-30T09:00:00Z"}) + "\n"
            )
            before = (home / "sqlite" / "codex-dev.db").read_bytes()
            ctx = _base_ctx(codex_home=home)
            report = js.collect_codex(ctx)
            after = (home / "sqlite" / "codex-dev.db").read_bytes()
            self.assertEqual(before, after)
            self.assertEqual(report["extra"]["records"], 1)

    def test_home_present_but_no_jsonl_files_found(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "codex"
            home.mkdir(parents=True)
            ctx = _base_ctx(codex_home=home)
            report = js.collect_codex(ctx)
            self.assertTrue(report["available"])
            self.assertEqual(report["sessions"], 0)
            self.assertIn("no codex JSONL found", report["notes"])

    def test_codex_home_none_is_unavailable(self):
        ctx = _base_ctx(codex_home=None)
        report = js.collect_codex(ctx)
        self.assertFalse(report["available"])
        self.assertIn("codex home not found", report["notes"])


# ---- 6. git adapter -----------------------------------------------------------------------


class GitAdapterTests(unittest.TestCase):
    def setUp(self):
        if not _git_available():
            self.skipTest("git binary not available on PATH")

    def test_in_and_out_of_window_commits(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repoA"
            repo.mkdir()
            _mkrepo(repo)
            _stage(repo, "tracked.txt", "base\n")
            _commit(repo, "old commit", "2026-06-01T10:00:00+00:00")
            _commit(repo, "in-window work", "2026-06-30T10:00:00+00:00", allow_empty=True)
            ctx = _base_ctx(repos=[repo])
            report = js.collect_git(ctx)
            entry = report["extra"]["repos"][0]
            self.assertEqual(entry["commit_count"], 1)
            self.assertEqual(entry["commits"][0]["subject"], "in-window work")

    def test_dirty_and_untracked_counts(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repoB"
            repo.mkdir()
            _mkrepo(repo)
            _stage(repo, "tracked.txt", "base\n")
            _commit(repo, "init", "2026-06-30T09:00:00+00:00")
            (repo / "tracked.txt").write_text("base\nchanged\n")
            (repo / "untracked.txt").write_text("new\n")
            ctx = _base_ctx(repos=[repo])
            report = js.collect_git(ctx)
            entry = report["extra"]["repos"][0]
            self.assertGreaterEqual(entry["dirty_files"], 1)
            self.assertGreaterEqual(entry["untracked"], 1)
            self.assertTrue(entry["branch"])

    def test_non_repo_path_yields_note_not_crash(self):
        with tempfile.TemporaryDirectory() as td:
            not_repo = Path(td) / "not-a-repo"
            not_repo.mkdir()
            ctx = _base_ctx(repos=[not_repo])
            report = js.collect_git(ctx)
            self.assertTrue(any("not a git repo" in n for n in report["notes"]))
            self.assertEqual(report["extra"]["repos"], [])

    def test_no_repos_configured_note(self):
        ctx = _base_ctx(repos=[])
        report = js.collect_git(ctx)
        self.assertTrue(any("no repos configured" in n for n in report["notes"]))

    def test_subject_with_pipe_and_unicode_survives_the_separator_format(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repoC"
            repo.mkdir()
            _mkrepo(repo)
            subject = "fix: pipe | in subject and ünïcödé \U0001F389"
            _stage(repo, "tracked.txt", "base\n")
            _commit(repo, subject, "2026-06-30T09:00:00+00:00")
            ctx = _base_ctx(repos=[repo])
            report = js.collect_git(ctx)
            entry = report["extra"]["repos"][0]
            self.assertEqual(entry["commits"][0]["subject"], subject)


# ---- 7. deferred stubs ----------------------------------------------------------------------


class DeferredStubTests(unittest.TestCase):
    def test_cursor_stub_is_deferred_with_pinned_note(self):
        report = js.collect_cursor(_base_ctx())
        self.assertTrue(report["deferred"])
        self.assertFalse(report["available"])
        self.assertEqual(
            report["notes"],
            ["Deferred: Cursor usage lives in state.vscdb (SQLite, undocumented schema); "
             "v1 is JSONL-only — see docs/DAILY-JOURNAL.md."],
        )

    def test_vscode_stub_is_deferred_with_pinned_note(self):
        report = js.collect_vscode(_base_ctx())
        self.assertTrue(report["deferred"])
        self.assertFalse(report["available"])
        self.assertEqual(
            report["notes"],
            ["Deferred: VS Code Copilot chat usage lives in state.vscdb (SQLite, "
             "undocumented schema); v1 is JSONL-only — see docs/DAILY-JOURNAL.md."],
        )


# ---- 8. engine ------------------------------------------------------------------------------


class EngineTests(unittest.TestCase):
    def test_run_adapters_returns_all_six_sources_in_registry_order(self):
        ctx = _base_ctx()
        reports = js.run_adapters(ctx)
        expected_order = ["claude_code", "copilot_cli", "codex_cli", "git", "cursor", "vscode"]
        self.assertEqual(list(reports), expected_order)
        self.assertEqual([n for n, _ in js.ADAPTERS], expected_order)
        for name, rep in reports.items():
            self.assertEqual(frozenset(rep), REPORT_KEYS)

    def test_crashing_source_is_isolated_others_stay_intact(self):
        ctx = _base_ctx(claude_projects=123)  # provokes an AttributeError inside collect_claude
        reports = js.run_adapters(ctx)
        self.assertTrue(reports["claude_code"]["errors"])
        self.assertIn("adapter crashed", reports["claude_code"]["errors"][0])
        for name in ("copilot_cli", "codex_cli", "git", "cursor", "vscode"):
            self.assertEqual(frozenset(reports[name]), REPORT_KEYS)
            self.assertEqual(reports[name]["errors"], [])


# ---- 9. READ-ONLY byte-snapshot proof over a combined fixture tree --------------------------


class ReadOnlyProofTests(unittest.TestCase):
    def test_combined_fixture_tree_is_byte_identical_after_run_adapters(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            # Claude Code fixture.
            claude_root = root / "claude" / "projects"
            proj = claude_root / "-fake-projA"
            proj.mkdir(parents=True)
            (proj / "sess-1.jsonl").write_text(
                _crec("fake-big", "2026-06-30T10:00:00Z", "rp1", cwd="/work/projA") + "\n"
            )

            # Copilot fixture, incl. a junk session.db that must never be opened.
            co_home = root / "copilot"
            co_sess = co_home / "session-state" / "sess-co-1"
            co_sess.mkdir(parents=True)
            (co_sess / "workspace.yaml").write_text(
                "id: sess-co-1\nname: proj-co\ncwd: /work/proj-co\n"
            )
            (co_sess / "events.jsonl").write_text("\n".join([
                _ev("session.start", "2026-06-30T09:00:00Z", selectedModel="fake-co"),
                _ev("assistant.message", "2026-06-30T09:01:00Z", model="fake-co",
                    outputTokens=40, apiCallId="rp2"),
                _ev("session.shutdown", "2026-06-30T09:02:00Z", totalNanoAiu=100000000,
                    totalPremiumRequests=1, currentModel="fake-co",
                    tokenDetails=_td(400, 0, 0, 40)),
            ]) + "\n")
            (co_sess / "session.db").write_bytes(b"\x00JUNK-SESSION-DB\x01")

            # Codex fixture, incl. the sqlite subdir that must never be opened.
            codex_home = root / "codex"
            (codex_home / "sqlite").mkdir(parents=True)
            (codex_home / "sqlite" / "codex-dev.db").write_bytes(b"\x00JUNK-CODEX-DB\x01")
            (codex_home / "session_index.jsonl").write_text(
                json.dumps({"id": "rp3", "created_at": "2026-06-30T09:30:00Z"}) + "\n"
            )
            (codex_home / "history.jsonl").write_text("")

            ctx = _base_ctx(
                claude_projects=claude_root, copilot_home=co_home, codex_home=codex_home,
                repos=[], pricing_claude=P_CLAUDE, pricing_copilot=P_COPILOT,
            )

            def snapshot():
                files = sorted(p for p in root.rglob("*") if p.is_file())
                return [str(p) for p in files], {str(p): p.read_bytes() for p in files}

            before_paths, before_bytes = snapshot()
            reports = js.run_adapters(ctx)
            after_paths, after_bytes = snapshot()

            self.assertEqual(before_paths, after_paths)
            self.assertEqual(before_bytes, after_bytes)
            self.assertTrue(reports["claude_code"]["available"])
            self.assertTrue(reports["copilot_cli"]["available"])
            self.assertTrue(reports["codex_cli"]["available"])


if __name__ == "__main__":
    unittest.main()
