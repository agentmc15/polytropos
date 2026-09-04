"""Live-tree regression suite for `.claude/kits/docs-site/AUDIT.md` (T8 of the
docs-site kit), in the style of tests/test_guardrails_layout.py and
tests/test_docs_site.py: it asserts against the real, committed repo -- no
fixtures.

AUDIT.md (PLAN.md D8 / TASKS.md T8) is a read-and-judge, prose deliverable: no
skill file is edited by T8, and its dispositions are only APPLIED (not
rewritten) by T9-T14. That makes most of its content unsuited to a persisting
unit test -- the word counts and missing-subcommand facts it records describe
the PRE-T9 state on purpose, and a test pinning those numbers would go stale
the moment T9-T14 do their job correctly. What DOES stay true for as long as
AUDIT.md exists unedited is its own internal bookkeeping: that its roster of
`### <harness>/<name>` entries is exactly the live 39-skill inventory (so a
skill added/renamed/removed after this kit lands is flagged rather than
silently leaving AUDIT.md stale -- exactly the drift `copilot/goliath` caused
mid-plan, per PLAN.md's amendment note), that every entry carries its five
pinned fields in the pinned order, that every verdict is one of the three
sanctioned values, and that the free-text disposition-summary tally agrees
with a fresh count of the per-entry verdicts. These are structural checks on
the audit DOCUMENT, not on its transient judgments about SKILL.md word counts.
"""

import importlib.util
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = REPO_ROOT / ".claude" / "kits" / "docs-site" / "AUDIT.md"

EXPECTED_FIELD_ORDER = ["verdict", "skill-md", "references", "fragment-notes", "sentinels"]
VALID_VERDICTS = {"keep", "enrich", "relocate"}

# The seven skills PLAN.md/TASKS.md T8 name as deliberately thin, each requiring
# an explicit verdict with reasoning (T8 brief: "The seven thin skills ... each
# get an explicit verdict with reasoning").
THIN_SEVEN = [
    "claude/cost-report",
    "copilot/lessons-loop",
    "codex/bench-routing",
    "codex/doctor",
    "codex/memory",
    "codex/context-weight",
    "codex/execute",
]


def _load(name):
    bin_dir = REPO_ROOT / "bin"
    spec = importlib.util.spec_from_file_location(name, bin_dir / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read_audit():
    return AUDIT_PATH.read_text(encoding="utf-8")


def _entries(text):
    """Split the audit body into per-skill entries keyed by 'harness/name'."""
    parts = re.split(r"(?m)^### ", text)[1:]
    out = {}
    for part in parts:
        header, _, rest = part.partition("\n")
        out[header.strip()] = rest
    return out


class AuditFileExistsTests(unittest.TestCase):
    def test_audit_file_exists(self):
        self.assertTrue(AUDIT_PATH.is_file(), f"missing {AUDIT_PATH}")


@unittest.skipUnless(AUDIT_PATH.is_file(), "AUDIT.md not yet created")
class AuditRosterMatchesLiveInventoryTests(unittest.TestCase):
    """The audit's roster must equal the live skill_inventory() roster exactly --
    not just number 39. bin/docs_build.py's skill_inventory() (T1, done) is the
    generator's own source of truth for what skills exist; using it here (rather
    than re-walking skills/ by hand) means this test tracks the SAME notion of
    "a skill" the generator and T9-T14 use, including future additions like
    copilot/goliath."""

    def test_roster_is_exactly_the_live_39_skills(self):
        docs_build = _load("docs_build")
        inventory = docs_build.skill_inventory(repo_root=REPO_ROOT)
        live_roster = {f"{rec['harness']}/{rec['name']}" for rec in inventory}

        audit_roster = set(_entries(_read_audit()).keys())

        missing_from_audit = live_roster - audit_roster
        stale_in_audit = audit_roster - live_roster
        self.assertEqual(
            missing_from_audit, set(),
            f"skills in the live tree with no AUDIT.md entry: {sorted(missing_from_audit)}",
        )
        self.assertEqual(
            stale_in_audit, set(),
            f"AUDIT.md entries naming skills no longer in the live tree: {sorted(stale_in_audit)}",
        )


@unittest.skipUnless(AUDIT_PATH.is_file(), "AUDIT.md not yet created")
class AuditEntryShapeTests(unittest.TestCase):
    def setUp(self):
        self.entries = _entries(_read_audit())

    def test_exactly_39_entries(self):
        self.assertEqual(len(self.entries), 39)

    def test_every_entry_has_five_fields_in_pinned_order(self):
        for header, body in self.entries.items():
            fields = re.findall(
                r"(?m)^- (verdict|skill-md|references|fragment-notes|sentinels):", body
            )
            with self.subTest(header=header):
                self.assertEqual(
                    fields, EXPECTED_FIELD_ORDER,
                    f"{header} field order/count is {fields}, expected {EXPECTED_FIELD_ORDER}",
                )

    def test_no_stray_or_duplicate_field_labels(self):
        # Any '- <word>:' line at entry top level should be one of the five
        # pinned field names -- catches a typo'd label (e.g. "verdicts:") that
        # the order-check above would otherwise just silently drop.
        for header, body in self.entries.items():
            all_labels = re.findall(r"(?m)^- ([a-z-]+):", body)
            with self.subTest(header=header):
                self.assertEqual(set(all_labels), set(EXPECTED_FIELD_ORDER))
                self.assertEqual(len(all_labels), 5)

    def test_every_verdict_is_a_sanctioned_value(self):
        for header, body in self.entries.items():
            m = re.search(r"(?m)^- verdict: (\S+)", body)
            with self.subTest(header=header):
                self.assertIsNotNone(m, f"{header} has no verdict line")
                self.assertIn(m.group(1), VALID_VERDICTS)

    def test_thin_seven_all_present_with_explicit_verdicts(self):
        for name in THIN_SEVEN:
            with self.subTest(skill=name):
                self.assertIn(name, self.entries, f"thin-seven skill {name} missing from AUDIT.md")
                body = self.entries[name]
                m = re.search(r"(?m)^- verdict: (\S+)", body)
                self.assertIsNotNone(m)
                self.assertIn(m.group(1), VALID_VERDICTS)


@unittest.skipUnless(AUDIT_PATH.is_file(), "AUDIT.md not yet created")
class AuditDispositionSummaryConsistencyTests(unittest.TestCase):
    """The prose 'Disposition summary' tally must agree with a fresh count of the
    per-entry verdict lines -- catches the summary sentence going stale if an
    entry's verdict were ever changed without updating the headline count."""

    def test_summary_counts_match_counted_verdicts(self):
        text = _read_audit()
        m = re.search(
            r"(\d+)\s*`keep`,\s*(\d+)\s*`enrich`,\s*(\d+)\s*`relocate`", text
        )
        self.assertIsNotNone(m, "no '<N> `keep`, <N> `enrich`, <N> `relocate`' summary sentence found")
        summary_keep, summary_enrich, summary_relocate = (int(g) for g in m.groups())

        entries = _entries(text)
        counted = {"keep": 0, "enrich": 0, "relocate": 0}
        for body in entries.values():
            vm = re.search(r"(?m)^- verdict: (\S+)", body)
            if vm and vm.group(1) in counted:
                counted[vm.group(1)] += 1

        self.assertEqual(summary_keep, counted["keep"])
        self.assertEqual(summary_enrich, counted["enrich"])
        self.assertEqual(summary_relocate, counted["relocate"])
        self.assertEqual(summary_keep + summary_enrich + summary_relocate, len(entries))


if __name__ == "__main__":
    unittest.main()
