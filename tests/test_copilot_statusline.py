"""Stdlib unittest regression suite for bin/copilot_statusline.py.

bin/ is not a package; copilot_statusline.py is loaded via importlib by absolute path computed
from this file's own location (the tests/test_copilot_pricing.py convention).

Every test calls the module's `main()`/helper functions directly, in-process, with `sys.stdin`
monkeypatched to a synthetic payload — nothing here spawns a subprocess, invokes the real
`copilot` CLI, or reads/writes the real ~/.copilot. The `--capture` test writes to a temp file
only.

The canonical "full payload" fixture below mirrors the REAL captured Copilot CLI v1.0.70
statusline payload's nested shape: `model.display_name`, `context_window.*`, `cost.*`, and
`ai_used.total_nano_aiu`/`formatted`.

The one real-file read this suite performs is data/pricing.copilot.json's own
billing_unit.usd_per_credit, used to compute the EXPECTED USD gloss at test time so nothing here
hardcodes a credit value — if that number ever changes, the assertions still hold because they
were derived, not copied.
"""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
PRICING_PATH = BIN_DIR.parent / "data" / "pricing.copilot.json"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cs = _load("copilot_statusline")


def real_usd_per_credit():
    with open(PRICING_PATH) as f:
        pricing = json.load(f)
    return float(pricing["billing_unit"]["usd_per_credit"])


def run_main(payload_text, argv=None):
    """Run cs.main() in-process with stdin patched to `payload_text`; returns (stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(cs.sys, "stdin", io.StringIO(payload_text)):
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            cs.main(argv or [])
    return out.getvalue(), err.getvalue()


# A synthetic payload shaped exactly like the real captured Copilot CLI v1.0.70 statusline
# payload (fields/values changed, nesting/keys identical). `total_nano_aiu` is chosen so that
# nano/1e9 is a clean one-decimal figure and `formatted` agrees with it, just like the real
# capture (total_nano_aiu=17682890000, formatted="17.7").
REAL_SHAPE_PAYLOAD = {
    "cwd": "/Users/example",
    "session_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "session_name": "Example session",
    "transcript_path": "/Users/example/.copilot/session-state/aaaaaaaa",
    "model": {"id": "claude-sonnet-5", "display_name": "claude-sonnet-5 · high · 1M context"},
    "workspace": {"current_dir": "/Users/example"},
    "username": None,
    "remote": {"connected": False},
    "version": "1.0.70",
    "cost": {
        "total_api_duration_ms": 55104,
        "total_lines_added": 0,
        "total_lines_removed": 0,
        "total_duration_ms": 754_000,
        "total_premium_requests": 4,
    },
    "context_window": {
        "total_input_tokens": 389390,
        "total_output_tokens": 3697,
        "total_cache_read_tokens": 362437,
        "total_cache_write_tokens": 26931,
        "total_reasoning_tokens": 1424,
        "total_tokens": 393087,
        "context_window_size": 1_000_000,
        "used_percentage": 5,
        "remaining_percentage": 95,
        "remaining_tokens": 954813,
        "last_call_input_tokens": 45070,
        "last_call_output_tokens": 117,
        "current_context_tokens": 34712,
        "displayed_context_limit": 1_000_000,
        "current_context_used_percentage": 42,
    },
    "ai_used": {"total_nano_aiu": 23_400_000_000, "formatted": "23.4"},
    "allow_all_enabled": False,
}


class FullPayloadTests(unittest.TestCase):
    def test_full_payload_renders_all_segments(self):
        upc = real_usd_per_credit()
        out, _ = run_main(json.dumps(REAL_SHAPE_PAYLOAD))
        line = out.strip()

        expected_aic = REAL_SHAPE_PAYLOAD["ai_used"]["total_nano_aiu"] / 1e9
        expected_usd = expected_aic * upc
        self.assertIn(REAL_SHAPE_PAYLOAD["model"]["id"], line)
        self.assertIn(f"{expected_aic:,.1f} AIC", line)
        self.assertIn(f"(~${expected_usd:,.2f})", line)
        self.assertIn("ctx 42%", line)
        self.assertIn("12m34s", line)
        self.assertNotEqual(line, cs.FALLBACK_LINE)

    def test_real_captured_payload_shape_all_four_segments(self):
        # Drives the exact captured payload shape from the task brief: nano-scale AIC that
        # agrees with `formatted`, a duration that requires rounding to the nearest second,
        # and every field nested exactly as GitHub Copilot CLI v1.0.70 actually sends it.
        upc = real_usd_per_credit()
        payload = dict(REAL_SHAPE_PAYLOAD)
        payload["cost"] = dict(REAL_SHAPE_PAYLOAD["cost"], total_duration_ms=1_544_719)
        payload["context_window"] = dict(
            REAL_SHAPE_PAYLOAD["context_window"], current_context_used_percentage=3
        )
        payload["ai_used"] = {"total_nano_aiu": 17_682_890_000, "formatted": "17.7"}

        out, _ = run_main(json.dumps(payload))
        line = out.strip()

        expected_aic = 17_682_890_000 / 1e9
        expected_usd = expected_aic * upc
        self.assertIn(payload["model"]["id"], line)
        self.assertIn(f"{expected_aic:,.1f} AIC (~${expected_usd:,.2f})", line)
        self.assertIn("ctx 3%", line)
        self.assertIn(cs.fmt_duration(1_544_719), line)
        # All four segments, in order, separated by " | ".
        self.assertEqual(
            line,
            f"{payload['model']['id']} | {expected_aic:,.1f} AIC (~${expected_usd:,.2f})"
            f" | ctx 3% | {cs.fmt_duration(1_544_719)}",
        )

    def test_render_smoke_example_shape(self):
        # A realistic, minimal synthetic payload using the real nested paths.
        upc = real_usd_per_credit()
        payload = {
            "model": {"display_name": "Sonnet 5"},
            "ai_used": {"total_nano_aiu": 23_400_000_000, "formatted": "23.4"},
            "context_window": {"current_context_used_percentage": 42},
        }
        out, _ = run_main(json.dumps(payload))
        line = out.strip()
        expected_aic = 23_400_000_000 / 1e9
        expected_usd = expected_aic * upc
        self.assertEqual(
            line, f"Sonnet 5 | {expected_aic:,.1f} AIC (~${expected_usd:,.2f}) | ctx 42%"
        )


class GracefulDegradationTests(unittest.TestCase):
    def test_missing_fields_degrade_gracefully(self):
        out, _ = run_main(json.dumps({"model": {"display_name": "Haiku 4.5"}}))
        line = out.strip()
        self.assertEqual(line, "Haiku 4.5")

    def test_empty_object_falls_back(self):
        out, _ = run_main(json.dumps({}))
        self.assertEqual(out.strip(), cs.FALLBACK_LINE)

    def test_unrecognized_keys_only_falls_back(self):
        out, _ = run_main(json.dumps({"some_future_key": 123, "another": "x"}))
        self.assertEqual(out.strip(), cs.FALLBACK_LINE)

    def test_model_string_form(self):
        out, _ = run_main(json.dumps({"model": "claude-sonnet-5"}))
        self.assertEqual(out.strip(), "claude-sonnet-5")

    def test_model_top_level_display_name_fallback(self):
        # No nested model.display_name — falls back to the older top-level guess.
        out, _ = run_main(json.dumps({"display_name": "Opus 4.8"}))
        self.assertEqual(out.strip(), "Opus 4.8")

    def test_model_nested_wins_over_top_level(self):
        # When both are present, the real nested path takes priority.
        payload = {"display_name": "Old Guess", "model": {"display_name": "Real Name"}}
        out, _ = run_main(json.dumps(payload))
        self.assertEqual(out.strip(), "Real Name")

    def test_context_pct_nested_current_context_used_percentage(self):
        payload = {
            "model": "claude-sonnet-5",
            "context_window": {"current_context_used_percentage": 3},
        }
        out, _ = run_main(json.dumps(payload))
        self.assertIn("ctx 3%", out)

    def test_context_pct_nested_used_percentage_fallback(self):
        payload = {"model": "claude-sonnet-5", "context_window": {"used_percentage": 5}}
        out, _ = run_main(json.dumps(payload))
        self.assertIn("ctx 5%", out)

    def test_context_pct_nested_derived_from_tokens_and_limit(self):
        payload = {
            "model": "claude-sonnet-5",
            "context_window": {
                "current_context_tokens": 50_000,
                "displayed_context_limit": 200_000,
            },
        }
        out, _ = run_main(json.dumps(payload))
        self.assertIn("ctx 25%", out)

    def test_context_pct_nested_derived_from_total_tokens_and_window_size(self):
        payload = {
            "model": "claude-sonnet-5",
            "context_window": {"total_tokens": 100_000, "context_window_size": 400_000},
        }
        out, _ = run_main(json.dumps(payload))
        self.assertIn("ctx 25%", out)

    def test_context_pct_top_level_fallback_when_no_context_window_dict(self):
        payload = {
            "model": "claude-sonnet-5",
            "current_context_tokens": 50_000,
            "displayed_context_limit": 200_000,
        }
        out, _ = run_main(json.dumps(payload))
        self.assertIn("ctx 25%", out)

    def test_context_pct_derived_from_context_window_size_fallback(self):
        payload = {
            "model": "claude-sonnet-5",
            "current_context_tokens": 100_000,
            "context_window_size": 400_000,
        }
        out, _ = run_main(json.dumps(payload))
        self.assertIn("ctx 25%", out)

    def test_zero_limit_does_not_crash_and_omits_context(self):
        payload = {
            "model": "claude-sonnet-5",
            "current_context_tokens": 100,
            "displayed_context_limit": 0,
            "context_window_size": 0,
        }
        out, _ = run_main(json.dumps(payload))
        self.assertEqual(out.strip(), "claude-sonnet-5")

    def test_duration_nested_cost_total_duration_ms(self):
        payload = {"model": "claude-sonnet-5", "cost": {"total_duration_ms": 754_000}}
        out, _ = run_main(json.dumps(payload))
        self.assertIn("12m34s", out)

    def test_duration_top_level_fallback_when_no_cost_dict(self):
        payload = {"model": "claude-sonnet-5", "total_duration_ms": 754_000}
        out, _ = run_main(json.dumps(payload))
        self.assertIn("12m34s", out)

    def test_malformed_nested_types_do_not_crash(self):
        # model is a list, ai_used is a string, context_window is a string — nothing here is a
        # dict/number the way the happy path expects; must degrade to the fallback, never raise.
        payload = {
            "model": [1, 2, 3],
            "ai_used": "not-a-dict",
            "context_window": "not-a-dict-either",
        }
        out, _ = run_main(json.dumps(payload))
        self.assertEqual(out.strip(), cs.FALLBACK_LINE)


class EmptyInvalidStdinTests(unittest.TestCase):
    def test_empty_stdin_falls_back(self):
        out, _ = run_main("")
        self.assertEqual(out.strip(), cs.FALLBACK_LINE)

    def test_whitespace_only_stdin_falls_back(self):
        out, _ = run_main("   \n  ")
        self.assertEqual(out.strip(), cs.FALLBACK_LINE)

    def test_invalid_json_falls_back(self):
        out, _ = run_main("not json at all {{{")
        self.assertEqual(out.strip(), cs.FALLBACK_LINE)

    def test_json_array_falls_back(self):
        # Valid JSON, but not an object — render() expects a dict.
        out, _ = run_main(json.dumps([1, 2, 3]))
        self.assertEqual(out.strip(), cs.FALLBACK_LINE)

    def test_json_scalar_falls_back(self):
        out, _ = run_main(json.dumps(42))
        self.assertEqual(out.strip(), cs.FALLBACK_LINE)


class AicUsdGlossTests(unittest.TestCase):
    def test_gloss_derived_from_real_pricing_file(self):
        upc = real_usd_per_credit()
        pricing = cs.load_pricing()
        self.assertIsNotNone(pricing)
        self.assertEqual(cs.usd_per_credit(pricing), upc)

        aic = 100.0
        segment = cs.credits_segment({"ai_used": {"total_nano_aiu": 100_000_000_000}}, pricing)
        self.assertEqual(segment, f"{aic:,.1f} AIC (~${aic * upc:,.2f})")

    def test_gloss_omitted_when_pricing_unavailable(self):
        segment = cs.credits_segment({"ai_used": {"total_nano_aiu": 100_000_000_000}}, None)
        self.assertEqual(segment, "100.0 AIC")

    def test_total_nano_aiu_confirmed_scale_includes_usd_gloss(self):
        # The nano scale is now confirmed, so total_nano_aiu alone (no formatted string) must
        # yield the AIC figure AND its USD gloss — no more "raw, unscaled" caution.
        pricing = cs.load_pricing()
        upc = real_usd_per_credit()
        segment = cs.credits_segment({"ai_used": {"total_nano_aiu": 23_400_000_000}}, pricing)
        aic = 23_400_000_000 / 1e9
        self.assertEqual(segment, f"{aic:,.1f} AIC (~${aic * upc:,.2f})")
        self.assertNotIn("raw", segment)
        self.assertNotIn("unscaled", segment)

    def test_formatted_leading_number_used_when_no_nano(self):
        pricing = cs.load_pricing()
        upc = real_usd_per_credit()
        segment = cs.credits_segment({"ai_used": {"formatted": "23.4 AIC"}}, pricing)
        self.assertEqual(segment, f"23.4 AIC (~${23.4 * upc:,.2f})")

    def test_top_level_total_nano_aiu_fallback_when_ai_used_absent(self):
        pricing = cs.load_pricing()
        upc = real_usd_per_credit()
        segment = cs.credits_segment({"total_nano_aiu": 10_000_000_000}, pricing)
        self.assertEqual(segment, f"10.0 AIC (~${10.0 * upc:,.2f})")

    def test_no_aic_source_yields_no_credits_segment(self):
        self.assertIsNone(cs.credits_segment({}, cs.load_pricing()))

    def test_ai_used_present_but_unparseable_yields_no_segment(self):
        # No total_nano_aiu and formatted has no leading number to parse — never fabricate a
        # figure, so the segment is omitted entirely (not shown as raw unparsed text).
        pricing = cs.load_pricing()
        segment = cs.credits_segment({"ai_used": {"formatted": "n/a"}}, pricing)
        self.assertIsNone(segment)


class CompactModeTests(unittest.TestCase):
    """`--compact` (alias `--slim`) renders ONLY the USD gloss + duration, complementing
    Copilot's own built-in footer (which already shows model/ctx%/AIC) — see
    docs/COPILOT-HARNESS.md. Default (no flag) mode must stay byte-identical; covered by
    FullPayloadTests/GracefulDegradationTests elsewhere in this file, none of which pass
    `--compact`.
    """

    def test_compact_full_real_shape_payload(self):
        upc = real_usd_per_credit()
        payload = dict(REAL_SHAPE_PAYLOAD)
        payload["cost"] = dict(REAL_SHAPE_PAYLOAD["cost"], total_duration_ms=1_544_719)
        payload["ai_used"] = {"total_nano_aiu": 17_682_890_000, "formatted": "17.7"}

        out, _ = run_main(json.dumps(payload), argv=["--compact"])
        expected_aic = 17_682_890_000 / 1e9
        expected_usd = expected_aic * upc
        self.assertEqual(out.strip(), f"~${expected_usd:,.2f} · {cs.fmt_duration(1_544_719)}")
        self.assertEqual(out.strip(), "~$0.18 · 25m45s")

    def test_compact_alias_slim_matches_compact(self):
        payload = {
            "cost": {"total_duration_ms": 1_544_719},
            "ai_used": {"total_nano_aiu": 17_682_890_000, "formatted": "17.7"},
        }
        out_compact, _ = run_main(json.dumps(payload), argv=["--compact"])
        out_slim, _ = run_main(json.dumps(payload), argv=["--slim"])
        self.assertEqual(out_compact, out_slim)

    def test_compact_ai_used_absent_yields_duration_only(self):
        out, _ = run_main(
            json.dumps({"cost": {"total_duration_ms": 1_544_719}}), argv=["--compact"]
        )
        self.assertEqual(out.strip(), cs.fmt_duration(1_544_719))
        self.assertNotIn("$", out)

    def test_compact_neither_field_yields_empty_line(self):
        out, _ = run_main(json.dumps({}), argv=["--compact"])
        self.assertEqual(out, "\n")

    def test_compact_unparseable_stdin_yields_empty_line_not_fallback(self):
        # Unlike default mode (which prints FALLBACK_LINE on unparseable stdin), --compact
        # degrades to an empty line — the whole point is to contribute nothing when there's
        # nothing worth adding, never a placeholder line.
        out, _ = run_main("not json at all {{{", argv=["--compact"])
        self.assertEqual(out, "\n")
        self.assertNotIn(cs.FALLBACK_LINE, out)

    def test_compact_pricing_unavailable_omits_usd_but_keeps_duration(self):
        payload = {
            "cost": {"total_duration_ms": 1_544_719},
            "ai_used": {"total_nano_aiu": 17_682_890_000},
        }
        data = json.loads(json.dumps(payload))
        with mock.patch.object(cs, "load_pricing", return_value=None):
            line = cs.render_compact(data)
        self.assertEqual(line, cs.fmt_duration(1_544_719))

    def test_compact_plus_capture_still_writes_payload(self):
        payload_text = json.dumps(
            {
                "cost": {"total_duration_ms": 1_544_719},
                "ai_used": {"total_nano_aiu": 17_682_890_000, "formatted": "17.7"},
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            capture_path = Path(tmp) / "captured.json"
            out, _ = run_main(
                payload_text, argv=["--compact", "--capture", str(capture_path)]
            )
            self.assertEqual(capture_path.read_text(), payload_text)
            self.assertEqual(out.strip(), "~$0.18 · 25m45s")

    def test_default_mode_unchanged_when_compact_flag_absent(self):
        # Regression guard: rerunning the exact FullPayloadTests fixture WITHOUT --compact
        # must still produce the full pipe-delimited line, not the compact one.
        upc = real_usd_per_credit()
        out, _ = run_main(json.dumps(REAL_SHAPE_PAYLOAD))
        line = out.strip()
        expected_aic = REAL_SHAPE_PAYLOAD["ai_used"]["total_nano_aiu"] / 1e9
        expected_usd = expected_aic * upc
        self.assertIn(" | ", line)
        self.assertNotIn(" · ", line)
        self.assertIn(f"{expected_aic:,.1f} AIC (~${expected_usd:,.2f})", line)


class CaptureAffordanceTests(unittest.TestCase):
    def test_capture_writes_raw_payload_verbatim(self):
        payload_text = json.dumps({"model": "claude-sonnet-5", "weird_future_key": True})
        with tempfile.TemporaryDirectory() as tmp:
            capture_path = Path(tmp) / "captured.json"
            out, _ = run_main(payload_text, argv=["--capture", str(capture_path)])
            self.assertEqual(capture_path.read_text(), payload_text)
            # It still prints a normal status line, not just capturing silently.
            self.assertIn("claude-sonnet-5", out)

    def test_capture_of_empty_stdin_writes_empty_file_and_still_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            capture_path = Path(tmp) / "captured.json"
            out, _ = run_main("", argv=["--capture", str(capture_path)])
            self.assertEqual(capture_path.read_text(), "")
            self.assertEqual(out.strip(), cs.FALLBACK_LINE)

    def test_debug_writes_raw_payload_to_stderr(self):
        payload_text = json.dumps({"model": "claude-sonnet-5"})
        out, err = run_main(payload_text, argv=["--debug"])
        self.assertIn(payload_text, err)
        self.assertIn("claude-sonnet-5", out)

    def test_capture_to_unwritable_path_does_not_crash(self):
        # A directory that doesn't exist and can't be created as a file path — write must fail
        # silently, never raise, and the status line must still print.
        bogus_path = "/nonexistent-dir-xyz/definitely/not/here.json"
        out, _ = run_main(json.dumps({"model": "claude-sonnet-5"}), argv=["--capture", bogus_path])
        self.assertIn("claude-sonnet-5", out)


class HelperUnitTests(unittest.TestCase):
    def test_pick_model_name_top_level_display_name(self):
        self.assertEqual(cs.pick_model_name({"display_name": "Opus 4.8"}), "Opus 4.8")

    def test_pick_model_name_nested_model_dict(self):
        self.assertEqual(
            cs.pick_model_name({"model": {"display_name": "Opus 4.8"}}), "Opus 4.8"
        )

    def test_pick_model_name_plain_string_model(self):
        self.assertEqual(cs.pick_model_name({"model": "claude-opus-4.8"}), "claude-opus-4.8")

    def test_pick_model_name_absent(self):
        self.assertIsNone(cs.pick_model_name({}))

    def test_pick_aic_prefers_nested_nano_over_formatted(self):
        data = {"ai_used": {"total_nano_aiu": 5_000_000_000, "formatted": "999"}}
        self.assertEqual(cs.pick_aic(data), 5.0)

    def test_pick_aic_none_when_nothing_present(self):
        self.assertIsNone(cs.pick_aic({}))

    def test_fmt_duration_hours(self):
        self.assertEqual(cs.fmt_duration(3_754_000), "1h02m")

    def test_fmt_duration_minutes(self):
        self.assertEqual(cs.fmt_duration(754_000), "12m34s")

    def test_fmt_duration_seconds(self):
        self.assertEqual(cs.fmt_duration(9_000), "9s")

    def test_fmt_duration_rounds_to_nearest_second(self):
        # The real captured duration (1544719 ms) must round to 25m45s, not truncate to
        # 25m44s — fmt_duration rounds the millisecond figure to the nearest second first.
        self.assertEqual(cs.fmt_duration(1_544_719), "25m45s")

    def test_fmt_duration_non_numeric(self):
        self.assertIsNone(cs.fmt_duration("nope"))
        self.assertIsNone(cs.fmt_duration(None))

    def test_fmt_tokens(self):
        self.assertEqual(cs.fmt_tokens(500), "500")
        self.assertEqual(cs.fmt_tokens(12_000), "12K")
        self.assertEqual(cs.fmt_tokens(1_700_000), "1.7M")
        self.assertIsNone(cs.fmt_tokens("nope"))


if __name__ == "__main__":
    unittest.main()
