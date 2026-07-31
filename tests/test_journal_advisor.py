"""Stdlib unittest regression suite for the T5/T6 harness-advisor work (PLAN.md D5/D6/D7 of
the journal-augment kit): bin/journal_advisor.py's build_harness_signal, its wiring into
bin/journal_collect.py's signals.harness / signals.harness_error, and the two pinned prompt
revisions in bin/journal_summarize.py's build_prompts.

SAFETY CONTRACT (binds every test in this file): no test here ever reads or writes the real
``~/.claude``, ``~/.copilot``, or ``~/.codex`` home directories, and no test here calls the
stdlib home-directory helper. Every collector end-to-end fixture in this file lives under a
fresh ``tempfile.TemporaryDirectory()`` with every root flag (``--claude-projects``/
``--copilot-home``/``--codex-home``/``--kits-dir``/``--journal-dir``) explicitly overridden and
``--utc`` passed, so day membership never depends on the machine's timezone or its real home
directory. Every advisor unit test in this file feeds SYNTHETIC pricing dicts (fake model ids
such as ``"fake-haiku-1"``/``"fake-codex-mid"``) straight into ``build_harness_signal`` --
never a real model id, and this file never opens a real ``data/`` pricing file itself (the
collector end-to-end tests DO cause ``journal_collect.py`` to open the real pricing files
internally -- sanctioned config reuse, mirroring ``tests/test_journal_collect.py``). No test
here invokes a real ``claude``/``copilot``/``codex`` CLI binary, and no test here imports any
binary-database or network module.

bin/ is not a package; journal_advisor.py, journal_collect.py, journal_summarize.py,
copilot_pricing.py, and codex_pricing.py are loaded via importlib by absolute path computed
from this file's own location (BIN_DIR), mirroring tests/test_journal_codex_augment.py and
tests/test_journal_askpack.py.
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


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ja = _load("journal_advisor")
jc = _load("journal_collect")
jsz = _load("journal_summarize")
cp = _load("copilot_pricing")
cxp = _load("codex_pricing")


# ---- synthetic pricing fixtures (fake ids/values only -- never a real model id) --------------

CLAUDE_PRICING = {
    "cache_read_multiplier": 0.1,
    "task_profiles": {
        "S": {"input_tokens": 2000, "output_tokens": 500},
        "M": {"input_tokens": 8000, "output_tokens": 2000},
    },
    "models": {
        # Two haiku-tier fakes, in this order -- proves the FIRST one wins the "cheap" slot.
        "fake-haiku-1": {"tier": "haiku", "input_per_mtok": 1.0, "output_per_mtok": 5.0},
        "fake-haiku-2": {"tier": "haiku", "input_per_mtok": 1.5, "output_per_mtok": 6.0},
        "fake-sonnet-1": {"tier": "sonnet", "input_per_mtok": 3.0, "output_per_mtok": 15.0},
    },
}

# No "sonnet"-tier model at all -- the "mid" claude slot must resolve to None + a note.
CLAUDE_PRICING_NO_MID = {
    "cache_read_multiplier": 0.1,
    "task_profiles": {
        "S": {"input_tokens": 2000, "output_tokens": 500},
        "M": {"input_tokens": 8000, "output_tokens": 2000},
    },
    "models": {
        "fake-haiku-1": {"tier": "haiku", "input_per_mtok": 1.0, "output_per_mtok": 5.0},
    },
}

COPILOT_PRICING = {
    "billing_unit": {"usd_per_credit": 0.04},
    "task_profiles": {
        "S": {"input_tokens": 2000, "output_tokens": 500},
        "M": {"input_tokens": 8000, "output_tokens": 2000},
    },
    "models": {
        "fake-copilot-cheap": {
            "tier": "cheap", "input_per_mtok": 1.0, "cached_input_per_mtok": 0.1,
            "output_per_mtok": 5.0,
        },
        "fake-copilot-mid": {
            "tier": "mid", "input_per_mtok": 3.0, "cached_input_per_mtok": 0.3,
            "output_per_mtok": 15.0,
        },
    },
}

# No "mid"-tier model at all -- the "mid" copilot slot must resolve to None + a note.
COPILOT_PRICING_CHEAP_ONLY = {
    "billing_unit": {"usd_per_credit": 0.04},
    "task_profiles": {
        "S": {"input_tokens": 2000, "output_tokens": 500},
        "M": {"input_tokens": 8000, "output_tokens": 2000},
    },
    "models": {
        "fake-copilot-cheap": {
            "tier": "cheap", "input_per_mtok": 1.0, "cached_input_per_mtok": 0.1,
            "output_per_mtok": 5.0,
        },
    },
}

# Deliberately NO "cheap"-tier model -- proves codex_pricing.resolve_tier's skip-up rule (the
# advisor's "cheap" slot must resolve UP to "mid", exactly what resolve_tier itself returns).
CODEX_PRICING = {
    "cached_date": "2026-01-01",
    "cache_read_multiplier": 0.1,
    "task_profiles": {
        "S": {"input_tokens": 2000, "output_tokens": 500},
        "M": {"input_tokens": 8000, "output_tokens": 2000},
    },
    "models": {
        "fake-codex-mid": {"tier": "mid", "input_per_mtok": 2.0, "output_per_mtok": 10.0},
    },
}

# No models at all -- both codex slots must resolve to None + a note (a truly unpopulated
# roster, as opposed to the skip-up case above which DOES resolve).
CODEX_PRICING_EMPTY = {
    "cached_date": "2026-01-01",
    "cache_read_multiplier": 0.1,
    "task_profiles": {
        "S": {"input_tokens": 2000, "output_tokens": 500},
        "M": {"input_tokens": 8000, "output_tokens": 2000},
    },
    "models": {},
}


# ---- 1. shape ----------------------------------------------------------------------------

class ShapeTests(unittest.TestCase):
    def test_pinned_top_level_keys_and_advisory_flag(self):
        sig = ja.build_harness_signal({}, CLAUDE_PRICING, COPILOT_PRICING, CODEX_PRICING)
        self.assertEqual(
            set(sig), {"advisory", "note", "profiles", "cache_hit", "harnesses", "notes"})
        self.assertIs(sig["advisory"], True)
        self.assertEqual(sig["note"], ja.ADVISORY_NOTE)
        self.assertEqual(sig["profiles"], list(ja.ADVISOR_PROFILES))
        self.assertEqual(sig["cache_hit"], ja.ADVISOR_CACHE_HIT)
        self.assertEqual(set(sig["harnesses"]), {"claude_code", "copilot_cli", "codex_cli"})

    def test_command_templates_match_verbatim_with_placeholder_intact(self):
        sig = ja.build_harness_signal({}, CLAUDE_PRICING, COPILOT_PRICING, CODEX_PRICING)
        for harness, template in ja.COMMAND_TEMPLATES.items():
            self.assertEqual(sig["harnesses"][harness]["command_template"], template)
            self.assertIn("{model}", template)


# ---- 2. estimate math reuse ----------------------------------------------------------------

class EstimateMathReuseTests(unittest.TestCase):
    def setUp(self):
        self.sig = ja.build_harness_signal({}, CLAUDE_PRICING, COPILOT_PRICING, CODEX_PRICING)

    def test_copilot_estimate_matches_direct_est_cost_call(self):
        slot = self.sig["harnesses"]["copilot_cli"]["est"]["S"]["cheap"]
        expected = cp.est_cost(
            COPILOT_PRICING, "S", "fake-copilot-cheap", cache_hit=ja.ADVISOR_CACHE_HIT)
        self.assertEqual(slot["model"], "fake-copilot-cheap")
        self.assertAlmostEqual(slot["usd_est"], expected["usd"], places=9)
        self.assertAlmostEqual(slot["aic_est"], expected["aic"], places=9)

    def test_codex_estimate_matches_direct_est_cost_call_and_is_never_a_bill(self):
        slot = self.sig["harnesses"]["codex_cli"]["est"]["S"]["mid"]
        expected = cxp.est_cost(
            CODEX_PRICING, "S", "fake-codex-mid", cache_hit=ja.ADVISOR_CACHE_HIT)
        self.assertEqual(slot["model"], "fake-codex-mid")
        self.assertAlmostEqual(slot["usd_api_equivalent"], expected["usd_api"], places=9)
        self.assertIsNone(slot["billed_usd"])

    def test_claude_estimate_matches_documented_formula(self):
        slot = self.sig["harnesses"]["claude_code"]["est"]["S"]["cheap"]
        p = CLAUDE_PRICING["task_profiles"]["S"]
        model = CLAUDE_PRICING["models"]["fake-haiku-1"]
        cache_hit = ja.ADVISOR_CACHE_HIT
        cache_read_mult = CLAUDE_PRICING["cache_read_multiplier"]
        expected_usd = (
            p["input_tokens"]
            * ((1 - cache_hit) * model["input_per_mtok"]
               + cache_hit * model["input_per_mtok"] * cache_read_mult)
            / 1e6
            + p["output_tokens"] / 1e6 * model["output_per_mtok"]
        )
        self.assertEqual(slot["model"], "fake-haiku-1")
        self.assertAlmostEqual(slot["usd_est"], expected_usd, places=9)


# ---- 3. slot resolution --------------------------------------------------------------------

class SlotResolutionTests(unittest.TestCase):
    def test_claude_cheap_slot_picks_first_haiku_model_in_file_order(self):
        sig = ja.build_harness_signal({}, CLAUDE_PRICING, COPILOT_PRICING, CODEX_PRICING)
        self.assertEqual(
            sig["harnesses"]["claude_code"]["est"]["S"]["cheap"]["model"], "fake-haiku-1")

    def test_codex_cheap_slot_follows_resolve_tier_skip_up(self):
        sig = ja.build_harness_signal({}, CLAUDE_PRICING, COPILOT_PRICING, CODEX_PRICING)
        expected = cxp.resolve_tier(CODEX_PRICING, "cheap")
        # Sanity: this fixture really has no "cheap"-tier model, so `expected` is proof the
        # skip-up rule fired, not a coincidence of matching tier words.
        self.assertEqual(expected, "fake-codex-mid")
        self.assertEqual(sig["harnesses"]["codex_cli"]["est"]["S"]["cheap"]["model"], expected)


# ---- 4. degradation, never fabrication ------------------------------------------------------

class DegradationNeverFabricationTests(unittest.TestCase):
    def test_pricing_none_yields_est_none_and_pricing_unavailable_note(self):
        sig = ja.build_harness_signal({}, None, None, None)
        for harness in ("claude_code", "copilot_cli", "codex_cli"):
            self.assertIsNone(sig["harnesses"][harness]["est"])
        notes = sig["notes"]
        self.assertTrue(
            any(n.startswith("claude_code:") and "pricing unavailable" in n for n in notes))
        self.assertTrue(
            any(n.startswith("copilot_cli:") and "pricing unavailable" in n for n in notes))
        self.assertTrue(
            any(n.startswith("codex_cli:") and "pricing unavailable" in n for n in notes))

    def test_missing_report_degrades_honestly_never_fabricated(self):
        sig = ja.build_harness_signal({}, CLAUDE_PRICING, COPILOT_PRICING, CODEX_PRICING)
        for harness in ("claude_code", "copilot_cli", "codex_cli"):
            h = sig["harnesses"][harness]
            self.assertFalse(h["available_today"])
            self.assertEqual(h["sessions_today"], 0)
            self.assertIsNone(h["usd_today"])

    def test_unpopulated_tier_yields_none_slot_and_note(self):
        sig = ja.build_harness_signal(
            {}, CLAUDE_PRICING_NO_MID, COPILOT_PRICING_CHEAP_ONLY, CODEX_PRICING_EMPTY)
        self.assertIsNone(sig["harnesses"]["claude_code"]["est"]["S"]["mid"])
        self.assertIsNone(sig["harnesses"]["copilot_cli"]["est"]["S"]["mid"])
        self.assertIsNone(sig["harnesses"]["codex_cli"]["est"]["S"]["cheap"])
        self.assertIsNone(sig["harnesses"]["codex_cli"]["est"]["S"]["mid"])
        notes = sig["notes"]
        self.assertTrue(any("no sonnet-tier model" in n for n in notes))
        self.assertTrue(any("no mid-tier model" in n for n in notes))
        self.assertTrue(any("no model at or above tier" in n for n in notes))

    def test_unknown_profile_yields_none_slot_and_note_across_harnesses(self):
        sig = ja.build_harness_signal(
            {}, CLAUDE_PRICING, COPILOT_PRICING, CODEX_PRICING, profiles=("S", "ZZZ"))
        self.assertIsNone(sig["harnesses"]["claude_code"]["est"]["ZZZ"]["cheap"])
        self.assertIsNone(sig["harnesses"]["copilot_cli"]["est"]["ZZZ"]["cheap"])
        self.assertIsNone(sig["harnesses"]["codex_cli"]["est"]["ZZZ"]["mid"])
        notes = sig["notes"]
        self.assertTrue(any("unknown task profile" in n and "'ZZZ'" in n for n in notes))
        self.assertTrue(any("unknown profile in pricing.copilot.json" in n for n in notes))
        self.assertTrue(any("unknown profile in pricing.codex.json" in n for n in notes))

    def test_empty_reports_dict_all_three_entries_present_nothing_raises(self):
        sig = ja.build_harness_signal({}, CLAUDE_PRICING, COPILOT_PRICING, CODEX_PRICING)
        self.assertEqual(set(sig["harnesses"]), {"claude_code", "copilot_cli", "codex_cli"})


# ---- 5. codex passthrough honesty -----------------------------------------------------------

class CodexPassthroughHonestyTests(unittest.TestCase):
    def test_proxy_today_equals_total_while_usd_today_stays_none(self):
        reports = {
            "codex_cli": {
                "available": True, "sessions": 2, "usd": None,
                "extra": {"codex_proxy": {"billed_usd": None,
                                           "api_equivalent_usd_total": 0.87}},
            },
        }
        sig = ja.build_harness_signal(reports, CLAUDE_PRICING, COPILOT_PRICING, CODEX_PRICING)
        codex = sig["harnesses"]["codex_cli"]
        self.assertIsNone(codex["usd_today"])
        self.assertEqual(codex["proxy_today"], 0.87)

    def test_proxy_today_is_none_without_a_proxy(self):
        reports = {"codex_cli": {"available": True, "sessions": 1, "usd": None, "extra": {}}}
        sig = ja.build_harness_signal(reports, CLAUDE_PRICING, COPILOT_PRICING, CODEX_PRICING)
        self.assertIsNone(sig["harnesses"]["codex_cli"]["proxy_today"])


# ---- 6. collector wiring ----------------------------------------------------------------------

class CollectorWiringTests(unittest.TestCase):
    def _prep_root(self, root):
        for name in ("claude", "copilot", "codex", "kits"):
            (root / name).mkdir(parents=True, exist_ok=True)
        return root

    def _argv(self, root):
        return [
            "--date", "2026-04-01", "--utc",
            "--claude-projects", str(root / "claude"),
            "--copilot-home", str(root / "copilot"),
            "--codex-home", str(root / "codex"),
            "--kits-dir", str(root / "kits"),
            "--journal-dir", str(root / "journal"),
        ]

    def _call_main(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = jc.main(argv)
        return rc, buf.getvalue()

    def test_digest_carries_signals_harness_with_advisory_true(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._prep_root(Path(td))
            rc, _out = self._call_main(self._argv(root))
            self.assertEqual(rc, 0)
            digest = json.loads((root / "journal" / "2026-04-01" / "digest.json").read_text())
            harness = digest["signals"]["harness"]
            self.assertIs(harness["advisory"], True)
            self.assertEqual(
                set(harness["harnesses"]), {"claude_code", "copilot_cli", "codex_cli"})
            self.assertNotIn("harness_error", digest["signals"])

    def test_advisor_crash_degrades_to_harness_error_and_exit_zero(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._prep_root(Path(td))
            with mock.patch.object(
                jc.ja, "build_harness_signal",
                side_effect=RuntimeError("synthetic advisor crash"),
            ):
                rc, _out = self._call_main(self._argv(root))
            self.assertEqual(rc, 0)
            digest = json.loads((root / "journal" / "2026-04-01" / "digest.json").read_text())
            self.assertNotIn("harness", digest["signals"])
            self.assertIn("harness_error", digest["signals"])
            self.assertIn("advisor failed", digest["signals"]["harness_error"])


# ---- 7. prompt revisions ----------------------------------------------------------------------

SAMPLE_DIGEST = {
    "schema_version": 1,
    "date": "2026-05-01",
    "generated_at": "2026-05-01T05:00:00+00:00",
    "day_start": "2026-05-01T00:00:00+00:00",
    "day_end": "2026-05-02T00:00:00+00:00",
    "timezone": "UTC",
    "sources": {
        "codex_cli": {
            "source": "codex_cli", "available": True, "priced": False, "usd": None,
            "sessions": 1,
            "extra": {
                "codex_proxy": {
                    "billed_usd": None,
                    "api_equivalent_usd_total": 0.42,
                    "by_model": {"fake-codex-mid": 0.42},
                    "approx_attribution": False,
                    "disclaimer": "Figures are API-equivalent dollars.",
                    "pricing_cached_date": "2026-01-01",
                },
            },
        },
    },
    "totals": {
        "usd_priced": 0.0, "sessions": 1,
        "sources_active": ["codex_cli"], "unpriced_sources": ["codex_cli"],
    },
    "signals": {
        "kit_tasks": [], "inbox": {"present": False, "items": []}, "wip": [],
        "harness": {"advisory": True, "harnesses": {}},
    },
}


class PromptRevisionTests(unittest.TestCase):
    def test_technical_prompt_carries_labeled_proxy_exception(self):
        prompts = jsz.build_prompts(SAMPLE_DIGEST)
        self.assertIn("api_equivalent_usd_total", prompts["technical"])
        self.assertIn("not a bill", prompts["technical"])

    def test_next_day_prompt_carries_harness_plan_after_how_to_run(self):
        next_day = jsz.build_prompts(SAMPLE_DIGEST)["next_day"]
        self.assertIn("## Harness plan", next_day)
        self.assertLess(next_day.index("## How to run"), next_day.index("## Harness plan"))

    def test_three_legacy_h2_orderings_hold_in_both_prompts(self):
        prompts = jsz.build_prompts(SAMPLE_DIGEST)
        technical = prompts["technical"]
        self.assertLess(technical.index("## Sessions & cost"), technical.index("## Models"))
        self.assertLess(technical.index("## Models"), technical.index("## Repos & commits"))

        next_day = prompts["next_day"]
        self.assertLess(next_day.index("## Start here"), next_day.index("## To-dos"))
        self.assertLess(next_day.index("## To-dos"), next_day.index("## How to run"))

    def test_narrative_prompt_does_not_contain_harness_plan(self):
        narrative = jsz.build_prompts(SAMPLE_DIGEST)["narrative"]
        self.assertNotIn("Harness plan", narrative)


if __name__ == "__main__":
    unittest.main()
