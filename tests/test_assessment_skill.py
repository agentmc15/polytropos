"""Packaging guards for the `assess-improvement` skill card (kit task D25).

WHAT THIS FILE IS ABOUT. D25 stages one authored skill —
`tasks/kits/decision-improvement/skills/assess-improvement/` — into the native skill paths of
the harnesses that can actually carry it, and nowhere else. Everything asserted here is
structural: which entry points exist, which roster says they exist, which bytes an install
puts where, and that the card names no command to run. Nothing here tests whether a model
follows the card's prose; D26 owns the fixture-level behaviour and this file deliberately
makes no claim about it.

SAFETY CONTRACT. No test here runs `claude`, `codex`, `copilot`, Cursor's `agent`, `graphify`,
`gh`, or any other binary, and none reads or writes a home directory. The one installer
exercised (`bin/harness_select.py install --harness cursor`) is given a temporary project root
every time, and one test asserts by exact file-set equality that the run wrote nothing outside
it.

HOW THE ASSERTIONS ARE BUILT. Two rules, because this kit has shipped structural tests that
could not fail:

1. A roster claim is a claim that two INDEPENDENTLY DERIVED sets are equal. Each harness's
   membership is read at call time from that harness's own authority — `copilot/aesop.toml`'s
   `primitives.skills`, `bin/cursor_adapter.py`'s `BUNDLE`, the committed generated pages plus
   `mkdocs.yml`'s nav plus `.claude/kits/docs-site/AUDIT.md` for Claude — and compared to what
   is on disk. Where a harness has no independent roster (Codex discovers its skills from the
   directory the plugin manifest points at), that is said out loud rather than dressed up as
   agreement.
2. Presence is never asserted where a value can be. A no-clobber test that only proved
   "nothing was overwritten" would pass on an installer that did nothing at all, so the
   positive control below asserts the exact bytes an unowned destination receives.
"""

import contextlib
import hashlib
import importlib.util
import inspect
import io
import json
import os
import pathlib
import re
import socket
import subprocess
import tempfile
import tomllib
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = REPO_ROOT / "bin"

#: The card, by its one name. The brief pins this spelling in every native path.
SKILL_NAME = "assess-improvement"

#: The authored source D25 stages from. Still tracked, still the origin of the bytes.
PROTOTYPE_DIR = (REPO_ROOT / "tasks" / "kits" / "decision-improvement" / "skills"
                 / SKILL_NAME)

#: Every native skill root this repo ships, by harness key.
HARNESS_SKILL_ROOTS = {
    "claude": ("skills",),
    "copilot": ("copilot", ".github", "skills"),
    "codex": ("codex", "skills"),
    "cursor": ("cursor", "skills"),
}

#: Where D25 stages the card. Claude because `skills/` IS the plugin, Cursor because the
#: acceptance requires the Cursor install to carry it. The other two are named in the brief as
#: paths D25 MAY touch, and are deliberately left alone — see
#: `test_the_two_unstaged_harness_rosters_are_untouched_and_say_so`.
STAGED_ON = frozenset({"claude", "cursor"})

#: The project-relative destinations a Cursor install must produce for this card. A literal,
#: because the installed path IS the acceptance term — deriving it from BUNDLE would only
#: restate whatever BUNDLE happens to say.
CURSOR_CARD_DESTINATIONS = frozenset({
    ".cursor/skills/assess-improvement/SKILL.md",
    ".cursor/skills/assess-improvement/references/assessment-template.md",
})

#: The generated site page for the Claude card, and the nav path mkdocs uses for it.
SITE_PAGE = f"docs-site/skills/claude/{SKILL_NAME}.md"
NAV_PATH = f"skills/claude/{SKILL_NAME}.md"

#: Command shapes a staged file may not contain. "No borrowed CLI commands" is an acceptance
#: term: this card documents no verb, its own or anyone else's, and invokes nothing.
BORROWED_COMMAND_PATTERNS = (
    r"\bclaude\s+-{1,2}\w",
    r"\bcodex\s+(?:exec|-{1,2}\w)",
    r"\bcopilot\s+-{1,2}\w",
    r"\bagent\s+-{1,2}\w",
    r"\bgraphify\b",
    r"\bgh\b",
    r"\bnpm\b",
    r"\bpip\b",
    r"\buv\s+tool\b",
    r"\bpython3?\s+\S+\.py",
    r"bin/[A-Za-z0-9_]+\.py",
    r"```",
)


def _load(name):
    """Load a `bin/` module by path — `bin/` is not an importable package."""
    spec = importlib.util.spec_from_file_location(f"{name}_assessment_skill_test",
                                                 BIN_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ca = _load("cursor_adapter")
hs = _load("harness_select")
db = _load("docs_build")


def _skill_dir(harness):
    return REPO_ROOT.joinpath(*HARNESS_SKILL_ROOTS[harness], SKILL_NAME)


def _frontmatter(text):
    """The YAML frontmatter block of a SKILL.md, as text."""
    parts = text.split("---")
    return parts[1]


def _field(text, key):
    m = re.search(rf"(?m)^{key}:\s*(\S.*?)\s*$", _frontmatter(text))
    return m.group(1) if m else None


def _sha(data):
    return hashlib.sha256(data).hexdigest()


# ---- roster authorities, each read from the other side's own source of truth ---------------


def _claude_roster():
    """Claude skill names as the PUBLISHED surface reports them: the committed generated
    pages under `docs-site/skills/claude/`. Generated by `bin/docs_build.py` from the skills
    tree, so it is a different artifact from the tree itself — a skill dir with no rebuilt
    page is absent here."""
    page_dir = REPO_ROOT / "docs-site" / "skills" / "claude"
    return {p.stem for p in page_dir.glob("*.md") if p.stem != "index"}


def _copilot_roster():
    """Copilot skill names as `copilot/aesop.toml` declares them — the manifest that stands in
    for `aesop compile` in this repo."""
    with (REPO_ROOT / "copilot" / "aesop.toml").open("rb") as fh:
        return set(tomllib.load(fh)["primitives"]["skills"])


def _codex_roster():
    """Codex skill names as the Codex plugin manifest resolves them.

    Honest limitation, stated rather than hidden: `.codex-plugin/plugin.json` carries a
    DIRECTORY (`"skills": "./codex/skills/"`), not a list, so this "roster" is the directory
    listing and cannot disagree with the tree. The Codex roster that CAN disagree is the
    literal `EXPECTED_SKILL_STEMS` in tests/test_codex_bundle.py, which is why adding a Codex
    card is not a manifest edit but a test edit — and why D25 does not add one.
    """
    manifest = json.loads((REPO_ROOT / ".codex-plugin" / "plugin.json").read_text("utf-8"))
    skills_dir = (REPO_ROOT / manifest["skills"]).resolve()
    return {p.name for p in skills_dir.iterdir() if p.is_dir()}


def _cursor_roster():
    """Cursor skill names as `bin/cursor_adapter.py`'s BUNDLE ships them — the only thing that
    decides what an install puts in a project."""
    names = set()
    for _src, dest in ca.BUNDLE:
        parts = Path(dest).parts
        if len(parts) >= 3 and parts[0] == ".cursor" and parts[1] == "skills":
            names.add(parts[2])
    return names


ROSTER_AUTHORITIES = {
    "claude": _claude_roster,
    "copilot": _copilot_roster,
    "codex": _codex_roster,
    "cursor": _cursor_roster,
}


class SkillPackagingTests(unittest.TestCase):

    # ---- entry points and roster agreement -------------------------------------------------

    def test_the_card_is_on_disk_for_exactly_the_harnesses_whose_roster_lists_it(self):
        """The acceptance's "rosters/manifests agree", as an equality between two sets neither
        of which is written in this file: where the card's SKILL.md exists, and where each
        harness's own roster authority names it."""
        on_disk = {h for h in HARNESS_SKILL_ROOTS
                   if (_skill_dir(h) / "SKILL.md").is_file()}
        rostered = {h for h, authority in ROSTER_AUTHORITIES.items()
                    if SKILL_NAME in authority()}

        self.assertEqual(on_disk, rostered,
                         "a harness carries the card on disk without its roster naming it, "
                         "or names it without carrying it")
        self.assertEqual(on_disk, set(STAGED_ON))
        self.assertEqual(set(HARNESS_SKILL_ROOTS) - on_disk, {"copilot", "codex"})

    def test_the_two_unstaged_harness_rosters_are_untouched_and_say_so(self):
        """Copilot and Codex are named in the brief as paths D25 may touch. They are not
        touched, and the evidence is their own rosters: neither names the card. Both rosters
        are also internally consistent, which is what the bundle suites in the verify command
        are standing guard over."""
        copilot = _copilot_roster()
        codex = _codex_roster()
        self.assertNotIn(SKILL_NAME, copilot)
        self.assertNotIn(SKILL_NAME, codex)

        copilot_dirs = {p.name for p
                        in (REPO_ROOT / "copilot" / ".github" / "skills").iterdir()
                        if p.is_dir()}
        self.assertEqual(copilot, copilot_dirs,
                         "copilot/aesop.toml's primitives.skills and the .github/skills tree "
                         "must be the same set")
        for name in sorted(codex):
            with self.subTest(codex_skill=name):
                self.assertTrue((REPO_ROOT / "codex" / "skills" / name / "SKILL.md").is_file())

    def test_the_cursor_bundle_and_the_cursor_tree_are_the_same_file_set(self):
        """BUNDLE -> file is already guarded in tests/test_cursor_adapter.py; file -> BUNDLE
        was not. Without this direction a `cursor/` file that no install ships — a reference
        left out of BUNDLE, say — is a dead link in every installed project and nothing
        notices."""
        tracked = {p.relative_to(REPO_ROOT / "cursor").as_posix()
                   for p in (REPO_ROOT / "cursor").rglob("*") if p.is_file()}
        bundled = {src for src, _dest in ca.BUNDLE}
        self.assertEqual(tracked, bundled,
                         "every file under cursor/ must be a BUNDLE source and vice versa")

    def test_the_codex_plugin_manifest_is_valid_and_is_why_it_needed_no_edit(self):
        """"Codex plugin valid" as a value check, and the reason `.codex-plugin/plugin.json`
        is not in this change: its skills pointer is a directory, so Codex discovery grows
        with the tree and a new card is never a manifest edit."""
        manifest = json.loads((REPO_ROOT / ".codex-plugin" / "plugin.json").read_text("utf-8"))
        self.assertEqual(manifest["name"], "polytropos")
        self.assertEqual(manifest["skills"], "./codex/skills/")
        self.assertIsInstance(manifest["skills"], str)
        resolved = (REPO_ROOT / manifest["skills"]).resolve()
        self.assertEqual(resolved, (REPO_ROOT / "codex" / "skills").resolve())
        self.assertTrue(resolved.is_dir())
        for key in ("version", "description", "author", "interface"):
            with self.subTest(key=key):
                self.assertIn(key, manifest)
                self.assertTrue(manifest[key], f"{key} is present but empty")

    def test_the_claude_plugin_manifest_carries_no_skill_roster_at_all(self):
        """The reason `.claude-plugin/plugin.json` is not in this change either: the plugin
        manifest declares no skills, so `skills/` IS the roster. If a `skills` key ever
        appears there, this test fails and the card has a second place to be registered."""
        manifest = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text("utf-8"))
        self.assertEqual(set(manifest), {"name", "description", "version", "author"})
        self.assertEqual(manifest["name"], "polytropos")

    # ---- the card itself, and the reference it links --------------------------------------

    def test_every_staged_card_declares_its_own_directory_name_and_no_model_pin(self):
        for harness in sorted(STAGED_ON):
            path = _skill_dir(harness) / "SKILL.md"
            with self.subTest(harness=harness):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(_field(text, "name"), SKILL_NAME)
                description = _field(text, "description")
                self.assertTrue(description and len(description) > 40)
                self.assertNotRegex(_frontmatter(text), r"(?m)^model:")

    def test_the_linked_template_is_byte_identical_in_the_prototype_and_both_copies(self):
        """One authored reference, three locations. A divergent copy is a second authority for
        what a report must contain, which is the whole defect this test exists to prevent."""
        origin = (PROTOTYPE_DIR / "references" / "assessment-template.md").read_bytes()
        digests = {"prototype": _sha(origin)}
        for harness in sorted(STAGED_ON):
            path = _skill_dir(harness) / "references" / "assessment-template.md"
            self.assertTrue(path.is_file(), f"missing {path}")
            digests[harness] = _sha(path.read_bytes())
        self.assertEqual(set(digests.values()), {_sha(origin)}, digests)

    def test_every_shipped_reference_file_is_linked_from_its_card_and_vice_versa(self):
        """Both directions: an unlinked reference is dead weight the model never reads, and a
        link to a file that does not ship is a dangling pointer in an installed project."""
        for harness in sorted(STAGED_ON):
            skill_dir = _skill_dir(harness)
            with self.subTest(harness=harness):
                shipped = {p.relative_to(skill_dir).as_posix()
                           for p in (skill_dir / "references").rglob("*") if p.is_file()}
                text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
                linked = set(re.findall(r"\]\((references/[^)\s]+)\)", text))
                self.assertEqual(shipped, {"references/assessment-template.md"})
                self.assertEqual(linked, shipped)

    def test_the_no_fit_vocabulary_survived_the_move_intact(self):
        """The brief requires the prototype's no-fit behaviour to be retained. That behaviour
        is a closed vocabulary in two places: the card's five evidence statuses and the
        template's permitted assessments. Assert both as exact sets — a card that can only
        say "candidate" has lost the ability to conclude against itself."""
        card = (_skill_dir("claude") / "SKILL.md").read_text(encoding="utf-8")
        for token in ("`no-fit`", "`insufficient-evidence`", "`unknown`", "`unverified`",
                      "`observed`", "`documented`", "`inferred`"):
            with self.subTest(token=token):
                self.assertIn(token, card)

        template = (_skill_dir("claude") / "references" / "assessment-template.md").read_text(
            encoding="utf-8")
        m = re.search(r"(?m)^Permitted assessments:\s*(.+)$", template)
        self.assertIsNotNone(m, "the template must state its permitted assessments")
        permitted = set(re.findall(r"`([a-z-]+)`", m.group(1)))
        self.assertEqual(permitted, {"candidate", "defer", "not-applicable", "unknown",
                                     "insufficient-evidence"})

    def test_the_claude_card_is_the_prototype_body_verbatim(self):
        """The staged body moves byte for byte. Exactly ONE thing is rewritten on the way in,
        and it is not prose: `tests/test_skill_entrypoints.py` requires every Claude skill
        description to name a trigger ("use when" / "when the user"), and the prototype's said
        "Use for read-only improvement planning". That rule is repo reality the brief did not
        anticipate; this test pins the divergence to the description line alone so nobody later
        "restores" the prototype wording and breaks the entry-point grammar."""
        prototype = (PROTOTYPE_DIR / "SKILL.md").read_text(encoding="utf-8")
        claude = (_skill_dir("claude") / "SKILL.md").read_text(encoding="utf-8")

        body = lambda text: text.split("---", 2)[2]
        self.assertEqual(body(claude), body(prototype),
                         "the card body must be the staged prototype's, byte for byte")
        self.assertEqual(_field(claude, "name"), _field(prototype, "name"))
        self.assertNotEqual(_field(claude, "description"), _field(prototype, "description"))
        lowered = _field(claude, "description").lower()
        self.assertTrue(any(t in lowered for t in ("use when", "when the user")),
                        "the description must name a trigger, per tests/test_skill_entrypoints.py")

    def test_the_cursor_card_is_the_claude_card_plus_one_paragraph(self):
        """One authored card, two locations. Cursor's copy adds exactly one line and changes
        nothing else — same headings, same description — so the normative content has one
        author, not two."""
        claude_text = (_skill_dir("claude") / "SKILL.md").read_text(encoding="utf-8")
        cursor_text = (_skill_dir("cursor") / "SKILL.md").read_text(encoding="utf-8")
        headings = lambda text: [l for l in text.splitlines() if l.startswith("#")]
        self.assertEqual(headings(cursor_text), headings(claude_text))
        self.assertEqual(_field(cursor_text, "description"),
                         _field(claude_text, "description"))
        extra = [l for l in cursor_text.splitlines() if l and l not in claude_text.splitlines()]
        self.assertEqual(len(extra), 1, f"expected exactly one Cursor-specific line: {extra}")
        self.assertIn(".cursor/skills/assess-improvement/", extra[0])

    # ---- no borrowed CLI commands ----------------------------------------------------------

    def test_no_staged_file_names_a_command_to_run(self):
        """The card assesses; it does not dispatch. It names no harness binary, no engine in
        `bin/`, no package manager, and ships no fenced block a reader could paste."""
        offenders = []
        for harness in sorted(STAGED_ON):
            for path in sorted((_skill_dir(harness)).rglob("*")):
                if not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8")
                for pattern in BORROWED_COMMAND_PATTERNS:
                    for hit in re.findall(pattern, text):
                        offenders.append(f"{path.relative_to(REPO_ROOT)}: {pattern} -> {hit!r}")
        self.assertEqual(offenders, [], f"borrowed command shapes: {offenders}")

    def test_the_cursor_copy_respects_the_cursor_bundles_own_content_fences(self):
        """The Cursor bundle's standing fences, applied to the new files: no other harness's
        command tokens, and no dollar sign at all (`tests/test_cursor_adapter.py` enforces the
        same two on every BUNDLE source, and this card must not be the file that needs an
        exception)."""
        for rel in sorted(CURSOR_CARD_DESTINATIONS):
            src = REPO_ROOT / "cursor" / rel[len(".cursor/"):]
            with self.subTest(file=src.name):
                text = src.read_text(encoding="utf-8")
                for token in ca.OTHER_HARNESS_TOKENS:
                    self.assertNotIn(token, text)
                self.assertNotIn("$", text)

    # ---- docs regenerated -------------------------------------------------------------------

    def test_the_generated_site_page_is_committed_exactly_as_the_generator_renders_it(self):
        """"docs regenerated", asserted on bytes rather than on existence: the committed page
        must equal what `expected_pages()` renders right now."""
        pages = db.expected_pages(REPO_ROOT)
        self.assertIn(SITE_PAGE, pages)
        self.assertEqual((REPO_ROOT / SITE_PAGE).read_bytes(), pages[SITE_PAGE])

        stale, unknown = db.check_site(REPO_ROOT)
        self.assertEqual([p for p in stale if SKILL_NAME in p], [])
        self.assertEqual([p for p in unknown if SKILL_NAME in p], [])

    def test_the_parity_page_publishes_the_claude_only_roster_asymmetry(self):
        """The card ships on one of the three harnesses the site covers. The parity matrix has
        to say so in its own row — an em dash in the Copilot and Codex cells — or the site
        claims a coverage the rosters do not have."""
        parity = (REPO_ROOT / "docs-site" / "skills" / "index.md").read_text(encoding="utf-8")
        row = (f"| {SKILL_NAME} | [{SKILL_NAME}](claude/{SKILL_NAME}.md) | — | — |")
        self.assertIn(row, parity)

    def test_the_site_nav_lists_the_page_once_and_the_audit_roster_covers_the_card(self):
        nav = (REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8")
        self.assertEqual(nav.count(NAV_PATH), 1)

        audit = (REPO_ROOT / ".claude" / "kits" / "docs-site" / "AUDIT.md").read_text("utf-8")
        self.assertIn(f"### claude/{SKILL_NAME}\n", audit)

    def test_no_staged_file_points_into_the_generated_site(self):
        """CLAUDE.md: site content is human-facing, never model-loaded. A card that cited a
        docs-site page would be telling the model to read the generated mirror of itself."""
        for harness in sorted(STAGED_ON):
            for path in sorted(_skill_dir(harness).rglob("*")):
                if path.is_file():
                    with self.subTest(file=str(path.relative_to(REPO_ROOT))):
                        self.assertNotIn("docs-site", path.read_text(encoding="utf-8"))

    # ---- installation: ownership, and the positive control --------------------------------

    def test_claude_needs_no_installer_and_harness_select_writes_nothing_for_it(self):
        """Why `bin/harness_select.py` has no Claude-side change to make: the plugin at this
        repo's root IS the install, so `install --harness claude-code` writes nothing. The
        assertion is on the message's value and on an empty temp tree."""
        def snapshot():
            return {p.relative_to(REPO_ROOT).as_posix(): _sha(p.read_bytes())
                    for p in sorted((REPO_ROOT / "skills").rglob("*")) if p.is_file()}

        before = snapshot()
        self.assertIn(f"skills/{SKILL_NAME}/SKILL.md", before)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            hs.main(["install", "--harness", "claude-code"])
        self.assertEqual(out.getvalue().strip(), f"claude-code: {hs.CLAUDE_CODE_MESSAGE}")
        self.assertIn("nothing to install", hs.CLAUDE_CODE_MESSAGE)
        self.assertEqual(snapshot(), before)

    def test_harness_select_is_the_production_path_that_installs_the_cursor_card(self):
        """POSITIVE CONTROL for every no-clobber test below: an unowned destination DOES get
        the card, with the exact bytes the bundle resolves to, through the real installer
        entry point — not through the adapter's internals."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            project.mkdir()
            with contextlib.redirect_stdout(io.StringIO()):
                hs.main(["install", "--harness", "cursor", "--project", str(project)])

            sources = ca.bundle_sources()
            for rel in sorted(CURSOR_CARD_DESTINATIONS):
                dest = project / rel
                self.assertTrue(dest.is_file(), f"not installed: {rel}")
                self.assertEqual(dest.read_bytes(), sources[rel])
                self.assertNotIn(ca.PLACEHOLDER, dest.read_text(encoding="utf-8"))

            manifest = json.loads((project / ca.MANIFEST_REL).read_text(encoding="utf-8"))
            self.assertTrue(CURSOR_CARD_DESTINATIONS <= set(manifest["files"]))
            for rel in sorted(CURSOR_CARD_DESTINATIONS):
                self.assertEqual(manifest["files"][rel], _sha(sources[rel]))

    def test_the_install_writes_only_inside_the_project_root(self):
        """Exact file-set equality over the whole temp tree, plus a sibling marker the run must
        not have touched. A containment claim asserted any weaker than this is a claim about
        intent, not about what happened."""
        cursor_dir_before = (REPO_ROOT / ".cursor").exists()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "proj"
            project.mkdir()
            sibling = root / "elsewhere"
            sibling.mkdir()
            (sibling / "keep.txt").write_text("untouched\n", encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                hs.main(["install", "--harness", "cursor", "--project", str(project)])

            actual = {p.relative_to(root).as_posix()
                      for p in root.rglob("*") if p.is_file()}
            expected = {f"proj/{dest}" for _src, dest in ca.BUNDLE}
            expected.add(f"proj/{ca.MANIFEST_REL}")
            expected.add("elsewhere/keep.txt")
            self.assertEqual(actual, expected)
            self.assertEqual((sibling / "keep.txt").read_text(encoding="utf-8"), "untouched\n")
        self.assertEqual((REPO_ROOT / ".cursor").exists(), cursor_dir_before,
                         "the install must not have created a .cursor/ in this checkout")

    def test_a_card_this_installer_does_not_own_is_preserved_and_the_run_writes_nothing(self):
        """No-clobber, and specifically all-or-nothing: one unowned destination refuses the
        WHOLE plan, so a project never ends up with half a bundle."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            target = project / ".cursor" / "skills" / SKILL_NAME / "SKILL.md"
            target.parent.mkdir(parents=True)
            mine = "---\nname: assess-improvement\n---\n\n# my own card\n"
            target.write_text(mine, encoding="utf-8")

            plan = ca.plan_install(project)
            states = {a["destination"]: a["state"] for a in plan["actions"]}
            self.assertEqual(states[".cursor/skills/assess-improvement/SKILL.md"], "unmanaged")
            self.assertEqual(plan["conflicts"],
                             [".cursor/skills/assess-improvement/SKILL.md"])

            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
                hs.main(["install", "--harness", "cursor", "--project", str(project)])
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("--adopt-existing", err.getvalue())

            self.assertEqual(target.read_text(encoding="utf-8"), mine)
            self.assertFalse((project / ca.MANIFEST_REL).exists())
            for _src, dest in ca.BUNDLE:
                if dest == ".cursor/skills/assess-improvement/SKILL.md":
                    continue
                self.assertFalse((project / dest).exists(),
                                 f"a refused plan still wrote {dest}")

    def test_adopting_an_unowned_card_keeps_the_bytes_it_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            rel = ".cursor/skills/assess-improvement/SKILL.md"
            target = project / rel
            target.parent.mkdir(parents=True)
            mine = "# my own card\n"
            target.write_text(mine, encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                hs.main(["install", "--harness", "cursor", "--project", str(project),
                         "--adopt-existing"])

            self.assertEqual(target.read_bytes(), ca.bundle_sources()[rel])
            backup = project / (rel + ca.BACKUP_SUFFIX)
            self.assertTrue(backup.is_file(), "adoption must keep a backup")
            self.assertEqual(backup.read_text(encoding="utf-8"), mine)

    def test_reinstalling_is_up_to_date_and_a_moved_bundle_refreshes_what_we_own(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            project.mkdir()
            ca.apply_install(ca.plan_install(project))

            again = ca.plan_install(project)
            self.assertEqual({a["state"] for a in again["actions"]}, {"up-to-date"})
            self.assertEqual(ca.apply_install(again), [])

            rel = ".cursor/skills/assess-improvement/references/assessment-template.md"
            moved = dict(ca.bundle_sources())
            moved[rel] = moved[rel] + b"\n<!-- a later revision -->\n"
            original = ca.bundle_sources
            try:
                ca.bundle_sources = lambda *a, **k: moved
                plan = ca.plan_install(project)
                states = {a["destination"]: a["state"] for a in plan["actions"]}
                self.assertEqual(states[rel], "managed-update")
                self.assertEqual(ca.apply_install(plan), [rel])
            finally:
                ca.bundle_sources = original
            self.assertEqual((project / rel).read_bytes(), moved[rel])


# ==============================================================================================
#  D26 — the assessment fixture corpus
# ==============================================================================================
#
# WHAT THIS SECTION IS ABOUT, AND WHAT IT IS NOT. `tests/fixtures/assessment-skill/` is a corpus
# of synthetic SOURCE documents (what a bounded read of some repository would have shown) paired
# with synthetic REPORT documents (what an assessment claims to have concluded from them).
# `review_assessment` below is a deterministic checker over that pairing, and every assertion in
# `AssessmentSkillFixtureTests` is a claim about THE FIXTURE AND THE CHECKER.
#
# NOT ONE ASSERTION HERE IS ABOUT A MODEL. No test runs the card, no test observes a model
# reading it, and no test name says "the skill identifies X" — because nothing here watched a
# skill identify anything. A fixture a test walks is evidence about the fixture and the test.
# What the corpus can show is that the card's and the template's own vocabularies are closed and
# machine-checkable, that a report which violates one is refusable on a bounded read, and that
# the refusal is deterministic. Whether a model follows the prose is a behavioural question that
# static fixtures cannot answer; paid behavioural evaluation is separately authorized and is not
# this task.
#
# WHERE THE RULES COME FROM. Every vocabulary the checker enforces is read at call time out of
# the shipped card and template — evidence statuses, permitted assessments, permitted
# recommendations, permitted decisions, the ranking basis, the whole-system surfaces. None of
# them is a literal written here. `SkillPackagingTests` pins those same sets to exact literals;
# this section consumes them. If the card's wording changes, these readers fail loudly rather
# than silently enforcing a stale vocabulary.
#
# WHERE THE ORACLE COMES FROM, HONESTLY. `expected-verdicts.json` is authored, like the corpus.
# An authored corpus compared to an authored oracle is circular on its own, so three things carry
# the weight instead: (1) every rule the checker applies is derived from the other side's source
# of truth, not from the oracle; (2) the corpus is built as DIFFERENTIALS — sibling cases share a
# byte-identical `sources.json` and differ only in the report, so the verdict is demonstrably
# decided by the report and not by the fixture's mood; (3) the union of every finding the corpus
# produces is pinned EQUAL to the checker's whole vocabulary, so a rule with no case, and a case
# asserting a code no rule can emit, are both failures.
#
# NO HIDDEN ANSWERS. A `sources.json` states what a reader would see; it never states the
# conclusion. `test_no_source_document_carries_the_assessment_side_vocabulary` enforces that as a
# token ban. The one source that names a held-out label set marks it `hidden-label` and says its
# contents are unreadable — quarantining a leak is the D06 precedent, and citing that row is
# exactly the defect `hidden-answer-use` names.

#: The corpus root, its case directories, and the oracle — which deliberately lives OUTSIDE every
#: case directory so no case dir contains its own answer.
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "assessment-skill"
CASES_DIR = FIXTURE_ROOT / "cases"
EXPECTED_PATH = FIXTURE_ROOT / "expected-verdicts.json"
QUALITATIVE_PATH = FIXTURE_ROOT / "QUALITATIVE-OBSERVATION.md"

#: The only two files a case directory may contain. Asserted by exact set equality, so an oracle
#: smuggled in beside the inputs is a failure rather than a convenience.
CASE_FILES = frozenset({"sources.json", "report.json"})

#: The checker's whole finding vocabulary. Pinned equal to the union of everything the corpus
#: produces, in both directions.
FINDING_CODES = frozenset({
    "assessment-not-permitted", "contradiction-fabricated", "contradiction-silently-resolved",
    "contradiction-unreported", "cross-harness-transfer", "decision-not-permitted",
    "fabricated-confidence", "forced-recommendation", "gain-claim", "hidden-answer-use",
    "malformed-json", "malformed-shape", "malformed-sources", "observed-without-observation",
    "ranking-basis-not-permitted", "recommendation-not-permitted", "recurrence-unsupported",
    "redesign-not-deferred", "scope-overreach", "silent-mutation", "status-not-permitted",
    "unknown-evidence-id", "unknown-not-carried", "unranked-candidate",
})

#: Fixture schema, as exact key sets. A missing or extra key is `malformed-shape` /
#: `malformed-sources` rather than a KeyError escaping to the caller — "malformed bounded".
SOURCE_KEYS = frozenset({"repository", "revision", "kind", "responsibilities",
                         "harness_support", "access_denied", "observations"})
OBSERVATION_KEYS = frozenset({"id", "category", "subject", "asserts", "path", "locator",
                              "provenance", "statement"})
REPORT_KEYS = frozenset({"scope", "ledger", "contradictions", "signals", "candidates",
                         "ranking", "surface_answers", "decision", "notes"})
SCOPE_KEYS = frozenset({"repository", "revision", "surfaces", "excluded",
                        "evidence_not_available"})

#: Provenance classes an observation may carry. `source`, `test` and `record` are what the card
#: calls directly supporting — the ones a status of `observed` may rest on. `document` is the
#: card's `documented`. `hidden-label` is a controller-owned held-out set: present so the corpus
#: can exhibit a citation of it, never readable.
OBSERVED_PROVENANCE = frozenset({"source", "test", "record"})
HIDDEN_PROVENANCE = "hidden-label"

#: The one resolution a reported contradiction may carry. The corpus also uses the spelling
#: `resolved-by-picking-a-side`, which exists ONLY so a fixture can exhibit the defect the brief
#: names: a contradiction resolved by choosing a side instead of surfaced.
RESOLUTION_REPORTED = "reported-unresolved"

#: Candidate kinds the card defers by default: "Broad executable policy languages and autonomous
#: self-modification are `no-fit` or deferred by default."
DEFERRED_KINDS = frozenset({"broad-executable-policy", "autonomous-self-modification"})

#: What the card requires beside a numeric confidence: "state its prediction target, provenance,
#: and validation status separately".
CONFIDENCE_META_KEYS = ("prediction_target", "provenance", "validation_status")

#: Assessment-side vocabulary a SOURCE document may not contain. These are CONCLUSIONS. The
#: evidence states `unknown` and `unverified` are deliberately NOT banned: they are things a
#: repository legitimately records about itself (a capability record whose value is the literal
#: `unknown` is the real shape this corpus models), and banning them would be an exclusion wider
#: than its reason.
ANSWER_SIDE_TOKENS = frozenset(FINDING_CODES) | frozenset({
    "candidate", "not-applicable", "insufficient-evidence", "no-fit", "defer",
    "prepare brief", "collect evidence", "manual-only", "no supported intervention",
    "evidence collection needed", "draft task brief", "requires explicit authorization",
})

we = _load("workflow_eval")

_CARD_TEXT = (_skill_dir("claude") / "SKILL.md").read_text(encoding="utf-8")
_TEMPLATE_TEXT = (_skill_dir("claude") / "references"
                  / "assessment-template.md").read_text(encoding="utf-8")


def _must(match, what):
    if match is None:
        raise AssertionError(f"the shipped card no longer states {what}; this checker enforces "
                             f"a vocabulary it can no longer read")
    return match


def _evidence_statuses():
    """The card's own five evidence statuses, read out of its "Distinguish these statuses" list.
    Six tokens, because `unknown` / `unverified` share one bullet."""
    block = _must(re.search(r"Distinguish these statuses:\n\n((?:- .*\n)+)", _CARD_TEXT),
                  "its evidence statuses")
    return frozenset(re.findall(r"`([a-z-]+)`", block.group(1)))


def _permitted_assessments():
    """The template's own `Permitted assessments:` line."""
    line = _must(re.search(r"(?m)^Permitted assessments:\s*(.+)$", _TEMPLATE_TEXT),
                 "its permitted assessments")
    return frozenset(re.findall(r"`([a-z-]+)`", line.group(1)))


def _permitted_recommendations():
    """The template's own `**Recommendation:**` line."""
    line = _must(re.search(r"(?m)^- \*\*Recommendation:\*\*\s*(.+)$", _TEMPLATE_TEXT),
                 "its permitted recommendations")
    return frozenset(re.findall(r"`([a-z][a-z -]*)`", line.group(1)))


def _permitted_decisions():
    """The template's own `State one of:` line."""
    line = _must(re.search(r"(?m)^State one of:\s*(.+?)\. Include", _TEMPLATE_TEXT),
                 "its permitted decisions")
    return frozenset(re.findall(r"`([^`]+)`", line.group(1)))


def _ranking_basis():
    """The four things the card permits a ranking to rest on, and nothing else: "rank only
    within the assessment scope using expected learning value, reversibility, evidence quality,
    and disruption"."""
    line = _must(re.search(r"rank only within the assessment scope using ([^.]+)\.", _CARD_TEXT),
                 "its ranking basis")
    return frozenset(t.strip().removeprefix("and ") for t in line.group(1).split(","))


def _surface_keys():
    """The four whole-system surfaces from the card's own table, slugified. The corpus answers
    exactly these and no others."""
    rows = re.findall(r"(?m)^\| ([A-Z][^|]+?) \| (?:Which|Is|Are)", _CARD_TEXT)
    keys = frozenset(re.sub(r"[^a-z0-9]+", "-", row.lower()).strip("-") for row in rows)
    if len(keys) != 4:
        raise AssertionError(f"the card's whole-system table no longer has four rows: {keys}")
    return keys


# ---- the checker ---------------------------------------------------------------------------


def _rows_ok(value):
    if not isinstance(value, list):
        return False
    return all(isinstance(row, dict) for row in value)


def _sources_shape_error(sources):
    if not isinstance(sources, dict) or set(sources) != SOURCE_KEYS:
        return "malformed-sources"
    if not isinstance(sources["harness_support"], dict):
        return "malformed-sources"
    for key in ("responsibilities", "access_denied"):
        if not isinstance(sources[key], list):
            return "malformed-sources"
    if not _rows_ok(sources["observations"]):
        return "malformed-sources"
    for obs in sources["observations"]:
        if set(obs) != OBSERVATION_KEYS:
            return "malformed-sources"
    return None


def _report_shape_error(report):
    if not isinstance(report, dict) or set(report) != REPORT_KEYS:
        return "malformed-shape"
    if not isinstance(report["scope"], dict) or set(report["scope"]) != SCOPE_KEYS:
        return "malformed-shape"
    for key in ("ledger", "contradictions", "signals", "candidates"):
        if not _rows_ok(report[key]):
            return "malformed-shape"
    if not isinstance(report["notes"], list):
        return "malformed-shape"
    if not isinstance(report["ranking"], dict) or set(report["ranking"]) != {"basis", "order"}:
        return "malformed-shape"
    if not isinstance(report["decision"], str):
        return "malformed-shape"
    answers = report["surface_answers"]
    if not isinstance(answers, dict) or set(answers) != set(_surface_keys()):
        return "malformed-shape"
    for value in answers.values():
        if not isinstance(value, dict) or set(value) != {"assessment", "reason"}:
            return "malformed-shape"
    return None


def review_assessment(sources, report):
    """One synthetic source document plus one synthetic report -> a bounded, deterministic
    verdict `{"verdict": ..., "findings": [sorted codes]}`.

    THIS IS NOT A MODEL AND IT DOES NOT RUN ONE. It is a structural reader: it decides whether a
    written report is consistent with the written evidence it cites and with the vocabularies the
    shipped card and template define. It never decides whether an assessment is a GOOD one.

    It returns on every input it is given — a malformed document is a finding, never an
    exception — so a caller is never handed a traceback instead of a verdict.
    """
    error = _sources_shape_error(sources)
    if error:
        return {"verdict": "refused", "findings": [error]}
    error = _report_shape_error(report)
    if error:
        return {"verdict": "refused", "findings": [error]}

    statuses = _evidence_statuses()
    assessments = _permitted_assessments()
    recommendations = _permitted_recommendations()
    decisions = _permitted_decisions()
    basis = _ranking_basis()

    observations = {obs["id"]: obs for obs in sources["observations"]}
    responsibilities = set(sources["responsibilities"])
    findings = set()

    # "No gain inference", delegated to the product authority that already owns the rule rather
    # than re-spelled here. `workflow_eval.assert_no_gain_claim` sweeps every string in a nested
    # document, keys included, and names what a token sweep cannot prove.
    try:
        we.assert_no_gain_claim(report, where="this fixture report")
    except we.EvalError:
        findings.add("gain-claim")

    cited = []

    for row in report["ledger"]:
        evidence = row.get("evidence") or []
        cited.extend(evidence)
        status = row.get("status")
        if status not in statuses:
            findings.add("status-not-permitted")
        elif status == "observed":
            supporting = [observations[oid] for oid in evidence if oid in observations]
            if not any(obs["provenance"] in OBSERVED_PROVENANCE for obs in supporting):
                findings.add("observed-without-observation")

    for signal in report["signals"]:
        recurrence = signal.get("recurrence") or []
        cited.extend(recurrence)
        assessment = signal.get("assessment")
        if assessment not in assessments:
            findings.add("assessment-not-permitted")
        elif assessment == "candidate":
            known = [oid for oid in recurrence if oid in observations]
            categories = {observations[oid]["category"] for oid in known}
            if len(set(known)) < 2 or categories != {signal.get("category")}:
                findings.add("recurrence-unsupported")

    for oid in cited:
        if oid not in observations:
            findings.add("unknown-evidence-id")
        elif observations[oid]["provenance"] == HIDDEN_PROVENANCE:
            findings.add("hidden-answer-use")

    # A contradiction is DERIVED from the sources — two observations about one subject that
    # assert different things — and never stated by them. The report must carry exactly the
    # derived set, with both sides intact.
    grouped = {}
    for obs in sources["observations"]:
        grouped.setdefault(obs["subject"], {}).setdefault(obs["asserts"], set()).add(obs["id"])
    derived = {subject: set().union(*by_claim.values())
               for subject, by_claim in grouped.items() if len(by_claim) > 1}
    declared = {row.get("subject"): row for row in report["contradictions"]}
    if set(derived) - set(declared):
        findings.add("contradiction-unreported")
    if set(declared) - set(derived):
        findings.add("contradiction-fabricated")
    for subject in sorted(set(derived) & set(declared)):
        row = declared[subject]
        if (set(row.get("observations") or []) != derived[subject]
                or row.get("resolution") != RESOLUTION_REPORTED):
            findings.add("contradiction-silently-resolved")

    for key, answer in report["surface_answers"].items():
        if answer["assessment"] not in assessments:
            findings.add("assessment-not-permitted")
        if key not in responsibilities:
            if (answer["assessment"] != "not-applicable"
                    or not str(answer["reason"]).strip()):
                findings.add("forced-recommendation")

    scoped_surfaces = set(report["scope"]["surfaces"])
    for candidate in report["candidates"]:
        if candidate.get("recommendation") not in recommendations:
            findings.add("recommendation-not-permitted")
        if (candidate.get("kind") in DEFERRED_KINDS
                and candidate.get("recommendation") != "defer"):
            findings.add("redesign-not-deferred")
        confidence = candidate.get("numeric_confidence")
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
            meta = candidate.get("confidence_meta") or {}
            if not all(str(meta.get(key, "")).strip() for key in CONFIDENCE_META_KEYS):
                findings.add("fabricated-confidence")
        if not set(candidate.get("surfaces") or []) <= scoped_surfaces:
            findings.add("scope-overreach")
        for harness in candidate.get("harnesses") or []:
            if sources["harness_support"].get(harness) != "supported":
                findings.add("cross-harness-transfer")
        for use in candidate.get("tool_use") or []:
            if use.get("mutates") and (use.get("target") != "temporary-copy"
                                       or not str(use.get("limitation", "")).strip()):
                findings.add("silent-mutation")

    if set(report["ranking"]["basis"]) - basis:
        findings.add("ranking-basis-not-permitted")
    if set(report["ranking"]["order"]) != {c.get("id") for c in report["candidates"]}:
        findings.add("unranked-candidate")

    if report["decision"] not in decisions:
        findings.add("decision-not-permitted")

    if set(report["scope"]["evidence_not_available"]) != set(sources["access_denied"]):
        findings.add("unknown-not-carried")

    return {"verdict": "refused" if findings else "accepted", "findings": sorted(findings)}


def _case_names():
    return sorted(p.name for p in CASES_DIR.iterdir() if p.is_dir())


def _read_json(path, hook=None):
    """Parse one fixture file, or report the bounded refusal code for a file that will not
    parse. A truncated document is a finding, not a traceback."""
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=hook), None
    except json.JSONDecodeError:
        return None, "malformed-json"


def review_case(name, hook=None):
    case_dir = CASES_DIR / name
    sources, error = _read_json(case_dir / "sources.json", hook)
    if error:
        return {"verdict": "refused", "findings": [error]}
    report, error = _read_json(case_dir / "report.json", hook)
    if error:
        return {"verdict": "refused", "findings": [error]}
    return review_assessment(sources, report)


def _review_corpus(hook=None):
    return {name: review_case(name, hook) for name in _case_names()}


def _unreadable_sources():
    """Case names whose `sources.json` the checker cannot read. Pinned to an exact set by a
    test, so no other test has to skip a case on a condition nobody checked."""
    names = set()
    for name in _case_names():
        sources, error = _read_json(CASES_DIR / name / "sources.json")
        if error or _sources_shape_error(sources):
            names.add(name)
    return names


def _unreadable_reports():
    """The same, for `report.json`."""
    names = set()
    for name in _case_names():
        report, error = _read_json(CASES_DIR / name / "report.json")
        if error or _report_shape_error(report):
            names.add(name)
    return names


def _reversed_pairs(pairs):
    """An `object_pairs_hook` that builds every object with its keys in the opposite order. Used
    to prove the checker reads values, not insertion order."""
    return dict(reversed(pairs))


# ---- the trap, and its control ---------------------------------------------------------------


class _SeamReached(AssertionError):
    """Raised by an armed seam. A distinct type on purpose: a control that merely asserted
    "something raised" would also pass when the seam was never replaced and the real call failed
    on its own arguments."""


class _Raiser:
    def __init__(self, name):
        self.name = name

    def __call__(self, *args, **kwargs):
        raise _SeamReached(f"{self.name} was reached: args={args!r} kwargs={kwargs!r}")


#: Every way this process could reach a home directory, the network, or another program. Armed
#: for the whole corpus review; `PROBES` below fires each one so "nothing was called" can never
#: be confused with "nothing was armed".
FORBIDDEN_SEAMS = (
    ("pathlib.Path.home", pathlib.Path, "home"),
    ("os.path.expanduser", os.path, "expanduser"),
    ("os.system", os, "system"),
    ("os.popen", os, "popen"),
    ("subprocess.run", subprocess, "run"),
    ("subprocess.Popen", subprocess, "Popen"),
    ("subprocess.call", subprocess, "call"),
    ("subprocess.check_call", subprocess, "check_call"),
    ("subprocess.check_output", subprocess, "check_output"),
    ("socket.socket", socket, "socket"),
    ("socket.create_connection", socket, "create_connection"),
    ("socket.getaddrinfo", socket, "getaddrinfo"),
    ("urllib.request.urlopen", urllib.request, "urlopen"),
)

#: One call per armed seam, with arguments that would fail harmlessly if the seam were NOT armed
#: — a missing binary, a closed port — so the control distinguishes `_SeamReached` from the real
#: call's own error. Pinned equal to `FORBIDDEN_SEAMS` by name, so a seam added without a probe
#: fails rather than going unfired.
PROBES = {
    "pathlib.Path.home": lambda: pathlib.Path.home(),
    "os.path.expanduser": lambda: os.path.expanduser("~"),
    "os.system": lambda: os.system(":"),
    "os.popen": lambda: os.popen(":"),
    "subprocess.run": lambda: subprocess.run(["/nonexistent-d26-probe"]),
    "subprocess.Popen": lambda: subprocess.Popen(["/nonexistent-d26-probe"]),
    "subprocess.call": lambda: subprocess.call(["/nonexistent-d26-probe"]),
    "subprocess.check_call": lambda: subprocess.check_call(["/nonexistent-d26-probe"]),
    "subprocess.check_output": lambda: subprocess.check_output(["/nonexistent-d26-probe"]),
    "socket.socket": lambda: socket.socket(),
    "socket.create_connection": lambda: socket.create_connection(("127.0.0.1", 1), 0.01),
    "socket.getaddrinfo": lambda: socket.getaddrinfo("localhost", 1),
    "urllib.request.urlopen": lambda: urllib.request.urlopen("http://127.0.0.1:1/"),
}


@contextlib.contextmanager
def _armed_seams():
    with contextlib.ExitStack() as stack:
        for name, target, attribute in FORBIDDEN_SEAMS:
            stack.enter_context(mock.patch.object(target, attribute, _Raiser(name)))
        yield


class AssessmentSkillFixtureTests(unittest.TestCase):
    """Invariants of the `tests/fixtures/assessment-skill/` corpus and of the checker over it.

    Every claim below is about a fixture, a vocabulary read out of the shipped card, or the
    checker's own determinism. None is about a model: nothing here dispatches one, observes one,
    or infers what one would do.
    """

    # ---- the corpus, its shape, and the oracle's placement ---------------------------------

    def test_every_case_directory_holds_exactly_the_two_files_the_checker_reads(self):
        """Exact set equality per case, because the defect this guards against is an oracle,
        a hint or a README sitting beside the inputs where the checker could reach it."""
        self.assertTrue(_case_names(), "the corpus is empty")
        for name in _case_names():
            with self.subTest(case=name):
                present = {p.name for p in (CASES_DIR / name).iterdir()}
                self.assertEqual(present, set(CASE_FILES))

    def test_the_oracle_covers_exactly_the_cases_on_disk_and_sits_outside_them(self):
        """`shared | uncovered == every case` with an empty intersection: a case with no
        expected verdict and an expected verdict with no case are both failures."""
        expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
        cases = set(_case_names())
        self.assertEqual(set(expected), cases)
        self.assertEqual(set(expected) & (cases - set(expected)), set())
        self.assertEqual(EXPECTED_PATH.parent, FIXTURE_ROOT)
        self.assertFalse((CASES_DIR / EXPECTED_PATH.name).exists())

    def test_every_expected_verdict_is_a_verdict_and_a_sorted_subset_of_the_vocabulary(self):
        expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
        for name, verdict in sorted(expected.items()):
            with self.subTest(case=name):
                self.assertEqual(set(verdict), {"verdict", "findings"})
                self.assertIn(verdict["verdict"], {"accepted", "refused"})
                self.assertEqual(verdict["findings"], sorted(verdict["findings"]))
                self.assertLessEqual(set(verdict["findings"]), FINDING_CODES)
                self.assertEqual(bool(verdict["findings"]), verdict["verdict"] == "refused")

    # ---- the verdicts themselves ------------------------------------------------------------

    def test_every_case_produces_exactly_the_verdict_and_finding_set_the_oracle_records(self):
        """Exact dict equality per case — not "a finding was produced", not "the code is in
        there". A checker that emitted every code for every case would pass a membership test
        and fails this one."""
        expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
        actual = _review_corpus()
        for name in _case_names():
            with self.subTest(case=name):
                self.assertEqual(actual[name], expected[name])
        self.assertEqual(actual, expected)

    def test_the_corpus_exercises_every_finding_code_and_invents_none(self):
        """Exact partition against the checker's vocabulary, both directions at once: a rule
        with no case that reaches it is as much a failure as a case asserting a code no rule
        can emit."""
        produced = {code for verdict in _review_corpus().values()
                    for code in verdict["findings"]}
        self.assertEqual(produced, set(FINDING_CODES))
        self.assertEqual(produced - set(FINDING_CODES), set())
        self.assertEqual(set(FINDING_CODES) - produced, set())

    def test_the_corpus_accepts_as_well_as_refuses_and_names_a_mutant_that_flips_one(self):
        """POSITIVE CONTROL. A corpus where every case refuses proves only that the checker can
        refuse. At least ten cases are accepted; and the mutation named here — dropping the
        healthy case's recurrence to a single observation — turns the flagship accept into
        exactly one refusal, so the accept is not vacuous."""
        verdicts = _review_corpus()
        accepted = {n for n, v in verdicts.items() if v["verdict"] == "accepted"}
        refused = {n for n, v in verdicts.items() if v["verdict"] == "refused"}
        self.assertEqual(accepted | refused, set(_case_names()))
        self.assertEqual(accepted & refused, set())
        self.assertGreaterEqual(len(accepted), 10)
        self.assertIn("healthy-recurring-signal", accepted)

        case_dir = CASES_DIR / "healthy-recurring-signal"
        sources = json.loads((case_dir / "sources.json").read_text(encoding="utf-8"))
        report = json.loads((case_dir / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(review_assessment(sources, report),
                         {"verdict": "accepted", "findings": []})
        report["signals"][0]["recurrence"] = ["OBS-1"]
        self.assertEqual(review_assessment(sources, report),
                         {"verdict": "refused", "findings": ["recurrence-unsupported"]})

    def test_sibling_cases_share_byte_identical_sources_so_the_report_decides_the_verdict(self):
        """The differential control. Eight source documents carry every case; within a
        group the sources bytes are equal and the reports are pairwise distinct, so a verdict
        difference inside a group can only have come from the report. Every group with more
        than one case contains at least one accept and at least one refusal."""
        verdicts = _review_corpus()
        groups = {}
        for name in _case_names():
            digest = _sha((CASES_DIR / name / "sources.json").read_bytes())
            groups.setdefault(digest, []).append(name)
        self.assertEqual(len(groups), 8, sorted((len(v), v[0]) for v in groups.values()))
        for digest, names in sorted(groups.items()):
            with self.subTest(group=names[0], size=len(names)):
                reports = [(_sha((CASES_DIR / n / "report.json").read_bytes()), n)
                           for n in names]
                self.assertEqual(len({d for d, _ in reports}), len(names),
                                 f"two cases in one group share a report: {reports}")
                if len(names) > 1:
                    outcomes = {verdicts[n]["verdict"] for n in names}
                    self.assertEqual(outcomes, {"accepted", "refused"}, names)

    # ---- the acceptance terms, one test each -------------------------------------------------

    def test_a_malformed_document_is_refused_with_a_bounded_code_and_raises_nothing(self):
        """"Malformed bounded". Three shapes — unparseable JSON, a report that is not an object,
        and a source document with the wrong keys — each produce exactly one code and no
        exception. The in-memory half proves the guard is the checker's, not the corpus's:
        every key of a well-formed report, deleted one at a time, is still bounded."""
        self.assertEqual(review_case("report-json-is-truncated"),
                         {"verdict": "refused", "findings": ["malformed-json"]})
        self.assertEqual(review_case("report-shape-is-not-a-report"),
                         {"verdict": "refused", "findings": ["malformed-shape"]})
        self.assertEqual(review_case("source-shape-is-not-a-source"),
                         {"verdict": "refused", "findings": ["malformed-sources"]})

        case_dir = CASES_DIR / "healthy-recurring-signal"
        sources = json.loads((case_dir / "sources.json").read_text(encoding="utf-8"))
        report = json.loads((case_dir / "report.json").read_text(encoding="utf-8"))
        for key in sorted(REPORT_KEYS):
            with self.subTest(dropped=key):
                broken = {k: v for k, v in report.items() if k != key}
                self.assertEqual(review_assessment(sources, broken),
                                 {"verdict": "refused", "findings": ["malformed-shape"]})
        for key in sorted(SOURCE_KEYS):
            with self.subTest(dropped_source=key):
                broken = {k: v for k, v in sources.items() if k != key}
                self.assertEqual(review_assessment(broken, report),
                                 {"verdict": "refused", "findings": ["malformed-sources"]})
        for junk in (None, [], "", 0, {"scope": None}):
            with self.subTest(junk=repr(junk)):
                self.assertEqual(review_assessment(sources, junk)["findings"],
                                 ["malformed-shape"])
                self.assertEqual(review_assessment(junk, report)["findings"],
                                 ["malformed-sources"])

    def test_a_contradiction_derived_from_the_sources_must_be_carried_not_settled(self):
        """"Contradictions surfaced". The pair is DERIVED — two observations about one subject
        that assert different things — so the sources never state that a contradiction exists.
        Three reports over one byte-identical source document: carrying both sides is accepted,
        dropping the pair is `contradiction-unreported`, and settling it on one side is
        `contradiction-silently-resolved` rather than a silent pass."""
        base = CASES_DIR / "contradiction-reported-unresolved"
        sources = json.loads((base / "sources.json").read_text(encoding="utf-8"))
        for sibling in ("contradiction-left-unreported",
                        "contradiction-resolved-by-picking-a-side"):
            self.assertEqual((CASES_DIR / sibling / "sources.json").read_bytes(),
                             (base / "sources.json").read_bytes())

        grouped = {}
        for obs in sources["observations"]:
            grouped.setdefault(obs["subject"], set()).add(obs["asserts"])
        conflicted = {s for s, claims in grouped.items() if len(claims) > 1}
        self.assertEqual(conflicted, {"capability:cursor:confined-dispatch"})

        report = json.loads((base / "report.json").read_text(encoding="utf-8"))
        self.assertEqual({row["subject"] for row in report["contradictions"]}, conflicted)
        self.assertEqual(set(report["contradictions"][0]["observations"]), {"OBS-1", "OBS-2"})
        self.assertEqual(review_assessment(sources, report),
                         {"verdict": "accepted", "findings": []})

        self.assertEqual(review_case("contradiction-left-unreported"),
                         {"verdict": "refused", "findings": ["contradiction-unreported"]})
        self.assertEqual(review_case("contradiction-resolved-by-picking-a-side"),
                         {"verdict": "refused",
                          "findings": ["contradiction-silently-resolved"]})
        self.assertEqual(review_case("contradiction-declared-without-evidence"),
                         {"verdict": "refused", "findings": ["contradiction-fabricated"]})

    def test_the_gain_sweep_is_the_products_own_authority_and_not_a_second_token_list(self):
        """"No gain inference", enforced by `workflow_eval.assert_no_gain_claim` — the rule the
        product already owns — rather than by a list re-spelled here. The checker holds no gain
        vocabulary of its own; this test proves that by replacing the authority with a raiser
        and watching the finding appear on a report that carries no token at all."""
        self.assertEqual(review_case("fabricated-gain-in-a-note"),
                         {"verdict": "refused", "findings": ["gain-claim"]})

        case_dir = CASES_DIR / "healthy-recurring-signal"
        sources = json.loads((case_dir / "sources.json").read_text(encoding="utf-8"))
        report = json.loads((case_dir / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(review_assessment(sources, report)["findings"], [])
        with mock.patch.object(we, "assert_no_gain_claim",
                               side_effect=we.EvalError("stubbed")):
            self.assertEqual(review_assessment(sources, report),
                             {"verdict": "refused", "findings": ["gain-claim"]})

        source = inspect.getsource(review_assessment)
        self.assertIn("assert_no_gain_claim", source)
        for token in sorted(we.GAIN_TOKENS):
            with self.subTest(token=token):
                self.assertNotIn(token, source,
                                 "the checker must delegate the gain vocabulary, not copy it")

    def test_reviewing_the_whole_corpus_reaches_no_home_network_or_process_seam(self):
        """"No home/network/CLI". Thirteen seams armed with a raiser for the duration of a full
        corpus review, including every `subprocess` entry point — so a `claude`, `codex`,
        `copilot`, `agent`, `graphify` or `gh` invocation could not happen quietly even if
        something tried. Paired with the control below, which fires all thirteen."""
        expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
        with _armed_seams():
            actual = _review_corpus()
        self.assertEqual(actual, expected)

    def test_the_armed_seam_trap_fires_on_every_seam_it_claims_to_arm(self):
        """CONTROL. Without this, the test above could be passing because nothing was replaced.
        `PROBES` is pinned equal to `FORBIDDEN_SEAMS` by name, and each probe is given arguments
        that would fail with the real call's own error — so catching `_SeamReached` specifically
        is what distinguishes armed from merely absent."""
        self.assertEqual(set(PROBES), {name for name, _, _ in FORBIDDEN_SEAMS})
        self.assertEqual(len(FORBIDDEN_SEAMS), 13)
        with _armed_seams():
            # Checked BEFORE any probe is fired: if arming had silently failed, firing a probe
            # would be the very call this suite forbids, so the replacement is confirmed first
            # and the probes below can only ever reach a raiser.
            for name, target, attribute in FORBIDDEN_SEAMS:
                self.assertIsInstance(getattr(target, attribute), _Raiser,
                                      f"{name} was not replaced")
            for name, probe in sorted(PROBES.items()):
                with self.subTest(seam=name):
                    with self.assertRaises(_SeamReached):
                        probe()
        self.assertFalse(isinstance(subprocess.run, _Raiser), "seams restored afterwards")
        self.assertFalse(isinstance(os.path.expanduser, _Raiser), "seams restored afterwards")

    def test_the_corpus_reviews_identically_twice_and_under_reversed_key_order(self):
        """"Stable fixture output". Run twice, compare serialised; then rebuild every JSON
        object with its keys in the opposite insertion order and compare again — a checker that
        read `next(iter(...))` anywhere would diverge on the second half."""
        first = json.dumps(_review_corpus(), sort_keys=True)
        second = json.dumps(_review_corpus(), sort_keys=True)
        self.assertEqual(first, second)
        reversed_order = json.dumps(_review_corpus(hook=_reversed_pairs), sort_keys=True)
        self.assertEqual(first, reversed_order)

        verdicts = _review_corpus()
        for verdict in verdicts.values():
            self.assertEqual(verdict["findings"], sorted(verdict["findings"]))
            self.assertLessEqual(set(verdict["findings"]), FINDING_CODES)
        self.assertEqual({n for n, v in verdicts.items() if len(v["findings"]) > 1},
                         {"one-harness-transfer-with-a-gain-note"},
                         "at least one case must carry two findings, or the sort above is "
                         "satisfied by any ordering at all and pins nothing")

    # ---- the fixtures are fixtures: no hidden answers, no real repository -------------------

    def test_no_source_document_carries_the_assessment_side_vocabulary(self):
        """"Hidden-answer use" at the corpus level. A source states what a reader would SEE; the
        moment it states the conclusion, the checker is proving retrieval rather than
        consistency. The ban covers every finding code and every conclusion token; it
        deliberately excludes `unknown` and `unverified`, which are evidence states a repository
        legitimately records about itself."""
        for name in _case_names():
            text = (CASES_DIR / name / "sources.json").read_text(encoding="utf-8").lower()
            for token in sorted(ANSWER_SIDE_TOKENS):
                with self.subTest(case=name, token=token):
                    self.assertNotIn(token, text)
            self.assertNotIn("expected", text)

    def test_the_held_out_source_is_marked_quarantined_and_its_citation_is_what_is_refused(self):
        """The corpus's only `hidden-label` row exists so a report can be caught citing it.
        What is asserted: it is marked quarantined, its statement says the assessment may not
        read it, and the sibling case that leaves it unread is ACCEPTED on byte-identical
        sources — so the finding tracks the CITATION, not the presence of the row. What is NOT
        asserted, because a test cannot: that the statement leaks nothing."""
        sources = json.loads(
            (CASES_DIR / "hidden-label-left-unread" / "sources.json").read_text("utf-8"))
        hidden = [o for o in sources["observations"]
                  if o["provenance"] == HIDDEN_PROVENANCE]
        self.assertEqual([o["id"] for o in hidden], ["OBS-9"])
        self.assertIn("not permitted", hidden[0]["statement"])
        self.assertEqual((CASES_DIR / "hidden-label-cited-as-evidence"
                          / "sources.json").read_bytes(),
                         (CASES_DIR / "hidden-label-left-unread"
                          / "sources.json").read_bytes())
        self.assertEqual(review_case("hidden-label-left-unread")["verdict"], "accepted")
        self.assertEqual(review_case("hidden-label-cited-as-evidence"),
                         {"verdict": "refused", "findings": ["hidden-answer-use"]})

    def test_exactly_the_named_cases_carry_a_document_the_checker_cannot_read(self):
        """The corpus's malformed cases, as exact sets. Every other test below iterates the
        readable cases; without this pin, a test that skipped an unreadable fixture would be
        indistinguishable from one that never ran."""
        self.assertEqual(_unreadable_sources(), {"source-shape-is-not-a-source"})
        self.assertEqual(_unreadable_reports(),
                         {"report-json-is-truncated", "report-shape-is-not-a-report"})
        readable = set(_case_names()) - _unreadable_sources()
        self.assertEqual(readable | _unreadable_sources(), set(_case_names()))
        self.assertEqual(readable & _unreadable_sources(), set())

    def test_every_fixture_path_sits_under_its_own_synthetic_tree_and_in_no_real_one(self):
        """A synthetic corpus that cited a real file would silently become a test of this
        repository. Every observation path is prefixed with the tree name its own source
        document declares, and no such tree exists in this checkout."""
        readable = sorted(set(_case_names()) - _unreadable_sources())
        self.assertEqual(len(readable), len(_case_names()) - 1)
        trees = set()
        for name in readable:
            sources, _ = _read_json(CASES_DIR / name / "sources.json")
            tree = sources["repository"].split("/")[1]
            trees.add(tree)
            with self.subTest(case=name):
                self.assertFalse((REPO_ROOT / tree).exists(),
                                 f"{tree}/ is a real directory in this checkout")
                for obs in sources["observations"]:
                    self.assertTrue(obs["path"].startswith(f"{tree}/"), obs["path"])
                    self.assertFalse((REPO_ROOT / obs["path"]).exists(),
                                     f"{obs['path']} is a real path in this checkout")
                self.assertRegex(sources["revision"], r"^fixture-revision-")
        self.assertEqual(len(trees), 7)

    def test_no_fixture_file_carries_a_forty_hex_string_that_could_read_as_a_revision(self):
        for path in sorted(FIXTURE_ROOT.rglob("*")):
            if path.is_file():
                with self.subTest(file=path.name):
                    self.assertNotRegex(path.read_text(encoding="utf-8"),
                                        r"\b[0-9a-f]{40}\b")

    def test_no_fixture_file_names_a_command_to_run(self):
        """The corpus is data a checker reads. It names no harness binary, no engine, no package
        manager — the same fence `SkillPackagingTests` holds over the staged card, reused rather
        than re-spelled."""
        offenders = []
        for path in sorted(FIXTURE_ROOT.rglob("*")):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for pattern in BORROWED_COMMAND_PATTERNS:
                for hit in re.findall(pattern, text):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {pattern} -> {hit!r}")
        self.assertEqual(offenders, [], f"command shapes in the corpus: {offenders}")

    # ---- the vocabularies are the card's, read at call time ---------------------------------

    def test_every_vocabulary_the_checker_enforces_is_the_cards_or_the_templates_own(self):
        """Not one of these sets is a literal in this section: each is parsed out of the shipped
        card or template at call time. `SkillPackagingTests` pins the same sets to literals, so
        the two files disagree loudly if the card's wording drifts."""
        self.assertEqual(_evidence_statuses(),
                         {"observed", "documented", "inferred", "unknown", "unverified",
                          "insufficient-evidence"})
        self.assertEqual(_permitted_assessments(),
                         {"candidate", "defer", "not-applicable", "unknown",
                          "insufficient-evidence"})
        self.assertEqual(_permitted_recommendations(),
                         {"prepare brief", "collect evidence", "manual-only", "defer",
                          "no supported intervention"})
        self.assertEqual(_permitted_decisions(),
                         {"no supported intervention", "evidence collection needed",
                          "draft task brief(s)", "requires explicit authorization"})
        self.assertEqual(_ranking_basis(),
                         {"expected learning value", "reversibility", "evidence quality",
                          "disruption"})
        self.assertEqual(_surface_keys(),
                         {"shared-runtime-contracts", "four-harnesses",
                          "skills-and-context-planning", "evaluation-and-release"})

    def test_every_report_answers_exactly_the_four_surfaces_the_card_names(self):
        readable = sorted(set(_case_names()) - _unreadable_reports())
        self.assertEqual(len(readable), len(_case_names()) - 2)
        for name in readable:
            report, _ = _read_json(CASES_DIR / name / "report.json")
            with self.subTest(case=name):
                self.assertEqual(set(report["surface_answers"]), set(_surface_keys()))

    def test_every_source_harness_map_uses_exactly_this_repos_four_harness_keys(self):
        """The corpus's harness names come from this repository's own roster roots, not from a
        list invented here — so a fixture cannot name a fifth harness or quietly drop one. The
        SUPPORT VALUES stay synthetic: nothing here reads a real capability record."""
        readable = sorted(set(_case_names()) - _unreadable_sources())
        self.assertEqual(len(readable), len(_case_names()) - 1)
        for name in readable:
            sources, _ = _read_json(CASES_DIR / name / "sources.json")
            with self.subTest(case=name):
                self.assertEqual(set(sources["harness_support"]), set(HARNESS_SKILL_ROOTS))

    def test_the_one_harness_case_scopes_its_claim_and_refuses_to_transfer_it(self):
        """The brief's fourth named fixture: a capability exactly one harness carries. The
        accepted report scopes the candidate to that harness; the sibling that extends it to all
        four is refused. Both sit on the same source document, whose other three records carry
        the literal `unknown` — which is neither a denial nor a confirmation."""
        sources = json.loads((CASES_DIR / "one-harness-capability-scoped"
                              / "sources.json").read_text(encoding="utf-8"))
        supported = {h for h, v in sources["harness_support"].items() if v == "supported"}
        self.assertEqual(len(supported), 1)
        self.assertEqual({v for h, v in sources["harness_support"].items()
                          if h not in supported}, {"unknown"})
        self.assertEqual(review_case("one-harness-capability-scoped")["verdict"], "accepted")
        self.assertEqual(review_case("one-harness-capability-transferred"),
                         {"verdict": "refused", "findings": ["cross-harness-transfer"]})

    def test_the_non_agent_fixture_records_not_applicable_and_a_forced_candidate_is_refused(self):
        """The brief's first named fixture. A repository with no analogous responsibility gets
        `not-applicable` with a reason on every surface — the card's own instruction — and the
        sibling that answers `candidate` on one of them is refused."""
        sources = json.loads((CASES_DIR / "non-agent-repository-not-applicable"
                              / "sources.json").read_text(encoding="utf-8"))
        self.assertEqual(sources["responsibilities"], [])
        report = json.loads((CASES_DIR / "non-agent-repository-not-applicable"
                             / "report.json").read_text(encoding="utf-8"))
        self.assertEqual({a["assessment"] for a in report["surface_answers"].values()},
                         {"not-applicable"})
        self.assertTrue(all(a["reason"].strip()
                            for a in report["surface_answers"].values()))
        self.assertEqual(report["candidates"], [])
        self.assertEqual(report["decision"], "no supported intervention")
        self.assertEqual(review_case("non-agent-repository-not-applicable")["verdict"],
                         "accepted")
        self.assertEqual(review_case("non-agent-repository-forced-candidate"),
                         {"verdict": "refused", "findings": ["forced-recommendation"]})

    def test_the_settled_repository_fixture_records_no_change_and_carries_no_repeated_category(self):
        """The brief's second named fixture. "Nothing to change" is a legitimate result: no
        category in this source document occurs twice, so no recurrence exists to support a
        candidate — and the sibling that calls one a candidate anyway is refused."""
        sources = json.loads((CASES_DIR / "mature-repository-no-change"
                              / "sources.json").read_text(encoding="utf-8"))
        categories = [obs["category"] for obs in sources["observations"]]
        self.assertEqual(len(set(categories)), len(categories), "no category may repeat here")
        report = json.loads((CASES_DIR / "mature-repository-no-change"
                             / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["decision"], "no supported intervention")
        self.assertEqual(report["candidates"], [])
        self.assertNotIn("candidate", {s["assessment"] for s in report["signals"]})
        self.assertEqual(review_case("mature-repository-no-change")["verdict"], "accepted")
        self.assertEqual(review_case("mature-repository-candidate-without-recurrence"),
                         {"verdict": "refused", "findings": ["recurrence-unsupported"]})

    def test_the_recurring_signal_fixture_carries_one_category_in_three_evidence_classes(self):
        """The brief's third named fixture. "Reproducible" here means a bounded read finds the
        same category in three independent evidence classes — source, record and test — not that
        anything was measured twice."""
        sources = json.loads((CASES_DIR / "healthy-recurring-signal"
                              / "sources.json").read_text(encoding="utf-8"))
        report = json.loads((CASES_DIR / "healthy-recurring-signal"
                             / "report.json").read_text(encoding="utf-8"))
        signal = report["signals"][0]
        cited = [o for o in sources["observations"] if o["id"] in signal["recurrence"]]
        self.assertEqual(len(cited), 3)
        self.assertEqual({o["category"] for o in cited}, {signal["category"]})
        self.assertEqual({o["provenance"] for o in cited}, {"source", "record", "test"})
        tree = sources["repository"].split("/")[1]
        self.assertEqual({o["path"] for o in cited},
                         {f"{tree}/src/verify/ceiling.py",
                          f"{tree}/records/2031-02-04-run.json",
                          f"{tree}/tests/test_verify_ceiling.py"})
        self.assertTrue(signal["no_fit_scope"].strip(),
                        "a candidate must name what it does NOT cover")

    def test_fabricated_confidence_is_refused_and_a_declared_one_is_not(self):
        """The card permits a number only beside its prediction target, provenance and
        validation status. Both sides are in the corpus, so this is not "every number is
        refused"."""
        self.assertEqual(review_case("uncalibrated-confidence"),
                         {"verdict": "refused", "findings": ["fabricated-confidence"]})
        self.assertEqual(review_case("confidence-declared-with-provenance")["verdict"],
                         "accepted")
        declared = json.loads((CASES_DIR / "confidence-declared-with-provenance"
                               / "report.json").read_text(encoding="utf-8"))
        meta = declared["candidates"][0]["confidence_meta"]
        self.assertEqual(set(meta), set(CONFIDENCE_META_KEYS))
        self.assertTrue(all(v.strip() for v in meta.values()))

    def test_a_mutating_tool_use_is_refused_unless_it_names_a_temporary_copy_and_its_limit(self):
        self.assertEqual(review_case("silent-mutation-of-the-target"),
                         {"verdict": "refused", "findings": ["silent-mutation"]})
        self.assertEqual(review_case("mutation-on-a-temporary-copy")["verdict"], "accepted")
        ok = json.loads((CASES_DIR / "mutation-on-a-temporary-copy"
                         / "report.json").read_text(encoding="utf-8"))
        use = ok["candidates"][0]["tool_use"][0]
        self.assertTrue(use["mutates"])
        self.assertEqual(use["target"], "temporary-copy")
        self.assertTrue(use["limitation"].strip())

    def test_a_broad_redesign_is_refused_unless_deferred_and_a_scope_jump_is_refused(self):
        """The card defers broad executable policy languages and autonomous self-modification by
        default, and a candidate may not reach a surface the assessment never scoped."""
        self.assertEqual(review_case("broad-policy-language-not-deferred"),
                         {"verdict": "refused", "findings": ["redesign-not-deferred"]})
        self.assertEqual(review_case("broad-policy-language-deferred")["verdict"], "accepted")
        self.assertEqual(review_case("scope-overreach-beyond-the-assessed-surfaces"),
                         {"verdict": "refused", "findings": ["scope-overreach"]})

    def test_a_withheld_evidence_class_must_be_carried_onto_the_report(self):
        """"Unknowns and gaps". The source names three evidence classes it could not show; the
        report must carry exactly those three, and the sibling that drops two is refused."""
        sources = json.loads((CASES_DIR / "partial-access-unknowns-carried"
                              / "sources.json").read_text(encoding="utf-8"))
        report = json.loads((CASES_DIR / "partial-access-unknowns-carried"
                             / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(set(report["scope"]["evidence_not_available"]),
                         set(sources["access_denied"]))
        self.assertEqual(len(sources["access_denied"]), 3)
        self.assertEqual(review_case("partial-access-unknowns-carried")["verdict"], "accepted")
        self.assertEqual(review_case("partial-access-unknowns-dropped"),
                         {"verdict": "refused", "findings": ["unknown-not-carried"]})

    # ---- the qualitative note ------------------------------------------------------------------

    def test_the_qualitative_note_labels_itself_qualitative_and_disclaims_observing_a_model(self):
        """The brief asks for a bounded application of the card to be inspected independently
        and LABELLED QUALITATIVE. It is a note, not a measurement: it asserts nothing, it is not
        compared to any checker output, and it says in its own text that no model was run."""
        text = QUALITATIVE_PATH.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^Status: qualitative$")
        self.assertIn("No model was run, dispatched or observed", text)
        we.assert_no_gain_claim(text, where="the qualitative note")

    def test_the_qualitative_note_is_bounded_to_named_cases_and_encodes_no_verdict(self):
        """"Bounded": it names the cases it looked at, every one exists, and they are a strict
        subset of the corpus. "Not an oracle": it carries no finding code and neither of the
        verdict keys, so no test could read it as an expectation even by accident."""
        text = QUALITATIVE_PATH.read_text(encoding="utf-8")
        line = re.search(r"(?m)^Cases inspected: (.+)$", text)
        self.assertIsNotNone(line, "the note must name the cases it inspected")
        named = set(re.findall(r"`([a-z0-9-]+)`", line.group(1)))
        cases = set(_case_names())
        self.assertTrue(named)
        self.assertLess(named, cases, "the inspection must be bounded, not the whole corpus")
        self.assertEqual(named - cases, set())
        for code in sorted(FINDING_CODES):
            with self.subTest(code=code):
                self.assertNotIn(code, text)
        self.assertNotIn('"verdict"', text)
        self.assertNotIn('"findings"', text)


if __name__ == "__main__":
    unittest.main()
