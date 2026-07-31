"""Stdlib unittest regression suite for the T1 Codex-deepening work in
bin/journal_sources.py's collect_codex (PLAN.md D2/D3/D7 of the journal-augment kit).

SAFETY CONTRACT (binds every test in this file): no test here ever reads or writes the
real ``~/.claude``, ``~/.copilot``, or ``~/.codex`` home directories, and no test here
resolves the caller's real home directory via any stdlib home-directory helper. Every Codex
fixture -- session_index/history lines and day-partitioned rollout files -- is synthesized
in-process under a fresh ``tempfile.TemporaryDirectory()`` per test, and every source root
is passed to the adapter explicitly via ``ctx`` (never inferred from this machine). The
synthetic pricing dict below (``PRICING``) uses a fake model id and round numbers; the ONE
place this file opens the real ``data/pricing.codex.json`` is the content-hygiene
end-to-end test, which derives its planted model id from that file AT RUN TIME (never a
literal). No test here invokes a real ``claude``/``copilot``/``codex`` CLI binary --
everything is driven in-process via ``js.collect_codex(ctx)`` or ``jc.main([...])``. No
test here opens any binary log-store file even read-only (a junk ``.db``-style file is
planted in one fixture purely to prove it is never touched). Day windows passed to the
adapter are always explicit, aware UTC datetimes.

bin/ is not a package; journal_sources.py and journal_collect.py are loaded via importlib
by absolute path computed from this file's own location (BIN_DIR), mirroring
tests/test_journal_sources.py and tests/test_journal_collect.py.
"""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


js = _load("journal_sources")
jc = _load("journal_collect")


# ---- synthetic pricing fixture --------------------------------------------------------------
#
# Deliberately fake id and round numbers -- one "mid" tier Codex model, proving every dollar
# figure below is derived from this dict at run time, never hardcoded.

PRICING = {
    "cached_date": "2026-01-01",
    "cache_read_multiplier": 0.1,
    "models": {
        "fake-codex-a": {
            "display": "Fake Codex A",
            "tier": "mid",
            "input_per_mtok": 2.0,
            "output_per_mtok": 10.0,
        },
    },
}

# The day window used throughout: an explicit, aware UTC datetime pair -- never local time.
DAY_START = datetime(2026, 2, 10, tzinfo=timezone.utc)
DAY_END = DAY_START + timedelta(days=1)

REPORT_KEYS = frozenset({
    "source", "available", "priced", "deferred", "sessions", "first_ts", "last_ts",
    "models", "totals", "usd", "projects", "tool_uses", "errors", "notes", "extra",
})


def _base_ctx(**overrides):
    # Deliberately mirrors the frozen tests' _base_ctx: no "pricing_codex" key by default,
    # so building ctx via this helper alone already exercises the "key absent" legacy path.
    ctx = {
        "day_start": DAY_START, "day_end": DAY_END,
        "claude_projects": None, "copilot_home": None, "codex_home": None,
        "repos": [], "pricing_claude": None, "pricing_copilot": None,
    }
    ctx.update(overrides)
    return ctx


def _dir_for_date(home, d):
    """The day-partitioned rollout directory for date ``d`` (a ``date`` object)."""
    return home / "sessions" / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"


def _rollout_line(model=None, session_id=None, total_token_usage=None, text=None):
    """One JSONL line for a synthetic Codex rollout file."""
    obj = {}
    if session_id is not None:
        obj["session_id"] = session_id
    if model is not None:
        obj["model"] = model
    if total_token_usage is not None:
        obj["total_token_usage"] = total_token_usage
    if text is not None:
        obj["text"] = text
    return json.dumps(obj)


# ---- 1. legacy path frozen (no pricing_codex key, and explicit None) -------------------------


class LegacyPathFrozenTests(unittest.TestCase):
    def test_ctx_without_pricing_codex_key_at_all(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "codex"
            home.mkdir(parents=True)
            (home / "session_index.jsonl").write_text(
                json.dumps({"id": "legacy-1", "created_at": "2026-02-10T09:00:00Z"}) + "\n"
            )
            ctx = _base_ctx(codex_home=home)
            self.assertNotIn("pricing_codex", ctx)
            report = js.collect_codex(ctx)
            self.assertFalse(report["priced"])
            self.assertIsNone(report["usd"])
            self.assertIn(js.CODEX_UNPRICED_NOTE, report["notes"])
            self.assertNotIn("codex_proxy", report["extra"])
            self.assertEqual(report["extra"]["rollouts_scanned"], 0)
            self.assertEqual(frozenset(report), REPORT_KEYS)

    def test_ctx_with_pricing_codex_explicit_none(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "codex"
            home.mkdir(parents=True)
            (home / "history.jsonl").write_text(
                json.dumps({"session_id": "legacy-2", "ts": "2026-02-10T09:00:00Z"}) + "\n"
            )
            ctx = _base_ctx(codex_home=home, pricing_codex=None)
            report = js.collect_codex(ctx)
            self.assertFalse(report["priced"])
            self.assertIsNone(report["usd"])
            self.assertIn(js.CODEX_UNPRICED_NOTE, report["notes"])
            self.assertNotIn("codex_proxy", report["extra"])
            self.assertEqual(report["extra"]["rollouts_scanned"], 0)
            self.assertEqual(frozenset(report), REPORT_KEYS)


# ---- 2. deepening without pricing --------------------------------------------------------------


class DeepeningWithoutPricingTests(unittest.TestCase):
    def test_rollout_tokens_counted_without_pricing(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "codex"
            day_dir = _dir_for_date(home, DAY_START.date())
            day_dir.mkdir(parents=True)
            (day_dir / "r1.jsonl").write_text(_rollout_line(
                model="some-model", session_id="sess-a",
                total_token_usage={
                    "input_tokens": 1000, "cached_input_tokens": 200, "output_tokens": 100,
                },
            ) + "\n")
            ctx = _base_ctx(codex_home=home, pricing_codex=None)
            report = js.collect_codex(ctx)
            self.assertEqual(report["totals"]["input"], 1000)
            self.assertEqual(report["totals"]["cache_read"], 200)
            self.assertEqual(report["totals"]["output"], 100)
            self.assertEqual(report["extra"]["rollouts_with_tokens"], 1)
            self.assertNotIn("codex_proxy", report["extra"])
            self.assertIsNone(report["models"]["some-model"]["usd"])


# ---- 3. proxy happy path ------------------------------------------------------------------------


class ProxyHappyPathTests(unittest.TestCase):
    def test_proxy_shape_matches_price_tokens_reuse(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "codex"
            day_dir = _dir_for_date(home, DAY_START.date())
            day_dir.mkdir(parents=True)
            (day_dir / "r1.jsonl").write_text(_rollout_line(
                model="fake-codex-a", session_id="sess-p",
                total_token_usage={
                    "input_tokens": 1000, "cached_input_tokens": 200, "output_tokens": 100,
                },
            ) + "\n")
            ctx = _base_ctx(codex_home=home, pricing_codex=PRICING)
            report = js.collect_codex(ctx)

            self.assertFalse(report["priced"])
            self.assertIsNone(report["usd"])

            px = report["extra"]["codex_proxy"]
            self.assertIsNone(px["billed_usd"])
            expected = js.cxu.price_tokens(
                {"input": 1000, "cache_read": 200, "output": 100}, "fake-codex-a", PRICING)
            self.assertAlmostEqual(px["api_equivalent_usd_total"], expected, places=9)
            self.assertEqual(set(px["by_model"]), {"fake-codex-a"})
            self.assertAlmostEqual(px["by_model"]["fake-codex-a"], expected, places=9)
            self.assertEqual(px["disclaimer"], js.cxu.PROXY_DISCLAIMER)
            self.assertEqual(px["pricing_cached_date"], "2026-01-01")
            self.assertFalse(px["approx_attribution"])

            b = report["models"]["fake-codex-a"]
            self.assertIsNone(b["usd"])
            self.assertIn(js.cxu.PROXY_DISCLAIMER, report["notes"])


# ---- 4. cumulative MAX honored via reuse -------------------------------------------------------


class CumulativeMaxTests(unittest.TestCase):
    def test_two_growing_total_token_usage_lines_take_max_not_sum(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "codex"
            day_dir = _dir_for_date(home, DAY_START.date())
            day_dir.mkdir(parents=True)
            lines = [
                _rollout_line(model="fake-codex-a", session_id="sess-c",
                               total_token_usage={"input_tokens": 500, "output_tokens": 50}),
                _rollout_line(model="fake-codex-a", session_id="sess-c",
                               total_token_usage={"input_tokens": 1200, "output_tokens": 120}),
            ]
            (day_dir / "r1.jsonl").write_text("\n".join(lines) + "\n")
            ctx = _base_ctx(codex_home=home, pricing_codex=None)
            report = js.collect_codex(ctx)
            # 500 + 1200 = 1700 would prove summing; the honest cumulative rule takes the MAX.
            self.assertEqual(report["totals"]["input"], 1200)
            self.assertEqual(report["totals"]["output"], 120)
            self.assertEqual(report["extra"]["rollouts_scanned"], 1)


# ---- 5. day-dir isolation -----------------------------------------------------------------------


class DayDirIsolationTests(unittest.TestCase):
    def test_other_day_rollouts_never_counted(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "codex"
            today = DAY_START.date()
            prev_day = (DAY_START - timedelta(days=1)).date()
            next_day = (DAY_START + timedelta(days=1)).date()
            today_dir = _dir_for_date(home, today)
            prev_dir = _dir_for_date(home, prev_day)
            next_dir = _dir_for_date(home, next_day)
            for d in (today_dir, prev_dir, next_dir):
                d.mkdir(parents=True)

            (today_dir / "r1.jsonl").write_text(_rollout_line(
                model="fake-codex-a", session_id="sess-today",
                total_token_usage={"input_tokens": 100, "output_tokens": 10},
            ) + "\n")
            (prev_dir / "r0.jsonl").write_text(_rollout_line(
                model="fake-codex-a", session_id="sess-prev",
                total_token_usage={"input_tokens": 999999, "output_tokens": 999999},
            ) + "\n")
            (next_dir / "r2.jsonl").write_text(_rollout_line(
                model="fake-codex-a", session_id="sess-next",
                total_token_usage={"input_tokens": 888888, "output_tokens": 888888},
            ) + "\n")

            ctx = _base_ctx(codex_home=home, pricing_codex=None)
            report = js.collect_codex(ctx)
            self.assertEqual(report["totals"]["input"], 100)
            self.assertEqual(report["totals"]["output"], 10)
            self.assertEqual(report["extra"]["rollouts_scanned"], 1)


# ---- 6. unmatched models --------------------------------------------------------------------


class UnmatchedModelTests(unittest.TestCase):
    def test_unknown_model_id_lands_in_unpriced_models_with_note(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "codex"
            day_dir = _dir_for_date(home, DAY_START.date())
            day_dir.mkdir(parents=True)
            (day_dir / "r1.jsonl").write_text(_rollout_line(
                model="totally-unknown-model", session_id="sess-u",
                total_token_usage={"input_tokens": 300, "output_tokens": 30},
            ) + "\n")
            ctx = _base_ctx(codex_home=home, pricing_codex=PRICING)
            report = js.collect_codex(ctx)
            self.assertNotIn("codex_proxy", report["extra"])
            self.assertIn("totally-unknown-model", report["extra"]["unpriced_models"])
            self.assertIn(js.CODEX_UNMATCHED_NOTE, report["notes"])
            self.assertFalse(report["priced"])
            self.assertIsNone(report["usd"])


# ---- 7. no tokens, pricing present -----------------------------------------------------------


class NoTokensPricingPresentTests(unittest.TestCase):
    def test_index_only_fixture_yields_cxu_unpriced_note(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "codex"
            home.mkdir(parents=True)
            (home / "session_index.jsonl").write_text(
                json.dumps({"id": "idx-only", "created_at": "2026-02-10T09:00:00Z"}) + "\n"
            )
            ctx = _base_ctx(codex_home=home, pricing_codex=PRICING)
            report = js.collect_codex(ctx)
            self.assertIn(js.cxu.UNPRICED_NOTE, report["notes"])
            self.assertNotIn("codex_proxy", report["extra"])


# ---- 8. READ-ONLY byte-snapshot proof ----------------------------------------------------------


class ReadOnlyProofTests(unittest.TestCase):
    def test_fixture_tree_byte_identical_after_collect_codex_with_rollouts_and_pricing(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "codex"
            day_dir = _dir_for_date(home, DAY_START.date())
            day_dir.mkdir(parents=True)
            (home / "session_index.jsonl").write_text(
                json.dumps({"id": "ro-idx", "created_at": "2026-02-10T09:00:00Z"}) + "\n"
            )
            (day_dir / "r1.jsonl").write_text(_rollout_line(
                model="fake-codex-a", session_id="sess-ro",
                total_token_usage={"input_tokens": 400, "output_tokens": 40},
            ) + "\n")
            # A junk binary store file that must never be opened by the adapter.
            junk_dir = home / "junk_store"
            junk_dir.mkdir(parents=True)
            (junk_dir / "codex-dev.db").write_bytes(b"\x00NEVER-OPEN\x01")

            def snapshot():
                files = sorted(p for p in home.rglob("*") if p.is_file())
                return [str(p) for p in files], {str(p): p.read_bytes() for p in files}

            before_paths, before_bytes = snapshot()
            ctx = _base_ctx(codex_home=home, pricing_codex=PRICING)
            report = js.collect_codex(ctx)
            after_paths, after_bytes = snapshot()

            self.assertEqual(before_paths, after_paths)
            self.assertEqual(before_bytes, after_bytes)
            self.assertTrue(report["available"])
            self.assertIn("codex_proxy", report["extra"])


# ---- 9. content hygiene: marker never reaches the digest --------------------------------------


class ContentHygieneTests(unittest.TestCase):
    def test_marker_in_rollout_message_like_field_never_reaches_digest(self):
        marker = "MARKER-NEVER-IN-DIGEST"
        real_pricing = json.loads(
            (REPO_ROOT / "data" / "pricing.codex.json").read_text()
        )
        real_model_id = next(iter(real_pricing["models"]))  # computed at run time, never a literal

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            codex_home = base / "codex"
            day_dir = _dir_for_date(codex_home, DAY_START.date())
            day_dir.mkdir(parents=True)
            (day_dir / "r1.jsonl").write_text(_rollout_line(
                model=real_model_id, session_id="sess-hygiene",
                total_token_usage={"input_tokens": 1000, "output_tokens": 100},
                text=f"assistant prose containing {marker} inline",
            ) + "\n")

            journal_dir = base / "journal"

            argv = [
                "--date", "2026-02-10", "--utc",
                "--claude-projects", str(base / "claude" / "projects"),
                "--copilot-home", str(base / "copilot"),
                "--codex-home", str(codex_home),
                "--kits-dir", str(base / "kits"),
                "--journal-dir", str(journal_dir),
                "--print",
            ]
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = jc.main(argv)
            out = buf.getvalue()
            self.assertEqual(rc, 0)
            self.assertNotIn(marker, out)

            digest_path = journal_dir / "2026-02-10" / "digest.json"
            digest_text = digest_path.read_text()
            self.assertNotIn(marker, digest_text)

            digest = json.loads(digest_text)
            codex_report = digest["sources"]["codex_cli"]
            self.assertIn("codex_proxy", codex_report["extra"])
            self.assertFalse(codex_report["priced"])
            self.assertIsNone(codex_report["usd"])
            proxy_total = codex_report["extra"]["codex_proxy"]["api_equivalent_usd_total"]
            self.assertGreater(proxy_total, 0)

            # The labeled proxy never enters the priced total, and codex_cli still counts as
            # an unpriced source -- no claude/copilot activity here, so usd_priced is exactly
            # 0.0 while the (much larger, or at least nonzero) proxy total lives only in extra.
            self.assertEqual(digest["totals"]["usd_priced"], 0.0)
            self.assertIn("codex_cli", digest["totals"]["unpriced_sources"])


if __name__ == "__main__":
    unittest.main()
