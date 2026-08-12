"""Stdlib unittest regression suite for bin/harness_update.py (harness-update kit, T1-T6).

SAFETY CONTRACT: every fixture used below lives under a fresh `tempfile.TemporaryDirectory()`
(or, for `demo`, `harness_update.py`'s own self-cleaning `tempfile.mkdtemp()`) and is handed to
the engine via explicit `--repo-root` / `--installed-manifest` / `--copilot-home` /
`--codex-home` CLI flags (or the matching pure-function parameters). Every `_run_main` call
below passes `--copilot-home` and `--codex-home` explicitly so a run never falls through to the
real-home argparse defaults. This file never reads or writes the real `~/.claude`, `~/.copilot`,
or `~/.codex` -- `Path.home()` is never invoked anywhere in this file, and the real
`claude`/`copilot`/`codex`/`gh` CLIs are never invoked. `LiveTreeFreshnessTests` below is the one
exception that deliberately reads the real repo tree -- read-only, per PLAN.md D7 -- it is not a
fixture test and never writes.

bin/ is not a package; harness_update.py, harness_select.py, and sync_codex_surfaces.py (reused
only to materialize copilot-/codex-/data-section fixtures via their own `install_copilot` /
`plan_codex_setup` + `apply_codex_plan` / `sync` writers -- never imported into the engine's OWN
test assertions as a shortcut) are loaded via importlib by absolute path computed from this
file's own location, mirroring tests/test_harness_select.py's `_load` and
tests/test_plugin_staleness.py's `_load`.
"""

import ast
import contextlib
import hashlib
import importlib.util
import inspect
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hu = _load("harness_update")
hs = _load("harness_select")
ps = _load("plugin_staleness")

# A never-created directory under a temp root -- passed as --copilot-home / --codex-home in
# every _run_main call that isn't specifically exercising a real (fixture) home, so the CLI
# path never falls through to a real-home argparse default.
_UNUSED_HOME_NAME = "never-created-home"


# ---- fixture helpers (local to this file -- never imports another test module) ----------------

def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _make_repo(base, name="fake-plugin", marketplace="fake-market", version="1.0.0"):
    repo = base / "repo"
    _write(repo / ".claude-plugin" / "plugin.json", json.dumps({"name": name, "version": version}))
    _write(repo / ".claude-plugin" / "marketplace.json", json.dumps({"name": marketplace}))
    _write(repo / "CLAUDE.md", "# fixture guardrails\n")
    _write(repo / "bin" / "tool.py", "print('tool')\n")
    return repo


# Fake agent/skill bundle content -- deliberately not real route.agent.md / SKILL.md text, just
# something with the {{POLYTROPOS_ROOT}} placeholder appearing plus surrounding text that must
# survive byte-identical through install_copilot's resolution. Mirrors
# tests/test_harness_select.py's FAKE_AGENT_TEXT / FAKE_SKILL_TEXT fixtures (defined locally
# here, never imported from that file).
FAKE_AGENT_TEXT = (
    "---\n"
    "name: route\n"
    "description: fake agent fixture for harness-update copilot-section tests\n"
    "---\n"
    "\n"
    "Repo root is {{POLYTROPOS_ROOT}}.\n"
    "Pricing data lives at {{POLYTROPOS_ROOT}}/data/pricing.copilot.json.\n"
    "Nothing else here should change.\n"
)

FAKE_SKILL_TEXT = (
    "# lessons-loop (fake fixture)\n"
    "\n"
    "This skill lives under {{POLYTROPOS_ROOT}}/copilot/.github/skills/lessons-loop.\n"
    "Nothing else here should change.\n"
)


def _make_fake_copilot_bundle(repo, agent_text=FAKE_AGENT_TEXT, filename="route.agent.md"):
    """Add `<repo>/copilot/.github/agents/<filename>` with `agent_text` to an existing (or
    fresh) repo root."""
    agents_dir = repo / "copilot" / ".github" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / filename).write_text(agent_text)
    return repo


def _add_fake_skill(repo, skill_text=FAKE_SKILL_TEXT, rel="lessons-loop/SKILL.md"):
    """Add `<repo>/copilot/.github/skills/<rel>` with `skill_text` to an existing repo root."""
    skill_path = repo / "copilot" / ".github" / "skills" / rel
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(skill_text)
    return repo


# Canonical Codex agent roster harness_select._validate_agent_sources requires exactly --
# mismatching this set makes the "agents" component report "conflict" regardless of individual
# file states. Mirrors tests/test_codex_setup.py's AGENTS tuple (defined locally here, never
# imported from that file).
_CODEX_AGENT_ROSTER = ("kit-implementer", "kit-verifier", "phase-reviewer", "repo-explorer")


def _add_fake_codex_bundle(repo):
    """Add a minimal, VALID codex bundle to an existing repo root: `.codex-plugin/plugin.json`,
    `.agents/plugins/marketplace.json`, `codex/agents/<canonical-roster>.toml`,
    `codex/skills/route/SKILL.md`, `codex/prompts/route.md`, `codex/AGENTS.md`. Mirrors
    tests/test_codex_setup.py's `_fake_repo` fixture (defined locally here, never imported from
    that file) -- valid enough that harness_select's plugin/agent validation passes cleanly, so
    tests can focus on per-file install/up-to-date/managed-update/unmanaged/conflict states."""
    manifest = {"name": "polytropos", "version": "1.2.3", "skills": "./codex/skills/"}
    marketplace = {"plugins": [{"name": "polytropos", "source": {"source": "local", "path": "./"}}]}
    _write(repo / ".codex-plugin" / "plugin.json", json.dumps(manifest))
    _write(repo / ".agents" / "plugins" / "marketplace.json", json.dumps(marketplace))
    for name in _CODEX_AGENT_ROSTER:
        _write(
            repo / "codex" / "agents" / f"{name}.toml",
            f'name = "{name}"\n'
            f'description = "Fixture for {name}"\n'
            'developer_instructions = """Use tasks/kits/<slug>. '
            'States: pending | in-progress | done | blocked."""\n',
        )
    _write(repo / "codex" / "skills" / "route" / "SKILL.md", "Repo: {{POLYTROPOS_ROOT}}\n")
    _write(repo / "codex" / "prompts" / "route.md", "Repo: {{POLYTROPOS_ROOT}}\n")
    _write(repo / "codex" / "AGENTS.md", "Repo: {{POLYTROPOS_ROOT}}\n")
    return repo


def _apply_full_codex_install(hs_mod, repo, codex_home):
    """Materialize every codex component (plugin validation aside, which writes nothing) into
    `codex_home` / the repo's own `.codex/agents` -- the exact same call shape
    `harness_select.doctor_codex` itself uses (`legacy_copy=True, refresh_managed=False`,
    `agent_scope="project"`), so a follow-up `doctor_codex` call reports everything
    up-to-date."""
    plan = hs_mod.plan_codex_setup(
        repo,
        codex_home,
        components=hs_mod.CODEX_COMPONENTS,
        agent_scope="project",
        legacy_copy=True,
        refresh_managed=False,
    )
    hs_mod.apply_codex_plan(plan)
    return plan


def _add_full_codex_surfaces_bundle(repo, scs_mod):
    """On top of an existing `_add_fake_codex_bundle(repo)` fixture, add every
    `codex/skills/<stem>/SKILL.md` source `sync_codex_surfaces.expected_prompts()` needs
    (`scs_mod.SKILL_STEMS` -- reused by import, never hardcoded here; its `AGENT_PROMPTS` values
    are already covered by `_add_fake_codex_bundle`'s 4-agent roster), then materializes the
    `codex/prompts/*.md` mirrors via the module's own `sync(mode="build")` writer so a follow-up
    `sync(mode="check")` call reports clean."""
    for stem in scs_mod.SKILL_STEMS:
        _write(
            repo / "codex" / "skills" / stem / "SKILL.md",
            f"---\nname: {stem}\ndescription: fixture skill {stem}\n---\n\nFixture body for {stem}.\n",
        )
    scs_mod.sync(repo, "build")
    return repo


def _build_fresh_data_fixture(base, cached_dates=None):
    """Build `<base>/repo` with fully in-sync pricing mirrors, matching docs snapshot labels,
    and a complete codex-surfaces bundle, so `build_data_section()` reports "up-to-date" by
    default. Also writes a default `.claude-plugin/plugin.json`/`marketplace.json` identity
    (name "fake-plugin", marketplace "fake-market", version "1.0.0") -- `build_claude_section`
    is called unconditionally by `run_check` and `plugin_staleness.read_plugin_identity` raises
    if those files are absent, so every `run_check` caller needs them regardless of whether the
    test cares about the claude section; callers wanting different identity values (or a
    matching install dir for an IN-SYNC scenario) overwrite these two files afterward.
    `cached_dates` optionally overrides the three pricing files' `cached_date` strings (keyed by
    the same relative paths `hu.PRICING_FILES` uses). Returns `(repo, dates)`."""
    cached_dates = cached_dates or {}
    dates = {
        "data/pricing.json": cached_dates.get("data/pricing.json", "2020-01-01"),
        "data/pricing.copilot.json": cached_dates.get("data/pricing.copilot.json", "2020-01-02"),
        "data/pricing.codex.json": cached_dates.get("data/pricing.codex.json", "2020-01-03"),
    }
    repo = base / "repo"
    _write(repo / ".claude-plugin" / "plugin.json", json.dumps({"name": "fake-plugin", "version": "1.0.0"}))
    _write(repo / ".claude-plugin" / "marketplace.json", json.dumps({"name": "fake-market"}))
    for rel, cached_date in dates.items():
        _write(repo / rel, json.dumps({"cached_date": cached_date, "models": {}}))
    _write(repo / "README.md", f"Pricing snapshot cached {dates['data/pricing.json']}.\n")
    _write(repo / "docs" / "COPILOT-HARNESS.md", f"Copilot snapshot cached {dates['data/pricing.copilot.json']}.\n")

    (repo / "skills" / "route").mkdir(parents=True, exist_ok=True)
    (repo / "skills" / "fable-check").mkdir(parents=True, exist_ok=True)
    spr = _load("sync_pricing_refs")
    spr.sync(repo)

    _add_fake_codex_bundle(repo)
    scs = _load("sync_codex_surfaces")
    _add_full_codex_surfaces_bundle(repo, scs)

    return repo, dates


def _make_install(base, subdir="install/1.0.0"):
    install = base / subdir
    _write(install / "CLAUDE.md", "# fixture guardrails\n")
    _write(install / "bin" / "tool.py", "print('tool')\n")
    return install


def _write_manifest(base, plugin_key, entry, name="manifest.json"):
    path = base / name
    path.write_text(json.dumps({"version": 2, "plugins": {plugin_key: [entry]}}))
    return path


def _add_git_ref_head(repo, sha, ref="refs/heads/main"):
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text(f"ref: {ref}\n")
    ref_path = git_dir / ref
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_text(sha + "\n")


def _tree_digest(base):
    """Recursive content digest of every file under base, keyed by relative path -- used to
    prove `check` never writes anything anywhere in its fixture trees."""
    base = Path(base)
    digest = hashlib.sha256()
    if not base.exists():
        return digest.hexdigest()
    for path in sorted(base.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(base).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _run_main(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = hu.main(argv)
    return code, buf.getvalue()


# ---- T6 apply fixtures --------------------------------------------------------------------------
#
# Every apply fixture below is built from `hu.build_demo_tree()` -- the engine's OWN synthetic
# tree builder -- rather than a hand-rolled repo. That is deliberate: build_demo_tree already
# knows the canonical Codex agent roster harness_select._validate_agent_sources demands, and the
# kit's standing rule is that no THIRD copy of that roster may exist (the demo's copy is the
# documented second one, and it fails loudly if the roster ever drifts). Reusing the builder here
# means these tests inherit that single source instead of adding another. build_demo_tree creates
# and fully installs its own temp repo root, copilot home, and codex home; the caller owns
# cleanup via shutil.rmtree(root).

def _seed_drifted_claude_manifest(root, manifest_path):
    """Make the claude section report DRIFTED against a fixture, using only fixture paths: write
    an installed-plugins manifest whose install record points at a directory that never exists, so
    plugin_staleness's compare_files sees every repo-side file as missing on the installed side.
    The plugin key is READ from the fixture's own identity files (never hardcoded here)."""
    name, marketplace, version = ps.read_plugin_identity(root)
    entry = {"installPath": str(root / "never-installed-cache"), "version": version}
    manifest_path.write_text(json.dumps({"version": 2, "plugins": {f"{name}@{marketplace}": [entry]}}))
    return manifest_path


def _seed_repairable_drift(root, copilot_home, codex_home):
    """Seed exactly the three drifts `apply`'s delegated writers own -- and nothing else. No docs
    snapshot label is touched here (unlike `hu.seed_demo_drift`), because this fixture exists to
    prove the round-trip reaches "fresh everywhere except claude": a stale docs label is drift
    `apply` deliberately refuses to fix, so seeding one would make the follow-up check fail for a
    second, unrelated reason."""
    agent = sorted((copilot_home / "agents").glob("*.agent.md"))[0]
    agent.write_text(agent.read_text() + "\n# tampered by the user\n")
    installed_prompts = sorted((codex_home / "prompts").glob("*.md"))
    assert installed_prompts, "fixture codex home should have installed prompts"
    for prompt in installed_prompts:
        prompt.unlink()
    (root / "skills" / "route" / "references" / "pricing.json").write_text('{"corrupted": true}\n')


def _claude_named_paths(base):
    """Every path under `base` with a `.claude` path component -- the canary set apply must never
    grow (`.claude-plugin` is a different component name and is deliberately not matched)."""
    base = Path(base)
    if not base.exists():
        return set()
    return {
        path.relative_to(base).as_posix()
        for path in base.rglob("*")
        if ".claude" in path.relative_to(base).parts
    }


# ---- build_claude_section / run_check: reuse of plugin_staleness's statuses --------------------

class ClaudeSectionInSyncTests(unittest.TestCase):
    def test_in_sync_fixture_produces_in_sync_status_and_no_drift(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market", version="1.0.0")
            sha = "d" * 40
            _add_git_ref_head(repo, sha)
            install = _make_install(base)
            entry = {"installPath": str(install), "version": "1.0.0", "gitCommitSha": sha}
            manifest = _write_manifest(base, "fake-plugin@fake-market", entry)

            result = hu.run_check(repo, manifest)
            self.assertEqual(result["claude"]["status"], "IN SYNC")
            self.assertFalse(result["claude"]["drift"])
            # Not asserting the aggregate result["status"]/["exit"] here: this minimal fixture
            # has no data/pricing*.json files, so the (unrelated, since T5) data section
            # legitimately reports drift on its own -- the aggregate widening itself is covered
            # by JsonEnvelopeTests and AggregateNoPlaceholderTests against a fully-fresh fixture.

    def test_extra_glob_matched_pricing_file_in_repo_but_not_install_drifts_claude(self):
        # Regression guard for the exact fixture-composition trap above: plugin_staleness's
        # COMPARE_GLOBS includes "data/pricing*.json", so if a repo fixture carries pricing
        # files (as T5's data-section fixtures do) but the paired install dir does not, the
        # CLAUDE section itself -- not just data -- correctly reports DRIFTED (a missing file).
        # This is existing plugin_staleness behavior, not new in this task; documented here so
        # a future editor does not "fix" ClaudeSectionInSyncTests by blindly reusing
        # _build_fresh_data_fixture for its repo.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, _dates = _build_fresh_data_fixture(base)
            _write(repo / ".claude-plugin" / "plugin.json", json.dumps({"name": "fake-plugin", "version": "1.0.0"}))
            _write(repo / ".claude-plugin" / "marketplace.json", json.dumps({"name": "fake-market"}))
            sha = "d" * 40
            _add_git_ref_head(repo, sha)
            install = _make_install(base)  # no data/ dir -> pricing files are "missing" there
            entry = {"installPath": str(install), "version": "1.0.0", "gitCommitSha": sha}
            manifest = _write_manifest(base, "fake-plugin@fake-market", entry)

            result = hu.run_check(repo, manifest)
            self.assertEqual(result["claude"]["status"], "DRIFTED")
            self.assertTrue(result["claude"]["drift"])


class ClaudeSectionNotInstalledTests(unittest.TestCase):
    def test_not_installed_exits_0(self):
        # "not installed" short-circuits before plugin_staleness ever calls compare_files, so
        # combining this with a fully-fresh data fixture is safe and lets this test prove what
        # its name says: the aggregate genuinely exits 0.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, _dates = _build_fresh_data_fixture(base)
            _write(repo / ".claude-plugin" / "plugin.json", json.dumps({"name": "fake-plugin", "version": "1.0.0"}))
            _write(repo / ".claude-plugin" / "marketplace.json", json.dumps({"name": "fake-market"}))
            manifest = base / "does-not-exist.json"

            result = hu.run_check(repo, manifest, today=date(2020, 1, 10))
            self.assertEqual(result["claude"]["status"], "not installed")
            self.assertFalse(result["claude"]["drift"])
            self.assertEqual(result["status"], "fresh")
            self.assertEqual(result["exit"], 0)


class ClaudeSectionDriftedTests(unittest.TestCase):
    def test_file_diff_drifts_and_exits_3(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market", version="1.0.0")
            install = _make_install(base)
            (install / "CLAUDE.md").write_text("# stale content\n")
            entry = {"installPath": str(install), "version": "1.0.0"}
            manifest = _write_manifest(base, "fake-plugin@fake-market", entry)

            result = hu.run_check(repo, manifest)
            self.assertEqual(result["claude"]["status"], "DRIFTED")
            self.assertTrue(result["claude"]["drift"])
            self.assertEqual(result["status"], "drift")
            self.assertEqual(result["exit"], hu.EXIT_DRIFT)
            self.assertEqual(result["exit"], 3)

    def test_sha_mismatch_counts_as_drift_and_exits_3(self):
        # plugin_staleness itself treats a lone SHA mismatch (identical files, matching version)
        # as SHA STALE -- exit 0, non-actionable. This engine's aggregate check widens that: SHA
        # STALE still counts as drift for harness-update's own exit code (see
        # build_claude_section's docstring for why).
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market", version="1.0.0")
            _add_git_ref_head(repo, "6" * 40)
            install = _make_install(base)  # byte-identical files
            entry = {"installPath": str(install), "version": "1.0.0", "gitCommitSha": "e" * 40}
            manifest = _write_manifest(base, "fake-plugin@fake-market", entry)

            result = hu.run_check(repo, manifest)
            self.assertEqual(result["claude"]["status"], "SHA STALE")
            self.assertTrue(result["claude"]["drift"])
            self.assertEqual(result["status"], "drift")
            self.assertEqual(result["exit"], 3)


# ---- --json envelope shape ----------------------------------------------------------------------

class JsonEnvelopeTests(unittest.TestCase):
    def test_json_has_four_sections_plus_status_and_exit(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, dates = _build_fresh_data_fixture(base)
            _write(repo / ".claude-plugin" / "plugin.json", json.dumps({"name": "fake-plugin", "version": "1.0.0"}))
            _write(repo / ".claude-plugin" / "marketplace.json", json.dumps({"name": "fake-market"}))
            manifest = base / "absent.json"
            copilot_home = base / _UNUSED_HOME_NAME  # never created -> "not installed"
            codex_home = base / "never-created-codex-home"

            code, out = _run_main(
                [
                    "check",
                    "--repo-root", str(repo),
                    "--installed-manifest", str(manifest),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                    "--json",
                ]
            )
            self.assertEqual(code, 0)
            parsed = json.loads(out)
            self.assertEqual(set(parsed.keys()), {"claude", "copilot", "codex", "data", "status", "exit"})
            self.assertEqual(
                parsed["copilot"], {"status": "not installed", "drift": False, "counts": {}, "files": []}
            )
            self.assertEqual(
                parsed["codex"],
                {
                    "status": "not installed",
                    "drift": False,
                    "counts": {},
                    "ownership_manifest": None,
                    "session_note": None,
                    "actions": [],
                },
            )
            self.assertEqual(parsed["data"]["status"], "up-to-date")
            self.assertFalse(parsed["data"]["drift"])
            self.assertEqual(len(parsed["data"]["pricing_ages"]), 3)
            self.assertEqual(parsed["status"], "fresh")
            self.assertEqual(parsed["exit"], 0)

    def test_json_drift_status_and_exit_agree(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market", version="2.0.0")
            install = _make_install(base)  # byte-identical files, version differs
            entry = {"installPath": str(install), "version": "1.0.0"}
            manifest = _write_manifest(base, "fake-plugin@fake-market", entry)
            copilot_home = base / _UNUSED_HOME_NAME
            codex_home = base / "never-created-codex-home"

            code, out = _run_main(
                [
                    "check",
                    "--repo-root", str(repo),
                    "--installed-manifest", str(manifest),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                    "--json",
                ]
            )
            self.assertEqual(code, 3)
            parsed = json.loads(out)
            self.assertEqual(parsed["status"], "drift")
            self.assertEqual(parsed["exit"], 3)
            self.assertEqual(parsed["claude"]["status"], "DRIFTED")

    def test_human_card_renders_without_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, dates = _build_fresh_data_fixture(base)
            _write(repo / ".claude-plugin" / "plugin.json", json.dumps({"name": "fake-plugin", "version": "1.0.0"}))
            _write(repo / ".claude-plugin" / "marketplace.json", json.dumps({"name": "fake-market"}))
            manifest = base / "absent.json"
            copilot_home = base / _UNUSED_HOME_NAME
            codex_home = base / "never-created-codex-home"

            code, out = _run_main(
                [
                    "check",
                    "--repo-root", str(repo),
                    "--installed-manifest", str(manifest),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                ]
            )
            self.assertEqual(code, 0)
            self.assertNotIn("Traceback", out)
            self.assertIn("## claude", out)
            self.assertIn("## copilot", out)
            self.assertIn("## codex", out)
            self.assertIn("## data", out)
            self.assertIn("verdict: all sections fresh", out)
            self.assertIn("status: fresh", out)
            self.assertIn("exit: 0", out)


# ---- copilot section: build_copilot_section / run_check states --------------------------------

class CopilotSectionNotInstalledTests(unittest.TestCase):
    # manifest stays absent below -> claude is always "not installed" (never calls
    # plugin_staleness.compare_files), so combining these fixtures with a fully-fresh data
    # fixture is safe and lets each test prove a genuinely fresh aggregate, not just the
    # copilot section in isolation.
    def test_absent_copilot_home_is_not_installed_exit_0(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, _dates = _build_fresh_data_fixture(base)
            _make_fake_copilot_bundle(repo)
            copilot_home = base / _UNUSED_HOME_NAME  # never created
            manifest = base / "absent.json"

            result = hu.run_check(repo, manifest, copilot_home=copilot_home, today=date(2020, 1, 10))
            self.assertEqual(
                result["copilot"], {"status": "not installed", "drift": False, "counts": {}, "files": []}
            )
            self.assertEqual(result["exit"], 0)

    def test_copilot_home_none_is_also_not_installed(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, _dates = _build_fresh_data_fixture(base)
            _make_fake_copilot_bundle(repo)
            manifest = base / "absent.json"

            result = hu.run_check(repo, manifest, today=date(2020, 1, 10))  # copilot_home omitted entirely
            self.assertEqual(result["copilot"]["status"], "not installed")
            self.assertEqual(result["exit"], 0)


class CopilotSectionFreshInstallTests(unittest.TestCase):
    def test_fresh_install_all_up_to_date_exit_0(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, _dates = _build_fresh_data_fixture(base)
            _add_fake_skill(_make_fake_copilot_bundle(repo))
            copilot_home = base / "copilot-home"
            hs.install_copilot(copilot_home, repo_root=repo)
            manifest = base / "absent.json"

            result = hu.run_check(repo, manifest, copilot_home=copilot_home, today=date(2020, 1, 10))
            section = result["copilot"]
            self.assertEqual(section["status"], "up-to-date")
            self.assertFalse(section["drift"])
            self.assertEqual(section["counts"], {"up-to-date": 2, "missing": 0, "differs": 0})
            self.assertEqual(result["exit"], 0)
            paths = {f["path"] for f in section["files"]}
            self.assertEqual(paths, {"agents/route.agent.md", "skills/lessons-loop/SKILL.md"})


class CopilotSectionDriftedTests(unittest.TestCase):
    def test_edited_destination_is_differs_exit_3(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_fake_copilot_bundle(_make_repo(base))
            copilot_home = base / "copilot-home"
            hs.install_copilot(copilot_home, repo_root=repo)
            (copilot_home / "agents" / "route.agent.md").write_text("# tampered by the user\n")
            manifest = base / "absent.json"

            result = hu.run_check(repo, manifest, copilot_home=copilot_home)
            section = result["copilot"]
            self.assertEqual(section["status"], "drift")
            self.assertTrue(section["drift"])
            self.assertEqual(section["counts"]["differs"], 1)
            self.assertEqual(result["exit"], 3)

    def test_never_installed_destination_file_is_missing_exit_3(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_fake_copilot_bundle(_make_repo(base))
            copilot_home = base / "copilot-home"
            # Home directory exists (e.g. created for other reasons) but nothing was ever
            # installed into it -- the comparator must report the bundle file "missing", not
            # fall back to the "not installed" status (that's reserved for a wholly absent home).
            copilot_home.mkdir(parents=True)
            manifest = base / "absent.json"

            result = hu.run_check(repo, manifest, copilot_home=copilot_home)
            section = result["copilot"]
            self.assertEqual(section["status"], "drift")
            self.assertTrue(section["drift"])
            self.assertEqual(section["counts"]["missing"], 1)
            self.assertEqual(result["exit"], 3)


class CopilotSectionIgnoresExtraDestFileTests(unittest.TestCase):
    def test_extra_unbundled_destination_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, _dates = _build_fresh_data_fixture(base)
            _make_fake_copilot_bundle(repo)
            copilot_home = base / "copilot-home"
            hs.install_copilot(copilot_home, repo_root=repo)
            # A file the bundle knows nothing about, e.g. the user's own personal agent.
            (copilot_home / "agents" / "not-ours.agent.md").write_text("# some other agent\n")
            manifest = base / "absent.json"

            result = hu.run_check(repo, manifest, copilot_home=copilot_home, today=date(2020, 1, 10))
            section = result["copilot"]
            self.assertEqual(section["status"], "up-to-date")
            self.assertFalse(section["drift"])
            self.assertEqual(result["exit"], 0)
            paths = {f["path"] for f in section["files"]}
            self.assertNotIn("agents/not-ours.agent.md", paths)


class CopilotSectionMissingRepoBundleTests(unittest.TestCase):
    # These fixtures still need valid .claude-plugin identity files (via _make_repo) so the
    # claude section (built first, unconditionally, by run_check) doesn't itself raise -- only
    # the copilot bundle under repo/copilot/.github/agents/ is deliberately absent/empty.
    def test_missing_agents_dir_is_error_and_drift_exit_3(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base)  # no copilot/.github/agents at all
            copilot_home = base / "copilot-home"
            copilot_home.mkdir()
            manifest = base / "absent.json"

            result = hu.run_check(repo, manifest, copilot_home=copilot_home)
            section = result["copilot"]
            self.assertEqual(section["status"], "error")
            self.assertTrue(section["drift"])
            self.assertIn("copilot/.github/agents", section["error"])
            self.assertEqual(result["exit"], 3)

    def test_empty_agents_dir_is_also_error(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base)
            (repo / "copilot" / ".github" / "agents").mkdir(parents=True)  # present but empty
            copilot_home = base / "copilot-home"
            copilot_home.mkdir()
            manifest = base / "absent.json"

            result = hu.run_check(repo, manifest, copilot_home=copilot_home)
            self.assertEqual(result["copilot"]["status"], "error")
            self.assertEqual(result["exit"], 3)


class CopilotPlaceholderReuseTests(unittest.TestCase):
    def test_engine_defines_no_second_placeholder_constant(self):
        source = (BIN_DIR / "harness_update.py").read_text()
        self.assertNotIn("{{POLYTROPOS_ROOT}}", source)
        self.assertIn("harness_select_mod.PLACEHOLDER", source)


# ---- codex section: build_codex_section / run_check states -------------------------------------

class CodexSectionNotInstalledTests(unittest.TestCase):
    # manifest stays absent below -> claude is always "not installed" and codex_home is either
    # absent or None, so build_codex_section short-circuits before ever reading the repo's
    # codex/ bundle -- combining these with a fully-fresh data fixture is safe and proves a
    # genuinely fresh aggregate.
    def test_absent_codex_home_is_not_installed_exit_0(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, _dates = _build_fresh_data_fixture(base)
            codex_home = base / "never-created-codex-home"  # never created
            manifest = base / "absent.json"

            result = hu.run_check(repo, manifest, codex_home=codex_home, today=date(2020, 1, 10))
            self.assertEqual(
                result["codex"],
                {
                    "status": "not installed",
                    "drift": False,
                    "counts": {},
                    "ownership_manifest": None,
                    "session_note": None,
                    "actions": [],
                },
            )
            self.assertEqual(result["exit"], 0)

    def test_codex_home_none_is_also_not_installed(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, _dates = _build_fresh_data_fixture(base)
            manifest = base / "absent.json"

            result = hu.run_check(repo, manifest, today=date(2020, 1, 10))  # codex_home omitted entirely
            self.assertEqual(result["codex"]["status"], "not installed")
            self.assertEqual(result["exit"], 0)


class CodexSectionFreshTests(unittest.TestCase):
    def test_fresh_nothing_installed_counts_install_actions_and_drifts_exit_3(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _add_fake_codex_bundle(_make_repo(base))
            codex_home = base / "codex-home"
            codex_home.mkdir()  # home exists but nothing was ever installed into it
            manifest = base / "absent.json"

            result = hu.run_check(repo, manifest, codex_home=codex_home)
            section = result["codex"]
            self.assertEqual(section["status"], "drift")
            self.assertTrue(section["drift"])
            # 4 canonical agents + skills + prompts + guidance, all destinations absent.
            self.assertEqual(section["counts"].get("install", 0), 7)
            self.assertEqual(section["ownership_manifest"], "absent")
            self.assertEqual(result["exit"], 3)


class CodexSectionFullyInstalledTests(unittest.TestCase):
    def test_fully_installed_and_matching_exits_0(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, _dates = _build_fresh_data_fixture(base)  # already carries a valid codex bundle
            codex_home = base / "codex-home"
            _apply_full_codex_install(hs, repo, codex_home)
            manifest = base / "absent.json"

            result = hu.run_check(repo, manifest, codex_home=codex_home, today=date(2020, 1, 10))
            section = result["codex"]
            self.assertEqual(section["status"], "up-to-date")
            self.assertFalse(section["drift"])
            self.assertEqual(section["counts"].get("install", 0), 0)
            self.assertEqual(section["counts"].get("conflict", 0), 0)
            self.assertEqual(section["ownership_manifest"], "present")
            self.assertEqual(result["exit"], 0)


class CodexSectionConflictTests(unittest.TestCase):
    def test_unresolved_placeholder_destination_is_conflict_and_drifts_exit_3(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _add_fake_codex_bundle(_make_repo(base))
            codex_home = base / "codex-home"
            # Destination carries the raw, unresolved {{POLYTROPOS_ROOT}} literal --
            # plan_codex_setup flags this specific shape as "conflict".
            dest = codex_home / "skills" / "route" / "SKILL.md"
            dest.parent.mkdir(parents=True)
            dest.write_text((repo / "codex" / "skills" / "route" / "SKILL.md").read_text())
            manifest = base / "absent.json"

            result = hu.run_check(repo, manifest, codex_home=codex_home)
            section = result["codex"]
            self.assertEqual(section["status"], "drift")
            self.assertTrue(section["drift"])
            self.assertGreaterEqual(section["counts"].get("conflict", 0), 1)
            self.assertEqual(result["exit"], 3)


class CodexSectionUnmanagedWarningTests(unittest.TestCase):
    def test_unmanaged_is_a_warning_not_drift(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, _dates = _build_fresh_data_fixture(base)  # already carries a valid codex bundle
            codex_home = base / "codex-home"
            _apply_full_codex_install(hs, repo, codex_home)
            # Edit the SOURCE after install -- doctor_codex (refresh_managed=False) reports the
            # managed copy as merely "unmanaged" (stale, no refresh requested), not "conflict".
            source = repo / "codex" / "agents" / "kit-implementer.toml"
            source.write_text(source.read_text() + "# refreshed upstream\n")
            manifest = base / "absent.json"

            result = hu.run_check(repo, manifest, codex_home=codex_home, today=date(2020, 1, 10))
            section = result["codex"]
            self.assertEqual(section["counts"].get("unmanaged", 0), 1)
            self.assertEqual(section["counts"].get("install", 0), 0)
            self.assertEqual(section["counts"].get("conflict", 0), 0)
            self.assertEqual(section["counts"].get("managed-update", 0), 0)
            self.assertFalse(section["drift"])
            self.assertEqual(section["status"], "up-to-date")
            self.assertEqual(result["exit"], 0)
            # The warning must still be visible in the human card, never hidden.
            card = hu.render_card(result)
            self.assertIn("unmanaged", card)
            self.assertIn("not drift", card)


# ---- data section: build_data_section states ----------------------------------------------------

class DataSectionFreshTests(unittest.TestCase):
    def test_fully_fresh_fixture_is_up_to_date(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, dates = _build_fresh_data_fixture(base)

            section = hu.build_data_section(repo, today=date(2020, 1, 10))
            self.assertEqual(section["status"], "up-to-date")
            self.assertFalse(section["drift"])
            self.assertEqual(len(section["pricing_ages"]), 3)
            for age in section["pricing_ages"]:
                self.assertFalse(age["stale_flag"])
                self.assertNotIn("note", age)
            for label in section["docs_labels"]:
                self.assertTrue(label["ok"])
            self.assertEqual(section["mirrors"]["pricing_stale"], [])
            self.assertEqual(section["mirrors"]["codex_stale"], [])
            self.assertEqual(section["mirrors"]["errors"], [])


class DataSectionPricingAgeTests(unittest.TestCase):
    def test_age_over_60_days_flags_but_never_drifts(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, dates = _build_fresh_data_fixture(base)  # cached_date 2020-01-0{1,2,3}

            section = hu.build_data_section(repo, today=date(2020, 6, 1))  # ~150 days later
            for age in section["pricing_ages"]:
                self.assertTrue(age["stale_flag"])
                self.assertGreater(age["age_days"], hu.PRICING_AGE_STALE_DAYS)
                self.assertEqual(age["note"], "re-verify against source")
            # Age staleness alone must never drift -- everything else in this fixture is fresh.
            self.assertFalse(section["drift"])
            self.assertEqual(section["status"], "up-to-date")

    def test_age_computed_correctly_against_injected_today(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, dates = _build_fresh_data_fixture(base)

            section = hu.build_data_section(repo, today=date(2020, 1, 11))
            ages = {age["file"]: age["age_days"] for age in section["pricing_ages"]}
            self.assertEqual(ages["data/pricing.json"], 10)  # 2020-01-01 -> 2020-01-11
            self.assertEqual(ages["data/pricing.copilot.json"], 9)
            self.assertEqual(ages["data/pricing.codex.json"], 8)

    def test_missing_pricing_file_reports_unreadable_not_a_crash(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, dates = _build_fresh_data_fixture(base)
            (repo / "data" / "pricing.json").unlink()

            section = hu.build_data_section(repo, today=date(2020, 1, 10))
            age = next(a for a in section["pricing_ages"] if a["file"] == "data/pricing.json")
            self.assertIsNone(age["cached_date"])
            self.assertIsNone(age["age_days"])
            self.assertFalse(age["stale_flag"])
            self.assertIn("unreadable or missing", age["note"])


class DataSectionMirrorDriftTests(unittest.TestCase):
    def test_stale_pricing_mirror_drifts(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, dates = _build_fresh_data_fixture(base)
            (repo / "skills" / "route" / "references" / "pricing.json").write_text('{"corrupted": true}')

            section = hu.build_data_section(repo, today=date(2020, 1, 10))
            self.assertEqual(section["status"], "drift")
            self.assertTrue(section["drift"])
            self.assertIn(
                "skills/route/references/pricing.json", section["mirrors"]["pricing_stale"]
            )
            self.assertEqual(section["mirrors"]["codex_stale"], [])

    def test_stale_codex_mirror_drifts(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, dates = _build_fresh_data_fixture(base)
            prompt_files = sorted((repo / "codex" / "prompts").glob("*.md"))
            self.assertTrue(prompt_files)
            prompt_files[0].write_text("corrupted mirror content\n")

            section = hu.build_data_section(repo, today=date(2020, 1, 10))
            self.assertEqual(section["status"], "drift")
            self.assertTrue(section["drift"])
            self.assertTrue(section["mirrors"]["codex_stale"])
            self.assertEqual(section["mirrors"]["pricing_stale"], [])


class DataSectionMirrorErrorTests(unittest.TestCase):
    def test_missing_codex_bundle_surfaces_as_mirror_error_and_drift(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = base / "repo"
            for rel, cached_date in (
                ("data/pricing.json", "2020-01-01"),
                ("data/pricing.copilot.json", "2020-01-02"),
                ("data/pricing.codex.json", "2020-01-03"),
            ):
                _write(repo / rel, json.dumps({"cached_date": cached_date}))
            (repo / "skills" / "route").mkdir(parents=True)
            (repo / "skills" / "fable-check").mkdir(parents=True)
            spr = _load("sync_pricing_refs")
            spr.sync(repo)
            # No codex/ bundle at all -> sync_codex_surfaces.expected_prompts() raises reading
            # the first missing canonical skill source -- must be caught, not crash `check`.

            section = hu.build_data_section(repo, today=date(2020, 1, 10))
            self.assertEqual(section["status"], "drift")
            self.assertTrue(section["drift"])
            self.assertTrue(section["mirrors"]["errors"])
            self.assertEqual(section["mirrors"]["codex_stale"], [])
            # Pricing mirrors were still built cleanly -- only the codex side errored.
            self.assertEqual(section["mirrors"]["pricing_stale"], [])


class DataSectionDocsLabelTests(unittest.TestCase):
    def test_stale_pricing_json_label_drifts(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, dates = _build_fresh_data_fixture(base)
            (repo / "README.md").write_text("no matching date in here\n")

            section = hu.build_data_section(repo, today=date(2020, 1, 10))
            self.assertEqual(section["status"], "drift")
            self.assertTrue(section["drift"])
            label = next(l for l in section["docs_labels"] if l["file"] == "data/pricing.json")
            self.assertFalse(label["ok"])
            self.assertIn("docs snapshot label stale", label["note"])

    def test_stale_copilot_pricing_label_drifts(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, dates = _build_fresh_data_fixture(base)
            (repo / "docs" / "COPILOT-HARNESS.md").write_text("no matching date in here\n")

            section = hu.build_data_section(repo, today=date(2020, 1, 10))
            self.assertTrue(section["drift"])
            label = next(l for l in section["docs_labels"] if l["file"] == "data/pricing.copilot.json")
            self.assertFalse(label["ok"])

    def test_codex_partner_doc_never_checked_and_never_drifts(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, dates = _build_fresh_data_fixture(base)

            section = hu.build_data_section(repo, today=date(2020, 1, 10))
            label = next(l for l in section["docs_labels"] if l["file"] == "data/pricing.codex.json")
            self.assertTrue(label["ok"])
            self.assertIsNone(label["doc"])
            self.assertIn("codex partner doc carries no numeric snapshot by design", label["note"])


# ---- aggregate: no T1 placeholder survives --------------------------------------------------------

class AggregateNoPlaceholderTests(unittest.TestCase):
    def test_json_contains_no_not_implemented_value_anywhere(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, dates = _build_fresh_data_fixture(base)
            _write(repo / ".claude-plugin" / "plugin.json", json.dumps({"name": "x", "version": "1.0.0"}))
            _write(repo / ".claude-plugin" / "marketplace.json", json.dumps({"name": "y"}))
            manifest = base / "absent.json"
            copilot_home = base / "never-created-copilot-home"
            codex_home = base / "never-created-codex-home"

            result = hu.run_check(
                repo, manifest, copilot_home=copilot_home, codex_home=codex_home, today=date(2020, 1, 10)
            )
            raw = json.dumps(result)
            self.assertNotIn("not-implemented", raw)
            self.assertEqual(set(result.keys()), {"claude", "copilot", "codex", "data", "status", "exit"})


# ---- demo: synthetic, self-cleaning smoke ---------------------------------------------------------

class DemoTreeTests(unittest.TestCase):
    def test_build_demo_tree_root_is_a_temp_tree_not_the_real_repo(self):
        root, copilot_home, codex_home, installed_manifest = hu.build_demo_tree()
        try:
            self.assertNotEqual(str(root), str(REPO_ROOT))
            self.assertTrue(root.name.startswith("harness-update-demo-"))
            self.assertFalse(installed_manifest.exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_demo_tree_is_genuinely_fresh_then_seeded_drift_is_genuinely_drift(self):
        root, copilot_home, codex_home, installed_manifest = hu.build_demo_tree()
        try:
            fresh = hu.run_check(root, installed_manifest, copilot_home=copilot_home, codex_home=codex_home)
            self.assertEqual(fresh["status"], "fresh")
            self.assertEqual(fresh["exit"], 0)

            hu.seed_demo_drift(root, copilot_home)

            drifted = hu.run_check(root, installed_manifest, copilot_home=copilot_home, codex_home=codex_home)
            self.assertEqual(drifted["status"], "drift")
            self.assertEqual(drifted["exit"], 3)
            self.assertTrue(drifted["copilot"]["drift"])
            self.assertTrue(drifted["data"]["drift"])
        finally:
            shutil.rmtree(root, ignore_errors=True)


class RunDemoCliTests(unittest.TestCase):
    def test_demo_subcommand_prints_every_card_and_exits_0(self):
        code, out = _run_main(["demo"])
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", out)
        self.assertIn("=== demo: fresh synthetic tree ===", out)
        self.assertIn("=== demo: seeded drift ===", out)
        self.assertIn("=== demo: apply --dry-run (writes nothing) ===", out)
        self.assertIn("=== demo: apply ===", out)
        self.assertIn("verdict: all sections fresh", out)
        self.assertIn("verdict: drifted", out)
        self.assertIn("verdict: dry-run complete -- nothing written", out)
        self.assertIn("verdict: apply complete", out)
        # The last card legitimately prints "exit: 3" (the docs snapshot label is never
        # auto-fixed). The smoke must say plainly that this is the CARD's value, not its own.
        self.assertIn("exit: 3", out)
        self.assertIn(
            "demo process exit: 0 -- this smoke always exits 0. Any `exit:` line above is the "
            "value that CARD would have returned, not this process's exit code.",
            out,
        )


# ---- apply: delegated writers only (T6) -----------------------------------------------------------

class ApplyRoundTripTests(unittest.TestCase):
    def test_check_apply_check_goes_drift_to_fresh_everywhere_except_claude(self):
        root, copilot_home, codex_home, manifest = hu.build_demo_tree()
        try:
            _seed_drifted_claude_manifest(root, manifest)
            _seed_repairable_drift(root, copilot_home, codex_home)

            before = hu.run_check(root, manifest, copilot_home=copilot_home, codex_home=codex_home)
            self.assertEqual(before["exit"], 3)
            for name in ("claude", "copilot", "codex", "data"):
                self.assertTrue(before[name]["drift"], f"{name} should start drifted")

            code, out = _run_main(
                [
                    "apply",
                    "--repo-root", str(root),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                ]
            )
            self.assertEqual(code, 0)
            self.assertNotIn("Traceback", out)

            after = hu.run_check(root, manifest, copilot_home=copilot_home, codex_home=codex_home)
            self.assertFalse(after["copilot"]["drift"], "copilot should be repaired by apply")
            self.assertFalse(after["codex"]["drift"], "codex should be repaired by apply")
            self.assertFalse(after["data"]["drift"], "mirrors should be repaired by apply")
            # ...and claude must be exactly as drifted as it was: apply prints, it never fixes.
            self.assertTrue(after["claude"]["drift"])
            self.assertEqual(after["claude"]["status"], "DRIFTED")
            self.assertEqual(after["exit"], 3)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_apply_prints_the_claude_remedy_with_the_restart_note(self):
        root, copilot_home, codex_home, manifest = hu.build_demo_tree()
        try:
            _seed_drifted_claude_manifest(root, manifest)
            check_result = hu.run_check(root, manifest, copilot_home=copilot_home, codex_home=codex_home)
            check_remedy = check_result["claude"]["detail"]["remedy"]

            code, out = _run_main(
                [
                    "apply",
                    "--repo-root", str(root),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                    "--only", "claude",
                ]
            )
            self.assertEqual(code, 0)
            # The SAME remedy string check prints -- not a second, re-worded copy.
            self.assertIn(check_remedy, out)
            self.assertIn("(restart to apply)", out)
            self.assertIn("remedy-printed", out)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_the_remedy_is_framed_conditionally_because_apply_determines_nothing(self):
        # apply reads no installed manifest, so printing the remedy must not read as an assertion
        # that the install IS stale. Proven against a fixture whose claude section is "not
        # installed": apply prints the same conditional framing regardless.
        root, copilot_home, codex_home, manifest = hu.build_demo_tree()
        try:
            self.assertFalse(manifest.exists())
            check_result = hu.run_check(root, manifest, copilot_home=copilot_home, codex_home=codex_home)
            self.assertEqual(check_result["claude"]["status"], "not installed")

            code, out = _run_main(
                [
                    "apply",
                    "--repo-root", str(root),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                    "--only", "claude",
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn(
                "apply makes no freshness determination -- if `check` reported claude drift, "
                "refresh with:",
                out,
            )
            result = hu.run_apply(root, only=["claude"])
            self.assertEqual(result["results"]["claude"]["framing"], hu._CLAUDE_CONDITIONAL_FRAMING)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class ApplyJsonEnvelopeTests(unittest.TestCase):
    def test_json_shape_and_claude_action_is_remedy_printed(self):
        root, copilot_home, codex_home, manifest = hu.build_demo_tree()
        try:
            code, out = _run_main(
                [
                    "apply",
                    "--repo-root", str(root),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                    "--json",
                ]
            )
            self.assertEqual(code, 0)
            parsed = json.loads(out)
            self.assertEqual(
                set(parsed.keys()), {"dry_run", "targets", "results", "errors", "status", "exit"}
            )
            self.assertEqual(parsed["targets"], ["claude", "copilot", "codex", "mirrors"])
            self.assertEqual(parsed["status"], "ok")
            self.assertEqual(parsed["exit"], 0)
            self.assertEqual(parsed["errors"], [])
            self.assertEqual(parsed["results"]["claude"]["action"], "remedy-printed")
            self.assertFalse(parsed["results"]["claude"]["wrote"])
            self.assertEqual(parsed["results"]["copilot"]["action"], "installed")
            self.assertEqual(parsed["results"]["codex"]["action"], "installed")
            self.assertEqual(parsed["results"]["mirrors"]["action"], "rewritten")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_only_flag_is_repeatable_and_normalized_to_canonical_order(self):
        self.assertEqual(hu.resolve_apply_targets(None), ["claude", "copilot", "codex", "mirrors"])
        self.assertEqual(hu.resolve_apply_targets(["mirrors", "claude"]), ["claude", "mirrors"])
        self.assertEqual(hu.resolve_apply_targets(["codex", "codex"]), ["codex"])


class ApplyCodexPromptsOverwriteTests(unittest.TestCase):
    """`install_codex`'s prompts loop is an UNCONDITIONAL overwrite (harness_select.py's prompt
    loop appends every source as `(dest, "install")` and calls `write_text` with no comparison).
    PLAN.md D3(b) as corrected at the P2 review keeps that write behavior -- prompts are
    plugin-generated deprecated mirrors -- but requires every real overwrite to be named."""

    def test_differing_prompt_is_rewritten_and_listed_in_human_and_json_output(self):
        root, copilot_home, codex_home, manifest = hu.build_demo_tree()
        try:
            target = sorted((codex_home / "prompts").glob("*.md"))[0]
            source = root / "codex" / "prompts" / target.name
            expected = source.read_text().replace(hs.PLACEHOLDER, str(root))
            target.write_text("# my hand-edited prompt, materially different\n")
            self.assertNotEqual(target.read_text(), expected)

            code, out = _run_main(
                [
                    "apply",
                    "--repo-root", str(root),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                    "--only", "codex",
                    "--json",
                ]
            )
            self.assertEqual(code, 0)
            parsed = json.loads(out)
            entry = parsed["results"]["codex"]
            self.assertEqual(entry["prompts_overwritten"], [str(target)])
            # The overwrite genuinely happened -- this is reporting the truth, not preventing it.
            self.assertEqual(target.read_text(), expected)

            _code, human = _run_main(
                [
                    "apply",
                    "--repo-root", str(root),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                    "--only", "codex",
                ]
            )
            # Second run: the destination now matches, so nothing is listed as overwritten.
            self.assertIn("prompts differing before this run: 0", human)
            self.assertIn("prompts overwrite in place", human)

            target.write_text("# edited again\n")
            _code, human = _run_main(
                [
                    "apply",
                    "--repo-root", str(root),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                    "--only", "codex",
                ]
            )
            self.assertIn("prompts differing before this run: 1", human)
            self.assertIn(str(target), human)
            self.assertIn(
                "rewritten -- differing generated mirror replaced (prompts are plugin-owned)", human
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_dry_run_lists_the_would_be_overwrite_without_performing_it(self):
        root, copilot_home, codex_home, manifest = hu.build_demo_tree()
        try:
            target = sorted((codex_home / "prompts").glob("*.md"))[0]
            user_text = "# my hand-edited prompt, materially different\n"
            target.write_text(user_text)

            code, out = _run_main(
                [
                    "apply",
                    "--repo-root", str(root),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                    "--only", "codex",
                    "--dry-run",
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn(str(target), out)
            self.assertIn(
                "would be rewritten -- differing generated mirror replaced "
                "(prompts are plugin-owned)",
                out,
            )
            self.assertEqual(target.read_text(), user_text)  # dry-run wrote nothing

            result = hu.run_apply(
                root, copilot_home=copilot_home, codex_home=codex_home, only=["codex"], dry_run=True
            )
            self.assertEqual(result["results"]["codex"]["prompts_overwritten"], [str(target)])
            self.assertEqual(target.read_text(), user_text)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_the_word_preserved_never_appears_when_nothing_was_preserved(self):
        root, copilot_home, codex_home, manifest = hu.build_demo_tree()
        try:
            # A differing PROMPT is not preservation -- it is an overwrite. Seeding one here makes
            # the assertion below meaningful rather than vacuous.
            sorted((codex_home / "prompts").glob("*.md"))[0].write_text("# differing prompt\n")

            code, out = _run_main(
                [
                    "apply",
                    "--repo-root", str(root),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                ]
            )
            self.assertEqual(code, 0)
            self.assertNotIn("preserved", out.lower())

            result = hu.run_apply(root, copilot_home=copilot_home, codex_home=codex_home)
            entry = result["results"]["codex"]
            self.assertEqual(entry["skip_differs"], [])
            self.assertIsNone(entry.get("preserved_note"))
        finally:
            shutil.rmtree(root, ignore_errors=True)


class ApplyCodexCoverageLimitTests(unittest.TestCase):
    def test_project_scope_agent_drift_is_named_as_out_of_reach_and_survives_apply(self):
        root, copilot_home, codex_home, manifest = hu.build_demo_tree()
        try:
            # build_demo_tree installs the canonical agents at PROJECT scope
            # (<repo>/.codex/agents/*.toml, per plan_codex_setup's agent_scope="project"). The
            # legacy install_codex apply delegates to never writes them.
            project_agents = sorted((root / ".codex" / "agents").glob("*.toml"))
            self.assertTrue(project_agents, "fixture should carry project-scope agent TOMLs")
            project_agents[0].unlink()

            before = hu.run_check(root, manifest, copilot_home=copilot_home, codex_home=codex_home)
            self.assertTrue(before["codex"]["drift"])

            code, out = _run_main(
                [
                    "apply",
                    "--repo-root", str(root),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("coverage limit", out)
            self.assertIn("OUTSIDE apply's reach", out)
            self.assertIn("python3 bin/harness_select.py install --harness codex", out)
            self.assertIn("(printed, never executed)", out)
            # The verdict must not claim bare completion over drift apply cannot touch.
            self.assertNotIn("verdict: apply complete\n", out)
            self.assertIn(
                "verdict: apply complete -- rerun check; drift outside apply's writers "
                "(claude remedy, codex modern components, docs labels) is reported there",
                out,
            )

            # ...and the drift is genuinely still there: apply reported honestly, not optimistically.
            after = hu.run_check(root, manifest, copilot_home=copilot_home, codex_home=codex_home)
            self.assertTrue(after["codex"]["drift"])
            self.assertGreaterEqual(after["codex"]["counts"].get("install", 0), 1)
            self.assertFalse(project_agents[0].exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_coverage_fields_are_machine_readable(self):
        root, copilot_home, codex_home, manifest = hu.build_demo_tree()
        try:
            result = hu.run_apply(root, copilot_home=copilot_home, codex_home=codex_home, only=["codex"])
            entry = result["results"]["codex"]
            self.assertEqual(entry["covers"], ["prompts", "AGENTS.md", "skills/<name>/"])
            self.assertEqual(
                entry["not_covered"],
                ["agents (project-scope <repo>/.codex/agents/*.toml)", "plugin (modern component)"],
            )
            self.assertIn("harness_select.py install --harness codex", entry["coverage_limit"])
        finally:
            shutil.rmtree(root, ignore_errors=True)


class ApplyCodexNoClobberTests(unittest.TestCase):
    def test_skip_differs_destination_is_preserved_byte_for_byte_and_listed(self):
        root, copilot_home, codex_home, manifest = hu.build_demo_tree()
        try:
            user_file = codex_home / "AGENTS.md"
            user_text = "# my own global Codex instructions\nDo not clobber me.\n"
            user_file.write_text(user_text)
            before_bytes = user_file.read_bytes()

            code, out = _run_main(
                [
                    "apply",
                    "--repo-root", str(root),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                    "--only", "codex",
                ]
            )
            self.assertEqual(code, 0)
            self.assertEqual(user_file.read_bytes(), before_bytes)
            self.assertEqual(user_file.read_text(), user_text)

            self.assertIn(str(user_file), out)
            self.assertIn(
                "preserved -- user file differs; resolve via harness_select install "
                "--harness codex if intended",
                out,
            )

            result = hu.run_apply(root, copilot_home=copilot_home, codex_home=codex_home, only=["codex"])
            entry = result["results"]["codex"]
            self.assertEqual(entry["counts"].get("skip-differs"), 1)
            self.assertEqual(entry["skip_differs"], [str(user_file)])
            # The "preserved" claim is emitted precisely because something was preserved.
            self.assertEqual(entry["preserved_note"], hu._CODEX_SKIP_DIFFERS_NOTE)
            self.assertEqual(user_file.read_bytes(), before_bytes)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class ApplyDryRunTests(unittest.TestCase):
    def test_dry_run_writes_nothing_anywhere(self):
        root, copilot_home, codex_home, manifest = hu.build_demo_tree()
        try:
            _seed_drifted_claude_manifest(root, manifest)
            _seed_repairable_drift(root, copilot_home, codex_home)

            before_root = _tree_digest(root)
            before_copilot = _tree_digest(copilot_home)
            before_codex = _tree_digest(codex_home)

            code, out = _run_main(
                [
                    "apply",
                    "--repo-root", str(root),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                    "--dry-run",
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("nothing was written", out)
            self.assertIn("would-install", out)

            self.assertEqual(_tree_digest(root), before_root)
            self.assertEqual(_tree_digest(copilot_home), before_copilot)
            self.assertEqual(_tree_digest(codex_home), before_codex)

            # ...and the drift is genuinely still there afterwards.
            still = hu.run_check(root, manifest, copilot_home=copilot_home, codex_home=codex_home)
            self.assertEqual(still["exit"], 3)
            self.assertTrue(still["copilot"]["drift"])
            self.assertTrue(still["codex"]["drift"])
            self.assertTrue(still["data"]["drift"])
        finally:
            shutil.rmtree(root, ignore_errors=True)


class ApplyOnlyMirrorsTests(unittest.TestCase):
    def test_only_mirrors_touches_neither_home(self):
        root, copilot_home, codex_home, manifest = hu.build_demo_tree()
        try:
            _seed_repairable_drift(root, copilot_home, codex_home)
            before_copilot = _tree_digest(copilot_home)
            before_codex = _tree_digest(codex_home)

            code, out = _run_main(
                [
                    "apply",
                    "--repo-root", str(root),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                    "--only", "mirrors",
                ]
            )
            self.assertEqual(code, 0)
            self.assertEqual(_tree_digest(copilot_home), before_copilot)
            self.assertEqual(_tree_digest(codex_home), before_codex)
            self.assertNotIn("## copilot", out)
            self.assertNotIn("## codex", out)

            after = hu.run_check(root, manifest, copilot_home=copilot_home, codex_home=codex_home)
            self.assertFalse(after["data"]["drift"])  # mirrors repaired
            self.assertTrue(after["copilot"]["drift"])  # home deliberately left alone
            self.assertTrue(after["codex"]["drift"])
        finally:
            shutil.rmtree(root, ignore_errors=True)


class ApplyClaudeCanaryTests(unittest.TestCase):
    def test_apply_never_creates_or_changes_anything_under_a_dot_claude_path(self):
        root, copilot_home, codex_home, manifest = hu.build_demo_tree()
        try:
            _seed_drifted_claude_manifest(root, manifest)
            _seed_repairable_drift(root, copilot_home, codex_home)

            canaries = []
            for base in (root, copilot_home, codex_home):
                canary = base / ".claude" / "plugins" / "installed_plugins.json"
                canary.parent.mkdir(parents=True, exist_ok=True)
                canary.write_text('{"canary": "do not touch"}\n')
                canaries.append(canary)

            before_digests = [_tree_digest(c.parent.parent) for c in canaries]
            before_named = [_claude_named_paths(b) for b in (root, copilot_home, codex_home)]

            code, _out = _run_main(
                [
                    "apply",
                    "--repo-root", str(root),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                ]
            )
            self.assertEqual(code, 0)

            self.assertEqual([_tree_digest(c.parent.parent) for c in canaries], before_digests)
            self.assertEqual(
                [_claude_named_paths(b) for b in (root, copilot_home, codex_home)], before_named
            )
            for canary in canaries:
                self.assertEqual(canary.read_text(), '{"canary": "do not touch"}\n')
        finally:
            shutil.rmtree(root, ignore_errors=True)


class ApplyCopilotSymlinkCouplingTests(unittest.TestCase):
    """Binds the T2 comparator to `install_copilot`'s ACTUAL substitution semantics.

    `_bundle_resolved_bytes` deliberately forks one line of `install_copilot`: it substitutes the
    UNRESOLVED `str(repo_root)` (what install_copilot does) rather than the resolved form
    `harness_select._resolved_bytes` uses. A symlinked repo root is the only fixture shape where
    those two forms differ on every platform, so this test makes the fork observable: if
    install_copilot ever starts resolving its repo root (or the comparator stops matching it),
    the comparator reports `differs` here and this test fails everywhere, not just on macOS."""

    def test_install_through_apply_and_the_comparator_agree_via_a_symlinked_repo_root(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            real = base / "realrepo"
            real.mkdir()
            _add_fake_skill(_make_fake_copilot_bundle(real))
            link = base / "linkrepo"
            os.symlink(real, link, target_is_directory=True)
            # The fixture is only meaningful if the two path forms actually differ.
            self.assertNotEqual(str(link), str(Path(link).resolve()))

            copilot_home = base / "copilot-home"
            copilot_home.mkdir()

            code, _out = _run_main(
                [
                    "apply",
                    "--repo-root", str(link),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(base / _UNUSED_HOME_NAME),
                    "--only", "copilot",
                ]
            )
            self.assertEqual(code, 0)

            section = hu.build_copilot_section(link, copilot_home)
            self.assertFalse(section["drift"])
            self.assertEqual(section["counts"], {"up-to-date": 2, "missing": 0, "differs": 0})

            installed = (copilot_home / "agents" / "route.agent.md").read_text()
            self.assertIn(str(link), installed)
            self.assertNotIn(hs.PLACEHOLDER, installed)


class ApplyNotInstalledHomesTests(unittest.TestCase):
    def test_absent_homes_are_not_installed_and_are_never_created(self):
        root, copilot_home, codex_home, manifest = hu.build_demo_tree()
        try:
            absent_copilot = root / "no-copilot-home"
            absent_codex = root / "no-codex-home"

            result = hu.run_apply(
                root,
                copilot_home=absent_copilot,
                codex_home=absent_codex,
                only=["copilot", "codex"],
            )
            self.assertEqual(result["exit"], 0)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["results"]["copilot"]["action"], "not installed")
            self.assertEqual(result["results"]["codex"]["action"], "not installed")
            self.assertFalse(result["results"]["copilot"]["wrote"])
            self.assertFalse(result["results"]["codex"]["wrote"])
            self.assertFalse(absent_copilot.exists())
            self.assertFalse(absent_codex.exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)


class ApplyWriterErrorTests(unittest.TestCase):
    def test_writer_error_is_surfaced_and_exits_1(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base)  # no copilot/.github/agents bundle at all
            copilot_home = base / "copilot-home"
            copilot_home.mkdir()

            code, out = _run_main(
                [
                    "apply",
                    "--repo-root", str(repo),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(base / _UNUSED_HOME_NAME),
                    "--only", "copilot",
                ]
            )
            self.assertEqual(code, 1)
            self.assertIn("FileNotFoundError", out)
            self.assertIn("copilot/.github/agents", out)
            self.assertIn("verdict: errors", out)


class ApplyNeverNamesTheClaudeHomeTests(unittest.TestCase):
    def test_apply_code_and_notes_contain_no_dot_claude_literal_at_all(self):
        # Stronger than the acceptance criterion (which permits `.claude` inside remedy/reporting
        # strings): apply's code does not contain the substring anywhere, so a grep for a write
        # path under it has nothing to adjudicate. The remedy itself is built at run time by
        # plugin_staleness and names no directory.
        apply_functions = [
            obj
            for name, obj in vars(hu).items()
            if inspect.isfunction(obj) and obj.__module__ == hu.__name__ and "apply" in name
        ]
        self.assertGreaterEqual(len(apply_functions), 12, [fn.__name__ for fn in apply_functions])
        source = "\n".join(inspect.getsource(fn) for fn in apply_functions)
        self.assertNotIn(".claude", source)
        self.assertIn("remedy-printed", source)

        notes = "".join(
            [
                hu._CLAUDE_CONDITIONAL_FRAMING,
                hu._CLAUDE_PRINT_ONLY_NOTE,
                hu._COPILOT_OVERWRITE_NOTE,
                hu._CODEX_PROMPTS_OVERWRITE_NOTE,
                hu._CODEX_PROMPT_OVERWRITE_LABEL,
                hu._CODEX_PROMPT_OVERWRITE_LABEL_DRY,
                hu._CODEX_NO_CLOBBER_NOTE,
                hu._CODEX_SKIP_DIFFERS_NOTE,
                hu._CODEX_COVERAGE_NOTE,
                hu._NOT_INSTALLED_NOTE,
                hu._APPLY_RESIDUAL_DRIFT_CAVEAT,
            ]
        )
        self.assertNotIn(".claude", notes)

    def test_apply_defines_no_file_write_call_of_its_own(self):
        # PLAN.md D3/D4: every byte apply causes to be written is written by a reused module's
        # writer. Nothing in apply's own code opens a file for writing, makes a directory, or
        # deletes anything. Asserted over parsed CALL nodes, not raw text -- apply's docstrings
        # legitimately quote `install_codex`'s own `write_text` to explain why its prompts channel
        # overwrites, and describing a delegated writer is not performing a write.
        forbidden = {
            "write_text", "write_bytes", "mkdir", "makedirs", "unlink", "remove", "rmtree",
            "open", "rename", "touch", "copy", "copyfile", "copytree",
        }
        apply_functions = [
            obj
            for name, obj in vars(hu).items()
            if inspect.isfunction(obj) and obj.__module__ == hu.__name__ and "apply" in name
        ]
        called = set()
        for fn in apply_functions:
            for node in ast.walk(ast.parse(inspect.getsource(fn))):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Attribute):
                    called.add(func.attr)
                elif isinstance(func, ast.Name):
                    called.add(func.id)
        self.assertTrue(called, "expected to parse at least one call out of apply's code")
        self.assertEqual(called & forbidden, set(), f"apply must not call these itself: {called & forbidden}")

    def test_the_prompt_pre_scan_reuses_the_single_placeholder_substitution_helper(self):
        # One substitution implementation serves both the T2 copilot comparator and T6's prompts
        # pre-scan, because install_copilot and install_codex share the identical mechanism.
        # Again asserted over parsed CALL nodes: the docstring quotes install_codex's own
        # `text.replace(...)` line to explain which mechanism is being mirrored.
        called = set()
        for node in ast.walk(ast.parse(inspect.getsource(hu._codex_prompt_overwrites))):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute):
                    called.add(func.attr)
                elif isinstance(func, ast.Name):
                    called.add(func.id)
        self.assertIn("_bundle_resolved_bytes", called)
        self.assertNotIn("replace", called, "the pre-scan must not re-implement the substitution")


# ---- read-only proof ----------------------------------------------------------------------------

class ReadOnlyTests(unittest.TestCase):
    def test_fixture_tree_byte_identical_before_and_after_check(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, _dates = _build_fresh_data_fixture(base)  # already carries .claude-plugin identity
            _write(repo / "CLAUDE.md", "# fixture guardrails\n")
            _write(repo / "bin" / "tool.py", "print('tool')\n")
            _add_fake_skill(_make_fake_copilot_bundle(repo))
            sha = "a" * 40
            _add_git_ref_head(repo, sha)
            install = _make_install(base)
            # plugin_staleness's COMPARE_GLOBS includes "data/pricing*.json" -- the fresh data
            # fixture above put pricing files under repo/data/, so the paired install dir needs
            # byte-identical copies too, or the claude section reports DRIFTED (missing files)
            # rather than IN SYNC.
            for rel in _dates:
                src, dst = repo / rel, install / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())
            entry = {"installPath": str(install), "version": "1.0.0", "gitCommitSha": sha}
            manifest = _write_manifest(base, "fake-plugin@fake-market", entry)

            copilot_home = base / "copilot-home"
            hs.install_copilot(copilot_home, repo_root=repo)
            codex_home = base / "codex-home"
            _apply_full_codex_install(hs, repo, codex_home)

            before_repo = _tree_digest(repo)
            before_copilot = _tree_digest(copilot_home)
            before_codex = _tree_digest(codex_home)

            code, _ = _run_main(
                [
                    "check",
                    "--repo-root", str(repo),
                    "--installed-manifest", str(manifest),
                    "--copilot-home", str(copilot_home),
                    "--codex-home", str(codex_home),
                    "--json",
                ]
            )
            self.assertEqual(code, 0)

            after_repo = _tree_digest(repo)
            after_copilot = _tree_digest(copilot_home)
            after_codex = _tree_digest(codex_home)
            self.assertEqual(before_repo, after_repo)
            self.assertEqual(before_copilot, after_copilot)
            self.assertEqual(before_codex, after_codex)


# ---- source-introspection guard over the pure layer ----------------------------------------------

class SourceHygieneTests(unittest.TestCase):
    def test_pure_layer_never_resolves_home_shells_out_or_hits_network(self):
        # "Pure layer" = every function in the module except the DEFAULT_* constants and any
        # cmd_* handler -- those two places are the only sanctioned homes for a real-home
        # resolution per the kit's guardrails.
        pure_functions = [
            obj
            for name, obj in vars(hu).items()
            if inspect.isfunction(obj) and obj.__module__ == hu.__name__ and not name.startswith("cmd_")
        ]
        self.assertTrue(pure_functions, "expected at least one pure function to introspect")
        source = "\n".join(inspect.getsource(fn) for fn in pure_functions)
        self.assertNotIn("Path.home", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("urlopen", source)

    def test_module_docstring_states_the_read_only_contract(self):
        doc = hu.__doc__ or ""
        self.assertIn("read-only", doc.lower())
        self.assertIn("~/.claude", doc)


# ---- live-tree gate: permanent regression guard for the T4 drift (PLAN.md D7) --------------------

class LiveTreeFreshnessTests(unittest.TestCase):
    """Drift tripwire (precedent: tests/test_pricing_refs.py's LiveTreeMirrorTests): fails if a
    pricing file's `cached_date` is bumped without updating its partner doc's snapshot label.
    Reads the REAL repo tree only -- never writes, never uses a fixture."""

    def test_pricing_json_label_appears_in_readme(self):
        cached_date = json.loads((REPO_ROOT / "data" / "pricing.json").read_text())["cached_date"]
        readme = (REPO_ROOT / "README.md").read_text()
        self.assertIn(cached_date, readme)

    def test_pricing_copilot_json_label_appears_in_copilot_harness_doc(self):
        cached_date = json.loads((REPO_ROOT / "data" / "pricing.copilot.json").read_text())["cached_date"]
        doc = (REPO_ROOT / "docs" / "COPILOT-HARNESS.md").read_text()
        self.assertIn(cached_date, doc)

    def test_same_assertion_shape_fails_on_a_synthetic_stale_tree(self):
        # Proves the assertion above is not vacuously true: run the identical shape against a
        # synthetic tree where the doc deliberately does not carry the cached_date, and confirm
        # it actually fails.
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _write(repo / "data" / "pricing.json", json.dumps({"cached_date": "2020-01-01"}))
            _write(repo / "README.md", "no date in here at all\n")
            cached_date = json.loads((repo / "data" / "pricing.json").read_text())["cached_date"]
            readme = (repo / "README.md").read_text()
            with self.assertRaises(AssertionError):
                self.assertIn(cached_date, readme)


if __name__ == "__main__":
    unittest.main()
