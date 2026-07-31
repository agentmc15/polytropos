"""Stdlib unittest regression suite for bin/context_weight.py (T1 of the context-weight kit).

SAFETY CONTRACT (binds every test in this file, mirrors tests/test_codex_usage.py): no test
here ever invokes the real ``claude``/``codex``/``copilot`` CLI, opens a ``*.db``/SQLite file,
writes anything outside a fresh ``tempfile.TemporaryDirectory()``, or resolves the caller's
real home via ``Path.home``. ``Path.home()`` count in this file: ZERO — every seam is passed
explicitly via ``--projects-dir``. Pricing comes from the REAL ``data/pricing.json`` (there is
no synthetic pricing fixture here, unlike the codex/copilot usage-reader tests) because the
module under test never hardcodes a price, ratio, or model id — it always resolves the model
id it needs (first sonnet-tier key) from the pricing file at run time, per PLAN D9/D11.

bin/ is not a package; context_weight.py is loaded via importlib by absolute path computed
from this file's own location (BIN_DIR), the ``_load`` idiom from tests/test_codex_usage.py.
"""

import contextlib
import importlib.util
import io
import json
import os
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


cw = _load("context_weight")


def _first_sonnet_model():
    pricing = cw.cr.load_pricing()
    for key, v in pricing["models"].items():
        if v.get("tier") == "sonnet":
            return key
    raise AssertionError("no sonnet-tier model in data/pricing.json")


# ---- pinned Claude fixture (T1 brief; also T7's demo fixture) -----------------------------
#
# One <tmp>/projects/demo-proj/demo-claude.jsonl. Every assistant record is non-sidechain
# except m5. Distinct message.id m1-m5, ISO timestamps one minute apart.


def _ts(n):
    base = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(minutes=n)).isoformat().replace("+00:00", "Z")


def _assistant_record(msg_id, model, in_, cache_read, cache_write, out, minute,
                       tool_use=None, is_sidechain=False):
    content = []
    if tool_use:
        content.append({
            "type": "tool_use",
            "id": tool_use["id"],
            "name": tool_use["name"],
            "input": tool_use["input"],
        })
    rec = {
        "type": "assistant",
        "timestamp": _ts(minute),
        "message": {
            "id": msg_id,
            "model": model,
            "usage": {
                "input_tokens": in_,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_write,
                "output_tokens": out,
            },
            "content": content,
        },
    }
    if is_sidechain:
        rec["isSidechain"] = True
    return rec


def _user_tool_result(tool_use_id, content_text, minute):
    return {
        "type": "user",
        "timestamp": _ts(minute),
        "message": {
            "content": [
                {"type": "tool_result", "tool_use_id": tool_use_id, "content": content_text},
            ],
        },
    }


def _claude_fixture_records(model_id):
    """The exact pinned fixture (T1 brief) as parsed dicts, in file order. Reused by T7's demo
    tests via the module-level helper below, which serializes these to JSONL text."""
    return [
        _assistant_record("m1", model_id, 9000, 0, 1000, 200, 0,
                           tool_use={"id": "toolu_d1", "name": "Bash",
                                     "input": {"command": "ls -la"}}),
        _user_tool_result("toolu_d1", "x" * 20000, 1),
        _assistant_record("m2", model_id, 1000, 10000, 9000, 300, 2,
                           tool_use={"id": "toolu_d2", "name": "Read",
                                     "input": {"file_path": "/workspace/demo.txt"}}),
        _user_tool_result("toolu_d2", "y" * 8000, 3),
        _assistant_record("m3", model_id, 1000, 20000, 9000, 150, 4),
        _assistant_record("m4", model_id, 8000, 0, 0, 100, 5),
        _assistant_record("m5", model_id, 4000, 1000, 0, 50, 6, is_sidechain=True),
    ]


def _claude_fixture_lines(model_id):
    """Module-level helper (per the T1 brief). T7 MOVED this builder's body into the engine as
    ``cw.demo_claude_fixture_lines`` (the one sanctioned test-file refactor — the engine cannot
    import this test file, so ``demo`` needs its own copy); this wrapper re-points every existing
    call site at that engine copy. Content is unchanged: same fixture as ``_claude_fixture_records``
    above, serialized to JSONL text lines."""
    return cw.demo_claude_fixture_lines(model_id)


def _write_claude_fixture(projects_dir, model_id, project="demo-proj",
                           filename="demo-claude.jsonl"):
    d = Path(projects_dir) / project
    d.mkdir(parents=True, exist_ok=True)
    p = d / filename
    p.write_text("\n".join(_claude_fixture_lines(model_id)) + "\n")
    return p


def _audit_fixture(project_dir):
    """Synthetic resident-surface fixture (T6 brief; also T7's demo fixture): CLAUDE.md 2000
    chars, AGENTS.md 1200 chars, .github/copilot-instructions.md 800 chars -> against the 5000
    default budget, est. 500/300/200 tokens = 10%/6%/4%. This is a SYNTHETIC fixture, NOT this
    repo's real files — the pinned numbers below must never be swapped for real file sizes. T7
    MOVED the builder itself into the engine as ``cw.demo_audit_fixture`` (the one sanctioned
    test-file refactor); this wrapper re-points every existing call site at that engine copy."""
    return cw.demo_audit_fixture(project_dir)


def _snapshot_tree(root):
    """paths + mtimes, for the read-only proof."""
    snap = {}
    for p in Path(root).rglob("*"):
        if p.is_file():
            st = p.stat()
            snap[str(p)] = (st.st_mtime_ns, st.st_size)
    return snap


# ---- 1. claude_call_weights on the pinned fixture ------------------------------------------


class ClaudeCallWeightsTests(unittest.TestCase):
    def setUp(self):
        self.model_id = _first_sonnet_model()
        self.objs = _claude_fixture_records(self.model_id)

    def test_weights_avg_peak_total(self):
        calls, sidechain, notes = cw.claude_call_weights(self.objs)
        weights = [c["weight"] for c in calls]
        self.assertEqual(weights, [10000, 20000, 30000, 8000])
        self.assertEqual(round(sum(weights) / len(weights)), 17000)
        self.assertEqual(max(weights), 30000)
        self.assertEqual(sum(weights), 68000)

    def test_sidechain_aggregate(self):
        _calls, sidechain, _notes = cw.claude_call_weights(self.objs)
        self.assertEqual(sidechain, {"calls": 1, "weight": 5000})

    def test_non_sidechain_calls_carry_expected_fields(self):
        calls, _sidechain, _notes = cw.claude_call_weights(self.objs)
        self.assertEqual(len(calls), 4)
        first = calls[0]
        for key in ("weight", "input", "cache_read", "cache_write", "output",
                    "timestamp", "model"):
            self.assertIn(key, first)
        self.assertEqual(first["input"], 9000)
        self.assertEqual(first["output"], 200)
        self.assertEqual(first["model"], self.model_id)

    def test_message_id_dedupe(self):
        duplicated = self.objs + [self.objs[0]]  # re-append m1's line
        calls, _sidechain, _notes = cw.claude_call_weights(duplicated)
        self.assertEqual(len(calls), 4)  # still 4, not 5 — duplicate counted once

    def test_confirmed_compact_summary_note(self):
        tagged = list(self.objs)
        tagged[4] = dict(tagged[4])  # m3's record
        tagged[4]["isCompactSummary"] = True
        calls, _sidechain, notes = cw.claude_call_weights(tagged)
        # m3 is the 3rd non-sidechain call -> index 2 within `calls`.
        self.assertEqual(notes, [{"index": 2, "kind": "confirmed_compact_summary"}])
        self.assertEqual(calls[2]["input"], 1000)  # unaffected otherwise

    def test_non_dict_and_malformed_lines_are_skipped(self):
        objs = [None, "not a dict", {"type": "system"}] + self.objs
        calls, sidechain, _notes = cw.claude_call_weights(objs)
        self.assertEqual(len(calls), 4)
        self.assertEqual(sidechain["calls"], 1)

    def test_tool_result_and_usageless_records_are_skipped(self):
        calls, _sidechain, _notes = cw.claude_call_weights(self.objs)
        # 7 pinned records total; only the 4 non-sidechain assistant records become calls.
        self.assertEqual(len(calls), 4)


# ---- 2. detect_drops -------------------------------------------------------------------------


class DetectDropsTests(unittest.TestCase):
    def test_exactly_one_inferred_drop(self):
        drops = cw.detect_drops([10000, 20000, 30000, 8000])
        self.assertEqual(drops, [{"index": 3, "before": 30000, "after": 8000}])

    def test_no_drop_on_monotonic_growth(self):
        self.assertEqual(cw.detect_drops([1000, 2000, 3000]), [])

    def test_exactly_half_is_not_a_drop(self):
        # weights[i] must be STRICTLY less than before * (1 - DROP_FRACTION); an exact half
        # (10000 -> 5000, with DROP_FRACTION=0.5) is the boundary and must NOT fire.
        self.assertEqual(cw.detect_drops([10000, 5000]), [])

    def test_empty_and_singleton(self):
        self.assertEqual(cw.detect_drops([]), [])
        self.assertEqual(cw.detect_drops([1234]), [])


# ---- 3. carry cost hand computation -----------------------------------------------------------


class CarryCostTests(unittest.TestCase):
    def test_carry_cost_matches_hand_computation(self):
        model_id = _first_sonnet_model()
        objs = _claude_fixture_records(model_id)
        calls, _sidechain, notes = cw.claude_call_weights(objs)
        drops = cw.detect_drops([c["weight"] for c in calls])
        pricing = cw.cr.load_pricing()
        card = cw.build_session_card(
            "sess", ["one-file"], calls, {"calls": 0, "weight": 0}, notes, drops, pricing
        )

        usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
        for c in calls:
            for f in ("input", "output", "cache_read", "cache_write"):
                usage[f] += c[f]
        zeroed = dict(usage)
        zeroed["output"] = 0
        expected_carry = cw.cr.price(model_id, zeroed, None, pricing)
        expected_total = cw.cr.price(model_id, usage, None, pricing)

        self.assertAlmostEqual(card["carry_cost"]["carry_usd"], expected_carry, places=9)
        self.assertAlmostEqual(card["carry_cost"]["session_total_usd"], expected_total, places=9)
        self.assertEqual(card["carry_cost"]["label"], cw.CARRY_COST_LABEL)


# ---- 4. CLI end-to-end -------------------------------------------------------------------------


def _run_main(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cw.main(argv)
    return rc, buf.getvalue()


class CliEndToEndTests(unittest.TestCase):
    def test_session_claude_json_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_id = _first_sonnet_model()
            projects_dir = Path(tmp) / "projects"
            _write_claude_fixture(projects_dir, model_id)

            rc, out = _run_main(
                ["session", "--harness", "claude", "--projects-dir", str(projects_dir), "--json"]
            )
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertTrue(data["found"])
            self.assertEqual(data["schema_version"], cw.CW_SCHEMA_VERSION)
            self.assertEqual(data["calls"], 4)
            self.assertEqual(data["avg_weight"], 17000)
            self.assertEqual(data["peak_weight"], 30000)
            self.assertEqual(data["total_submitted"], 68000)
            self.assertEqual(data["sidechain"], {"calls": 1, "weight": 5000})
            self.assertEqual(len(data["inferred_drops"]), 1)
            self.assertEqual(data["inferred_drops"][0],
                              {"index": 3, "before": 30000, "after": 8000})
            self.assertIn("carry_cost", data)
            self.assertEqual(data["carry_cost"]["label"], cw.CARRY_COST_LABEL)

    def test_session_claude_markdown_renders(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_id = _first_sonnet_model()
            projects_dir = Path(tmp) / "projects"
            _write_claude_fixture(projects_dir, model_id)

            rc, out = _run_main(
                ["session", "--harness", "claude", "--projects-dir", str(projects_dir)]
            )
            self.assertEqual(rc, 0)
            self.assertIn("Context weight — session", out)
            self.assertIn("inferred compaction", out)
            self.assertIn("Sidechain (subagents)", out)
            self.assertIn("context carry cost:", out)
            self.assertIn(cw.CARRY_COST_LABEL, out)

    def test_absent_projects_dir_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            nowhere = Path(tmp) / "does-not-exist"
            rc, out = _run_main(
                ["session", "--harness", "claude", "--projects-dir", str(nowhere), "--json"]
            )
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertFalse(data["found"])
            self.assertIn(str(nowhere), data["message"])

    def test_empty_projects_dir_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp) / "projects"
            projects_dir.mkdir()
            rc, out = _run_main(
                ["session", "--harness", "claude", "--projects-dir", str(projects_dir)]
            )
            self.assertEqual(rc, 0)
            self.assertIn("No claude transcript found", out)

    def test_session_copilot_harness_no_longer_a_placeholder(self):
        # Copilot is implemented as of T4 (see CopilotSession* tests below) — the old
        # "lands in a later task" placeholder no longer applies to any harness in `session`.
        with tempfile.TemporaryDirectory() as tmp:
            copilot_home = Path(tmp) / "copilot-home"
            rc, out = _run_main(
                ["session", "--harness", "copilot", "--copilot-home", str(copilot_home)]
            )
            self.assertEqual(rc, 0)
            self.assertNotIn("lands in a later task", out)

# ---- 4b. demo (T7, PLAN D11) ---------------------------------------------------------------
#
# `demo` takes NO home-override flags at all — it builds its own synthetic fixtures inside a
# throwaway temp dir and never reads `~/.claude`, `~/.codex`, or `~/.copilot`, so `main(["demo"])`
# is safe to call directly here with no fixture setup, unlike every other CLI test in this file.


class DemoTests(unittest.TestCase):
    def test_markdown_pinned_facts(self):
        rc, out = _run_main(["demo"])
        self.assertEqual(rc, 0)

        # Claude: weights [10000, 20000, 30000, 8000], avg 17000, peak 30000, total 68000.
        self.assertIn("avg weight 17,000 · peak weight 30,000 · total submitted 68,000", out)
        self.assertIn("| 1 | 9,000 | 0 | 1,000 | 10,000 |", out)
        self.assertIn("| 2 | 1,000 | 10,000 | 9,000 | 20,000 |", out)
        self.assertIn("| 3 | 1,000 | 20,000 | 9,000 | 30,000 |", out)
        self.assertIn("| 4 | 8,000 | 0 | 0 | 8,000 |", out)
        # one inferred compaction, 30000 -> 8000.
        self.assertIn("call 4: inferred compaction (30,000 → 8,000)", out)
        # sidechain: 1 call, 5000 tokens.
        self.assertIn("Sidechain (subagents): 1 call(s), 5,000 tokens", out)
        # attribution: Bash 5000 est. ranked ahead of Read 2000 est.; assistant output (measured)
        # 750 measured; unattributed 12250 est. (NOT 13000 — T13 subtracted measured output).
        self.assertIn("| Bash | ls -la | 5,000 est. |", out)
        self.assertIn("| Read | /workspace/demo.txt | 2,000 est. |", out)
        self.assertIn(f"| {cw.ASSISTANT_OUTPUT_LABEL} |  | 750 measured |", out)
        self.assertIn("| unattributed growth |  | 12,250 est. |", out)
        bash_idx = out.index("| Bash | ls -la | 5,000 est. |")
        read_idx = out.index("| Read | /workspace/demo.txt | 2,000 est. |")
        self.assertLess(bash_idx, read_idx)

        # Codex: weights [3000, 8000, 13000], avg 8000; verbatim no-provenance line.
        self.assertIn("| 1 | 3,000 |", out)
        self.assertIn("| 2 | 8,000 |", out)
        self.assertIn("| 3 | 13,000 |", out)
        self.assertIn("avg weight 8,000 · peak weight 13,000", out)
        self.assertIn(cw.CODEX_NO_PROVENANCE_LINE, out)

        # Copilot: session-average 21000, 2 turns; verbatim no-curve line.
        self.assertIn("2 assistant turn(s).", out)
        self.assertIn("session-average weight: 21,000", out)
        self.assertIn(cw.COPILOT_NO_CURVE_LINE, out)

        # Audit: 500/300/200 est. tokens = 10%/6%/4%; reframe ~= 6% (1000 of 17000).
        self.assertIn("| CLAUDE.md | present | 2,000 | 500 est. | 10% |", out)
        self.assertIn("| AGENTS.md | present | 1,200 | 300 est. | 6% |", out)
        self.assertIn(
            "| .github/copilot-instructions.md | present | 800 | 200 est. | 4% |", out
        )
        self.assertIn("resident surfaces ≈ 6% of this session's avg per-call weight", out)
        self.assertIn("(1,000 of 17,000 tokens)", out)
        self.assertIn(cw.AUDIT_UNMEASURABLE_LINE, out)

        # All four honesty labels present: est., measured, inferred, and both verbatim
        # not-available lines.
        self.assertIn("est.", out)
        self.assertIn("measured", out)
        self.assertIn("inferred", out)
        self.assertIn(cw.CODEX_NO_PROVENANCE_LINE, out)
        self.assertIn(cw.COPILOT_NO_CURVE_LINE, out)

        # Header names it a synthetic smoke touching no real data.
        self.assertIn("Synthetic", out)

    def test_json_round_trip_and_pinned_numbers(self):
        rc, out = _run_main(["demo", "--json"])
        self.assertEqual(rc, 0)
        data = json.loads(out)  # must round-trip through json.loads.

        self.assertEqual(data["schema_version"], cw.CW_SCHEMA_VERSION)
        self.assertTrue(data["demo"])

        claude = data["claude"]
        self.assertEqual([r["weight"] for r in claude["table_rows"]], [10000, 20000, 30000, 8000])
        self.assertEqual(claude["avg_weight"], 17000)
        self.assertEqual(claude["peak_weight"], 30000)
        self.assertEqual(claude["total_submitted"], 68000)
        self.assertEqual(claude["sidechain"], {"calls": 1, "weight": 5000})
        attribution = claude["attribution"]
        self.assertEqual(attribution["measured_growth"], 20000)
        self.assertEqual(attribution["attributed_total"], 7000)
        self.assertEqual(attribution["assistant_output_measured"], 750)
        self.assertEqual(attribution["unattributed"], 12250)

        codex = data["codex"]
        self.assertEqual([r["weight"] for r in codex["table_rows"]], [3000, 8000, 13000])
        self.assertEqual(codex["avg_weight"], 8000)
        self.assertEqual(codex["attribution"]["provenance_note"], cw.CODEX_NO_PROVENANCE_LINE)

        copilot = data["copilot"]
        self.assertEqual(copilot["turns"], 2)
        self.assertEqual(copilot["session_average_weight"], 21000)
        self.assertEqual(copilot["no_curve_line"], cw.COPILOT_NO_CURVE_LINE)

        audit = data["audit"]
        self.assertEqual(audit["sections"]["claude"]["surfaces"][0]["est_tokens"], 500)
        self.assertEqual(audit["sections"]["codex"]["surfaces"][0]["est_tokens"], 300)
        copilot_surfaces = {s["path"]: s["est_tokens"] for s in audit["sections"]["copilot"]["surfaces"]}
        self.assertEqual(copilot_surfaces[".github/copilot-instructions.md"], 200)
        self.assertEqual(audit["reframe"]["pct"], 6)
        self.assertEqual(audit["reframe"]["avg_weight"], 17000)

        # Paths embedded in the JSON point into a temp dir that is gone by the time this
        # process resumes — proves the fixtures were built and torn down inside `demo`, not
        # left lying around.
        self.assertFalse(Path(audit["project_dir"]).exists())
        self.assertFalse(Path(codex["rollout_file"]).exists())

    def test_no_real_home_path_referenced(self):
        # `demo` never overrides --projects-dir/--codex-home/--copilot-home because it never
        # needs to — it builds its own homes inside a temp dir. Proving no real home was ever
        # touched: none of the engine's own resolved DEFAULT_* home paths (module attributes,
        # already computed at import time — reading them is not a `Path.home()` CALL in this
        # file, which the kit guardrail requires to stay at zero) appear anywhere in the
        # printed cards, whose paths all point inside the demo's own throwaway temp dir.
        rc, out = _run_main(["demo"])
        self.assertEqual(rc, 0)
        self.assertNotIn(str(cw.DEFAULT_PROJECTS_DIR), out)
        self.assertNotIn(str(cw.DEFAULT_CODEX_HOME), out)
        self.assertNotIn(str(cw.DEFAULT_COPILOT_HOME), out)

    def test_takes_no_home_override_flags(self):
        # `demo`'s argparser exposes only --json — confirms it cannot be pointed at a real home
        # even by accident.
        ap = cw.build_parser()
        demo_actions = {a.dest for sub in ap._subparsers._group_actions
                        for choice, sub_ap in sub.choices.items() if choice == "demo"
                        for a in sub_ap._actions}
        self.assertEqual(demo_actions - {"help"}, {"json"})

    def test_constraints_sections_present_for_both_synthetic_sessions(self):
        # U2 acceptance: demo shows a residency section on a session containing guardrails
        # content AND one lacking it.
        rc, out = _run_main(["demo"])
        self.assertEqual(rc, 0)
        self.assertIn("Context weight — constraints demo-constraints-with", out)
        self.assertIn("resident: YES — 100 est. tokens", out)
        self.assertIn("Weight trend across the growth curve (est.)", out)

        self.assertIn("Context weight — constraints demo-constraints-without", out)
        self.assertIn(
            "no read of", out
        )
        self.assertIn("GUARDRAILS.md content for this kit was never loaded into context", out)

    def test_constraints_json_pinned_numbers(self):
        rc, out = _run_main(["demo", "--json"])
        self.assertEqual(rc, 0)
        data = json.loads(out)

        with_card = data["constraints_with_guardrails"]
        self.assertTrue(with_card["resident"])
        self.assertEqual(with_card["reads"], 1)
        self.assertEqual(with_card["current_weight_est_tokens"], 100)
        self.assertEqual(with_card["weight_label"], "est.")

        without_card = data["constraints_without_guardrails"]
        self.assertFalse(without_card["resident"])
        self.assertEqual(without_card["reads"], 0)
        self.assertIsNone(without_card["current_weight_est_tokens"])
        self.assertIsNotNone(without_card["not_found_line"])


# ---- 5. read-only proof -------------------------------------------------------------------------


class ReadOnlyTests(unittest.TestCase):
    def test_fixture_tree_unchanged_after_a_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_id = _first_sonnet_model()
            projects_dir = Path(tmp) / "projects"
            _write_claude_fixture(projects_dir, model_id)

            before = _snapshot_tree(tmp)
            _run_main(
                ["session", "--harness", "claude", "--projects-dir", str(projects_dir), "--json"]
            )
            after = _snapshot_tree(tmp)
            self.assertEqual(before, after)


# ---- 6. attribute_growth (T2, PLAN D4) ---------------------------------------------------------


class AttributeGrowthTests(unittest.TestCase):
    def setUp(self):
        self.model_id = _first_sonnet_model()
        self.objs = _claude_fixture_records(self.model_id)

    def test_bash_and_read_entries_pinned_and_ranked(self):
        entries, notes = cw.attribute_growth(self.objs)
        by_tool = {e["tool"]: e for e in entries}
        self.assertEqual(by_tool["Bash"]["est_tokens"], 5000)      # 20000 chars / 4
        self.assertEqual(by_tool["Read"]["est_tokens"], 2000)      # 8000 chars / 4
        self.assertEqual(by_tool["Read"]["salient"], "/workspace/demo.txt")
        tools_in_order = [e["tool"] for e in entries]
        self.assertLess(tools_in_order.index("Bash"), tools_in_order.index("Read"))
        self.assertEqual(notes, [])

    def test_measured_growth_and_unattributed_reconciliation(self):
        entries, _notes = cw.attribute_growth(self.objs)
        calls, _sidechain, _cw_notes = cw.claude_call_weights(self.objs)
        drops = cw.detect_drops([c["weight"] for c in calls])
        recon = cw._reconcile_growth(calls, drops, entries)
        self.assertEqual(recon["measured_growth"], 20000)   # 8000 - 10000 + 22000
        self.assertEqual(recon["attributed_total"], 7000)   # 5000 + 2000
        # T13: assistant output (measured) = summed `output` of the 4 main calls (200 + 300 +
        # 150 + 100 = 750), an EXACT output_tokens sum — not a byte estimate.
        self.assertEqual(recon["assistant_output_measured"], 750)
        self.assertEqual(recon["unattributed"], 12250)      # 20000 - 7000 - 750
        self.assertFalse(recon["attribution_exceeded_growth"])

    def test_unmapped_tool_use_id_lands_in_unknown(self):
        stray = {
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "toolu_ghost",
                             "content": "z" * 400}],
            },
        }
        entries, notes = cw.attribute_growth([self.objs[0], stray])
        unknown = [e for e in entries if e["tool"] == "(unknown)"]
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0]["est_tokens"], 100)  # 400 chars / 4
        self.assertEqual(notes, [{"kind": "unmapped_tool_use_id", "tool_use_id": "toolu_ghost"}])

    def test_dict_content_tool_result_sized_via_json_serialization(self):
        payload = {"a": "b" * 100}
        stray = {
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "toolu_d1",
                             "content": payload}],
            },
        }
        entries, _notes = cw.attribute_growth([self.objs[0], stray])
        expected_tokens = round(len(json.dumps(payload)) / cw.EST_CHARS_PER_TOKEN)
        by_tool = {e["tool"]: e for e in entries}
        self.assertEqual(by_tool["Bash"]["est_tokens"], expected_tokens)

    def test_sidechain_content_excluded(self):
        sidechain_assistant = _assistant_record(
            "msc", self.model_id, 100, 0, 0, 10, 10,
            tool_use={"id": "toolu_side", "name": "Bash", "input": {"command": "echo hi"}},
            is_sidechain=True,
        )
        sidechain_result = {
            "type": "user",
            "isSidechain": True,
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "toolu_side",
                             "content": "s" * 4000}],
            },
        }
        entries, notes = cw.attribute_growth(
            self.objs + [sidechain_assistant, sidechain_result]
        )
        by_tool = {e["tool"]: e for e in entries}
        # Sidechain content never entered the main window: the Bash bucket must be exactly the
        # T1-fixture figure, not inflated by the 4000-char sidechain tool_result, and no
        # unmapped-id note should have been raised for it either (the record was skipped
        # wholesale before the mapping lookup ever ran).
        self.assertEqual(by_tool["Bash"]["est_tokens"], 5000)
        self.assertEqual(notes, [])

    def test_plain_user_text_attributed_to_user_input(self):
        text_turn = {
            "type": "user",
            "message": {"content": [{"type": "text", "text": "t" * 40}]},
        }
        entries, _notes = cw.attribute_growth([text_turn])
        by_tool = {e["tool"]: e for e in entries}
        self.assertIn("user input", by_tool)
        self.assertEqual(by_tool["user input"]["est_tokens"], 10)  # 40 chars / 4

    def test_attachment_record_attributed_to_attachment(self):
        rec = {"type": "attachment", "attachment": "a" * 80}
        entries, _notes = cw.attribute_growth([rec])
        by_tool = {e["tool"]: e for e in entries}
        self.assertIn("attachment", by_tool)
        self.assertEqual(by_tool["attachment"]["est_tokens"], 20)  # 80 chars / 4


# ---- 7. attribution rendered into the session card (T2) ---------------------------------------


def _attributed_card():
    model_id = _first_sonnet_model()
    objs = _claude_fixture_records(model_id)
    calls, sidechain, notes = cw.claude_call_weights(objs)
    drops = cw.detect_drops([c["weight"] for c in calls])
    entries, attr_notes = cw.attribute_growth(objs)
    pricing = cw.cr.load_pricing()
    return cw.build_session_card(
        "sess", ["one-file"], calls, sidechain, notes, drops, pricing,
        attribution_entries=entries, attribution_notes=attr_notes,
    )


class AttributionCardTests(unittest.TestCase):
    def test_json_attribution_section_pinned_numbers(self):
        card = _attributed_card()
        attribution = card["attribution"]
        self.assertEqual(attribution["measured_growth"], 20000)
        self.assertEqual(attribution["attributed_total"], 7000)
        # T13: assistant output (measured) is exact (summed output_tokens), not an est.
        self.assertEqual(attribution["assistant_output_measured"], 750)
        self.assertEqual(attribution["unattributed"], 12250)
        self.assertEqual(attribution["basis"], "bytes/4 heuristic — never priced")
        tools = [e["tool"] for e in attribution["entries"]]
        self.assertLess(tools.index("Bash"), tools.index("Read"))

    def test_assistant_output_row_present_and_labeled_measured(self):
        card = _attributed_card()
        entries = card["attribution"]["entries"]
        rows = {e["tool"]: e for e in entries}
        self.assertIn(cw.ASSISTANT_OUTPUT_LABEL, rows)
        row = rows[cw.ASSISTANT_OUTPUT_LABEL]
        self.assertEqual(row["tokens"], 750)
        self.assertEqual(row["label"], "measured")
        # every other row (est. tool attribution + the unattributed remainder) stays "est."
        for tool, e in rows.items():
            if tool != cw.ASSISTANT_OUTPUT_LABEL:
                self.assertEqual(e["label"], "est.")

    def test_assistant_output_and_unattributed_ranked_inline_by_size(self):
        # T13 acceptance: unattributed (12250) > Bash (5000) > Read (2000) >
        # assistant output measured (750). The unattributed row must be POSITIONED by that
        # magnitude (first, since it is largest) rather than always printed last, and it must
        # keep a non-numeric "—" rank marker; the measured row gets a real inline rank.
        card = _attributed_card()
        entries = card["attribution"]["entries"]
        tokens_in_order = [e["tokens"] for e in entries]
        self.assertEqual(tokens_in_order, sorted(tokens_in_order, reverse=True))

        by_tool = {e["tool"]: e for e in entries}
        self.assertEqual(by_tool["unattributed growth"]["rank"], "—")
        self.assertEqual(by_tool["unattributed growth"]["tokens"], 12250)
        # Largest row overall -> first in the ranked list.
        self.assertEqual(entries[0]["tool"], "unattributed growth")

        measured_row = by_tool[cw.ASSISTANT_OUTPUT_LABEL]
        self.assertIsInstance(measured_row["rank"], int)
        # Smallest row overall (750) -> last in the ranked list.
        self.assertEqual(entries[-1]["tool"], cw.ASSISTANT_OUTPUT_LABEL)

    def test_est_label_present_in_rendered_output(self):
        md = cw.render_session_markdown(_attributed_card())
        self.assertIn("est.", md)
        self.assertIn("What filled the window (est.)", md)
        self.assertIn("unattributed growth", md)
        self.assertIn(cw.ASSISTANT_OUTPUT_LABEL, md)
        self.assertIn("measured", md)

    def test_corrected_unattributed_explanation_line_present(self):
        md = cw.render_session_markdown(_attributed_card())
        self.assertIn(
            "system overhead and tool schemas are not measurable from the transcript", md
        )
        self.assertIn(
            "assistant output (including thinking) is measured exactly and shown above", md
        )
        self.assertNotIn("thinking, and tool schemas are not measurable", md)

    def test_attribution_section_has_no_dollar_sign(self):
        md = cw.render_session_markdown(_attributed_card())
        section = md.split("## What filled the window (est.)")[1]
        section = section.split("\ncontext carry cost:")[0]
        self.assertNotIn("$", section)

    def test_card_without_attribution_args_omits_attribution_key(self):
        # T1's exact (pre-T2) call shape must still produce a card with no "attribution" key.
        model_id = _first_sonnet_model()
        objs = _claude_fixture_records(model_id)
        calls, sidechain, notes = cw.claude_call_weights(objs)
        drops = cw.detect_drops([c["weight"] for c in calls])
        pricing = cw.cr.load_pricing()
        card = cw.build_session_card(
            "sess", ["one-file"], calls, sidechain, notes, drops, pricing
        )
        self.assertNotIn("attribution", card)


# ---- 7b. avoidable-mass denominator regression (T10 review fix) --------------------------------
#
# The line's first cut divided by `total_submitted` (the CUMULATIVE sum of every call's fully
# resubmitted window) instead of a window-scale quantity (a single call's resident content).
# On a long session total_submitted runs 100x+ larger than any one call's weight, so that
# division silently rounded real, actionable avoidable mass down to "0%" -- recreating the exact
# "nothing to do" reading the line exists to prevent. This fixture reproduces that failure mode
# on purpose (cumulative >> peak) and proves the fixed line does NOT reproduce it.


class AvoidableMassDenominatorTests(unittest.TestCase):
    def test_denominator_is_window_scale_not_cumulative_total_submitted(self):
        model_id = _first_sonnet_model()
        records = [
            # One call carries the peak weight (5000) AND a sizeable Bash tool_result --
            # 4000 chars -> 1000 est. tokens of genuinely avoidable, tool-ingested mass.
            _assistant_record(
                "peak", model_id, 5000, 0, 0, 10, 0,
                tool_use={"id": "tu_big", "name": "Bash", "input": {"command": "cat big.log"}},
            ),
            _user_tool_result("tu_big", "z" * 4000, 1),
        ]
        # Many small calls to inflate the CUMULATIVE total_submitted far past the peak/
        # window-scale mass -- >100x, per the coordinator's regression requirement.
        n_small = 700
        for i in range(n_small):
            records.append(_assistant_record(f"m{i}", model_id, 800, 0, 0, 5, i + 2))

        calls, sidechain, notes = cw.claude_call_weights(records)
        drops = cw.detect_drops([c["weight"] for c in calls])
        entries, attr_notes = cw.attribute_growth(records)
        pricing = cw.cr.load_pricing()
        card = cw.build_session_card(
            "sess", ["one-file"], calls, sidechain, notes, drops, pricing,
            attribution_entries=entries, attribution_notes=attr_notes,
        )
        attribution = card["attribution"]
        total_submitted = card["total_submitted"]
        peak_weight = card["peak_weight"]
        avoidable = attribution["avoidable_tool_ingested_est_tokens"]

        # Fixture sanity: cumulative total_submitted really is >100x the window-scale mass.
        self.assertGreater(total_submitted, peak_weight * 100)
        self.assertEqual(avoidable, 1000)

        # Proves this fixture reproduces the original failure mode: dividing by
        # total_submitted (the bug) rounds the percentage to 0%.
        buggy_pct = round(avoidable / total_submitted * 100)
        self.assertEqual(buggy_pct, 0)

        # The fix: the reported percentage must be window-scale, non-zero, and actionable --
        # and must NOT equal the (bugged) cumulative-denominator calculation.
        self.assertEqual(attribution["avoidable_of_window_content"], peak_weight)
        self.assertNotEqual(attribution["avoidable_of_window_content"], total_submitted)
        self.assertGreater(attribution["avoidable_pct"], 1)
        self.assertNotAlmostEqual(
            attribution["avoidable_pct"], avoidable / total_submitted * 100, places=3
        )

        # The rendered line itself must carry the non-zero percentage, not "(0%)".
        md = cw.render_session_markdown(card)
        self.assertIn("avoidable (tool-ingested) mass:", md)
        avoidable_line = md.split("avoidable (tool-ingested) mass:")[1].splitlines()[0]
        self.assertIn(f"{peak_weight:,}", avoidable_line)
        self.assertNotIn(f"{total_submitted:,}", avoidable_line)
        self.assertNotIn("(0%)", avoidable_line)


# ---- 8. CLI end-to-end includes attribution (T2) -----------------------------------------------


class AttributionCliTests(unittest.TestCase):
    def test_session_json_includes_attribution_pinned_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_id = _first_sonnet_model()
            projects_dir = Path(tmp) / "projects"
            _write_claude_fixture(projects_dir, model_id)

            rc, out = _run_main(
                ["session", "--harness", "claude", "--projects-dir", str(projects_dir), "--json"]
            )
            self.assertEqual(rc, 0)
            data = json.loads(out)
            attribution = data["attribution"]
            self.assertEqual(attribution["measured_growth"], 20000)
            self.assertEqual(attribution["assistant_output_measured"], 750)
            self.assertEqual(attribution["unattributed"], 12250)
            tools = [e["tool"] for e in attribution["entries"]]
            self.assertLess(tools.index("Bash"), tools.index("Read"))
            self.assertIn(cw.ASSISTANT_OUTPUT_LABEL, tools)
            # T1's pinned numbers must be untouched by this extension.
            self.assertEqual(data["calls"], 4)
            self.assertEqual(data["avg_weight"], 17000)
            self.assertEqual(data["peak_weight"], 30000)
            self.assertEqual(data["total_submitted"], 68000)
            self.assertEqual(data["sidechain"], {"calls": 1, "weight": 5000})


# ---- 9. Codex session mode (T3, PLAN D3 Codex rung — curve, NEVER content attribution) ---------
#
# Fixture idioms reproduced LOCALLY (not imported) from tests/test_codex_usage.py's
# `_tok_rec`/`_model_rec`/`_write_rollout`, per the T3 brief.


def _first_codex_model():
    pricing = cw.cx.load_pricing()
    return next(iter(pricing["models"]))


def _codex_tok_rec(container_key, **fields):
    """A rollout token record nested under payload.info, exercising the chained wrapper
    descent (mirrors tests/test_codex_usage.py's `_tok_rec` shape)."""
    return {"type": "event_msg", "payload": {"info": {container_key: dict(fields)}}}


def _codex_model_rec(model):
    return {"type": "turn_context", "payload": {"model": model}}


def _codex_lines(records):
    return [json.dumps(r) for r in records]


def _write_codex_rollout(codex_home, records, when=None, name="rollout-x.jsonl"):
    """Write one rollout .jsonl under sessions/YYYY/MM/DD/ for `when` (default now)."""
    when = when or datetime.now(timezone.utc)
    d = Path(codex_home) / "sessions" / f"{when:%Y}" / f"{when:%m}" / f"{when:%d}"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text("\n".join(_codex_lines(records)) + "\n")
    return p


def _codex_fixture_records(model):
    """The exact pinned T3 fixture (also T7's demo fixture): one turn_context record, then
    three per-turn `last_token_usage` containers -> weights [3000, 8000, 13000], avg 8000,
    kind "per-turn". T7 MOVED this builder into the engine as ``cw.demo_codex_fixture_records``
    (the one sanctioned test-file refactor); this wrapper re-points every existing call site at
    that engine copy."""
    return cw.demo_codex_fixture_records(model)


class CodexCurveTests(unittest.TestCase):
    def test_per_turn_pinned_weights_and_kind(self):
        model = _first_codex_model()
        lines = _codex_lines(_codex_fixture_records(model))
        points, kind, notes = cw.codex_curve(lines)
        self.assertEqual(points, [3000, 8000, 13000])
        self.assertEqual(kind, "per-turn")
        self.assertEqual(round(sum(points) / len(points)), 8000)
        self.assertEqual(notes, [])

    def test_cumulative_only_fixture_yields_cumulative_snapshots_kind(self):
        records = [
            _codex_tok_rec("total_token_usage", input_tokens=1000, cached_input_tokens=0,
                            output_tokens=10),
            _codex_tok_rec("total_token_usage", input_tokens=3000, cached_input_tokens=2000,
                            output_tokens=30),
        ]
        points, kind, notes = cw.codex_curve(_codex_lines(records))
        self.assertEqual(points, [1000, 5000])  # per-snapshot, in order, not maxed
        self.assertEqual(kind, "cumulative snapshots")
        self.assertEqual(notes, [])

    def test_mixed_container_kinds_uses_per_turn_only(self):
        records = [
            _codex_tok_rec("total_token_usage", input_tokens=999, cached_input_tokens=999,
                            output_tokens=999),
            _codex_tok_rec("last_token_usage", input_tokens=100, cached_input_tokens=50,
                            output_tokens=5),
            _codex_tok_rec("last_token_usage", input_tokens=200, cached_input_tokens=50,
                            output_tokens=5),
        ]
        points, kind, notes = cw.codex_curve(_codex_lines(records))
        self.assertEqual(points, [150, 250])  # only the per-turn containers, cumulative ignored
        self.assertEqual(kind, "per-turn")

    def test_no_token_rollout_yields_no_curve_and_honesty_note(self):
        records = [_codex_model_rec("some-model")]
        points, kind, notes = cw.codex_curve(_codex_lines(records))
        self.assertEqual(points, [])
        self.assertIsNone(kind)
        self.assertEqual(notes, [cw.cx.UNPRICED_NOTE])


class CodexByteShareTests(unittest.TestCase):
    def test_rows_labeled_est_and_carry_no_dollar_sign(self):
        model = _first_codex_model()
        lines = _codex_lines(_codex_fixture_records(model))
        rows, total_bytes = cw.codex_byte_share(lines)
        self.assertGreater(total_bytes, 0)
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["label"], "est.")
            self.assertNotIn("$", json.dumps(row))
            self.assertNotIn("file_path", row)
            self.assertNotIn("path", row)
        types = {row["type"] for row in rows}
        self.assertEqual(types, {"turn_context", "event_msg"})

    def test_malformed_lines_skipped_not_raised(self):
        rows, total_bytes = cw.codex_byte_share(["not json {{{", "", "   "])
        self.assertEqual(rows, [])
        self.assertEqual(total_bytes, 0)


class CodexCardTests(unittest.TestCase):
    def test_card_pinned_numbers_and_no_provenance_line(self):
        model = _first_codex_model()
        lines = _codex_lines(_codex_fixture_records(model))
        pricing = cw.cx.load_pricing()
        card = cw.build_codex_session_card("sess", "rollout.jsonl", lines, pricing)
        self.assertEqual(card["calls"], 3)
        self.assertEqual(card["curve_kind"], "per-turn")
        self.assertEqual([r["weight"] for r in card["table_rows"]], [3000, 8000, 13000])
        self.assertEqual(card["avg_weight"], 8000)
        self.assertEqual(card["peak_weight"], 13000)
        self.assertEqual(
            card["attribution"]["provenance_note"], cw.CODEX_NO_PROVENANCE_LINE
        )
        self.assertEqual(
            cw.CODEX_NO_PROVENANCE_LINE,
            "provenance not recorded in these logs — byte-share of rollout record types "
            "shown as a labeled estimate",
        )

    def test_card_never_carries_a_ranked_attribution_entries_key(self):
        # The single most important constraint in T3: no content-attribution table, ever.
        model = _first_codex_model()
        lines = _codex_lines(_codex_fixture_records(model))
        pricing = cw.cx.load_pricing()
        card = cw.build_codex_session_card("sess", "rollout.jsonl", lines, pricing)
        self.assertNotIn("entries", card["attribution"])
        self.assertNotIn("salient", json.dumps(card["attribution"]))
        self.assertFalse(hasattr(cw, "attribute_growth_codex"))

    def test_carry_cost_matches_hand_computation_output_zeroed(self):
        model = _first_codex_model()
        lines = _codex_lines(_codex_fixture_records(model))
        pricing = cw.cx.load_pricing()
        card = cw.build_codex_session_card("sess", "rollout.jsonl", lines, pricing)

        parsed = cw.cx.parse_rollout(lines)
        zeroed = dict(parsed["tokens"])
        zeroed["output"] = 0
        expected_carry = cw.cx.price_tokens(zeroed, model, pricing)

        self.assertIsNotNone(card["carry_cost"])
        self.assertAlmostEqual(card["carry_cost"]["carry_usd"], expected_carry, places=9)
        self.assertEqual(card["carry_cost"]["disclaimer"], cw.cx.PROXY_DISCLAIMER)


class CodexRenderTests(unittest.TestCase):
    def _card(self):
        model = _first_codex_model()
        lines = _codex_lines(_codex_fixture_records(model))
        pricing = cw.cx.load_pricing()
        return cw.build_codex_session_card("sess", "rollout.jsonl", lines, pricing)

    def test_markdown_carries_verbatim_no_provenance_line(self):
        md = cw.render_codex_session_markdown(self._card())
        self.assertIn(cw.CODEX_NO_PROVENANCE_LINE, md)
        self.assertIn(cw.cx.PROXY_DISCLAIMER, md)

    def test_provenance_section_has_no_dollar_sign(self):
        md = cw.render_codex_session_markdown(self._card())
        # Bound the section to the Provenance heading through end-of-string (no next heading
        # follows it here) — per NOTES.md instrument #3, never sweep past the section boundary.
        section = md.split("## Provenance (est.)")[1]
        self.assertNotIn("$", section)
        self.assertIn("est.", section)

    def test_no_token_rollout_renders_activity_only_line(self):
        records = [_codex_model_rec("some-model")]
        lines = _codex_lines(records)
        pricing = cw.cx.load_pricing()
        card = cw.build_codex_session_card("sess", "rollout.jsonl", lines, pricing)
        md = cw.render_codex_session_markdown(card)
        self.assertIn(cw.cx.UNPRICED_NOTE, md)
        self.assertIsNone(card["curve_kind"])


# ---- 10. Codex CLI end-to-end (T3) ---------------------------------------------------------------


class CodexCliEndToEndTests(unittest.TestCase):
    def test_session_json_pinned_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _first_codex_model()
            codex_home = Path(tmp) / "codex-home"
            _write_codex_rollout(codex_home, _codex_fixture_records(model))

            rc, out = _run_main(
                ["session", "--harness", "codex", "--codex-home", str(codex_home), "--json"]
            )
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertTrue(data["found"])
            self.assertEqual(data["harness"], "codex")
            self.assertEqual(data["calls"], 3)
            self.assertEqual(data["curve_kind"], "per-turn")
            self.assertEqual([r["weight"] for r in data["table_rows"]], [3000, 8000, 13000])
            self.assertEqual(data["avg_weight"], 8000)
            self.assertNotIn("entries", data["attribution"])

    def test_session_markdown_carries_no_provenance_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _first_codex_model()
            codex_home = Path(tmp) / "codex-home"
            _write_codex_rollout(codex_home, _codex_fixture_records(model))

            rc, out = _run_main(
                ["session", "--harness", "codex", "--codex-home", str(codex_home)]
            )
            self.assertEqual(rc, 0)
            self.assertIn(cw.CODEX_NO_PROVENANCE_LINE, out)
            self.assertIn("est.", out)

    def test_absent_codex_home_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            nowhere = Path(tmp) / "does-not-exist"
            rc, out = _run_main(
                ["session", "--harness", "codex", "--codex-home", str(nowhere), "--json"]
            )
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertFalse(data["found"])

    def test_empty_sessions_dir_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            (codex_home / "sessions").mkdir(parents=True)
            rc, out = _run_main(
                ["session", "--harness", "codex", "--codex-home", str(codex_home)]
            )
            self.assertEqual(rc, 0)
            self.assertIn("No codex", out)

    def test_session_id_filter_by_filename_stem(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _first_codex_model()
            codex_home = Path(tmp) / "codex-home"
            _write_codex_rollout(codex_home, _codex_fixture_records(model), name="target.jsonl")
            _write_codex_rollout(
                codex_home,
                [_codex_model_rec(model),
                 _codex_tok_rec("last_token_usage", input_tokens=1, output_tokens=1)],
                name="other.jsonl",
            )
            rc, out = _run_main(
                ["session", "--harness", "codex", "--codex-home", str(codex_home),
                 "--session", "target", "--json"]
            )
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertTrue(data["found"])
            self.assertIn("target.jsonl", data["rollout_file"])
            self.assertEqual(data["calls"], 3)

    def test_session_id_filter_by_discovered_session_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            records = [{"type": "session_meta", "session_id": "abc-123"}] + \
                _codex_fixture_records(_first_codex_model())
            _write_codex_rollout(codex_home, records, name="some-file.jsonl")
            rc, out = _run_main(
                ["session", "--harness", "codex", "--codex-home", str(codex_home),
                 "--session", "abc-123", "--json"]
            )
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertTrue(data["found"])
            self.assertIn("some-file.jsonl", data["rollout_file"])

    def test_no_token_rollout_cli_renders_activity_only_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            _write_codex_rollout(codex_home, [_codex_model_rec("some-model")])
            rc, out = _run_main(
                ["session", "--harness", "codex", "--codex-home", str(codex_home)]
            )
            self.assertEqual(rc, 0)
            self.assertIn(cw.cx.UNPRICED_NOTE, out)


class CodexReadOnlyTests(unittest.TestCase):
    def test_fixture_tree_unchanged_after_a_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _first_codex_model()
            codex_home = Path(tmp) / "codex-home"
            _write_codex_rollout(codex_home, _codex_fixture_records(model))

            before = _snapshot_tree(tmp)
            _run_main(
                ["session", "--harness", "codex", "--codex-home", str(codex_home), "--json"]
            )
            after = _snapshot_tree(tmp)
            self.assertEqual(before, after)


# ---- 11. Copilot session mode (T4, PLAN D3 Copilot rung — session-average, NEVER a curve) -----
#
# `_ev`/`_td` idioms reproduced LOCALLY (not imported) from tests/test_copilot_usage.py, per the
# T4 brief.


def _copilot_ev(etype, ts, **data):
    return json.dumps({"type": etype, "timestamp": ts, "data": data})


def _copilot_td(input_count, cache_read, cache_write, output_count):
    return {
        "input": {"tokenCount": input_count},
        "cache_read": {"tokenCount": cache_read},
        "cache_write": {"tokenCount": cache_write},
        "output": {"tokenCount": output_count},
    }


def _first_copilot_model():
    pricing = cw.cp.load_pricing()
    return next(iter(pricing["models"]))


def _copilot_fixture_lines(model):
    """The exact pinned T4 fixture (also T7's demo fixture): two assistant.message events
    (outputTokens 100 and 200, distinct apiCallIds) + one session.shutdown with
    tokenDetails = _td(10000, 30000, 2000, 300) -> turns 2, session-average weight 21000
    (= (10000 + 30000 + 2000) // 2). T7 MOVED this builder into the engine as
    ``cw.demo_copilot_fixture_lines`` (the one sanctioned test-file refactor); this wrapper
    re-points every existing call site at that engine copy."""
    return cw.demo_copilot_fixture_lines(model)


def _write_copilot_fixture(copilot_home, model, session_id="copilot-sess-1"):
    d = Path(copilot_home) / "session-state" / session_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "events.jsonl").write_text("\n".join(_copilot_fixture_lines(model)) + "\n")
    return d / "events.jsonl"


class CopilotSessionCardTests(unittest.TestCase):
    def test_pinned_session_average_and_turns(self):
        model = _first_copilot_model()
        parsed = cw.cp.parse_events(_copilot_fixture_lines(model))
        pricing = cw.cp.load_pricing()
        card = cw.copilot_session_card(parsed, pricing, session_id="sess")
        self.assertEqual(card["turns"], 2)
        self.assertEqual(card["session_average_weight"], 21000)
        self.assertEqual(card["session_average_label"], "session-average")

    def test_verbatim_no_curve_line_byte_exact(self):
        self.assertEqual(
            cw.COPILOT_NO_CURVE_LINE,
            "growth curve: not available — Copilot events do not record per-turn "
            "input/cache token splits",
        )
        model = _first_copilot_model()
        parsed = cw.cp.parse_events(_copilot_fixture_lines(model))
        pricing = cw.cp.load_pricing()
        card = cw.copilot_session_card(parsed, pricing, session_id="sess")
        self.assertEqual(card["no_curve_line"], cw.COPILOT_NO_CURVE_LINE)
        md = cw.render_copilot_session_markdown(card)
        self.assertIn(cw.COPILOT_NO_CURVE_LINE, md)

    def test_no_attribution_key_and_no_codex_curve_reuse(self):
        # The single most important constraint in T4: no growth curve, no content-attribution
        # table, ever — and no reuse of T3's codex_curve or T2's attribute_growth here.
        model = _first_copilot_model()
        parsed = cw.cp.parse_events(_copilot_fixture_lines(model))
        pricing = cw.cp.load_pricing()
        card = cw.copilot_session_card(parsed, pricing, session_id="sess")
        self.assertNotIn("attribution", card)
        self.assertNotIn("sparkline", card)
        self.assertNotIn("curve_kind", card)
        self.assertFalse(hasattr(cw, "attribute_growth_copilot"))
        self.assertFalse(hasattr(cw, "copilot_curve"))

    def test_carry_cost_matches_hand_computation_output_zeroed(self):
        model = _first_copilot_model()
        parsed = cw.cp.parse_events(_copilot_fixture_lines(model))
        pricing = cw.cp.load_pricing()
        card = cw.copilot_session_card(parsed, pricing, session_id="sess")

        zeroed = dict(parsed["tokens"])
        zeroed["output"] = 0
        expected_usd = cw.cp.price_tokens(zeroed, model, pricing)
        expected_aic = cw.cp.usd_to_aic(expected_usd, pricing)

        self.assertIsNotNone(card["carry_cost"])
        self.assertAlmostEqual(card["carry_cost"]["carry_usd"], expected_usd, places=9)
        self.assertAlmostEqual(card["carry_cost"]["aic"], expected_aic, places=9)
        self.assertEqual(card["carry_cost"]["label"], cw.CARRY_COST_LABEL)

        md = cw.render_copilot_session_markdown(card)
        self.assertIn("AIC", md)
        self.assertIn(cw.CARRY_COST_LABEL, md)

    def test_multi_model_session_carry_cost_flagged_approx(self):
        pricing = cw.cp.load_pricing()
        model_a, model_b = list(pricing["models"].keys())[:2]
        lines = [
            _copilot_ev("session.start", "2026-06-30T10:00:00Z", selectedModel=model_a),
            _copilot_ev("assistant.message", "2026-06-30T10:01:00Z", model=model_a,
                         outputTokens=50, apiCallId="mm-a1"),
            _copilot_ev("session.model_change", "2026-06-30T10:01:30Z",
                        previousModel=model_a, newModel=model_b),
            _copilot_ev("assistant.message", "2026-06-30T10:02:00Z", model=model_b,
                         outputTokens=60, apiCallId="mm-a2"),
            _copilot_ev("session.shutdown", "2026-06-30T10:03:00Z", totalNanoAiu=1,
                         totalPremiumRequests=1, currentModel=model_b,
                         tokenDetails=_copilot_td(100, 100, 0, 110)),
        ]
        parsed = cw.cp.parse_events(lines)
        card = cw.copilot_session_card(parsed, pricing, session_id="sess")
        self.assertIsNotNone(card["carry_cost"])
        self.assertTrue(card["carry_cost"]["approx"])
        self.assertEqual(card["carry_cost"]["model"], model_b)
        md = cw.render_copilot_session_markdown(card)
        self.assertIn("approx", md)

    def test_no_shutdown_prices_nothing_and_fabricates_nothing(self):
        model = _first_copilot_model()
        lines = [
            _copilot_ev("session.start", "2026-06-30T10:00:00Z", selectedModel=model),
            _copilot_ev("assistant.message", "2026-06-30T10:01:00Z", model=model,
                         outputTokens=50, apiCallId="nc-a1"),
        ]
        parsed = cw.cp.parse_events(lines)
        pricing = cw.cp.load_pricing()
        card = cw.copilot_session_card(parsed, pricing, session_id="sess")
        self.assertFalse(card["tokens_recorded"])
        self.assertIsNone(card["session_average_weight"])
        self.assertIsNone(card["carry_cost"])

        md = cw.render_copilot_session_markdown(card)
        self.assertNotIn("$", md)
        self.assertIn("not recorded", md)
        self.assertIn(cw.COPILOT_NO_CURVE_LINE, md)


# ---- 12. Copilot CLI end-to-end (T4) -------------------------------------------------------


class CopilotCliEndToEndTests(unittest.TestCase):
    def test_session_json_round_trips_pinned_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _first_copilot_model()
            copilot_home = Path(tmp) / "copilot-home"
            _write_copilot_fixture(copilot_home, model)

            rc, out = _run_main(
                ["session", "--harness", "copilot", "--copilot-home", str(copilot_home), "--json"]
            )
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertTrue(data["found"])
            self.assertEqual(data["harness"], "copilot")
            self.assertEqual(data["schema_version"], cw.CW_SCHEMA_VERSION)
            self.assertEqual(data["turns"], 2)
            self.assertEqual(data["session_average_weight"], 21000)
            self.assertEqual(data["no_curve_line"], cw.COPILOT_NO_CURVE_LINE)
            self.assertNotIn("attribution", data)
            self.assertIn("carry_cost", data)
            self.assertEqual(data["carry_cost"]["label"], cw.CARRY_COST_LABEL)

    def test_session_markdown_carries_no_curve_line_and_carry_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _first_copilot_model()
            copilot_home = Path(tmp) / "copilot-home"
            _write_copilot_fixture(copilot_home, model)

            rc, out = _run_main(
                ["session", "--harness", "copilot", "--copilot-home", str(copilot_home)]
            )
            self.assertEqual(rc, 0)
            self.assertIn(cw.COPILOT_NO_CURVE_LINE, out)
            self.assertIn(cw.CARRY_COST_LABEL, out)
            self.assertIn("session-average", out)

    def test_absent_copilot_home_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            nowhere = Path(tmp) / "does-not-exist"
            rc, out = _run_main(
                ["session", "--harness", "copilot", "--copilot-home", str(nowhere), "--json"]
            )
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertFalse(data["found"])
            self.assertIn(str(nowhere), data["message"])

    def test_empty_session_state_dir_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            copilot_home = Path(tmp) / "copilot-home"
            (copilot_home / "session-state").mkdir(parents=True)
            rc, out = _run_main(
                ["session", "--harness", "copilot", "--copilot-home", str(copilot_home)]
            )
            self.assertEqual(rc, 0)
            self.assertIn("No copilot", out)

    def test_session_id_selects_named_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _first_copilot_model()
            copilot_home = Path(tmp) / "copilot-home"
            _write_copilot_fixture(copilot_home, model, session_id="target-sess")
            _write_copilot_fixture(copilot_home, model, session_id="other-sess")

            rc, out = _run_main(
                ["session", "--harness", "copilot", "--copilot-home", str(copilot_home),
                 "--session", "target-sess", "--json"]
            )
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertTrue(data["found"])
            self.assertEqual(data["session_id"], "target-sess")

    def test_unknown_session_id_reports_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _first_copilot_model()
            copilot_home = Path(tmp) / "copilot-home"
            _write_copilot_fixture(copilot_home, model, session_id="only-sess")

            rc, out = _run_main(
                ["session", "--harness", "copilot", "--copilot-home", str(copilot_home),
                 "--session", "no-such-sess", "--json"]
            )
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertFalse(data["found"])


class CopilotReadOnlyTests(unittest.TestCase):
    def test_fixture_tree_unchanged_after_a_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _first_copilot_model()
            copilot_home = Path(tmp) / "copilot-home"
            _write_copilot_fixture(copilot_home, model)

            before = _snapshot_tree(tmp)
            _run_main(
                ["session", "--harness", "copilot", "--copilot-home", str(copilot_home), "--json"]
            )
            after = _snapshot_tree(tmp)
            self.assertEqual(before, after)


# ---- 13. overview (T5) ----------------------------------------------------------------------


def _write_overview_fixtures(tmp):
    """One instance of each harness's pinned rung fixture (T1/T3/T4), written under a shared
    temp root, for the overview cross-harness tests. Returns (projects_dir, codex_home,
    copilot_home)."""
    projects_dir = Path(tmp) / "projects"
    _write_claude_fixture(projects_dir, _first_sonnet_model())
    codex_home = Path(tmp) / "codex-home"
    _write_codex_rollout(codex_home, _codex_fixture_records(_first_codex_model()))
    copilot_home = Path(tmp) / "copilot-home"
    _write_copilot_fixture(copilot_home, _first_copilot_model())
    return projects_dir, codex_home, copilot_home


class OverviewTests(unittest.TestCase):
    def test_pinned_numbers_across_all_three_harnesses(self):
        # The Copilot fixture's events carry FIXED 2026-06-30 timestamps (unlike the Claude/
        # Codex fixture writers, which write "now"); overview filters Copilot sessions by EVENT
        # timestamp (last_seen), mirroring copilot_usage.py's own --days convention, so a wide
        # --days window is needed here to include it. A realistic window is exercised in
        # test_days_filtering_excludes_old_mtime_claude_transcript below.
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir, codex_home, copilot_home = _write_overview_fixtures(tmp)
            rc, out = _run_main([
                "overview", "--harness", "all", "--days", "400",
                "--projects-dir", str(projects_dir), "--codex-home", str(codex_home),
                "--copilot-home", str(copilot_home), "--json",
            ])
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertEqual(data["schema_version"], cw.CW_SCHEMA_VERSION)

            claude = data["sections"]["claude"]
            self.assertTrue(claude["found"])
            self.assertEqual(len(claude["sessions"]), 1)
            row = claude["sessions"][0]
            self.assertEqual(row["calls"], 4)
            self.assertEqual(row["avg_weight"], 17000)
            self.assertEqual(row["inferred_compactions"], 1)

            codex = data["sections"]["codex"]
            self.assertTrue(codex["found"])
            self.assertEqual(len(codex["rollouts"]), 1)
            crow = codex["rollouts"][0]
            self.assertEqual(crow["points"], 3)
            self.assertEqual(crow["avg_weight"], 8000)

            copilot = data["sections"]["copilot"]
            self.assertTrue(copilot["found"])
            self.assertEqual(len(copilot["sessions"]), 1)
            prow = copilot["sessions"][0]
            self.assertEqual(prow["turns"], 2)
            self.assertEqual(prow["session_average_weight"], 21000)

    def test_absent_codex_home_others_still_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp) / "projects"
            _write_claude_fixture(projects_dir, _first_sonnet_model())
            copilot_home = Path(tmp) / "copilot-home"
            _write_copilot_fixture(copilot_home, _first_copilot_model())
            codex_home = Path(tmp) / "no-such-codex-home"

            rc, out = _run_main([
                "overview", "--harness", "all", "--days", "400",
                "--projects-dir", str(projects_dir), "--codex-home", str(codex_home),
                "--copilot-home", str(copilot_home), "--json",
            ])
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertFalse(data["sections"]["codex"]["found"])
            self.assertIn(str(codex_home), data["sections"]["codex"]["message"])
            self.assertIsNone(data["sections"]["codex"]["carry_cost"])
            self.assertTrue(data["sections"]["claude"]["found"])
            self.assertEqual(data["sections"]["claude"]["sessions_scanned"], 1)
            self.assertTrue(data["sections"]["copilot"]["found"])
            self.assertEqual(data["sections"]["copilot"]["sessions_scanned"], 1)

    def test_days_filtering_excludes_old_mtime_claude_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp) / "projects"
            _write_claude_fixture(projects_dir, _first_sonnet_model(),
                                   project="recent-proj", filename="recent.jsonl")
            old_path = _write_claude_fixture(projects_dir, _first_sonnet_model(),
                                              project="old-proj", filename="old.jsonl")
            old_time = (datetime.now(timezone.utc) - timedelta(days=40)).timestamp()
            os.utime(old_path, (old_time, old_time))

            rc, out = _run_main([
                "overview", "--harness", "claude", "--days", "7",
                "--projects-dir", str(projects_dir),
                "--codex-home", str(Path(tmp) / "codex-home"),
                "--copilot-home", str(Path(tmp) / "copilot-home"), "--json",
            ])
            self.assertEqual(rc, 0)
            data = json.loads(out)
            claude = data["sections"]["claude"]
            self.assertEqual(claude["sessions_scanned"], 1)
            self.assertEqual(claude["sessions"][0]["session_id"], "recent")

    def test_json_sections_are_exactly_the_three_harnesses_no_combined_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir, codex_home, copilot_home = _write_overview_fixtures(tmp)
            rc, out = _run_main([
                "overview", "--harness", "all", "--days", "400",
                "--projects-dir", str(projects_dir), "--codex-home", str(codex_home),
                "--copilot-home", str(copilot_home), "--json",
            ])
            data = json.loads(out)
            # No top-level key beyond this pinned set -- in particular no blended/combined
            # dollar field of any kind (D5: the three harnesses' dollars never merge).
            self.assertEqual(set(data.keys()),
                              {"schema_version", "days", "harness_filter", "sections"})
            self.assertEqual(set(data["sections"].keys()), {"claude", "codex", "copilot"})
            for name in ("claude", "codex", "copilot"):
                cc = data["sections"][name]["carry_cost"]
                self.assertIsNotNone(cc)
                self.assertIn("carry_usd", cc)

    def test_harness_claude_renders_only_that_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir, codex_home, copilot_home = _write_overview_fixtures(tmp)
            rc, out = _run_main([
                "overview", "--harness", "claude", "--days", "400",
                "--projects-dir", str(projects_dir), "--codex-home", str(codex_home),
                "--copilot-home", str(copilot_home), "--json",
            ])
            data = json.loads(out)
            self.assertEqual(set(data["sections"].keys()), {"claude"})

            rc2, md = _run_main([
                "overview", "--harness", "claude", "--days", "400",
                "--projects-dir", str(projects_dir), "--codex-home", str(codex_home),
                "--copilot-home", str(copilot_home),
            ])
            self.assertEqual(rc2, 0)
            self.assertIn("## Claude", md)
            self.assertNotIn("## Codex", md)
            self.assertNotIn("## Copilot", md)

    def test_sidechain_only_transcript_gets_a_note_not_a_silent_zero(self):
        # Phase-1 review flagged: a wholly-sidechain transcript renders "0 call(s)" alongside a
        # large sidechain figure, which reads as "nothing happened" unless flagged explicitly.
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp) / "projects"
            model_id = _first_sonnet_model()
            _write_claude_fixture(projects_dir, model_id)
            sidechain_only = [
                _assistant_record("sc1", model_id, 4000, 1000, 0, 50, 6, is_sidechain=True),
            ]
            d = projects_dir / "sidechain-proj"
            d.mkdir(parents=True, exist_ok=True)
            (d / "sidechain-only.jsonl").write_text(
                "\n".join(json.dumps(r) for r in sidechain_only) + "\n"
            )

            rc, out = _run_main([
                "overview", "--harness", "claude", "--days", "7",
                "--projects-dir", str(projects_dir),
                "--codex-home", str(Path(tmp) / "codex-home"),
                "--copilot-home", str(Path(tmp) / "copilot-home"), "--json",
            ])
            self.assertEqual(rc, 0)
            data = json.loads(out)
            rows = {r["session_id"]: r for r in data["sections"]["claude"]["sessions"]}
            self.assertIn("sidechain-only", rows)
            row = rows["sidechain-only"]
            self.assertEqual(row["calls"], 0)
            self.assertEqual(row["sidechain"]["calls"], 1)
            self.assertIn("note", row)
            self.assertIn("sidechain", row["note"])

            rc2, md = _run_main([
                "overview", "--harness", "claude", "--days", "7",
                "--projects-dir", str(projects_dir),
                "--codex-home", str(Path(tmp) / "codex-home"),
                "--copilot-home", str(Path(tmp) / "copilot-home"),
            ])
            self.assertEqual(rc2, 0)
            self.assertIn("sidechain-only", md)
            self.assertIn(row["note"], md)

    def test_codex_no_provenance_and_copilot_no_curve_lines_present_verbatim(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir, codex_home, copilot_home = _write_overview_fixtures(tmp)
            rc, md = _run_main([
                "overview", "--harness", "all", "--days", "400",
                "--projects-dir", str(projects_dir), "--codex-home", str(codex_home),
                "--copilot-home", str(copilot_home),
            ])
            self.assertEqual(rc, 0)
            self.assertIn(cw.CODEX_NO_PROVENANCE_LINE, md)
            self.assertIn(cw.COPILOT_NO_CURVE_LINE, md)
            # Claude's D4 attribution ("what filled the window") never leaks into overview at
            # all -- overview aggregates session summaries, never a ranked content table.
            self.assertNotIn("salient", md)

    def test_no_dollar_figure_sums_carry_cost_across_harnesses(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir, codex_home, copilot_home = _write_overview_fixtures(tmp)
            rc, out = _run_main([
                "overview", "--harness", "all", "--days", "400",
                "--projects-dir", str(projects_dir), "--codex-home", str(codex_home),
                "--copilot-home", str(copilot_home), "--json",
            ])
            data = json.loads(out)
            claude_usd = data["sections"]["claude"]["carry_cost"]["carry_usd"]
            codex_usd = data["sections"]["codex"]["carry_cost"]["carry_usd"]
            copilot_usd = data["sections"]["copilot"]["carry_cost"]["carry_usd"]
            blended = claude_usd + codex_usd + copilot_usd
            # This sum is computed here, by the TEST, purely to prove it never appears anywhere
            # in the tool's own output -- the tool itself must never compute or print it.
            self.assertNotIn(f"{blended:.2f}", out)
            self.assertNotIn(f"{blended:.4f}", out)

    def test_absent_all_three_homes_exits_0_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, out = _run_main([
                "overview", "--harness", "all",
                "--projects-dir", str(Path(tmp) / "nope-projects"),
                "--codex-home", str(Path(tmp) / "nope-codex"),
                "--copilot-home", str(Path(tmp) / "nope-copilot"), "--json",
            ])
            self.assertEqual(rc, 0)
            data = json.loads(out)
            for name in ("claude", "codex", "copilot"):
                self.assertFalse(data["sections"][name]["found"])
                self.assertIsNone(data["sections"][name]["carry_cost"])


class OverviewReadOnlyTests(unittest.TestCase):
    def test_fixture_tree_unchanged_after_a_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir, codex_home, copilot_home = _write_overview_fixtures(tmp)
            before = _snapshot_tree(tmp)
            _run_main([
                "overview", "--harness", "all", "--days", "400",
                "--projects-dir", str(projects_dir), "--codex-home", str(codex_home),
                "--copilot-home", str(copilot_home), "--json",
            ])
            after = _snapshot_tree(tmp)
            self.assertEqual(before, after)


# ---- 8. audit (T6, PLAN D10) ----------------------------------------------------------------


class AuditSurfacesTests(unittest.TestCase):
    def test_pinned_fixture_bytes_and_est_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = _audit_fixture(Path(tmp) / "proj")
            sections, notes = cw.audit_surfaces(project_dir, [], cw.DEFAULT_SURFACE_BUDGET_TOKENS)

            claude_md = next(s for s in sections["claude"]["surfaces"] if s["path"] == "CLAUDE.md")
            self.assertTrue(claude_md["present"])
            self.assertEqual(claude_md["bytes"], 2000)
            self.assertEqual(claude_md["est_tokens"], 500)
            self.assertAlmostEqual(claude_md["pct_budget"], 10.0)

            agents_md = next(s for s in sections["codex"]["surfaces"] if s["path"] == "AGENTS.md")
            self.assertTrue(agents_md["present"])
            self.assertEqual(agents_md["est_tokens"], 300)
            self.assertAlmostEqual(agents_md["pct_budget"], 6.0)

            copilot_instr = next(
                s for s in sections["copilot"]["surfaces"]
                if s["path"] == ".github/copilot-instructions.md"
            )
            self.assertTrue(copilot_instr["present"])
            self.assertEqual(copilot_instr["est_tokens"], 200)
            self.assertAlmostEqual(copilot_instr["pct_budget"], 4.0)

    def test_copilot_section_totals_shared_agents_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = _audit_fixture(Path(tmp) / "proj")
            sections, _ = cw.audit_surfaces(project_dir, [], cw.DEFAULT_SURFACE_BUDGET_TOKENS)
            # copilot-instructions.md (200) + AGENTS.md (300), AGENTS.md counted in full here
            # even though it also appears under "codex" — only the cross-harness reframe dedupes.
            self.assertEqual(sections["copilot"]["total_est_tokens"], 500)

    def test_per_100_calls_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = _audit_fixture(Path(tmp) / "proj")
            sections, _ = cw.audit_surfaces(project_dir, [], cw.DEFAULT_SURFACE_BUDGET_TOKENS)
            self.assertEqual(sections["claude"]["per_100_calls_tokens"], 50000)
            self.assertEqual(sections["codex"]["per_100_calls_tokens"], 30000)
            self.assertEqual(sections["copilot"]["per_100_calls_tokens"], 50000)

    def test_absent_surface_listed_absent_never_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = _audit_fixture(Path(tmp) / "proj")
            sections, _ = cw.audit_surfaces(project_dir, [], cw.DEFAULT_SURFACE_BUDGET_TOKENS)
            local = next(
                s for s in sections["claude"]["surfaces"] if s["path"] == "CLAUDE.local.md"
            )
            self.assertEqual(local, {"path": "CLAUDE.local.md", "present": False})
            self.assertNotIn("bytes", local)
            self.assertNotIn("est_tokens", local)

    def test_extra_surface_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = _audit_fixture(Path(tmp) / "proj")
            (Path(project_dir) / "docs").mkdir()
            (Path(project_dir) / "docs" / "EXTRA.md").write_text("z" * 400)
            sections, notes = cw.audit_surfaces(
                project_dir, ["docs/EXTRA.md"], cw.DEFAULT_SURFACE_BUDGET_TOKENS
            )
            self.assertIn("extra", sections)
            extra = sections["extra"]["surfaces"][0]
            self.assertTrue(extra["present"])
            self.assertEqual(extra["est_tokens"], 100)
            self.assertEqual(sections["extra"]["total_est_tokens"], 100)
            self.assertEqual(notes, [])

    def test_missing_extra_surface_is_a_note_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = _audit_fixture(Path(tmp) / "proj")
            sections, notes = cw.audit_surfaces(
                project_dir, ["docs/NOPE.md"], cw.DEFAULT_SURFACE_BUDGET_TOKENS
            )
            self.assertIn("extra", sections)
            self.assertFalse(sections["extra"]["surfaces"][0]["present"])
            self.assertTrue(any("docs/NOPE.md" in n for n in notes))

    def test_custom_budget_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = _audit_fixture(Path(tmp) / "proj")
            sections, _ = cw.audit_surfaces(project_dir, [], 1000)
            claude_md = next(s for s in sections["claude"]["surfaces"] if s["path"] == "CLAUDE.md")
            self.assertAlmostEqual(claude_md["pct_budget"], 50.0)

    def test_distinct_present_tokens_dedupes_agents_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = _audit_fixture(Path(tmp) / "proj")
            sections, _ = cw.audit_surfaces(project_dir, [], cw.DEFAULT_SURFACE_BUDGET_TOKENS)
            self.assertEqual(cw._audit_distinct_present_tokens(sections), 1000)


class AuditCliEndToEndTests(unittest.TestCase):
    def test_markdown_has_verbatim_closing_line_and_no_dollars(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = _audit_fixture(Path(tmp) / "proj")
            rc, out = _run_main(["audit", "--project", str(project_dir)])
            self.assertEqual(rc, 0)
            self.assertIn(cw.AUDIT_UNMEASURABLE_LINE, out)
            self.assertIn("CLAUDE.local.md", out)
            self.assertIn("absent", out)
            self.assertNotIn("$", out)

    def test_json_round_trips_with_pinned_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = _audit_fixture(Path(tmp) / "proj")
            rc, out = _run_main(["audit", "--project", str(project_dir), "--json"])
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertEqual(data["schema_version"], cw.CW_SCHEMA_VERSION)
            self.assertEqual(data["distinct_present_tokens"], 1000)
            self.assertIsNone(data["reframe"])
            self.assertEqual(data["unmeasurable_line"], cw.AUDIT_UNMEASURABLE_LINE)
            self.assertEqual(data["qualitative_reframe_line"], cw.AUDIT_QUALITATIVE_REFRAME_LINE)
            self.assertEqual(json.dumps(data), json.dumps(json.loads(json.dumps(data))))
            # NO dollar sign anywhere in the serialized JSON either.
            self.assertNotIn("$", json.dumps(data))

    def test_bare_audit_prints_qualitative_reframe_prominently_not_numeric(self):
        # D10 requires the reframe UNCONDITIONALLY. The common, bare-run case (no --session) has
        # no avg weight to divide by, so it must fall back to the qualitative line rather than
        # fabricate a percentage or omit the reframe entirely -- omission is exactly what would
        # let a bare `audit --project .` read as "your CLAUDE.md is eating N% of the budget."
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = _audit_fixture(Path(tmp) / "proj")
            rc, out = _run_main(["audit", "--project", str(project_dir)])
            self.assertEqual(rc, 0)
            self.assertIn(cw.AUDIT_QUALITATIVE_REFRAME_LINE, out)
            self.assertIn("the working set, not config, is the lever", out)
            # No numeric reframe was fabricated -- only the qualitative fallback appears.
            self.assertNotIn("of this session's avg per-call weight", out)
            self.assertNotIn("≈", out)
            self.assertNotIn("$", out)
            # Prominent, not buried: precedes the first per-harness section heading.
            reframe_pos = out.index(cw.AUDIT_QUALITATIVE_REFRAME_LINE)
            claude_table_pos = out.index("## Claude")
            self.assertLess(reframe_pos, claude_table_pos)

            rc_json, out_json = _run_main(["audit", "--project", str(project_dir), "--json"])
            self.assertEqual(rc_json, 0)
            data = json.loads(out_json)
            self.assertIsNone(data["reframe"])
            self.assertEqual(data["qualitative_reframe_line"], cw.AUDIT_QUALITATIVE_REFRAME_LINE)

    def test_reframe_line_with_session_pinned_to_6_percent(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = _audit_fixture(Path(tmp) / "proj")
            model_id = _first_sonnet_model()
            projects_dir = Path(tmp) / "projects"
            _write_claude_fixture(projects_dir, model_id)

            rc, out = _run_main([
                "audit", "--project", str(project_dir),
                "--session", "demo-claude", "--projects-dir", str(projects_dir),
            ])
            self.assertEqual(rc, 0)
            self.assertIn("1,000", out)
            self.assertIn("17,000", out)
            self.assertIn("≈ 6%", out)
            self.assertIn("the working set, not config, is the lever", out)
            # The reframe must appear BEFORE the per-harness tables — prominent, not buried.
            reframe_pos = out.index("the working set, not config, is the lever")
            claude_table_pos = out.index("## Claude")
            self.assertLess(reframe_pos, claude_table_pos)

            rc_json, out_json = _run_main([
                "audit", "--project", str(project_dir),
                "--session", "demo-claude", "--projects-dir", str(projects_dir), "--json",
            ])
            self.assertEqual(rc_json, 0)
            data = json.loads(out_json)
            self.assertEqual(data["reframe"]["avg_weight"], 17000)
            self.assertEqual(data["reframe"]["distinct_present_tokens"], 1000)
            self.assertEqual(data["reframe"]["pct"], 6)

    def test_session_not_found_notes_reframe_omitted_without_dollars(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = _audit_fixture(Path(tmp) / "proj")
            projects_dir = Path(tmp) / "projects"
            projects_dir.mkdir()
            rc, out = _run_main([
                "audit", "--project", str(project_dir),
                "--session", "does-not-exist", "--projects-dir", str(projects_dir),
            ])
            self.assertEqual(rc, 0)
            # No numeric reframe was computed, but the unconditional qualitative fallback still
            # prints (D10), plus the specific note explaining WHY the number is missing.
            self.assertIn(cw.AUDIT_QUALITATIVE_REFRAME_LINE, out)
            self.assertIn("reframe line omitted", out)
            self.assertNotIn("$", out)


class AuditReadOnlyTests(unittest.TestCase):
    def test_fixture_tree_unchanged_after_a_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = _audit_fixture(Path(tmp) / "proj")
            before = _snapshot_tree(tmp)
            _run_main(["audit", "--project", str(project_dir), "--json"])
            after = _snapshot_tree(tmp)
            self.assertEqual(before, after)


# ---- 15. `watch` — classify_prunable (T10, PLAN D15) -------------------------------------------
#
# Minimal, focused fixtures per rule rather than one giant scenario — each test isolates exactly
# one branch of classify_prunable's documented precedence order.


def _uw_text(text, minute):
    return {
        "type": "user", "timestamp": _ts(minute),
        "message": {"content": [{"type": "text", "text": text}]},
    }


def _uw_assistant(msg_id, minute, tool_use=None, thinking=None):
    content = []
    if thinking is not None:
        content.append({"type": "thinking", "thinking": thinking})
    if tool_use:
        content.append({
            "type": "tool_use", "id": tool_use["id"], "name": tool_use["name"],
            "input": tool_use["input"],
        })
    return {
        "type": "assistant", "timestamp": _ts(minute),
        "message": {"id": msg_id, "content": content},
    }


def _uw_tool_result(tool_use_id, content_text, minute, is_error=False):
    block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content_text}
    if is_error:
        block["is_error"] = True
    return {"type": "user", "timestamp": _ts(minute), "message": {"content": [block]}}


class PrunableClassifierTests(unittest.TestCase):
    def test_first_user_message_is_load_bearing(self):
        records = [_uw_text("Refactor the auth module.", 0)]
        prunable, load_bearing, unknown = cw.classify_prunable(records)
        self.assertEqual(prunable, [])
        self.assertEqual(unknown, [])
        self.assertEqual(len(load_bearing), 1)
        self.assertEqual(load_bearing[0]["reason"], "first user message of the session")

    def test_marker_in_later_user_message_is_load_bearing(self):
        records = [
            _uw_text("Start the task.", 0),
            _uw_text("We agreed to never modify prod config directly.", 1),
        ]
        prunable, load_bearing, unknown = cw.classify_prunable(records)
        self.assertEqual(unknown, [])
        self.assertEqual(len(load_bearing), 2)
        reasons = {item["reason"] for item in load_bearing}
        self.assertIn("decision/constraint marker", reasons)

    def test_later_user_message_without_marker_is_unknown(self):
        records = [
            _uw_text("Start the task.", 0),
            _uw_text("Sounds good, continue.", 1),
        ]
        prunable, load_bearing, unknown = cw.classify_prunable(records)
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0]["reason"], "later user message, no marker")
        self.assertEqual(len(load_bearing), 1)  # only the first message

    def test_superseded_read_is_prunable_latest_read_is_load_bearing(self):
        records = [
            _uw_assistant("a1", 0, tool_use={
                "id": "tu_r1", "name": "Read", "input": {"file_path": "/workspace/a.txt"},
            }),
            _uw_tool_result("tu_r1", "A" * 400, 1),
            _uw_assistant("a2", 2, tool_use={
                "id": "tu_r2", "name": "Read", "input": {"file_path": "/workspace/a.txt"},
            }),
            _uw_tool_result("tu_r2", "B" * 400, 3),
        ]
        prunable, load_bearing, unknown = cw.classify_prunable(records)
        self.assertEqual(unknown, [])
        prunable_reads = [i for i in prunable if i["tool"] == "Read"]
        load_bearing_reads = [i for i in load_bearing if i["tool"] == "Read"]
        self.assertEqual(len(prunable_reads), 1)
        self.assertIn("superseded", prunable_reads[0]["reason"])
        self.assertEqual(len(load_bearing_reads), 1)
        self.assertEqual(load_bearing_reads[0]["reason"], "most recent read of this path")

    def test_unresolved_error_is_load_bearing(self):
        records = [
            _uw_assistant("a1", 0, tool_use={
                "id": "tu_e1", "name": "Bash", "input": {"command": "rm -rf /nonexistent"},
            }),
            _uw_tool_result("tu_e1", "No such file", 1, is_error=True),
        ]
        prunable, load_bearing, unknown = cw.classify_prunable(records)
        self.assertEqual(prunable, [])
        self.assertEqual(unknown, [])
        self.assertEqual(len(load_bearing), 1)
        self.assertIn("unresolved error", load_bearing[0]["reason"])

    def test_error_with_later_successful_retry_is_not_load_bearing(self):
        records = [
            _uw_assistant("a1", 0, tool_use={
                "id": "tu_e1", "name": "Bash", "input": {"command": "make build"},
            }),
            _uw_tool_result("tu_e1", "build failed", 1, is_error=True),
            _uw_assistant("a2", 2, tool_use={
                "id": "tu_e2", "name": "Bash", "input": {"command": "make build"},
            }),
            _uw_tool_result("tu_e2", "ok", 3, is_error=False),
            _uw_assistant("a3", 4),  # a later assistant record so the first result is "acted on"
        ]
        prunable, load_bearing, unknown = cw.classify_prunable(records)
        # No unresolved-error item at all: the retry resolved it.
        self.assertFalse(any("unresolved error" in i["reason"] for i in load_bearing))

    def test_large_bash_output_is_prunable_even_without_later_assistant(self):
        records = [
            _uw_assistant("a1", 0, tool_use={
                "id": "tu_b1", "name": "Bash", "input": {"command": "tail -f huge.log"},
            }),
            _uw_tool_result("tu_b1", "y" * (cw.LARGE_TOOL_OUTPUT_EST_TOKENS * cw.EST_CHARS_PER_TOKEN),
                             1),
        ]
        # No assistant record follows this tool_result at all -- proves the size rule fires
        # independent of the "acted on by a later assistant message" rule.
        prunable, load_bearing, unknown = cw.classify_prunable(records)
        self.assertEqual(unknown, [])
        self.assertEqual(len(prunable), 1)
        self.assertIn("large command output", prunable[0]["reason"])

    def test_small_trailing_tool_result_without_later_assistant_is_unknown(self):
        records = [
            _uw_assistant("a1", 0, tool_use={
                "id": "tu_g1", "name": "Grep", "input": {"pattern": "TODO"},
            }),
            _uw_tool_result("tu_g1", "z" * 40, 1),
        ]
        prunable, load_bearing, unknown = cw.classify_prunable(records)
        self.assertEqual(prunable, [])
        self.assertEqual(load_bearing, [])
        self.assertEqual(len(unknown), 1)
        self.assertIn("not yet confirmed acted on", unknown[0]["reason"])

    def test_tool_result_acted_on_by_later_assistant_is_prunable(self):
        records = [
            _uw_assistant("a1", 0, tool_use={
                "id": "tu_g1", "name": "Grep", "input": {"pattern": "TODO"},
            }),
            _uw_tool_result("tu_g1", "z" * 40, 1),
            _uw_assistant("a2", 2),  # a later assistant message -- this result was acted on
        ]
        prunable, load_bearing, unknown = cw.classify_prunable(records)
        self.assertEqual(unknown, [])
        self.assertEqual(len(prunable), 1)
        self.assertEqual(prunable[0]["reason"], "acted on by a later assistant message")

    def test_thinking_from_completed_call_is_prunable_last_call_thinking_is_unknown(self):
        records = [
            _uw_assistant("a1", 0, thinking="figuring out the file layout"),
            _uw_assistant("a2", 1, thinking="still reasoning about it"),
        ]
        prunable, load_bearing, unknown = cw.classify_prunable(records)
        self.assertEqual(len(prunable), 1)
        self.assertEqual(prunable[0]["reason"], "thinking from a completed call")
        self.assertEqual(len(unknown), 1)
        self.assertIn("not yet confirmed acted on", unknown[0]["reason"])

    def test_sidechain_content_excluded_entirely(self):
        records = [
            _uw_text("Start.", 0),
            {**_uw_assistant("side1", 1, tool_use={
                "id": "tu_s1", "name": "Bash", "input": {"command": "echo hi"},
            }), "isSidechain": True},
            {**_uw_tool_result("tu_s1", "s" * 5000, 2), "isSidechain": True},
        ]
        prunable, load_bearing, unknown = cw.classify_prunable(records)
        # Only the first user message should be classified; sidechain content never entered
        # the main window (D7) and must not appear in any bucket.
        all_items = prunable + load_bearing + unknown
        self.assertEqual(len(all_items), 1)
        self.assertEqual(all_items[0]["reason"], "first user message of the session")


# ---- 15b. `watch` — classify_prunable window scoping (regression, D6/D15) ---------------------
#
# classify_prunable ran over the ENTIRE transcript, including records an earlier compaction had
# already discarded -- describing session HISTORY, not the live window, while the `watch` card
# renders the result directly beneath `current weight` as if it were resident. A partition of
# the current window can never exceed the window itself. Fixture below reproduces the real
# session that surfaced the bug: two large pre-compaction calls (900000/800000 tokens) followed
# by an inferred compaction (D6) into a small resident window (a3/a4, tens of thousands of
# tokens) -- pre-compaction mass several times the post-compaction window, per the coordinator's
# regression requirement.


class PrunableWindowScopingTests(unittest.TestCase):
    def _fixture(self, model_id):
        return [
            _uw_text("Investigate the flaky test.", 0),
            _assistant_record(
                "a1", model_id, 900000, 0, 0, 10, 1,
                tool_use={"id": "tu1", "name": "Bash", "input": {"command": "cat huge.log"}},
            ),
            _user_tool_result("tu1", "z" * 400000, 2),
            _assistant_record("a2", model_id, 800000, 0, 0, 10, 3),
            _assistant_record(
                "a3", model_id, 50000, 0, 0, 10, 4,
                tool_use={"id": "tu2", "name": "Read",
                          "input": {"file_path": "/workspace/note.txt"}},
            ),
            _user_tool_result("tu2", "y" * 4000, 5),
            _assistant_record("a4", model_id, 60000, 0, 0, 10, 6),
        ]

    def test_fixture_reproduces_old_bug_under_unscoped_computation(self):
        """Proves the fixture is actually sensitive to the bug (mirrors
        AvoidableMassDenominatorTests' `buggy_pct` check): classifying the WHOLE transcript,
        unscoped -- the old behavior, still reachable via the private `_classify_prunable_over`
        -- must produce classified mass that exceeds `current_weight`."""
        model_id = _first_sonnet_model()
        records = self._fixture(model_id)
        calls, _sidechain, _notes = cw.claude_call_weights(records)
        current_weight = calls[-1]["weight"]
        self.assertEqual(current_weight, 60000)

        # Fixture sanity: one inferred compaction, pre-compaction mass >> post-compaction window.
        drops = cw.detect_drops([c["weight"] for c in calls])
        self.assertEqual(len(drops), 1)
        self.assertGreater(calls[0]["weight"], current_weight * 10)

        prunable, load_bearing, unknown = cw._classify_prunable_over(records)
        buggy_total = sum(i["est_tokens"] for i in prunable + load_bearing + unknown)
        self.assertGreater(buggy_total, current_weight)

    def test_classified_mass_never_exceeds_current_weight(self):
        """The regression invariant: prunable + load_bearing + unknown, as returned by the
        PUBLIC (scoped) `classify_prunable`, must never exceed `current_weight` -- a partition
        of the current window cannot be larger than the window."""
        model_id = _first_sonnet_model()
        records = self._fixture(model_id)
        calls, sidechain, _notes = cw.claude_call_weights(records)
        current_weight = calls[-1]["weight"]

        prunable, load_bearing, unknown = cw.classify_prunable(records)
        classified_total = sum(i["est_tokens"] for i in prunable + load_bearing + unknown)
        self.assertLessEqual(classified_total, current_weight)

        # And end-to-end through the actual `watch` card assembly.
        pricing = cw.cr.load_pricing()
        card = cw.build_watch_card("sess", calls, sidechain, records, pricing)
        card_total = (
            card["prunable"]["est_tokens"]
            + card["load_bearing"]["est_tokens"]
            + card["unknown"]["est_tokens"]
        )
        self.assertLessEqual(card_total, card["current_weight"])

    def test_no_compaction_leaves_behavior_unchanged(self):
        """Without a compaction, the whole transcript IS the window -- scoping must be a no-op,
        so `classify_prunable` and the unscoped `_classify_prunable_over` agree exactly."""
        records = [
            _uw_text("Start.", 0),
            _uw_assistant("a1", 1, tool_use={
                "id": "tu1", "name": "Grep", "input": {"pattern": "TODO"},
            }),
            _uw_tool_result("tu1", "z" * 40, 2),
            _uw_assistant("a2", 3),
        ]
        self.assertEqual(cw.classify_prunable(records), cw._classify_prunable_over(records))


# ---- 16. `watch` — card assembly + CLI (T10) ----------------------------------------------------


class WatchCardTests(unittest.TestCase):
    def test_card_top_level_keys_and_mass_sums(self):
        model_id = _first_sonnet_model()
        objs = _claude_fixture_records(model_id)
        calls, sidechain, _notes = cw.claude_call_weights(objs)
        pricing = cw.cr.load_pricing()
        card = cw.build_watch_card("sess", calls, sidechain, objs, pricing)
        for key in ("prunable", "load_bearing", "unknown"):
            self.assertIn(key, card)
            self.assertEqual(
                card[key]["est_tokens"], sum(i["est_tokens"] for i in card[key]["items"])
            )
            self.assertEqual(card[key]["count"], len(card[key]["items"]))
        self.assertEqual(card["current_weight"], calls[-1]["weight"])

    def test_window_tokens_resolved_from_pricing_json_not_hardcoded(self):
        model_id = _first_sonnet_model()
        objs = _claude_fixture_records(model_id)
        calls, sidechain, _notes = cw.claude_call_weights(objs)
        pricing = cw.cr.load_pricing()
        card = cw.build_watch_card("sess", calls, sidechain, objs, pricing)
        expected = pricing["models"][model_id]["context_window"]
        self.assertEqual(card["window_tokens"], expected)
        self.assertAlmostEqual(
            card["pct_of_window"], calls[-1]["weight"] / expected * 100, places=6
        )

    def test_window_tokens_override_flag_wins(self):
        model_id = _first_sonnet_model()
        objs = _claude_fixture_records(model_id)
        calls, sidechain, _notes = cw.claude_call_weights(objs)
        pricing = cw.cr.load_pricing()
        card = cw.build_watch_card("sess", calls, sidechain, objs, pricing,
                                    window_tokens_override=1234)
        self.assertEqual(card["window_tokens"], 1234)

    def test_recommendation_ladder(self):
        model_id = _first_sonnet_model()
        objs = _claude_fixture_records(model_id)
        calls, sidechain, _notes = cw.claude_call_weights(objs)
        pricing = cw.cr.load_pricing()
        current = calls[-1]["weight"]

        below_40 = cw.build_watch_card("sess", calls, sidechain, objs, pricing,
                                        window_tokens_override=current * 100)
        self.assertEqual(below_40["recommendation"], "no action")

        mid_band = cw.build_watch_card("sess", calls, sidechain, objs, pricing,
                                        window_tokens_override=current * 2)  # 50%
        self.assertEqual(mid_band["recommendation"], "delegate new bulk reads, do not inline")

        above_60 = cw.build_watch_card("sess", calls, sidechain, objs, pricing,
                                        window_tokens_override=int(current * 1.5))  # ~67%
        self.assertEqual(above_60["recommendation"], "checkpoint decisions to disk, then compact")

    def test_never_claims_to_delete_anything(self):
        model_id = _first_sonnet_model()
        objs = _claude_fixture_records(model_id)
        calls, sidechain, _notes = cw.claude_call_weights(objs)
        pricing = cw.cr.load_pricing()
        card = cw.build_watch_card("sess", calls, sidechain, objs, pricing)
        md = cw.render_watch_markdown(card)
        self.assertIn("never deletes anything", md)
        self.assertNotIn("will delete", md)
        self.assertNotIn("has been deleted", md)

    def test_card_discloses_what_the_three_classes_do_not_cover(self):
        """The classes enumerate droppable ITEMS, not the whole window (~10% on a real
        session). Without a coverage line a reader cannot distinguish "the rest is
        known-not-droppable" from "the rest was never examined" — the same honesty rule the
        attribution table holds when it names what is not measurable."""
        model_id = _first_sonnet_model()
        objs = _claude_fixture_records(model_id)
        calls, sidechain, _notes = cw.claude_call_weights(objs)
        pricing = cw.cr.load_pricing()
        card = cw.build_watch_card("sess", calls, sidechain, objs, pricing)
        md = cw.render_watch_markdown(card)

        classified = sum(card[k]["est_tokens"] for k in ("prunable", "load_bearing", "unknown"))
        self.assertIn("these classes cover discrete droppable items", md)
        self.assertIn(f"{classified:,} est. of {card['current_weight']:,}", md)
        # the remainder must be NAMED, not merely implied by the arithmetic
        self.assertIn("assistant output and user input", md)
        # est. figures are never priced (D5/D9)
        self.assertNotIn("$", md.split("these classes cover")[1].split("\n")[0])

    def test_coverage_line_omitted_when_there_is_no_window_to_divide_by(self):
        """A sidechain-only transcript yields current_weight 0; the line must be skipped
        rather than dividing by zero or printing a meaningless 0%."""
        pricing = cw.cr.load_pricing()
        card = cw.build_watch_card("sess", [], {"calls": 3, "weight": 5000}, [], pricing)
        md = cw.render_watch_markdown(card)
        self.assertNotIn("these classes cover discrete droppable items", md)


class WatchCliEndToEndTests(unittest.TestCase):
    def test_watch_json_validates_with_pinned_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_id = _first_sonnet_model()
            projects_dir = Path(tmp) / "projects"
            _write_claude_fixture(projects_dir, model_id)

            rc, out = _run_main(["watch", "--projects-dir", str(projects_dir), "--json"])
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertIn("prunable", data)
            self.assertIn("load_bearing", data)
            self.assertIn("unknown", data)
            self.assertEqual(data["schema_version"], cw.CW_SCHEMA_VERSION)

    def test_watch_markdown_renders(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_id = _first_sonnet_model()
            projects_dir = Path(tmp) / "projects"
            _write_claude_fixture(projects_dir, model_id)

            rc, out = _run_main(["watch", "--projects-dir", str(projects_dir)])
            self.assertEqual(rc, 0)
            self.assertIn("Context weight — watch", out)
            self.assertIn("recommendation:", out)
            self.assertIn("of a", out)
            self.assertIn("-token", out)

    def test_absent_projects_dir_exits_0_with_pinned_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            nowhere = Path(tmp) / "does-not-exist"
            rc, out = _run_main(["watch", "--projects-dir", str(nowhere), "--json"])
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertFalse(data["found"])
            for key in ("prunable", "load_bearing", "unknown"):
                self.assertIn(key, data)
                self.assertEqual(data[key]["count"], 0)

    def test_codex_positional_prints_byte_exact_refusal_and_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, out = _run_main(["watch", "codex", "--projects-dir", str(tmp)])
            self.assertEqual(rc, 0)
            self.assertEqual(out.strip(), cw.WATCH_REFUSAL_LINE)

    def test_copilot_positional_prints_byte_exact_refusal_and_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, out = _run_main(["watch", "copilot", "--projects-dir", str(tmp)])
            self.assertEqual(rc, 0)
            self.assertEqual(out.strip(), cw.WATCH_REFUSAL_LINE)

    def test_watch_has_no_dashdash_harness_flag(self):
        # Hard constraint: watch is Claude-only and must NOT grow a --harness flag (unlike
        # session/overview) -- the positional harness value above is the sanctioned way for a
        # Codex/Copilot invocation to reach the refusal line instead.
        ap = cw.build_parser()
        found_watch = False
        for sub in ap._subparsers._group_actions:
            for choice, sub_ap in sub.choices.items():
                if choice != "watch":
                    continue
                found_watch = True
                for a in sub_ap._actions:
                    self.assertNotIn("--harness", a.option_strings)
        self.assertTrue(found_watch)

    def test_window_tokens_flag_overrides_pricing_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_id = _first_sonnet_model()
            projects_dir = Path(tmp) / "projects"
            _write_claude_fixture(projects_dir, model_id)

            rc, out = _run_main([
                "watch", "--projects-dir", str(projects_dir), "--window-tokens", "16000", "--json",
            ])
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertEqual(data["window_tokens"], 16000)
            # last call weight is 8000 (T1 fixture) -> 8000 / 16000 = 50% -> mid band.
            self.assertEqual(data["recommendation"], "delegate new bulk reads, do not inline")


class WatchReadOnlyTests(unittest.TestCase):
    def test_fixture_tree_unchanged_after_a_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_id = _first_sonnet_model()
            projects_dir = Path(tmp) / "projects"
            _write_claude_fixture(projects_dir, model_id)

            before = _snapshot_tree(tmp)
            _run_main(["watch", "--projects-dir", str(projects_dir), "--json"])
            after = _snapshot_tree(tmp)
            self.assertEqual(before, after)


# ---- 17. `constraints` — GUARDRAILS.md residency (evidence-loop kit U2, PLAN E1) ---------------


class GuardrailsReadsTests(unittest.TestCase):
    def test_finds_matching_read_and_ignores_others(self):
        model_id = _first_sonnet_model()
        guardrails_path = "/repo/.claude/kits/demo-kit/GUARDRAILS.md"
        records = [
            _assistant_record("g1", model_id, 1000, 0, 0, 10, 0,
                               tool_use={"id": "t1", "name": "Read",
                                         "input": {"file_path": guardrails_path}}),
            _user_tool_result("t1", "g" * 400, 1),
            _assistant_record("g2", model_id, 1000, 0, 0, 10, 2,
                               tool_use={"id": "t2", "name": "Read",
                                         "input": {"file_path": "/repo/other.md"}}),
            _user_tool_result("t2", "z" * 40, 3),
        ]
        reads = cw.find_guardrails_reads(records, guardrails_path)
        self.assertEqual(len(reads), 1)
        self.assertEqual(reads[0]["est_tokens"], 100)

    def test_sidechain_reads_are_excluded(self):
        model_id = _first_sonnet_model()
        guardrails_path = "/repo/.claude/kits/demo-kit/GUARDRAILS.md"
        assistant_rec = _assistant_record(
            "g1", model_id, 1000, 0, 0, 10, 0,
            tool_use={"id": "t1", "name": "Read", "input": {"file_path": guardrails_path}},
            is_sidechain=True,
        )
        tool_result_rec = dict(_user_tool_result("t1", "g" * 400, 1))
        tool_result_rec["isSidechain"] = True
        reads = cw.find_guardrails_reads([assistant_rec, tool_result_rec], guardrails_path)
        self.assertEqual(reads, [])

    def test_path_matching_is_exact_not_fuzzy(self):
        # PLAN/GUARDRAILS: no fuzzy matching anywhere in this kit — a different file under the
        # same basename must never match.
        self.assertFalse(cw._guardrails_path_matches(
            "/repo/other-kit/GUARDRAILS.md", "/repo/.claude/kits/demo-kit/GUARDRAILS.md",
        ))
        # normpath-only tolerance (no filesystem resolve()) still recognizes a trivially
        # different spelling of the SAME path.
        self.assertTrue(cw._guardrails_path_matches(
            "/repo/./kit/GUARDRAILS.md", "/repo/kit/GUARDRAILS.md",
        ))
        self.assertFalse(cw._guardrails_path_matches(None, "/repo/kit/GUARDRAILS.md"))
        self.assertFalse(cw._guardrails_path_matches("", "/repo/kit/GUARDRAILS.md"))

    def test_relative_and_absolute_spellings_of_the_same_path_match(self):
        # Claude Code records `file_path` as an ABSOLUTE path; `--kit` is routinely given
        # relatively. A lexical abspath (cwd join + normpath, no filesystem access) must make
        # those two spellings compare equal, or a relative --kit yields a confident
        # "never loaded into context here" for a session that DID read the fences.
        cwd_before = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                # `tmp` may itself be a symlinked path (/var -> /private/var on macOS); abspath
                # is deliberately lexical, so compare against os.getcwd()'s own spelling.
                here = os.getcwd()
                absolute = os.path.join(here, "kits", "demo-kit", "GUARDRAILS.md")
                relative = os.path.join("kits", "demo-kit", "GUARDRAILS.md")
                self.assertTrue(cw._guardrails_path_matches(absolute, relative))
                self.assertTrue(cw._guardrails_path_matches(relative, absolute))
                # Still no filesystem access and still exact: nothing above exists on disk,
                # and a different kit under the same basename must still not match.
                self.assertFalse(os.path.exists(absolute))
                self.assertFalse(cw._guardrails_path_matches(
                    absolute, os.path.join("kits", "other-kit", "GUARDRAILS.md"),
                ))
            finally:
                os.chdir(cwd_before)

    def test_symlinked_spelling_of_a_real_path_matches_via_samefile(self):
        # abspath cannot reconcile a symlink: two different path SHAPES that stat to the same
        # inode. Constructed via a real symlink in a temp dir (portable; a case-insensitive
        # filesystem is not). This is the exact residual F2 flagged, reproduced against a real
        # session: `--kit` given via one spelling of a symlinked ancestor directory must still
        # match a Read recorded under the other spelling of the SAME file.
        with tempfile.TemporaryDirectory() as tmp:
            real_dir = os.path.join(tmp, "real")
            os.makedirs(real_dir)
            guardrails_path = os.path.join(real_dir, "GUARDRAILS.md")
            with open(guardrails_path, "w") as f:
                f.write("fences")
            link_dir = os.path.join(tmp, "link")
            os.symlink(real_dir, link_dir)
            via_symlink = os.path.join(link_dir, "GUARDRAILS.md")
            # Lexically these differ — abspath alone does not reconcile a symlink hop — so this
            # actually exercises the samefile fallback tier, not the lexical tier.
            self.assertNotEqual(os.path.abspath(guardrails_path), os.path.abspath(via_symlink))
            self.assertTrue(cw._guardrails_path_matches(via_symlink, guardrails_path))
            self.assertTrue(cw._guardrails_path_matches(guardrails_path, via_symlink))

    def test_never_read_session_still_reports_not_found_under_every_spelling(self):
        # A genuinely-never-read session must still get the honest not-found line: a Read of a
        # DIFFERENT real file must not spuriously match just because both paths now exist on
        # disk and the samefile tier is reachable.
        with tempfile.TemporaryDirectory() as tmp:
            guardrails_path = os.path.join(tmp, "GUARDRAILS.md")
            with open(guardrails_path, "w") as f:
                f.write("fences")
            other_real = os.path.join(tmp, "OTHER.md")
            with open(other_real, "w") as f:
                f.write("not fences")
            model_id = _first_sonnet_model()
            records = [
                _assistant_record("g1", model_id, 1000, 0, 0, 10, 0,
                                   tool_use={"id": "t1", "name": "Read",
                                             "input": {"file_path": other_real}}),
                _user_tool_result("t1", "z" * 40, 1),
            ]
            reads = cw.find_guardrails_reads(records, guardrails_path)
            self.assertEqual(reads, [])

    def test_nonexistent_path_matches_lexically_with_no_stat_attempted(self):
        # Fictional paths (the shape every earlier test in this class uses) must never reach
        # the stat tier. Patch os.path.samefile to explode if invoked, and confirm
        # lexical-only behavior is unchanged for paths that do not exist on disk.
        def _boom(a, b):
            raise AssertionError("samefile must not be called for nonexistent paths")
        with mock.patch.object(os.path, "samefile", side_effect=_boom):
            self.assertTrue(cw._guardrails_path_matches(
                "/repo/./kit/GUARDRAILS.md", "/repo/kit/GUARDRAILS.md",
            ))
            self.assertFalse(cw._guardrails_path_matches(
                "/repo/other-kit/GUARDRAILS.md", "/repo/.claude/kits/demo-kit/GUARDRAILS.md",
            ))


class ConstraintsResidencyTests(unittest.TestCase):
    def test_resident_when_no_compaction_since_the_read(self):
        model_id = _first_sonnet_model()
        guardrails_path = "/repo/.claude/kits/demo-kit/GUARDRAILS.md"
        records = [
            _assistant_record("g1", model_id, 1000, 0, 0, 10, 0,
                               tool_use={"id": "t1", "name": "Read",
                                         "input": {"file_path": guardrails_path}}),
            _user_tool_result("t1", "g" * 400, 1),
            _assistant_record("g2", model_id, 1200, 1000, 400, 10, 2),
        ]
        calls, _sc, _notes = cw.claude_call_weights(records)
        residency = cw._constraints_residency(records, calls, guardrails_path)

        self.assertEqual(residency["reads"], 1)
        self.assertTrue(residency["resident"])
        self.assertEqual(residency["current_weight_est_tokens"], 100)
        self.assertEqual(residency["weight_label"], "est.")
        self.assertIsNone(residency["not_found_line"])
        self.assertEqual(len(residency["trend"]), 1)
        self.assertEqual(residency["trend"][0]["call_index"], 0)
        self.assertTrue(residency["trend"][0]["resident_now"])

    def test_evicted_by_compaction_with_no_reread(self):
        # Mirrors PrunableWindowScopingTests' fixture shape: a huge early call, a huge tool
        # result, then a >=50% weight drop the engine infers as a compaction. GUARDRAILS.md is
        # read only BEFORE that drop and never again -- residency must report NOT resident, even
        # though a read did happen earlier in the session (the exact decay E1 exists to catch).
        model_id = _first_sonnet_model()
        guardrails_path = "/repo/.claude/kits/demo-kit/GUARDRAILS.md"
        records = [
            _assistant_record("g1", model_id, 900000, 0, 0, 10, 0,
                               tool_use={"id": "t1", "name": "Read",
                                         "input": {"file_path": guardrails_path}}),
            _user_tool_result("t1", "g" * 4000, 1),
            _assistant_record("g2", model_id, 800000, 0, 0, 10, 2),
            _assistant_record("g3", model_id, 50000, 0, 0, 10, 3),
            _assistant_record("g4", model_id, 60000, 0, 0, 10, 4),
        ]
        calls, _sc, _notes = cw.claude_call_weights(records)
        drops = cw.detect_drops([c["weight"] for c in calls])
        self.assertEqual(len(drops), 1)  # fixture sanity: exactly one inferred compaction

        residency = cw._constraints_residency(records, calls, guardrails_path)
        self.assertEqual(residency["reads"], 1)
        self.assertFalse(residency["resident"])
        self.assertIsNone(residency["current_weight_est_tokens"])
        self.assertIsNone(residency["weight_label"])
        self.assertFalse(residency["trend"][0]["resident_now"])

    def test_no_read_gives_honest_fallback_never_a_verdict(self):
        model_id = _first_sonnet_model()
        guardrails_path = "/repo/.claude/kits/demo-kit/GUARDRAILS.md"
        records = [
            _assistant_record("g1", model_id, 1000, 0, 0, 10, 0,
                               tool_use={"id": "t1", "name": "Bash",
                                         "input": {"command": "ls"}}),
            _user_tool_result("t1", "x" * 40, 1),
        ]
        calls, _sc, _notes = cw.claude_call_weights(records)
        residency = cw._constraints_residency(records, calls, guardrails_path)

        self.assertEqual(residency["reads"], 0)
        self.assertFalse(residency["resident"])
        self.assertEqual(residency["trend"], [])
        self.assertEqual(
            residency["not_found_line"],
            cw.CONSTRAINTS_NOT_FOUND_LINE.format(path=guardrails_path),
        )


class ConstraintsCardTests(unittest.TestCase):
    def test_card_and_markdown_resident_case(self):
        model_id = _first_sonnet_model()
        with tempfile.TemporaryDirectory() as tmp:
            kit_dir = Path(tmp) / "kit"
            kit_dir.mkdir()
            (kit_dir / cw.GUARDRAILS_FILENAME).write_text("x" * 10)
            guardrails_path = str(kit_dir / cw.GUARDRAILS_FILENAME)
            records = [
                _assistant_record("g1", model_id, 1000, 0, 0, 10, 0,
                                   tool_use={"id": "t1", "name": "Read",
                                             "input": {"file_path": guardrails_path}}),
                _user_tool_result("t1", "g" * 400, 1),
            ]
            calls, _sc, _notes = cw.claude_call_weights(records)
            card = cw.build_constraints_card(kit_dir, records, calls, session_id="sess-1")

            self.assertTrue(card["found"])
            self.assertEqual(card["schema_version"], cw.CW_SCHEMA_VERSION)
            self.assertEqual(card["harness"], "claude")
            self.assertTrue(card["file_exists_now"])
            self.assertTrue(card["resident"])
            self.assertEqual(card["current_weight_est_tokens"], 100)

            md = cw.render_constraints_markdown(card)
            self.assertIn("resident: YES", md)
            self.assertIn("100 est. tokens", md)
            self.assertIn("Weight trend across the growth curve (est.)", md)
            self.assertIn("| 1 | yes | 100 est. |", md)
            self.assertIn(cw.ATTRIBUTION_BASIS, md)

            # JSON round-trips cleanly (D8/repo idiom: every card is plain JSON-safe data).
            payload = cw.build_constraints_json(card)
            self.assertEqual(json.dumps(payload), json.dumps(json.loads(json.dumps(payload))))

    def test_card_reports_file_absent_from_disk(self):
        card = cw.build_constraints_card("/does/not/exist/kit", [], [], session_id="sess-2")
        self.assertFalse(card["file_exists_now"])
        self.assertEqual(card["reads"], 0)
        md = cw.render_constraints_markdown(card)
        self.assertIn("does not exist on disk right now", md)

    def test_absent_session_card(self):
        card = cw.build_absent_constraints_card("/some/kit", "abc", Path("/nowhere"))
        self.assertFalse(card["found"])
        md = cw.render_constraints_markdown(card)
        self.assertIn("No claude transcript found", md)
        self.assertIn("/some/kit", md)


class ConstraintsCliEndToEndTests(unittest.TestCase):
    def test_codex_harness_prints_the_bespoke_subcommand_named_refusal(self):
        rc, out = _run_main(["constraints", "--harness", "codex", "--kit", "/x"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), cw.CONSTRAINTS_REFUSAL_LINE)

    def test_copilot_harness_prints_the_bespoke_subcommand_named_refusal(self):
        rc, out = _run_main(["constraints", "--harness", "copilot", "--kit", "/x"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), cw.CONSTRAINTS_REFUSAL_LINE)

    def test_refusal_is_subcommand_named_and_never_borrows_another_surfaces_line(self):
        # Follows `watch`'s ACTUAL precedent: WATCH_REFUSAL_LINE is bespoke and names its own
        # subcommand. The two per-harness fidelity lines caption output `constraints` does not
        # produce (a byte-share table; a growth curve) and neither says the RESIDENCY question
        # is the unanswerable one — so neither may be reused here.
        line = cw.CONSTRAINTS_REFUSAL_LINE
        self.assertTrue(line.startswith("constraints:"))
        self.assertIn("residency", line.lower())
        self.assertNotEqual(line, cw.CODEX_NO_PROVENANCE_LINE)
        self.assertNotEqual(line, cw.COPILOT_NO_CURVE_LINE)
        self.assertNotIn(cw.CODEX_NO_PROVENANCE_LINE, line)
        self.assertNotIn(cw.COPILOT_NO_CURVE_LINE, line)
        # ...and the two borrowed-from constants are untouched, still serving their own
        # surfaces byte for byte.
        self.assertEqual(
            cw.CODEX_NO_PROVENANCE_LINE,
            "provenance not recorded in these logs — byte-share of rollout record types shown "
            "as a labeled estimate",
        )
        self.assertEqual(
            cw.COPILOT_NO_CURVE_LINE,
            "growth curve: not available — Copilot events do not record per-turn input/cache "
            "token splits",
        )
        for harness in ("codex", "copilot"):
            _rc, out = _run_main(["constraints", "--harness", harness, "--kit", "/x"])
            self.assertNotIn("byte-share", out)
            self.assertNotIn("growth curve", out)

    def test_kit_flag_is_required(self):
        with self.assertRaises(SystemExit):
            cw.build_parser().parse_args(["constraints"])

    def test_json_round_trips_with_resident_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_id = _first_sonnet_model()
            kit_dir = Path(tmp) / "kit"
            kit_dir.mkdir()
            (kit_dir / cw.GUARDRAILS_FILENAME).write_text("x" * 10)
            guardrails_path = str(kit_dir / cw.GUARDRAILS_FILENAME)

            projects_dir = Path(tmp) / "projects"
            proj = projects_dir / "demo-proj"
            proj.mkdir(parents=True)
            records = [
                _assistant_record("g1", model_id, 1000, 0, 0, 10, 0,
                                   tool_use={"id": "t1", "name": "Read",
                                             "input": {"file_path": guardrails_path}}),
                _user_tool_result("t1", "g" * 400, 1),
            ]
            (proj / "sess.jsonl").write_text(
                "\n".join(json.dumps(r) for r in records) + "\n"
            )

            rc, out = _run_main([
                "constraints", "--kit", str(kit_dir),
                "--projects-dir", str(projects_dir), "--json",
            ])
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertTrue(data["found"])
            self.assertTrue(data["resident"])
            self.assertEqual(data["current_weight_est_tokens"], 100)
            self.assertEqual(data["weight_label"], "est.")

    def test_session_not_found_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp) / "projects"
            projects_dir.mkdir()
            rc, out = _run_main([
                "constraints", "--kit", "/some/kit",
                "--session", "nope", "--projects-dir", str(projects_dir),
            ])
            self.assertEqual(rc, 0)
            self.assertIn("No claude transcript found", out)


class ConstraintsKitArgSpellingTests(unittest.TestCase):
    """The same fixture must produce the same verdict whether `--kit` is spelled relatively or
    absolutely. `CONSTRAINTS_NOT_FOUND_LINE` states a fact about the SESSION; a fact about the
    ARGUMENT must never be able to produce it."""

    def _verdicts(self, tmp, kit_dir, projects_dir):
        cwd_before = os.getcwd()
        verdicts = []
        try:
            os.chdir(tmp)
            for kit_arg in (str(kit_dir), os.path.relpath(str(kit_dir), os.getcwd())):
                rc, out = _run_main([
                    "constraints", "--kit", kit_arg,
                    "--projects-dir", str(projects_dir), "--json",
                ])
                self.assertEqual(rc, 0)
                data = json.loads(out)
                verdicts.append((
                    kit_arg, data["reads"], data["resident"],
                    data["current_weight_est_tokens"], data["not_found_line"],
                ))
        finally:
            os.chdir(cwd_before)
        return verdicts

    def test_relative_kit_gives_the_same_verdict_as_absolute(self):
        model_id = _first_sonnet_model()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = os.path.realpath(tmp)
            kit_dir = Path(tmp) / "kits" / "demo-kit"
            kit_dir.mkdir(parents=True)
            (kit_dir / cw.GUARDRAILS_FILENAME).write_text("x" * 10)
            # Claude Code records file_path absolutely, whatever spelling --kit later uses.
            guardrails_path = str(kit_dir / cw.GUARDRAILS_FILENAME)

            projects_dir = Path(tmp) / "projects"
            proj = projects_dir / "demo-proj"
            proj.mkdir(parents=True)
            records = [
                _assistant_record("g1", model_id, 1000, 0, 0, 10, 0,
                                   tool_use={"id": "t1", "name": "Read",
                                             "input": {"file_path": guardrails_path}}),
                _user_tool_result("t1", "g" * 400, 1),
            ]
            (proj / "sess.jsonl").write_text(
                "\n".join(json.dumps(r) for r in records) + "\n"
            )

            absolute, relative = self._verdicts(tmp, kit_dir, projects_dir)
            self.assertNotEqual(absolute[0], relative[0])   # genuinely two spellings
            self.assertEqual(absolute[1:], relative[1:])    # one verdict
            # And it is the CORRECT verdict, not two matching wrong ones.
            self.assertEqual(relative[1], 1)
            self.assertTrue(relative[2])
            self.assertEqual(relative[3], 100)
            self.assertIsNone(relative[4])

    def test_a_session_that_never_read_the_file_still_reports_not_found_either_way(self):
        # The other direction of the same pin: closing the false-negative hole must not turn
        # the honest never-read fallback into a false positive.
        model_id = _first_sonnet_model()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = os.path.realpath(tmp)
            kit_dir = Path(tmp) / "kits" / "demo-kit"
            kit_dir.mkdir(parents=True)
            (kit_dir / cw.GUARDRAILS_FILENAME).write_text("x" * 10)

            projects_dir = Path(tmp) / "projects"
            proj = projects_dir / "demo-proj"
            proj.mkdir(parents=True)
            records = [
                _assistant_record("g1", model_id, 1000, 0, 0, 10, 0,
                                   tool_use={"id": "t1", "name": "Bash",
                                             "input": {"command": "ls"}}),
                _user_tool_result("t1", "x" * 40, 1),
            ]
            (proj / "sess.jsonl").write_text(
                "\n".join(json.dumps(r) for r in records) + "\n"
            )

            absolute, relative = self._verdicts(tmp, kit_dir, projects_dir)
            self.assertEqual(absolute[1:4], relative[1:4])
            self.assertEqual(relative[1], 0)
            self.assertFalse(relative[2])
            self.assertIn("never loaded into context here", relative[4])


class ConstraintsCompactionBasisTests(unittest.TestCase):
    """An INFERRED compaction must never be asserted as a KNOWN one (PLAN E4). `session`'s
    markdown already separates "Inferred compactions" from "Confirmed compact-summary markers";
    the card whose whole subject is compaction owes the reader the same distinction."""

    def _evicted_records(self, model_id, guardrails_path, confirmed=False):
        # A read, then a >=DROP_FRACTION weight drop with no re-read after it.
        records = [
            _assistant_record("g1", model_id, 900000, 0, 0, 10, 0,
                               tool_use={"id": "t1", "name": "Read",
                                         "input": {"file_path": guardrails_path}}),
            _user_tool_result("t1", "g" * 4000, 1),
            _assistant_record("g2", model_id, 800000, 0, 0, 10, 2),
            _assistant_record("g3", model_id, 50000, 0, 0, 10, 3),
            _assistant_record("g4", model_id, 60000, 0, 0, 10, 4),
        ]
        if confirmed:
            records[-1]["isCompactSummary"] = True
        return records

    def test_slice_reports_inferred_confirmed_and_none(self):
        model_id = _first_sonnet_model()
        gp = "/repo/.claude/kits/demo-kit/GUARDRAILS.md"

        _scoped, basis = cw._resident_window_slice(self._evicted_records(model_id, gp))
        self.assertEqual(basis, "inferred")

        _scoped, basis = cw._resident_window_slice(
            self._evicted_records(model_id, gp, confirmed=True))
        self.assertEqual(basis, "confirmed")

        quiet = [
            _assistant_record("q1", model_id, 1000, 0, 0, 10, 0),
            _assistant_record("q2", model_id, 1200, 1000, 400, 10, 1),
        ]
        scoped, basis = cw._resident_window_slice(quiet)
        self.assertIsNone(basis)
        self.assertEqual(scoped, quiet)   # unchanged-input behavior preserved

    def test_resident_window_records_behavior_is_unchanged_by_the_split(self):
        model_id = _first_sonnet_model()
        gp = "/repo/.claude/kits/demo-kit/GUARDRAILS.md"
        for recs in (self._evicted_records(model_id, gp),
                     self._evicted_records(model_id, gp, confirmed=True)):
            self.assertEqual(
                [id(o) for o in cw._resident_window_records(recs)],
                [id(o) for o in cw._resident_window_slice(recs)[0]],
            )

    def test_inferred_eviction_reads_as_an_inference_in_markdown_and_json(self):
        model_id = _first_sonnet_model()
        with tempfile.TemporaryDirectory() as tmp:
            kit_dir = Path(tmp) / "kit"
            kit_dir.mkdir()
            (kit_dir / cw.GUARDRAILS_FILENAME).write_text("x" * 10)
            gp = str(kit_dir / cw.GUARDRAILS_FILENAME)
            records = self._evicted_records(model_id, gp)
            calls, _sc, _notes = cw.claude_call_weights(records)
            card = cw.build_constraints_card(kit_dir, records, calls, session_id="sess-i")

            self.assertFalse(card["resident"])
            self.assertEqual(card["compaction_basis"], "inferred")
            self.assertEqual(
                json.loads(json.dumps(cw.build_constraints_json(card)))["compaction_basis"],
                "inferred",
            )

            md = cw.render_constraints_markdown(card)
            self.assertIn("resident: NO", md)
            self.assertIn("INFERRED compaction", md)
            self.assertIn("rather than read off a recorded marker", md)
            # DROP_FRACTION is rendered from the constant, never restated as a literal.
            self.assertIn(f"at least {cw.DROP_FRACTION:.0%}", md)
            self.assertNotIn("isCompactSummary", md)

    def test_confirmed_eviction_reads_as_the_recorded_marker_it_is(self):
        model_id = _first_sonnet_model()
        with tempfile.TemporaryDirectory() as tmp:
            kit_dir = Path(tmp) / "kit"
            kit_dir.mkdir()
            (kit_dir / cw.GUARDRAILS_FILENAME).write_text("x" * 10)
            gp = str(kit_dir / cw.GUARDRAILS_FILENAME)
            records = self._evicted_records(model_id, gp, confirmed=True)
            calls, _sc, _notes = cw.claude_call_weights(records)
            card = cw.build_constraints_card(kit_dir, records, calls, session_id="sess-c")

            self.assertFalse(card["resident"])
            self.assertEqual(card["compaction_basis"], "confirmed")
            md = cw.render_constraints_markdown(card)
            self.assertIn("confirmed compaction", md)
            self.assertIn("isCompactSummary", md)
            self.assertNotIn("INFERRED compaction", md)

    def test_resident_case_states_no_eviction_at_all(self):
        model_id = _first_sonnet_model()
        with tempfile.TemporaryDirectory() as tmp:
            kit_dir = Path(tmp) / "kit"
            kit_dir.mkdir()
            (kit_dir / cw.GUARDRAILS_FILENAME).write_text("x" * 10)
            gp = str(kit_dir / cw.GUARDRAILS_FILENAME)
            records = [
                _assistant_record("g1", model_id, 1000, 0, 0, 10, 0,
                                   tool_use={"id": "t1", "name": "Read",
                                             "input": {"file_path": gp}}),
                _user_tool_result("t1", "g" * 400, 1),
            ]
            calls, _sc, _notes = cw.claude_call_weights(records)
            md = cw.render_constraints_markdown(
                cw.build_constraints_card(kit_dir, records, calls, session_id="sess-r"))
            self.assertIn("resident: YES", md)
            self.assertNotIn("compaction", md)
            self.assertNotIn(cw.CONSTRAINTS_PHASE_ANCHOR_NOTE, md)

    def test_non_resident_card_carries_the_phase_anchor_context(self):
        # U1's guarantee is anchored to PHASE STARTS and explicitly is not compaction-triggered,
        # so a mid-phase compaction shows NO with nothing violated. The card must say so rather
        # than read as an indictment.
        model_id = _first_sonnet_model()
        with tempfile.TemporaryDirectory() as tmp:
            kit_dir = Path(tmp) / "kit"
            kit_dir.mkdir()
            (kit_dir / cw.GUARDRAILS_FILENAME).write_text("x" * 10)
            gp = str(kit_dir / cw.GUARDRAILS_FILENAME)
            records = self._evicted_records(model_id, gp)
            calls, _sc, _notes = cw.claude_call_weights(records)

            md = cw.render_constraints_markdown(
                cw.build_constraints_card(kit_dir, records, calls, session_id="sess-p"))
            self.assertIn(cw.CONSTRAINTS_PHASE_ANCHOR_NOTE, md)
            self.assertIn("PHASE STARTS", cw.CONSTRAINTS_PHASE_ANCHOR_NOTE)
            self.assertIn("`session`", cw.CONSTRAINTS_PHASE_ANCHOR_NOTE)

            section = cw.build_audit_constraints_section(
                kit_dir, cw.DEFAULT_SURFACE_BUDGET_TOKENS, records=records, calls=calls,
            )
            audit_md = cw._render_audit_constraints_section(section)
            self.assertIn("INFERRED compaction", audit_md)
            self.assertIn(cw.CONSTRAINTS_PHASE_ANCHOR_NOTE, audit_md)


class ConstraintsReadOnlyTests(unittest.TestCase):
    def test_fixture_tree_unchanged_after_a_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_id = _first_sonnet_model()
            kit_dir = Path(tmp) / "kit"
            kit_dir.mkdir()
            (kit_dir / cw.GUARDRAILS_FILENAME).write_text("x" * 10)
            projects_dir = Path(tmp) / "projects"
            _write_claude_fixture(projects_dir, model_id)

            before = _snapshot_tree(tmp)
            _run_main([
                "constraints", "--kit", str(kit_dir),
                "--projects-dir", str(projects_dir), "--json",
            ])
            after = _snapshot_tree(tmp)
            self.assertEqual(before, after)


# ---- 18. `audit --kit` — the constraints residency section on the resident-surface audit -------


class AuditConstraintsSectionTests(unittest.TestCase):
    def test_section_without_session_omits_residency_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit_dir = Path(tmp) / "kit"
            kit_dir.mkdir()
            (kit_dir / cw.GUARDRAILS_FILENAME).write_text("x" * 400)
            section = cw.build_audit_constraints_section(
                kit_dir, cw.DEFAULT_SURFACE_BUDGET_TOKENS,
                session_note="residency requires --session — omitted",
            )
            self.assertTrue(section["file"]["present"])
            self.assertEqual(section["file"]["est_tokens"], 100)
            self.assertIsNone(section["residency"])
            self.assertEqual(section["session_note"], "residency requires --session — omitted")

    def test_section_with_session_computes_residency(self):
        model_id = _first_sonnet_model()
        with tempfile.TemporaryDirectory() as tmp:
            kit_dir = Path(tmp) / "kit"
            kit_dir.mkdir()
            (kit_dir / cw.GUARDRAILS_FILENAME).write_text("x" * 10)
            guardrails_path = str(kit_dir / cw.GUARDRAILS_FILENAME)
            records = [
                _assistant_record("g1", model_id, 1000, 0, 0, 10, 0,
                                   tool_use={"id": "t1", "name": "Read",
                                             "input": {"file_path": guardrails_path}}),
                _user_tool_result("t1", "g" * 400, 1),
            ]
            calls, _sc, _notes = cw.claude_call_weights(records)
            section = cw.build_audit_constraints_section(
                kit_dir, cw.DEFAULT_SURFACE_BUDGET_TOKENS, records=records, calls=calls,
            )
            self.assertIsNotNone(section["residency"])
            self.assertTrue(section["residency"]["resident"])
            self.assertEqual(section["residency"]["current_weight_est_tokens"], 100)

    def test_absent_guardrails_file_on_disk(self):
        section = cw.build_audit_constraints_section(
            "/does/not/exist/kit", cw.DEFAULT_SURFACE_BUDGET_TOKENS,
        )
        self.assertFalse(section["file"]["present"])

    def test_cli_audit_with_kit_and_session_shows_resident_yes(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_id = _first_sonnet_model()
            project_dir = _audit_fixture(Path(tmp) / "proj")
            kit_dir = Path(tmp) / "kit"
            kit_dir.mkdir()
            (kit_dir / cw.GUARDRAILS_FILENAME).write_text("x" * 10)
            guardrails_path = str(kit_dir / cw.GUARDRAILS_FILENAME)

            projects_dir = Path(tmp) / "projects"
            proj = projects_dir / "demo-proj"
            proj.mkdir(parents=True)
            records = [
                _assistant_record("g1", model_id, 1000, 0, 0, 10, 0,
                                   tool_use={"id": "t1", "name": "Read",
                                             "input": {"file_path": guardrails_path}}),
                _user_tool_result("t1", "g" * 400, 1),
            ]
            (proj / "sess.jsonl").write_text(
                "\n".join(json.dumps(r) for r in records) + "\n"
            )

            rc, out = _run_main([
                "audit", "--project", str(project_dir),
                "--kit", str(kit_dir), "--session", "sess",
                "--projects-dir", str(projects_dir),
            ])
            self.assertEqual(rc, 0)
            self.assertIn("## Constraints (GUARDRAILS.md residency)", out)
            self.assertIn("resident: YES", out)
            self.assertNotIn("$", out)

    def test_cli_audit_with_kit_no_session_shows_omitted_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = _audit_fixture(Path(tmp) / "proj")
            kit_dir = Path(tmp) / "kit"
            kit_dir.mkdir()
            (kit_dir / cw.GUARDRAILS_FILENAME).write_text("x" * 10)

            rc, out = _run_main(["audit", "--project", str(project_dir), "--kit", str(kit_dir)])
            self.assertEqual(rc, 0)
            self.assertIn("## Constraints (GUARDRAILS.md residency)", out)
            self.assertIn("residency requires --session — omitted", out)

    def test_no_kit_flag_omits_section_entirely(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = _audit_fixture(Path(tmp) / "proj")
            rc, out = _run_main(["audit", "--project", str(project_dir)])
            self.assertEqual(rc, 0)
            self.assertNotIn("Constraints (GUARDRAILS.md residency)", out)


if __name__ == "__main__":
    unittest.main()
