"""Stdlib unittest regression suite for bin/copilot_usage.py (PLAN.md D1-D7).

SAFETY CONTRACT (binds every test in this file): no test here ever invokes the real
``copilot`` CLI, reads or writes the real ~/.copilot, or resolves the caller's real home
directory via the stdlib ``Path.home`` helper. Every session
fixture lives under a fresh ``tempfile.TemporaryDirectory()`` home built by this file;
``events.jsonl``/``workspace.yaml`` contents are synthesized in-process; and pricing is a
synthetic ``FIXTURE`` dict (fake model ids, round numbers, a fake
``billing_unit.usd_per_credit`` of 0.5) patched over ``load_pricing`` via
``mock.patch.object(cu, "load_pricing", return_value=FIXTURE)`` -- the real
``data/pricing.copilot.json`` is never opened by this file, and no ``*.db`` file is ever
opened either (one test proves this by byte-snapshotting a fixture home around a junk
``session.db``).

bin/ is not a package; copilot_usage.py is loaded via importlib by absolute path computed
from this file's own location (BIN_DIR), mirroring tests/test_copilot_pricing.py.
"""

import contextlib
import importlib.util
import io
import json
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


cu = _load("copilot_usage")


# ---- synthetic fixture --------------------------------------------------------------------
#
# Deliberately fake ids and round numbers, in the exact file order the downgrade-target
# rule depends on: fake-front (frontier) / fake-strong (strong, WITH cache_write_per_mtok)
# / fake-mid (mid -- the expected downgrade target, being the FIRST mid-tier row) /
# fake-mid-b (mid, must NEVER be picked) / fake-cheap (cheap, NO cache_write_per_mtok).
# billing_unit.usd_per_credit = 0.5 (nowhere near the real rate) proves USD->AIC is derived
# from the pricing dict at run time, never hardcoded.

FIXTURE = {
    "cached_date": "2020-06-01",
    "billing_unit": {
        "name": "FIC",
        "usd_per_credit": 0.5,
        "note": "Fixture unit -- deliberately not the real rate.",
    },
    "models": {
        "fake-front": {
            "display": "Fake Front",
            "vendor": "fake-vendor",
            "tier": "frontier",
            "input_per_mtok": 20.0,
            "cached_input_per_mtok": 2.0,
            "output_per_mtok": 100.0,
        },
        "fake-strong": {
            "display": "Fake Strong",
            "vendor": "fake-vendor",
            "tier": "strong",
            "input_per_mtok": 5.0,
            "cached_input_per_mtok": 0.5,
            "cache_write_per_mtok": 6.0,
            "output_per_mtok": 25.0,
        },
        "fake-mid": {
            "display": "Fake Mid One",
            "vendor": "fake-vendor",
            "tier": "mid",
            "input_per_mtok": 2.0,
            "cached_input_per_mtok": 0.2,
            "output_per_mtok": 10.0,
        },
        "fake-mid-b": {
            "display": "Fake Mid Two",
            "vendor": "fake-vendor",
            "tier": "mid",
            "input_per_mtok": 2.0,
            "cached_input_per_mtok": 0.2,
            "output_per_mtok": 10.0,
        },
        "fake-cheap": {
            "display": "Fake Cheap",
            "vendor": "fake-vendor",
            "tier": "cheap",
            "input_per_mtok": 1.0,
            "cached_input_per_mtok": 0.1,
            "output_per_mtok": 2.0,
        },
    },
}


def _ev(etype, ts, **data):
    """Build one events.jsonl line: {"type": ..., "timestamp": ..., "data": {...}}."""
    return json.dumps({"type": etype, "timestamp": ts, "data": data})


def _td(input_count, cache_read, cache_write, output_count):
    """Build a session.shutdown tokenDetails dict."""
    return {
        "input": {"tokenCount": input_count},
        "cache_read": {"tokenCount": cache_read},
        "cache_write": {"tokenCount": cache_write},
        "output": {"tokenCount": output_count},
    }


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- 1. parse_events: single-model session -------------------------------------------------


class ParseEventsSingleModelTests(unittest.TestCase):
    def test_single_model_session_fields(self):
        lines = [
            _ev("session.start", "2026-06-30T10:00:00Z", selectedModel="fake-strong"),
            _ev(
                "assistant.message",
                "2026-06-30T10:01:00Z",
                model="fake-strong",
                outputTokens=200,
                apiCallId="a1",
            ),
            _ev(
                "assistant.message",
                "2026-06-30T10:02:00Z",
                model="fake-strong",
                outputTokens=300,
                apiCallId="a2",
            ),
            _ev(
                "session.shutdown",
                "2026-06-30T10:03:00Z",
                totalNanoAiu=2500000000,
                totalPremiumRequests=1,
                currentModel="fake-strong",
                tokenDetails=_td(9000, 4500, 500, 500),
            ),
        ]
        parsed = cu.parse_events(lines)
        self.assertEqual(parsed["models"], ["fake-strong"])
        self.assertEqual(
            parsed["tokens"],
            {"input": 9000, "cache_read": 4500, "cache_write": 500, "output": 500},
        )
        self.assertEqual(parsed["nano_aiu"], 2500000000)
        self.assertEqual(parsed["premium_requests"], 1)
        self.assertEqual(parsed["shutdowns"], 1)
        self.assertTrue(parsed["has_token_details"])
        self.assertEqual(
            parsed["per_turn_output"]["fake-strong"],
            {"turns": 2, "output_tokens": 500},
        )


# ---- 2. parse_events: multi-model session, last_model ---------------------------------------


class ParseEventsMultiModelTests(unittest.TestCase):
    def test_multi_model_session_last_model(self):
        lines = [
            _ev("session.start", "2026-06-30T11:00:00Z", selectedModel="fake-mid"),
            _ev(
                "session.model_change",
                "2026-06-30T11:01:00Z",
                previousModel="fake-mid",
                newModel="fake-front",
            ),
            _ev(
                "assistant.message",
                "2026-06-30T11:02:00Z",
                model="fake-mid",
                outputTokens=50,
                apiCallId="m1",
            ),
            _ev(
                "assistant.message",
                "2026-06-30T11:03:00Z",
                model="fake-front",
                outputTokens=60,
                apiCallId="m2",
            ),
            _ev(
                "session.shutdown",
                "2026-06-30T11:04:00Z",
                totalNanoAiu=1000000,
                totalPremiumRequests=1,
                currentModel="fake-front",
                tokenDetails=_td(10, 10, 10, 10),
            ),
        ]
        parsed = cu.parse_events(lines)
        self.assertEqual(parsed["models"], ["fake-mid", "fake-front"])
        self.assertEqual(parsed["last_model"], "fake-front")


# ---- 3. Resume + MULTIPLE shutdowns: element-wise MAX, never sum ----------------------------


class ShutdownMaxAggregationTests(unittest.TestCase):
    def test_multiple_shutdowns_aggregate_by_element_wise_max(self):
        lines = [
            _ev("session.start", "2026-06-30T12:00:00Z", selectedModel="fake-mid"),
            _ev(
                "assistant.message",
                "2026-06-30T12:01:00Z",
                model="fake-mid",
                outputTokens=100,
                apiCallId="r1",
            ),
            _ev(
                "session.shutdown",
                "2026-06-30T12:02:00Z",
                totalNanoAiu=5000000000,
                totalPremiumRequests=1,
                currentModel="fake-mid",
                tokenDetails=_td(100, 0, 0, 500),
            ),
            _ev("session.resume", "2026-06-30T13:00:00Z", selectedModel="fake-mid"),
            _ev(
                "assistant.message",
                "2026-06-30T13:01:00Z",
                model="fake-mid",
                outputTokens=50,
                apiCallId="r2",
            ),
            _ev(
                "session.shutdown",
                "2026-06-30T13:02:00Z",
                totalNanoAiu=2000000000,
                totalPremiumRequests=9,
                currentModel="fake-mid",
                tokenDetails=_td(300, 0, 0, 400),
            ),
        ]
        parsed = cu.parse_events(lines)
        # Per-field max: input max(100, 300) == 300; output max(500, 400) == 500.
        self.assertEqual(parsed["tokens"]["input"], 300)
        self.assertEqual(parsed["tokens"]["output"], 500)
        # nano_aiu's max comes from shutdown 1; premium_requests' max comes from shutdown 2 --
        # proves the aggregation is independent per field, not "last wins" or "first wins".
        self.assertEqual(parsed["nano_aiu"], 5000000000)
        self.assertEqual(parsed["premium_requests"], 9)
        self.assertEqual(parsed["shutdowns"], 2)


# ---- 4. Missing tokenDetails -> output-only fallback -----------------------------------------


class MissingTokenDetailsTests(unittest.TestCase):
    def test_no_shutdown_falls_back_to_output_only(self):
        lines = [
            _ev("session.start", "2026-06-30T14:00:00Z", selectedModel="fake-cheap"),
            _ev(
                "assistant.message",
                "2026-06-30T14:01:00Z",
                model="fake-cheap",
                outputTokens=150,
                apiCallId="x1",
            ),
            _ev(
                "assistant.message",
                "2026-06-30T14:02:00Z",
                model="fake-cheap",
                outputTokens=250,
                apiCallId="x2",
            ),
        ]
        parsed = cu.parse_events(lines)
        self.assertFalse(parsed["has_token_details"])
        eff, output_only = cu.effective_tokens(parsed)
        self.assertTrue(output_only)
        self.assertEqual(
            eff, {"input": 0, "cache_read": 0, "cache_write": 0, "output": 400}
        )


# ---- 5. Robustness: blank/garbage/array/unknown/no-outputTokens lines -----------------------


class RobustnessTests(unittest.TestCase):
    def test_blank_garbage_array_unknown_and_missing_output_tokens_never_crash(self):
        lines = [
            "",
            "   ",
            "not json at all {{{",
            "[1, 2, 3]",
            _ev("weird.unknown.event.type", "2026-06-30T15:00:00Z", foo="bar"),
            _ev(
                "assistant.message",
                "2026-06-30T15:01:00Z",
                model="fake-mid",
                apiCallId="z1",
            ),  # no outputTokens key at all
            _ev(
                "session.shutdown",
                "2026-06-30T15:02:00Z",
                totalNanoAiu=1000000000,
                totalPremiumRequests=1,
                currentModel="fake-mid",
                tokenDetails=_td(1, 1, 1, 1),
            ),
        ]
        parsed = cu.parse_events(lines)  # must not raise
        self.assertEqual(parsed["models"], ["fake-mid"])
        self.assertEqual(parsed["per_turn_output"]["fake-mid"]["turns"], 1)
        self.assertEqual(parsed["per_turn_output"]["fake-mid"]["output_tokens"], 0)
        self.assertTrue(parsed["has_token_details"])
        self.assertEqual(parsed["shutdowns"], 1)


# ---- 6. apiCallId dedupe ----------------------------------------------------------------------


class ApiCallIdDedupeTests(unittest.TestCase):
    def test_same_api_call_id_counted_once(self):
        lines = [
            _ev(
                "assistant.message",
                "2026-06-30T16:00:00Z",
                model="fake-mid",
                outputTokens=100,
                apiCallId="dup1",
            ),
            _ev(
                "assistant.message",
                "2026-06-30T16:00:01Z",
                model="fake-mid",
                outputTokens=999,
                apiCallId="dup1",
            ),
        ]
        parsed = cu.parse_events(lines)
        self.assertEqual(parsed["per_turn_output"]["fake-mid"]["turns"], 1)
        self.assertEqual(parsed["per_turn_output"]["fake-mid"]["output_tokens"], 100)


# ---- 7. price_tokens / usd_to_aic hand math ---------------------------------------------------


class PriceTokensMathTests(unittest.TestCase):
    def test_cache_write_priced_when_rate_present(self):
        # fake-strong: input=5.0, cached=0.5, cache_write=6.0, output=25.0 per MTok.
        u = {
            "input": 1_000_000,
            "cache_read": 1_000_000,
            "cache_write": 1_000_000,
            "output": 1_000_000,
        }
        usd = cu.price_tokens(u, "fake-strong", FIXTURE)
        self.assertAlmostEqual(usd, 5.0 + 0.5 + 6.0 + 25.0)

    def test_cache_write_zero_effect_when_rate_absent(self):
        # fake-cheap carries NO cache_write_per_mtok -> that term contributes 0.
        u = {
            "input": 1_000_000,
            "cache_read": 1_000_000,
            "cache_write": 1_000_000,
            "output": 1_000_000,
        }
        usd = cu.price_tokens(u, "fake-cheap", FIXTURE)
        self.assertAlmostEqual(usd, 1.0 + 0.1 + 0.0 + 2.0)

    def test_usd_to_aic_divides_by_fixture_rate(self):
        # billing_unit.usd_per_credit == 0.5 -> aic == usd / 0.5 == usd * 2.
        self.assertAlmostEqual(cu.usd_to_aic(3.1, FIXTURE), 6.2)
        self.assertAlmostEqual(cu.usd_to_aic(0.0, FIXTURE), 0.0)


# ---- 8. match_model -----------------------------------------------------------------------


class MatchModelTests(unittest.TestCase):
    def test_exact_match(self):
        self.assertEqual(cu.match_model("fake-strong", FIXTURE), "fake-strong")

    def test_suffixed_match(self):
        self.assertEqual(cu.match_model("fake-strong-20260701", FIXTURE), "fake-strong")

    def test_unknown_returns_none(self):
        self.assertIsNone(cu.match_model("totally-unmapped-id", FIXTURE))
        self.assertIsNone(cu.match_model(None, FIXTURE))
        self.assertIsNone(cu.match_model("", FIXTURE))


# ---- 9. parse_workspace ---------------------------------------------------------------------


class ParseWorkspaceTests(unittest.TestCase):
    def test_flat_lines_parsed(self):
        text = "id: s1\nname: fixture-one\ncwd: /tmp/proj-one\n"
        self.assertEqual(
            cu.parse_workspace(text),
            {"id": "s1", "name": "fixture-one", "cwd": "/tmp/proj-one"},
        )

    def test_junk_lines_ignored(self):
        text = "not a kv line\n\n: no-key-value\nid: only-this-counts\n"
        self.assertEqual(cu.parse_workspace(text), {"id": "only-this-counts"})

    def test_empty_text_yields_empty_dict(self):
        self.assertEqual(cu.parse_workspace(""), {})


# ---- 10. End-to-end main -----------------------------------------------------------------


class MainEndToEndTests(unittest.TestCase):
    def test_report_sections_downgrade_target_and_unpriced_section(self):
        now = datetime.now(timezone.utc)

        def t(offset_seconds):
            return _iso(now - timedelta(seconds=offset_seconds))

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            state = home / "session-state"

            # Session A: single-model fake-strong, small footprint -> downgrade candidate.
            a = state / "aaaaaaaa-0000-0000-0000-000000000001"
            a.mkdir(parents=True)
            (a / "workspace.yaml").write_text(
                "id: sess-a\nname: proj-alpha\ncwd: /work/proj-alpha\n"
            )
            (a / "events.jsonl").write_text(
                "\n".join(
                    [
                        _ev("session.start", t(600), selectedModel="fake-strong"),
                        _ev(
                            "assistant.message",
                            t(590),
                            model="fake-strong",
                            outputTokens=100,
                            apiCallId="a1",
                        ),
                        _ev(
                            "assistant.message",
                            t(580),
                            model="fake-strong",
                            outputTokens=100,
                            apiCallId="a2",
                        ),
                        _ev(
                            "session.shutdown",
                            t(570),
                            totalNanoAiu=1500000000,
                            totalPremiumRequests=1,
                            currentModel="fake-strong",
                            tokenDetails=_td(1000, 200, 100, 200),
                        ),
                    ]
                )
                + "\n"
            )

            # Session B: multi-model (fake-mid -> fake-front) -> approx / "≈" marker.
            # Mixed tiers (mid + frontier) also keeps it OUT of downgrade candidates,
            # which requires ALL matched models in EXPENSIVE_TIERS.
            b = state / "bbbbbbbb-0000-0000-0000-000000000002"
            b.mkdir(parents=True)
            (b / "workspace.yaml").write_text(
                "id: sess-b\nname: proj-beta\ncwd: /work/proj-beta\n"
            )
            (b / "events.jsonl").write_text(
                "\n".join(
                    [
                        _ev("session.start", t(500), selectedModel="fake-mid"),
                        _ev(
                            "session.model_change",
                            t(490),
                            previousModel="fake-mid",
                            newModel="fake-front",
                        ),
                        _ev(
                            "assistant.message",
                            t(480),
                            model="fake-mid",
                            outputTokens=50,
                            apiCallId="b1",
                        ),
                        _ev(
                            "assistant.message",
                            t(470),
                            model="fake-front",
                            outputTokens=80,
                            apiCallId="b2",
                        ),
                        _ev(
                            "session.shutdown",
                            t(460),
                            totalNanoAiu=4000000000,
                            totalPremiumRequests=2,
                            currentModel="fake-front",
                            tokenDetails=_td(2000, 500, 0, 130),
                        ),
                    ]
                )
                + "\n"
            )

            # Session C: model unknown to the fixture pricing -> Unpriced models section.
            c = state / "cccccccc-0000-0000-0000-000000000003"
            c.mkdir(parents=True)
            (c / "workspace.yaml").write_text(
                "id: sess-c\nname: proj-gamma\ncwd: /work/proj-gamma\n"
            )
            (c / "events.jsonl").write_text(
                "\n".join(
                    [
                        _ev(
                            "session.start",
                            t(400),
                            selectedModel="unmapped-experimental-model",
                        ),
                        _ev(
                            "assistant.message",
                            t(390),
                            model="unmapped-experimental-model",
                            outputTokens=75,
                            apiCallId="c1",
                        ),
                        _ev(
                            "session.shutdown",
                            t(380),
                            totalNanoAiu=500000000,
                            totalPremiumRequests=1,
                            currentModel="unmapped-experimental-model",
                            tokenDetails=_td(400, 0, 0, 75),
                        ),
                    ]
                )
                + "\n"
            )

            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cu.main(["--copilot-home", str(home), "--days", "30"])
                out = buf.getvalue()

        for heading in [
            "## Spend by model",
            "## Output tokens by model (per-turn, exact)",
            "## Top 10 sessions by estimated cost",
            "## Downgrade candidates",
            "## Copilot-reported AIU cross-check",
            "## Unpriced models (not in pricing.copilot.json)",
        ]:
            self.assertIn(heading, out)

        self.assertIn("across 3 sessions.", out)
        self.assertIn("≈", out)
        self.assertIn("multi-model", out)

        # Downgrade target must be the FIRST mid-tier model in file order (fake-mid), never
        # the second (fake-mid-b) -- the table header text is "On {target display}".
        self.assertIn("On Fake Mid One", out)
        self.assertNotIn("On Fake Mid Two", out)

        # Unpriced section lists the unknown raw model id.
        self.assertIn("unmapped-experimental-model", out)

        # AIU cross-check present with the pinned caveat.
        self.assertIn("AIU", out)
        self.assertIn("NOT assumed equal to the AIC billing unit", out)


# ---- 11. READ-ONLY byte-snapshot proof (incl. a junk session.db) ----------------------------


class ReadOnlyProofTests(unittest.TestCase):
    def test_fixture_home_bytes_unchanged_and_no_new_files(self):
        now = datetime.now(timezone.utc)

        def t(offset_seconds):
            return _iso(now - timedelta(seconds=offset_seconds))

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            state = home / "session-state"
            s = state / "dddddddd-0000-0000-0000-000000000004"
            s.mkdir(parents=True)
            (s / "workspace.yaml").write_text(
                "id: sess-d\nname: proj-delta\ncwd: /work/proj-delta\n"
            )
            (s / "events.jsonl").write_text(
                "\n".join(
                    [
                        _ev("session.start", t(200), selectedModel="fake-cheap"),
                        _ev(
                            "assistant.message",
                            t(190),
                            model="fake-cheap",
                            outputTokens=40,
                            apiCallId="d1",
                        ),
                        _ev(
                            "session.shutdown",
                            t(180),
                            totalNanoAiu=100000000,
                            totalPremiumRequests=1,
                            currentModel="fake-cheap",
                            tokenDetails=_td(500, 0, 0, 40),
                        ),
                    ]
                )
                + "\n"
            )
            # A junk SQLite-shaped file -- must NEVER be opened (D1).
            (s / "session.db").write_bytes(b"\x00NOT-A-REAL-DB\x01junk-bytes\x02")

            def snapshot():
                files = sorted(p for p in home.rglob("*") if p.is_file())
                return [str(p) for p in files], {str(p): p.read_bytes() for p in files}

            before_paths, before_bytes = snapshot()

            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cu.main(["--copilot-home", str(home), "--days", "30"])

            after_paths, after_bytes = snapshot()

            self.assertEqual(before_paths, after_paths)
            self.assertEqual(before_bytes, after_bytes)


# ---- 12. --days filter ------------------------------------------------------------------


class DaysFilterTests(unittest.TestCase):
    def test_old_session_excluded_no_timestamp_session_kept(self):
        now = datetime.now(timezone.utc)
        recent_offset_old = timedelta(days=90)
        old = _iso(now - recent_offset_old)

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            state = home / "session-state"

            old_s = state / "eeeeeeee-0000-0000-0000-000000000005"
            old_s.mkdir(parents=True)
            (old_s / "events.jsonl").write_text(
                "\n".join(
                    [
                        _ev("session.start", old, selectedModel="fake-cheap"),
                        _ev(
                            "assistant.message",
                            old,
                            model="fake-cheap",
                            outputTokens=10,
                            apiCallId="e1",
                        ),
                        _ev(
                            "session.shutdown",
                            old,
                            totalNanoAiu=100,
                            totalPremiumRequests=1,
                            currentModel="fake-cheap",
                            tokenDetails=_td(10, 0, 0, 10),
                        ),
                    ]
                )
                + "\n"
            )

            no_ts_s = state / "ffffffff-0000-0000-0000-000000000006"
            no_ts_s.mkdir(parents=True)
            (no_ts_s / "events.jsonl").write_text(
                "\n".join(
                    [
                        _ev("session.start", None, selectedModel="fake-cheap"),
                        _ev(
                            "assistant.message",
                            None,
                            model="fake-cheap",
                            outputTokens=20,
                            apiCallId="f1",
                        ),
                    ]
                )
                + "\n"
            )

            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cu.main(["--copilot-home", str(home), "--days", "30"])
                out = buf.getvalue()

        self.assertIn("across 1 sessions.", out)
        self.assertNotIn(old_s.name[:12], out)
        self.assertIn(no_ts_s.name[:12], out)


# ---- 13. Missing session dir -> SystemExit -----------------------------------------------


class MissingSessionDirTests(unittest.TestCase):
    def test_missing_session_state_dir_raises_system_exit(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)  # deliberately has no "session-state" child
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                with self.assertRaises(SystemExit):
                    cu.main(["--copilot-home", str(home)])

    def test_missing_explicit_session_dir_raises_system_exit(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "does-not-exist"
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                with self.assertRaises(SystemExit):
                    cu.main(["--session-dir", str(missing)])


# ---- 14. build_usage_payload: absent session_dir never exits ------------------------------


class BuildUsagePayloadAbsentTests(unittest.TestCase):
    def test_absent_session_dir_returns_found_false_payload(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "no-such-session-state"
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                payload = cu.build_usage_payload(missing)  # must never raise/exit

        self.assertEqual(payload["schema_version"], 1)
        self.assertFalse(payload["found"])
        self.assertEqual(payload["days"], 30)
        self.assertEqual(payload["top"], 10)
        self.assertEqual(payload["session_dir"], str(missing))
        self.assertEqual(payload["totals"]["sessions"], 0)
        self.assertEqual(payload["by_model"], [])
        self.assertEqual(payload["top_sessions"], [])
        self.assertEqual(payload["multi_model_sessions"], 0)
        self.assertEqual(payload["read_errors"], 0)
        self.assertIn(f"session-state directory absent: {missing}", payload["labels"])
        json.dumps(payload)  # must be JSON-serializable

    def test_absent_session_dir_honors_days_and_top_overrides(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "gone"
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                payload = cu.build_usage_payload(missing, days=7, top=3)
        self.assertEqual(payload["days"], 7)
        self.assertEqual(payload["top"], 3)


# ---- 15. build_usage_payload: happy path, required keys + totals parity with markdown -----


class BuildUsagePayloadHappyPathTests(unittest.TestCase):
    def _make_home(self, td):
        now = datetime.now(timezone.utc)

        def t(offset_seconds):
            return _iso(now - timedelta(seconds=offset_seconds))

        home = Path(td)
        state = home / "session-state"

        a = state / "aaaaaaaa-0000-0000-0000-000000000001"
        a.mkdir(parents=True)
        (a / "workspace.yaml").write_text(
            "id: sess-a\nname: proj-alpha\ncwd: /work/proj-alpha\n"
        )
        (a / "events.jsonl").write_text(
            "\n".join(
                [
                    _ev("session.start", t(600), selectedModel="fake-strong"),
                    _ev(
                        "assistant.message", t(590), model="fake-strong",
                        outputTokens=100, apiCallId="a1",
                    ),
                    _ev(
                        "session.shutdown", t(570), totalNanoAiu=1500000000,
                        totalPremiumRequests=1, currentModel="fake-strong",
                        tokenDetails=_td(1000, 200, 100, 200),
                    ),
                ]
            )
            + "\n"
        )

        b = state / "bbbbbbbb-0000-0000-0000-000000000002"
        b.mkdir(parents=True)
        (b / "workspace.yaml").write_text(
            "id: sess-b\nname: proj-beta\ncwd: /work/proj-beta\n"
        )
        (b / "events.jsonl").write_text(
            "\n".join(
                [
                    _ev("session.start", t(500), selectedModel="fake-mid"),
                    _ev(
                        "session.model_change", t(490), previousModel="fake-mid",
                        newModel="fake-front",
                    ),
                    _ev(
                        "assistant.message", t(480), model="fake-mid",
                        outputTokens=50, apiCallId="b1",
                    ),
                    _ev(
                        "assistant.message", t(470), model="fake-front",
                        outputTokens=80, apiCallId="b2",
                    ),
                    _ev(
                        "session.shutdown", t(460), totalNanoAiu=4000000000,
                        totalPremiumRequests=2, currentModel="fake-front",
                        tokenDetails=_td(2000, 500, 0, 130),
                    ),
                ]
            )
            + "\n"
        )
        return home

    def test_payload_required_keys_present(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._make_home(td)
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                payload = cu.build_usage_payload(
                    home / "session-state", days=30, top=10
                )

        self.assertEqual(payload["schema_version"], 1)
        self.assertTrue(payload["found"])
        for key in (
            "schema_version", "found", "days", "top", "session_dir", "totals",
            "by_model", "per_turn_output", "top_sessions", "multi_model_sessions",
            "read_errors", "labels",
        ):
            self.assertIn(key, payload)
        for key in ("usd", "aic", "aiu", "premium_requests", "sessions"):
            self.assertIn(key, payload["totals"])
        for entry in payload["by_model"]:
            for key in ("model", "usd", "aic", "sessions"):
                self.assertIn(key, entry)
            for tok_field in ("input", "cache_read", "cache_write", "output"):
                self.assertIn(tok_field, entry)
        for entry in payload["top_sessions"]:
            for key in ("session_id", "usd", "models"):
                self.assertIn(key, entry)
        self.assertIn(
            "token-priced estimate (est.) — Copilot bills in premium requests/AIC",
            payload["labels"],
        )
        # session B is multi-model -> the ≈ honesty label must be present.
        self.assertGreater(payload["multi_model_sessions"], 0)
        self.assertIn(
            "multi-model sessions attributed to last model (≈)", payload["labels"]
        )
        json.dumps(payload)  # must be JSON-serializable

    def test_payload_totals_match_markdown_path_numbers(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._make_home(td)
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                payload = cu.build_usage_payload(
                    home / "session-state", days=30, top=10
                )
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cu.main(["--copilot-home", str(home), "--days", "30"])
                out = buf.getvalue()

        totals = payload["totals"]
        self.assertIn(f"across {totals['sessions']} sessions.", out)
        self.assertIn(f"${totals['usd']:,.2f} ({totals['aic']:,.1f} AIC)", out)
        self.assertIn(
            f"{totals['aiu']:,.2f} AIU, {totals['premium_requests']:,} premium requests",
            out,
        )


# ---- 16. --json CLI path ------------------------------------------------------------------


class JsonCliTests(unittest.TestCase):
    def test_json_flag_present_dir_prints_payload_and_matches_builder(self):
        now = datetime.now(timezone.utc)

        def t(offset_seconds):
            return _iso(now - timedelta(seconds=offset_seconds))

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            state = home / "session-state"
            s = state / "aaaaaaaa-0000-0000-0000-000000000009"
            s.mkdir(parents=True)
            (s / "events.jsonl").write_text(
                "\n".join(
                    [
                        _ev("session.start", t(100), selectedModel="fake-cheap"),
                        _ev(
                            "assistant.message", t(90), model="fake-cheap",
                            outputTokens=10, apiCallId="j1",
                        ),
                        _ev(
                            "session.shutdown", t(80), totalNanoAiu=100,
                            totalPremiumRequests=1, currentModel="fake-cheap",
                            tokenDetails=_td(10, 0, 0, 10),
                        ),
                    ]
                )
                + "\n"
            )

            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cu.main(["--copilot-home", str(home), "--days", "30", "--json"])
                out = buf.getvalue()

                direct = cu.build_usage_payload(state, days=30, top=10)

        payload = json.loads(out)
        self.assertTrue(payload["found"])
        self.assertEqual(payload["totals"]["sessions"], direct["totals"]["sessions"])
        self.assertAlmostEqual(payload["totals"]["usd"], direct["totals"]["usd"])

    def test_json_flag_absent_dir_prints_found_false_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)  # no "session-state" child -> absent
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    try:
                        cu.main(["--copilot-home", str(home), "--json"])
                    except SystemExit as e:
                        self.fail(f"--json must exit 0, not sys.exit: {e}")
                out = buf.getvalue()

        payload = json.loads(out)
        self.assertFalse(payload["found"])
        self.assertIn("absent", payload["labels"][0])


# ---- 17. the public card is top-capped; render transport lives under _render ---------------


class PublicPayloadIsBoundedTests(unittest.TestCase):
    """T4b/F5: `session_rows` was an UNCAPPED top-level duplicate of the `top`-capped
    `top_sessions` -- a 900-session Copilot home would have put 900 per-session dicts into
    anything that persisted the card. It now lives under `_render` (the only `_`-prefixed
    top-level key), the public card keeps only `top_sessions`, and `--json` emits the public
    card. The fixture builds far MORE sessions than `top`, so an uncapped list is visible."""

    SESSIONS = 12
    TOP = 3

    def _make_home(self, td, n=None):
        """Every session's footprint is deliberately ABOVE ``DOWNGRADE_TOKEN_CEILING`` so
        the (pre-existing, markdown-pinned, therefore uncappable) ``downgrade_candidates``
        list stays empty here — this test is about the SESSION-keyed lists F5 moved."""
        n = self.SESSIONS if n is None else n
        now = datetime.now(timezone.utc)
        home = Path(td)
        state = home / "session-state"
        model_ids = list(FIXTURE["models"])
        big = cu.DOWNGRADE_TOKEN_CEILING * 2
        for i in range(n):
            model = model_ids[i % len(model_ids)]
            s = state / f"aaaaaaaa-0000-0000-0000-{i:012d}"
            s.mkdir(parents=True)
            (s / "workspace.yaml").write_text(
                f"id: sess-{i}\nname: proj-{i}\ncwd: /work/proj-{i}\n"
            )
            t = now - timedelta(seconds=600 + i * 10)
            (s / "events.jsonl").write_text("\n".join([
                _ev("session.start", _iso(t), selectedModel=model),
                _ev("assistant.message", _iso(t + timedelta(seconds=1)), model=model,
                    outputTokens=100 * (i + 1), apiCallId=f"a{i}"),
                _ev("session.shutdown", _iso(t + timedelta(seconds=2)),
                    totalNanoAiu=1500000000 * (i + 1), totalPremiumRequests=i + 1,
                    currentModel=model,
                    tokenDetails=_td(big + 1000 * (i + 1), 200 * (i + 1),
                                     100 * (i + 1), 200 * (i + 1))),
            ]) + "\n")
        return home

    def _payload(self, state, top=None):
        with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
            return cu.build_usage_payload(state, days=30,
                                          top=self.TOP if top is None else top)

    def test_render_is_the_only_underscore_key_on_both_branches(self):
        with tempfile.TemporaryDirectory() as td:
            present = self._payload(self._make_home(td) / "session-state")
        with tempfile.TemporaryDirectory() as td:
            absent = self._payload(Path(td) / "session-state")

        for name, payload in (("present", present), ("absent", absent)):
            with self.subTest(branch=name):
                stray = [k for k in payload if k.startswith("_") and k != "_render"]
                self.assertEqual(stray, [], f"{name}: stray transport keys {stray}")
                self.assertNotIn("session_rows", payload)
                self.assertIn("session_rows", payload["_render"])

    def test_public_card_has_no_uncapped_session_list(self):
        with tempfile.TemporaryDirectory() as td:
            payload = self._payload(self._make_home(td) / "session-state")

        public = {k: v for k, v in payload.items() if k != "_render"}
        json.dumps(public)

        self.assertEqual(payload["totals"]["sessions"], self.SESSIONS)  # all were scanned
        self.assertEqual(len(payload["top_sessions"]), self.TOP)        # only `top` kept
        self.assertEqual(len(payload["_render"]["session_rows"]), self.SESSIONS)
        self.assertEqual(payload["downgrade_candidates"], [])  # fixture keeps it empty

        # Every public list is bounded by `top` or by the pricing roster (by_model,
        # per_turn_output, unpriced_models are keyed by model, never by session), so none
        # of them can grow with the number of sessions scanned.
        ceiling = max(self.TOP, len(FIXTURE["models"]))
        self.assertLess(ceiling, self.SESSIONS)  # the check can actually fail
        for key, value in public.items():
            if isinstance(value, list):
                self.assertLessEqual(
                    len(value), ceiling,
                    f"public key {key!r} carries {len(value)} entries with "
                    f"top={self.TOP} -- an uncapped list escaped into the public card",
                )

        # Doubling the session count must not grow the public card's session-keyed data.
        with tempfile.TemporaryDirectory() as td2:
            bigger = self._payload(
                self._make_home(td2, self.SESSIONS * 2) / "session-state"
            )
        self.assertEqual(bigger["totals"]["sessions"], self.SESSIONS * 2)
        self.assertEqual(len(bigger["top_sessions"]), self.TOP)
        self.assertEqual(len(bigger["_render"]["session_rows"]), self.SESSIONS * 2)

    def test_json_flag_emits_the_public_card_without_render(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._make_home(td)
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cu.main(["--copilot-home", str(home), "--days", "30",
                             "--top", str(self.TOP), "--json"])
                out = buf.getvalue()

        printed = json.loads(out)
        self.assertNotIn("_render", printed)
        self.assertNotIn("session_rows", printed)
        self.assertEqual(len(printed["top_sessions"]), self.TOP)
        self.assertTrue(printed["found"])

    def test_markdown_top_table_still_holds_exactly_top_rows(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._make_home(td)
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cu.main(["--copilot-home", str(home), "--days", "30",
                             "--top", str(self.TOP)])
                md = buf.getvalue()

        heading = f"## Top {self.TOP} sessions by estimated cost"
        self.assertIn(heading, md)
        # Count rows inside the Top-sessions section only (it ends at the ≈/† legend).
        section = md.split(heading, 1)[1].split("\n`≈`", 1)[0]
        session_rows = [ln for ln in section.splitlines() if ln.startswith("| aaaaaaaa-000")]
        self.assertEqual(len(session_rows), self.TOP)


# ---- 18. T10: --kits-dir DATE-level ledger join --------------------------------------------
#
# The brief's own verbatim label ("ledger join, time-window match") was overridden per
# graph-convergence NOTES.md T10: a `run=` id carries no clock (PLAN D8's four hex characters
# are random), so only a same-day match is derivable. These tests pin the honest label text,
# the date-only join, the ambiguity-reporting rule (list every candidate, never guess one),
# read-only behavior over `--kits-dir`, and byte-identical degrade when unused/unmatched.


def _kit_notes(run_id, task_ids):
    lines = ["# NOTES\n"]
    for t in task_ids:
        lines.append(
            f"outcome: {t} model=sonnet attempts=1 result=pass review=clean run={run_id}"
        )
    return "\n".join(lines) + "\n"


class LedgerJoinTests(unittest.TestCase):
    WHEN = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)

    def _make_home(self, td):
        home = Path(td) / "copilot-home"
        state = home / "session-state"
        s = state / "aaaaaaaa-0000-0000-0000-00000000000a"
        s.mkdir(parents=True)
        (s / "events.jsonl").write_text(
            "\n".join(
                [
                    _ev("session.start", _iso(self.WHEN), selectedModel="fake-cheap"),
                    _ev(
                        "assistant.message",
                        _iso(self.WHEN + timedelta(seconds=30)),
                        model="fake-cheap",
                        outputTokens=10,
                        apiCallId="k1",
                    ),
                    _ev(
                        "session.shutdown",
                        _iso(self.WHEN + timedelta(seconds=60)),
                        totalNanoAiu=100,
                        totalPremiumRequests=1,
                        currentModel="fake-cheap",
                        tokenDetails=_td(10, 0, 0, 10),
                    ),
                ]
            )
            + "\n"
        )
        return home

    def test_no_kits_dir_flag_leaves_output_byte_identical(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._make_home(td)
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                without = cu.build_usage_payload(home / "session-state", days=30, top=10)
                with_none = cu.build_usage_payload(
                    home / "session-state", days=30, top=10, kits_dir=None
                )
        self.assertEqual(without, with_none)
        self.assertNotIn("ledger_join", without["top_sessions"][0])
        self.assertNotIn("kits_dir", without)

    def test_matching_kits_dir_annotates_row_with_honest_label(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._make_home(td)
            kits_dir = Path(td) / "kits"
            kit = kits_dir / "demo-kit"
            kit.mkdir(parents=True)
            run_id = f"{self.WHEN:%Y-%m-%d}-9f3a"
            (kit / "NOTES.md").write_text(_kit_notes(run_id, ["T1", "T2"]))

            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                payload = cu.build_usage_payload(
                    home / "session-state", days=30, top=10, kits_dir=str(kits_dir)
                )

        row = payload["top_sessions"][0]
        self.assertIn("ledger_join", row)
        lj = row["ledger_join"]
        self.assertEqual(
            lj["label"],
            "(ledger join, same-day run-id match — not a time-window match)",
        )
        self.assertEqual(lj["label"], cu.LEDGER_JOIN_LABEL)
        self.assertEqual(lj["date"], f"{self.WHEN:%Y-%m-%d}")
        self.assertFalse(lj["ambiguous"])
        self.assertEqual(
            lj["candidates"], [{"kit": "demo-kit", "run": run_id, "tasks": ["T1", "T2"]}]
        )
        self.assertEqual(payload["kits_dir"], str(kits_dir))

        md = cu.render_markdown(payload)
        self.assertIn(cu.LEDGER_JOIN_LABEL, md)
        self.assertIn("## Ledger join (--kits-dir)", md)
        self.assertIn("T1, T2", md)

    def test_non_matching_date_degrades_to_unannotated_byte_identical_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._make_home(td)
            kits_dir = Path(td) / "kits"
            kit = kits_dir / "demo-kit"
            kit.mkdir(parents=True)
            other_day = self.WHEN - timedelta(days=5)
            run_id = f"{other_day:%Y-%m-%d}-abcd"
            (kit / "NOTES.md").write_text(_kit_notes(run_id, ["T1"]))

            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                annotated_attempt = cu.build_usage_payload(
                    home / "session-state", days=30, top=10, kits_dir=str(kits_dir)
                )
                without = cu.build_usage_payload(home / "session-state", days=30, top=10)

        self.assertNotIn("ledger_join", annotated_attempt["top_sessions"][0])
        self.assertNotIn("kits_dir", annotated_attempt)
        self.assertEqual(cu.render_markdown(annotated_attempt), cu.render_markdown(without))

    def test_absent_kits_dir_path_degrades_silently(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._make_home(td)
            missing = Path(td) / "does-not-exist"
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                payload = cu.build_usage_payload(
                    home / "session-state", days=30, top=10, kits_dir=str(missing)
                )
        self.assertNotIn("ledger_join", payload["top_sessions"][0])
        self.assertNotIn("kits_dir", payload)

    def test_ambiguous_same_date_lists_every_candidate_never_guesses(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._make_home(td)
            kits_dir = Path(td) / "kits"
            kit_a = kits_dir / "kit-alpha"
            kit_b = kits_dir / "kit-beta"
            kit_a.mkdir(parents=True)
            kit_b.mkdir(parents=True)
            run_a = f"{self.WHEN:%Y-%m-%d}-1111"
            run_b = f"{self.WHEN:%Y-%m-%d}-2222"
            (kit_a / "NOTES.md").write_text(_kit_notes(run_a, ["T1"]))
            (kit_b / "NOTES.md").write_text(_kit_notes(run_b, ["T5", "T6"]))

            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                payload = cu.build_usage_payload(
                    home / "session-state", days=30, top=10, kits_dir=str(kits_dir)
                )

        lj = payload["top_sessions"][0]["ledger_join"]
        self.assertTrue(lj["ambiguous"])
        self.assertEqual(len(lj["candidates"]), 2)
        self.assertEqual(sorted(c["kit"] for c in lj["candidates"]), ["kit-alpha", "kit-beta"])

        md = cu.render_markdown(payload)
        self.assertIn("matched more than one kit/run on the same date", md)

    def test_kits_dir_never_written_to(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._make_home(td)
            kits_dir = Path(td) / "kits"
            kit = kits_dir / "demo-kit"
            kit.mkdir(parents=True)
            run_id = f"{self.WHEN:%Y-%m-%d}-9f3a"
            (kit / "NOTES.md").write_text(_kit_notes(run_id, ["T1"]))

            def snapshot():
                files = sorted(p for p in kits_dir.rglob("*") if p.is_file())
                return [str(p) for p in files], {str(p): p.read_bytes() for p in files}

            before = snapshot()
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                cu.build_usage_payload(
                    home / "session-state", days=30, top=10, kits_dir=str(kits_dir)
                )
            after = snapshot()
        self.assertEqual(before, after)

    def test_json_output_serializable_and_carries_ledger_join(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._make_home(td)
            kits_dir = Path(td) / "kits"
            kit = kits_dir / "demo-kit"
            kit.mkdir(parents=True)
            run_id = f"{self.WHEN:%Y-%m-%d}-9f3a"
            (kit / "NOTES.md").write_text(_kit_notes(run_id, ["T1"]))

            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cu.main([
                        "--copilot-home", str(home), "--days", "30",
                        "--kits-dir", str(kits_dir), "--json",
                    ])
                out = buf.getvalue()

        printed = json.loads(out)
        self.assertEqual(printed["kits_dir"], str(kits_dir))
        self.assertIn("ledger_join", printed["top_sessions"][0])


if __name__ == "__main__":
    unittest.main()
