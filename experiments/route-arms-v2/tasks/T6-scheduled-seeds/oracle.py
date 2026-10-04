import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "route_oracle_journal_plan", ROOT / "bin" / "journal_plan.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load()


def _call_main(argv):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = mod.main(argv)
    except SystemExit as exc:
        rc = exc.code
    return rc, buf.getvalue()


def _build(seed_text, for_date="2026-03-09", as_of="2026-03-01"):
    with tempfile.TemporaryDirectory() as td:
        journal_dir = Path(td)
        plan_dir = journal_dir / "plan"
        plan_dir.mkdir(parents=True)
        (plan_dir / "seed.md").write_text(seed_text)
        rc, out = _call_main([
            "build", "--date", as_of, "--utc", "--for", for_date,
            "--journal-dir", str(journal_dir),
        ])
        plan_path = plan_dir / f"{for_date}.md"
        text = plan_path.read_text() if plan_path.exists() else ""
        parsed = mod.parse_plan(text) if text else {"cards": [], "notes": []}
        return rc, out, parsed, text


def _titles(parsed):
    return [c["title"] for c in parsed["cards"]]


def _invalid_notes(parsed):
    return [n for n in parsed["notes"] if n.startswith("invalid seed directive")]


class BackwardCompatibilityTests(unittest.TestCase):
    def test_plain_seed_still_builds_a_seed_card(self):
        rc, _out, parsed, _text = _build("- Water plants\n")
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), ["Water plants"])
        self.assertEqual(parsed["cards"][0]["source"], "seed")

    def test_plain_seed_what_how_is_unchanged(self):
        rc, _out, parsed, _text = _build("Call Sam\n")
        self.assertEqual(rc, 0)
        self.assertEqual(
            parsed["cards"][0]["how"],
            "1. Call Sam\n2. Refine this card during enrichment, then check it off once finished.",
        )

    def test_existing_list_markers_are_stripped_before_scheduling(self):
        rc, _out, parsed, _text = _build("* on 2026-03-09: Pay tax\n")
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), ["Pay tax"])

    def test_blank_lines_and_comments_are_silent(self):
        rc, _out, parsed, _text = _build("\n# skip me\n  \n- Keep me\n")
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), ["Keep me"])
        self.assertEqual(_invalid_notes(parsed), [])


class OneTimeDirectiveTests(unittest.TestCase):
    def test_on_date_includes_exact_target(self):
        rc, _out, parsed, _text = _build("on 2026-03-09: File report\n")
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), ["File report"])

    def test_on_date_excludes_before_target(self):
        rc, _out, parsed, _text = _build("on 2026-03-10: File report\n", "2026-03-09")
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), [])

    def test_on_date_excludes_after_target(self):
        rc, _out, parsed, _text = _build("on 2026-03-08: File report\n", "2026-03-09")
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), [])

    def test_on_leap_day_includes_in_leap_year(self):
        rc, _out, parsed, _text = _build("on 2024-02-29: Leap review\n", "2024-02-29")
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), ["Leap review"])

    def test_on_invalid_calendar_date_adds_note(self):
        rc, _out, parsed, _text = _build("on 2025-02-29: Bad leap\n", "2025-02-28")
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), [])
        self.assertIn(
            "invalid seed directive in seed.md line 1: invalid date '2025-02-29'",
            parsed["notes"],
        )

    def test_on_missing_colon_adds_shape_note(self):
        rc, _out, parsed, _text = _build("on 2026-03-09 Missing colon\n")
        self.assertEqual(rc, 0)
        self.assertIn(
            "invalid seed directive in seed.md line 1: expected 'on YYYY-MM-DD: title'",
            parsed["notes"],
        )

    def test_on_empty_title_adds_missing_title_note(self):
        rc, _out, parsed, _text = _build("on 2026-03-09:    \n")
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), [])
        self.assertIn(
            "invalid seed directive in seed.md line 1: missing title",
            parsed["notes"],
        )


class IntervalDirectiveTests(unittest.TestCase):
    def test_from_every_one_day_includes_start_date(self):
        rc, _out, parsed, _text = _build(
            "from 2026-03-09 every 1d: Daily review\n", "2026-03-09"
        )
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), ["Daily review"])

    def test_from_every_two_days_includes_divisible_difference(self):
        rc, _out, parsed, _text = _build(
            "from 2026-03-01 every 2d: Alternating review\n", "2026-03-05"
        )
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), ["Alternating review"])

    def test_from_every_two_days_excludes_non_divisible_difference(self):
        rc, _out, parsed, _text = _build(
            "from 2026-03-01 every 2d: Alternating review\n", "2026-03-04"
        )
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), [])

    def test_from_excludes_before_start_date(self):
        rc, _out, parsed, _text = _build(
            "from 2026-03-10 every 1d: Daily review\n", "2026-03-09"
        )
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), [])

    def test_from_month_and_year_rollover_uses_real_dates(self):
        rc, _out, parsed, _text = _build(
            "from 2025-12-31 every 2d: Year boundary\n", "2026-01-02"
        )
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), ["Year boundary"])

    def test_from_leap_year_difference_uses_real_dates(self):
        rc, _out, parsed, _text = _build(
            "from 2024-02-28 every 2d: Leap cadence\n", "2024-03-01"
        )
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), ["Leap cadence"])

    def test_from_zero_interval_adds_note(self):
        rc, _out, parsed, _text = _build("from 2026-03-01 every 0d: Bad\n")
        self.assertEqual(rc, 0)
        self.assertIn(
            "invalid seed directive in seed.md line 1: interval must be 1..366 days",
            parsed["notes"],
        )

    def test_from_too_large_interval_adds_note(self):
        rc, _out, parsed, _text = _build("from 2026-03-01 every 367d: Bad\n")
        self.assertEqual(rc, 0)
        self.assertIn(
            "invalid seed directive in seed.md line 1: interval must be 1..366 days",
            parsed["notes"],
        )

    def test_from_malformed_shape_adds_note(self):
        rc, _out, parsed, _text = _build("from 2026-03-01 daily: Bad\n")
        self.assertEqual(rc, 0)
        self.assertIn(
            "invalid seed directive in seed.md line 1: expected 'from YYYY-MM-DD every Nd: title'",
            parsed["notes"],
        )


class WeekdayDirectiveTests(unittest.TestCase):
    def test_every_monday_includes_monday(self):
        rc, _out, parsed, _text = _build("every mon: Weekly review\n", "2026-03-09")
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), ["Weekly review"])

    def test_every_monday_excludes_tuesday(self):
        rc, _out, parsed, _text = _build("every mon: Weekly review\n", "2026-03-10")
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), [])

    def test_every_weekend_list_includes_sunday(self):
        rc, _out, parsed, _text = _build("every sat,sun: Weekend review\n", "2026-03-15")
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), ["Weekend review"])

    def test_every_weekday_list_allows_spaces_and_case(self):
        rc, _out, parsed, _text = _build("EVERY  Mon, WED : Mixed case\n", "2026-03-11")
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), ["Mixed case"])

    def test_every_unknown_weekday_adds_note(self):
        rc, _out, parsed, _text = _build("every monday: Bad weekday\n")
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), [])
        self.assertIn(
            "invalid seed directive in seed.md line 1: unknown weekday 'monday'",
            parsed["notes"],
        )

    def test_every_missing_colon_adds_shape_note(self):
        rc, _out, parsed, _text = _build("every mon Missing colon\n")
        self.assertEqual(rc, 0)
        self.assertIn(
            "invalid seed directive in seed.md line 1: expected 'every mon[,tue...]: title'",
            parsed["notes"],
        )


class IntegrationSemanticsTests(unittest.TestCase):
    def test_directive_prefix_is_stripped_from_title_and_what_how(self):
        rc, _out, parsed, _text = _build("on 2026-03-09: Trim me\n")
        self.assertEqual(rc, 0)
        card = parsed["cards"][0]
        self.assertEqual(card["title"], "Trim me")
        self.assertNotIn("on 2026-03-09", card["how"])
        self.assertIn("1. Trim me", card["how"])

    def test_mixed_seed_order_is_preserved_for_included_cards(self):
        seed = "Plain first\non 2026-03-10: Not today\nevery mon: Weekly second\non 2026-03-09: Exact third\n"
        rc, _out, parsed, _text = _build(seed, "2026-03-09")
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), ["Plain first", "Weekly second", "Exact third"])

    def test_invalid_line_does_not_abort_valid_cards(self):
        seed = "on 2026-99-99: Bad\nKeep building\n"
        rc, _out, parsed, _text = _build(seed)
        self.assertEqual(rc, 0)
        self.assertEqual(_titles(parsed), ["Keep building"])
        self.assertEqual(len(_invalid_notes(parsed)), 1)

    def test_invalid_note_renders_in_notes_section(self):
        rc, _out, _parsed, text = _build("every funday: Bad\n")
        self.assertEqual(rc, 0)
        self.assertIn("## Notes", text)
        self.assertIn("- invalid seed directive in seed.md line 1: unknown weekday 'funday'", text)

    def test_physical_line_numbers_count_comments_and_blanks(self):
        seed = "# heading\n\n- on 2026-99-99: Bad\n"
        rc, _out, parsed, _text = _build(seed)
        self.assertEqual(rc, 0)
        self.assertIn(
            "invalid seed directive in seed.md line 3: invalid date '2026-99-99'",
            parsed["notes"],
        )

    def test_scheduled_seed_uses_seed_source_and_none_model_hint(self):
        rc, _out, parsed, _text = _build("every mon: Check invoices\n", "2026-03-09")
        self.assertEqual(rc, 0)
        card = parsed["cards"][0]
        self.assertEqual(card["source"], "seed")
        self.assertEqual(card["model_hint"], "none")

    def test_existing_carried_card_wins_over_due_scheduled_seed_by_stripped_title(self):
        with tempfile.TemporaryDirectory() as td:
            journal_dir = Path(td)
            plan_dir = journal_dir / "plan"
            plan_dir.mkdir(parents=True)
            old_card = {
                "id": "R7", "checked": False, "title": "Carry me", "source": "seed",
                "due": "2026-03-08", "first_planned": "2026-03-08",
                "model_hint": "none", "deferred_to": None,
                "how": "1. ENRICHED BODY", "harness": "",
            }
            (plan_dir / "2026-03-08.md").write_text(
                mod.render_plan("2026-03-08", None, [old_card], [], None)
            )
            (plan_dir / "seed.md").write_text("on 2026-03-09: Carry me\n")
            rc, _out = _call_main([
                "build", "--date", "2026-03-08", "--utc", "--for", "2026-03-09",
                "--journal-dir", str(journal_dir),
            ])
            self.assertEqual(rc, 0)
            parsed = mod.parse_plan((plan_dir / "2026-03-09.md").read_text())
            self.assertEqual(_titles(parsed), ["Carry me"])
            self.assertEqual(parsed["cards"][0]["first_planned"], "2026-03-08")
            self.assertIn("ENRICHED BODY", parsed["cards"][0]["how"])


if __name__ == "__main__":
    unittest.main()
