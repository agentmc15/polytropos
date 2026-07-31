"""Stdlib unittest regression suite for cross-repo ``--history`` (repeatable ``--kits-dir``)
and the snapshot/trend time series in bin/routing_scorecard.py (crossrepo-trend T4).

SAFETY CONTRACT (binds every test in this file): no test here ever reads the real Claude
Code project store or resolves the caller's real home directory via the stdlib home
helper -- this file never calls it, and it never spells out the real projects path as a
literal string. Every kit fixture (TASKS.md / NOTES.md), transcript, and snapshot store
lives under a fresh ``tempfile.TemporaryDirectory()`` and is handed to the CLI or the pure
functions via an explicit ``--kits-dir`` / ``--projects-dir`` / ``--snapshot-dir`` or an
explicit path -- never a bare run against real dirs. ``test_trend_never_loads_pricing``
additionally PROVES the pure ``--trend`` path never loads pricing: it stubs
``rs.cr.load_pricing`` to raise and shows ``--history --trend`` still succeeds (restoring
the stub in ``finally``). All ids/values in every fixture are synthetic; the only model
tokens anywhere in this file are the sanctioned tier vocabulary
(``haiku``/``sonnet``/``opus``/``frontier``) plus the ``fable`` Agent-tool alias, EXCEPT
the dollar-fixture transcript model ids, which are computed at run time from
``rs.cr.load_pricing()`` + ``rs._first_model_of_tier`` -- never a spelled model id.

bin/ is not a package; routing_scorecard.py is loaded via importlib by absolute path
computed from this file's own location (BIN_DIR), mirroring tests/test_routing_history.py
and tests/test_routing_scorecard.py. Do NOT edit tests/test_routing_scorecard.py,
tests/test_reroute_live.py, tests/test_routing_history.py, or tests/test_per_task_dollars.py
-- this is a new, standalone file.
"""

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
REPO_ROOT = BIN_DIR.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rs = _load("routing_scorecard")


# ---- fixture helpers --------------------------------------------------------------------------

def write_kit(kits_root, name, tasks_md, notes_md=None):
    """Write a temp kit dir under ``kits_root/name`` (TASKS.md + optional NOTES.md).

    ``kits_root`` is a directory path (e.g. ``<tmp>/repo-a/.claude/kits`` for a conventional
    layout, shared across several calls for a multi-kit fixture). Returns the kit dir path.
    """
    kit_dir = Path(kits_root) / name
    kit_dir.mkdir(parents=True, exist_ok=True)
    (kit_dir / "TASKS.md").write_text(tasks_md)
    if notes_md is not None:
        (kit_dir / "NOTES.md").write_text(notes_md)
    return kit_dir


def write_transcript(projects_root, session_id, messages, slug="-t"):
    """Write a synthetic transcript JSONL under ``projects_root/<slug>/<session_id>.jsonl``.

    ``messages`` is a list of dicts ``{"model", "id", "input_tokens", "output_tokens"}``;
    the JSONL shape mirrors ``run_demo``'s transcript fixtures
    (``{"timestamp", "message": {"model", "id", "usage": {...}}}``). ``slug`` (default
    ``"-t"``) is a synthetic project-slug subdir name -- ``find_main_transcript`` locates
    files by recursive glob on the session-id filename, so any two calls with DIFFERENT
    ``slug`` values still resolve from a single shared ``--projects-dir``, exercising the
    cross-repo dollars honesty rule (the shared transcript store holds every repo's
    sessions).
    """
    proj = Path(projects_root) / slug
    proj.mkdir(parents=True, exist_ok=True)
    ts = "2026-07-01T12:00:00+00:00"
    lines = []
    for m in messages:
        lines.append(json.dumps({
            "timestamp": ts,
            "message": {
                "model": m["model"],
                "id": m["id"],
                "usage": {
                    "input_tokens": m["input_tokens"],
                    "output_tokens": m["output_tokens"],
                },
            },
        }))
    path = proj / f"{session_id}.jsonl"
    path.write_text("\n".join(lines) + "\n")
    return path


def make_history_card(tier_overrides=None, kits=None, dollars=None):
    """Compose a minimal synthetic HISTORY-shaped card dict for direct snapshot-file
    fixtures (PLAN D7/D8's snapshot store holds exactly this shape).

    ``build_trend`` reads per-tier cells TOLERANTLY -- only ``with_outcome``/``first_try``/
    ``first_try_rate`` per ``LIVE_TIER_ORDER`` tier are consumed -- so this writer keeps
    every other per-tier key out by design (old/foreign-shaped cards are meant to be
    tolerated, not exhaustively mimicked). ``dollars`` is a dict or ``None`` (never
    fabricated by this helper -- the caller decides).
    """
    tiers = {tier: {"with_outcome": 0, "first_try": 0, "first_try_rate": None}
             for tier in rs.LIVE_TIER_ORDER}
    if tier_overrides:
        for tier, overrides in tier_overrides.items():
            tiers[tier].update(overrides)
    return {
        "schema_version": rs.HISTORY_SCHEMA_VERSION,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "kits_dir": "/synthetic/kits",
        "kits": kits if kits is not None else [],
        "tiers": tiers,
        "reroutes": {"events": 0, "applied": 0, "advisory": 0},
        "dollars": dollars,
        "notes": [],
    }


def tree(root):
    """Recursive byte-snapshot of every file under ``root`` -> ``{relative_path: bytes}``,
    for read-only before/after proofs. A nonexistent ``root`` snapshots as ``{}``.
    """
    root = Path(root)
    if not root.exists():
        return {}
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _run_cli(args):
    """subprocess.run the real CLI from the repo root (never the dotted-module form)."""
    return subprocess.run(
        [sys.executable, "bin/routing_scorecard.py"] + args,
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )


# ---- kit fixtures (spaced em dash headings, pinned outcome:/reroute:/session: grammars) --------

ALPHA_TASKS_MD = """# TASKS — aaa-kit (synthetic)

## Phase 1 — only phase

### AA1 — a haiku task
- status: done
- model: haiku
"""

BETA_TASKS_MD = """# TASKS — bbb-kit (synthetic)

## Phase 1 — only phase

### BB1 — a sonnet task
- status: done
- model: sonnet
"""

# Namespacing/aggregation fixture (T4 #5): repo-a holds "alpha" + "gamma", repo-b holds an
# UNRELATED "alpha" of its own -- the collision is the point (namespaced rows must stay
# distinct). No session: lines anywhere -- keeps this test purely about tier/re-route
# aggregation, never touching pricing.
NS_ALPHA_TASKS_MD = """# TASKS — alpha (synthetic, repo-a)

## Phase 1 — only phase

### A1 — a haiku task with an advisory reroute
- status: done
- model: haiku
"""

NS_ALPHA_NOTES_MD = """# NOTES — alpha (synthetic, repo-a)

## Outcome ledger
outcome: A1 model=haiku attempts=1 result=pass review=clean
reroute: haiku to=sonnet mode=advisory tasks=A1 rate=1/1
"""

NS_GAMMA_TASKS_MD = """# TASKS — gamma (synthetic, repo-a's second kit)

## Phase 1 — only phase

### G1 — a sonnet retry task
- status: done
- model: sonnet
"""

NS_GAMMA_NOTES_MD = """# NOTES — gamma (synthetic, repo-a's second kit)

## Outcome ledger
outcome: G1 model=sonnet attempts=2 result=retry-pass review=revised
"""

NS_BETA_ALPHA_TASKS_MD = """# TASKS — alpha (synthetic, repo-b -- same name as repo-a's)

## Phase 1 — only phase

### B1 — an opus task with an advisory reroute
- status: done
- model: opus
"""

NS_BETA_ALPHA_NOTES_MD = """# NOTES — alpha (synthetic, repo-b)

## Outcome ledger
outcome: B1 model=opus attempts=1 result=pass review=clean
reroute: sonnet to=opus mode=advisory tasks=B1 rate=1/1
"""

# Cross-repo dollars fixture (T4 #6): repo-a/alpha and repo-b/alpha each carry ONE priced
# session; a third repo (repo-c/ghost) carries a session with NO transcript.
DOL_ALPHA_A_TASKS_MD = """# TASKS — alpha (synthetic, repo-a, priced)

## Phase 1 — only phase

### AA1 — a priced sonnet task
- status: done
- model: sonnet
"""

DOL_ALPHA_A_NOTES_MD = """# NOTES — alpha (synthetic, repo-a, priced)

## Outcome ledger
outcome: AA1 model=sonnet attempts=1 result=pass review=clean
session: alpha-a-session
"""

DOL_ALPHA_B_TASKS_MD = """# TASKS — alpha (synthetic, repo-b, priced)

## Phase 1 — only phase

### AB1 — a priced opus task
- status: done
- model: opus
"""

DOL_ALPHA_B_NOTES_MD = """# NOTES — alpha (synthetic, repo-b, priced)

## Outcome ledger
outcome: AB1 model=opus attempts=1 result=pass review=clean
session: alpha-b-session
"""

DOL_GHOST_TASKS_MD = """# TASKS — ghost (synthetic, repo-c, unpriceable)

## Phase 1 — only phase

### GX1 — a task whose session has no transcript
- status: done
- model: sonnet
"""

DOL_GHOST_NOTES_MD = """# NOTES — ghost (synthetic, repo-c, unpriceable)

## Outcome ledger
outcome: GX1 model=sonnet attempts=1 result=pass review=clean
session: ghost-x-no-transcript-session
"""


# ---- 1. parse_kits_dir_token --------------------------------------------------------------


class ParseKitsDirTokenTests(unittest.TestCase):
    def test_parse_kits_dir_token_grammar(self):
        # plain path (no "=") -> (None, path) verbatim
        self.assertEqual(
            rs.parse_kits_dir_token("/synthetic-repo/.claude/kits"),
            (None, "/synthetic-repo/.claude/kits"))

        # label=path -> split on the label grammar
        self.assertEqual(
            rs.parse_kits_dir_token("repo-a=/synthetic-repo-a/.claude/kits"),
            ("repo-a", "/synthetic-repo-a/.claude/kits"))

        # pre-"=" prefix containing a path separator -> whole token is a path
        self.assertEqual(
            rs.parse_kits_dir_token("a/b=/synthetic/c"),
            (None, "a/b=/synthetic/c"))

        # pre-"=" prefix failing the label charset (a space) -> whole token is a path
        self.assertEqual(
            rs.parse_kits_dir_token("bad label=/synthetic/c"),
            (None, "bad label=/synthetic/c"))

        # "=x" (empty label) -> whole token is the path, label None
        self.assertEqual(rs.parse_kits_dir_token("=x"), (None, "=x"))

        # first-"=" split only
        self.assertEqual(
            rs.parse_kits_dir_token("repo-a=/synthetic/path=with=equals"),
            ("repo-a", "/synthetic/path=with=equals"))


# ---- 2. derive_repo_label -------------------------------------------------------------------


class DeriveRepoLabelTests(unittest.TestCase):
    def test_derive_repo_label_conventional_and_fallback(self):
        # conventional <repo>/.claude/kits -> the repo directory's basename; no filesystem
        # access needed -- these paths are entirely synthetic and never touched on disk.
        self.assertEqual(
            rs.derive_repo_label("/synthetic-home/repo-a/.claude/kits"), "repo-a")
        self.assertEqual(
            rs.derive_repo_label("/synthetic-home/nested/repo-b/.claude/kits"), "repo-b")

        # any other dir -> its own basename
        self.assertEqual(
            rs.derive_repo_label("/synthetic-home/some/other/widget-dir"), "widget-dir")

        # trailing-slash tokens normalize (Path semantics strip the trailing separator)
        self.assertEqual(
            rs.derive_repo_label("/synthetic-home/repo-a/.claude/kits/"), "repo-a")
        self.assertEqual(
            rs.derive_repo_label("/synthetic-home/some/other/widget-dir/"), "widget-dir")

        # a "kits" dir whose parent is NOT ".claude" is non-conventional -> own basename
        self.assertEqual(
            rs.derive_repo_label("/synthetic-home/not-dot-claude/kits"), "kits")


# ---- 3. resolve_kits_dirs ---------------------------------------------------------------------


class ResolveKitsDirsTests(unittest.TestCase):
    def test_resolve_kits_dirs_dedupe_and_collisions(self):
        # the same resolved path twice -> one entry + a note
        entries, notes = rs.resolve_kits_dirs([
            "/synthetic-home/repo-a/.claude/kits",
            "/synthetic-home/repo-a/.claude/kits",
        ])
        self.assertEqual(len(entries), 1)
        self.assertTrue(any("duplicate kits-dir" in n for n in notes))

        # two dirs deriving the SAME label (different parents, same basename) -> label,
        # label-2 + a note -- never a silent merge
        entries2, notes2 = rs.resolve_kits_dirs([
            "/synthetic-home/proj1/widget-dir",
            "/synthetic-home/proj2/widget-dir",
        ])
        self.assertEqual([e["label"] for e in entries2], ["widget-dir", "widget-dir-2"])
        self.assertTrue(any("duplicate kits-dir label" in n for n in notes2))
        self.assertEqual(
            [e["path"] for e in entries2],
            ["/synthetic-home/proj1/widget-dir", "/synthetic-home/proj2/widget-dir"])

        # explicit label wins over derivation
        entries3, notes3 = rs.resolve_kits_dirs(["myrepo=/synthetic-home/anything/.claude/kits"])
        self.assertEqual(entries3[0]["label"], "myrepo")
        self.assertTrue(entries3[0]["explicit"])
        self.assertEqual(entries3[0]["path"], "/synthetic-home/anything/.claude/kits")
        self.assertEqual(notes3, [])

        # entries keep the given order (three distinct, non-colliding dirs)
        entries4, _ = rs.resolve_kits_dirs([
            "/synthetic-home/repo-x/.claude/kits",
            "/synthetic-home/repo-y/.claude/kits",
            "/synthetic-home/repo-z/.claude/kits",
        ])
        self.assertEqual([e["label"] for e in entries4], ["repo-x", "repo-y", "repo-z"])


# ---- 4. single-dir byte shape ------------------------------------------------------------------


class SingleDirByteShapeTests(unittest.TestCase):
    def test_single_dir_history_byte_shape(self):
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            write_kit(kits_root, "solo-kit", ALPHA_TASKS_MD)
            projects_root = Path(td) / "projects"
            projects_root.mkdir()

            result = _run_cli(["--history", "--kits-dir", str(kits_root),
                               "--projects-dir", str(projects_root), "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            card = json.loads(result.stdout)

            md_result = _run_cli(["--history", "--kits-dir", str(kits_root),
                                  "--projects-dir", str(projects_root)])
            self.assertEqual(md_result.returncode, 0, md_result.stderr)

        self.assertEqual(set(card), {
            "schema_version", "generated_at", "kits_dir", "kits", "tiers",
            "reroutes", "roles", "dollars", "notes",
        })
        self.assertNotIn("kits_dirs", card)
        self.assertIsInstance(card["kits_dir"], str)
        self.assertEqual(card["kits"][0]["kit"], "solo-kit")  # unprefixed

        h2s = ["## Verdict", "## Per-tier track record", "## Role quality",
               "## Re-route history", "## Kits", "## Dollars"]
        self.assertIn("# Routing history — cross-kit per-tier track record",
                      md_result.stdout)
        idx = [md_result.stdout.index(h) for h in h2s]
        self.assertEqual(idx, sorted(idx))
        self.assertNotIn("- scanned", md_result.stdout)


# ---- 5. multi-dir namespacing + global aggregation ---------------------------------------------


class MultiDirNamespaceTests(unittest.TestCase):
    def test_multi_dir_namespaces_and_aggregates(self):
        with tempfile.TemporaryDirectory() as td:
            repo_a_kits = Path(td) / "repo-a" / ".claude" / "kits"
            repo_b_kits = Path(td) / "repo-b" / ".claude" / "kits"
            write_kit(repo_a_kits, "alpha", NS_ALPHA_TASKS_MD, NS_ALPHA_NOTES_MD)
            write_kit(repo_a_kits, "gamma", NS_GAMMA_TASKS_MD, NS_GAMMA_NOTES_MD)
            write_kit(repo_b_kits, "alpha", NS_BETA_ALPHA_TASKS_MD, NS_BETA_ALPHA_NOTES_MD)
            projects_root = Path(td) / "projects"
            projects_root.mkdir()

            solo_a = _run_cli(["--history", "--kits-dir", str(repo_a_kits),
                               "--projects-dir", str(projects_root), "--json"])
            self.assertEqual(solo_a.returncode, 0, solo_a.stderr)
            card_a = json.loads(solo_a.stdout)

            solo_b = _run_cli(["--history", "--kits-dir", str(repo_b_kits),
                               "--projects-dir", str(projects_root), "--json"])
            self.assertEqual(solo_b.returncode, 0, solo_b.stderr)
            card_b = json.loads(solo_b.stdout)

            multi = _run_cli(["--history",
                              "--kits-dir", str(repo_a_kits),
                              "--kits-dir", str(repo_b_kits),
                              "--projects-dir", str(projects_root), "--json"])
            self.assertEqual(multi.returncode, 0, multi.stderr)
            card = json.loads(multi.stdout)

            md_multi = _run_cli(["--history",
                                 "--kits-dir", str(repo_a_kits),
                                 "--kits-dir", str(repo_b_kits),
                                 "--projects-dir", str(projects_root)])
            self.assertEqual(md_multi.returncode, 0, md_multi.stderr)

        # namespaced kit rows, in given dir order (scan_kits sorts within a dir)
        self.assertEqual([r["kit"] for r in card["kits"]],
                         ["repo-a/alpha", "repo-a/gamma", "repo-b/alpha"])

        # per-tier aggregates equal the SUMS of the per-repo ledgers
        K = ("pinned", "with_outcome", "first_try", "retry_pass", "escalated_pass", "blocked")
        for tier in rs.LIVE_TIER_ORDER:
            for k in K:
                self.assertEqual(
                    card["tiers"][tier][k],
                    card_a["tiers"][tier][k] + card_b["tiers"][tier][k],
                    f"{tier}.{k} did not sum across repos")
            for rk in ("applied_from", "applied_to", "advisory_from", "advisory_to"):
                self.assertEqual(
                    card["tiers"][tier]["reroutes"][rk],
                    card_a["tiers"][tier]["reroutes"][rk] + card_b["tiers"][tier]["reroutes"][rk])

        # re-route events tallied globally
        for rk in ("events", "applied", "advisory"):
            self.assertEqual(
                card["reroutes"][rk], card_a["reroutes"][rk] + card_b["reroutes"][rk])

        self.assertIsNone(card["kits_dir"])
        self.assertEqual(card["kits_dirs"], [
            {"label": "repo-a", "path": str(repo_a_kits)},
            {"label": "repo-b", "path": str(repo_b_kits)},
        ])

        self.assertIn(f"- scanned repo-a: {repo_a_kits}", md_multi.stdout)
        self.assertIn(f"- scanned repo-b: {repo_b_kits}", md_multi.stdout)


# ---- 6. cross-repo dollars, shared --projects-dir -----------------------------------------------


class MultiDirDollarsTests(unittest.TestCase):
    def test_multi_dir_dollars_shared_projects_dir(self):
        pricing = rs.cr.load_pricing()
        sonnet_id = rs._first_model_of_tier(pricing, "sonnet")
        opus_id = rs._first_model_of_tier(pricing, "opus")
        self.assertIsNotNone(sonnet_id)
        self.assertIsNotNone(opus_id)

        with tempfile.TemporaryDirectory() as td:
            repo_a_kits = Path(td) / "repo-a" / ".claude" / "kits"
            repo_b_kits = Path(td) / "repo-b" / ".claude" / "kits"
            repo_c_kits = Path(td) / "repo-c" / ".claude" / "kits"
            write_kit(repo_a_kits, "alpha", DOL_ALPHA_A_TASKS_MD, DOL_ALPHA_A_NOTES_MD)
            write_kit(repo_b_kits, "alpha", DOL_ALPHA_B_TASKS_MD, DOL_ALPHA_B_NOTES_MD)
            write_kit(repo_c_kits, "ghost", DOL_GHOST_TASKS_MD, DOL_GHOST_NOTES_MD)

            projects_root = Path(td) / "projects"
            # two DIFFERENT project slugs under ONE shared projects dir -- find_main_transcript
            # rglobs, so both resolve regardless of which repo scanned them.
            write_transcript(projects_root, "alpha-a-session", [
                {"model": sonnet_id, "id": "aa-msg", "input_tokens": 1000, "output_tokens": 200},
            ], slug="-slug-one")
            write_transcript(projects_root, "alpha-b-session", [
                {"model": opus_id, "id": "ab-msg", "input_tokens": 800, "output_tokens": 150},
            ], slug="-slug-two")

            full = _run_cli(["--history",
                             "--kits-dir", str(repo_a_kits),
                             "--kits-dir", str(repo_b_kits),
                             "--projects-dir", str(projects_root),
                             "--no-subagents", "--json"])
            self.assertEqual(full.returncode, 0, full.stderr)
            full_card = json.loads(full.stdout)

            partial = _run_cli(["--history",
                                "--kits-dir", str(repo_a_kits),
                                "--kits-dir", str(repo_b_kits),
                                "--kits-dir", str(repo_c_kits),
                                "--projects-dir", str(projects_root),
                                "--no-subagents", "--json"])
            self.assertEqual(partial.returncode, 0, partial.stderr)
            partial_card = json.loads(partial.stdout)

        self.assertEqual(full_card["dollars"]["coverage"], "full")
        self.assertEqual(full_card["dollars"]["sessions_priced"], 2)
        rows_full = {r["kit"]: r for r in full_card["kits"]}
        self.assertIsNotNone(rows_full["repo-a/alpha"]["cost"])
        self.assertIsNotNone(rows_full["repo-b/alpha"]["cost"])
        self.assertGreater(rows_full["repo-a/alpha"]["cost"]["actual_usd"], 0)
        self.assertGreater(rows_full["repo-b/alpha"]["cost"]["actual_usd"], 0)

        self.assertEqual(partial_card["dollars"]["coverage"], "partial")
        self.assertEqual(partial_card["dollars"]["sessions_priced"], 2)
        rows_partial = {r["kit"]: r for r in partial_card["kits"]}
        self.assertIsNotNone(rows_partial["repo-a/alpha"]["cost"])
        self.assertIsNotNone(rows_partial["repo-b/alpha"]["cost"])
        self.assertIsNone(rows_partial["repo-c/ghost"]["cost"])  # never fabricated
        self.assertTrue(any("ghost-x-no-transcript-session" in n for n in partial_card["notes"]))


# ---- 7. explicit label on a lone dir ------------------------------------------------------------


class ExplicitLabelLoneDirTests(unittest.TestCase):
    def test_explicit_label_lone_dir_namespaces(self):
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            write_kit(kits_root, "solo", ALPHA_TASKS_MD)
            projects_root = Path(td) / "projects"
            projects_root.mkdir()

            result = _run_cli(["--history", "--kits-dir", f"mylabel={kits_root}",
                               "--projects-dir", str(projects_root), "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            card = json.loads(result.stdout)

        self.assertIsNone(card["kits_dir"])
        self.assertIn("kits_dirs", card)
        self.assertEqual(card["kits_dirs"], [{"label": "mylabel", "path": str(kits_root)}])
        self.assertEqual(card["kits"][0]["kit"], "mylabel/solo")


# ---- 8. repeated --kits-dir rejected outside --history ------------------------------------------


class MultiKitsDirRejectionTests(unittest.TestCase):
    def test_multi_kits_dir_rejected_outside_history(self):
        r1 = _run_cli(["some-kit",
                       "--kits-dir", "/synthetic-nonexistent-repo-a/.claude/kits",
                       "--kits-dir", "/synthetic-nonexistent-repo-b/.claude/kits"])
        self.assertNotEqual(r1.returncode, 0)
        self.assertIn("--history", r1.stderr)

        r2 = _run_cli(["--live",
                       "--kits-dir", "/synthetic-nonexistent-repo-a/.claude/kits",
                       "--kits-dir", "/synthetic-nonexistent-repo-b/.claude/kits"])
        self.assertNotEqual(r2.returncode, 0)
        self.assertIn("--history", r2.stderr)


# ---- 9. write_snapshot grammar + traversal guard ------------------------------------------------


class WriteSnapshotTests(unittest.TestCase):
    def test_write_snapshot_grammar_and_traversal_guard(self):
        with tempfile.TemporaryDirectory() as td:
            snap_dir = Path(td) / "snap"
            card1 = make_history_card()
            path = rs.write_snapshot(card1, snap_dir, "2026-03-04")
            self.assertEqual(path, snap_dir / "2026-03-04.json")
            self.assertTrue(path.is_file())
            self.assertEqual(json.loads(path.read_text()), card1)

            # same-day overwrite = latest-wins
            card2 = make_history_card(kits=[{"kit": "v2"}])
            path2 = rs.write_snapshot(card2, snap_dir, "2026-03-04")
            self.assertEqual(path2, path)
            self.assertEqual(json.loads(path.read_text()), card2)

            for bad in ("2026-1-1", "../evil", "2026-01-01x", "20260101"):
                before = sorted(p.name for p in snap_dir.glob("*"))
                with self.assertRaises(ValueError):
                    rs.write_snapshot(card1, snap_dir, bad)
                after = sorted(p.name for p in snap_dir.glob("*"))
                self.assertEqual(before, after, f"a write leaked through for {bad!r}")

            # a bad date_str against a NONEXISTENT dir must not even create the dir
            fresh_dir = Path(td) / "fresh"
            with self.assertRaises(ValueError):
                rs.write_snapshot(card1, fresh_dir, "../evil")
            self.assertFalse(fresh_dir.exists())


# ---- 10. snapshot CLI writes only the dated file -------------------------------------------------


class SnapshotCliTests(unittest.TestCase):
    def test_snapshot_cli_writes_only_dated_file(self):
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            write_kit(kits_root, "solo", ALPHA_TASKS_MD)
            projects_root = Path(td) / "projects"
            projects_root.mkdir()
            snap_dir = Path(td) / "snap"  # does not exist yet

            root_before = tree(Path(td))

            result = _run_cli(["--history", "--kits-dir", str(kits_root),
                               "--projects-dir", str(projects_root),
                               "--snapshot", "--snapshot-dir", str(snap_dir), "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            printed = json.loads(result.stdout)

            root_after = tree(Path(td))

            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            stored = json.loads((snap_dir / f"{today}.json").read_text())

        added = set(root_after) - set(root_before)
        removed = set(root_before) - set(root_after)
        self.assertEqual(removed, set())
        self.assertEqual(added, {f"snap/{today}.json"})
        for rel in set(root_before) & set(root_after):
            self.assertEqual(root_before[rel], root_after[rel], f"{rel} mutated in place")

        # the PRINTED card carries the note; the STORED card does not
        self.assertTrue(any(n.startswith("snapshot written:") for n in printed["notes"]))
        self.assertFalse(any(n.startswith("snapshot written:") for n in stored["notes"]))
        self.assertEqual(set(stored), {
            "schema_version", "generated_at", "kits_dir", "kits", "tiers",
            "reroutes", "roles", "dollars", "notes",
        })


# ---- 11. --snapshot/--trend flag rejections -------------------------------------------------------


class SnapshotTrendRejectionTests(unittest.TestCase):
    def test_snapshot_and_trend_flag_rejections(self):
        r1 = _run_cli(["--snapshot"])
        self.assertNotEqual(r1.returncode, 0)
        self.assertIn("--history", r1.stderr)

        r2 = _run_cli(["--trend"])
        self.assertNotEqual(r2.returncode, 0)
        self.assertIn("--history", r2.stderr)

        r3 = _run_cli(["--demo", "--history", "--snapshot"])
        self.assertNotEqual(r3.returncode, 0)
        self.assertIn("--demo", r3.stderr)


# ---- 12. trend degradation: 0 and 1 snapshots ------------------------------------------------------


class TrendDegradeTests(unittest.TestCase):
    def test_trend_zero_and_one_snapshot_degrade(self):
        with tempfile.TemporaryDirectory() as td:
            empty_dir = Path(td) / "empty"
            empty_dir.mkdir()
            missing_dir = Path(td) / "missing"  # never created

            r_empty = _run_cli(["--history", "--trend",
                                "--snapshot-dir", str(empty_dir), "--json"])
            self.assertEqual(r_empty.returncode, 0, r_empty.stderr)
            card_empty = json.loads(r_empty.stdout)
            self.assertEqual(card_empty["points"], [])
            self.assertTrue(any("no snapshots found" in n for n in card_empty["notes"]))

            md_empty = _run_cli(["--history", "--trend", "--snapshot-dir", str(empty_dir)])
            self.assertEqual(md_empty.returncode, 0, md_empty.stderr)
            self.assertIn("no snapshots — n/a", md_empty.stdout)

            r_missing = _run_cli(["--history", "--trend",
                                  "--snapshot-dir", str(missing_dir), "--json"])
            self.assertEqual(r_missing.returncode, 0, r_missing.stderr)
            card_missing = json.loads(r_missing.stdout)
            self.assertEqual(card_missing["points"], [])
            self.assertTrue(any("snapshot dir not found" in n for n in card_missing["notes"]))

            one_dir = Path(td) / "one"
            rs.write_snapshot(make_history_card(), one_dir, "2026-02-01")

            r_one = _run_cli(["--history", "--trend", "--snapshot-dir", str(one_dir), "--json"])
            self.assertEqual(r_one.returncode, 0, r_one.stderr)
            card_one = json.loads(r_one.stdout)
            self.assertEqual(len(card_one["points"]), 1)
            self.assertEqual(card_one["points"][0]["date"], "2026-02-01")
            self.assertTrue(any(
                "one snapshot — no trend yet (a trend needs at least 2 points)" in n
                for n in card_one["notes"]))


# ---- 13. two-snapshot trend table -------------------------------------------------------------------


class TrendTableTests(unittest.TestCase):
    def test_trend_two_snapshots_table(self):
        with tempfile.TemporaryDirectory() as td:
            snap_dir = Path(td) / "snap"
            card_a = make_history_card(
                tier_overrides={"haiku": {"with_outcome": 4, "first_try": 3,
                                          "first_try_rate": 0.75}},
                kits=[{"kit": "solo"}],
                dollars=None,
            )
            card_b = make_history_card(
                tier_overrides={
                    "haiku": {"with_outcome": 4, "first_try": 3, "first_try_rate": 0.75},
                    "sonnet": {"with_outcome": 5, "first_try": 2, "first_try_rate": 0.4},
                },
                kits=[{"kit": "solo"}, {"kit": "duo"}],
                dollars={"actual_usd": 12.5, "delta_usd": 3.0},
            )
            rs.write_snapshot(card_a, snap_dir, "2026-02-01")
            rs.write_snapshot(card_b, snap_dir, "2026-02-02")

            r = _run_cli(["--history", "--trend", "--snapshot-dir", str(snap_dir), "--json"])
            self.assertEqual(r.returncode, 0, r.stderr)
            card = json.loads(r.stdout)

            md = _run_cli(["--history", "--trend", "--snapshot-dir", str(snap_dir)])
            self.assertEqual(md.returncode, 0, md.stderr)

        self.assertEqual([p["date"] for p in card["points"]], ["2026-02-01", "2026-02-02"])
        self.assertEqual(card["points"][0]["tiers"]["haiku"]["first_try_rate"], 0.75)
        self.assertEqual(card["points"][1]["tiers"]["sonnet"]["first_try_rate"], 0.4)
        self.assertIsNone(card["points"][0]["dollars"])
        self.assertIsNotNone(card["points"][1]["dollars"])
        self.assertFalse(any("no trend yet" in n for n in card["notes"]))

        self.assertIn("| Date | haiku | sonnet | opus | frontier | Kits | Actual $ |",
                      md.stdout)
        self.assertIn("n/a", md.stdout)      # day 1's Actual $ cell (dollars None)
        self.assertIn("$12.50", md.stdout)   # day 2's Actual $ cell


# ---- 13b. role-ledger T4: an old-shape (schema v1, no "roles" key) snapshot still trends -------


class OldShapeSnapshotStillTrendsTests(unittest.TestCase):
    def test_v1_snapshot_without_roles_key_still_trends(self):
        # read_snapshots/build_trend are .get-tolerant of a pre-role-ledger (schema_version 1,
        # no top-level "roles" key) stored card -- exactly the shape every kit run BEFORE this
        # kit landed would have written. Neither function is edited by this kit; this proves
        # the tolerance holds rather than asserting it by inspection.
        with tempfile.TemporaryDirectory() as td:
            snap_dir = Path(td) / "snap"
            old_shape_card = {
                "schema_version": 1,   # pre-role-ledger — deliberately NOT rs.HISTORY_SCHEMA_VERSION
                "generated_at": "2026-01-01T00:00:00+00:00",
                "kits_dir": "/synthetic/kits",
                "kits": [{"kit": "solo"}],
                "tiers": {tier: {"with_outcome": 2, "first_try": 1, "first_try_rate": 0.5}
                          for tier in rs.LIVE_TIER_ORDER},
                "reroutes": {"events": 0, "applied": 0, "advisory": 0},
                "dollars": None,
                "notes": [],
                # no "roles" key at all
            }
            self.assertNotIn("roles", old_shape_card)
            rs.write_snapshot(old_shape_card, snap_dir, "2026-03-01")
            rs.write_snapshot(make_history_card(), snap_dir, "2026-03-02")

            r = _run_cli(["--history", "--trend", "--snapshot-dir", str(snap_dir), "--json"])
            self.assertEqual(r.returncode, 0, r.stderr)
            card = json.loads(r.stdout)

        self.assertEqual([p["date"] for p in card["points"]], ["2026-03-01", "2026-03-02"])
        self.assertEqual(card["points"][0]["tiers"]["haiku"]["first_try_rate"], 0.5)
        self.assertFalse(any("no trend yet" in n for n in card["notes"]))
        self.assertFalse(any("roles" in n for n in card["notes"]))  # no note about the gap


# ---- 14. malformed/rogue snapshots skipped -------------------------------------------------------


class TrendMalformedTests(unittest.TestCase):
    def test_trend_skips_malformed_and_rogue(self):
        with tempfile.TemporaryDirectory() as td:
            snap_dir = Path(td) / "snap"
            rs.write_snapshot(make_history_card(), snap_dir, "2026-01-01")
            rs.write_snapshot(make_history_card(), snap_dir, "2026-01-02")

            (snap_dir / "rogue.json").write_text("{}")
            (snap_dir / "2026-01-03.json").write_text("{not valid json")
            (snap_dir / "2026-01-04.json").write_text(
                json.dumps({"schema_version": 1, "notes": []}))  # no dict "tiers" key

            r = _run_cli(["--history", "--trend", "--snapshot-dir", str(snap_dir), "--json"])
            self.assertEqual(r.returncode, 0, r.stderr)
            card = json.loads(r.stdout)

        self.assertEqual([p["date"] for p in card["points"]], ["2026-01-01", "2026-01-02"])
        self.assertTrue(any(
            "rogue snapshot file skipped" in n and "rogue.json" in n for n in card["notes"]))
        self.assertTrue(any("2026-01-03.json" in n for n in card["notes"]))
        self.assertTrue(any("2026-01-04.json" in n for n in card["notes"]))
        self.assertFalse(any("no trend yet" in n for n in card["notes"]))


# ---- 15. pure --trend never loads pricing ---------------------------------------------------------


class TrendPricingFreeTests(unittest.TestCase):
    def test_trend_never_loads_pricing(self):
        original = rs.cr.load_pricing

        def _boom():
            raise RuntimeError("the pure --trend path must never load pricing")

        rs.cr.load_pricing = _boom
        try:
            with tempfile.TemporaryDirectory() as td:
                snap_dir = Path(td) / "snap"
                rs.write_snapshot(make_history_card(), snap_dir, "2026-03-01")

                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = rs.main(["--history", "--trend",
                                 "--snapshot-dir", str(snap_dir), "--json"])
            self.assertEqual(rc, 0)
            card = json.loads(buf.getvalue())
            self.assertEqual(len(card["points"]), 1)
        finally:
            rs.cr.load_pricing = original


# ---- 16. read-only proof, non-snapshot modes -------------------------------------------------------


class ReadOnlyNonSnapshotTests(unittest.TestCase):
    def test_readonly_non_snapshot_modes(self):
        with tempfile.TemporaryDirectory() as td:
            repo_a_kits = Path(td) / "repo-a" / ".claude" / "kits"
            repo_b_kits = Path(td) / "repo-b" / ".claude" / "kits"
            write_kit(repo_a_kits, "alpha", ALPHA_TASKS_MD)
            write_kit(repo_b_kits, "beta", BETA_TASKS_MD)
            projects_root = Path(td) / "projects"
            projects_root.mkdir()

            before = tree(Path(td))
            result = _run_cli(["--history",
                               "--kits-dir", str(repo_a_kits),
                               "--kits-dir", str(repo_b_kits),
                               "--projects-dir", str(projects_root), "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            after = tree(Path(td))
        self.assertEqual(before, after)

        with tempfile.TemporaryDirectory() as td2:
            snap_dir = Path(td2) / "snap"
            rs.write_snapshot(make_history_card(), snap_dir, "2026-04-01")
            rs.write_snapshot(make_history_card(), snap_dir, "2026-04-02")

            before2 = tree(Path(td2))
            result2 = _run_cli(["--history", "--trend",
                                "--snapshot-dir", str(snap_dir), "--json"])
            self.assertEqual(result2.returncode, 0, result2.stderr)
            after2 = tree(Path(td2))
        self.assertEqual(before2, after2)


# ---- 17. prior demos stay additive -------------------------------------------------------------------


class PriorDemosRegressionTests(unittest.TestCase):
    def test_prior_demos_regression(self):
        j = _run_cli(["--demo", "--json"])
        self.assertEqual(j.returncode, 0, j.stderr)
        c = json.loads(j.stdout)
        q = c["quality"]
        self.assertEqual(
            (q["total"], q["with_outcome"], q["first_try_pass"], q["retry_pass"],
             q["escalated_pass"], q["blocked"]), (6, 6, 3, 1, 1, 1))
        self.assertEqual(c["model_mix"], {"haiku": 1, "sonnet": 4, "fable": 1})
        self.assertAlmostEqual(c["review"]["survival_rate"], 0.75, places=9)

        l = _run_cli(["--demo", "--live", "--json"])
        self.assertEqual(l.returncode, 0, l.stderr)
        d = json.loads(l.stdout)
        self.assertEqual(d["autonomy"], "advisory")
        self.assertEqual(d["budget"], {"cap": 2, "applied": 0, "remaining": 2})
        recs = d["recommendations"]
        self.assertEqual(len(recs), 1)
        self.assertEqual((recs[0]["from"], recs[0]["to"], recs[0]["task_ids"]),
                         ("sonnet", "opus", ["L5", "L6"]))

        h = _run_cli(["--demo", "--history", "--json"])
        self.assertEqual(h.returncode, 0, h.stderr)
        hc = json.loads(h.stdout)
        K = ("pinned", "with_outcome", "first_try", "retry_pass", "escalated_pass", "blocked")
        pick = lambda tier: tuple(hc["tiers"][tier][k] for k in K)
        self.assertEqual(pick("haiku"), (3, 3, 2, 1, 0, 0))
        self.assertEqual(pick("sonnet"), (6, 5, 2, 1, 1, 1))
        self.assertEqual(pick("opus"), (2, 1, 1, 0, 0, 0))
        self.assertEqual(pick("frontier"), (1, 0, 0, 0, 0, 0))
        self.assertEqual(hc["reroutes"], {"events": 1, "applied": 0, "advisory": 1})
        self.assertEqual(hc["dollars"]["coverage"], "partial")
        self.assertNotIn("kits_dirs", hc)

        bt = _run_cli(["--demo", "--by-task", "--json"])
        self.assertEqual(bt.returncode, 0, bt.stderr)
        btc = json.loads(bt.stdout)["by_task"]
        self.assertEqual([r["id"] for r in btc["tasks"]], ["P1", "P2", "P3", "P4", "P5"])
        self.assertEqual(len(btc["clusters"]), 1)
        self.assertEqual(btc["clusters"][0]["agent_id"], "ag-warm")
        self.assertEqual(btc["clusters"][0]["task_ids"], ["P3", "P4"])
        self.assertEqual(btc["unattributed"]["agent_ids"], ["ag-reviewer"])
        self.assertEqual(btc["coverage"], "partial")


# ---- 18. the new demo's pinned trend card --------------------------------------------------------------


class TrendDemoPinnedTests(unittest.TestCase):
    def test_trend_demo_pinned(self):
        j = _run_cli(["--demo", "--history", "--trend", "--json"])
        self.assertEqual(j.returncode, 0, j.stderr)
        card = json.loads(j.stdout)

        self.assertEqual(card["schema_version"], 1)
        self.assertEqual([p["date"] for p in card["points"]], ["2026-01-01", "2026-01-02"])
        self.assertEqual(card["points"][0]["kits"], 2)
        self.assertEqual(card["points"][1]["kits"], 3)

        K = ("with_outcome", "first_try")
        for p in card["points"]:
            t = p["tiers"]
            self.assertEqual(tuple(t["haiku"][k] for k in K), (3, 2))
            self.assertEqual(tuple(t["sonnet"][k] for k in K), (5, 2))
            self.assertEqual(tuple(t["opus"][k] for k in K), (1, 1))
            self.assertEqual(tuple(t["frontier"][k] for k in K), (0, 0))
            self.assertIsNone(t["frontier"]["first_try_rate"])
            self.assertIsNotNone(p["dollars"])
            self.assertGreater(p["dollars"]["actual_usd"], 0)

        self.assertFalse(any("no trend yet" in n for n in card["notes"]))

        m = _run_cli(["--demo", "--history", "--trend"])
        self.assertEqual(m.returncode, 0, m.stderr)
        for needle in ("# Routing trend — per-tier first-try rate over time",
                      "| Date | haiku | sonnet | opus | frontier | Kits | Actual $ |",
                      "| 2026-01-01 |", "| 2026-01-02 |",
                      "2/3 (67%)", "2/5 (40%)", "1/1 (100%)"):
            self.assertIn(needle, m.stdout)


# ---- 19. default snapshot dir is gitignored --------------------------------------------------------


class DefaultSnapshotDirTests(unittest.TestCase):
    def test_default_snapshot_dir_gitignored(self):
        self.assertEqual(rs.DEFAULT_SNAPSHOT_DIR.name, "trends")

        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "check-ignore", "-q", "trends/2026-01-01.json"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
