"""Privacy layout guard — personal data stores must never become tracked.

The repo carries several gitignored personal-data surfaces (dollar telemetry, daily
journals, memory facts, prefs, trend snapshots, generated value reports). Each is
protected by a root-anchored .gitignore rule — but an ignore rule only guards the
UNtracked; a single `git add -f`, a rule edit, or a typo'd anchor silently starts
tracking, and the next push surfaces personal data remotely. This suite makes that
mistake fail the whole test suite instead of shipping.

Git is not the only remote channel (docs/PRIVACY.md, "The iCloud lesson"): a checkout
under a cloud-synced folder ships every gitignored store wholesale, so the repo's own
location is guarded here too.

Uses `git` read-only (`ls-files`, `check-ignore`) — the repo's CLI bans cover the
copilot/codex/claude harness CLIs, not git plumbing over the repo's own tree.
"""
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Every personal-data surface and the root-anchored rule that must protect it.
PRIVATE_DIRS = ("journal", "telemetry", "memory", "prefs", "trends")
REQUIRED_RULES = tuple(f"/{d}/" for d in PRIVATE_DIRS) + ("/value-report*.html",)


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True
    )


class PrivacyLayoutTests(unittest.TestCase):
    def test_no_personal_store_file_is_tracked(self):
        """The load-bearing check: ignore rules guard the untracked only —
        this catches a force-add or rule regression after the fact."""
        r = _git("ls-files", "--", *PRIVATE_DIRS)
        self.assertEqual(
            r.stdout.strip(), "",
            f"tracked files under personal-data dirs — these would push remotely:\n{r.stdout}",
        )

    def test_no_generated_value_report_is_tracked(self):
        r = _git("ls-files", "--", "value-report*.html")
        self.assertEqual(r.stdout.strip(), "", r.stdout)

    def test_gitignore_carries_every_root_anchored_rule(self):
        rules = {
            line.strip()
            for line in (REPO / ".gitignore").read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        missing = [r for r in REQUIRED_RULES if r not in rules]
        self.assertEqual(
            missing, [],
            f".gitignore lost root-anchored privacy rules: {missing} "
            "(the leading slash is load-bearing — see the /memory/ precedent)",
        )

    def test_probe_paths_are_actually_ignored(self):
        """check-ignore proves the rules FIRE, not merely exist — a typo'd
        anchor passes a content grep and fails here."""
        probes = [f"{d}/probe/x.json" for d in PRIVATE_DIRS] + ["value-report.html"]
        r = _git("check-ignore", "--", *probes)
        ignored = set(r.stdout.split())
        not_ignored = [p for p in probes if p not in ignored]
        self.assertEqual(not_ignored, [], f"paths NOT ignored: {not_ignored}")

    def test_repo_lives_outside_cloud_synced_folders(self):
        """The iCloud lesson: ~/Desktop synced the whole tree, gitignored stores
        included, while the gitignore fortress guarded only the GitHub door. A
        path-component check — not assumption — catches Desktop/Documents (iCloud
        Desktop & Documents sync), iCloud Drive, and the CloudStorage mounts
        (Dropbox/Drive/OneDrive) before a single sync happens."""
        banned = {
            "desktop", "documents", "mobile documents", "dropbox",
            "onedrive", "google drive", "cloudstorage",
        }
        hits = sorted({
            part for part in REPO.parts
            if part.casefold() in banned or "com~apple~clouddocs" in part.casefold()
        })
        self.assertEqual(
            hits, [],
            f"repo checkout {REPO} sits under a cloud-synced folder ({hits}) — "
            "its gitignored personal stores are syncing remotely; move the repo "
            "outside sync scope (docs/PRIVACY.md, 'The iCloud lesson')",
        )

    def test_skills_dirs_survive_the_root_anchoring(self):
        """The rules must be root-anchored precisely so tracked skill/tool files
        with matching names stay tracked (skills/memory/ precedent)."""
        r = _git("ls-files", "--", "skills/memory", "skills/journal")
        self.assertNotEqual(
            r.stdout.strip(), "",
            "skills/memory or skills/journal vanished from tracking — "
            "a privacy rule lost its root anchor and over-matched",
        )


if __name__ == "__main__":
    unittest.main()
