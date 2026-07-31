"""Stdlib unittest regression suite for bin/cost_report.py.

bin/ is not a package; cost_report.py is loaded via importlib by absolute path
computed from this file's own location, per PLAN.md D2.
"""

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cr = _load("cost_report")


class MatchModelTests(unittest.TestCase):
    def setUp(self):
        self.pricing = cr.load_pricing()

    def test_known_keys_map_to_themselves(self):
        for key in self.pricing["models"]:
            with self.subTest(key=key):
                self.assertEqual(cr.match_model(key, self.pricing), key)

    def test_suffix_and_date_variants(self):
        cases = {
            "claude-fable-5[1m]": "claude-fable-5",
            "claude-sonnet-5-20260203": "claude-sonnet-5",
            "claude-opus-4-7-20250601": "claude-opus-4-7",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(cr.match_model(raw, self.pricing), expected)

    def test_unknowns_return_none(self):
        bad = [
            None,
            "",
            "<synthetic>",
            "claude-sonnet-50",
            "claude-sonnet-5x-beta",
            "us.anthropic.claude-opus-4-8-v1:0",
        ]
        for b in bad:
            with self.subTest(bad=b):
                self.assertIsNone(cr.match_model(b, self.pricing))


class RatesForTests(unittest.TestCase):
    def setUp(self):
        self.pricing = cr.load_pricing()

    def test_intro_pricing_before_and_on_boundary(self):
        for day in ("2026-07-15", "2026-08-31"):
            when = datetime.fromisoformat(f"{day}T00:00:00+00:00")
            with self.subTest(day=day):
                self.assertEqual(
                    cr.rates_for("claude-sonnet-5", when, self.pricing), (2.0, 10.0)
                )

    def test_base_pricing_after_intro_window(self):
        when = datetime.fromisoformat("2026-09-01T00:00:00+00:00")
        self.assertEqual(cr.rates_for("claude-sonnet-5", when, self.pricing), (3.0, 15.0))

    def test_when_none_uses_base_rates(self):
        self.assertEqual(cr.rates_for("claude-sonnet-5", None, self.pricing), (3.0, 15.0))

    def test_fable_has_no_intro_pricing(self):
        when = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
        self.assertEqual(cr.rates_for("claude-fable-5", when, self.pricing), (10.0, 50.0))
        self.assertEqual(cr.rates_for("claude-fable-5", None, self.pricing), (10.0, 50.0))


class PriceTests(unittest.TestCase):
    def test_fable_price_with_cache_multipliers(self):
        pricing = cr.load_pricing()
        u = {
            "input": 1_000_000,
            "output": 100_000,
            "cache_read": 1_000_000,
            "cache_write": 100_000,
        }
        cost = cr.price("claude-fable-5", u, None, pricing)
        self.assertAlmostEqual(cost, 17.25)


class ParseTimestampTests(unittest.TestCase):
    def test_z_suffix_is_aware(self):
        ts = cr.parse_timestamp("2026-06-01T12:00:00Z")
        self.assertIsNotNone(ts.tzinfo)

    def test_explicit_offset_is_aware(self):
        ts = cr.parse_timestamp("2026-06-01T12:00:00+00:00")
        self.assertIsNotNone(ts.tzinfo)

    def test_naive_is_coerced_to_utc(self):
        ts = cr.parse_timestamp("2026-06-01T12:00:00")
        self.assertIsNotNone(ts.tzinfo)
        self.assertEqual(ts.tzinfo, timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        # Regression guard for T1: must not raise offset-naive/aware TypeError.
        _ = ts < cutoff

        # A naive timestamp near "now" must compare as recent (not filtered out),
        # deterministic regardless of when this test runs.
        recent_naive = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(tzinfo=None)
        recent_ts = cr.parse_timestamp(recent_naive.isoformat())
        self.assertGreaterEqual(recent_ts, cutoff)

    def test_garbage_and_none_and_empty(self):
        self.assertIsNone(cr.parse_timestamp("garbage"))
        self.assertIsNone(cr.parse_timestamp(None))
        self.assertIsNone(cr.parse_timestamp(""))


class ExtractRecordTests(unittest.TestCase):
    def test_nested_message_with_two_tool_uses(self):
        obj = {
            "message": {
                "id": "m1",
                "model": "claude-sonnet-5",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
                "content": [
                    {"type": "tool_use", "name": "Bash"},
                    {"type": "text", "text": "hi"},
                    {"type": "tool_use", "name": "Read"},
                ],
            }
        }
        rec = cr.extract_record(obj)
        self.assertIsNotNone(rec)
        model, u, msg_id, tool_uses = rec
        self.assertEqual(model, "claude-sonnet-5")
        self.assertEqual(msg_id, "m1")
        self.assertEqual(tool_uses, 2)
        self.assertEqual(u["input"], 10)
        self.assertEqual(u["output"], 5)

    def test_top_level_fallback_form(self):
        obj = {"usage": {"input_tokens": 3, "output_tokens": 1}, "model": "claude-haiku-4-5"}
        rec = cr.extract_record(obj)
        self.assertIsNotNone(rec)
        model, u, msg_id, tool_uses = rec
        self.assertEqual(model, "claude-haiku-4-5")
        self.assertEqual(tool_uses, 0)
        self.assertEqual(u["input"], 3)
        self.assertEqual(u["output"], 1)

    def test_all_zero_usage_returns_none(self):
        obj = {
            "message": {
                "id": "m2",
                "model": "claude-sonnet-5",
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
        }
        self.assertIsNone(cr.extract_record(obj))

    def test_missing_model_returns_none(self):
        obj = {"message": {"id": "m3", "usage": {"input_tokens": 5, "output_tokens": 1}}}
        self.assertIsNone(cr.extract_record(obj))

    def test_null_usage_fields_coerce_to_zero(self):
        obj = {
            "message": {
                "id": "m4",
                "model": "claude-sonnet-5",
                "usage": {
                    "input_tokens": 5,
                    "output_tokens": None,
                    "cache_read_input_tokens": None,
                    "cache_creation_input_tokens": None,
                },
            }
        }
        rec = cr.extract_record(obj)
        self.assertIsNotNone(rec)
        _, u, _, _ = rec
        self.assertEqual(u["output"], 0)
        self.assertEqual(u["cache_read"], 0)
        self.assertEqual(u["cache_write"], 0)


class MainEndToEndTests(unittest.TestCase):
    def test_main_report_dedupes_ages_and_prices_correctly(self):
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old = (now - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        naive = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")  # no Z / offset

        def line(ts, model, mid):
            return json.dumps(
                {
                    "timestamp": ts,
                    "sessionId": "s1",
                    "message": {
                        "id": mid,
                        "model": model,
                        "usage": {"input_tokens": 100, "output_tokens": 10},
                    },
                }
            )

        lines = [
            line(recent, "claude-fable-5", "m1"),
            line(recent, "claude-fable-5", "m1"),  # exact duplicate -> counted once
            line(recent, "claude-sonnet-4-6", "m2"),  # historical model must price
            line(recent, "claude-sonnet-50", "m3"),  # unknown -> Unpriced models
            line(recent, "<synthetic>", "m4"),  # synthetic -> must not appear anywhere
            line(old, "claude-opus-4-7", "m5"),  # older than --days window -> excluded
            line(naive, "claude-haiku-4-5", "m6"),  # naive timestamp -> included, no crash
        ]

        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            (proj / "s1.jsonl").write_text("\n".join(lines) + "\n")

            orig_dir = cr.PROJECTS_DIR
            orig_argv = sys.argv
            try:
                cr.PROJECTS_DIR = Path(td)
                sys.argv = ["cost_report.py", "--days", "30"]
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cr.main()
                out = buf.getvalue()
            finally:
                cr.PROJECTS_DIR = orig_dir
                sys.argv = orig_argv

        self.assertIn("Fable 5", out)
        self.assertIn("Sonnet 4.6", out)
        self.assertIn("claude-sonnet-50", out)
        self.assertNotIn("<synthetic>", out)
        self.assertIn("| Fable 5 | 1 |", out)
        # Extra regression coverage beyond the brief's minimum assertions:
        self.assertIn("Haiku 4.5", out)  # naive-timestamp record was included
        self.assertNotIn("| Opus 4.7 |", out)  # out-of-window record was excluded


class BuildReportPayloadTests(unittest.TestCase):
    """T1: build_report_payload is the pure builder behind both the markdown
    report and --json. It must reproduce the same numbers the markdown path
    prints, never raise on an absent dir, and stay JSON-serializable."""

    def _write_fixture(self, td):
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old = (now - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        naive = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")

        def line(ts, model, mid):
            return json.dumps(
                {
                    "timestamp": ts,
                    "sessionId": "s1",
                    "message": {
                        "id": mid,
                        "model": model,
                        "usage": {"input_tokens": 100, "output_tokens": 10},
                    },
                }
            )

        lines = [
            line(recent, "claude-fable-5", "m1"),
            line(recent, "claude-fable-5", "m1"),  # exact duplicate -> counted once
            line(recent, "claude-sonnet-4-6", "m2"),
            line(recent, "claude-sonnet-50", "m3"),  # unknown -> unpriced
            line(recent, "<synthetic>", "m4"),  # synthetic -> never surfaced
            line(old, "claude-opus-4-7", "m5"),  # out of window
            line(naive, "claude-haiku-4-5", "m6"),  # naive timestamp, included
        ]
        proj = Path(td) / "proj"
        proj.mkdir()
        (proj / "s1.jsonl").write_text("\n".join(lines) + "\n")
        return Path(td)

    def test_happy_path_required_keys_and_totals_match_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            projects_dir = self._write_fixture(td)
            payload = cr.build_report_payload(projects_dir, days=30, top=10, mode=None)

            # Payload must be JSON-serializable and carry every pinned key.
            json.dumps(payload)
            for key in (
                "schema_version", "found", "days", "top", "mode", "projects_dir",
                "pricing_cached_date", "totals", "by_model", "sessions",
                "downgrade_candidates", "unknown_models", "parse_errors", "labels",
            ):
                self.assertIn(key, payload)

            self.assertEqual(payload["schema_version"], 1)
            self.assertTrue(payload["found"])
            self.assertIn("usd", payload["totals"])
            self.assertIn("sessions", payload["totals"])
            self.assertIn("tokens", payload["totals"])
            self.assertIsInstance(payload["parse_errors"], int)
            self.assertIn(f"billing mode: {payload['mode']}", payload["labels"])
            self.assertIn("unpriced models present", payload["labels"])

            models_seen = {b["model"] for b in payload["by_model"]}
            self.assertIn("claude-fable-5", models_seen)
            self.assertIn("claude-sonnet-4-6", models_seen)
            self.assertIn("claude-haiku-4-5", models_seen)
            self.assertNotIn("claude-opus-4-7", models_seen)  # out of window

            fable_bucket = next(b for b in payload["by_model"] if b["model"] == "claude-fable-5")
            self.assertEqual(fable_bucket["messages"], 1)  # deduped

            unpriced = {u["model"] for u in payload["unknown_models"]}
            self.assertIn("claude-sonnet-50", unpriced)
            self.assertNotIn("<synthetic>", unpriced)

            self.assertGreater(payload["totals"]["usd"], 0)

            # Now render the markdown path over the same fixture and confirm the
            # dollar figures match exactly (same numbers, computed once).
            orig_dir = cr.PROJECTS_DIR
            orig_argv = sys.argv
            try:
                cr.PROJECTS_DIR = projects_dir
                sys.argv = ["cost_report.py", "--days", "30"]
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cr.main()
                md = buf.getvalue()
            finally:
                cr.PROJECTS_DIR = orig_dir
                sys.argv = orig_argv

            self.assertIn(f"${payload['totals']['usd']:,.2f}", md)
            for b in payload["by_model"]:
                self.assertIn(f"${b['usd']:,.2f}", md)

    def test_absent_dir_returns_found_false_never_raises(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "nope" / "deeper"
            payload = cr.build_report_payload(missing, days=30, top=10, mode=None)

        self.assertEqual(payload["schema_version"], 1)
        self.assertFalse(payload["found"])
        self.assertEqual(payload["totals"], {"usd": 0.0, "sessions": 0, "tokens": 0})
        self.assertEqual(payload["by_model"], [])
        self.assertEqual(payload["sessions"], [])
        self.assertFalse(payload["dir_present"])
        self.assertIn(f"transcript directory absent: {missing}", payload["labels"])
        self.assertNotIn(f"no transcripts in window: {missing}", payload["labels"])
        json.dumps(payload)  # must stay JSON-serializable

    def test_builder_never_exits_or_prints(self):
        # No sys.exit, no stdout noise — a pure function over an absent dir.
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "absent"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                payload = cr.build_report_payload(missing)
            self.assertEqual(buf.getvalue(), "")
        self.assertFalse(payload["found"])


class MainJsonFlagTests(unittest.TestCase):
    """--json prints the payload as JSON via main(); absent dir exits 0 with a
    found:false payload instead of the sys.exit markdown behavior (new flag,
    new honest shape)."""

    def test_json_flag_over_present_dir(self):
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            now = datetime.now(timezone.utc)
            recent = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            line = json.dumps({
                "timestamp": recent,
                "sessionId": "s1",
                "message": {
                    "id": "m1",
                    "model": "claude-fable-5",
                    "usage": {"input_tokens": 100, "output_tokens": 10},
                },
            })
            (proj / "s1.jsonl").write_text(line + "\n")

            orig_argv = sys.argv
            try:
                sys.argv = ["cost_report.py", "--json", "--projects-dir", str(Path(td))]
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cr.main()
                out = buf.getvalue()
            finally:
                sys.argv = orig_argv

            payload = json.loads(out)
            self.assertTrue(payload["found"])
            self.assertEqual(payload["schema_version"], 1)

    def test_json_flag_over_absent_dir_exits_zero_with_found_false(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "nope"
            orig_argv = sys.argv
            try:
                sys.argv = ["cost_report.py", "--json", "--projects-dir", str(missing)]
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    # main() must return normally (no SystemExit) with --json.
                    cr.main()
                out = buf.getvalue()
            finally:
                sys.argv = orig_argv

            payload = json.loads(out)
            self.assertFalse(payload["found"])
            self.assertIn(f"transcript directory absent: {missing}", payload["labels"])

    def test_absent_dir_without_json_still_exits_as_before(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "nope"
            orig_dir = cr.PROJECTS_DIR
            orig_argv = sys.argv
            try:
                cr.PROJECTS_DIR = missing
                sys.argv = ["cost_report.py"]
                with self.assertRaises(SystemExit) as ctx:
                    cr.main()
                self.assertIn(f"No transcript directory at {missing}", str(ctx.exception))
            finally:
                cr.PROJECTS_DIR = orig_dir
                sys.argv = orig_argv


class FoundMeansEvidenceTests(unittest.TestCase):
    """T4b/F2+F3: ``found`` means EVIDENCE PRESENT (at least one record priced inside the
    window), not "the directory exists". A present-but-empty dir, or one whose every record
    falls outside ``--days``, previously reported ``found: True`` with fabricated zeros —
    a store would have recorded "we measured $0.00" where the truth was "we measured
    nothing". The two absence causes carry two DISTINCT labels, and ``dir_present`` keeps
    the directory fact separate so the markdown CLI's exit gate (and therefore its bytes)
    is unchanged."""

    def _md(self, projects_dir, argv=("cost_report.py",)):
        orig_dir, orig_argv = cr.PROJECTS_DIR, sys.argv
        try:
            cr.PROJECTS_DIR = projects_dir
            sys.argv = list(argv)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cr.main()
            return buf.getvalue()
        finally:
            cr.PROJECTS_DIR = orig_dir
            sys.argv = orig_argv

    def test_present_but_empty_dir_is_not_found(self):
        with tempfile.TemporaryDirectory() as td:
            empty = Path(td) / "projects"
            empty.mkdir()
            payload = cr.build_report_payload(empty, days=30, top=10, mode=None)

            self.assertFalse(payload["found"])
            self.assertTrue(payload["dir_present"])
            self.assertIn(f"no transcripts in window: {empty}", payload["labels"])
            # The MISSING-dir label is a different truth and must not appear here.
            self.assertNotIn(f"transcript directory absent: {empty}", payload["labels"])
            self.assertEqual(payload["totals"]["usd"], 0.0)
            self.assertEqual(payload["by_model"], [])
            json.dumps(payload)

    def test_all_records_outside_days_window_is_not_found(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "projects"
            proj = root / "p"
            proj.mkdir(parents=True)
            pricing = cr.load_pricing()
            model_id = next(iter(pricing["models"]))  # run-time id, never spelled here
            old = (datetime.now(timezone.utc) - timedelta(days=400)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            (proj / "s.jsonl").write_text(json.dumps({
                "timestamp": old, "sessionId": "s1",
                "message": {"id": "m1", "model": model_id,
                            "usage": {"input_tokens": 5000, "output_tokens": 400}},
            }) + "\n")

            narrow = cr.build_report_payload(root, days=30, top=10, mode=None)
            self.assertFalse(narrow["found"])
            self.assertTrue(narrow["dir_present"])
            self.assertIn(f"no transcripts in window: {root}", narrow["labels"])
            self.assertEqual(narrow["totals"]["usd"], 0.0)

            # Widen the window over the SAME fixture: the record reappears and so does
            # found — proving the flag tracks evidence, not the calendar or the dir.
            wide = cr.build_report_payload(root, days=500, top=10, mode=None)
            self.assertTrue(wide["found"])
            self.assertGreater(wide["totals"]["usd"], 0.0)
            self.assertNotIn(f"no transcripts in window: {root}", wide["labels"])

    def test_markdown_for_empty_and_out_of_window_dirs_is_unchanged(self):
        """The honesty change is payload-only: both cases still render the full zero-row
        markdown report (never the missing-dir exit), exactly as before."""
        with tempfile.TemporaryDirectory() as td:
            empty = Path(td) / "empty"
            empty.mkdir()
            outside = Path(td) / "outside"
            proj = outside / "p"
            proj.mkdir(parents=True)
            pricing = cr.load_pricing()
            model_id = next(iter(pricing["models"]))
            old = (datetime.now(timezone.utc) - timedelta(days=400)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            (proj / "s.jsonl").write_text(json.dumps({
                "timestamp": old, "sessionId": "s1",
                "message": {"id": "m1", "model": model_id,
                            "usage": {"input_tokens": 5000, "output_tokens": 400}},
            }) + "\n")

            for label, d in (("empty", empty), ("out-of-window", outside)):
                with self.subTest(case=label):
                    md = self._md(d)
                    # Full report body, zeros and all — not the sys.exit path.
                    self.assertIn("# Claude Code usage — last 30 days", md)
                    # Mode word comes from pricing.json's billing_mode at run time.
                    self.assertIn("$0.00** across 0 sessions.", md)
                    self.assertIn("## By model", md)
                    self.assertIn("| Model | Messages | Input | Output "
                                  "| Cache read | Cache write | Cost |", md)
                    self.assertIn("## Top 10 sessions by cost", md)
                    self.assertIn("None found in this window.", md)
                    self.assertIn("costs are API-list estimates, not bills.", md)
                    self.assertNotIn("No transcript directory at", md)

            # The two markdown reports differ only by their (absent) data — byte-identical
            # here, which is what "a present dir always renders" means.
            self.assertEqual(self._md(empty), self._md(outside))

    def test_missing_dir_still_exits_and_empty_dir_still_renders(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "gone"
            with self.assertRaises(SystemExit) as ctx:
                self._md(missing)
            self.assertIn(f"No transcript directory at {missing}", str(ctx.exception))

            empty = Path(td) / "here"
            empty.mkdir()
            self.assertIn("# Claude Code usage", self._md(empty))  # no SystemExit

    def test_est_caveat_label_present_on_every_branch(self):
        """F3: the markdown footer prints "costs are API-list estimates, not bills." but
        the payload never carried it — the caveat would have been dropped on the way into
        the store. GUARDRAILS requires est. caveats to survive the round trip."""
        caveat = "API-list estimates, not bills (est.)"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "projects"
            proj = root / "p"
            proj.mkdir(parents=True)
            pricing = cr.load_pricing()
            model_id = next(iter(pricing["models"]))
            recent = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            (proj / "s.jsonl").write_text(json.dumps({
                "timestamp": recent, "sessionId": "s1",
                "message": {"id": "m1", "model": model_id,
                            "usage": {"input_tokens": 5000, "output_tokens": 400}},
            }) + "\n")

            found_payload = cr.build_report_payload(root, days=30, top=10, mode=None)
            self.assertTrue(found_payload["found"])
            self.assertIn(caveat, found_payload["labels"])

            empty = Path(td) / "empty"
            empty.mkdir()
            self.assertIn(caveat,
                          cr.build_report_payload(empty, days=30)["labels"])
            self.assertIn(caveat,
                          cr.build_report_payload(Path(td) / "gone", days=30)["labels"])

            # And the markdown the payload feeds still prints the same sentence.
            md = self._md(root)
            self.assertIn("costs are API-list estimates, not bills.", md)


class DefaultProjectsDirTests(unittest.TestCase):
    """The default transcript dir honors CLAUDE_CONFIG_DIR, else falls back to
    ~/.claude/projects. Real home never read — Path.home is patched to a fake path."""

    def test_honors_claude_config_dir_when_set(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "/cfg/home"}, clear=False):
            self.assertEqual(cr._default_projects_dir(), Path("/cfg/home") / "projects")

    def test_falls_back_to_claude_home_when_unset(self):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(cr.Path, "home", return_value=Path("/fake/home")):
            self.assertEqual(cr._default_projects_dir(), Path("/fake/home/.claude/projects"))


if __name__ == "__main__":
    unittest.main()
