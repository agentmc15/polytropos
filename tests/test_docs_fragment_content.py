"""Content-level tests for the hand-authored fragments themselves (T7 of the
docs-site kit): docs-src/fragments/TEMPLATE.md's own pinned mechanical rules,
proven against the currently committed fragment files.

Derived from TEMPLATE.md ("The six required sections", "Mechanical rules",
"The link contract") and PLAN.md D5/T7's brief in
.claude/kits/docs-site/TASKS.md -- never from reading bin/docs_build.py's
implementation first. The generator (see FragmentValidationTests in
tests/test_docs_build.py) enforces exactly one fragment rule: no reserved
h1/h2 heading outside a fenced code block. Everything checked in this file --
word count, heading identity/order, the "not for" bullet, the splice-context
link contract, and the no-stale-numbers rule -- is a TEMPLATE.md/GUARDRAILS.md
MUST that nothing else in the suite currently enforces mechanically.

Every assertion here is written against db.skill_inventory()/the three known
fragment kinds rather than a hardcoded file list, and skips any fragment that
does not exist yet -- so this file needs no edits when Phases 4-5 (T12/T13/T14)
land the remaining 33 per-skill fragments; it starts checking each one the
moment its file is committed.

bin/ is not a package; docs_build.py is loaded via importlib by absolute path,
this repo's established `_load` idiom (see tests/test_harness_select.py).
"""

import importlib.util
import re
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = REPO_ROOT / "bin"
DOCS_SITE_ROOT = REPO_ROOT / "docs-site"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


db = _load("docs_build")
context_weight = _load("context_weight")
bench_routing = _load("bench_routing")


def _subparser(module, command):
    """The real argparse subparser object for one CLI subcommand, so a claim
    about a flag's presence/absence is checked against the engine's own
    parser rather than against prose. Duplicated from
    tests/test_docs_skill_dispositions.py's helper of the same purpose
    (kept independent here per this file's own stated convention of
    duplicating small helpers rather than cross-importing test modules)."""
    parser = module.build_parser()
    subparsers_action = next(
        a for a in parser._subparsers._group_actions if a.dest == "command"
    )
    return subparsers_action.choices[command]


def _option_strings(subparser):
    return {opt for a in subparser._actions for opt in a.option_strings}


def _positional_dests(subparser):
    return {a.dest for a in subparser._actions if not a.option_strings and a.dest != "help"}

# TEMPLATE.md "The six required sections": exact headings, exact order.
SIX_HEADINGS = (
    "### What it does",
    "### When to reach for it",
    "### Worked example",
    "### Failure modes & fallbacks",
    "### Cost & safety",
    "### Related",
)


def _existing_per_skill_fragments(repo_root=REPO_ROOT):
    """Yield (harness, name, path, text) for every per-skill 'In practice'
    fragment that currently exists on disk -- skips any skill with no
    fragment yet, so this generalizes to T12/T13/T14 without edits here."""
    for record in db.skill_inventory(repo_root):
        rel = db.skill_fragment_rel_path(record["harness"], record["name"])
        path = Path(repo_root) / rel
        if path.is_file():
            yield record["harness"], record["name"], path, path.read_text(encoding="utf-8")


def _all_existing_fragment_rel_paths(repo_root=REPO_ROOT):
    """Every fragment file (per-skill, harness-index, and parity) that
    currently exists under docs-src/fragments/, as repo-relative POSIX
    strings. TEMPLATE.md itself is deliberately excluded -- 'Nothing else in
    this directory is spliced anywhere -- this file included.'"""
    paths = []
    for record in db.skill_inventory(repo_root):
        rel = db.skill_fragment_rel_path(record["harness"], record["name"])
        if (Path(repo_root) / rel).is_file():
            paths.append(rel)
    for harness in db._HARNESS_SKILL_ROOTS:
        rel = db.harness_index_fragment_rel_path(harness)
        if (Path(repo_root) / rel).is_file():
            paths.append(rel)
    if (Path(repo_root) / db.PARITY_FRAGMENT_REL_PATH).is_file():
        paths.append(db.PARITY_FRAGMENT_REL_PATH)
    return paths


def _h3_heading_lines(text):
    """Every exact-h3 ATX heading line ('### ...', never h1/h2/h4+) outside a
    fenced code block, in document order -- uses db._fence_flags/_HEADING_RE
    directly (the same machinery the generator itself uses for this) rather
    than re-implementing heading parsing here."""
    lines = text.splitlines(keepends=True)
    flags = db._fence_flags(lines)
    headings = []
    for line, in_fence in zip(lines, flags):
        if in_fence:
            continue
        content = line.rstrip("\r\n")
        match = db._HEADING_RE.match(content)
        if match and len(match.group(1)) == 3:
            headings.append(content.rstrip())
    return headings


def _iter_inline_link_targets(text):
    """Yield the raw target string of every inline [text](target) markdown
    link outside a fenced code block. Same idiom as
    tests/test_docs_site.py's helper of the same name (db._fence_flags/
    _LINK_RE/_TARGET_RE) -- duplicated here rather than imported, since this
    is a separate, independently runnable test file."""
    lines = text.splitlines(keepends=True)
    flags = db._fence_flags(lines)
    for line, in_fence in zip(lines, flags):
        if in_fence:
            continue
        for match in db._LINK_RE.finditer(line):
            inner = match.group(2)
            target_match = db._TARGET_RE.match(inner)
            if target_match is None:
                continue
            _leading, target, _trailing = target_match.groups()
            wrapped = len(target) >= 2 and target.startswith("<") and target.endswith(">")
            yield target[1:-1] if wrapped else target


def _splice_target_dir(fragment_rel_path):
    """The docs-site/ directory a link IN this fragment must resolve
    against, per TEMPLATE.md's 'The link contract': a per-skill or
    harness-index fragment splices into docs-site/skills/<harness>/; the
    parity fragment splices into docs-site/skills/ (one level up -- 'the
    base directory is one level up')."""
    if fragment_rel_path == db.PARITY_FRAGMENT_REL_PATH:
        return DOCS_SITE_ROOT / "skills"
    parts = fragment_rel_path.split("/")
    # docs-src/fragments/skills/<harness>/<name-or-index>.md
    harness = parts[3]
    return DOCS_SITE_ROOT / "skills" / harness


def _section_body(text, start_heading, end_heading):
    """Text strictly between two heading lines (exclusive of both)."""
    start_idx = text.index(start_heading) + len(start_heading)
    end_idx = text.index(end_heading, start_idx)
    return text[start_idx:end_idx]


def _prose_word_count(text):
    """TEMPLATE.md's 'Mechanical rules' prose measure, T7b/P3-gate ruling 1:
    'prose = the file with fenced blocks and table rows (lines beginning |)
    removed.' Uses db._fence_flags (the generator's own fence tracker) rather
    than re-implementing fence detection -- a line is dropped if it is inside
    a fence OR (once un-fenced) starts with '|' after left-stripping."""
    lines = text.splitlines(keepends=True)
    flags = db._fence_flags(lines)
    kept = []
    for line, in_fence in zip(lines, flags):
        if in_fence:
            continue
        if line.lstrip().startswith("|"):
            continue
        kept.append(line)
    return len("".join(kept).split())


def _existing_index_and_parity_fragments(repo_root=REPO_ROOT):
    """Yield (label, path, text) for every harness-index fragment and the
    parity fragment that currently exists on disk. These share one word
    budget (TEMPLATE.md: 'Harness-index and parity fragments get 150-700
    wc -w, with no prose ceiling') distinct from the per-skill band."""
    for harness in db._HARNESS_SKILL_ROOTS:
        rel = db.harness_index_fragment_rel_path(harness)
        path = Path(repo_root) / rel
        if path.is_file():
            yield f"{harness}/index", path, path.read_text(encoding="utf-8")
    parity_path = Path(repo_root) / db.PARITY_FRAGMENT_REL_PATH
    if parity_path.is_file():
        yield "parity", parity_path, parity_path.read_text(encoding="utf-8")


class PerSkillFragmentWordBudgetTests(unittest.TestCase):
    """TEMPLATE.md 'Mechanical rules' as amended by T7b / P3 gate ruling 1
    (NOTES.md 'PHASE 3 GATE VERDICT'): 'per-skill fragments are 150-550 words
    by `wc -w` on the file (scaffolding included) AND at most 450 words of
    prose', where prose = the file with fenced code blocks and table rows
    (lines starting with `|`) removed. TWO ceilings, not one -- the gate's
    own reasoning is that a single total-only ceiling makes the budget the
    output: a 6-row table costs ~90 `wc -w` tokens, ~41 of them literal pipe
    characters carrying no information, so a fragment that legitimately
    needs a table pays for punctuation out of the same budget as its
    sentences. This supersedes the old single 150-450 band this class used
    to enforce, which `route.md` now fails (459 wc -w after its brief-
    required `escalate` Related link was restored) even though it is well
    inside both new numbers (459 total / 450 prose).

    This is at least as strong as the old guard on the dimension that
    matters: the old rule capped total words at 450 with no prose distinction,
    so a fragment could in principle spend its whole 450-word budget on
    prose. The new rule keeps that exact same 450-word prose ceiling (it did
    not move) and ADDS a separate, independent total-word ceiling (550) that
    only ever gives back the words a table/fence's own punctuation costs --
    prose can never exceed 450 under the new rule either, so nothing that
    passed the old rule's actual intent (bounded human-authored prose) can
    newly slip through; only the literal table/fence "tax" the gate
    identified as noise gets the extra headroom."""

    def test_every_existing_per_skill_fragment_is_within_the_two_new_ceilings(self):
        checked = 0
        for harness, name, path, text in _existing_per_skill_fragments():
            checked += 1
            word_count = len(text.split())  # matches `wc -w` token counting
            prose_count = _prose_word_count(text)
            rel = path.relative_to(REPO_ROOT).as_posix()
            with self.subTest(harness=harness, name=name):
                self.assertTrue(
                    150 <= word_count <= 550,
                    f"{rel}: {word_count} words (wc -w equivalent), outside "
                    "TEMPLATE.md's pinned 150-550 total band",
                )
                self.assertLessEqual(
                    prose_count,
                    450,
                    f"{rel}: {prose_count} prose words (fenced blocks and "
                    "table rows removed), exceeds TEMPLATE.md's 450-word "
                    "prose ceiling",
                )
        self.assertGreaterEqual(
            checked, 3, "expected at least the three T7 pilot fragments to exist"
        )


class HarnessIndexAndParityFragmentWordBudgetTests(unittest.TestCase):
    """TEMPLATE.md 'Mechanical rules' as amended by T7b: 'Harness-index and
    parity fragments get 150-700 wc -w, with no prose ceiling -- they
    summarize a roster rather than one skill and legitimately run longer.'
    P3 gate NOTES.md: 'nothing currently guards these; parity.md is ~616
    [words]' -- this class is the guard the gate said was missing, not a
    tightening of an existing one."""

    def test_every_existing_index_or_parity_fragment_is_within_150_to_700_words(self):
        checked = 0
        for label, path, text in _existing_index_and_parity_fragments():
            checked += 1
            word_count = len(text.split())
            with self.subTest(fragment=label):
                self.assertTrue(
                    150 <= word_count <= 700,
                    f"{path.relative_to(REPO_ROOT).as_posix()}: {word_count} "
                    "words (wc -w equivalent), outside TEMPLATE.md's pinned "
                    "150-700 band for harness-index/parity fragments",
                )
        self.assertGreaterEqual(
            checked, 3, "expected the three harness index fragments plus parity.md"
        )


class WordBudgetGuardFalsifiabilityTests(unittest.TestCase):
    """Proves the two guards above are not vacuous, per this dispatch's
    instruction to 'prove any new or changed guard is falsifiable with a
    temp-fixture probe before trusting it.' Each sub-test constructs a
    fixture the real guard must reject, and a control the real guard must
    accept, using the exact same counting helpers
    (_prose_word_count/len(text.split())) and the same repo_root-parameterized
    iteration (_existing_per_skill_fragments/_existing_index_and_parity_fragments)
    the production test classes above use -- not a reimplementation."""

    def test_prose_word_count_excludes_fenced_blocks_and_table_rows(self):
        # 100 prose words, then a 500-word fenced block and a pipe-table row
        # that together would blow any single 450-word ceiling if counted.
        text = (
            ("word " * 100).strip()
            + "\n\n```text\n"
            + ("x " * 500).strip()
            + "\n```\n\n"
            + "| a | " + ("y " * 60).strip() + " |\n"
        )
        self.assertEqual(
            _prose_word_count(text),
            100,
            "prose word count must exclude fenced-block and pipe-table-row "
            "text, or the two-ceiling fix does not actually close the "
            "table-tax hole the gate identified",
        )

    def test_guard_rejects_a_fragment_whose_prose_exceeds_450_even_though_total_is_in_band(self):
        """The critical falsifiability case: a fragment with NO table or
        fence at all, so prose == total, sized at 470 words -- inside the
        new 150-550 TOTAL band (so a total-only check would wave it
        through) but over the 450-word PROSE ceiling. If this fixture does
        not fail the guard, the prose ceiling is not actually being
        enforced and the two-number fix is cosmetic."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_minimal_harness_roots(root)
            skill_dir = root / "skills" / "widget"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: widget\ndescription: A widget skill.\n---\nBody.\n",
                encoding="utf-8",
            )
            fragment_path = root / "docs-src" / "fragments" / "skills" / "claude" / "widget.md"
            fragment_path.parent.mkdir(parents=True)
            fragment_path.write_text(("prose " * 470).strip() + "\n", encoding="utf-8")

            found = list(_existing_per_skill_fragments(repo_root=root))
            self.assertEqual(len(found), 1)
            _harness, _name, _path, text = found[0]
            word_count = len(text.split())
            prose_count = _prose_word_count(text)
            self.assertTrue(150 <= word_count <= 550, "fixture must be inside the total band")
            self.assertGreater(
                prose_count,
                450,
                "fixture must violate the prose ceiling for this probe to mean anything",
            )

    def test_guard_accepts_a_table_heavy_fragment_the_old_single_ceiling_would_have_rejected(self):
        """Mirrors the real defect: `route.md` is 459 total / 450 prose --
        legitimately over the OLD 450 ceiling but inside both NEW ones. This
        proves the widened total band does not silently re-admit unbounded
        prose: prose here stays at exactly 450, the tight edge."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_minimal_harness_roots(root)
            skill_dir = root / "skills" / "widget"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: widget\ndescription: A widget skill.\n---\nBody.\n",
                encoding="utf-8",
            )
            fragment_path = root / "docs-src" / "fragments" / "skills" / "claude" / "widget.md"
            fragment_path.parent.mkdir(parents=True)
            table = "| a | b |\n| --- | --- |\n" + "\n".join(
                f"| {i} | {'w' * 3} |" for i in range(9)
            )
            fragment_path.write_text(
                ("prose " * 450).strip() + "\n\n" + table + "\n", encoding="utf-8"
            )

            found = list(_existing_per_skill_fragments(repo_root=root))
            _harness, _name, _path, text = found[0]
            word_count = len(text.split())
            prose_count = _prose_word_count(text)
            self.assertTrue(150 <= word_count <= 550, "total must land inside the new band")
            self.assertLessEqual(prose_count, 450, "prose must stay within the unmoved ceiling")
            self.assertGreater(
                word_count,
                450,
                "fixture must exceed the OLD 450 total ceiling to prove the widening matters",
            )

    def test_index_or_parity_guard_rejects_a_701_word_fragment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "docs-src" / "fragments" / "skills" / "claude" / "index.md"
            index_path.parent.mkdir(parents=True)
            index_path.write_text(("word " * 701).strip() + "\n", encoding="utf-8")

            found = list(_existing_index_and_parity_fragments(repo_root=root))
            self.assertEqual(len(found), 1)
            _label, _path, text = found[0]
            word_count = len(text.split())
            self.assertGreater(
                word_count,
                700,
                "fixture must actually violate the 700-word ceiling for this probe to mean anything",
            )

    @staticmethod
    def _write_minimal_harness_roots(root):
        """skill_inventory() raises unless all three harness roots exist as
        directories, even if empty -- create the two we do not populate."""
        for parts in db._HARNESS_SKILL_ROOTS.values():
            (root.joinpath(*parts)).mkdir(parents=True, exist_ok=True)


class PerSkillFragmentHeadingOrderTests(unittest.TestCase):
    """TEMPLATE.md 'The six required sections': 'Every per-skill fragment
    carries exactly these six ### headings, in this order, with no others.'
    bin/docs_build.py's validate_fragment only rejects reserved h1/h2
    headings -- it does not check that the six pinned h3 headings are
    present, correctly ordered, or exclusive of extras, so a fragment could
    pass `docs_build.py check` while silently missing, reordering, or adding
    to the pinned section set."""

    def test_headings_are_exactly_the_six_pinned_ones_in_order(self):
        checked = 0
        for harness, name, path, text in _existing_per_skill_fragments():
            checked += 1
            with self.subTest(harness=harness, name=name):
                self.assertEqual(
                    tuple(_h3_heading_lines(text)),
                    SIX_HEADINGS,
                    f"{path.relative_to(REPO_ROOT).as_posix()}: h3 headings do not "
                    "exactly match TEMPLATE.md's six pinned headings in order",
                )
        self.assertGreaterEqual(checked, 3)


class PerSkillFragmentNotForBulletTests(unittest.TestCase):
    """TEMPLATE.md 'The six required sections' / '### When to reach for it':
    'At least one bullet must be a "not for..." bullet... a real boundary...
    not a throwaway disclaimer.' The semantic judgment ('is this a real
    boundary') is not machine-checkable, but the convention all three T7
    pilots (and TEMPLATE.md's own worked example) use -- a bullet opening
    with bold 'Not' -- is: this is a mechanical PROXY for the rule, not the
    rule itself, and is stated as such."""

    def test_at_least_one_bold_not_bullet_in_when_to_reach_for_it(self):
        checked = 0
        for harness, name, path, text in _existing_per_skill_fragments():
            checked += 1
            section = _section_body(
                text, "### When to reach for it", "### Worked example"
            )
            with self.subTest(harness=harness, name=name):
                self.assertRegex(
                    section,
                    r"(?m)^-\s+\*\*Not\*\*",
                    f"{path.relative_to(REPO_ROOT).as_posix()}: no '- **Not** ...' "
                    "bullet found in '### When to reach for it'",
                )
        self.assertGreaterEqual(checked, 3)


class FragmentLinkSpliceContextTests(unittest.TestCase):
    """TEMPLATE.md 'The link contract -- read this before you type a link':
    'Fragments are spliced byte-verbatim. The generator does not rewrite
    your links... Write links relative to the page the fragment lands on' --
    and the parity fragment's splice target is ONE LEVEL UP from every other
    fragment's. This is a source-level check on docs-src/fragments/ itself,
    independent of whether docs-site/ has already been rebuilt --
    complementing (not duplicating) tests/test_docs_site.py's
    OfflineLinkIntegrityTests, which only walks the already-committed
    generated pages and would stay silent about a dangling fragment link
    until the next rebuild surfaced it."""

    def test_every_relative_link_resolves_from_its_actual_splice_location(self):
        checked = 0
        broken = []
        docs_site_resolved = DOCS_SITE_ROOT.resolve()
        for rel in _all_existing_fragment_rel_paths():
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            splice_dir = _splice_target_dir(rel)
            for target in _iter_inline_link_targets(text):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                if target.startswith("#"):
                    continue
                path_part = target.split("#", 1)[0]
                if not path_part:
                    continue
                checked += 1
                resolved = (splice_dir / path_part).resolve()
                try:
                    resolved.relative_to(docs_site_resolved)
                    under_site = True
                except ValueError:
                    under_site = False
                if not (under_site and resolved.is_file()):
                    broken.append(
                        f"{rel} -> {target} (resolved against splice dir "
                        f"{splice_dir.relative_to(REPO_ROOT)}, expected an existing "
                        "file there)"
                    )
        self.assertEqual(broken, [], f"dangling fragment link(s): {broken!r}")
        self.assertGreater(checked, 0, "expected at least one relative link across the fragments")


class FragmentNoStaleNumbersTests(unittest.TestCase):
    """GUARDRAILS.md 'Numbers, facts, and honesty' + TEMPLATE.md 'Mechanical
    rules': 'No numbers that go stale. No prices, ratios, plan allowances,
    model ids, cached dates, or roster counts anywhere in a fragment...
    Aliases and tier names (cheap, mid, strong, frontier; haiku/sonnet/
    opus/fable...) are fine... because they do not carry a value.'
    Mechanically checkable subset: a literal dollar figure ($<digit>) or a
    vendor/tier alias immediately followed by a version number (e.g.
    'sonnet-5', 'gpt-5.6-sol', 'claude-opus-4.8') outside a fenced code
    block. Bare aliases with no trailing digit are explicitly permitted and
    are not flagged."""

    _DOLLAR_RE = re.compile(r"\$\d")
    _VERSIONED_MODEL_RE = re.compile(
        r"\b(?:claude|gpt|gemini|sonnet|opus|haiku|fable|kimi|mai|raptor)-[0-9]",
        re.IGNORECASE,
    )
    # T7b / P3 gate ruling ("The two HIGH findings nobody had caught", #2 in
    # NOTES.md's PHASE 3 GATE VERDICT): the outside-fences-only _DOLLAR_RE
    # above lets a decimal dollar amount like "$17.22" hide inside a fenced
    # code block and still pass, even though TEMPLATE.md's amended rule ("No
    # dollar figure, in prose or inside a fence") and GUARDRAILS forbid it
    # everywhere. Fixed by a SEPARATE, fence-INCLUSIVE pattern that requires
    # a decimal point -- \d+\.\d -- rather than widening _DOLLAR_RE itself:
    # the gate's exact instruction was "do NOT extend the existing \$\d to
    # inside fences -- it would match shell positionals like $1", which a
    # worked example legitimately contains (see docs-src/fragments/skills/
    # codex/doctor.md's "$POLYTROPOS_ROOT" and codex/index.md's "$route").
    _DOLLAR_AMOUNT_RE = re.compile(r"\$\d+\.\d")

    @staticmethod
    def _non_fenced_text(text):
        lines = text.splitlines(keepends=True)
        flags = db._fence_flags(lines)
        return "".join(line for line, in_fence in zip(lines, flags) if not in_fence)

    def test_no_dollar_figures_or_versioned_model_ids_outside_fences(self):
        checked = 0
        for rel in _all_existing_fragment_rel_paths():
            checked += 1
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            body = self._non_fenced_text(text)
            with self.subTest(fragment=rel):
                dollar_hits = self._DOLLAR_RE.findall(body)
                self.assertEqual(
                    dollar_hits, [], f"{rel}: dollar figure(s) found: {dollar_hits!r}"
                )
                model_hits = self._VERSIONED_MODEL_RE.findall(body)
                self.assertEqual(
                    model_hits, [], f"{rel}: versioned model id(s) found: {model_hits!r}"
                )
        self.assertGreaterEqual(checked, 7, "expected all 7 currently-committed fragments")

    def test_no_decimal_dollar_amount_anywhere_including_inside_fences(self):
        """TEMPLATE.md 'No dollar figure, in prose or inside a fence.' Runs
        against the FULL text (fences included) -- the gap the P3 gate found
        in the outside-fences-only check above."""
        checked = 0
        for rel in _all_existing_fragment_rel_paths():
            checked += 1
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(fragment=rel):
                hits = self._DOLLAR_AMOUNT_RE.findall(text)
                self.assertEqual(
                    hits,
                    [],
                    f"{rel}: decimal dollar amount found (prose or fence): {hits!r}",
                )
        self.assertGreaterEqual(checked, 7, "expected all 7 currently-committed fragments")


class DollarAmountGuardFalsifiabilityTests(unittest.TestCase):
    """Proves the new fence-inclusive guard actually closes the gap the P3
    gate found, and proves it the gate's own way: a fenced '$17.22' must be
    invisible to the OLD outside-fences-only check and caught by the NEW
    one, while an un-decimaled shell positional like '$1' inside a fence
    must NOT be caught by the new one (the gate's explicit reason for using
    \\$\\d+\\.\\d instead of widening \\$\\d itself)."""

    _DOLLAR_RE = FragmentNoStaleNumbersTests._DOLLAR_RE
    _DOLLAR_AMOUNT_RE = FragmentNoStaleNumbersTests._DOLLAR_AMOUNT_RE

    @staticmethod
    def _non_fenced_text(text):
        lines = text.splitlines(keepends=True)
        flags = db._fence_flags(lines)
        return "".join(line for line, in_fence in zip(lines, flags) if not in_fence)

    def test_fenced_decimal_dollar_amount_invisible_to_old_check_caught_by_new_one(self):
        text = (
            "### Cost & safety\n\n"
            "See the worked example below.\n\n"
            "```text\n"
            "planned at $17.22, actual $100.00\n"
            "```\n"
        )
        old_check_body = self._non_fenced_text(text)
        self.assertEqual(
            self._DOLLAR_RE.findall(old_check_body),
            [],
            "fixture is invalid: the fenced dollar amount must be absent "
            "from the outside-fences-only body, or this does not reproduce "
            "the gap the gate found",
        )
        self.assertTrue(
            self._DOLLAR_AMOUNT_RE.search(text),
            "the fence-inclusive guard must catch a decimal dollar amount "
            "hidden inside a fenced code block",
        )

    def test_shell_positional_dollar_one_inside_a_fence_is_not_flagged(self):
        text = (
            "### Worked example\n\n"
            "```bash\n"
            'python3 "$POLYTROPOS_ROOT/bin/harness_select.py" doctor --arg $1\n'
            "```\n"
        )
        self.assertIsNone(
            self._DOLLAR_AMOUNT_RE.search(text),
            "a shell positional ($1, no decimal point) must not be flagged "
            "by the decimal-amount guard -- this is exactly why the gate "
            "said not to widen \\$\\d itself into fences",
        )


class MemoryDuplicateMessageQuotationTests(unittest.TestCase):
    """T12 test-author finding (content-truth, not structure): TEMPLATE.md's
    '### Failure modes & fallbacks' section requires quoting a skill's own
    failure vocabulary EXACTLY where it has one -- "those words are what the
    reader will see on screen, and several are pinned by tests. Do not soften
    a refusal into a suggestion." bin/memory_store.py's `add` duplicate-exit
    message is exactly such a state string, and skills/memory/SKILL.md
    already quotes it verbatim ("If `add` exits 2 with `duplicate of
    [<slug>] -- update it instead (or pass --force)`, UPDATE").

    This derives the message's static text from the ENGINE SOURCE at test
    time via regex -- never a hardcoded literal, so a future engine wording
    change does not silently invalidate this guard -- and checks that both
    the skill card and the claude/memory fragment still quote it
    byte-for-byte. Proven necessary live: as authored,
    docs-src/fragments/skills/claude/memory.md quotes `(or --force)`,
    dropping the word "pass" that the engine (and the skill card) actually
    print -- a state the reader will never see on screen."""

    _DUP_RE = re.compile(r'duplicate of \[\{\w+\}\](?P<suffix>[^"]*)"')

    def _derive_suffix(self):
        source = (BIN_DIR / "memory_store.py").read_text(encoding="utf-8")
        matches = self._DUP_RE.findall(source)
        self.assertTrue(
            matches,
            "could not find the `duplicate of [...]` f-string in "
            "bin/memory_store.py -- fixture needs updating, or the engine "
            "no longer prints this message this way",
        )
        # Every occurrence in the engine (the `add` and `update` exits both
        # hit this branch) must agree, so there is exactly ONE message to
        # quote, never several worded differently.
        unique = set(matches)
        self.assertEqual(
            len(unique),
            1,
            f"bin/memory_store.py prints multiple differently-worded "
            f"duplicate messages: {sorted(unique)!r}",
        )
        return "]" + matches[0]

    def test_skill_card_quotes_the_engines_duplicate_message_verbatim(self):
        suffix = self._derive_suffix()
        body = (REPO_ROOT / "skills/memory/SKILL.md").read_text(encoding="utf-8")
        self.assertIn(
            suffix,
            body,
            f"skills/memory/SKILL.md does not quote the engine's duplicate "
            f"message verbatim (expected suffix {suffix!r})",
        )

    def test_fragment_quotes_the_engines_duplicate_message_verbatim(self):
        path = REPO_ROOT / "docs-src/fragments/skills/claude/memory.md"
        if not path.is_file():
            self.skipTest("claude/memory fragment not yet written")
        suffix = self._derive_suffix()
        text = path.read_text(encoding="utf-8")
        self.assertIn(
            suffix,
            text,
            f"docs-src/fragments/skills/claude/memory.md does not quote the "
            f"engine's duplicate message verbatim (expected suffix "
            f"{suffix!r}) -- TEMPLATE.md requires quoting a skill's own "
            f"failure vocabulary exactly, not paraphrasing it, because "
            f"those are the words the reader will see on screen",
        )


class CopilotArchitectPlanningCostHonestyTests(unittest.TestCase):
    """T13's Copilot honesty law, stated in TASKS.md's own words: 'the
    ### Cost & safety section must distinguish free/read-only operations
    from AIC-spending dispatches (copilot -p spends ... and no example may
    imply it is free)'.

    copilot/.github/skills/architect/SKILL.md's own 'Model honesty' section
    instructs the reader to, before architecting anything nontrivial, either
    switch the session to the frontier tier -- the single most expensive
    lane on the whole roster -- or 'hand the whole job to `copilot --agent
    architect`', a real dispatch whose frontmatter pin carries the frontier
    model. That is the opposite of a free operation: the card's own design
    intent for this skill is that planning quality is worth deliberately
    spending on the priciest tier.

    Both assertions below are DERIVED from the live card text rather than
    hardcoded, so this guard cannot pass vacuously if the card's wording
    changes -- the first test proves the premise (the card really does
    recommend a paid frontier dispatch for planning) before the second
    checks the fragment does not contradict it."""

    _CARD = REPO_ROOT / "copilot/.github/skills/architect/SKILL.md"
    _FRAGMENT = REPO_ROOT / "docs-src/fragments/skills/copilot/architect.md"
    _SECTION_RE = re.compile(
        r"### Cost & safety\n\n(?P<body>.*?)\n\n### Related", re.DOTALL
    )

    def test_card_recommends_a_paid_frontier_dispatch_for_planning(self):
        card = self._CARD.read_text(encoding="utf-8")
        self.assertIn(
            "frontier tier",
            card,
            "copilot/architect's Model honesty section no longer names the "
            "frontier tier -- this test's premise needs re-deriving before "
            "trusting its second assertion",
        )
        self.assertIn(
            "copilot --agent architect",
            card,
            "copilot/architect no longer documents a same-named paid agent "
            "dispatch -- this test's premise needs re-deriving before "
            "trusting its second assertion",
        )

    def test_fragment_cost_safety_does_not_call_planning_unconditionally_free(self):
        if not self._FRAGMENT.is_file():
            self.skipTest("copilot/architect fragment not yet written")
        text = self._FRAGMENT.read_text(encoding="utf-8")
        m = self._SECTION_RE.search(text)
        self.assertIsNotNone(
            m, "could not locate a '### Cost & safety' ... '### Related' "
            "section in docs-src/fragments/skills/copilot/architect.md"
        )
        section = m.group("body")
        self.assertNotIn(
            "is free",
            section,
            "docs-src/fragments/skills/copilot/architect.md's Cost & safety "
            "section claims planning 'is free', but copilot/architect's own "
            "card recommends running it on the frontier tier (the single "
            "most AIC-expensive lane on the roster) or via a paid `copilot "
            "--agent architect` dispatch for anything nontrivial -- that is "
            "real AI-Credit spend, not a free operation, and TASKS.md's "
            "Copilot honesty law forbids an example that implies a dispatch "
            "is free",
        )


class CodexArchitectPlanningSpendLocationTests(unittest.TestCase):
    """T14 dispatch note (docs-site TASKS.md): 'the implementer says the
    Codex card, unlike Copilot's, has NO "switch to the frontier tier before
    planning" instruction, and that real spend lands later at $execute's
    dispatch.' This is the exact analogue of
    CopilotArchitectPlanningCostHonestyTests above, but for the OPPOSITE
    premise: codex/skills/architect/SKILL.md's own 'Dispatch, model
    selection, and the placeholder' section says the skill carries no
    `model:` pin -- the desktop app supplies its own model -- and that
    real dispatch happens only later, when bin/codex_execute.py resolves a
    kit task's model and passes it to `codex exec --model <id>`. Both
    assertions below are derived from the live card text before the
    fragment is checked against them, so this cannot pass vacuously if the
    card's wording changes."""

    _CARD = REPO_ROOT / "codex/skills/architect/SKILL.md"
    _FRAGMENT = REPO_ROOT / "docs-src/fragments/skills/codex/architect.md"

    def test_card_states_no_model_pin_and_desktop_supplies_its_own(self):
        card = self._CARD.read_text(encoding="utf-8")
        self.assertIn(
            "This skill carries no `model:` pin",
            card,
            "codex/architect no longer states its no-model-pin design -- "
            "this test's premise needs re-deriving before trusting the "
            "fragment checks below",
        )
        self.assertIn("the desktop app supplies its own model", card)

    def test_card_places_real_dispatch_at_codex_execute_time(self):
        card = self._CARD.read_text(encoding="utf-8")
        self.assertIn("bin/codex_execute.py", card)
        self.assertIn("codex exec --model", card)

    def test_fragment_does_not_claim_a_planning_time_frontier_switch(self):
        if not self._FRAGMENT.is_file():
            self.skipTest("codex/architect fragment not yet written")
        flat = " ".join(self._FRAGMENT.read_text(encoding="utf-8").split())
        # The Copilot-specific instruction this harness's own card does not
        # carry -- if this ever appears, the fragment invented a spend point
        # the card doesn't have (T13's defect, mirrored onto Codex).
        self.assertNotIn("switch the session to the frontier tier", flat)
        self.assertNotIn("switch to the frontier tier", flat)

    def test_fragment_cost_safety_places_spend_at_execute_not_at_planning(self):
        if not self._FRAGMENT.is_file():
            self.skipTest("codex/architect fragment not yet written")
        text = self._FRAGMENT.read_text(encoding="utf-8")
        section = _section_body(text, "### Cost & safety", "### Related")
        flat = " ".join(section.split())
        self.assertIn("codex_execute.py", flat)
        self.assertIn("codex exec", flat)
        # The section must not assert that writing the kit itself spends or
        # dispatches -- only that the LATER execute step does.
        self.assertNotIn("writing the kit spends", flat.lower())
        self.assertNotIn("writing the kit dispatches", flat.lower())


class CodexBenchRoutingFragmentDispositionTests(unittest.TestCase):
    """T14 priority 4: bench-routing.md must not contradict T11's enrich.
    tests/test_docs_skill_dispositions.py's CodexBenchRoutingDispositionTests
    already pins the SKILL.md side against the real argparse source:
    `compare` has no `--harness` flag, `roles` does. This is the FRAGMENT-side
    guard -- the fragment is spliced onto the same page as that card, so an
    invented `compare --harness` form here would mislead a reader even with
    the card correct just below it."""

    _FRAGMENT = REPO_ROOT / "docs-src/fragments/skills/codex/bench-routing.md"

    def test_compare_genuinely_has_no_harness_flag_in_the_real_parser(self):
        self.assertNotIn(
            "--harness", _option_strings(_subparser(bench_routing, "compare"))
        )

    def test_roles_genuinely_has_harness_flag_for_contrast(self):
        self.assertIn(
            "--harness", _option_strings(_subparser(bench_routing, "roles"))
        )

    def test_fragment_never_shows_compare_taking_dashharness(self):
        if not self._FRAGMENT.is_file():
            self.skipTest("codex/bench-routing fragment not yet written")
        text = self._FRAGMENT.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "compare" in line and "--harness" in line:
                self.fail(
                    f"docs-src/fragments/skills/codex/bench-routing.md:{lineno} "
                    f"implies `compare` takes --harness, but the real parser "
                    f"has no such option: {line!r}"
                )

    def test_fragment_states_compare_lacks_the_harness_flag(self):
        if not self._FRAGMENT.is_file():
            self.skipTest("codex/bench-routing fragment not yet written")
        flat = " ".join(self._FRAGMENT.read_text(encoding="utf-8").split())
        self.assertIn("no `--harness` flag", flat)


class CodexContextWeightWatchConstraintsFlagFormTests(unittest.TestCase):
    """T14 priority 5: context-weight.md's `watch`/`constraints` precision.
    `watch` takes a POSITIONAL harness argument (default 'claude') and has
    no `--harness` option; `--harness` belongs to `constraints`. AUDIT's own
    prose says 'watch is Claude-only' and 'constraints --harness codex can
    only return the fidelity-limit line' -- the dispatch note warns that a
    prior fragment (T13, on a different skill) shipped a bold headword
    naming a non-existent flag form, so this checks the actual engine
    parser rather than trusting either AUDIT's or the fragment's prose."""

    _FRAGMENT = REPO_ROOT / "docs-src/fragments/skills/codex/context-weight.md"

    def test_watch_has_a_positional_harness_and_no_dashharness_option(self):
        sub = _subparser(context_weight, "watch")
        self.assertNotIn("--harness", _option_strings(sub))
        self.assertIn("harness", _positional_dests(sub))

    def test_constraints_genuinely_has_dashharness_option(self):
        sub = _subparser(context_weight, "constraints")
        self.assertIn("--harness", _option_strings(sub))

    def test_fragment_never_shows_watch_taking_dashharness(self):
        if not self._FRAGMENT.is_file():
            self.skipTest("codex/context-weight fragment not yet written")
        text = self._FRAGMENT.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "watch" in line and "--harness" in line:
                self.fail(
                    f"docs-src/fragments/skills/codex/context-weight.md:{lineno} "
                    f"implies `watch` takes --harness, but it is a positional "
                    f"argument with no such option: {line!r}"
                )

    def test_fragment_shows_constraints_with_the_real_dashharness_form(self):
        if not self._FRAGMENT.is_file():
            self.skipTest("codex/context-weight fragment not yet written")
        flat = " ".join(self._FRAGMENT.read_text(encoding="utf-8").split())
        self.assertIn("constraints --harness codex", flat)


class CodexMemoryFragmentScopeAndNegativePinTests(unittest.TestCase):
    """T14 priority 3: memory.md and the recall-only scope. AUDIT's T14
    carry-forward (P3 finding 6) requires the fragment to say plainly that
    the Codex memory card is deliberately recall-only, so the parity row
    reads as a scoped port rather than a half-finished one -- derived here
    against the Claude sibling's own card, which genuinely documents
    add/update/remove/list in addition to review. Also re-checks, at the
    fragment level, the five negative pins tests/test_codex_memory_skill.py
    and tests/test_docs_skill_dispositions.py already enforce on the
    SKILL.md: a fragment that casually mentions any of these five strings
    while explaining the card would misrepresent what the card actually
    does."""

    _CLAUDE_CARD = REPO_ROOT / "skills/memory/SKILL.md"
    _FRAGMENT = REPO_ROOT / "docs-src/fragments/skills/codex/memory.md"
    _NEGATIVE_PINS = ("Path.home", "subprocess", "urlopen", "codex exec", "pricing.json")

    def test_claude_sibling_genuinely_documents_add_update_remove_list(self):
        card = self._CLAUDE_CARD.read_text(encoding="utf-8")
        for verb in ("memory_store.py\" add", "memory_store.py\" update",
                     "memory_store.py\" remove", "memory_store.py\" list"):
            self.assertIn(
                verb, card,
                "skills/memory/SKILL.md no longer documents the full "
                "add/update/remove/list surface -- this test's premise "
                "(the Codex card is a deliberately NARROWER scope, not a "
                "half-port) needs re-deriving",
            )

    def test_codex_card_genuinely_documents_recall_and_review_only(self):
        card = (REPO_ROOT / "codex/skills/memory/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("memory_recall.py", card)
        self.assertIn("memory_store.py\" review", card)
        for verb in ("memory_store.py\" add", "memory_store.py\" update",
                     "memory_store.py\" remove", "memory_store.py\" list"):
            self.assertNotIn(verb, card)

    def test_fragment_states_the_recall_only_scope_plainly(self):
        if not self._FRAGMENT.is_file():
            self.skipTest("codex/memory fragment not yet written")
        flat = " ".join(self._FRAGMENT.read_text(encoding="utf-8").split())
        self.assertIn("recall-only", flat)
        # Must read as a scope decision, not an apology for an incomplete
        # port -- AUDIT's own words for the required framing.
        self.assertNotIn("not yet implemented", flat)
        self.assertNotIn("not yet ported", flat)
        self.assertNotIn("half-finished", flat)
        self.assertNotIn("half-ported", flat)

    def test_fragment_carries_none_of_the_five_negative_pins(self):
        if not self._FRAGMENT.is_file():
            self.skipTest("codex/memory fragment not yet written")
        text = self._FRAGMENT.read_text(encoding="utf-8")
        for banned in self._NEGATIVE_PINS:
            with self.subTest(banned=banned):
                self.assertNotIn(banned, text)


class CodexSubscriptionNeverABillCoOccurrenceTests(unittest.TestCase):
    """Durable cross-fragment guard (T14's closing instruction: 'consider one
    durable cross-harness guard that would generalize ... only if you can
    make it non-brittle'). Considered and rejected: a blanket ban on the
    literal phrase 'is free' anywhere in a '### Cost & safety' section --
    docs-src/fragments/skills/codex/journal.md legitimately says
    'Collecting is free, model-free, and strictly read-only', which is TRUE
    (the collector dispatches no model) and is exactly the honest
    free-vs-paid contrast TEMPLATE.md asks '### Cost & safety' to draw; a
    blanket guard would flag correct writing.

    The narrower, non-brittle version implemented here targets the actual
    CLAUDE.md invariant instead: whenever a Codex fragment's prose invokes
    ChatGPT-plan billing language (mentions both 'ChatGPT' and a dollar/burn
    figure), the file must also carry the 'never a bill' / 'not a bill'
    label somewhere -- the exact contract `bin/codex_pricing.py` and
    `data/pricing.codex.json`'s own honesty design encode. This cannot
    false-positive on a fragment that never raises ChatGPT billing at all
    (journal.md, architect.md, bench-routing.md, context-weight.md, and
    memory.md all pass trivially, unchecked, because none of them says
    'ChatGPT')."""

    FRAGMENT_NAMES = (
        "architect", "bench-routing", "context-weight", "effort", "escalate",
        "execute", "frontier-check", "journal", "memory", "route", "usage",
    )

    def test_every_fragment_mentioning_chatgpt_billing_also_labels_the_proxy(self):
        offenders = []
        checked_any = False
        for name in self.FRAGMENT_NAMES:
            path = REPO_ROOT / f"docs-src/fragments/skills/codex/{name}.md"
            if not path.is_file():
                continue
            flat = " ".join(path.read_text(encoding="utf-8").split())
            if "ChatGPT" not in flat:
                continue
            checked_any = True
            if "dollar" not in flat and "burn" not in flat:
                continue
            if "never a bill" not in flat and "not a bill" not in flat:
                offenders.append(name)
        if not checked_any:
            self.skipTest("no codex fragment yet mentions ChatGPT billing")
        self.assertEqual(
            offenders, [],
            f"fragment(s) discuss ChatGPT-mode dollar/burn framing without "
            f"the never/not-a-bill label the subscription-honesty law "
            f"requires: {offenders!r}",
        )


if __name__ == "__main__":
    unittest.main()
