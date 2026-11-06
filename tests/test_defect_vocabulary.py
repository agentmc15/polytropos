"""Stdlib unittest suite for the sanctioned defect vocabulary (kit-preflight PLAN D9-D11):
``DEFECT_KINDS``/``DEFECT_FOLDS``/``DEFECT_EXCLUDED``/``DEFECT_WHEN``, ``canonical_defect_kind``,
the optional ``when=`` pair on ``defect:`` lines, the architect aggregate's folded /
unsanctioned / excluded / pre_run view, the card render, and ``lessons_promote`` parity.

Pure-function and temp-dir fixtures, plus a before/after snapshot of the explicit repository
kits directory to verify that module import does not change it. No network or subprocesses.
"""
import importlib.util
import hashlib
import os
import stat
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIN_DIR = REPO / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _kit_tree_snapshot(root):
    """Capture paths, types, modes, content digests and mtimes without following symlinks."""
    root = Path(root)
    if not root.exists() and not root.is_symlink():
        return None
    snapshot = {}

    def visit(path, relative):
        info = path.lstat()
        kind = stat.S_IFMT(info.st_mode)
        details = [kind, stat.S_IMODE(info.st_mode), info.st_size, info.st_mtime_ns]
        if stat.S_ISREG(info.st_mode):
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(65536), b""):
                    digest.update(chunk)
            details.append(digest.hexdigest())
        elif stat.S_ISLNK(info.st_mode):
            details.append(os.readlink(path))
        snapshot[relative] = tuple(details)
        if stat.S_ISDIR(info.st_mode):
            for child in sorted(path.iterdir(), key=lambda item: item.name):
                visit(child, f"{relative}/{child.name}" if relative else child.name)

    visit(root, "")
    return snapshot


KITS_DIR = REPO / ".claude" / "kits"
KIT_SNAPSHOT_BEFORE_IMPORT = _kit_tree_snapshot(KITS_DIR)
rs = _load("routing_scorecard")
lp = _load("lessons_promote")
KIT_SNAPSHOT_AFTER_IMPORT = _kit_tree_snapshot(KITS_DIR)

SANCTIONED = [k for k, _ in rs.DEFECT_KINDS]


class VocabularyTests(unittest.TestCase):
    def test_nine_kinds_in_order(self):
        self.assertEqual(SANCTIONED, [
            "stale-pin", "tautological-verify", "unrunnable-verify", "missing-helper",
            "unspecified-path", "contradictory-acceptance", "stale-plan-decision",
            "false-zero-spec", "underivable-requirement"])
        for _, definition in rs.DEFECT_KINDS:
            self.assertTrue(definition.endswith("."))

    def test_folds_and_exclusions_are_disjoint_from_sanctioned(self):
        for raw, target in rs.DEFECT_FOLDS.items():
            self.assertIn(target, SANCTIONED)
            self.assertNotIn(raw, SANCTIONED)
        self.assertEqual(set(rs.DEFECT_FOLDS), {
            "incomplete-acceptance", "process-guardrail", "unsafe-parallel-marking"})
        for kind in rs.DEFECT_EXCLUDED:
            self.assertNotIn(kind, SANCTIONED)
            self.assertNotIn(kind, rs.DEFECT_FOLDS)
        self.assertEqual(rs.DEFECT_EXCLUDED, ("verifier-destructive-restore",))
        self.assertEqual(rs.DEFECT_WHEN, ("pre-run",))

    def test_canonical_defect_kind_four_classes(self):
        self.assertEqual(rs.canonical_defect_kind("stale-pin"), ("stale-pin", None))
        self.assertEqual(rs.canonical_defect_kind("incomplete-acceptance"),
                         ("underivable-requirement", "folded"))
        self.assertEqual(rs.canonical_defect_kind("verifier-destructive-restore"),
                         (None, "excluded"))
        self.assertEqual(rs.canonical_defect_kind("stale-pin-2"),
                         ("stale-pin-2", "unsanctioned"))


class ParseWhenTests(unittest.TestCase):
    def test_when_pre_run_kept(self):
        ev, notes = rs.parse_defects("defect: T1 kind=stale-pin when=pre-run\n")
        self.assertEqual(ev, [{"task": "T1", "kind": "stale-pin", "when": "pre-run"}])
        self.assertEqual(notes, [])

    def test_unknown_when_noted_and_dropped(self):
        ev, notes = rs.parse_defects("defect: T1 kind=stale-pin when=later\n")
        self.assertEqual(ev, [{"task": "T1", "kind": "stale-pin"}])
        self.assertEqual(notes, ["defect T1 stale-pin: unknown when=later, ignored"])

    def test_no_when_exact_shape(self):
        ev, notes = rs.parse_defects("defect: T1 kind=stale-pin\n")
        self.assertEqual(ev, [{"task": "T1", "kind": "stale-pin"}])
        self.assertEqual(notes, [])

    def test_raw_kind_not_canonicalized_by_parser(self):
        ev, _ = rs.parse_defects("defect: T1 kind=incomplete-acceptance\n")
        self.assertEqual(ev[0]["kind"], "incomplete-acceptance")


NOTES = """\
defect: T1 kind=stale-pin
defect: T2 kind=incomplete-acceptance
defect: T3 kind=verifier-destructive-restore
defect: T4 kind=stale-pin-2
defect: T5 kind=stale-pin when=pre-run
"""


def _zero_tiers():
    return {tier: {"pinned": 0, "with_outcome": 0, "first_try": 0, "retry_pass": 0,
                   "escalated_pass": 0, "blocked": 0, "first_try_rate": None,
                   "escalation_rate": None,
                   "reroutes": {"applied_from": 0, "applied_to": 0,
                                "advisory_from": 0, "advisory_to": 0}}
            for tier in rs.LIVE_TIER_ORDER}


def _minimal_card(roles):
    return {"schema_version": rs.HISTORY_SCHEMA_VERSION,
            "generated_at": "2026-01-01T00:00:00+00:00", "kits_dir": "/synthetic/kits",
            "kits": [], "tiers": _zero_tiers(),
            "reroutes": {"events": 0, "applied": 0, "advisory": 0},
            "roles": roles, "dollars": None, "notes": []}


class AggregateTests(unittest.TestCase):
    def setUp(self):
        events, notes = rs.parse_defects(NOTES)
        self.assertEqual(notes, [])
        self.records = [{"kit": "k1", "agents": [], "reviewers": [], "defects": events}]
        self.roles, self.notes = rs.role_quality_stats(self.records)
        self.arch = self.roles["architect"]

    def test_aggregate(self):
        a = self.arch
        self.assertEqual(a["defects"], 4)
        self.assertEqual(a["kits_recording"], 1)
        self.assertEqual(a["by_kit"], {"k1": 5})
        self.assertEqual(a["by_kind"], {"stale-pin": 2, "underivable-requirement": 1,
                                         "stale-pin-2": 1})
        self.assertEqual(a["folded"], {"incomplete-acceptance":
                                       {"into": "underivable-requirement", "count": 1}})
        self.assertEqual(a["unsanctioned"], {"stale-pin-2": 1})
        self.assertEqual(a["excluded"], {"verifier-destructive-restore": 1})
        self.assertEqual(a["pre_run"], 1)

    def test_card_render(self):
        text = rs.render_history_markdown(_minimal_card(self.roles))
        for needle in ("folded: incomplete-acceptance\u2192underivable-requirement 1",
                       "unsanctioned: stale-pin-2 1",
                       "excluded: verifier-destructive-restore 1",
                       "caught pre-run: 1", "floor"):
            self.assertIn(needle, text)

    def test_clean_card_keeps_zero_pre_run(self):
        events, _ = rs.parse_defects("defect: T1 kind=stale-pin\n")
        roles, _ = rs.role_quality_stats(
            [{"kit": "k", "agents": [], "reviewers": [], "defects": events}])
        self.assertEqual(set(roles["architect"]),
                         {"defects", "kits_recording", "by_kind", "by_kit"})


class LessonsPromoteParityTests(unittest.TestCase):
    def _kits(self, tmp):
        kits = Path(tmp) / "kits"
        for name, body in (("ka", "defect: T1 kind=incomplete-acceptance\n"
                                  "defect: T2 kind=verifier-destructive-restore\n"),
                           ("kb", "defect: T1 kind=underivable-requirement\n")):
            (kits / name).mkdir(parents=True)
            (kits / name / "NOTES.md").write_text(body, encoding="utf-8")
        return kits

    def test_without_canonical_is_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev, notes = lp.collect_defect_evidence(self._kits(tmp), rs.parse_defects)
        self.assertEqual(sorted(e["kind"] for e in ev),
                         ["incomplete-acceptance", "underivable-requirement",
                          "verifier-destructive-restore"])
        self.assertEqual(notes, [])

    def test_with_canonical_folds_and_drops(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev, notes = lp.collect_defect_evidence(
                self._kits(tmp), rs.parse_defects, rs.canonical_defect_kind)
        self.assertEqual(sorted(e["kind"] for e in ev),
                         ["underivable-requirement", "underivable-requirement"])
        self.assertEqual(notes, ["ka: defect T1 incomplete-acceptance folded into "
                                 "underivable-requirement"])
        candidates, _ = lp.cluster_defects(ev)
        self.assertIn("underivable-requirement", candidates)


class NoWriteGuardTests(unittest.TestCase):
    def test_kits_dir_unchanged_by_import(self):
        self.assertEqual(KIT_SNAPSHOT_AFTER_IMPORT, KIT_SNAPSHOT_BEFORE_IMPORT)
        before = _kit_tree_snapshot(KITS_DIR)
        _load("routing_scorecard")
        self.assertEqual(_kit_tree_snapshot(KITS_DIR), before)

    def test_snapshot_detects_changes_to_preexisting_files_and_membership(self):
        for mutation in ("change", "add", "delete"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                kits = Path(temporary) / "kits"
                kits.mkdir()
                dirty = kits / "already-edited.md"
                dirty.write_text("preexisting edit\n")
                before = _kit_tree_snapshot(kits)
                if mutation == "change":
                    dirty.write_text("changed again\n")
                elif mutation == "add":
                    (kits / "added.md").write_text("new\n")
                else:
                    dirty.unlink()
                self.assertNotEqual(_kit_tree_snapshot(kits), before)

    def test_snapshot_does_not_follow_fixture_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            kits = base / "kits"
            kits.mkdir()
            outside = base / "outside.md"
            outside.write_text("outside\n")
            (kits / "link.md").symlink_to(outside)
            before = _kit_tree_snapshot(kits)
            outside.write_text("changed outside\n")
            self.assertEqual(_kit_tree_snapshot(kits), before)




# --- T2: documentation parity -------------------------------------------------------------
LEDGER = REPO / "skills" / "execute" / "references" / "ledger.md"
KIND_DOCS = (
    LEDGER,
    REPO / "skills" / "architect" / "references" / "routing-evidence.md",
    REPO / "docs" / "SPEC-DRIVEN.md",
    REPO / "docs" / "sdd" / "guide.md",
)


def ledger_definition_mismatches(text):
    """Kinds whose "`<kind>` — <definition>" line is absent or worded differently."""
    return [k for k, d in rs.DEFECT_KINDS if f"`{k}` — {d}" not in text]


class DocParityTests(unittest.TestCase):
    def test_ledger_carries_every_definition_verbatim(self):
        self.assertEqual(ledger_definition_mismatches(LEDGER.read_text(encoding="utf-8")), [])

    def test_ledger_documents_when_pre_run(self):
        self.assertIn("when=pre-run", LEDGER.read_text(encoding="utf-8"))

    def test_each_doc_names_all_nine_kinds(self):
        for path in KIND_DOCS:
            text = path.read_text(encoding="utf-8")
            for kind in SANCTIONED:
                self.assertIn(f"`{kind}`", text, f"{path.name} lacks {kind}")

    def test_altered_definition_fails_the_comparison(self):
        text = LEDGER.read_text(encoding="utf-8")
        first = rs.DEFECT_KINDS[0][1]
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "ledger.md"
            copy.write_text(text.replace(first, first.replace("no longer exists", "never existed"), 1),
                            encoding="utf-8")
            self.assertEqual(ledger_definition_mismatches(copy.read_text(encoding="utf-8")),
                             [rs.DEFECT_KINDS[0][0]])


if __name__ == "__main__":
    unittest.main()
