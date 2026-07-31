"""Stdlib unittest regression suite for bin/telemetry_snapshot.py (telemetry-store T5).

bin/ is not a package; telemetry_snapshot.py is loaded via importlib by absolute path
computed from this file's own location — the house pattern (tests/test_cost_report.py).

SAFETY CONTRACT (binds every test in this file):

* No real home dir is ever read and the repo's real ``telemetry/`` is never opened, listed,
  or written — not even to check it. Every capture passes temp ``store_dir`` /
  ``projects_dir`` / ``codex_home`` / ``copilot_home`` / ``kits_dir`` explicitly, so no module
  default is ever scanned; the demo-safety test monkeypatches ``DEFAULT_STORE_DIR`` to a temp
  dir rather than inspecting the live store. The two tests that touch a default
  (``test_home_defaults_come_from_the_loaded_modules_own_constants``,
  ``test_store_dir_default_is_the_repo_store``) only COMPARE path constants — they open
  nothing and capture nothing.
* Nothing here invokes a CLI, spawns anything, or reaches the network — the tool under test
  imports sibling builders and calls them in-process, and so do these tests.
* Kit fixtures are synthetic TASKS.md/NOTES.md trees written into a fresh temp dir.
"""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ts = _load("telemetry_snapshot")

PINNED_ENVELOPE_KEYS = {
    "store_schema_version",
    "source",
    "source_schema_version",
    "captured_at",
    "capture_date",
    "period",
    "status",
    "labels",
    "notes",
    "payload",
}

# A kit whose ledger records outcomes but NEVER a session id: there was no dollar evidence to
# lose, so the honest label is quality-only.
QUALITY_ONLY_TASKS = """# TASKS — synth-quality (synthetic)

## Phase 1 — synth

### A1 — a task
- status: done
- model: sonnet
"""
QUALITY_ONLY_NOTES = """# NOTES — synth-quality (synthetic)

outcome: A1 model=sonnet result=pass review=clean
"""

# A kit that DID record a session id whose transcript no longer exists: the evaporation this
# store exists to record. Its label must never be the quality-only one.
EVAPORATED_TASKS = """# TASKS — synth-evaporated (synthetic)

## Phase 1 — synth

### B1 — a task
- status: done
- model: opus
"""
EVAPORATED_NOTES = """# NOTES — synth-evaporated (synthetic)

outcome: B1 model=opus result=pass review=clean
session: synthetic-session-that-never-existed
"""


def _write_kit(kits_dir, slug, tasks_md, notes_md):
    kit = Path(kits_dir) / slug
    kit.mkdir(parents=True, exist_ok=True)
    (kit / "TASKS.md").write_text(tasks_md)
    (kit / "NOTES.md").write_text(notes_md)
    return kit


class _TempWorld:
    """A whole synthetic world: empty temp homes plus a kits dir with the named fixtures."""

    def __init__(self, kits=(("quality", QUALITY_ONLY_TASKS, QUALITY_ONLY_NOTES),)):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for name in ("store", "proj", "codex", "copilot", "kits"):
            (self.root / name).mkdir()
        for slug, tasks_md, notes_md in kits:
            _write_kit(self.root / "kits", slug, tasks_md, notes_md)

    @property
    def store(self):
        return self.root / "store"

    def opts(self, **over):
        base = {
            "projects_dir": self.root / "proj",
            "codex_home": self.root / "codex",
            "copilot_home": self.root / "copilot",
            "kits_dir": self.root / "kits",
            "days": 30,
            "overview_days": 7,
        }
        base.update(over)
        return base

    def argv(self, *extra):
        return [
            "--store-dir", str(self.store),
            "--projects-dir", str(self.root / "proj"),
            "--codex-home", str(self.root / "codex"),
            "--copilot-home", str(self.root / "copilot"),
            "--kits-dir", str(self.root / "kits"),
        ] + list(extra)

    def envelopes(self):
        return {p.parent.name: json.loads(p.read_text())
                for p in self.store.rglob("*.json")}

    def cleanup(self):
        self._tmp.cleanup()


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.world = _TempWorld()
        self.addCleanup(self.world.cleanup)

    def test_five_envelopes_written_all_ok(self):
        summary = ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        self.assertEqual(summary["written"], 5)
        self.assertEqual(summary["ok"], 5)
        self.assertEqual(summary["errors"], 0)
        files = sorted(p.relative_to(self.world.store).as_posix()
                       for p in self.world.store.rglob("*.json"))
        self.assertEqual(files, sorted(f"{s}/2026-03-04.json" for s in ts.SOURCES))
        for source, env in self.world.envelopes().items():
            with self.subTest(source=source):
                self.assertEqual(env["status"], "ok", source)
                self.assertIsInstance(env["payload"], dict)

    def test_registry_is_the_five_pinned_sources(self):
        self.assertEqual(
            set(ts.SOURCES),
            {"cost_report", "codex_usage", "copilot_usage", "context_overview",
             "routing_history"},
        )

    def test_envelope_key_set_is_exactly_the_ten_pinned_keys(self):
        ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        envs = self.world.envelopes()
        self.assertEqual(len(envs), 5)
        for source, env in envs.items():
            with self.subTest(source=source):
                self.assertEqual(set(env), PINNED_ENVELOPE_KEYS)
                self.assertEqual(env["store_schema_version"], ts.STORE_SCHEMA_VERSION)
                self.assertEqual(env["source"], source)

    def test_envelope_key_order_matches_the_plan(self):
        ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        path = ts.envelope_path(self.world.store, "cost_report", "2026-03-04")
        env = json.loads(path.read_text())
        self.assertEqual(tuple(env), ts.ENVELOPE_KEYS)

    def test_capture_date_equals_filename_stem_and_passed_date(self):
        ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        for path in self.world.store.rglob("*.json"):
            with self.subTest(path=path.name):
                env = json.loads(path.read_text())
                self.assertEqual(env["capture_date"], path.stem)
                self.assertEqual(env["capture_date"], "2026-03-04")
                self.assertRegex(path.name, ts.TELEMETRY_FILENAME_RE)

    def test_default_date_is_the_LOCAL_run_date_not_the_utc_one(self):
        """F5: the filename date keys on the LOCAL day, because the journal flow that runs
        this capture keys its day on ``date.today()``. A UTC default stamped an evening run
        west of Greenwich with TOMORROW's date, splitting one work day across two files.

        Monkeypatch-free on purpose: the assertion is the real default against the real local
        clock, so it fails the moment the default goes back to UTC in any timezone where the
        two dates differ. Local and UTC dates are also asserted to be computed from different
        clocks below (see ``test_captured_at_stays_utc_while_the_filename_is_local``)."""
        expected = datetime.now().strftime("%Y-%m-%d")
        summary = ts.capture(self.world.store, opts=self.world.opts())
        self.assertEqual(summary["capture_date"], expected)
        self.assertTrue(
            ts.envelope_path(self.world.store, "cost_report", expected).is_file())

    def test_captured_at_stays_utc_while_the_filename_is_local(self):
        """The date is local; the instant is not. ``captured_at`` remains a full UTC ISO
        timestamp with a ``+00:00`` offset, so the exact capture moment is unambiguous."""
        fixed = datetime(2031, 12, 25, 9, 30, 15, tzinfo=timezone.utc)
        with mock.patch.object(ts, "_now_utc", return_value=fixed):
            ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        env = json.loads(
            ts.envelope_path(self.world.store, "cost_report", "2026-03-04").read_text())
        self.assertEqual(env["captured_at"], "2031-12-25T09:30:15+00:00")
        self.assertTrue(env["captured_at"].endswith("+00:00"))

    def test_today_str_is_the_naive_local_clock(self):
        """The seam itself: ``_today_str`` reads ``_now_local`` (naive local, the journal's
        ``date.today()`` semantics), never ``_now_utc``."""
        self.assertIsNone(ts._now_local().tzinfo)
        with mock.patch.object(ts, "_now_local", return_value=datetime(2031, 12, 25, 19, 30)):
            self.assertEqual(ts._today_str(), "2031-12-25")

    def test_period_records_the_window_separately_from_the_capture_date(self):
        ts.capture(self.world.store, date="2026-03-04",
                   opts=self.world.opts(days=14, overview_days=3))
        envs = self.world.envelopes()
        for source in ("cost_report", "codex_usage", "copilot_usage"):
            self.assertEqual(envs[source]["period"], {"days": 14}, source)
        self.assertEqual(envs["context_overview"]["period"], {"days": 3})
        self.assertEqual(envs["routing_history"]["period"],
                         {"description": "cumulative kit ledger as of capture"})

    def test_source_schema_version_lifted_from_payload(self):
        ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        for source, env in self.world.envelopes().items():
            with self.subTest(source=source):
                self.assertEqual(env["source_schema_version"],
                                 env["payload"].get("schema_version"))

    def test_every_envelope_is_json_serializable(self):
        summary = ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        json.dumps(summary)
        for path in self.world.store.rglob("*.json"):
            env = json.loads(path.read_text())
            self.assertEqual(json.loads(json.dumps(env)), env)


class HonestyLabelTests(unittest.TestCase):
    """Absence is recorded AS absence — never as a measured zero, never as silence."""

    def setUp(self):
        self.world = _TempWorld()
        self.addCleanup(self.world.cleanup)
        ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        self.envs = self.world.envelopes()

    def test_cost_report_empty_window_is_not_found_and_labelled(self):
        env = self.envs["cost_report"]
        self.assertIs(env["payload"]["found"], False)
        self.assertTrue(
            any("absent" in lab or "no transcripts in window" in lab
                for lab in env["labels"]),
            env["labels"],
        )

    def test_cost_report_estimate_caveat_survives_into_the_envelope(self):
        self.assertTrue(any("est." in lab for lab in self.envs["cost_report"]["labels"]),
                        self.envs["cost_report"]["labels"])

    def test_codex_and_copilot_absence_labels(self):
        for source in ("codex_usage", "copilot_usage"):
            with self.subTest(source=source):
                env = self.envs[source]
                self.assertIs(env["payload"]["found"], False)
                self.assertTrue(any("absent" in lab for lab in env["labels"]), env["labels"])

    def test_context_overview_absent_sections_labelled_mechanically(self):
        env = self.envs["context_overview"]
        self.assertIn("codex section absent", env["labels"])
        self.assertIn("copilot section absent", env["labels"])

    def test_context_overview_found_but_empty_claude_section_is_labelled_empty(self):
        """F2 — ``context_weight`` keys the claude section's ``found`` on the projects
        DIRECTORY existing, so an empty home yields ``found: true, sessions_scanned: 0``.
        Absent and empty are two different truths and get two different labels; an unlabelled
        empty section reads as a measured zero, which is the fabrication this store forbids."""
        env = self.envs["context_overview"]
        claude = env["payload"]["sections"]["claude"]
        self.assertIs(claude["found"], True)
        self.assertEqual(claude["sessions_scanned"], 0)
        self.assertIn("claude section: no sessions in window", env["labels"])
        # Empty is NOT absent — the absence label is never substituted for it.
        self.assertNotIn("claude section absent", env["labels"])

    def test_envelope_labels_are_lifted_not_authored(self):
        for source in ("cost_report", "codex_usage", "copilot_usage"):
            with self.subTest(source=source):
                env = self.envs[source]
                self.assertEqual(env["labels"], env["payload"]["labels"])

    def test_labels_are_never_empty_for_an_absent_source(self):
        for source in ("cost_report", "codex_usage", "copilot_usage", "context_overview",
                       "routing_history"):
            with self.subTest(source=source):
                self.assertTrue(self.envs[source]["labels"], source)


class ContextOverviewLabelTests(unittest.TestCase):
    """F1/F2 — the overview envelope's labels, derived mechanically from documented payload
    fields: the carry-cost caveats the payload itself carries (never authored here) and the
    found-but-empty state that would otherwise render as a measured zero.

    The overview is driven through a SYNTHETIC payload (``build_overview`` patched on the
    loaded sibling module) so the assertions pin the derivation rule, not this machine's home
    dirs. ``bin/context_weight.py`` is untouchable in this kit — the fix lives here, at the
    collector, which is why these tests live here too.
    """

    CARRY_LABEL = "API-equivalent dollars — an estimate, not a bill."
    CODEX_DISCLAIMER = ("Figures are API-equivalent dollars — a relative-burn proxy. "
                        "Subscription (ChatGPT-plan) usage is usage-limited, not "
                        "token-billed.")

    def setUp(self):
        self.world = _TempWorld()
        self.addCleanup(self.world.cleanup)

    def _labels_for(self, sections):
        payload = {"schema_version": 1, "days": 7, "harness_filter": "all",
                   "sections": sections}
        cw = ts._mod("context_weight")
        with mock.patch.object(cw, "build_overview", return_value=payload):
            _payload, _period, labels, _notes = ts.collect_context_overview(
                ts.resolve_opts(self.world.opts()))
        return labels

    def _populated_sections(self):
        return {
            "claude": {
                "harness": "claude", "found": True, "sessions_scanned": 50,
                "carry_cost": {"carry_usd": 266.84, "window_total_usd": 289.45,
                               "pct": 92.1, "label": self.CARRY_LABEL},
            },
            "codex": {
                "harness": "codex", "found": True, "rollouts_scanned": 4,
                "carry_cost": {"carry_usd": 118.47, "disclaimer": self.CODEX_DISCLAIMER,
                               "priced_rollouts": 1, "unpriced_rollouts": 0},
            },
            "copilot": {
                "harness": "copilot", "found": True, "sessions_scanned": 24,
                "carry_cost": {"carry_usd": 62.14, "aic": 6214.4,
                               "label": self.CARRY_LABEL,
                               "priced_sessions": 24, "unpriced_sessions": 0},
            },
        }

    def test_carry_cost_caveats_are_lifted_with_their_harness_prefix(self):
        labels = self._labels_for(self._populated_sections())
        self.assertEqual(labels, [
            f"claude: {self.CARRY_LABEL}",
            f"codex: {self.CODEX_DISCLAIMER}",
            f"copilot: {self.CARRY_LABEL}",
        ])

    def test_dollars_never_ride_without_their_caveat(self):
        """The F1 defect in one assertion: three sections carrying dollar figures produced
        ZERO labels before the fix."""
        sections = self._populated_sections()
        self.assertTrue(all(s["carry_cost"]["carry_usd"] for s in sections.values()))
        labels = self._labels_for(sections)
        self.assertEqual(len(labels), 3)
        for name in ("claude", "codex", "copilot"):
            self.assertTrue(any(lab.startswith(f"{name}: ") and "API-equivalent" in lab
                                for lab in labels), labels)

    def test_identical_caveat_wording_stays_attributed_per_harness(self):
        """claude and copilot emit the SAME caveat string; deduping without the harness
        prefix would collapse two harnesses' caveats into one unattributed line."""
        labels = self._labels_for(self._populated_sections())
        same = [lab for lab in labels if lab.endswith(self.CARRY_LABEL)]
        self.assertEqual(same, [f"claude: {self.CARRY_LABEL}",
                                f"copilot: {self.CARRY_LABEL}"])

    def test_a_repeated_caveat_within_one_section_is_deduped(self):
        sections = self._populated_sections()
        sections["claude"]["carry_cost"]["caveat"] = self.CARRY_LABEL
        labels = self._labels_for(sections)
        self.assertEqual(labels.count(f"claude: {self.CARRY_LABEL}"), 1)

    def test_a_section_with_no_carry_cost_contributes_no_caveat(self):
        sections = self._populated_sections()
        sections["claude"]["carry_cost"] = None
        labels = self._labels_for(sections)
        self.assertFalse(any(lab.startswith("claude: ") for lab in labels), labels)

    def test_populated_sections_get_no_empty_window_label(self):
        labels = self._labels_for(self._populated_sections())
        self.assertFalse(any("no sessions in window" in lab or "no rollouts in window" in lab
                             for lab in labels), labels)

    def test_found_but_zero_scan_counters_are_labelled_per_harness(self):
        sections = self._populated_sections()
        sections["claude"]["sessions_scanned"] = 0
        sections["claude"]["carry_cost"] = None
        sections["codex"]["rollouts_scanned"] = 0
        sections["codex"]["carry_cost"] = None
        labels = self._labels_for(sections)
        self.assertIn("claude section: no sessions in window", labels)
        self.assertIn("codex section: no rollouts in window", labels)
        self.assertNotIn("claude section absent", labels)

    def test_absent_section_gets_the_absence_label_only(self):
        sections = self._populated_sections()
        sections["copilot"] = {"harness": "copilot", "found": False,
                               "sessions_scanned": 0, "carry_cost": None}
        labels = self._labels_for(sections)
        self.assertIn("copilot section absent", labels)
        self.assertNotIn("copilot section: no sessions in window", labels)

    def test_carry_cost_caveat_helper_ignores_non_strings_and_blanks(self):
        self.assertEqual(ts._carry_cost_caveats({"carry_cost": None}), [])
        self.assertEqual(ts._carry_cost_caveats({}), [])
        self.assertEqual(
            ts._carry_cost_caveats({"carry_cost": {"label": "  ", "disclaimer": 12.3}}), [])
        self.assertEqual(
            ts._carry_cost_caveats({"carry_cost": {"caveat": "a", "label": "b"}}),
            ["a", "b"])


class DollarsStateLabelTests(unittest.TestCase):
    """``dollars is None`` has TWO states that mean opposite things (T5 amendment #2).

    Mislabelling the evaporated state as quality-only would be fabricated honesty: it claims
    no dollar evidence ever existed when in fact it existed and was lost.
    """

    def test_quality_only_kit_gets_the_quality_only_label(self):
        world = _TempWorld(kits=(("quality", QUALITY_ONLY_TASKS, QUALITY_ONLY_NOTES),))
        self.addCleanup(world.cleanup)
        ts.capture(world.store, date="2026-03-04", opts=world.opts())
        env = world.envelopes()["routing_history"]
        self.assertIsNone(env["payload"]["dollars"])
        self.assertEqual(env["labels"], ["dollars n/a (quality-only history)"])

    def test_evaporated_kit_gets_the_evaporated_label_not_the_quality_only_one(self):
        world = _TempWorld(kits=(("evaporated", EVAPORATED_TASKS, EVAPORATED_NOTES),))
        self.addCleanup(world.cleanup)
        ts.capture(world.store, date="2026-03-04", opts=world.opts())
        env = world.envelopes()["routing_history"]
        self.assertIsNone(env["payload"]["dollars"])
        self.assertEqual(
            env["labels"],
            ["dollars n/a — sessions recorded but transcripts already evaporated/unpriced"],
        )
        self.assertNotIn("dollars n/a (quality-only history)", env["labels"])
        self.assertTrue(
            any("session: lines found but no transcript priced" in n
                for n in env["payload"]["notes"]),
            env["payload"]["notes"],
        )

    def test_two_states_never_share_a_label(self):
        quality = _TempWorld(kits=(("quality", QUALITY_ONLY_TASKS, QUALITY_ONLY_NOTES),))
        self.addCleanup(quality.cleanup)
        evaporated = _TempWorld(kits=(("evaporated", EVAPORATED_TASKS, EVAPORATED_NOTES),))
        self.addCleanup(evaporated.cleanup)
        ts.capture(quality.store, date="2026-03-04", opts=quality.opts())
        ts.capture(evaporated.store, date="2026-03-04", opts=evaporated.opts())
        a = quality.envelopes()["routing_history"]["labels"]
        b = evaporated.envelopes()["routing_history"]["labels"]
        self.assertNotEqual(a, b)
        self.assertFalse(set(a) & set(b))

    def test_priced_dollars_get_a_coverage_label(self):
        card = {
            "dollars": {"coverage": "partial", "kits_with_sessions": 9, "kits_total": 22},
            "notes": [],
        }
        self.assertEqual(ts._routing_dollars_labels(card),
                         ["dollars coverage: partial (9/22 kits)"])

    def test_dollars_none_with_no_explaining_note_is_never_silently_quality_only(self):
        labels = ts._routing_dollars_labels({"dollars": None, "notes": ["unrelated"]})
        self.assertEqual(labels, ["dollars n/a (no coverage note emitted)"])


class RenderTransportStrippedTests(unittest.TestCase):
    """Render-only ``_``-prefixed transport never lands in the store (T5 amendment #1)."""

    def setUp(self):
        self.world = _TempWorld()
        self.addCleanup(self.world.cleanup)

    def test_no_stored_envelope_has_an_underscore_prefixed_payload_key(self):
        ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        for source, env in self.world.envelopes().items():
            with self.subTest(source=source):
                bad = [k for k in env["payload"] if k.startswith("_")]
                self.assertEqual(bad, [], f"{source} kept render transport: {bad}")

    def test_builders_really_do_emit_render_transport_that_we_strip(self):
        """Guards the strip from becoming a no-op assertion: the raw builder payload for the
        two usage sources carries ``_render``, and the stored payload does not."""
        opts = ts.resolve_opts(self.world.opts())
        raw_copilot, *_ = ts.collect_copilot_usage(opts)
        self.assertIn("_render", raw_copilot)
        ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        self.assertNotIn("_render", self.world.envelopes()["copilot_usage"]["payload"])

    def test_public_payload_keeps_public_keys_and_drops_underscored_ones(self):
        out = ts._public_payload({"a": 1, "_render": {"big": [1, 2]}, "_x": 2})
        self.assertEqual(out, {"a": 1})

    def test_public_payload_passes_none_through(self):
        self.assertIsNone(ts._public_payload(None))


class DateGuardTests(unittest.TestCase):
    """The date is validated FIRST — a bad date never creates a directory or writes a file."""

    def setUp(self):
        self.world = _TempWorld()
        self.addCleanup(self.world.cleanup)

    def test_bad_dates_raise_value_error_before_any_write(self):
        # ``None`` is absent here on purpose: it is the sanctioned "use the run date"
        # sentinel, covered by test_default_date_is_the_utc_run_date.
        for bad in ("2026-7-1", "../evil", "2026-03-04/../..", "", "20260304",
                    "2026-03-04.json", "2026-03-04 ", 20260304):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    ts.capture(self.world.store, date=bad, opts=self.world.opts())
                self.assertEqual(list(self.world.store.rglob("*.json")), [])
                self.assertEqual(list(self.world.store.iterdir()), [])

    def test_traversal_date_never_escapes_the_store(self):
        outside = self.world.root / "outside.json"
        with self.assertRaises(ValueError):
            ts.capture(self.world.store, date="../../outside", opts=self.world.opts())
        self.assertFalse(outside.exists())

    def test_validate_date_accepts_the_grammar_and_returns_it(self):
        self.assertEqual(ts._validate_date("2026-03-04"), "2026-03-04")

    def test_filename_grammar_matches_the_scorecard_snapshot_grammar(self):
        rs = _load("routing_scorecard")
        self.assertEqual(ts.TELEMETRY_FILENAME_RE.pattern, rs.SNAPSHOT_FILENAME_RE.pattern)

    def test_no_backdating_flag_exists_on_the_cli(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            ts.main(["--help"])
        help_text = buf.getvalue()
        self.assertNotIn("--date", help_text)
        self.assertNotIn("--capture-date", help_text)


class OverwriteTests(unittest.TestCase):
    def setUp(self):
        self.world = _TempWorld()
        self.addCleanup(self.world.cleanup)

    def test_same_day_rerun_overwrites_latest_wins(self):
        first = datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        second = datetime(2030, 1, 2, 8, 9, 10, tzinfo=timezone.utc)
        with mock.patch.object(ts, "_now_utc", return_value=first):
            ts.capture(self.world.store, opts=self.world.opts())
        before = sorted(p.relative_to(self.world.store).as_posix()
                        for p in self.world.store.rglob("*.json"))
        stamp_before = self.world.envelopes()["cost_report"]["captured_at"]

        with mock.patch.object(ts, "_now_utc", return_value=second):
            ts.capture(self.world.store, opts=self.world.opts())
        after = sorted(p.relative_to(self.world.store).as_posix()
                       for p in self.world.store.rglob("*.json"))
        stamp_after = self.world.envelopes()["cost_report"]["captured_at"]

        self.assertEqual(before, after)
        self.assertEqual(len(after), 5)
        self.assertEqual(stamp_before, "2030-01-02T03:04:05+00:00")
        self.assertEqual(stamp_after, "2030-01-02T08:09:10+00:00")
        self.assertNotEqual(stamp_before, stamp_after)


class ErrorNeverReplacesOkTests(unittest.TestCase):
    """F3 — the evidence-destruction guard: an error envelope NEVER replaces an ok one.

    Before the fix, a same-day re-run whose collector raised overwrote that day's good
    envelope with ``status: error, payload: null`` — the store's whole reason to exist,
    destroyed by a transient failure. The rule now: ok overwrites anything (latest good
    wins), error may overwrite error, error never overwrites ok, and an unreadable file has
    nothing worth keeping so the new envelope wins with a note.
    """

    def setUp(self):
        self.world = _TempWorld()
        self.addCleanup(self.world.cleanup)

    def _boom(self):
        return mock.patch.object(
            ts, "collect_codex_usage",
            mock.Mock(side_effect=RuntimeError("synthetic collector explosion")))

    def _codex_envelope(self):
        return json.loads(
            ts.envelope_path(self.world.store, "codex_usage", "2026-03-04").read_text())

    def test_ok_then_error_keeps_the_ok_envelope_intact(self):
        ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        good = self._codex_envelope()
        self.assertEqual(good["status"], "ok")
        self.assertIsInstance(good["payload"], dict)

        with self._boom():
            summary = ts.capture(self.world.store, date="2026-03-04",
                                 opts=self.world.opts())

        kept = self._codex_envelope()
        self.assertEqual(kept["status"], "ok")
        self.assertEqual(kept["payload"], good["payload"])
        self.assertEqual(kept["captured_at"], good["captured_at"])
        self.assertEqual(kept["labels"], good["labels"])
        self.assertEqual(kept, good)
        # The failure is recorded in the summary, never in place of the evidence.
        self.assertEqual(summary["kept"], 1)
        self.assertEqual(summary["written"], 4)
        self.assertEqual(summary["errors"], 1)
        self.assertTrue(
            any(n.startswith("kept existing ok envelope for codex_usage; "
                             "new collector error: ") and
                "synthetic collector explosion" in n
                for n in summary["notes"]),
            summary["notes"],
        )

    def test_the_kept_note_reaches_the_rendered_summary(self):
        ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        with self._boom():
            summary = ts.capture(self.world.store, date="2026-03-04",
                                 opts=self.world.opts())
        rendered = ts.render_summary_markdown(summary)
        self.assertIn("kept existing ok envelope for codex_usage", rendered)
        self.assertIn("1 existing ok envelope(s) kept.", rendered)

    def test_ok_then_ok_still_overwrites_latest_good_wins(self):
        first = datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        second = datetime(2030, 1, 2, 8, 9, 10, tzinfo=timezone.utc)
        with mock.patch.object(ts, "_now_utc", return_value=first):
            ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        with mock.patch.object(ts, "_now_utc", return_value=second):
            summary = ts.capture(self.world.store, date="2026-03-04",
                                 opts=self.world.opts())
        env = self._codex_envelope()
        self.assertEqual(env["status"], "ok")
        self.assertEqual(env["captured_at"], "2030-01-02T08:09:10+00:00")
        self.assertEqual(summary["kept"], 0)
        self.assertEqual(summary["written"], 5)

    def test_error_then_error_overwrites(self):
        first = datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        second = datetime(2030, 1, 2, 8, 9, 10, tzinfo=timezone.utc)
        with self._boom(), mock.patch.object(ts, "_now_utc", return_value=first):
            ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        self.assertEqual(self._codex_envelope()["captured_at"],
                         "2030-01-02T03:04:05+00:00")
        with self._boom(), mock.patch.object(ts, "_now_utc", return_value=second):
            summary = ts.capture(self.world.store, date="2026-03-04",
                                 opts=self.world.opts())
        env = self._codex_envelope()
        self.assertEqual(env["status"], "error")
        self.assertIsNone(env["payload"])
        self.assertEqual(env["captured_at"], "2030-01-02T08:09:10+00:00")
        self.assertEqual(summary["kept"], 0)
        self.assertEqual(summary["notes"], [])

    def test_corrupt_existing_file_is_replaced_by_the_error_envelope_with_a_note(self):
        path = ts.envelope_path(self.world.store, "codex_usage", "2026-03-04")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ this is not json at all")
        with self._boom():
            summary = ts.capture(self.world.store, date="2026-03-04",
                                 opts=self.world.opts())
        env = self._codex_envelope()
        self.assertEqual(env["status"], "error")
        self.assertEqual(summary["kept"], 0)
        self.assertEqual(summary["written"], 5)
        self.assertTrue(
            any("replaced unreadable/corrupt existing envelope for codex_usage" in n
                for n in env["notes"]),
            env["notes"],
        )

    def test_non_object_existing_json_is_replaced_by_the_error_envelope(self):
        path = ts.envelope_path(self.world.store, "codex_usage", "2026-03-04")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(["status", "ok"]))
        with self._boom():
            ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        env = self._codex_envelope()
        self.assertEqual(env["status"], "error")
        self.assertTrue(any("replaced unreadable/corrupt" in n for n in env["notes"]),
                        env["notes"])

    def test_existing_ok_classifier_states(self):
        d = self.world.root / "classify"
        d.mkdir()
        self.assertIsNone(ts._existing_ok_envelope(d / "nothing.json"))
        (d / "ok.json").write_text(json.dumps({"status": "ok", "payload": {}}))
        self.assertEqual(ts._existing_ok_envelope(d / "ok.json"), "ok")
        (d / "err.json").write_text(json.dumps({"status": "error", "payload": None}))
        self.assertEqual(ts._existing_ok_envelope(d / "err.json"), "other")
        (d / "junk.json").write_text("nope")
        self.assertEqual(ts._existing_ok_envelope(d / "junk.json"), "unreadable")
        (d / "list.json").write_text("[1, 2]")
        self.assertEqual(ts._existing_ok_envelope(d / "list.json"), "unreadable")

    def test_a_kept_source_still_counts_as_an_error_and_points_at_the_survivor(self):
        ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        with self._boom():
            summary = ts.capture(self.world.store, date="2026-03-04",
                                 opts=self.world.opts())
        row = next(r for r in summary["sources"] if r["source"] == "codex_usage")
        self.assertEqual(set(row), {"source", "status", "labels", "notes", "path"})
        self.assertEqual(row["status"], "error")
        self.assertEqual(
            row["path"],
            str(ts.envelope_path(self.world.store, "codex_usage", "2026-03-04")))
        self.assertEqual(json.loads(Path(row["path"]).read_text())["status"], "ok")


class CollectorFailureTests(unittest.TestCase):
    def setUp(self):
        self.world = _TempWorld()
        self.addCleanup(self.world.cleanup)

    def test_one_failing_collector_still_leaves_five_envelopes(self):
        boom = mock.Mock(side_effect=RuntimeError("synthetic collector explosion"))
        with mock.patch.object(ts, "collect_codex_usage", boom):
            summary = ts.capture(self.world.store, date="2026-03-04",
                                 opts=self.world.opts())
        self.assertEqual(summary["written"], 5)
        self.assertEqual(summary["ok"], 4)
        self.assertEqual(summary["errors"], 1)

        envs = self.world.envelopes()
        self.assertEqual(len(envs), 5)
        bad = envs["codex_usage"]
        self.assertEqual(bad["status"], "error")
        self.assertIsNone(bad["payload"])
        self.assertIsNone(bad["source_schema_version"])
        self.assertEqual(bad["labels"], [])
        self.assertTrue(any("collector failed" in n and "synthetic collector explosion" in n
                            for n in bad["notes"]), bad["notes"])
        self.assertEqual(set(bad), PINNED_ENVELOPE_KEYS)
        # The error envelope still records which window was attempted.
        self.assertEqual(bad["period"], {"days": 30})
        for source in ("cost_report", "copilot_usage", "context_overview", "routing_history"):
            self.assertEqual(envs[source]["status"], "ok", source)

    def test_missing_kits_dir_becomes_an_error_envelope_not_an_empty_ledger(self):
        summary = ts.capture(self.world.store, date="2026-03-04",
                             opts=self.world.opts(kits_dir=self.world.root / "nope"))
        self.assertEqual(summary["errors"], 1)
        env = self.world.envelopes()["routing_history"]
        self.assertEqual(env["status"], "error")
        self.assertIsNone(env["payload"])
        self.assertTrue(any("kits dir not found" in n for n in env["notes"]), env["notes"])

    def test_all_five_failing_still_writes_five_envelopes(self):
        boom = mock.Mock(side_effect=RuntimeError("all down"))
        patches = [mock.patch.object(ts, f"collect_{s}", boom) for s in ts.SOURCES]
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            summary = ts.capture(self.world.store, date="2026-03-04",
                                 opts=self.world.opts())
        self.assertEqual(summary["written"], 5)
        self.assertEqual(summary["ok"], 0)
        self.assertEqual(summary["errors"], 5)
        self.assertEqual(len(self.world.envelopes()), 5)


class MainTests(unittest.TestCase):
    def setUp(self):
        self.world = _TempWorld()
        self.addCleanup(self.world.cleanup)

    def _run(self, argv):
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = ts.main(argv)
        return rc, buf.getvalue(), err.getvalue()

    def test_exit_zero_and_markdown_summary(self):
        rc, out, _ = self._run(self.world.argv())
        self.assertEqual(rc, 0)
        for source in ts.SOURCES:
            self.assertIn(source, out)
        self.assertIn("5 envelope(s) written — 5 ok, 0 error.", out)
        self.assertEqual(len(list(self.world.store.rglob("*.json"))), 5)

    def test_summary_prints_metadata_only_never_payload_contents(self):
        rc, out, _ = self._run(self.world.argv())
        self.assertEqual(rc, 0)
        # Metadata receipt, not a data dump: no payload keys, no JSON body.
        for leak in ("by_model", "totals", "sessions_scanned", "schema_version", '"payload"'):
            self.assertNotIn(leak, out)
        self.assertLess(len(out.splitlines()), 20)

    def test_json_summary_shape(self):
        rc, out, _ = self._run(self.world.argv("--json"))
        self.assertEqual(rc, 0)
        summary = json.loads(out)
        self.assertEqual(summary["store_schema_version"], ts.STORE_SCHEMA_VERSION)
        self.assertEqual([r["source"] for r in summary["sources"]], list(ts.SOURCES))
        self.assertEqual(summary["ok"], 5)
        for row in summary["sources"]:
            self.assertEqual(set(row), {"source", "status", "labels", "notes", "path"})
            self.assertTrue(Path(row["path"]).is_file())
            self.assertIsInstance(row["labels"], int)

    def test_days_flags_reach_the_envelopes(self):
        rc, _, _ = self._run(self.world.argv("--days", "5", "--overview-days", "2"))
        self.assertEqual(rc, 0)
        envs = self.world.envelopes()
        self.assertEqual(envs["cost_report"]["period"], {"days": 5})
        self.assertEqual(envs["cost_report"]["payload"]["days"], 5)
        self.assertEqual(envs["context_overview"]["period"], {"days": 2})

    def test_exit_one_when_every_source_errored(self):
        boom = mock.Mock(side_effect=RuntimeError("all down"))
        with contextlib.ExitStack() as stack:
            for source in ts.SOURCES:
                stack.enter_context(mock.patch.object(ts, f"collect_{source}", boom))
            rc, out, _ = self._run(self.world.argv())
        self.assertEqual(rc, 1)
        self.assertIn("0 ok, 5 error", out)
        self.assertEqual(len(self.world.envelopes()), 5)

    def test_exit_zero_when_only_some_sources_errored(self):
        boom = mock.Mock(side_effect=RuntimeError("one down"))
        with mock.patch.object(ts, "collect_cost_report", boom):
            rc, _, _ = self._run(self.world.argv())
        self.assertEqual(rc, 0)

    def test_exit_two_on_unwritable_store_dir(self):
        blocked = self.world.root / "blocked"
        blocked.write_text("i am a file, not a directory\n")
        rc, out, err = self._run([
            "--store-dir", str(blocked),
            "--projects-dir", str(self.world.root / "proj"),
            "--codex-home", str(self.world.root / "codex"),
            "--copilot-home", str(self.world.root / "copilot"),
            "--kits-dir", str(self.world.root / "kits"),
        ])
        self.assertEqual(rc, 2)
        self.assertIn("cannot write telemetry store", err)
        self.assertEqual(out, "")
        self.assertEqual(blocked.read_text(), "i am a file, not a directory\n")

    def test_store_dir_default_is_the_repo_store(self):
        self.assertEqual(ts.DEFAULT_STORE_DIR, ts.PLUGIN_ROOT / "telemetry")


class SourceLawTests(unittest.TestCase):
    """The module's own text is part of the contract: it spawns nothing and resolves no home
    dir of its own (kit GUARDRAILS / PLAN D3)."""

    def setUp(self):
        self.text = (BIN_DIR / "telemetry_snapshot.py").read_text()

    def test_no_process_spawning_tokens_anywhere_in_the_source(self):
        for token in ("subprocess", "os.system", "popen", "Popen", "shell=True"):
            self.assertNotIn(token, self.text, f"{token} must not appear in the source")

    def test_no_home_dir_resolution_in_this_module(self):
        self.assertNotIn("Path.home()", self.text)
        self.assertNotIn("expanduser", self.text)

    def test_home_defaults_come_from_the_loaded_modules_own_constants(self):
        """Resolution reads the sibling module's default; it never invents a path here."""
        cx = _load("codex_usage")
        cp = _load("copilot_usage")
        rs = _load("routing_scorecard")
        cr = _load("cost_report")
        resolved = ts.resolve_opts({})
        self.assertEqual(resolved["codex_home"], Path(cx.DEFAULT_CODEX_HOME))
        self.assertEqual(resolved["copilot_home"], Path(cp.DEFAULT_COPILOT_HOME))
        self.assertEqual(resolved["kits_dir"], Path(rs.DEFAULT_KITS_DIR))
        self.assertEqual(resolved["projects_dir"], Path(cr.PROJECTS_DIR))

    def test_explicit_opts_win_over_module_defaults(self):
        world = _TempWorld()
        self.addCleanup(world.cleanup)
        resolved = ts.resolve_opts(world.opts())
        self.assertEqual(resolved["projects_dir"], world.root / "proj")
        self.assertEqual(resolved["kits_dir"], world.root / "kits")
        self.assertEqual(resolved["days"], 30)


class ReadSourceSnapshotsTests(unittest.TestCase):
    """The tolerant reader seam (PLAN D6), modeled on
    ``routing_scorecard.read_snapshots`` — never a crash, never a guess."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Path(self._tmp.name)

    def _write(self, source, name, text):
        d = self.store / source
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(text)

    def test_missing_source_dir_returns_empty_with_a_note(self):
        cards, notes = ts.read_source_snapshots(self.store, "cost_report")
        self.assertEqual(cards, [])
        self.assertEqual(
            notes, [f"no snapshots for source 'cost_report' under {self.store}"])

    def test_rogue_filename_is_skipped_with_a_note(self):
        self._write("cost_report", "not-a-date.json", "{}")
        cards, notes = ts.read_source_snapshots(self.store, "cost_report")
        self.assertEqual(cards, [])
        self.assertTrue(
            any("rogue snapshot file skipped: cost_report/not-a-date.json" in n
                for n in notes),
            notes,
        )

    def test_undecodable_file_is_skipped_with_a_note_naming_it(self):
        self._write("cost_report", "2026-01-02.json", "NOT JSON AT ALL")
        cards, notes = ts.read_source_snapshots(self.store, "cost_report")
        self.assertEqual(cards, [])
        self.assertTrue(any("2026-01-02.json" in n for n in notes), notes)

    def test_non_dict_json_is_skipped_with_a_note(self):
        self._write("cost_report", "2026-01-02.json", json.dumps([1, 2, 3]))
        cards, notes = ts.read_source_snapshots(self.store, "cost_report")
        self.assertEqual(cards, [])
        self.assertTrue(any("2026-01-02.json" in n for n in notes), notes)

    def test_missing_payload_key_is_skipped_with_a_note(self):
        self._write("cost_report", "2026-01-02.json",
                    json.dumps({"status": "ok", "labels": []}))
        cards, notes = ts.read_source_snapshots(self.store, "cost_report")
        self.assertEqual(cards, [])
        self.assertTrue(any("2026-01-02.json" in n for n in notes), notes)

    def test_payload_that_is_neither_dict_nor_null_is_skipped_with_a_note(self):
        self._write("cost_report", "2026-01-02.json",
                    json.dumps({"status": "ok", "payload": "a string, not a dict"}))
        cards, notes = ts.read_source_snapshots(self.store, "cost_report")
        self.assertEqual(cards, [])
        self.assertTrue(any("2026-01-02.json" in n for n in notes), notes)

    def test_null_payload_is_a_valid_survivor(self):
        self._write("cost_report", "2026-01-02.json",
                    json.dumps({"status": "error", "payload": None}))
        cards, notes = ts.read_source_snapshots(self.store, "cost_report")
        self.assertEqual([d for d, _ in cards], ["2026-01-02"])
        self.assertEqual(notes, [])

    def test_unknown_envelope_keys_are_ignored_not_a_reason_to_skip(self):
        self._write("cost_report", "2026-01-02.json", json.dumps({
            "payload": {"found": True}, "status": "ok",
            "a_future_key_this_reader_has_never_seen": {"nested": [1, 2]},
        }))
        cards, notes = ts.read_source_snapshots(self.store, "cost_report")
        self.assertEqual(len(cards), 1)
        date, env = cards[0]
        self.assertEqual(date, "2026-01-02")
        self.assertIn("a_future_key_this_reader_has_never_seen", env)
        self.assertEqual(notes, [])

    def test_survivors_ascend_by_date(self):
        for name in ("2026-03-01.json", "2026-01-15.json", "2026-02-20.json"):
            self._write("cost_report", name, json.dumps({"status": "ok", "payload": None}))
        cards, notes = ts.read_source_snapshots(self.store, "cost_report")
        self.assertEqual([d for d, _ in cards],
                         ["2026-01-15", "2026-02-20", "2026-03-01"])
        self.assertEqual(notes, [])

    def test_mixed_matrix_keeps_only_the_valid_survivor(self):
        self._write("cost_report", "2026-01-01.json", json.dumps({"payload": None}))
        self._write("cost_report", "rogue.json", "{}")
        self._write("cost_report", "2026-01-02.json", "NOT JSON")
        self._write("cost_report", "2026-01-03.json", json.dumps([1, 2]))
        self._write("cost_report", "2026-01-04.json", json.dumps({"status": "ok"}))
        cards, notes = ts.read_source_snapshots(self.store, "cost_report")
        self.assertEqual([d for d, _ in cards], ["2026-01-01"])
        self.assertEqual(len(notes), 4)


class ListSummaryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Path(self._tmp.name)

    def _write(self, source, name, envelope):
        d = self.store / source
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(json.dumps(envelope))

    def test_missing_store_dir_returns_none_with_the_friendly_note(self):
        missing = self.store / "does-not-exist"
        summary, notes = ts.build_list_summary(missing)
        self.assertIsNone(summary)
        self.assertEqual(notes, [f"no telemetry store at {missing} — run a capture first"])

    def test_two_dates_plus_one_rogue_file_render(self):
        self._write("cost_report", "2026-01-01.json",
                    {"status": "ok", "payload": {"found": True}, "labels": ["est."]})
        self._write("cost_report", "2026-01-02.json",
                    {"status": "ok", "payload": {"found": True},
                     "labels": ["est.", "billing mode: subscription"]})
        self._write("cost_report", "rogue-name.json", {"status": "ok", "payload": None})
        summary, notes = ts.build_list_summary(self.store)
        self.assertIsNotNone(summary)
        row = next(r for r in summary["sources"] if r["source"] == "cost_report")
        self.assertEqual(row["count"], 2)
        self.assertEqual(row["first_date"], "2026-01-01")
        self.assertEqual(row["last_date"], "2026-01-02")
        self.assertEqual(row["latest_status"], "ok")
        self.assertEqual(row["latest_labels"], ["est.", "billing mode: subscription"])
        self.assertTrue(
            any("rogue snapshot file skipped: cost_report/rogue-name.json" in n
                for n in notes),
            notes,
        )
        rendered = ts.render_list_markdown(summary, notes)
        self.assertIn("2026-01-01", rendered)
        self.assertIn("2026-01-02", rendered)
        self.assertIn("rogue", rendered)

    def test_unregistered_subdir_is_listed_and_flagged(self):
        self._write("a_future_source", "2026-01-01.json",
                    {"status": "ok", "payload": {}, "labels": []})
        summary, notes = ts.build_list_summary(self.store)
        row = next(r for r in summary["sources"] if r["source"] == "a_future_source")
        self.assertFalse(row["registered"])
        self.assertEqual(row["count"], 1)
        self.assertTrue(any("unregistered source dir: a_future_source" in n for n in notes),
                        notes)

    def test_registered_subdir_is_not_flagged_unregistered(self):
        self._write("cost_report", "2026-01-01.json",
                    {"status": "ok", "payload": {}, "labels": []})
        summary, notes = ts.build_list_summary(self.store)
        row = next(r for r in summary["sources"] if r["source"] == "cost_report")
        self.assertTrue(row["registered"])
        self.assertFalse(any("unregistered source dir: cost_report" in n for n in notes))

    def test_list_renders_label_figures_verbatim_but_never_reads_a_payload(self):
        """F4 — the real ``--list`` contract, corrected.

        Envelope ``labels`` are strings LIFTED from a source's own payload, so a label that
        carries a per-source dollar figure or caveat renders here VERBATIM — it must, or the
        listing would look more authoritative than the output it captured. The guard is
        narrower and stronger than "no ``$`` ever appears": the lister reads only
        ``status``/``labels`` and never a payload field, so it can never compute, sum, or
        merge dollars across harnesses. Every figure it shows arrived attached to exactly one
        source's own label.
        """
        self._write("routing_history", "2026-01-01.json", {
            "status": "ok",
            # A payload-only figure: nothing here may reach the rendered listing.
            "payload": {"dollars": {"actual_usd": 999.99, "all_fable_usd": 888.88}},
            "labels": ["dollars coverage: partial (9/22 kits) — $244.69 actual, est."],
        })
        self._write("context_overview", "2026-01-01.json", {
            "status": "ok",
            "payload": {"sections": {"claude": {"carry_cost": {"carry_usd": 777.77}}}},
            "labels": ["claude: API-equivalent dollars — an estimate, not a bill."],
        })
        summary, notes = ts.build_list_summary(self.store)
        rendered = ts.render_list_markdown(summary, notes)

        # The lifted label — dollar figure and caveat wording — survives into the listing.
        self.assertIn("$244.69 actual, est.", rendered)
        self.assertIn("API-equivalent dollars — an estimate, not a bill.", rendered)
        # Payload-only dollars never leak: no payload field is ever read.
        for leaked in ("999.99", "888.88", "777.77", "actual_usd", "carry_usd"):
            self.assertNotIn(leaked, rendered)
        # And no row ever merges the two sources' figures into one number.
        for row in summary["sources"]:
            self.assertEqual(set(row), {"source", "registered", "count", "first_date",
                                        "last_date", "latest_status", "latest_labels"})


class ListCliTests(unittest.TestCase):
    def setUp(self):
        self.world = _TempWorld()
        self.addCleanup(self.world.cleanup)

    def _run(self, argv):
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = ts.main(argv)
        return rc, buf.getvalue(), err.getvalue()

    def test_list_on_missing_store_exits_zero_with_the_friendly_line(self):
        missing = self.world.root / "no-store-here"
        rc, out, err = self._run(["--list", "--store-dir", str(missing)])
        self.assertEqual(rc, 0)
        self.assertIn(f"no telemetry store at {missing} — run a capture first", out)
        self.assertEqual(err, "")

    def test_list_after_a_real_capture_renders_the_source_and_never_crashes(self):
        ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        rc, out, _ = self._run(["--list", "--store-dir", str(self.world.store)])
        self.assertEqual(rc, 0)
        for source in ts.SOURCES:
            self.assertIn(source, out)
        self.assertIn("2026-03-04", out)

    def test_list_never_invokes_a_capture(self):
        rc, out, _ = self._run(["--list", "--store-dir", str(self.world.store)])
        self.assertEqual(rc, 0)
        self.assertEqual(list(self.world.store.rglob("*.json")), [])

    def test_list_json_shape(self):
        ts.capture(self.world.store, date="2026-03-04", opts=self.world.opts())
        rc, out, _ = self._run(["--list", "--store-dir", str(self.world.store), "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out)
        self.assertEqual(set(payload), {"store_dir", "sources", "notes"})
        sources = {row["source"] for row in payload["sources"]}
        self.assertEqual(sources, set(ts.SOURCES))


class DemoTests(unittest.TestCase):
    def _run(self, argv):
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = ts.main(argv)
        return rc, buf.getvalue(), err.getvalue()

    def test_demo_exits_zero_and_names_all_five_sources(self):
        rc, out, err = self._run(["--demo"])
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        for source in ts.SOURCES:
            self.assertIn(source, out)

    def test_demo_json_names_all_five_sources_and_is_valid_json(self):
        rc, out, _ = self._run(["--demo", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out)
        self.assertEqual({r["source"] for r in payload["capture"]["sources"]},
                         set(ts.SOURCES))
        self.assertEqual({r["source"] for r in payload["list"]["sources"]}, set(ts.SOURCES))

    def test_demo_writes_nothing_to_the_default_store(self):
        """F6 — hermetic and able to FAIL.

        The old version iterated the REAL ``telemetry/`` and compared a before/after name
        list: it touched live evidence and could not fail, because a demo writing
        ``telemetry/<source>/<today>.json`` would land in an already-listed subdir and leave
        the name list identical. Here ``DEFAULT_STORE_DIR`` is monkeypatched to an empty temp
        dir — ``run_demo`` and ``main``'s ``--store-dir`` default both read the module
        attribute at call time — and the assertion is that NOTHING appears under it. Proven
        to fail: making ``run_demo`` write a single file to ``DEFAULT_STORE_DIR`` breaks this
        test. The real store is never read or touched by this file at all.
        """
        with tempfile.TemporaryDirectory() as tmp:
            fake_default = Path(tmp) / "telemetry"
            with mock.patch.object(ts, "DEFAULT_STORE_DIR", fake_default):
                rc, out, err = self._run(["--demo"])
                self.assertEqual(rc, 0)
                self.assertEqual(err, "")
                self.assertFalse(fake_default.exists(),
                                 f"--demo created the default store: "
                                 f"{sorted(p.name for p in fake_default.rglob('*'))}"
                                 if fake_default.exists() else "")
                self.assertEqual(sorted(Path(tmp).iterdir()), [])
                # The demo's own temp store is torn down with it: no path it printed
                # survives, and none of them is under the default store.
                for line in out.splitlines():
                    self.assertNotIn(str(fake_default), line)

    def test_demo_temp_store_is_cleaned_up(self):
        """Every path the demo prints is gone once it returns — the receipt names a store
        that no longer exists, which is what "throwaway" has to mean."""
        rc, out, _ = self._run(["--demo", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out)
        for row in payload["capture"]["sources"]:
            self.assertFalse(Path(row["path"]).exists(), row["path"])
        self.assertFalse(Path(payload["list"]["store_dir"]).exists())

    def test_demo_all_five_sources_ok_and_labelled(self):
        rc, out, _ = self._run(["--demo", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out)
        for row in payload["capture"]["sources"]:
            with self.subTest(source=row["source"]):
                self.assertEqual(row["status"], "ok", row)
        for row in payload["list"]["sources"]:
            with self.subTest(source=row["source"]):
                self.assertTrue(row["latest_labels"], row)


if __name__ == "__main__":
    unittest.main()
