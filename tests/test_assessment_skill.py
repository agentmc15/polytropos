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
import io
import json
import re
import tempfile
import tomllib
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
