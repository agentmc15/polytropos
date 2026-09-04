"""Stdlib unittest regression suite for T3 of the docs-site kit: the GitHub
Actions workflow (.github/workflows/docs-site.yml).

These tests are derived from the T3 brief in .claude/kits/docs-site/TASKS.md
("### T3 — GitHub Actions workflow: build --strict + deploy to Pages") and
PLAN.md's D7 ("CI/deploy shape"), NOT from reading the implementer's actual
workflow file first. The task's own verify command already proves a subset
of the pinned strings exist (mkdocs build --strict, the test_docs_*.py drift
gate, upload-pages-artifact@v3, deploy-pages@v4, id-token: write,
path: site-build, docs-src/requirements.txt, no tabs, exactly one workflow
file). This file targets what that grep chain does NOT cover:

  - the top-level `name: docs-site` key
  - the trigger shape (push to main + workflow_dispatch)
  - the full top-level `permissions:` block (contents: read, pages: write —
    the verify command only checks id-token: write)
  - the top-level `concurrency:` block (group: pages, cancel-in-progress)
  - pinned action versions/inputs for checkout and setup-python, and the
    pip-install step
  - ORDER: the brief pins the drift-gate unittest run as happening BEFORE
    `mkdocs build --strict` ("a stale generated page fails the deploy") —
    the verify grep chain proves both strings exist but not their order
  - the upload-pages-artifact step's `path: site-build` is on that step,
    not just present anywhere in the file
  - the deploy job's shape: needs: build, environment name + url expression,
    a single step using deploy-pages@v4 with id: deployment
  - the header comment's two pinned facts (Pages source setting + "only
    other place that knows about mkdocs" claim)
  - the gotcha ban: no step invokes claude/copilot/codex/gh, nothing
    references secrets.
  - two-space indentation as a specific unit (the verify command only rules
    out tabs, not odd-width indentation)

No YAML parser is used (stdlib has no YAML, and the brief itself says the
verify is structural / string-based) — every check here is line/regex-based
against the raw text.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO / ".github" / "workflows"
WORKFLOW = WORKFLOW_DIR / "docs-site.yml"


def _block(text, start_key):
    """Return the block of text starting at the first non-blank line whose
    stripped content equals start_key (stripped) or begins with it, running
    until the next non-blank line whose leading-whitespace count is <= the
    start line's own leading-whitespace count (a sibling or shallower key),
    or EOF. Works for both top-level (column-0) keys and nested keys (e.g.
    finding "build:" inside a "jobs:" block already isolated by a prior
    _block call) — purely line-based, no YAML parsing."""
    lines = text.splitlines()
    target = start_key.strip()
    start = None
    start_indent = None
    for i, line in enumerate(lines):
        if line.strip() == "":
            continue
        candidate = line.strip()
        if candidate == target or candidate.startswith(target):
            start = i
            start_indent = len(line) - len(line.lstrip(" "))
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.strip() == "":
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent <= start_indent:
            end = i
            break
    return "\n".join(lines[start:end])


def _line_index_containing(lines, needle):
    for i, line in enumerate(lines):
        if needle in line:
            return i
    return None


class WorkflowFileExistsTests(unittest.TestCase):
    def test_file_exists(self):
        self.assertTrue(
            WORKFLOW.is_file(),
            ".github/workflows/docs-site.yml must exist",
        )

    def test_docs_site_workflow_file_present(self):
        """Relaxed (Phase 1 review carry-forward, F1 review item F4): the original
        version of this test pinned '.github/workflows contains ONLY
        docs-site.yml' forever, which would fail this kit's own drift gate the
        moment any OTHER CI workflow is later added to the repo. The T3
        acceptance ("no other workflow files created") was scoped to what T3
        itself added, not a permanent ceiling on .github/workflows/ — so this
        now asserts only what this kit actually needs: docs-site.yml exists."""
        self.assertTrue(WORKFLOW_DIR.is_dir())
        self.assertTrue(
            (WORKFLOW_DIR / "docs-site.yml").is_file(),
            ".github/workflows/docs-site.yml must exist",
        )


@unittest.skipUnless(WORKFLOW.is_file(), "docs-site.yml missing")
class WorkflowTopLevelShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.lines = cls.text.splitlines()

    def test_workflow_name_is_docs_site(self):
        """Brief pinned shape: 'name: docs-site'."""
        self.assertRegex(self.text, r"(?m)^name:\s*docs-site\s*$")

    def test_trigger_push_to_main(self):
        """Brief pinned shape: 'triggers: push to main + workflow_dispatch'."""
        on_block = _block(self.text, "on:") or ""
        self.assertTrue(on_block, "top-level 'on:' key must be present")
        push_block = _block(on_block, "push:") or ""
        self.assertTrue(push_block, "'on:' must have a 'push:' sub-key")
        self.assertRegex(
            push_block, r"branches:\s*\n\s*-\s*main|branches:\s*\[\s*main\s*\]",
            "push trigger must be scoped to the main branch",
        )

    def test_trigger_workflow_dispatch(self):
        on_block = _block(self.text, "on:") or ""
        self.assertRegex(on_block, r"workflow_dispatch\s*:?")

    def test_top_level_permissions_block_pinned(self):
        """Brief: 'Top-level permissions: -> contents: read, pages: write,
        id-token: write'."""
        perm_block = _block(self.text, "permissions:")
        self.assertIsNotNone(perm_block, "top-level 'permissions:' block must exist")
        self.assertRegex(perm_block, r"contents:\s*read")
        self.assertRegex(perm_block, r"pages:\s*write")
        self.assertRegex(perm_block, r"id-token:\s*write")

    def test_top_level_concurrency_block_pinned(self):
        """Brief: 'concurrency: -> group: pages, cancel-in-progress: true'."""
        conc_block = _block(self.text, "concurrency:")
        self.assertIsNotNone(conc_block, "top-level 'concurrency:' block must exist")
        self.assertRegex(conc_block, r"group:\s*pages")
        self.assertRegex(conc_block, r"cancel-in-progress:\s*true")


@unittest.skipUnless(WORKFLOW.is_file(), "docs-site.yml missing")
class WorkflowBuildJobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.lines = cls.text.splitlines()
        cls.jobs_block = _block(cls.text, "jobs:") or ""

    def test_build_job_runs_on_ubuntu_latest(self):
        build_block = _block(self.jobs_block, "build:") or ""
        self.assertTrue(build_block, "jobs.build must exist")
        self.assertRegex(build_block, r"runs-on:\s*ubuntu-latest")

    def test_checkout_action_pinned_v4(self):
        self.assertRegex(self.text, r"uses:\s*actions/checkout@v4")

    def test_setup_python_action_pinned_v5_with_312(self):
        self.assertRegex(self.text, r"uses:\s*actions/setup-python@v5")
        # python-version must be pinned to 3.12 (brief: 'python-version: "3.12"')
        self.assertRegex(self.text, r'python-version:\s*["\']?3\.12["\']?')

    def test_pip_install_requirements_step(self):
        self.assertRegex(
            self.text, r"pip install -r docs-src/requirements\.txt"
        )

    def test_drift_gate_step_present(self):
        self.assertRegex(
            self.text,
            r"python3 -m unittest discover -s tests -p ['\"]test_docs_\*\.py['\"] -v",
        )

    def test_mkdocs_build_strict_step_present(self):
        self.assertRegex(self.text, r"mkdocs build --strict")

    def test_drift_gate_precedes_mkdocs_build_strict(self):
        """Brief: the drift-gate unittest run ('a stale generated page fails
        the deploy') is listed BEFORE 'mkdocs build --strict' in the pinned
        step order. The verify grep chain proves both strings exist but not
        their relative order — this is exactly the gap it leaves open."""
        drift_idx = _line_index_containing(self.lines, "test_docs_*.py")
        strict_idx = _line_index_containing(self.lines, "mkdocs build --strict")
        self.assertIsNotNone(drift_idx, "drift-gate step must be present")
        self.assertIsNotNone(strict_idx, "mkdocs build --strict step must be present")
        self.assertLess(
            drift_idx, strict_idx,
            "the drift-gate unittest run must run BEFORE mkdocs build --strict "
            "so a stale generated page fails the deploy before a build is even "
            "attempted",
        )

    def test_upload_pages_artifact_step_has_path_site_build(self):
        """Brief: 'actions/upload-pages-artifact@v3 with path: site-build'.
        Check the path is an input on THAT step, not merely present somewhere
        else in the file."""
        idx = _line_index_containing(self.lines, "upload-pages-artifact@v3")
        self.assertIsNotNone(idx, "upload-pages-artifact@v3 step must be present")
        # the `with:`/`path:` for this step should appear within the next
        # few lines (same step block), not arbitrarily far away.
        window = "\n".join(self.lines[idx: idx + 6])
        self.assertRegex(window, r"path:\s*site-build")


@unittest.skipUnless(WORKFLOW.is_file(), "docs-site.yml missing")
class WorkflowDeployJobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.jobs_block = _block(cls.text, "jobs:") or ""
        cls.deploy_block = _block(cls.jobs_block, "  deploy:") or ""

    def test_deploy_job_exists(self):
        self.assertTrue(self.deploy_block, "jobs.deploy must exist")

    def test_deploy_needs_build(self):
        self.assertRegex(self.deploy_block, r"needs:\s*build")

    def test_deploy_environment_name_github_pages(self):
        env_block = _block(self.deploy_block, "environment:") or self.deploy_block
        self.assertRegex(env_block, r"name:\s*github-pages")

    def test_deploy_environment_url_expression(self):
        env_block = _block(self.deploy_block, "environment:") or self.deploy_block
        self.assertRegex(
            env_block,
            r"url:\s*\$\{\{\s*steps\.deployment\.outputs\.page_url\s*\}\}",
        )

    def test_deploy_pages_action_pinned_v4(self):
        self.assertRegex(self.deploy_block, r"uses:\s*actions/deploy-pages@v4")

    def test_deploy_step_id_is_deployment(self):
        self.assertRegex(self.deploy_block, r"id:\s*deployment")

    def test_deploy_job_has_a_single_step(self):
        """Brief: deploy job is 'single step actions/deploy-pages@v4'."""
        steps_block = _block(self.deploy_block, "steps:") or self.deploy_block
        step_markers = re.findall(r"(?m)^\s*-\s*(?:name:|uses:|id:)", steps_block)
        # Count actual step entries (lines starting a new list item "- ")
        step_starts = re.findall(r"(?m)^\s*-\s", steps_block)
        self.assertEqual(
            len(step_starts), 1,
            f"deploy job must have exactly one step, found {len(step_starts)} "
            f"step-start markers in:\n{steps_block}",
        )


@unittest.skipUnless(WORKFLOW.is_file(), "docs-site.yml missing")
class WorkflowHeaderCommentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        # header comment block: leading contiguous "#" lines at top of file
        lines = cls.text.splitlines()
        header_lines = []
        for line in lines:
            if line.strip().startswith("#") or line.strip() == "":
                if line.strip().startswith("#"):
                    header_lines.append(line)
                elif header_lines:
                    # blank line inside/after header; stop only on a non-comment,
                    # non-blank line below
                    continue
            else:
                break
        cls.header = "\n".join(header_lines)

    def test_header_comment_exists(self):
        self.assertTrue(
            self.header.strip(),
            "workflow must open with a header comment block",
        )

    def test_header_mentions_publish_url(self):
        self.assertIn("https://agentmc15.github.io/polytropos/", self.header)

    def test_header_mentions_pages_settings_source_switch(self):
        """Brief fact (1): 'the user sets repo Settings -> Pages -> Source to
        \"GitHub Actions\" (manual, one-time)'."""
        self.assertIn("Settings", self.header)
        self.assertIn("Pages", self.header)
        self.assertRegex(self.header, r"GitHub Actions")

    def test_header_mentions_manual_one_time_nature(self):
        self.assertRegex(self.header, r"(?i)manual|one-time|one time")

    def test_header_mentions_sole_toolchain_owner_fact(self):
        """Brief fact (2): 'this workflow is the ONLY place besides
        docs-src/requirements.txt that knows about the mkdocs toolchain'."""
        self.assertRegex(self.header, r"(?i)only")
        self.assertIn("docs-src/requirements.txt", self.header)
        self.assertRegex(self.header, r"(?i)mkdocs")


@unittest.skipUnless(WORKFLOW.is_file(), "docs-site.yml missing")
class WorkflowGotchaBanTests(unittest.TestCase):
    """Brief gotcha: 'Do not add any step that invokes claude/copilot/codex/gh
    or touches secrets.'"""

    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_no_claude_copilot_codex_gh_cli_invocation(self):
        for token in ("claude", "copilot", "codex", "gh"):
            self.assertNotRegex(
                self.text, r"\b%s\b" % token,
                f"workflow must not invoke or reference the {token!r} CLI",
            )

    def test_no_secrets_reference(self):
        self.assertNotIn(
            "secrets.", self.text,
            "workflow must not reference any secrets.* context value",
        )


@unittest.skipUnless(WORKFLOW.is_file(), "docs-site.yml missing")
class WorkflowIndentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_no_tabs(self):
        self.assertNotIn("\t", self.text, "workflow must use spaces, not tabs")

    def test_two_space_indentation_unit(self):
        """Brief acceptance: 'two-space indentation, no tabs.' Every
        indented, non-comment line's leading-space count must be an even
        number (i.e. a multiple of the 2-space unit) — an odd leading-space
        count would mean some line broke the 2-space convention (e.g. was
        indented 1, 3, or 5 spaces)."""
        bad_lines = []
        for i, line in enumerate(self.text.splitlines(), start=1):
            if not line or line.strip() == "":
                continue
            leading = len(line) - len(line.lstrip(" "))
            if leading % 2 != 0:
                bad_lines.append((i, line))
        self.assertEqual(
            bad_lines, [],
            f"lines with odd (non-2-space-unit) indentation: {bad_lines!r}",
        )


if __name__ == "__main__":
    unittest.main()
