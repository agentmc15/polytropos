"""Stdlib unittest regression suite for bin/journal_plan.py (PLAN.md D1, D3-D8 of the
next-day-runbook kit -- the dated, checkable next-day plan with per-harness commands).

SAFETY CONTRACT (binds every test in this file): no test here reads or writes any real home
directory (the stdlib home-directory helper is never called), no test here launches an
external process or reaches the network, and no test here opens any binary session-store
file. Every fixture -- plan directories, digests, seed files -- lives under a fresh
``tempfile.TemporaryDirectory()`` per test, ``journal_plan.main`` is always driven in-process
(never as a separately launched program) with every root flag pointed at those temp
fixtures, and every CLI call passes ``--utc`` wherever day membership matters.

NO FABRICATION, NO HARDCODING: every asserted model id in the CLI end-to-end tests is
derived from ``data/pricing.json`` at run time via the same reuse load journal_plan.py
itself uses (``cr.load_pricing()``) -- never a literal model id. Unit tests that exercise
the pure harness-composition functions build a synthetic advisor-signal dict with clearly
fake ids (``fake-haiku-1`` and friends) -- sanctioned synthetic fixture values, never real
ones.

bin/ is not a package; journal_plan.py is loaded via importlib by absolute path computed
from this file's own location (BIN_DIR), mirroring tests/test_journal_askpack.py.
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


mod = _load("journal_plan")


def _call_main(argv):
    """Run mod.main(argv) in-process with stdout captured -> (rc, stdout_text).

    mod.main's error paths call ``sys.exit(<message>)`` and never launch a child program; the
    resulting SystemExit is caught here and its code (usually a string message) is returned as
    ``rc`` so callers can assert both "it failed" (truthy) and the message content.
    """
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = mod.main(argv)
    except SystemExit as e:
        rc = e.code
    return rc, buf.getvalue()


def _card(title, source="inbox", model_hint="none", how="1. do it",
          due="2026-02-05", first_planned="2026-02-05", checked=False,
          deferred_to=None, harness=""):
    """A synthetic id-less card dict with the pinned key set (mirrors _new_card's shape
    without reaching into that private helper -- built from the public field contract)."""
    return {
        "id": None,
        "checked": checked,
        "title": title,
        "source": source,
        "due": due,
        "first_planned": first_planned,
        "model_hint": model_hint,
        "deferred_to": deferred_to,
        "how": how,
        "harness": harness,
    }


def make_signal(*, claude_cheap=None, claude_mid=None,
                 copilot_cheap=None, copilot_mid=None,
                 codex_cheap=None, codex_mid=None):
    """A synthetic advisor-signal dict shaped like journal_advisor.build_harness_signal's
    result -- only the keys compose_harness_block actually reads (command_template + est).
    Fake ids like "fake-haiku-1" are the sanctioned synthetic fixture values."""
    def est_block(cheap, mid):
        if cheap is None and mid is None:
            return None
        return {mod.EST_PROFILE: {"cheap": cheap, "mid": mid}}

    return {
        "harnesses": {
            "claude_code": {
                "command_template": 'claude -p --model {model} "<task>"',
                "est": est_block(claude_cheap, claude_mid),
            },
            "copilot_cli": {
                "command_template": 'copilot --model {model} -p "<task>"',
                "est": est_block(copilot_cheap, copilot_mid),
            },
            "codex_cli": {
                "command_template": 'codex exec --model {model} --full-auto "<task>"',
                "est": est_block(codex_cheap, codex_mid),
            },
        },
    }


# ---- 1. grammar round-trip: render -> parse -> re-render is byte-identical -------------------

class RoundTripTests(unittest.TestCase):
    def test_render_parse_rerender_reproduces_bytes_with_full_signal(self):
        signal = make_signal(
            claude_mid={"model": "fake-sonnet-1", "usd_est": 0.05},
            copilot_mid={"model": "fake-cop-1", "usd_est": 0.03, "aic_est": 3.0},
            codex_mid={"model": "fake-cx-1", "usd_api_equivalent": 0.02, "billed_usd": None},
        )
        digest = {"signals": {
            "kit_tasks": [{"kit": "demo", "id": "T1", "title": "Do thing",
                           "status": "pending", "model": "sonnet"}],
            "wip": [{"repo": "demo", "branch": "main", "dirty_files": 1, "untracked": 0}],
            "inbox": {"items": ["Email Sam"]},
        }}
        cards, notes = mod.assemble_cards(digest, ["seed line"], [], "2026-02-01")
        text = mod.render_plan("2026-02-01", "2026-01-31", cards, notes, signal)

        parsed = mod.parse_plan(text)
        self.assertEqual(parsed["date"], "2026-02-01")
        self.assertEqual(len(parsed["cards"]), 4)

        # Re-render with signal=None: since every parsed card already carries a real id
        # (was_new is False for all of them), no Harness block is recomposed -- the parsed
        # text is reproduced byte-for-byte, proving the parse/render round trip is faithful.
        rerendered = mod.render_plan("2026-02-01", "2026-01-31", parsed["cards"],
                                     parsed["notes"], None)
        self.assertEqual(text, rerendered)

    def test_round_trip_preserves_checkbox_deferred_and_bodies(self):
        cards = [
            _card("Task A", source="seed", checked=True, model_hint="sonnet",
                  first_planned="2026-01-20", due="2026-02-01",
                  how="1. do a\n2. verify a"),
            _card("Task B", source="inbox", deferred_to="2026-02-10",
                  how="1. do b"),
        ]
        text = mod.render_plan("2026-02-01", None, cards, [], None)
        parsed = mod.parse_plan(text)

        self.assertTrue(parsed["cards"][0]["checked"])
        self.assertEqual(parsed["cards"][0]["how"], "1. do a\n2. verify a")
        self.assertIsNone(parsed["cards"][0]["deferred_to"])
        self.assertFalse(parsed["cards"][1]["checked"])
        self.assertEqual(parsed["cards"][1]["deferred_to"], "2026-02-10")

        rerendered = mod.render_plan("2026-02-01", None, parsed["cards"], [], None)
        self.assertEqual(text, rerendered)

    def test_notes_section_round_trips_only_when_present(self):
        cards = [_card("Solo task")]
        text_no_notes = mod.render_plan("2026-02-01", None, cards, [], None)
        self.assertNotIn(mod._NOTES_HEADING, text_no_notes)

        text_with_notes = mod.render_plan("2026-02-01", None, cards,
                                          ["a degradation note"], None)
        self.assertIn("## Notes", text_with_notes)
        self.assertIn("- a degradation note", text_with_notes)
        parsed = mod.parse_plan(text_with_notes)
        self.assertEqual(parsed["notes"], ["a degradation note"])


# ---- 2. card building: kit/wip/inbox/seed shapes, tolerance, the MAX_PLAN_CARDS cap ----------

class CardBuildingTests(unittest.TestCase):
    def test_kit_wip_inbox_cards_have_pinned_shape(self):
        digest = {"signals": {
            "kit_tasks": [{"kit": "demo-kit", "id": "T9", "title": "Wire widget",
                           "status": "pending", "model": "sonnet"}],
            "wip": [{"repo": "myrepo", "branch": "main", "dirty_files": 2, "untracked": 1}],
            "inbox": {"items": ["Call Sam"]},
        }}
        cards = mod.cards_from_digest(digest, "2026-02-05")
        self.assertEqual(len(cards), 3)
        kit_card, wip_card, inbox_card = cards

        self.assertEqual(kit_card["title"], "demo-kit/T9 — Wire widget")
        self.assertEqual(kit_card["source"], "kit:demo-kit/T9")
        self.assertEqual(kit_card["model_hint"], "sonnet")
        self.assertIn(".claude/kits/demo-kit/TASKS.md", kit_card["how"])
        self.assertIn("/polytropos:execute demo-kit", kit_card["how"])

        self.assertEqual(wip_card["title"], "Resume uncommitted work in myrepo (main)")
        self.assertEqual(wip_card["source"], "wip:myrepo")
        self.assertEqual(wip_card["model_hint"], "none")
        self.assertIn("git status", wip_card["how"])
        self.assertIn("2 dirty and 1 untracked", wip_card["how"])

        self.assertEqual(inbox_card["title"], "Call Sam")
        self.assertEqual(inbox_card["source"], "inbox")
        self.assertIn("1. Call Sam", inbox_card["how"])
        self.assertIn("Refine this card during enrichment", inbox_card["how"])

        for c in cards:
            self.assertEqual(c["due"], "2026-02-05")
            self.assertEqual(c["first_planned"], "2026-02-05")
            self.assertFalse(c["checked"])
            self.assertIsNone(c["deferred_to"])
            self.assertIsNone(c["id"])

    def test_kit_task_model_not_a_known_tier_falls_back_to_none_hint(self):
        digest = {"signals": {"kit_tasks": [
            {"kit": "k", "id": "T1", "title": "x", "status": "pending", "model": "haiku"},
            {"kit": "k", "id": "T2", "title": "y", "status": "pending", "model": None},
            {"kit": "k", "id": "T3", "title": "z", "status": "pending", "model": "frontier"},
        ]}}
        cards = mod.cards_from_digest(digest, "2026-02-05")
        self.assertEqual([c["model_hint"] for c in cards], ["haiku", "none", "none"])

    def test_seed_card_shape(self):
        card = mod.card_from_seed("Refill the widget stock", "2026-02-05")
        self.assertEqual(card["title"], "Refill the widget stock")
        self.assertEqual(card["source"], "seed")
        self.assertEqual(card["model_hint"], "none")
        self.assertIn("1. Refill the widget stock", card["how"])
        self.assertIn("Refine this card during enrichment", card["how"])

    def test_none_or_malformed_digest_yields_no_cards_without_crashing(self):
        for bad in (None, {}, {"signals": "oops"}, {"signals": {}}, 42, ["not", "a", "dict"]):
            self.assertEqual(mod.cards_from_digest(bad, "2026-02-05"), [])

    def test_max_plan_cards_cap_adds_a_note(self):
        seeds = [f"seed line {i}" for i in range(mod.MAX_PLAN_CARDS + 5)]
        cards, notes = mod.assemble_cards(None, seeds, [], "2026-02-05")
        self.assertEqual(len(cards), mod.MAX_PLAN_CARDS)
        self.assertTrue(any("card cap reached" in n for n in notes))


# ---- 3. slot + command composition -----------------------------------------------------------

class SlotAndCommandCompositionTests(unittest.TestCase):
    def _signal(self):
        return make_signal(
            claude_cheap={"model": "fake-haiku-1", "usd_est": 0.01},
            claude_mid={"model": "fake-sonnet-1", "usd_est": 0.05},
            copilot_cheap={"model": "fake-cop-cheap", "usd_est": 0.008, "aic_est": 0.8},
            copilot_mid={"model": "fake-cop-1", "usd_est": 0.03, "aic_est": 3.0},
            codex_cheap={"model": "fake-cx-cheap", "usd_api_equivalent": 0.006,
                         "billed_usd": None},
            codex_mid={"model": "fake-cx-1", "usd_api_equivalent": 0.02, "billed_usd": None},
        )

    def test_haiku_hint_uses_cheap_slot_in_all_three_commands(self):
        card = _card("Title", model_hint="haiku")
        block = mod.compose_harness_block(card, self._signal())
        self.assertIn("fake-haiku-1", block)
        self.assertIn("fake-cop-cheap", block)
        self.assertIn("fake-cx-cheap", block)
        self.assertNotIn("fake-sonnet-1", block)
        self.assertNotIn("fake-cop-1", block)
        self.assertNotIn("fake-cx-1", block)

    def test_sonnet_opus_none_hints_use_mid_slot(self):
        sig = self._signal()
        for hint in ("sonnet", "opus", "none"):
            card = _card("Title", model_hint=hint)
            block = mod.compose_harness_block(card, sig)
            self.assertIn("fake-sonnet-1", block, hint)
            self.assertIn("fake-cop-1", block, hint)
            self.assertIn("fake-cx-1", block, hint)
            self.assertNotIn("fake-haiku-1", block, hint)

    def test_opus_hint_appends_the_pinned_slot_note(self):
        card = _card("Title", model_hint="opus")
        block = mod.compose_harness_block(card, self._signal())
        self.assertTrue(block.endswith(mod.OPUS_SLOT_NOTE))

    def test_non_opus_hints_carry_no_slot_note(self):
        for hint in ("haiku", "sonnet", "none"):
            card = _card("Title", model_hint=hint)
            block = mod.compose_harness_block(card, self._signal())
            self.assertNotIn(mod.OPUS_SLOT_NOTE, block, hint)

    def test_title_quotes_and_backticks_stripped_from_task_substitution(self):
        card = _card('Say "hi" `now`   please', model_hint="sonnet")
        block = mod.compose_harness_block(card, self._signal())
        self.assertIn('"Say hi now please"', block)
        self.assertNotIn('"hi"', block)
        self.assertNotIn("`now`", block)

    def test_codex_line_always_labeled_not_a_bill(self):
        card = _card("Title", model_hint="sonnet")
        block = mod.compose_harness_block(card, self._signal())
        codex_line = next(l for l in block.splitlines() if l.startswith("- codex_cli"))
        self.assertIn("API-equivalent — not a bill", codex_line)


# ---- 4. ideal-harness policy (D4) --------------------------------------------------------------

class IdealPolicyTests(unittest.TestCase):
    def test_kit_source_is_structurally_claude_code(self):
        card = _card("demo/T1 — thing", source="kit:demo/T1")
        harness, reason = mod.pick_ideal(card, {
            "claude_code": {"model": "x", "usd_est": 9.0},
            "copilot_cli": {"model": "y", "usd_est": 0.001},
        })
        self.assertEqual(harness, "claude_code")
        self.assertIn("/polytropos:execute", reason)

    def test_cheaper_copilot_wins_with_both_figures_named_and_codex_excluded(self):
        card = _card("Task", source="inbox")
        harness, reason = mod.pick_ideal(card, {
            "claude_code": {"model": "x", "usd_est": 0.05},
            "copilot_cli": {"model": "y", "usd_est": 0.03},
            "codex_cli": {"model": "z", "usd_api_equivalent": 0.0001},
        })
        self.assertEqual(harness, "copilot_cli")
        self.assertIn("0.0500", reason)
        self.assertIn("0.0300", reason)
        self.assertIn("not a bill", reason)

    def test_cheaper_claude_wins(self):
        card = _card("Task", source="inbox")
        harness, _reason = mod.pick_ideal(card, {
            "claude_code": {"model": "x", "usd_est": 0.02},
            "copilot_cli": {"model": "y", "usd_est": 0.09},
        })
        self.assertEqual(harness, "claude_code")

    def test_only_claude_estimate_available_wins_by_default(self):
        card = _card("Task", source="inbox")
        harness, reason = mod.pick_ideal(card, {
            "claude_code": {"model": "x", "usd_est": 0.02}, "copilot_cli": None,
        })
        self.assertEqual(harness, "claude_code")
        self.assertIn("only harness", reason)

    def test_only_copilot_estimate_available_wins_by_default(self):
        card = _card("Task", source="inbox")
        harness, reason = mod.pick_ideal(card, {
            "claude_code": None, "copilot_cli": {"model": "y", "usd_est": 0.02},
        })
        self.assertEqual(harness, "copilot_cli")
        self.assertIn("only harness", reason)

    def test_no_estimates_falls_back_to_pinned_default(self):
        card = _card("Task", source="inbox")
        harness, reason = mod.pick_ideal(
            card, {"claude_code": None, "copilot_cli": None})
        self.assertEqual(harness, "claude_code")
        self.assertIn("default", reason)

    def test_codex_never_ideal_even_when_its_figure_is_cheapest(self):
        card = _card("Task", source="inbox")
        harness, _reason = mod.pick_ideal(card, {
            "claude_code": {"model": "x", "usd_est": 0.09},
            "copilot_cli": {"model": "y", "usd_est": 0.08},
            "codex_cli": {"model": "z", "usd_api_equivalent": 0.00001},
        })
        self.assertNotEqual(harness, "codex_cli")


# ---- 5. degradation honesty --------------------------------------------------------------------

class DegradationHonestyTests(unittest.TestCase):
    def test_none_signal_is_the_pinned_single_line(self):
        self.assertEqual(mod.compose_harness_block(_card("Task"), None), mod.NO_SIGNAL_LINE)

    def test_all_none_est_signal_degrades_to_the_pinned_line(self):
        signal = make_signal()  # every harness's est is None
        self.assertEqual(mod.compose_harness_block(_card("Task"), signal), mod.NO_SIGNAL_LINE)

    def test_missing_slot_renders_est_na_with_no_command_and_no_model_id(self):
        # Only claude has an estimate; copilot/codex have none at all for this profile.
        signal = make_signal(claude_mid={"model": "fake-sonnet-1", "usd_est": 0.05})
        block = mod.compose_harness_block(_card("Task", model_hint="sonnet"), signal)

        self.assertIn(f"- copilot_cli: {mod.EST_NA}", block)
        self.assertIn(f"- codex_cli: {mod.EST_NA}", block)
        self.assertNotIn("copilot_cli (", block)
        self.assertNotIn("codex_cli (", block)

        copilot_line = next(l for l in block.splitlines() if l.startswith("- copilot_cli"))
        codex_line = next(l for l in block.splitlines() if l.startswith("- codex_cli"))
        # never a fabricated dollar figure standing in for an unknown estimate
        self.assertNotIn("$", copilot_line)
        self.assertNotIn("$", codex_line)

    def test_partial_slot_within_a_harness_also_degrades_honestly(self):
        # cheap slot present, mid slot absent -- a haiku-hint card is fine, a sonnet-hint
        # card (which needs the mid slot) must degrade rather than borrow the cheap figure.
        signal = make_signal(claude_cheap={"model": "fake-haiku-1", "usd_est": 0.01})
        block = mod.compose_harness_block(_card("Task", model_hint="sonnet"), signal)
        claude_line = next(l for l in block.splitlines() if l.startswith("- claude_code"))
        self.assertIn(mod.EST_NA, claude_line)
        self.assertNotIn("fake-haiku-1", claude_line)
        self.assertNotIn("$", claude_line)


# ---- 6. carry-forward (D5) ----------------------------------------------------------------------

class CarryForwardTests(unittest.TestCase):
    def test_unchecked_card_carries_with_first_planned_preserved_and_due_updated(self):
        with tempfile.TemporaryDirectory() as td:
            plan_dir = Path(td) / "plan"
            plan_dir.mkdir()
            card = _card("Old task", how="1. do it\n2. verify",
                         due="2026-01-10", first_planned="2026-01-10")
            (plan_dir / "2026-01-10.md").write_text(
                mod.render_plan("2026-01-10", None, [card], [], None))
            original_bytes = (plan_dir / "2026-01-10.md").read_bytes()

            carried, notes = mod.collect_carry(plan_dir, "2026-01-12")
            self.assertEqual(len(carried), 1)
            self.assertEqual(notes, [])
            self.assertEqual(carried[0]["first_planned"], "2026-01-10")
            self.assertEqual(carried[0]["due"], "2026-01-12")
            self.assertIsNone(carried[0]["id"])
            self.assertFalse(carried[0]["checked"])
            self.assertEqual(carried[0]["how"], "1. do it\n2. verify")

            # historical file untouched by collect_carry
            self.assertEqual((plan_dir / "2026-01-10.md").read_bytes(), original_bytes)

            # ... and untouched by a subsequent build too (byte-snapshot proof)
            journal_dir = Path(td)
            rc, _ = _call_main(["build", "--date", "2026-01-11", "--utc",
                                "--journal-dir", str(journal_dir)])
            self.assertEqual(rc, 0)
            self.assertEqual((plan_dir / "2026-01-10.md").read_bytes(), original_bytes)

            rebuilt = mod.parse_plan((plan_dir / "2026-01-12.md").read_text())
            self.assertEqual(len(rebuilt["cards"]), 1)
            self.assertEqual(rebuilt["cards"][0]["first_planned"], "2026-01-10")
            self.assertEqual(rebuilt["cards"][0]["due"], "2026-01-12")

    def test_checked_card_does_not_carry(self):
        with tempfile.TemporaryDirectory() as td:
            plan_dir = Path(td) / "plan"
            plan_dir.mkdir()
            card = _card("Done already", checked=True)
            (plan_dir / "2026-01-10.md").write_text(
                mod.render_plan("2026-01-10", None, [card], [], None))
            carried, _ = mod.collect_carry(plan_dir, "2026-01-12")
            self.assertEqual(carried, [])

    def test_deferred_card_excluded_until_its_own_deferred_date_arrives(self):
        with tempfile.TemporaryDirectory() as td:
            plan_dir = Path(td) / "plan"
            plan_dir.mkdir()
            card = _card("Deferred task", deferred_to="2026-01-20")
            (plan_dir / "2026-01-10.md").write_text(
                mod.render_plan("2026-01-10", None, [card], [], None))

            carried_early, _ = mod.collect_carry(plan_dir, "2026-01-12")
            self.assertEqual(carried_early, [])

            carried_later, _ = mod.collect_carry(plan_dir, "2026-01-20")
            self.assertEqual(len(carried_later), 1)
            self.assertIsNone(carried_later[0]["deferred_to"])


# ---- 7. latest-occurrence dedup (D5, the double-reporting guard) -------------------------------

class LatestOccurrenceDedupTests(unittest.TestCase):
    def test_same_key_in_two_files_carries_once_with_the_later_hows(self):
        with tempfile.TemporaryDirectory() as td:
            plan_dir = Path(td) / "plan"
            plan_dir.mkdir()
            older = _card("Recurring task", how="1. old how")
            newer = _card("Recurring task", how="1. NEW how (enriched)")
            (plan_dir / "2026-01-05.md").write_text(
                mod.render_plan("2026-01-05", None, [older], [], None))
            (plan_dir / "2026-01-08.md").write_text(
                mod.render_plan("2026-01-08", None, [newer], [], None))

            carried, _ = mod.collect_carry(plan_dir, "2026-01-10")
            self.assertEqual(len(carried), 1)
            self.assertIn("NEW how (enriched)", carried[0]["how"])

    def test_check_reports_the_duplicate_key_exactly_once(self):
        with tempfile.TemporaryDirectory() as td:
            plan_dir = Path(td) / "plan"
            plan_dir.mkdir()
            older = _card("Recurring task")
            newer = _card("Recurring task")
            (plan_dir / "2026-01-05.md").write_text(
                mod.render_plan("2026-01-05", None, [older], [], None))
            (plan_dir / "2026-01-08.md").write_text(
                mod.render_plan("2026-01-08", None, [newer], [], None))

            rows, _ = mod.check_cards(plan_dir, "2026-01-10")
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]["handle"].startswith("2026-01-08/"))


# ---- 8. merge preservation (D6) -----------------------------------------------------------------

class MergePreservationTests(unittest.TestCase):
    def test_merge_preserves_state_and_appends_next_id(self):
        existing = [_card("Old card A"), _card("Old card B")]
        existing[0]["id"] = "R1"
        existing[0]["checked"] = True
        existing[1]["id"] = "R2"
        existing[1]["how"] = "1. MARKER ENRICHED BODY"

        new = [_card("Old card B"), _card("Brand new card")]

        merged, refresh = mod.merge_cards(existing, new)
        ids = [c["id"] for c in merged]
        self.assertEqual(ids[:2], ["R1", "R2"])
        self.assertEqual(ids[2], "R3")
        self.assertTrue(merged[0]["checked"])
        self.assertEqual(merged[1]["how"], "1. MARKER ENRICHED BODY")
        self.assertEqual(merged[2]["title"], "Brand new card")

        self.assertIn("R2", refresh)     # matched by an incoming card -> refresh
        self.assertIn("R3", refresh)     # newly appended -> refresh
        self.assertNotIn("R1", refresh)  # unmatched existing card -> NOT refreshed

    def test_unmatched_existing_card_is_never_dropped(self):
        existing = [_card("Stale card")]
        existing[0]["id"] = "R1"
        merged, refresh = mod.merge_cards(existing, [])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["id"], "R1")
        self.assertNotIn("R1", refresh)


class MergePreservationCliTests(unittest.TestCase):
    def test_full_rebuild_cycle_preserves_checkbox_and_enriched_body_and_appends_new_card(self):
        with tempfile.TemporaryDirectory() as td:
            journal_dir = Path(td)
            date_str = "2026-03-01"
            for_date = "2026-03-02"
            digest_dir = journal_dir / date_str
            digest_dir.mkdir(parents=True)
            digest = {"signals": {
                "kit_tasks": [{"kit": "demo", "id": "T1", "title": "First kit task",
                               "status": "pending", "model": "sonnet"}],
                "wip": [], "inbox": {"items": ["Reply to Sam"]},
            }}
            (digest_dir / "digest.json").write_text(json.dumps(digest))

            rc, _ = _call_main(["build", "--date", date_str, "--utc",
                                "--journal-dir", str(journal_dir)])
            self.assertEqual(rc, 0)
            plan_path = journal_dir / "plan" / f"{for_date}.md"
            self.assertTrue(plan_path.is_file())

            parsed = mod.parse_plan(plan_path.read_text())
            self.assertEqual(len(parsed["cards"]), 2)  # kit task + inbox item
            kit_id = next(c["id"] for c in parsed["cards"] if c["source"].startswith("kit:"))
            inbox_id = next(c["id"] for c in parsed["cards"] if c["source"] == "inbox")

            # mark the kit card done, and hand-enrich the inbox card's What/How
            text = mod.mark_done(plan_path.read_text(), kit_id)
            text = text.replace(
                "1. Reply to Sam\n"
                "2. Refine this card during enrichment, then check it off once finished.",
                "1. MARKER ENRICHED STEP ONE\n2. MARKER ENRICHED STEP TWO",
            )
            plan_path.write_text(text)

            # add a second kit task to the digest, then rebuild the SAME due date
            digest["signals"]["kit_tasks"].append(
                {"kit": "demo", "id": "T2", "title": "Second kit task",
                 "status": "pending", "model": "haiku"})
            (digest_dir / "digest.json").write_text(json.dumps(digest))

            rc, _ = _call_main(["build", "--date", date_str, "--utc",
                                "--for", for_date, "--journal-dir", str(journal_dir)])
            self.assertEqual(rc, 0)

            rebuilt = mod.parse_plan(plan_path.read_text())
            by_id = {c["id"]: c for c in rebuilt["cards"]}
            self.assertEqual(len(by_id), 3)  # 2 preserved + 1 new -- no duplicates

            self.assertTrue(by_id[kit_id]["checked"])
            self.assertIn("MARKER ENRICHED STEP ONE", by_id[inbox_id]["how"])
            self.assertIn("MARKER ENRICHED STEP TWO", by_id[inbox_id]["how"])

            new_ids = set(by_id) - {kit_id, inbox_id}
            self.assertEqual(len(new_ids), 1)
            new_card = by_id[next(iter(new_ids))]
            self.assertIn("Second kit task", new_card["title"])


# ---- 9. seeds (D7) ------------------------------------------------------------------------------

class SeedsTests(unittest.TestCase):
    def test_seed_lines_become_seed_cards_and_the_seed_file_is_never_written(self):
        with tempfile.TemporaryDirectory() as td:
            journal_dir = Path(td)
            plan_dir = journal_dir / "plan"
            plan_dir.mkdir(parents=True)
            seed_text = "# seeds\n- Water the plants\n* Call the bank\n[ ] Renew the license\n\n"
            (plan_dir / "seed.md").write_text(seed_text)
            original_bytes = (plan_dir / "seed.md").read_bytes()

            rc, _ = _call_main(["build", "--date", "2026-04-01", "--utc",
                                "--journal-dir", str(journal_dir)])
            self.assertEqual(rc, 0)
            self.assertEqual((plan_dir / "seed.md").read_bytes(), original_bytes)

            plan_path = plan_dir / "2026-04-02.md"
            parsed = mod.parse_plan(plan_path.read_text())
            titles = sorted(c["title"] for c in parsed["cards"])
            self.assertEqual(titles, ["Call the bank", "Renew the license", "Water the plants"])
            self.assertTrue(all(c["source"] == "seed" for c in parsed["cards"]))

            # a rebuild does not duplicate the seed cards, and seed.md stays untouched
            rc, _ = _call_main(["build", "--date", "2026-04-01", "--utc",
                                "--journal-dir", str(journal_dir)])
            self.assertEqual(rc, 0)
            reparsed = mod.parse_plan(plan_path.read_text())
            self.assertEqual(len(reparsed["cards"]), 3)
            self.assertEqual((plan_dir / "seed.md").read_bytes(), original_bytes)


# ---- 10. check classification (D5) ---------------------------------------------------------------

class CheckClassificationTests(unittest.TestCase):
    def test_empty_store_returns_the_honest_message_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            rc, out = _call_main(["check", "--date", "2026-05-01", "--utc",
                                  "--journal-dir", str(td)])
            self.assertEqual(rc, 0)
            self.assertIn("no runbook cards due for 2026-05-01", out)

    def test_due_overdue_future_and_deferred_to_today_classification(self):
        with tempfile.TemporaryDirectory() as td:
            plan_dir = Path(td) / "plan"
            plan_dir.mkdir()

            (plan_dir / "2026-05-01.md").write_text(
                mod.render_plan("2026-05-01", None, [_card("Overdue task")], [], None))
            (plan_dir / "2026-05-05.md").write_text(
                mod.render_plan("2026-05-05", None, [_card("Due today task")], [], None))
            (plan_dir / "2026-05-10.md").write_text(
                mod.render_plan("2026-05-10", None, [_card("Future task")], [], None))
            deferred_card = _card("Deferred-to-today task", deferred_to="2026-05-05")
            (plan_dir / "2026-04-20.md").write_text(
                mod.render_plan("2026-04-20", None, [deferred_card], [], None))

            rows, _ = mod.check_cards(plan_dir, "2026-05-05")
            titles = {r["title"]: r for r in rows}

            self.assertTrue(titles["Overdue task"]["overdue"])
            self.assertEqual(titles["Overdue task"]["handle"], "2026-05-01/R1")

            self.assertFalse(titles["Due today task"]["overdue"])
            self.assertNotIn("Future task", titles)

            self.assertFalse(titles["Deferred-to-today task"]["overdue"])
            self.assertEqual(titles["Deferred-to-today task"]["effective_due"], "2026-05-05")

    def test_rogue_non_date_file_in_plan_dir_gets_a_note(self):
        with tempfile.TemporaryDirectory() as td:
            plan_dir = Path(td) / "plan"
            plan_dir.mkdir()
            (plan_dir / "notes-random.md").write_text("not a plan file")
            rows, notes = mod.check_cards(plan_dir, "2026-05-05")
            self.assertEqual(rows, [])
            self.assertTrue(any("notes-random.md" in n for n in notes))

    def test_check_cli_prints_the_handle_format(self):
        with tempfile.TemporaryDirectory() as td:
            journal_dir = Path(td)
            plan_dir = journal_dir / "plan"
            plan_dir.mkdir()
            (plan_dir / "2026-05-01.md").write_text(
                mod.render_plan("2026-05-01", None, [_card("Some task")], [], None))
            rc, out = _call_main(["check", "--date", "2026-05-01", "--utc",
                                  "--journal-dir", str(journal_dir)])
            self.assertEqual(rc, 0)
            self.assertIn("[2026-05-01/R1]", out)
            self.assertIn("DUE 2026-05-01", out)


# ---- 11. done/defer via main() ------------------------------------------------------------------

class DoneDeferCliTests(unittest.TestCase):
    def _seed_plan(self, journal_dir, date_str, title="Some task"):
        plan_dir = journal_dir / "plan"
        plan_dir.mkdir(parents=True, exist_ok=True)
        path = plan_dir / f"{date_str}.md"
        path.write_text(mod.render_plan(date_str, None, [_card(title)], [], None))
        return path

    def test_done_happy_path_rewrites_only_the_addressed_file(self):
        with tempfile.TemporaryDirectory() as td:
            journal_dir = Path(td)
            other_path = self._seed_plan(journal_dir, "2026-06-01", "Other date task")
            target_path = self._seed_plan(journal_dir, "2026-06-02", "Target task")
            other_before = other_path.read_bytes()

            rc, out = _call_main(["done", "R1", "--date", "2026-06-02", "--utc",
                                  "--journal-dir", str(journal_dir)])
            self.assertEqual(rc, 0)
            self.assertIn("[2026-06-02/R1]", out)
            self.assertIn("### [x] R1", target_path.read_text())
            self.assertEqual(other_path.read_bytes(), other_before)

    def test_defer_happy_path_adds_the_deferred_to_line(self):
        with tempfile.TemporaryDirectory() as td:
            journal_dir = Path(td)
            target_path = self._seed_plan(journal_dir, "2026-06-05")
            rc, out = _call_main(["defer", "R1", "--to", "2026-06-20",
                                  "--date", "2026-06-05", "--utc",
                                  "--journal-dir", str(journal_dir)])
            self.assertEqual(rc, 0)
            self.assertIn("deferred to 2026-06-20", out)
            self.assertIn("- deferred-to: 2026-06-20", target_path.read_text())

    def test_unknown_id_exits_nonzero_with_a_useful_message(self):
        with tempfile.TemporaryDirectory() as td:
            journal_dir = Path(td)
            self._seed_plan(journal_dir, "2026-06-08")
            rc, _out = _call_main(["done", "R99", "--date", "2026-06-08", "--utc",
                                   "--journal-dir", str(journal_dir)])
            self.assertTrue(rc)
            self.assertIn("R99", str(rc))

    def test_missing_file_exits_nonzero_with_a_useful_message(self):
        with tempfile.TemporaryDirectory() as td:
            journal_dir = Path(td)
            rc, _out = _call_main(["done", "R1", "--date", "2026-06-09", "--utc",
                                   "--journal-dir", str(journal_dir)])
            self.assertTrue(rc)
            self.assertIn("2026-06-09", str(rc))

    def test_invalid_to_date_rejected_before_any_path_is_composed(self):
        with tempfile.TemporaryDirectory() as td:
            journal_dir = Path(td)
            self._seed_plan(journal_dir, "2026-06-10")
            before = sorted(str(p) for p in journal_dir.rglob("*") if p.is_file())
            rc, _out = _call_main(["defer", "R1", "--to", "not-a-date",
                                   "--date", "2026-06-10", "--utc",
                                   "--journal-dir", str(journal_dir)])
            self.assertTrue(rc)
            after = sorted(str(p) for p in journal_dir.rglob("*") if p.is_file())
            self.assertEqual(before, after)

    def test_invalid_for_date_on_build_rejected_before_any_path_is_composed(self):
        with tempfile.TemporaryDirectory() as td:
            journal_dir = Path(td)
            before = sorted(str(p) for p in journal_dir.rglob("*") if p.is_file())
            rc, _out = _call_main(["build", "--for", "2026-99-99",
                                   "--date", "2026-06-10", "--utc",
                                   "--journal-dir", str(journal_dir)])
            self.assertTrue(rc)
            after = sorted(str(p) for p in journal_dir.rglob("*") if p.is_file())
            self.assertEqual(before, after)


# ---- 12. enrichment prompt ------------------------------------------------------------------------

class EnrichmentPromptTests(unittest.TestCase):
    def test_pinned_header_phrases_present(self):
        prompt = mod.build_enrich_prompt("# Runbook — 2026-07-01\n", None)
        self.assertIn("You are enriching a next-day runbook", prompt)
        self.assertIn("byte-identical", prompt)
        self.assertIn("Nothing here auto-executes", prompt)
        self.assertIn("Respond with ONLY the full revised markdown document.", prompt)

    def test_embeds_the_plan_text_verbatim(self):
        plan_text = "# Runbook — 2026-07-01\n\nSOME UNIQUE MARKER LINE\n"
        prompt = mod.build_enrich_prompt(plan_text, None)
        self.assertIn(plan_text, prompt)

    def test_no_digest_line_when_digest_is_none(self):
        prompt = mod.build_enrich_prompt("text", None)
        self.assertIn("No digest is available for extra context.", prompt)
        self.assertNotIn("Digest (JSON):", prompt)

    def test_digest_json_embedded_when_present(self):
        digest = {"date": "2026-07-01", "signals": {"kit_tasks": []}}
        prompt = mod.build_enrich_prompt("text", digest)
        self.assertIn("Digest (JSON):", prompt)
        self.assertIn(json.dumps(digest, indent=None, separators=(",", ":")), prompt)
        self.assertNotIn("No digest is available", prompt)

    def test_prompt_cli_prints_the_pinned_header_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            journal_dir = Path(td)
            plan_dir = journal_dir / "plan"
            plan_dir.mkdir(parents=True)
            (plan_dir / "2026-07-02.md").write_text(
                mod.render_plan("2026-07-02", None, [_card("A task")], [], None))

            before = sorted(str(p) for p in journal_dir.rglob("*") if p.is_file())
            rc, out = _call_main(["prompt", "--date", "2026-07-01", "--utc",
                                  "--journal-dir", str(journal_dir)])
            self.assertEqual(rc, 0)
            self.assertIn("You are enriching a next-day runbook", out)
            after = sorted(str(p) for p in journal_dir.rglob("*") if p.is_file())
            self.assertEqual(before, after)


# ---- 13. CLI end-to-end, determinism, write-isolation --------------------------------------------

class CliEndToEndDeterminismTests(unittest.TestCase):
    def test_build_writes_only_the_one_plan_file_with_run_time_pricing_model_ids(self):
        with tempfile.TemporaryDirectory() as td:
            journal_dir = Path(td)
            date_str = "2026-08-01"
            for_date = "2026-08-02"
            digest_dir = journal_dir / date_str
            digest_dir.mkdir(parents=True)
            digest = {"signals": {
                "kit_tasks": [{"kit": "demo", "id": "T1", "title": "A kit task",
                               "status": "pending", "model": "sonnet"}],
                "wip": [], "inbox": {"items": []},
            }}
            (digest_dir / "digest.json").write_text(json.dumps(digest))

            before = sorted(str(p) for p in journal_dir.rglob("*") if p.is_file())
            rc, _ = _call_main(["build", "--date", date_str, "--utc",
                                "--journal-dir", str(journal_dir)])
            self.assertEqual(rc, 0)
            after = sorted(str(p) for p in journal_dir.rglob("*") if p.is_file())
            new_files = sorted(set(after) - set(before))
            expected_path = journal_dir / "plan" / f"{for_date}.md"
            self.assertEqual(new_files, [str(expected_path)])

            pricing = mod.cr.load_pricing()
            mid_model = next(m for m, s in pricing["models"].items()
                              if isinstance(s, dict) and s.get("tier") == "sonnet")
            text = expected_path.read_text()
            self.assertIn(mid_model, text)

    def test_two_identical_builds_over_identical_inputs_produce_identical_bytes(self):
        with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
            for td in (td1, td2):
                plan_dir = Path(td) / "plan"
                plan_dir.mkdir(parents=True)
                (plan_dir / "seed.md").write_text("- Do the thing\n")

            rc1, _ = _call_main(["build", "--date", "2026-08-05", "--utc",
                                 "--journal-dir", str(Path(td1))])
            rc2, _ = _call_main(["build", "--date", "2026-08-05", "--utc",
                                 "--journal-dir", str(Path(td2))])
            self.assertEqual(rc1, 0)
            self.assertEqual(rc2, 0)

            b1 = (Path(td1) / "plan" / "2026-08-06.md").read_bytes()
            b2 = (Path(td2) / "plan" / "2026-08-06.md").read_bytes()
            self.assertEqual(b1, b2)

    def test_a_second_build_of_the_same_date_is_also_byte_identical(self):
        with tempfile.TemporaryDirectory() as td:
            journal_dir = Path(td)
            plan_dir = journal_dir / "plan"
            plan_dir.mkdir(parents=True)
            (plan_dir / "seed.md").write_text("- Refill the demo fixtures\n")

            rc, _ = _call_main(["build", "--date", "2026-09-01", "--utc",
                                "--journal-dir", str(journal_dir)])
            self.assertEqual(rc, 0)
            first_bytes = (plan_dir / "2026-09-02.md").read_bytes()

            rc, _ = _call_main(["build", "--date", "2026-09-01", "--utc",
                                "--journal-dir", str(journal_dir)])
            self.assertEqual(rc, 0)
            second_bytes = (plan_dir / "2026-09-02.md").read_bytes()

            self.assertEqual(first_bytes, second_bytes)


if __name__ == "__main__":
    unittest.main()
