"""Cross-builder uniformity contract for the four pure builders T5 (the telemetry store
engine) imports and calls (telemetry-store PLAN D3).

Phase 1 tested each builder against ITSELF. This file is the check that was missing: the
four builders diffed against EACH OTHER, so one drifting away from the shared shape fails
here rather than inside the snapshot tool.

SAFETY CONTRACT (binds every test in this file): no real home dir is read, no CLI is ever
invoked, nothing is written. Every builder is called with an absent path inside a fresh
``tempfile.TemporaryDirectory()``, and the temp dir is deleted before any assertion runs.
No model id, price, or home path is spelled here.

bin/ is not a package; each module is loaded via importlib by absolute path computed from
this file's own location (BIN_DIR), the house pattern.

THE CONTRACT, and the one documented asymmetry
----------------------------------------------
Three builders return a payload for an absent source, because absence is DATA for them:

    cost_report.build_report_payload / copilot_usage.build_usage_payload /
    codex_usage.build_usage_payload

        -> ``found is False``; ``labels`` is a list with >= 1 label containing "absent";
           the payload is JSON-serializable; nothing is printed; and ``_render`` is the
           only ``_``-prefixed top-level key (render transport never leaks into the card).

``routing_scorecard.assemble_history_card`` is deliberately DIFFERENT and must stay so:
PLAN D3 pins it to RAISE ``ValueError`` with the exact messages ``run_history`` exits on,
because ``run_history`` catches and exits identically -- a ``found: False`` card there
would silently change the CLI's exit behavior. So its absence contract is asserted as the
raise, and the shared half of the contract (silence, JSON-serializability, no stray
``_`` keys) is asserted against a card built over a real-but-empty temp kits dir.
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


cr = _load("cost_report")
cxu = _load("codex_usage")
cpu = _load("copilot_usage")
rs = _load("routing_scorecard")


def _payload_builders():
    """(name, callable taking an absent path) for the three absence-is-data builders."""
    return [
        ("cost_report.build_report_payload",
         lambda p: cr.build_report_payload(p, days=30, top=10)),
        ("codex_usage.build_usage_payload",
         lambda p: cxu.build_usage_payload(p, days=30, top=10)),
        ("copilot_usage.build_usage_payload",
         lambda p: cpu.build_usage_payload(p, days=30, top=10)),
    ]


def _call_on_absent_path(fn):
    """Call `fn` on a path that does not exist, capturing stdout. The temp dir is torn
    down before the caller asserts, so nothing can accidentally depend on it."""
    buf = io.StringIO()
    with tempfile.TemporaryDirectory() as td:
        absent = Path(td) / "definitely" / "not" / "here"
        with contextlib.redirect_stdout(buf):
            result = fn(absent)
    return result, buf.getvalue(), absent


class AbsentSourceUniformityTests(unittest.TestCase):
    def test_absent_source_yields_found_false(self):
        for name, fn in _payload_builders():
            with self.subTest(builder=name):
                payload, _, _ = _call_on_absent_path(fn)
                self.assertIs(payload["found"], False)

    def test_absent_source_carries_an_absence_label(self):
        for name, fn in _payload_builders():
            with self.subTest(builder=name):
                payload, _, absent = _call_on_absent_path(fn)
                labels = payload["labels"]
                self.assertIsInstance(labels, list)
                matching = [x for x in labels if "absent" in str(x)]
                self.assertTrue(
                    matching,
                    f"{name}: no absence label among {labels!r} -- absence of evidence "
                    f"must be written down AS absence",
                )
                # The label names the path that was missing, so a stored envelope stays
                # self-describing long after the run.
                self.assertTrue(
                    any(str(absent) in str(x) for x in matching),
                    f"{name}: absence label does not name the missing path {absent}",
                )

    def test_absent_source_payload_is_json_serializable(self):
        for name, fn in _payload_builders():
            with self.subTest(builder=name):
                payload, _, _ = _call_on_absent_path(fn)
                json.dumps(payload)

    def test_builders_never_print(self):
        for name, fn in _payload_builders():
            with self.subTest(builder=name):
                _, printed, _ = _call_on_absent_path(fn)
                self.assertEqual(printed, "", f"{name} wrote to stdout: {printed!r}")

    def test_render_is_the_only_underscore_prefixed_top_level_key(self):
        for name, fn in _payload_builders():
            with self.subTest(builder=name):
                payload, _, _ = _call_on_absent_path(fn)
                stray = sorted(k for k in payload
                               if str(k).startswith("_") and k != "_render")
                self.assertEqual(
                    stray, [],
                    f"{name}: render-only transport {stray} sits at the top level -- "
                    f"consolidate it under the single `_render` key",
                )

    def test_public_card_of_every_builder_is_json_serializable_without_render(self):
        for name, fn in _payload_builders():
            with self.subTest(builder=name):
                payload, _, _ = _call_on_absent_path(fn)
                json.dumps({k: v for k, v in payload.items() if k != "_render"})

    def test_shared_required_keys(self):
        for name, fn in _payload_builders():
            with self.subTest(builder=name):
                payload, _, _ = _call_on_absent_path(fn)
                for key in ("schema_version", "found", "days", "labels"):
                    self.assertIn(key, payload, f"{name} is missing {key!r}")
                self.assertEqual(payload["schema_version"], 1)
                self.assertEqual(payload["days"], 30)


class AssembleHistoryCardAsymmetryTests(unittest.TestCase):
    """The fourth builder's absence contract is a raise, by design (PLAN D3)."""

    def test_absent_kits_dir_raises_value_error_silently(self):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as td:
            absent = Path(td) / "definitely" / "not" / "here"
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(ValueError) as ctx:
                    rs.assemble_history_card([str(absent)],
                                             projects_dir=str(Path(td) / "projects"))
        self.assertIn("kits dir not found", str(ctx.exception))
        self.assertIn(str(absent), str(ctx.exception))
        self.assertEqual(buf.getvalue(), "")

    def test_no_kits_dir_at_all_raises_the_same_shape_never_index_error(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(ValueError) as ctx:
                rs.assemble_history_card([])
        self.assertIn("kits dir not found", str(ctx.exception))
        self.assertEqual(buf.getvalue(), "")

    def test_empty_but_present_kits_dir_returns_a_silent_serializable_card(self):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as td:
            kits = Path(td) / "kits"
            kits.mkdir()
            with contextlib.redirect_stdout(buf):
                card = rs.assemble_history_card([str(kits)],
                                                projects_dir=str(Path(td) / "projects"))
        self.assertEqual(buf.getvalue(), "")
        json.dumps(card)
        stray = sorted(k for k in card if str(k).startswith("_"))
        self.assertEqual(stray, [], f"card carries transport keys {stray}")
        # No kits found is written down as a note, never as a fabricated zero-kit result.
        self.assertTrue(any("no kits with a TASKS.md" in str(n) for n in card["notes"]),
                        card["notes"])
        self.assertIsNone(card["dollars"])


if __name__ == "__main__":
    unittest.main()
